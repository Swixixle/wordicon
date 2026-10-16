"""Go deeper's spending boundary, exact subject, and durable HTTP history.

Run with ``python -m pytest tests/test_deeper_integration.py``. Every store is
temporary and WORDICON_TEST_MODE is set before the application is imported.
The real controller, operations store, and pipeline run; only scheduling is
made synchronous so a failed assertion cannot leave a background writer.
"""
from __future__ import annotations

import json
import os
from pathlib import Path
import sys
import tempfile
from types import SimpleNamespace

import pytest


_REPO = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(_REPO))
sys.path.insert(0, str(_REPO / "scripts"))
os.environ["WORDICON_TEST_MODE"] = "1"
_IMPORT_STATE = tempfile.TemporaryDirectory(prefix="wordicon_deeper_import_")
os.environ["WORDICON_STATE"] = _IMPORT_STATE.name
os.environ.setdefault("WORDICON_TEST_EGRESS_LOG", str(Path(_IMPORT_STATE.name) / "egress_denied.jsonl"))

import server  # noqa: E402
import actions  # noqa: E402
import gate  # noqa: E402
import operations as ops  # noqa: E402
import snapshots  # noqa: E402
import state_root  # noqa: E402
import wordicon_cli as cli  # noqa: E402


@pytest.fixture
def app(tmp_path, monkeypatch):
    previous_root = cli.LOCAL_STATE
    state_root.apply(tmp_path)
    cli.RESULTS_DIR.mkdir(parents=True, exist_ok=True)
    cli.RECEIPTS_DIR.mkdir(parents=True, exist_ok=True)
    monkeypatch.setattr(server, "JOBS", {})
    monkeypatch.setattr(server.notify, "notify_job_complete", lambda job: None)
    prompts = []
    dispatched = []

    class CountingMock(cli.MockGateway):
        def complete(self, prompt):
            prompts.append(str(prompt))
            return super().complete(prompt)

    monkeypatch.setattr(server, "server_gateway", CountingMock)

    def dispatch(job_id, mode, input_text):
        assert ops.claim(job_id, "deeper-integration-tests"), "a reserved operation must be claimable exactly once"
        dispatched.append(job_id)
        server._run_job(job_id, mode, input_text)
        return server.jsonify({"job_id": job_id, "status": ops.get(job_id)["status"], "dispatched": True})

    monkeypatch.setattr(server, "_dispatch_job", dispatch)
    client = server.app.test_client()
    client.set_cookie(gate.SESSION_COOKIE, gate.issue_session("deeper-integration-tests")["token"])
    trace_id = "trace_cli_deeper_subject_01"
    parent = {
        "trace_id": trace_id,
        "mode": "sprout",
        "created_at": "2026-01-01T12:00:00Z",
        "source": {"title": "An earlier analogy", "definition": "The original analogy is not the selected work."},
        "threads": [
            {"anchor_name": "A different Augustine", "culture_or_work": "An unrelated work", "reading": "Not selected."},
            {
                "anchor_name": "Augustine's excavation of memory",
                "culture_or_work": "Augustine, Confessions, Book X",
                "source_shows": "A meditation on the capacity and limits of memory.",
                "reading": "Memory is examined from within.",
                "quote": "Great is this force of memory",
                "quote_status": "verbatim-recall",
                "locator": "Book X, chapters 8–17",
                "review_verdict": "strained",
                "review_note": "Recall only; this judges the analogy, not the work.",
            },
        ],
        "doors": [],
    }
    parent_path = cli.RESULTS_DIR / f"{trace_id}.json"
    parent_path.write_text(json.dumps(parent), encoding="utf-8")
    yield SimpleNamespace(client=client, trace_id=trace_id, parent=parent, parent_path=parent_path,
                          prompts=prompts, dispatched=dispatched, gateway_class=CountingMock)
    state_root.apply(previous_root)


def prepare(app, *, subject=None, inputs=None):
    response = app.client.post("/api/actions/prepare", json={
        "action_id": "explore.deepen",
        "subject": subject or {"kind": "result", "trace_id": app.trace_id, "thread_index": 1},
        "inputs": inputs or {},
    })
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def start(app, proposal, key="deeper-start", **extra):
    response = app.client.post("/api/operations", json={
        "prepared_id": proposal["prepared_id"], "request_key": key, **extra,
    })
    assert response.status_code == 200, response.get_json()
    return response.get_json()


def finished(app, started):
    response = app.client.get(f"/api/operations/{started['operation_id']}")
    assert response.status_code == 200, response.get_json()
    body = response.get_json()
    assert body["status"] == "complete", body
    return body["result"]


def test_open_prepare_and_abandon_make_no_model_call(app):
    assert app.client.get(f"/api/result/{app.trace_id}").status_code == 200
    proposal = prepare(app)
    frozen = snapshots.load(proposal["snapshot_id"])
    assert snapshots.verify(frozen)
    assert "Augustine, Confessions, Book X" in frozen["text"]
    assert "An unrelated work" not in frozen["text"]
    assert "strained" in frozen["text"]
    # Closing a proposal sends no Start request. Reopening the parent must
    # not silently start the proposal left behind on disk.
    assert app.client.get(f"/api/result/{app.trace_id}").status_code == 200
    assert app.prompts == []
    assert app.dispatched == []
    assert ops.list_ops()["total"] == 0


def test_direct_job_cannot_bypass_the_proposal(app):
    response = app.client.post("/api/jobs", json={
        "mode": "deepen", "deepen_context": {"focus": "arbitrary client material"},
    })
    assert response.status_code == 409, response.get_json()
    assert app.prompts == []
    assert app.dispatched == []
    assert ops.list_ops()["total"] == 0


def test_duplicate_start_is_one_dispatch_and_one_completion(app):
    proposal = prepare(app)
    first = start(app, proposal)
    second = start(app, proposal)
    result = finished(app, first)
    assert first["operation_id"] == second["operation_id"]
    assert second["repeated"] is True
    assert result["mode"] == "deepen"
    assert len(app.dispatched) == 1
    assert len(app.prompts) == 1
    kinds = [row["kind"] for row in ops.events(first["operation_id"])]
    assert kinds.count("reserved") == kinds.count("claimed") == 1
    assert not cli.JUDGMENTS_LOG.exists(), "curiosity must not become an endorsement"


def test_start_uses_exact_frozen_subject_ignoring_spoofed_fields(app):
    subject = {"kind": "result", "trace_id": app.trace_id, "thread_index": 1,
               "focus": {"title": "FORGED CLIENT SUBJECT"}, "original": {"title": "FORGED CLIENT SUBJECT"}}
    proposal = prepare(app, subject=subject, inputs={"question": "What is the role of forgetting?", "focus": "FORGED CLIENT SUBJECT"})
    frozen = snapshots.load(proposal["snapshot_id"])
    assert "FORGED CLIENT SUBJECT" not in frozen["text"]
    # Any fields smuggled into Start are irrelevant to the proposal.
    begun = start(app, proposal, deepen_context={"focus": "FORGED CLIENT SUBJECT"},
                  subject={"kind": "result", "trace_id": "other"})
    result = finished(app, begun)
    material = "\n".join(app.prompts) + json.dumps(result)
    assert "Augustine, Confessions, Book X" in material
    assert "What is the role of forgetting?" in material
    assert "FORGED CLIENT SUBJECT" not in material


def test_corrupting_the_immutable_source_refuses_before_model_call(app):
    proposal = prepare(app)
    # Saved results are immutable. A source record overwritten after
    # prepare is corruption, not a newer editable document revision.
    newer = json.loads(app.parent_path.read_text())
    newer["threads"][1]["culture_or_work"] = "MUTATED AFTER PREPARE"
    app.parent_path.write_text(json.dumps(newer))
    begun = start(app, proposal)
    row = ops.get(begun["operation_id"])
    assert row["status"] == "failed"
    assert "selection" in row["last_error"]
    assert len(app.dispatched) == 1
    assert app.prompts == []


def test_snapshot_tampering_refuses_start_before_dispatch(app):
    proposal = prepare(app)
    path = Path(cli.LOCAL_STATE) / "snapshots" / f"{proposal['snapshot_id']}.json"
    modified = json.loads(path.read_text())
    modified["text"] += " changed after approval"
    path.write_text(json.dumps(modified))
    response = app.client.post("/api/operations", json={
        "prepared_id": proposal["prepared_id"], "request_key": "tampered-snapshot",
    })
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["nothing_was_sent"] is True
    assert app.dispatched == app.prompts == []


@pytest.mark.parametrize("reference", [
    {"trace_id": "../outside", "thread_index": 0},
    {"trace_id": "trace_cli_missing", "thread_index": 0},
    {"thread_index": -1},
    {"thread_index": 2},
    {"thread_index": True},
    {"thread_index": "1"},
])
def test_invalid_result_reference_never_dispatches(app, reference):
    response = app.client.post("/api/actions/prepare", json={
        "action_id": "explore.deepen",
        "subject": {"kind": "result", "trace_id": app.trace_id, **reference},
        "inputs": {},
    })
    assert 400 <= response.status_code < 500, response.get_json()
    assert app.dispatched == app.prompts == []


def test_provider_change_requires_a_new_proposal(app, monkeypatch):
    proposal = prepare(app)

    class ChangedLane(app.gateway_class):
        name = "changed-provider"
        is_external = True

    monkeypatch.setattr(server, "server_gateway", ChangedLane)
    monkeypatch.setenv("WORDICON_MODEL", "changed-model")
    response = app.client.post("/api/operations", json={
        "prepared_id": proposal["prepared_id"], "request_key": "changed-lane",
    })
    assert response.status_code == 409, response.get_json()
    assert app.dispatched == app.prompts == []


def test_failure_is_durable_and_reading_it_does_not_retry(app, monkeypatch):
    proposal = prepare(app)

    class FailingMock(app.gateway_class):
        def complete(self, prompt):
            app.prompts.append(str(prompt))
            raise RuntimeError("deliberate offline provider failure")

    monkeypatch.setattr(server, "server_gateway", FailingMock)
    begun = start(app, proposal)
    operation_id = begun["operation_id"]
    assert ops.get(operation_id)["status"] == "failed"
    assert "deliberate offline provider failure" in ops.get(operation_id)["last_error"]
    server.JOBS.clear()
    reopened = app.client.get(f"/api/operations/{operation_id}")
    assert reopened.status_code == 200
    assert reopened.get_json()["status"] == "failed"
    assert len(app.prompts) == len(app.dispatched) == 1


def test_saved_result_reopens_after_projection_is_lost_without_calls(app):
    proposal = prepare(app)
    begun = start(app, proposal)
    result = finished(app, begun)
    trace_id = result["trace_id"]
    assert (cli.RESULTS_DIR / f"{trace_id}.json").exists()
    assert (cli.RECEIPTS_DIR / f"receipt_{trace_id}.json").exists()
    original_bytes = app.parent_path.read_bytes()
    server.JOBS.clear()
    reopened = app.client.get(f"/api/result/{trace_id}")
    durable = app.client.get(f"/api/operations/{begun['operation_id']}")
    assert reopened.status_code == durable.status_code == 200
    assert reopened.get_json()["trace_id"] == trace_id
    assert durable.get_json()["status"] == "complete"
    assert durable.get_json()["trace_id"] == trace_id
    assert durable.get_json()["result_ref"]["trace_id"] == trace_id
    assert app.parent_path.read_bytes() == original_bytes
    assert len(app.prompts) == len(app.dispatched) == 1


def test_followup_keeps_selected_work_and_cites_previous_step(app):
    first = finished(app, start(app, prepare(app)))
    question = "How does this account distinguish remembering from knowing?"
    next_proposal = prepare(app, subject={"kind": "result", "trace_id": first["trace_id"]},
                            inputs={"question": question})
    frozen = snapshots.load(next_proposal["snapshot_id"])["text"]
    assert "Augustine, Confessions, Book X" in frozen
    assert first["trace_id"] in frozen
    assert question in frozen
    assert len(app.prompts) == 1, "preparing the follow-up must not make its model call"
    second = finished(app, start(app, next_proposal, key="follow-up"))
    assert second["trace_id"] != first["trace_id"]
    assert question in app.prompts[-1]
    assert len(app.prompts) == len(app.dispatched) == 2


def test_changed_plan_retry_flag_cannot_replace_a_deeper_proposal(app, monkeypatch):
    begun = start(app, prepare(app))
    finished(app, begun)

    class ChangedLane(app.gateway_class):
        name = "changed-provider"
        is_external = True
        model = "changed-model"

    monkeypatch.setattr(server, "server_gateway", ChangedLane)
    monkeypatch.setenv("WORDICON_MODEL", "changed-model")
    response = app.client.post(f"/api/operations/{begun['operation_id']}/attempts", json={
        "request_key": "changed-plan-retry", "accept_changed_plan": True,
    })
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["nothing_was_sent"] is True
    assert len(app.prompts) == len(app.dispatched) == 1


def test_result_persisted_before_process_death_is_reconciled_without_replay(app, monkeypatch):
    class OfflineTransportBoundary(app.gateway_class):
        def complete_with_search(self, prompt):
            # Exercise the production attempt boundary with a deterministic
            # local reply. No HTTP request is made by this test gateway.
            return self._call_with_attempts("search", lambda: self.complete(prompt)), []

    monkeypatch.setattr(server, "server_gateway", OfflineTransportBoundary)
    proposal = prepare(app)
    saved = []
    real_update = server._update_job

    def die_before_operation_completion(job_id, **fields):
        if fields.get("status") == "complete":
            saved.append(fields["result"]["trace_id"])
            raise KeyboardInterrupt("simulated death after result persistence")
        return real_update(job_id, **fields)

    monkeypatch.setattr(server, "_update_job", die_before_operation_completion)
    with pytest.raises(KeyboardInterrupt, match="simulated death"):
        start(app, proposal, key="crash-after-result")
    assert len(saved) == 1
    assert (cli.RESULTS_DIR / f"{saved[0]}.json").exists()
    operation_id = app.dispatched[0]
    assert ops.get(operation_id)["status"] == "running"
    server.JOBS.clear()
    changes = ops.reconcile("replacement-process", cli.RESULTS_DIR, cli.RECEIPTS_DIR)
    assert changes and changes[0]["case"] == "result_persisted_link_missing", changes
    reopened = app.client.get(f"/api/operations/{operation_id}")
    assert reopened.status_code == 200
    assert reopened.get_json()["status"] == "complete"
    assert reopened.get_json()["trace_id"] == saved[0]
    assert app.client.get(f"/api/result/{saved[0]}").status_code == 200
    assert len(app.prompts) == len(app.dispatched) == 1
