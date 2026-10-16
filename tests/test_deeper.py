"""Focused exploration keeps its real parent, source standing and record."""
from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import deeper
import operations
import wordicon_cli as cli


@pytest.fixture
def store(tmp_path, monkeypatch):
    for name, path in (("LOCAL_STATE", tmp_path), ("RESULTS_DIR", tmp_path / "results"),
                       ("RECEIPTS_DIR", tmp_path / "receipts"), ("EDGES_LOG", tmp_path / "edges.jsonl")):
        monkeypatch.setattr(cli, name, path)
    cli.RESULTS_DIR.mkdir()
    snapshot = {"trace_id": "trace_sprout_test", "mode": "sprout",
                "created_at": "2026-10-16T00:00:00+00:00", "threads": [
                    {"anchor_name": "Augustine's excavation of memory",
                     "culture_or_work": "Augustine, Confessions, Book X",
                     "source_shows": "A recalled account of memory, not an admitted passage.",
                     "parallel": "A proposed relation to another concept.",
                     "quote": "A remembered quotation.", "quote_kind": "verbatim from recall",
                     "review_verdict": "strained", "review_note": "This analogy is incomplete.",
                     "verification_hint": "Confessions, Book X, chapters 8–17"},
                    {"anchor_name": "Another subject", "culture_or_work": "Another work"}]}
    cli.write_run_snapshot(snapshot["trace_id"], snapshot)
    return snapshot


def subject(**extra):
    return {"kind": "result", "trace_id": "trace_sprout_test", "thread_index": 0, **extra}


class CountingGateway(cli.Gateway):
    name = "test"
    last_acquisition = {"web_search_requests": 1}

    def __init__(self, payload=None, citations=None):
        self.prompts = []
        self.payload = payload if payload is not None else deeper.fixture_response()
        self.citations = citations or []

    def complete_with_search(self, prompt):
        self.prompts.append(prompt)
        return json.dumps(self.payload), self.citations


def test_selection_resolved_from_record_and_copied(store):
    context = deeper.build_context(subject(title="ATTACK", selection={"anchor_name": "ATTACK"}),
                                   {"focus": {"title": "ATTACK"}, "question": "How does memory work here?"})
    assert context["root"]["selection"] == store["threads"][0]
    assert context["focus"]["title"] == store["threads"][0]["anchor_name"]
    assert "ATTACK" not in json.dumps(context)
    assert context["root"]["source_standing"]["relation_verdict"] == "strained"
    context["root"]["selection"]["anchor_name"] = "changed in memory"
    assert deeper.build_context(subject())["root"]["selection"] == store["threads"][0]


@pytest.mark.parametrize("index", [True, False, -1, 2, "0", 0.0, None])
def test_index_is_exact_nonnegative_integer(store, index):
    with pytest.raises(ValueError):
        deeper.build_context(subject(thread_index=index))


@pytest.mark.parametrize("trace", ["../trace_sprout_test", "/tmp/x", "a/b", "a\\b", "x.json", "", None])
def test_path_traversal_refused(store, trace):
    with pytest.raises(ValueError):
        deeper.build_context(subject(trace_id=trace))


def test_missing_and_malformed_saved_result_refused(store):
    with pytest.raises(ValueError, match="unavailable"):
        deeper.build_context(subject(trace_id="trace_absent"))
    (cli.RESULTS_DIR / "trace_bad.json").write_text("not json")
    with pytest.raises(ValueError, match="unavailable"):
        deeper.build_context(subject(trace_id="trace_bad"))
    with pytest.raises(ValueError, match="at most"):
        deeper.build_context(subject(), {"question": "q" * 2001})
    with pytest.raises(ValueError, match="question"):
        deeper.build_context(subject(), {"question": "???"})


def test_symlink_outside_results_refused(store, tmp_path):
    outside = tmp_path / "elsewhere.json"
    outside.write_text(json.dumps({**store, "trace_id": "trace_link"}))
    (cli.RESULTS_DIR / "trace_link.json").symlink_to(outside)
    with pytest.raises(ValueError, match="outside"):
        deeper.build_context(subject(trace_id="trace_link"))


def test_run_preserves_receipt_before_snapshot_before_edge(store, monkeypatch):
    context = deeper.build_context(subject())
    before = copy.deepcopy(context)
    gateway = CountingGateway()
    real_edge = cli.record_edge
    seen = []

    def record_edge(*args, **kwargs):
        trace = args[3]
        assert (cli.RECEIPTS_DIR / f"receipt_{trace}.json").exists()
        assert (cli.RESULTS_DIR / f"{trace}.json").exists()
        seen.append((args, kwargs))
        return real_edge(*args, **kwargs)

    monkeypatch.setattr(cli, "record_edge", record_edge)
    result = deeper.run(context, gateway)
    assert context == before
    assert len(gateway.prompts) == 1
    assert result["mode"] == "deepen"
    assert result["parent_trace_id"] == store["trace_id"]
    assert result["context"]["root"]["selection"] == store["threads"][0]
    assert json.loads((cli.RESULTS_DIR / f"{result['trace_id']}.json").read_text()) == result
    receipt = json.loads((cli.RECEIPTS_DIR / f"{result['receipt_id']}.json").read_text())
    assert receipt["operation"] == "distill"
    assert receipt["candidates"] == receipt["claims"] == receipt["sources"] == []
    assert receipt["prompt_identities"][0]["stage"] == "deepen"
    assert receipt["prompt_identities"][0]["calls"] == 1
    assert result["raw_response"] == json.dumps(gateway.payload)
    assert seen[0][0][0] == "continued_from"
    assert seen[0][1]["origin"] == "mechanical"
    assert len(cli.EDGES_LOG.read_text().splitlines()) == 1


def test_tampered_frozen_focus_refused_before_call(store):
    context = deeper.build_context(subject())
    context["focus"]["title"] = "Another selection"
    gateway = CountingGateway()
    with pytest.raises(ValueError, match="focus"):
        deeper.run(context, gateway)
    assert gateway.prompts == []
    context = deeper.build_context(subject())
    context["root"]["selection"]["quote"] = "fabricated replacement"
    with pytest.raises(ValueError, match="selection"):
        deeper.run(context, gateway)
    assert gateway.prompts == []


def test_followup_keeps_root_and_latest_steps_with_disclosed_omissions(store):
    gateway = CountingGateway(payload={**deeper.fixture_response(), "explanation": "x" * 3000})
    result = deeper.run(deeper.build_context(subject()), gateway)
    for i in range(6):
        ref = {"kind": "result", "trace_id": result["trace_id"]}
        with pytest.raises(ValueError, match="follow-up"):
            deeper.build_context(ref)
        context = deeper.build_context(ref, {"question": f"Explain distinction {i}?"})
        assert context["root"]["selection"] == store["threads"][0]
        assert context["ancestry"][-1]["trace_id"] == result["trace_id"]
        assert context["ancestry"][-1]["explanation_omitted_chars"] == 800
        result = deeper.run(context, gateway)
    assert context["context_limits"]["omitted_prior_steps"] == 2
    assert len(context["ancestry"]) == 4
    assert context["context_limits"]["total_prior_steps"] == 6
    assert result["trail"][0]["trace_id"] == store["trace_id"]
    assert len(result["trail"]) == 8
    assert "omitted_prior_steps" in gateway.prompts[-1]
    assert "Explain distinction 5?" in gateway.prompts[-1]


def test_provider_citations_only_and_no_false_source_admission(store):
    payload = {**deeper.fixture_response(), "verified": True, "source_admitted": True,
               "citations": [{"url": "https://invented.example/model"}],
               "source_standing": {"kind": "verified"}}
    provider = [{"url": "https://primary.example/book", "title": "Returned by provider"},
                {"url": "javascript:alert(1)"}, {"url": "data:text/html,evil"},
                {"url": "https://user:password@example.com"}, {"url": "https://good.example\n.evil"},
                {"url": "file:///private"}]
    result = deeper.run(deeper.build_context(subject()), CountingGateway(payload, provider))
    assert result["citations"] == provider[:1]
    assert result["verified"] is result["source_admitted"] is False
    assert result["source_standing"]["kind"] == "model_recall"
    assert result["source_standing"]["quotes"] == "unverified"
    assert result["source_standing"]["relation_verdict"] == "strained"
    assert not result["is_fixture"]


def test_missing_explanation_cannot_be_a_finished_reading(store):
    with pytest.raises(RuntimeError, match="no usable explanation"):
        deeper.run(deeper.build_context(subject()), CountingGateway({"title": "No answer"}))
    assert not cli.RECEIPTS_DIR.exists()
    assert not cli.EDGES_LOG.exists()
    kept = list((cli.LOCAL_STATE / "kept_replies").glob("*.txt"))
    assert len(kept) == 1
    assert json.loads(kept[0].read_text()) == {"title": "No answer"}


def test_malformed_reply_is_preserved_without_completed_record(store):
    class BadJSON(CountingGateway):
        def complete_with_search(self, prompt):
            return '{"explanation":', []
    with pytest.raises(cli.ReplyParseError):
        deeper.run(deeper.build_context(subject()), BadJSON())
    assert not cli.RECEIPTS_DIR.exists()
    assert not cli.EDGES_LOG.exists()
    assert next((cli.LOCAL_STATE / "kept_replies").glob("*.txt")).read_text() == '{"explanation":'


def test_exact_repeated_questions_are_not_offered_again(store):
    context = deeper.build_context(subject(), {"question": "What is memory here?"})
    payload = {**deeper.fixture_response(), "next_questions": [
        "WHAT is memory here?", "What comes next?", "What   comes next?", "What changes later?"]}
    result = deeper.run(context, CountingGateway(payload))
    assert result["next_questions"] == ["What comes next?", "What changes later?"]


def test_snapshot_failure_leaves_no_lineage_edge(store, monkeypatch):
    def fail(*args, **kwargs):
        raise OSError("disk unavailable")
    monkeypatch.setattr(cli, "write_run_snapshot", fail)
    with pytest.raises(OSError, match="disk"):
        deeper.run(deeper.build_context(subject()), CountingGateway())
    assert not cli.EDGES_LOG.exists()


def test_context_and_prompt_identity_do_not_depend_on_client_title(store):
    first = deeper.build_context(subject(title="Forged client title"))
    second = deeper.build_context(subject(), {"question": "A different question?"})
    assert first["focus"] == second["focus"]
    a = deeper.run(first, CountingGateway())
    b = deeper.run(second, CountingGateway())
    assert a["prompt_identities"][0]["template_sha"] == b["prompt_identities"][0]["template_sha"]
    prompt = deeper.build_prompt(first)
    assert prompt.startswith(deeper.PROMPT_PREFIX)
    assert "source_admitted" in prompt
    assert "Forged client title" not in prompt


def test_saved_result_recovers_via_attempt_id_before_operation_completion(store):
    class AttemptGateway(CountingGateway):
        def complete_with_search(self, prompt):
            self.prompts.append(prompt)
            raw = self._call_with_attempts("search", lambda: json.dumps(self.payload))
            return raw, []

    context = deeper.build_context(subject())
    op, created = operations.reserve(request_key="deeper-recovery", kind="job",
                                     execution={"mode": "deepen", "context": context})
    assert created
    assert operations.claim(op["op_id"], "dead-dispatcher")
    gateway = AttemptGateway()
    operations.attach(gateway, op["op_id"])
    result = deeper.run(context, gateway)
    # Deliberately omit the server's complete call: simulate loss after
    # snapshot persistence, when only durable attempt metadata can link it.
    events = operations.events(op["op_id"])
    attempt_ends = [e for e in events if e["kind"] == "attempt_end"]
    assert len(attempt_ends) == 1
    assert attempt_ends[0]["detail"]["run_id"] == result["trace_id"]
    assert result["attempts"][0]["run_id"] == result["trace_id"]
    analysis = operations.analyse({**op, "status": "claimed"}, events,
                                  cli.RESULTS_DIR, cli.RECEIPTS_DIR)
    assert analysis["case"] == "result_persisted_link_missing"
    assert analysis["persisted"] == [result["trace_id"]]
    changed = operations.reconcile("new-dispatcher", cli.RESULTS_DIR, cli.RECEIPTS_DIR)
    assert changed[0]["now"] == "complete"
    assert changed[0]["persisted"] == [result["trace_id"]]
    assert len(gateway.prompts) == 1
    assert not hasattr(gateway, "attempts")


def test_attempt_failure_keeps_run_id_and_closes_owned_ledger(store):
    class FailedGateway(CountingGateway):
        def complete_with_search(self, prompt):
            def fail():
                raise RuntimeError("provider failed")
            return self._call_with_attempts("search", fail)

    gateway = FailedGateway()
    events = []
    gateway.dispatch_hook = lambda kind, **detail: events.append((kind, detail))
    with pytest.raises(RuntimeError, match="provider failed"):
        deeper.run(deeper.build_context(subject()), gateway)
    assert events[-1][0] == "attempt_end"
    assert events[-1][1]["run_id"].startswith("trace_")
    assert events[-1][1]["outcome"] == "error"
    assert not hasattr(gateway, "attempts")
