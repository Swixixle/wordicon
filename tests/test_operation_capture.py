"""Actual gateway boundary fixtures; fake SDK streams, no credentials or egress."""
from concurrent.futures import ThreadPoolExecutor
import copy
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace as NS
import unittest
from unittest import mock

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
os.environ["WORDICON_TEST_MODE"] = "1"
import wordicon_cli as cli
import operations as ops
import operation_capture as capture
import operation_costs as costs
import producers
import capture as body_capture
import ledger


def objects(value):
    if isinstance(value, dict):
        return NS(**{k: objects(v) for k, v in value.items()})
    if isinstance(value, list):
        return [objects(v) for v in value]
    return value


class Message:
    def __init__(self, raw):
        self.raw = copy.deepcopy(raw)
        self.__dict__.update(objects(raw).__dict__)
    def model_dump(self, mode="json"):
        return copy.deepcopy(self.raw)


class Stream:
    def __init__(self, raw, interrupted=False):
        self.message = self.current_message_snapshot = Message(raw)
        self.interrupted = interrupted
    def __enter__(self): return self
    def __exit__(self, *args): return False
    def __iter__(self):
        yield NS(type="content_block_delta", delta=NS(text="observed fragment"))
        if self.interrupted:
            raise OSError("fixture connection loss")
    def get_final_message(self): return self.message


def raw_message(**changes):
    return {"id": "msg_fixture", "type": "message", "role": "assistant",
            "model": "claude-sonnet-5", "stop_reason": "end_turn", "stop_sequence": None,
            "content": [{"type": "text", "text": "A kept answer."}],
            "usage": {"input_tokens": 20, "output_tokens": 10,
                      "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0}, **changes}


class OperationCaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nk-body-capture-", dir="/private/tmp")
        self.old = cli.LOCAL_STATE, cli.INPUTS_LOG, cli.EDGES_LOG
        cli.LOCAL_STATE = Path(self.temp.name)
        cli.INPUTS_LOG, cli.EDGES_LOG = cli.LOCAL_STATE / "inputs.jsonl", cli.LOCAL_STATE / "edges.jsonl"
        self.op, _ = ops.reserve(request_key="fixture", kind="job", snapshot_id="snap_fixture",
                                prepared_id="prep_fixture", execution={"plan": {"origin": {"doc_id": "doc_fixture", "revision": 2}}})
        self.sent = []

    def tearDown(self):
        cli.LOCAL_STATE, cli.INPUTS_LOG, cli.EDGES_LOG = self.old
        self.temp.cleanup()

    def gateway(self, raw=None, interrupted=False, before=None):
        g = cli.AnthropicAPIGateway.__new__(cli.AnthropicAPIGateway)
        g.model = "claude-sonnet-5"
        g._retryable = lambda: ((), ())
        def stream(**kwargs):
            if before: before(kwargs)
            self.sent.append(copy.deepcopy(kwargs))
            return Stream(raw if raw is not None else raw_message(), interrupted)
        g.client = NS(messages=NS(stream=stream))
        ops.attach(g, self.op["op_id"])
        return g

    def records(self, phase=None):
        rows = capture.inspect(self.op["op_id"])["records"]
        return [r for r in rows if phase is None or r["record"]["phase"] == phase]

    def test_request_is_durable_before_dispatch_and_response_before_return(self):
        def before(kwargs):
            rows = self.records("request")
            self.assertEqual(len(rows), 1)
            self.assertEqual(rows[0]["record"]["body"], kwargs)
            self.assertTrue(rows[0]["linked"])
        prompt = cli.Cacheable("Stable instruction.", "Actual question\nSecond line.")
        g = self.gateway(before=before)
        self.assertEqual(g.complete(prompt), "A kept answer.")
        request, response = self.records("request")[0], self.records("response")[0]
        self.assertEqual(response["record"]["response"]["response"], raw_message())
        self.assertEqual(response["record"]["request_artifact"], request["artifact"])
        self.assertEqual(request["record"]["links"]["snapshot_id"], "snap_fixture")
        self.assertEqual(request["record"]["links"]["doc_id"], "doc_fixture")
        intents = [x for x in ops.events(self.op["op_id"]) if x["kind"] == "attempt_intent"]
        self.assertEqual(request["record"]["attempt_id"], intents[0]["detail"]["attempt_id"])
        self.assertEqual(len(costs._events(self.op["op_id"])), 1)
        self.assertEqual(costs.total(ops.get(self.op["op_id"]))["accounting_status"], "estimated")

    def test_server_search_keeps_actual_tool_inputs_results_and_unknown_tool_charge(self):
        raw = raw_message(content=[{"type": "server_tool_use", "id": "srv_1", "name": "web_search", "input": {"query": "fixture question"}},
            {"type": "web_search_tool_result", "tool_use_id": "srv_1", "content": [{"type": "web_search_result", "url": "https://example.test/source", "title": "Source", "encrypted_content": "opaque-provider-value"}]},
            {"type": "text", "text": "A source-based answer.", "citations": []}])
        raw["usage"]["server_tool_use"] = {"web_search_requests": 1}
        g = self.gateway(raw)
        text, _ = g.complete_with_search_budget("Investigate source", max_uses=2)
        self.assertEqual(text, "A source-based answer.")
        request = self.records("request")[0]["record"]
        self.assertEqual(request["body"]["tools"][0]["max_uses"], 2)
        self.assertEqual(self.records("response")[0]["record"]["response"]["response"], raw)
        row = costs._events(self.op["op_id"])[0]
        self.assertIsNone(row["estimated_cost_usd"])
        self.assertGreater(row["known_estimated_subtotal_usd"], 0)
        self.assertEqual(row["server_tool_usage"], {"web_search_requests": 1})
        self.assertEqual(len(self.sent), 1)

    def test_request_capture_failure_prevents_dispatch_and_no_charge_is_invented(self):
        g = self.gateway()
        real = capture._keep
        def fail(op_id, phase, attempt_id, body):
            if phase == "request": raise OSError("fixture full disk")
            return real(op_id, phase, attempt_id, body)
        with mock.patch.object(capture, "_keep", side_effect=fail):
            with self.assertRaises(capture.CaptureError): g.complete("Do not send")
        self.assertEqual(self.sent, [])
        self.assertEqual(self.records("failure")[0]["record"]["outcome"], "not_sent")
        self.assertEqual(costs._events(self.op["op_id"]), [])

    def test_response_link_failure_preserves_orphan_without_retry(self):
        g = self.gateway()
        original = ops._event
        def event(conn, op_id, kind, **kwargs):
            if (kwargs.get("detail", {}).get("capture") or {}).get("phase") == "response":
                raise OSError("fixture failed transaction")
            return original(conn, op_id, kind, **kwargs)
        with mock.patch.object(ops, "_event", side_effect=event):
            with self.assertRaises(capture.CaptureError): g.complete("One paid attempt")
        self.assertEqual(len(self.sent), 1)
        row = self.records("response")[0]
        self.assertFalse(row["linked"])
        self.assertEqual(row["record"]["response"]["response"], raw_message())
        self.assertEqual(capture.inspect(self.op["op_id"])["gaps"][0]["kind"], "artifact_link_missing")

    def test_truncation_and_interruption_keep_paid_body_usage_without_replay(self):
        g = self.gateway(raw_message(stop_reason="max_tokens"))
        with self.assertRaisesRegex(RuntimeError, "output ceiling"): g.complete("Will truncate")
        truncated = self.records("failure")[0]["record"]
        self.assertEqual(truncated["response"]["stop_reason"], "max_tokens")
        self.assertTrue(truncated["response"]["usage_complete"])
        g = self.gateway(raw_message(id="msg_partial", stop_reason=None), interrupted=True)
        with self.assertRaises(cli.StreamInterrupted): g.complete("Will interrupt")
        failures = [r["record"] for r in self.records("failure")]
        partial = next(r for r in failures if r["response"]["response_id"] == "msg_partial")
        self.assertFalse(partial["response"]["usage_complete"])
        self.assertEqual(partial["response"]["response"]["content"], raw_message()["content"])
        self.assertEqual(len(self.sent), 2)
        self.assertEqual(len(costs._events(self.op["op_id"])), 2)

    def test_provider_error_body_survives_friendly_wrapper_without_headers(self):
        class APIError(Exception): pass
        error = APIError("rejected request")
        error.body = {"error": {"type": "invalid_request", "message": "body detail", "headers": {"Authorization": "never-retain"}}}
        wrapper = RuntimeError("friendly failure"); wrapper.__cause__ = error
        attempt = capture.Attempt(self.op["op_id"], call_id="call_error", attempt_id="call_error:1", provider="anthropic", model="claude-sonnet-5")
        attempt.request({"messages": [{"content": "ordinary"}]})
        attempt.finish(error=wrapper)
        record = self.records("failure")[0]["record"]
        self.assertEqual(record["response"]["error_body"]["error"]["type"], "invalid_request")
        self.assertNotIn("never-retain", json.dumps(record))
        self.assertFalse(record["capture"]["exact"])

    def test_inspection_in_new_process_is_read_only_and_does_not_resume(self):
        g = self.gateway(); g.complete("Complete once")
        attempt = capture.Attempt(self.op["op_id"], call_id="call_crash", attempt_id="call_crash:1", provider="anthropic", model="claude-sonnet-5")
        attempt.request({"messages": [{"content": "Request kept; process lost before outcome"}]})
        before = {str(p.relative_to(cli.LOCAL_STATE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cli.LOCAL_STATE.rglob("*") if p.is_file()}
        script = "import sys,json; from pathlib import Path; import wordicon_cli as c; c.LOCAL_STATE=Path(sys.argv[1]); import operation_capture as x; print(json.dumps(x.inspect(sys.argv[2])))"
        result = subprocess.check_output([sys.executable, "-c", script, str(cli.LOCAL_STATE), self.op["op_id"]],
            env={**os.environ, "PYTHONPATH": str(ROOT / "scripts"), "PYTHONDONTWRITEBYTECODE": "1"}, text=True)
        after = {str(p.relative_to(cli.LOCAL_STATE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cli.LOCAL_STATE.rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(len(json.loads(result)["records"]), 3)
        self.assertEqual(json.loads(result)["gaps"][0]["kind"], "request_outcome_unavailable")
        self.assertEqual(len(self.sent), 1)

    def test_redactions_are_explicit_and_never_modify_dispatched_body(self):
        prompt = "Question api_key=fixture-secret-value\nhttps://example.test/?token=url-secret"
        g = self.gateway(); g.complete(prompt)
        self.assertEqual(self.sent[0]["messages"][0]["content"], prompt)
        record = self.records("request")[0]["record"]
        encoded = json.dumps(record)
        self.assertNotIn("fixture-secret-value", encoded)
        self.assertNotIn("url-secret", encoded)
        self.assertFalse(record["capture"]["exact"])
        self.assertNotIn("fixture-secret-value", json.dumps(ops.events(self.op["op_id"])))

    def test_no_duplicate_opencase_accounting_and_no_capture_grants_allowance(self):
        ops.mark(self.op["op_id"], status="running")
        own, _ = ops.reserve(request_key="oc", kind="investigation", action_id="investigate.opencase.question", execution={})
        a = capture.Attempt(own["op_id"], call_id="call_owned", attempt_id="call_owned:1", provider="anthropic", model="claude-sonnet-5")
        a.request({"max_tokens": 7}); a.finish(response=Message(raw_message()))
        self.assertEqual(costs._events(own["op_id"]), [])
        self.assertEqual(len(capture.inspect(own["op_id"])["records"]), 2)
        self.assertFalse(any(x["event_type"] == "reservation" for x in costs._events(self.op["op_id"])))

    def test_image_uses_single_attempt_and_keeps_selected_image_body(self):
        g = self.gateway()
        self.assertEqual(g.complete_with_image("Describe", b"fixture image", "image/png"), "A kept answer.")
        self.assertEqual(self.records("request")[0]["record"]["body"], self.sent[0])
        self.assertEqual(len(self.records("response")), 1)
        self.assertEqual(len(self.sent), 1)

    def test_concurrent_gateway_calls_have_distinct_attempt_bodies(self):
        g = self.gateway()
        with ThreadPoolExecutor(max_workers=2) as pool:
            self.assertEqual(list(pool.map(g.complete, ["First question", "Second question"])), ["A kept answer."] * 2)
        requests = self.records("request")
        self.assertEqual(len(requests), 2)
        self.assertEqual(len({r["record"]["attempt_id"] for r in requests}), 2)
        self.assertEqual({r["record"]["body"]["messages"][0]["content"] for r in requests}, {"First question", "Second question"})

    def test_input_and_edge_writes_fsync_and_report_failures_without_killing_action(self):
        real_sync = os.fsync
        with mock.patch.object(os, "fsync", wraps=real_sync) as sync:
            result = cli.record_input("job_fixture", "forge", "original input")
            self.assertTrue(result["durable"])
            self.assertGreaterEqual(sync.call_count, 2)
        with mock.patch.object(cli, "_append_capture_line", side_effect=OSError("private detail")):
            result = cli.record_input("job_failed", "forge", "lost input body")
            edge = cli.record_edge("parallels", {"key": "source"}, {"key": "target"}, "trace_fixture", origin="owner_declared", producer={"kind": "owner_declaration", "id": "event_fixture"})
        self.assertTrue(result["capture_gap"]["durable"])
        self.assertTrue(edge["capture_gap"]["durable"])
        gaps = body_capture.read_gaps()["gaps"]
        self.assertEqual({x["kind"] for x in gaps}, {"input_write_failed", "edge_write_failed"})
        self.assertNotIn("private detail", json.dumps(gaps))
        self.assertNotIn("lost input body", json.dumps(gaps))

    def test_existing_partial_log_tail_remains_and_failed_gap_is_explicit(self):
        cli.INPUTS_LOG.write_bytes(b'{"partial')
        cli.record_input("job_after", "forge", "kept later")
        self.assertTrue(cli.INPUTS_LOG.read_bytes().startswith(b'{"partial\n'))
        self.assertEqual(cli.load_inputs()[0]["job_id"], "job_after")
        with mock.patch.object(cli, "_append_capture_line", side_effect=OSError()), mock.patch.object(body_capture, "gap", side_effect=OSError()):
            result = cli.record_input("job_failed", "forge", "input")
        self.assertFalse(result["capture_gap"]["durable"])
        self.assertEqual(result["capture_gap"]["why"], "capture_gap_store_unavailable")


class SanitizerTests(unittest.TestCase):
    def test_nested_transport_secrets_urls_and_usage(self):
        value = {"body": [{"headers": {"Cookie": "cookie-raw"}, "api_key": "field-raw", "text": "Bearer bearer-raw https://user:pass@example.test/?%61pi_key=url-raw&ordinary=kept sk-ant-fixture-secret-12345"}],
                 "usage": {"input_tokens": 12, "output_tokens": 3, "cache_read_input_tokens": 7}, "environment": {"API_KEY": "env-raw"}}
        out = capture.sanitize_body(value)
        raw = json.dumps(out)
        for secret in ("cookie-raw", "field-raw", "bearer-raw", "user:pass", "url-raw", "fixture-secret", "env-raw"):
            self.assertNotIn(secret, raw)
        self.assertEqual(out["value"]["usage"], value["usage"])
        self.assertIn("ordinary=kept", raw)
        self.assertFalse(out["exact"])
        self.assertEqual(out, capture.sanitize_body(value))

    def test_plain_body_exact_unknown_objects_never_repr_and_cycles_explicit(self):
        plain = {"message": "Exact punctuation [1], multiline\ntext.", "list": [1, None, True]}
        self.assertEqual(capture.sanitize_body(plain)["value"], plain)
        self.assertTrue(capture.sanitize_body(plain)["exact"])
        class Private:
            def __repr__(self): raise AssertionError("must not inspect")
        cycle = []; cycle.append(cycle)
        got = capture.sanitize_body({"private": Private(), "float": float("nan"), "cycle": cycle})
        self.assertEqual(got["value"], {"private": None, "float": None, "cycle": [None]})
        self.assertEqual({x["kind"] for x in got["redactions"]}, {"unsupported_value_unavailable", "nonfinite_unavailable", "cycle_unavailable"})


if __name__ == "__main__": unittest.main()
