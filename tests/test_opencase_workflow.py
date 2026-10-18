"""Offline contract tests; no provider, network source or live store is used."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch
from contextlib import contextmanager

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
SCRATCH = tempfile.TemporaryDirectory(prefix="nk-opencase-", dir="/private/tmp")
os.environ["WORDICON_TEST_MODE"] = "1"
os.environ["WORDICON_STATE"] = str(Path(SCRATCH.name) / "state")
os.environ["NK_WORKFLOW_FIXTURE_TOKEN"] = "fixture-credential-do-not-store"

import server
import actions
import federation
import gate
import opencase
import operations as ops
import producers
import wordicon_cli as cli


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nk-case-test-", dir="/private/tmp")
        cli.LOCAL_STATE = Path(self.temp.name)
        federation.register_connector("case-test", "open_case", "http://127.0.0.1:31888", credential_ref="env:NK_WORKFLOW_FIXTURE_TOKEN", dev_loopback=True)
        self.client = server.app.test_client()
        self.client.set_cookie(gate.SESSION_COOKIE, gate.issue_session("test")["token"])
        self.calls = []
        self.plan = None
        self.status_word = "completed"
        self.deposition = None
        self.case_id = "c576b8c6-a658-4ae5-b813-f086430e8bea"

    def tearDown(self):
        self.temp.cleanup()

    def prepare(self, **inputs):
        data = {"subject_name": "Fixture Judge", "subject_type": "federal_judge", "allowance": {"max_cost_usd": 0, "paid_models": False}, **inputs}
        r = self.client.post("/api/actions/prepare", json={"action_id": opencase.ACTION,
            "subject": {"kind": "description", "text": "What public records concern Fixture Judge?"}, "inputs": data})
        self.assertEqual(r.status_code, 200, r.json)
        return r.json

    def fixture(self, connector, method, path, body, auth="none"):
        self.calls.append((method, path))
        self.assertEqual(auth, "bearer")
        if method == "POST":
            self.plan = {k: v for k, v in body.items() if k != "request_key"}
        job = {"job_id": "fixture-job", "status": self.status_word, "case_id": self.case_id,
               "plan": self.plan, "progress": {"stage": "source", "message": "FJC: clean"}, "events": [{"seq": 1, "type": "source"}]}
        result = {"schema": "open_case.investigation.result.v1", "job_id": "fixture-job", "case_id": self.case_id, "status": self.status_word,
                  "plan": self.plan, "question": self.plan["question"], "origin": self.plan["origin"], "allowance": self.plan["allowance"],
                  "actual_cost_usd": 0, "model_runs": [], "findings": [{"id": "e1", "title": "Fixture biography", "source_url": "https://example.test/fixture"}],
                  "sources": [{"name": "Fixture FJC", "url": "https://example.test/fixture"}], "failures": [], "deposition": self.deposition,
                  "deposition_json": json.dumps(self.deposition) if self.deposition else None}
        obj = result if path.endswith("/result") else job
        return {"ok": True, "json": obj, "raw": json.dumps(obj).encode(), "status": 200, "delivery": "delivered"}

    def start(self, prepared, key="one"):
        with patch.object(server, "_dispatching", return_value=True), patch.object(opencase, "launch", side_effect=lambda oid, resume=False: opencase._run(oid, resume)):
            return self.client.post("/api/operations", json={"prepared_id": prepared["prepared_id"], "request_key": key})

    def test_prepare_is_local_and_freezes_large_origin(self):
        with patch.object(producers, "_request", side_effect=AssertionError("prepare must be local")):
            p = self.prepare(origin={"kind": "description", "text": "source passage " * 10000, "title": "Large origin"})
        plan = p["inputs"]["plan"]
        self.assertGreater(len(plan["origin"]["text"]), 32000)
        self.assertLess(len(json.dumps(plan["outbound_origin"])), 32000)
        self.assertTrue(plan["origin"]["snapshot_id"])
        self.assertEqual(plan["subject_type"], "federal_judge_district")
        self.assertEqual(p["disclosure"]["investigation_plan"], plan)
        self.assertEqual(ops.counts()["complete"], 0)

    def test_complete_save_reopen_and_no_repeat(self):
        p = self.prepare()
        with patch.object(producers, "_request", side_effect=self.fixture):
            started = self.start(p)
            self.assertEqual(started.status_code, 200, started.json)
            repeated = self.start(p)
        oid = started.json["operation_id"]
        self.assertEqual(repeated.json["operation_id"], oid)
        self.assertEqual(sum(method == "POST" for method, _ in self.calls), 1)
        with patch.object(producers, "_request", side_effect=AssertionError("reopening is local")):
            got = self.client.get(f"/api/open-case/operations/{oid}")
            self.assertEqual(got.json["status"], "complete", got.json)
            self.assertEqual(got.json["result"]["findings"][0]["id"], "e1")
            saved = self.client.post(f"/api/open-case/operations/{oid}/save", json={})
            self.assertTrue(saved.json["saved"])
            fresh_client = server.app.test_client()
            fresh_client.set_cookie(gate.SESSION_COOKIE, gate.issue_session("reopened")["token"])
            reopened = fresh_client.get(f"/api/open-case/operations/{oid}").json
            self.assertEqual(reopened["result"], got.json["result"])
            self.assertEqual(reopened["artifacts"], got.json["artifacts"])
            self.assertTrue(reopened["saved"])
        self.assertNotIn(os.environ["NK_WORKFLOW_FIXTURE_TOKEN"], json.dumps(reopened))
        raw = self.client.get(reopened["artifacts"][-1]["url"])
        self.assertEqual(hashlib.sha256(raw.data).hexdigest(), reopened["artifacts"][-1]["sha256"])
        (producers.artifact_dir(oid) / reopened["artifacts"][-1]["name"]).write_text("tampered")
        self.assertEqual(self.client.get(reopened["artifacts"][-1]["url"]).status_code, 409)

    def test_paid_and_changed_connection_refused(self):
        for allowance in ({"max_cost_usd": 1, "paid_models": False}, {"max_cost_usd": 0, "paid_models": True}, {"max_cost_usd": False, "paid_models": False}):
            with self.assertRaises(opencase.WorkflowError):
                opencase.prepare("question", {"subject_name": "Fixture", "allowance": allowance})
        p = self.prepare()
        federation.register_connector("case-test", "open_case", "http://127.0.0.1:31889", credential_ref="env:NK_WORKFLOW_FIXTURE_TOKEN", dev_loopback=True)
        with patch.object(producers, "_request", side_effect=AssertionError("changed origin must not dispatch")):
            refused = self.start(p)
        self.assertEqual(refused.status_code, 409)
        self.assertTrue(refused.json["nothing_was_sent"])

    def test_unknown_start_is_not_replayed(self):
        p = self.prepare()
        failure = {"ok": False, "delivery": "unknown", "outcome": "unreachable", "detail": "fixture lost reply"}
        with patch.object(producers, "_request", return_value=failure) as request:
            started = self.start(p)
            self.assertEqual(request.call_count, 1)
        op = ops.get(started.json["operation_id"])
        self.assertEqual(op["status"], "unknown")
        with self.assertRaises(opencase.WorkflowError):
            opencase.recover(op)
        with patch.object(opencase, "launch") as launch:
            opencase.resume_known()
            launch.assert_not_called()

    def test_known_job_resumes_without_start(self):
        p = self.prepare()
        plan = p["inputs"]["plan"]
        self.plan = {k: plan[k] for k in ("question", "subject_name", "subject_type", "jurisdiction", "allowance", "follow_up_of", "task_profile")}
        self.plan["origin"] = plan["outbound_origin"]
        op, _ = ops.reserve(request_key="interrupted", kind="investigation", action_id=opencase.ACTION,
            execution={"plan": plan}, config={"state_root": str(cli.LOCAL_STATE.resolve())})
        ops.mark(op["op_id"], "unknown", result_ref={"upstream_id": "fixture-job"})
        copied, _ = ops.reserve(request_key="copied", kind="investigation", action_id=opencase.ACTION,
            execution={"plan": plan}, config={"state_root": "/a/different/original/store"})
        ops.mark(copied["op_id"], "unknown", result_ref={"upstream_id": "copied-job"})
        with patch.object(opencase, "launch", return_value=True) as launch:
            self.assertEqual(opencase.resume_known(), [op["op_id"]])
            launch.assert_called_once_with(op["op_id"], resume=True)
        depth = [0]
        @contextmanager
        def nonreentrant_guard():
            self.assertEqual(depth[0], 0, "vault guards must never nest")
            depth[0] += 1
            try:
                yield
            finally:
                depth[0] -= 1
        with patch.object(producers, "_request", side_effect=self.fixture), patch.object(opencase.vault, "corpus_write", nonreentrant_guard):
            opencase._run(op["op_id"], resume=True)
        self.assertEqual(ops.get(op["op_id"])["status"], "complete")
        self.assertFalse(any(m == "POST" for m, _ in self.calls))

    def test_followup_keeps_origin_and_bad_artifact_paths_refused(self):
        p = self.prepare(origin={"kind": "description", "text": "original passage"})
        with patch.object(producers, "_request", side_effect=self.fixture):
            started = self.start(p)
        oid = started.json["operation_id"]
        followup = self.prepare(follow_up_of=oid, origin={"kind": "question", "text": "replacement origin"})
        self.assertEqual(followup["inputs"]["plan"]["origin"], p["inputs"]["plan"]["origin"])
        with self.assertRaises(opencase.WorkflowError):
            opencase.artifact(ops.get(oid), "../../other")

    def test_verified_deposition_preserved_and_partial_is_explicit(self):
        directory = ROOT / "tests/fixtures/federation"
        self.deposition = json.loads((directory / "open_case.exemplar.deposition.json").read_text())
        self.case_id = self.deposition["object"]["id"]
        self.status_word = "partial"
        federation.pin_key("case-test", (directory / "open_case.fixture.pub.b64").read_text().strip(), label="test")
        prepared = self.prepare()
        with patch.object(producers, "_request", side_effect=self.fixture):
            started = self.start(prepared)
        view = opencase.view(ops.get(started.json["operation_id"]))
        self.assertEqual(view["result"]["status"], "partial")
        self.assertIn("Partial", view["progress"])
        self.assertTrue(view["custody"]["verification"]["ok"], view["custody"])
        self.assertTrue(view["deposition_id"])

    def test_wrong_record_and_paid_result_are_kept_but_not_accepted(self):
        for change in ("subject_name", "actual_cost_usd"):
            prepared = self.prepare()
            def wrong(*args, **kwargs):
                r = self.fixture(*args, **kwargs)
                if args[2].endswith("/result"):
                    obj = json.loads(r["raw"])
                    if change == "subject_name":
                        obj["plan"]["subject_name"] = "Another subject"
                    else:
                        obj["actual_cost_usd"] = 1
                    r.update(json=obj, raw=json.dumps(obj).encode())
                return r
            with patch.object(producers, "_request", side_effect=wrong):
                started = self.start(prepared, key=change)
            view = opencase.view(ops.get(started.json["operation_id"]))
            self.assertEqual(view["status"], "unknown")
            self.assertIsNone(view["result"])
            self.assertTrue(any(a["name"] == "result.json" for a in view["artifacts"]))

    def test_pairing_and_cross_origin_gates_apply(self):
        unpaired = server.app.test_client()
        self.assertEqual(unpaired.get("/api/open-case/operations").status_code, 401)
        self.assertEqual(self.client.post("/api/open-case/authorize", json={}, headers={"Origin": "https://outside.example"}).status_code, 403)


if __name__ == "__main__":
    unittest.main()
