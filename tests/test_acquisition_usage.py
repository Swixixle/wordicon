"""A provider result can settle its recorded outcome without claiming a model read it."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import wordicon_cli as cli


def sdk_shape(value):
    """Synthetic SDK objects with the same attribute shape as the provider types."""
    if isinstance(value, dict):
        return SimpleNamespace(**{key: sdk_shape(item) for key, item in value.items()})
    if isinstance(value, list):
        return [sdk_shape(item) for item in value]
    return value


def search_use(use_id):
    return {"type": "server_tool_use", "name": "web_search", "id": use_id,
            "input": {"query": "private query never copied into acquisition metadata"}}


def search_result(use_id, content):
    return {"type": "web_search_tool_result", "tool_use_id": use_id, "content": content}


def source(number=0):
    return {"type": "web_search_result", "url": f"https://example.test/{number}",
            "title": "A source title", "encrypted_content": "opaque result bytes"}


def search_error(code="max_uses_exceeded"):
    return {"type": "web_search_tool_result_error", "error_code": code}


@pytest.mark.parametrize("shape", [lambda value: value, sdk_shape], ids=["dict", "sdk-object"])
def test_one_reported_search_seven_attempts_retains_each_distinct_outcome(shape):
    blocks = []
    for index in range(7):
        use_id = f"search_{index}"
        blocks.extend([search_use(use_id), search_result(
            use_id, [source(number) for number in range(9)] if index == 0 else search_error())])
    response = {"content": blocks, "stop_reason": "end_turn", "usage": {
        "input_tokens": 40000, "output_tokens": 1200,
        "server_tool_use": {"web_search_requests": 1}}}
    record = cli.acquisition_usage(shape(response), tool_version="web_search_20260318", max_uses=1)

    assert record["web_search_requests"] == 1  # Attempts are not billed requests.
    assert len(record["search_tool_uses"]) == 7
    assert record["max_uses_requested"] == 1
    assert record["input_tokens"] == 40000
    assert record["response_stop_reason"] == "end_turn"
    assert record["cost"] == "unknown"
    first, *rest = record["search_result_outcomes"]
    assert first["outcome"] == "results_returned"
    assert first["result_count"] == 9
    assert first["tool_use_match"] == "matched"
    assert first["matched_tool_use_block_indexes"] == [0]
    assert all(item["outcome"] == "error" and item["error_code"] == "max_uses_exceeded"
               and item["result_count"] is None for item in rest)
    serialized = json.dumps(record)
    for private in ("private query", "opaque result bytes", "https://example.test", "A source title"):
        assert private not in serialized
    assert "model_read" not in record


@pytest.mark.parametrize("content,outcome,count,unknown,error", [
    ([], "empty_results", 0, 0, None),
    (search_error("unavailable"), "error", None, None, "unavailable"),
    ({"type": "web_search_tool_result_error"}, "error", None, None, None),
    (None, "unrecognized", None, None, None),
    ({"content": []}, "unrecognized", None, None, None),
    ("not a result list", "unrecognized", None, None, None),
    ([source(), {"type": "future_result"}], "unrecognized", 1, 1, None),
])
def test_empty_results_errors_and_unknown_content_never_collapse(content, outcome, count, unknown, error):
    record = cli.acquisition_usage({"content": [search_result("search_a", content)]})
    result = record["search_result_outcomes"][0]
    assert result["outcome"] == outcome
    assert result["result_count"] == count
    assert result["unrecognized_result_count"] == unknown
    assert result["error_code"] == error
    assert result["tool_use_match"] == "unmatched"
    assert record["web_search_requests"] is None
    assert record["usage_reported"] is False


def test_result_matches_only_explicit_same_kind_id_even_when_result_precedes_use():
    blocks = [search_result("later", []), search_use("later"),
              search_result("repeated", []), search_use("repeated"), search_use("repeated"),
              search_result(None, []), search_result("absent", []),
              {"type": "server_tool_use", "name": "code_execution", "id": "code"},
              search_result("code", [])]
    results = cli.acquisition_usage({"content": blocks})["search_result_outcomes"]
    assert [(item["tool_use_match"], item["matched_tool_use_block_indexes"]) for item in results] == [
        ("matched", [1]), ("ambiguous", [3, 4]), ("missing_tool_use_id", []),
        ("unmatched", []), ("unmatched", [])]


def test_provider_code_execution_retains_return_and_error_codes_separately():
    blocks = [search_use("search"), search_result("search", []),
              {"type": "server_tool_use", "name": "code_execution", "id": "code_a",
               "input": {"code": "private code"}},
              {"type": "code_execution_tool_result", "tool_use_id": "code_a", "content": {
                  "type": "code_execution_result", "return_code": 1, "content": [],
                  "stdout": "private stdout", "stderr": "private stderr"}},
              {"type": "server_tool_use", "name": "code_execution", "id": "code_b"},
              {"type": "code_execution_tool_result", "tool_use_id": "code_b", "content": {
                  "type": "code_execution_tool_result_error", "error_code": "execution_time_exceeded"}},
              {"type": "code_execution_tool_result", "content": {
                  "type": "code_execution_result", "return_code": True}}]
    record = cli.acquisition_usage(sdk_shape({"content": blocks}))
    assert len(record["search_tool_uses"]) == 1
    assert record["web_search_requests"] is None
    internal = record["provider_internal_dynamic_filtering"]
    assert internal["blocks"] == 3
    assert internal["observed"] is True
    assert len(internal["tool_uses"]) == 2
    first, second, third = internal["result_outcomes"]
    assert (first["outcome"], first["return_code"], first["tool_use_match"]) == (
        "execution_result", 1, "matched")
    assert (second["outcome"], second["error_code"]) == ("error", "execution_time_exceeded")
    assert third["outcome"] == "unrecognized"
    assert third["return_code"] is None
    assert "private" not in json.dumps(record)


@pytest.mark.parametrize("stop_reason", ["pause_turn", "max_tokens", "end_turn", None])
def test_stop_reason_and_missing_usage_are_retained_without_inventing_completion(stop_reason):
    record = cli.acquisition_usage(sdk_shape({"content": [], "stop_reason": stop_reason}))
    assert record["response_stop_reason"] == stop_reason
    assert record["usage_reported"] is False
    assert record["input_tokens"] is None
    assert record["web_search_requests"] is None
    assert record["search_outcomes_recorded"] is True
    assert record["search_result_outcomes"] == []


def test_search_usage_alone_counts_as_reported_and_unnamed_tools_are_not_search_attempts():
    record = cli.acquisition_usage({"usage": {"server_tool_use": {"web_search_requests": 0}},
                                   "content": [{"type": "server_tool_use", "id": "unknown"}]})
    assert record["usage_reported"] is True
    assert record["web_search_requests"] == 0
    assert record["input_tokens"] is None
    assert record["block_types"] == {"server_tool_use": 1}
    assert record["search_tool_uses"] == []


class TransientFailure(Exception):
    pass


class RateLimitFailure(Exception):
    response = SimpleNamespace(headers={"retry-after": "1"})


class OfflineAnthropic(cli.AnthropicAPIGateway):
    """Use the real gateway boundary with only its HTTP method replaced."""
    def __init__(self, responses):
        self.model = "offline-test-model"
        self.responses = list(responses)
        self.calls = []
        self.dispatch_events = []
        self.dispatch_hook = lambda event, **fields: self.dispatch_events.append((event, fields))

    def _retryable(self):
        return ((RateLimitFailure,), (TransientFailure,))

    def _create(self, prompt, tools=None, *, allow_truncated=False):
        self.calls.append({"prompt": prompt, "tools": tools})
        response = self.responses.pop(0)
        if isinstance(response, BaseException):
            raise response
        return response


def answer():
    return sdk_shape({"content": [{"type": "text", "text": "A recorded answer", "citations": []}],
                      "stop_reason": "end_turn", "usage": {"server_tool_use": {"web_search_requests": 1}}})


@pytest.mark.parametrize("limit", [1, 2, 3])
def test_explicit_search_budget_is_local_full_and_one_attempt(limit):
    pytest.importorskip("anthropic")
    original = dict(cli.AnthropicAPIGateway.WEB_SEARCH_TOOL)
    gateway = OfflineAnthropic([answer()])
    assert gateway.complete_with_search_budget("question", max_uses=limit) == ("A recorded answer", [])
    assert gateway.calls == [{"prompt": "question", "tools": [
        {**original, "max_uses": limit, "response_inclusion": "full"}]}]
    assert gateway.last_acquisition["max_uses_requested"] == limit
    assert cli.AnthropicAPIGateway.WEB_SEARCH_TOOL == original
    assert original["max_uses"] == 1
    assert [event for event, _ in gateway.dispatch_events] == ["attempt_intent", "attempt_end"]


@pytest.mark.parametrize("limit", [None, True, False, 0, -1, 4, "1", 1.0])
def test_invalid_explicit_search_budget_refused_before_dispatch(limit):
    gateway = OfflineAnthropic([])
    with pytest.raises(ValueError, match="max_uses"):
        gateway.complete_with_search_budget("question", max_uses=limit)
    assert gateway.calls == []
    assert gateway.dispatch_events == []


@pytest.mark.parametrize("failure,expected", [
    (TransientFailure("possibly sent"), TransientFailure),
    (RateLimitFailure("slow down"), cli.RateLimited),
    (cli.StreamInterrupted("lost before content", saw_content=False), cli.StreamInterrupted),
    (cli.StreamInterrupted("lost after content", saw_content=True), cli.StreamInterrupted),
])
def test_bounded_search_never_resets_allowance_after_ambiguous_failure(monkeypatch, failure, expected):
    pytest.importorskip("anthropic")
    monkeypatch.setattr(cli.time, "sleep", lambda *_: pytest.fail("bounded search must not retry"))
    gateway = OfflineAnthropic([failure, answer()])
    gateway.last_acquisition = {"web_search_requests": 99}  # Previous run must not survive failure.
    with pytest.raises(expected):
        gateway.complete_with_search_budget("question", max_uses=1)
    assert len(gateway.calls) == 1
    assert gateway.last_acquisition is None
    assert [event for event, _ in gateway.dispatch_events] == ["attempt_intent", "attempt_end"]
    assert gateway.dispatch_events[-1][1]["outcome"] == "error"


def test_ordinary_search_retains_one_search_default_and_three_attempt_retry_policy(monkeypatch):
    pytest.importorskip("anthropic")
    waits = []
    monkeypatch.setattr(cli.time, "sleep", waits.append)
    gateway = OfflineAnthropic([TransientFailure("one"), TransientFailure("two"), answer()])
    gateway.complete_with_search("ordinary question")
    assert len(gateway.calls) == 3
    assert all(call["tools"] == [cli.AnthropicAPIGateway.WEB_SEARCH_TOOL] for call in gateway.calls)
    assert gateway.last_acquisition["max_uses_requested"] == 1
    assert waits == [3, 6]


def test_complete_once_has_no_tools_and_no_retry(monkeypatch):
    monkeypatch.setattr(cli.time, "sleep", lambda *_: pytest.fail("complete_once must not retry"))
    success = OfflineAnthropic([answer()])
    assert success.complete_once("explain the acquired text") == "A recorded answer"
    assert success.calls == [{"prompt": "explain the acquired text", "tools": None}]
    failure = OfflineAnthropic([TransientFailure("possibly sent"), answer()])
    with pytest.raises(TransientFailure):
        failure.complete_once("explain the acquired text")
    assert len(failure.calls) == 1


def test_ordinary_complete_keeps_existing_retry_policy(monkeypatch):
    monkeypatch.setattr(cli.time, "sleep", lambda *_: None)
    gateway = OfflineAnthropic([TransientFailure("one"), TransientFailure("two"), answer()])
    assert gateway.complete("ordinary question") == "A recorded answer"
    assert len(gateway.calls) == 3
    assert all(call["tools"] is None for call in gateway.calls)


@pytest.mark.parametrize("method", ["complete_with_search_budget", "complete_once"])
def test_real_sdk_has_no_hidden_retry_and_sends_disclosed_request_settings(monkeypatch, method):
    anthropic = pytest.importorskip("anthropic")
    from anthropic import _base_client
    # The installed SDK may use httpx or httpx2; its accepted client class is
    # the one to stub, without depending on an unrelated transport package.
    httpx = getattr(_base_client, "httpx2", None) or getattr(_base_client, "httpx", None)
    assert httpx is not None, "the SDK's transport dependency changed"
    real_client = anthropic.Anthropic
    requests = []

    def respond(request):
        # An in-process transport: no sockets, credentials or provider calls.
        requests.append({"body": json.loads(request.content),
                         "timeout": request.extensions.get("timeout")})
        return httpx.Response(500, json={"type": "error", "error": {
            "type": "api_error", "message": "synthetic retryable provider error"}})

    def client_factory(**kwargs):
        # Preserve the real gateway's max_retries and timeout arguments while
        # substituting only an offline transport and an unresolvable origin.
        original_http_client = kwargs.pop("http_client", None)
        if original_http_client is not None:
            original_http_client.close()
        return real_client(**kwargs, base_url="https://provider.invalid",
                           http_client=httpx.Client(transport=httpx.MockTransport(respond)))

    monkeypatch.setenv("ANTHROPIC_API_KEY", "not-a-real-provider-key")
    monkeypatch.setattr(anthropic, "Anthropic", client_factory)
    monkeypatch.setattr(cli.time, "sleep", lambda *_: pytest.fail("no SDK or gateway retry allowed"))
    gateway = cli.AnthropicAPIGateway("offline-test-model")
    try:
        assert gateway.client.max_retries == 0
        with pytest.raises(anthropic.InternalServerError):
            if method == "complete_with_search_budget":
                gateway.complete_with_search_budget("question", max_uses=1)
            else:
                gateway.complete_once("question")
        assert len(requests) == 1
        request = requests[0]
        assert request["timeout"] == {key: 120.0 for key in ("connect", "read", "write", "pool")}
        assert request["body"]["max_tokens"] == cli.gateway_settings(gateway)["max_output_tokens"] == 24000
        assert request["body"]["stream"] is True
        if method == "complete_with_search_budget":
            assert request["body"]["tools"][0]["max_uses"] == 1
            assert request["body"]["tools"][0]["response_inclusion"] == "full"
        else:
            assert "tools" not in request["body"]
    finally:
        gateway.client.close()


@pytest.mark.parametrize("stop_reason", ["end_turn", "pause_turn"])
def test_bounded_discovery_preserves_leads_when_provider_writes_no_prose(stop_reason):
    pytest.importorskip("anthropic")
    response = sdk_shape({"content": [search_use("search"), search_result("search", [source()])],
                          "stop_reason": stop_reason,
                          "usage": {"server_tool_use": {"web_search_requests": 1}}})
    gateway = OfflineAnthropic([response])
    text, leads = gateway.complete_with_search_budget("find a source", max_uses=1)
    assert text == ""
    assert len(leads) == 1
    assert leads[0]["url"] == "https://example.test/0"
    assert gateway.last_acquisition["response_stop_reason"] == stop_reason
    assert gateway.last_acquisition["search_result_outcomes"][0]["outcome"] == "results_returned"
    assert len(gateway.calls) == 1  # A paused turn is recorded, never automatically resumed.


def test_bounded_discovery_preserves_error_only_response_without_prose():
    pytest.importorskip("anthropic")
    response = sdk_shape({"content": [search_use("search"), search_result("search", search_error())],
                          "stop_reason": "pause_turn",
                          "usage": {"server_tool_use": {"web_search_requests": 0}}})
    gateway = OfflineAnthropic([response])
    assert gateway.complete_with_search_budget("find a source", max_uses=1) == ("", [])
    assert gateway.last_acquisition["web_search_requests"] == 0
    result = gateway.last_acquisition["search_result_outcomes"][0]
    assert result["outcome"] == "error"
    assert result["error_code"] == "max_uses_exceeded"


def test_ordinary_search_still_requires_prose_but_keeps_acquisition_metadata():
    pytest.importorskip("anthropic")
    response = sdk_shape({"content": [search_use("search"), search_result("search", [source()])],
                          "stop_reason": "end_turn"})
    gateway = OfflineAnthropic([response])
    with pytest.raises(RuntimeError, match="no usable text"):
        gateway.complete_with_search("ordinary review needs an explanation")
    assert gateway.last_acquisition["search_result_outcomes"][0]["result_count"] == 1


@pytest.mark.parametrize("method", ["complete_with_search_budget", "complete_with_search", "complete_once"])
def test_only_bounded_discovery_can_consume_structured_results_at_output_ceiling(method):
    pytest.importorskip("anthropic")
    response = sdk_shape({"content": [search_use("search"), search_result("search", [source()])],
                          "stop_reason": "max_tokens",
                          "usage": {"server_tool_use": {"web_search_requests": 1}}})
    requests = []

    class SyntheticStream:
        def __enter__(self):
            return self

        def __exit__(self, *_):
            return False

        def __iter__(self):
            return iter([])

        def get_final_message(self):
            return response

    def stream(**kwargs):
        requests.append(kwargs)
        return SyntheticStream()

    gateway = OfflineAnthropic([])
    gateway.client = SimpleNamespace(messages=SimpleNamespace(stream=stream))
    # Exercise the real stream reader and its truncation gate, while the
    # synthetic stream itself is wholly offline.
    gateway._create = cli.AnthropicAPIGateway._create.__get__(gateway)
    if method == "complete_with_search_budget":
        text, leads = gateway.complete_with_search_budget("find a source", max_uses=1)
        assert text == ""
        assert [lead["url"] for lead in leads] == ["https://example.test/0"]
        assert gateway.last_acquisition["response_stop_reason"] == "max_tokens"
        assert gateway.last_acquisition["web_search_requests"] == 1
        assert gateway.last_acquisition["search_result_outcomes"][0]["result_count"] == 1
    else:
        with pytest.raises(RuntimeError, match="output ceiling"):
            getattr(gateway, method)("an explanation must be complete")
    assert len(requests) == 1
    assert "allow_truncated" not in requests[0]  # Local parsing policy is never sent to the API.
