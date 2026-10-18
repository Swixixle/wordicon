"""Authenticated capture boundaries, scratch state only; no provider calls."""
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
os.environ["WORDICON_TEST_MODE"] = "1"
BOOT = tempfile.TemporaryDirectory(prefix="nk-capture-route-", dir=Path(tempfile.gettempdir()).resolve())
os.environ["WORDICON_STATE"] = BOOT.name
import server
import gate
import wordicon_cli as cli
import workspace_identity
import operations as ops
import producers


class CaptureRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nk-capture-route-", dir=Path(tempfile.gettempdir()).resolve())
        self.prior = cli.LOCAL_STATE
        cli.LOCAL_STATE = Path(self.temp.name)
        self.client = server.app.test_client()
        self.client.set_cookie(gate.SESSION_COOKIE, gate.issue_session("fixture")["token"])

    def tearDown(self):
        cli.LOCAL_STATE = self.prior
        self.temp.cleanup()

    def hashes(self):
        return {str(p.relative_to(cli.LOCAL_STATE)): hashlib.sha256(p.read_bytes()).hexdigest()
                for p in cli.LOCAL_STATE.rglob("*") if p.is_file()}

    def test_capture_routes_require_pairing(self):
        client = server.app.test_client()
        for path in ("/api/capture/history?doc_id=doc_fixture", "/api/capture/gaps",
                     "/api/capture/operations/op_fixture/artifacts/body.json"):
            self.assertEqual(client.get(path).status_code, 401, path)

    def test_missing_identity_is_named_and_not_initialized_by_reads(self):
        before = self.hashes()
        for path in ("/api/ledger/config", "/api/ledger"):
            response = self.client.get(path)
            self.assertEqual(response.status_code, 503, response.json)
            self.assertEqual(response.json["code"], "workspace_identity_unavailable")
        self.assertEqual(self.hashes(), before)

    def test_search_still_returns_results_when_capture_guard_fails(self):
        with patch.object(server.library, "search", return_value=[{"id": "fixture"}]), \
             patch.object(server.vault, "corpus_write", side_effect=OSError("unavailable")):
            response = self.client.get("/api/library/search?q=fixture")
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json["results"], [{"id": "fixture"}])
        self.assertFalse(response.json["capture"]["kept"])
        self.assertFalse(response.json["capture"]["capture_gap"]["durable"])

    def test_history_and_artifact_reads_are_immutable_and_refuse_tampering(self):
        workspace_identity.ensure()
        op, _ = ops.reserve(request_key="fixture", kind="investigation", execution={"plan": {"question": "Fixture?"}})
        raw = json.dumps({"findings": [], "source_statuses": {}}).encode()
        kept = producers.keep_artifact(op["op_id"], "result.json", raw)
        ops.mark(op["op_id"], "complete", result_ref={"kept": [kept], "result_artifact": kept})
        before = self.hashes()
        path = "/api/capture/operations/" + op["op_id"] + "/artifacts/result.json"
        with patch.object(producers, "_request", side_effect=AssertionError("read cannot dispatch")):
            first = self.client.get("/api/capture/history?operation_id=" + op["op_id"])
            second = self.client.get("/api/capture/history?operation_id=" + op["op_id"])
            artifact = self.client.get(path)
        self.assertEqual(first.status_code, 200, first.json)
        self.assertEqual(first.json, second.json)
        self.assertEqual(artifact.data, raw)
        self.assertEqual(artifact.headers["X-Content-Type-Options"], "nosniff")
        self.assertEqual(self.hashes(), before)
        (producers.artifact_dir(op["op_id"]) / "result.json").write_text("substitute")
        self.assertEqual(self.client.get(path).status_code, 409)
        self.assertEqual(self.client.get("/api/capture/history?operation_id=" + op["op_id"] + "&doc_id=doc_fixture").status_code, 400)


if __name__ == "__main__":
    unittest.main()
