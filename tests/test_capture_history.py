"""Offline reconstruction tests: existing scratch records, no live calls."""
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
os.environ["WORDICON_TEST_MODE"] = "1"
BOOT = tempfile.TemporaryDirectory(prefix="nk-capture-history-", dir="/private/tmp")
os.environ["WORDICON_STATE"] = BOOT.name
import wordicon_cli as cli
import operations as ops
import producers
import notebook
import snapshots
import capture
import workspace_identity
import capture_history as history


class HistoryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nk-history-", dir="/private/tmp")
        self.prior = cli.LOCAL_STATE
        cli.LOCAL_STATE = Path(self.temp.name)
        self.workspace = workspace_identity.ensure()
        self.did = "doc_history_fixture"
        self.body = "PRIVATE BODY A. 😀 precise passage"
        first = notebook.save(self.did, title="Fixture", title_is_manual=True, body="PRIVATE BODY A.", base_revision=0, base_fingerprint="", request_id="request_history_a")
        notebook.save(self.did, title="Fixture", title_is_manual=True, body=self.body, base_revision=1, base_fingerprint=first["fingerprint"], request_id="request_history_b")
        start = len("PRIVATE BODY A. ")
        self.snap = snapshots.make(kind="selection", text="😀 precise passage", doc_id=self.did, revision=2,
                                   range_={"start": start, "end": start + len("😀 precise passage")}, units="codepoint")
        snapshots.write(self.snap)
        self.proposal = {"prepared_id": "", "action_id": "analyze.decompose", "snapshot_id": self.snap["snapshot_id"], "prepared_at": "2026-10-18T00:00:00Z"}
        self.proposal["prepared_id"] = "prep_" + hashlib.sha256(json.dumps(self.proposal, sort_keys=True, ensure_ascii=False).encode()).hexdigest()[:20]
        path = cli.LOCAL_STATE / "proposals"; path.mkdir()
        (path / (self.proposal["prepared_id"] + ".json")).write_text(json.dumps(self.proposal))

    def tearDown(self):
        cli.LOCAL_STATE = self.prior
        self.temp.cleanup()

    def hashes(self):
        return {str(p.relative_to(cli.LOCAL_STATE)): hashlib.sha256(p.read_bytes()).hexdigest() for p in cli.LOCAL_STATE.rglob("*") if p.is_file()}

    def operation(self, *, key="first", plan=None, retry_parent=None):
        op, _ = ops.reserve(request_key=key, kind="investigation", execution={"plan": plan or {"question": "What does this record say?", "origin": {"doc_id": self.did, "revision": 2}}},
                            action_id="investigate.opencase.question", prepared_id=self.proposal["prepared_id"], snapshot_id=self.snap["snapshot_id"], retry_parent=retry_parent)
        return op

    def source_result(self, op):
        result = {"findings": [{"id": "source1", "title": "Public fixture record", "body": "Saved public source body", "evidence_kind": "official_primary_record"}],
                  "source_statuses": {"fjc": "cached"}, "failures": [{"source": "optional-source", "status": "network_failure", "message": "Timed out"}],
                  "source_checks": [{"source_name": "FJC", "status": "searched_with_evidence", "result_count": 1}],
                  "dimensions": {"acquisition": {"capabilities": [{"id": "stub", "role": "unimplemented", "reason": "Adapter is not implemented"}]}}}
        kept = producers.keep_artifact(op["op_id"], "result.json", json.dumps(result).encode())
        ops.mark(op["op_id"], "complete", result_ref={"kept": [kept], "result_artifact": kept})
        return kept

    def test_unstarted_proposal_has_exact_selection_links_without_private_bodies_or_writes(self):
        before = self.hashes()
        with patch.object(ops, "_connect", side_effect=AssertionError("read must not initialize SQLite")), patch.object(producers, "_request", side_effect=AssertionError("no network")):
            view = history.view(doc_id=self.did)
        self.assertEqual(view["workspace"], self.workspace)
        self.assertEqual(len(view["nodes"]["revisions"]), 2)
        self.assertTrue(view["nodes"]["snapshots"][0]["committed_revision_match"])
        self.assertEqual(view["nodes"]["proposals"][0]["status"], "prepared")
        self.assertEqual(view["nodes"]["operations"], [])
        self.assertNotIn("PRIVATE BODY", json.dumps(view))
        self.assertNotIn("precise passage", json.dumps(view))
        self.assertEqual(before, self.hashes())

    def test_attempt_failure_and_response_capture_refs_are_traceable_without_credentials(self):
        op = self.operation()
        request = producers.keep_artifact(op["op_id"], "capture-request.json", b'{"private_prompt":"SECRET REQUEST"}')
        response = producers.keep_artifact(op["op_id"], "capture-response.json", b'{"response":"Saved exact response"}')
        for kind, phase, art, outcome in (("attempt_intent", "request", request, ""), ("attempt_end", "failure", response, "error")):
            ops.event(op["op_id"], kind, stage="fixture", outcome=outcome, detail={"call_id": "call-one", "attempt_id": "attempt-one", "message": "source failed",
                "capture": {"schema": "nikodemus.operation-capture.v1", "phase": phase, "artifact": art, "request_artifact": request,
                            "call_id": "call-one", "attempt_id": "attempt-one", "Authorization": "NEVER SHOW", "body": "NEVER SHOW"}})
        before = self.hashes()
        view = history.view(operation_id=op["op_id"])
        self.assertEqual(len(view["nodes"]["attempts"]), 2)
        self.assertEqual({a["detail"]["attempt_id"] for a in view["nodes"]["attempts"]}, {"attempt-one"})
        self.assertEqual(view["nodes"]["answers"][0]["phase"], "failure")
        self.assertFalse(view["nodes"]["answers"][0]["answer_available"])
        self.assertEqual(history.artifact(op["op_id"], response["name"]), b'{"response":"Saved exact response"}')
        self.assertNotIn("SECRET REQUEST", json.dumps(view))
        self.assertNotIn("NEVER SHOW", json.dumps(view))
        self.assertEqual(before, self.hashes())

    def test_changed_artifact_is_a_gap_and_never_displayed_as_evidence(self):
        op = self.operation(); self.source_result(op)
        (producers.artifact_dir(op["op_id"]) / "result.json").write_text('{"findings":[{"body":"substitute"}]}')
        view = history.view(operation_id=op["op_id"])
        self.assertEqual(view["nodes"]["evidence"], [])
        self.assertIn("artifact_integrity", {g["kind"] for g in view["gaps"]})
        with self.assertRaises(history.HistoryError) as err:
            history.artifact(op["op_id"], "result.json")
        self.assertEqual(err.exception.status, 409)
        with self.assertRaises(history.HistoryError):
            history.artifact(op["op_id"], "../../notebook.sqlite3")

    def test_source_failures_and_capture_gaps_survive_even_when_some_evidence_succeeded(self):
        op = self.operation(); self.source_result(op)
        capture.gap("source_capture_failed", {"op_id": op["op_id"]}, "OSError")
        view = history.view(operation_id=op["op_id"])
        self.assertEqual(len(view["nodes"]["evidence"]), 1)
        self.assertTrue(any(c["status"] == "network_failure" for c in view["nodes"]["source_checks"]))
        self.assertTrue(any(c["source"] == "FJC" and c["status"] == "searched_with_evidence" for c in view["nodes"]["source_checks"]))
        capability = next(c for c in view["nodes"]["source_checks"] if c["kind"] == "declared_source_capability")
        self.assertEqual(capability["role"], "unimplemented")
        self.assertFalse(capability["attempt_inferred"])
        self.assertEqual(view["capture_gaps"]["gaps"][0]["error_class"], "OSError")

    def test_only_explicit_followup_and_retry_edges_expand_the_operation_scope(self):
        op = self.operation()
        child = self.operation(key="child", plan={"question": "Next question", "follow_up_of": op["op_id"]})
        retry = self.operation(key="retry", retry_parent=child["op_id"])
        unlinked = self.operation(key="same-title", plan={"question": "Next question"})
        view = history.view(operation_id=child["op_id"])
        self.assertEqual({o["operation_id"] for o in view["nodes"]["operations"]}, {op["op_id"], child["op_id"], retry["op_id"]})
        self.assertNotIn(unlinked["op_id"], json.dumps(view))
        self.assertEqual({link["relation"] for link in view["links"]} & {"follow_up", "retry"}, {"follow_up", "retry"})

    def test_fresh_process_reconstructs_identical_projection_and_preserves_every_store_byte(self):
        op = self.operation(); self.source_result(op)
        initial = history.view(operation_id=op["op_id"])
        before = self.hashes()
        code = "import json,wordicon_cli; from pathlib import Path; wordicon_cli.LOCAL_STATE=Path(" + repr(str(cli.LOCAL_STATE)) + "); import capture_history; print(json.dumps(capture_history.view(operation_id=" + repr(op["op_id"]) + "),sort_keys=True))"
        env = {**os.environ, "WORDICON_STATE": str(cli.LOCAL_STATE), "WORDICON_TEST_MODE": "1", "PYTHONDONTWRITEBYTECODE": "1", "PYTHONPATH": str(ROOT / "scripts") + os.pathsep + str(ROOT)}
        restarted = json.loads(subprocess.check_output([sys.executable, "-c", code], env=env, text=True))
        self.assertEqual(restarted, initial)
        self.assertEqual(self.hashes(), before)

    def test_missing_snapshot_stays_a_gap_and_is_not_reconstructed_from_newer_head(self):
        op = self.operation()
        (cli.LOCAL_STATE / "snapshots" / (self.snap["snapshot_id"] + ".json")).unlink()
        view = history.view(operation_id=op["op_id"])
        self.assertEqual(view["nodes"]["snapshots"], [])
        self.assertIn("missing_or_invalid_snapshots", {g["kind"] for g in view["gaps"]})

    def test_read_does_not_initialize_missing_workspace_identity(self):
        (cli.LOCAL_STATE / workspace_identity.NAME).unlink()
        before = self.hashes()
        view = history.view(doc_id=self.did)
        self.assertIsNone(view["workspace"])
        self.assertIn("legacy_workspace_identity", {g["kind"] for g in view["gaps"]})
        self.assertEqual(before, self.hashes())

    def test_result_pointer_must_name_the_same_exact_hash_as_the_retained_artifact(self):
        op = self.operation(); kept = self.source_result(op)
        ops.mark(op["op_id"], "complete", result_ref={"kept": [kept], "result_artifact": {**kept, "sha256": "0" * 64}})
        view = history.view(operation_id=op["op_id"])
        self.assertEqual(view["nodes"]["evidence"], [])
        self.assertIn("result_reference_mismatch", {g["kind"] for g in view["gaps"]})

    def test_authoritative_note_retains_capture_failure_when_supplemental_gap_is_not_durable(self):
        op = self.operation()
        ops.event(op["op_id"], "note", detail={"capture_gap": {
            "kept": False, "durable": False, "why": "input_capture_failed", "body": "PRIVATE LOST BODY",
            "capture_gap": {"kept": False, "durable": False, "why": "capture_gap_store_unavailable", "Authorization": "SECRET"}}})
        before = self.hashes()
        with patch.object(ops, "_connect", side_effect=AssertionError("read must not initialize SQLite")):
            view = history.view(operation_id=op["op_id"])
        self.assertEqual(view["capture_gaps"]["gaps"], [])
        self.assertIn("operation_capture_failure", {g["kind"] for g in view["gaps"]})
        saved = view["nodes"]["attempts"][0]["detail"]["capture_gap"]
        self.assertFalse(saved["capture_gap"]["durable"])
        self.assertNotIn("PRIVATE LOST BODY", json.dumps(view)); self.assertNotIn("SECRET", json.dumps(view))
        self.assertEqual(before, self.hashes())

    def test_orphan_gateway_capture_survives_as_recovery_metadata_without_note_repair(self):
        import operation_capture
        op = self.operation()
        with patch.object(ops, "_event", side_effect=OSError("fixture failed event commit")):
            with self.assertRaises(OSError):
                operation_capture._keep(op["op_id"], "response", "attempt_orphan", {
                    "schema": operation_capture.SCHEMA, "phase": "response", "call_id": "call_orphan", "attempt_id": "attempt_orphan",
                    "links": {"operation_id": op["op_id"]}, "response": {"body": "PRIVATE ORPHAN BODY"}})
        before = self.hashes()
        with patch.object(ops, "_connect", side_effect=AssertionError("read must not repair journal")):
            view = history.view(operation_id=op["op_id"])
        recovered = next(a for a in view["nodes"]["artifacts"] if a["verification"] == "verified_unindexed")
        self.assertEqual(recovered["attempt_id"], "attempt_orphan")
        self.assertNotIn("url", recovered)
        self.assertIn("gateway_artifact_link_missing", {g["kind"] for g in view["gaps"]})
        self.assertNotIn("PRIVATE ORPHAN BODY", json.dumps(view))
        self.assertEqual(view["nodes"]["answers"], [])
        self.assertEqual(before, self.hashes())

    def test_duration_estimate_is_validated_and_kept_separate_from_observed_attention(self):
        directory = cli.LOCAL_STATE / "ledger"; directory.mkdir()
        interval = {"policy": "visibility_focus_idle.v1", "state": "foreground_active_estimate", "start_at": "2026-10-18T00:00:00Z",
                    "end_at": "2026-10-18T00:00:12Z", "duration_ms": 12000, "idle_after_ms": 60000, "reason": "checkpoint"}
        event = {"type": "activity_interval", "event_id": "event_interval", "subject": {"id": self.did}, "interval": interval}
        (directory / "events-2026-10-18.jsonl").write_text(json.dumps(event) + "\n" + json.dumps({**event, "event_id": "event_bad_interval", "interval": {**interval, "duration_ms": 999999}}) + "\n")
        view = history.view(doc_id=self.did)
        self.assertEqual(view["nodes"]["attention"][0]["interval"], interval)
        self.assertIsNone(view["nodes"]["attention"][1]["interval"])
        self.assertIn("invalid_activity_interval", {g["kind"] for g in view["gaps"]})


if __name__ == "__main__":
    unittest.main()
