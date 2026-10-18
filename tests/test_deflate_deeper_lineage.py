"""Actual paired proposal/Start chain; all providers and stores are offline fixtures."""
import copy
import base64
import hashlib
import json
from pathlib import Path

import pytest

from test_deeper_integration import app, prepare, start, finished
import capture_history
import deeper
import federation
import operation_costs as costs
import operations as ops
import producers
import server
import snapshots
import wordicon_cli as cli
import workspace_identity


@pytest.fixture
def reading(app, request):
    fixtures = Path(__file__).parent / "fixtures/federation"
    federation.register_connector("lineage-deflate", "deflate", "http://127.0.0.1:3123", dev_loopback=True)
    federation.pin_key("lineage-deflate", (fixtures / "deflate.fixture.pub.b64").read_text().strip())
    raw = (fixtures / "deflate.exemplar.deposition.json").read_bytes()
    envelope = json.loads(raw)
    if getattr(request, "param", None):
        selected = envelope["payload"]["claims"]["passages"][0]
        selected["readingGate"] = {"status": "ready"}
        selected["reading"] = copy.deepcopy(request.param)
        other = copy.deepcopy(selected); other["id"] = "other_not_selected"
        other["reading"] = {"deflated": {"hs": "PRIVATE other passage interpretation"}}
        envelope["payload"]["claims"]["passages"].append(other)
        from cryptography.hazmat.primitives import serialization
        key = serialization.load_der_private_key(base64.b64decode((fixtures.parent / "producers/deflate.fixture.key.pkcs8.b64").read_text()), password=None)
        envelope["payload_sha256"] = federation.payload_sha256(envelope["payload"])
        envelope["signature"]["value"] = base64.b64encode(key.sign(federation.canonical_json(envelope["payload"]))).decode()
        raw = json.dumps(envelope).encode()
    imported = federation.import_package(federation.get_connector("lineage-deflate"), raw, how="pasted")
    plan = {"workspace_id": workspace_identity.ensure()["workspace_id"],
            "producer_plan": {"contract": "deflate.bridge.v1", "reading_enabled": True, "allowance_usd": .5},
            "connector": {"connector_id": "lineage-deflate"}, "question": "PRIVATE ancestor question",
            "origin": {"kind": "selection", "doc_id": "doc_fixture_origin", "revision": 2,
                       "text": "PRIVATE ancestor document " * 5000}}
    plan["plan_sha256"] = federation.payload_sha256(plan["producer_plan"])
    plan["plan_id"] = "p_" + plan["plan_sha256"]
    op, _ = ops.reserve(request_key="source-reading", kind="investigation", action_id="investigate.deflate.read", execution={"plan": plan})
    bid = "b_" + hashlib.sha256(op["op_id"].encode()).hexdigest()[:32]
    dep = producers.keep_artifact(op["op_id"], "producer-deposition.json", raw)
    remote = {**dep, "path": f"/api/bridge/jobs/{bid}/artifacts/{dep['name']}", "exact": True}
    job = {"contract": "deflate.bridge.v1", "request_id": op["op_id"], "bridge_id": bid,
           "plan": plan["producer_plan"], "plan_id": plan["plan_id"], "plan_sha256": plan["plan_sha256"],
           "runId": envelope["object"]["id"], "state": "completed", "acquisition": {"status": "done"},
           "result": {"runId": envelope["object"]["id"], "deposition": remote,
                      "transcript_sha256": envelope["payload"]["transcript"]["sha256"]}}
    result = producers.keep_artifact(op["op_id"], "bridge-result.json", json.dumps(job).encode())
    ref = {"kept": [dep, result], "deposition_artifact": dep, "result_artifact": result,
           "upstream_id": bid, "custody": {"verification": {"ok": True}, "deposition_id": imported["deposition_id"]}}
    ops.mark(op["op_id"], "complete", result_ref=ref)
    costs._append(op["op_id"], {"schema": costs.SCHEMA, "entry_id": "fixture-source-charge", "operation_id": op["op_id"],
        "event_type": "settlement", "component": "producer_model", "attempt_id": "model_001", "accounting_status": "estimated",
        "estimated_cost_usd": .125678, "known_estimated_subtotal_usd": .125678, "actual_cost_usd": None, "usage": []})
    return {"operation_id": op["op_id"], "plan": plan, "ref": ref, "raw": raw,
            "subject": {"kind": "deposition", "deposition_id": imported["deposition_id"],
                        "item_ref": "deflate:passage:" + envelope["payload"]["claims"]["passages"][0]["id"],
                        "source_operation_id": op["op_id"]}}


def alter_execution(operation_id, change):
    execution = copy.deepcopy(ops.get(operation_id)["execution"])
    change(execution)
    conn = ops._connect()
    try:
        conn.execute("UPDATE operations SET execution=?,fingerprint=? WHERE op_id=?",
                     (ops.canonical(execution), ops.fingerprint(execution), operation_id))
    finally:
        conn.close()


def test_frozen_source_is_exact_local_bounded_and_legacy_unchanged(app, reading):
    legacy_subject = {k: v for k, v in reading["subject"].items() if k != "source_operation_id"}
    legacy = deeper.build_context(legacy_subject)
    proposal = prepare(app, subject=reading["subject"], inputs={"question": "Explain this reading."})
    context = json.loads(snapshots.load(proposal["snapshot_id"])["text"])
    source = context["root"]["source_operation"]
    assert source["operation_id"] == reading["operation_id"]
    assert source["deposition_sha256"] == hashlib.sha256(reading["raw"]).hexdigest()
    assert source["plan_sha256"] == deeper._digest(reading["plan"])
    assert source["origin"]["origin_sha256"] == deeper._digest(reading["plan"]["origin"])
    assert source["origin"]["doc_id"] == "doc_fixture_origin"
    assert "text" not in source["origin"]
    assert len(json.dumps(source)) < 6000
    assert {k: v for k, v in context["root"].items() if k != "source_operation"} == legacy["root"]
    assert "operation_lineage" not in legacy
    assert "PRIVATE ancestor" not in deeper.build_prompt(context)
    assert "source_operation" not in deeper.build_prompt(context)
    assert app.prompts == []


@pytest.mark.parametrize("reading", [{"deflated": {"hs": "EXACT attributed primary interpretation"},
    "supports": "EXACT attributed support", "notShown": ["EXACT unresolved limit"],
    "open": "EXACT open question", "defense": "EXACT attributed defense", "revision": "EXACT revised interpretation",
    "private_extra": "PRIVATE extra producer field"}], indirect=True)
def test_only_selected_signed_reading_fields_reach_prompt(app, reading):
    legacy = {k: v for k, v in reading["subject"].items() if k != "source_operation_id"}
    assert "reading" not in deeper.build_context(legacy)["root"]["selection"]["deposition"]["item"]
    proposal = prepare(app, subject=reading["subject"], inputs={"question": "Explain this interpretation."})
    frozen = json.loads(snapshots.load(proposal["snapshot_id"])["text"])
    selected = frozen["root"]["selection"]["deposition"]["item"]
    assert selected["reading"]["deflated"]["hs"] == "EXACT attributed primary interpretation"
    assert set(selected["reading"]) == {"deflated", "supports", "notShown", "open", "defense", "revision"}
    assert "not independent validation" in selected["attributed_to"]
    finished(app, start(app, proposal, "selected-reading-prose"))
    prompt = "\n".join(app.prompts)
    for field in selected["reading"].values():
        assert json.dumps(field, ensure_ascii=False) in prompt
    for excluded in ("PRIVATE ancestor", "PRIVATE other passage", "PRIVATE extra producer field"):
        assert excluded not in prompt


@pytest.mark.parametrize("reading", [{"deflated": {"hs": "x" * (deeper.MAX_SELECTION + 1)}}], indirect=True)
def test_linked_reading_prose_cannot_expand_existing_selection_allowance(app, reading):
    response = app.client.post("/api/actions/prepare", json={"action_id": "explore.deepen", "subject": reading["subject"]})
    assert response.status_code == 400
    assert "context limit" in response.get_json()["error"]
    assert app.prompts == app.dispatched == []


@pytest.mark.parametrize("change", ["missing", "foreign_action", "foreign_workspace", "wrong_deposition", "changed_artifact", "wrong_result_ref"])
def test_foreign_or_mismatched_source_is_refused_before_prepare(app, reading, change):
    subject = copy.deepcopy(reading["subject"])
    if change == "missing":
        subject["source_operation_id"] = "op_missing"
    elif change == "foreign_action":
        other, _ = ops.reserve(request_key="foreign", kind="job", action_id="explore.deepen", execution={})
        subject["source_operation_id"] = other["op_id"]
    elif change == "foreign_workspace":
        alter_execution(reading["operation_id"], lambda e: e["plan"].update(workspace_id="workspace_" + "1" * 32))
    elif change == "wrong_deposition":
        ref = copy.deepcopy(reading["ref"]); ref["custody"]["deposition_id"] = "different_import"
        ops.mark(reading["operation_id"], result_ref=ref)
    elif change == "wrong_result_ref":
        ref = copy.deepcopy(reading["ref"]); ref["result_artifact"]["sha256"] = "1" * 64
        ops.mark(reading["operation_id"], result_ref=ref)
    else:
        (producers.artifact_dir(reading["operation_id"]) / reading["ref"]["deposition_artifact"]["name"]).write_bytes(b"changed")
    response = app.client.post("/api/actions/prepare", json={"action_id": "explore.deepen", "subject": subject})
    assert response.status_code == 400
    assert app.dispatched == app.prompts == []


@pytest.mark.parametrize("field", ["question", "origin"])
def test_changed_parent_after_prepare_is_clean409_without_dispatch(app, reading, field):
    proposal = prepare(app, subject=reading["subject"])
    alter_execution(reading["operation_id"], lambda e: e["plan"].update({field: "changed" if field == "question" else {"kind": "other"}}))
    response = app.client.post("/api/operations", json={"prepared_id": proposal["prepared_id"], "request_key": "changed-parent"})
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["nothing_was_sent"] is True
    assert app.dispatched == app.prompts == []
    assert ops.list_ops()["operations"][0]["status"] == "failed"


def test_start_followup_costs_history_restart_and_known_key_recovery(app, reading, monkeypatch):
    proposal = prepare(app, subject=reading["subject"], inputs={"question": "Explain the reading."})
    first = start(app, proposal, "linked-first")
    result = finished(app, first)
    first_op = ops.get(first["operation_id"])
    assert first_op["execution"]["plan"]["follow_up_of"] == reading["operation_id"]
    assert "PRIVATE ancestor" not in "\n".join(app.prompts)
    follow = prepare(app, subject={"kind": "result", "trace_id": result["trace_id"]}, inputs={"question": "What remains open?"})
    second = start(app, follow, "linked-second")
    second_result = finished(app, second)
    second_op = ops.get(second["operation_id"])
    assert second_op["execution"]["plan"]["follow_up_of"] == first["operation_id"]
    assert second_result["context"]["root"] == result["context"]["root"]
    assert second_result["context"]["operation_lineage"]["parent_trace_id"] == result["trace_id"]
    total = costs.total(second_op, ancestry=True)
    assert total["operation_ids"] == [second["operation_id"], first["operation_id"], reading["operation_id"]]
    assert total["known_estimated_subtotal_usd"] >= .125678
    assert total["actual_cost_usd"] is None
    history = capture_history.view(operation_id=second["operation_id"])
    pairs = {(e["from"], e["to"]) for e in history["links"] if e["relation"] == "follow_up"}
    assert (reading["operation_id"], first["operation_id"]) in pairs
    assert (first["operation_id"], second["operation_id"]) in pairs
    # A process-memory reset reconstructs the same source and result from disk.
    monkeypatch.setattr(server, "JOBS", {})
    reopened = app.client.get("/api/operations/" + second["operation_id"]).get_json()
    assert reopened["trace_id"] == second_result["trace_id"]
    reopened_result = app.client.get("/api/result/" + reopened["trace_id"]).get_json()
    assert reopened_result["context"] == second_result["context"]
    before = len(app.dispatched)
    alter_execution(reading["operation_id"], lambda e: e["plan"].update(question="Changed after completion"))
    repeated = start(app, proposal, "linked-first")
    assert repeated["repeated"] is True and repeated["operation_id"] == first["operation_id"]
    assert len(app.dispatched) == before


@pytest.mark.parametrize("change", ["missing", "ambiguous", "malformed_trace_ids", "changed_result", "changed_execution"])
def test_followup_never_skips_an_immediate_operation_or_changed_frozen_parent(app, reading, change):
    first = start(app, prepare(app, subject=reading["subject"]), "parent-for-followup")
    result = finished(app, first)
    subject = {"kind": "result", "trace_id": result["trace_id"]}
    follow = prepare(app, subject=subject, inputs={"question": "Continue this question?"})
    if change == "missing":
        ops.mark(first["operation_id"], result_ref={})
    elif change == "malformed_trace_ids":
        ops.mark(first["operation_id"], result_ref={"trace_ids": "prefix_" + result["trace_id"] + "_suffix"})
    elif change == "ambiguous":
        other, _ = ops.reserve(request_key="duplicate-trace", kind="job", action_id="explore.deepen", execution=ops.get(first["operation_id"])["execution"])
        ops.mark(other["op_id"], "complete", result_ref={"trace_id": result["trace_id"]})
    elif change == "changed_result":
        path = cli.RESULTS_DIR / (result["trace_id"] + ".json")
        changed = json.loads(path.read_text()); changed["explanation"] = "Changed saved explanation"
        path.write_text(json.dumps(changed))
    else:
        alter_execution(first["operation_id"], lambda e: e.update(model="changed"))
    before = len(app.dispatched)
    response = app.client.post("/api/operations", json={"prepared_id": follow["prepared_id"], "request_key": "invalid-followup"})
    assert response.status_code == 409, response.get_json()
    assert response.get_json()["nothing_was_sent"] is True
    assert len(app.dispatched) == before


def test_run_rechecks_lineage_before_gateway_and_unknown_child_cost_remains_unknown(app, reading):
    proposal = prepare(app, subject=reading["subject"])
    context = json.loads(snapshots.load(proposal["snapshot_id"])["text"])
    execution = server._execution_for_proposal(proposal, server.actions.BY_ID["explore.deepen"], {"lane": {}}, "job/v1")
    op, _ = ops.reserve(request_key="unaccounted-linked-child", kind="job", action_id="explore.deepen", execution=execution)
    total = costs.total(op, ancestry=True)
    assert total["estimated_cost_usd"] is None
    assert total["known_estimated_subtotal_usd"] == .125678
    assert op["op_id"] in total["unaccounted_operation_ids"]
    alter_execution(reading["operation_id"], lambda e: e["plan"].update(question="changed before worker"))
    with pytest.raises(ValueError):
        deeper.run(context, app.gateway_class())
    assert app.prompts == []


def test_linked_retry_retains_failed_attempt_unknown_cost_and_known_key(app, reading, monkeypatch):
    class FailingGateway(app.gateway_class):
        def complete(self, prompt):
            raise RuntimeError("offline fixture interrupted response")
    monkeypatch.setattr(server, "server_gateway", FailingGateway)
    proposal = prepare(app, subject=reading["subject"])
    first = start(app, proposal, "failed-linked-first")
    prior = ops.get(first["operation_id"])
    assert prior["status"] == "failed"
    for name, amount in (("known_part", .07), ("unknown_part", None)):
        costs._append(prior["op_id"], {"schema": costs.SCHEMA, "entry_id": "failed-" + name,
            "operation_id": prior["op_id"], "event_type": "settlement", "component": name, "attempt_id": name,
            "estimated_cost_usd": amount, "known_estimated_subtotal_usd": amount or 0,
            "actual_cost_usd": None, "usage": []})
    monkeypatch.setattr(server, "server_gateway", app.gateway_class)
    url = "/api/operations/" + prior["op_id"] + "/attempts"
    reply = app.client.post(url, json={"request_key": "explicit-linked-retry"})
    assert reply.status_code == 200, reply.get_json()
    retry = ops.get(reply.get_json()["operation_id"])
    assert retry["status"] == "complete"
    assert retry["execution"]["plan"]["follow_up_of"] == prior["op_id"]
    assert retry["execution"]["plan"]["source_operation"] == prior["execution"]["plan"]["source_operation"]
    totals = costs.total(retry, ancestry=True)
    assert totals["operation_ids"] == [retry["op_id"], prior["op_id"], reading["operation_id"]]
    assert totals["known_estimated_subtotal_usd"] >= .195678
    assert totals["estimated_cost_usd"] is totals["actual_cost_usd"] is None
    before = len(app.dispatched)
    replay = app.client.post(url, json={"request_key": "explicit-linked-retry"}).get_json()
    assert replay["repeated"] is True and replay["operation_id"] == retry["op_id"]
    assert len(app.dispatched) == before


def test_linked_retry_refuses_cycle_without_dispatch(app, reading):
    first = start(app, prepare(app, subject=reading["subject"]), "cyclic-linked-first")
    alter_execution(first["operation_id"], lambda e: e["plan"].update(follow_up_of=first["operation_id"]))
    before = len(app.dispatched)
    response = app.client.post("/api/operations/" + first["operation_id"] + "/attempts", json={"request_key": "cyclic-retry"})
    assert response.status_code == 409 and response.get_json()["nothing_was_sent"] is True
    assert len(app.dispatched) == before


@pytest.mark.parametrize("missing_parent", [False, True])
def test_undispatched_linked_retry_resumes_same_fingerprint_after_restart(app, reading, monkeypatch, missing_parent):
    first = start(app, prepare(app, subject=reading["subject"]), "first-before-queued-retry")
    dispatch = server._dispatch_job
    monkeypatch.setattr(server, "_dispatch_job", lambda oid, mode, text: server.jsonify(
        {"job_id": oid, "status": "queued", "dispatched": False}))
    reply = app.client.post("/api/operations/" + first["operation_id"] + "/attempts", json={"request_key": "queued-linked-retry"})
    assert reply.status_code == 200, reply.get_json()
    retry_id = reply.get_json()["operation_id"]
    before = ops.get(retry_id)
    assert before["status"] == "queued" and retry_id not in app.dispatched
    if missing_parent:
        conn = ops._connect()
        try:
            conn.execute("DELETE FROM operations WHERE op_id=?", (first["operation_id"],))
        finally:
            conn.close()
    monkeypatch.setattr(server, "JOBS", {})
    monkeypatch.setattr(server, "_dispatch_job", dispatch)
    monkeypatch.setattr(server, "_dispatching", lambda: True)
    monkeypatch.setattr(server.vault, "preview_mode", lambda: False)
    monkeypatch.setattr(server.opencase, "resume_known", lambda: [])
    monkeypatch.setattr(server.deflate_workflow, "resume_known", lambda: [])
    summary = server._ops_startup()
    after = ops.get(retry_id)
    if missing_parent:
        assert after["status"] == "failed" and "prior attempt is missing" in after["last_error"]
        assert retry_id not in summary["resumed"] and retry_id not in app.dispatched
        return
    assert retry_id in summary["resumed"]
    assert after["status"] == "complete"
    assert after["fingerprint"] == before["fingerprint"]
    assert after["execution"]["plan"]["follow_up_of"] == first["operation_id"]
    assert app.dispatched.count(retry_id) == 1
    again = server._ops_startup()
    assert retry_id not in again["resumed"] and app.dispatched.count(retry_id) == 1
