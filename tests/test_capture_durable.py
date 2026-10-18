"""Capture persistence fixtures; no provider, network or live store."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
from types import SimpleNamespace
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
os.environ["WORDICON_TEST_MODE"] = "1"
SCRATCH = tempfile.TemporaryDirectory(prefix="nk-capture-fixture-", dir="/private/tmp")
os.environ["WORDICON_STATE"] = str(Path(SCRATCH.name) / "state")
import wordicon_cli as cli
import operations as ops


class CaptureTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nk-capture-test-", dir="/private/tmp")
        self.old = cli.LOCAL_STATE
        cli.LOCAL_STATE = Path(self.temp.name)
        self.op, _ = ops.reserve(request_key="fixture", kind="job", execution={"fixture": True})

    def tearDown(self):
        cli.LOCAL_STATE = self.old
        self.temp.cleanup()

    def test_response_metadata_survives_before_any_final_result(self):
        class Gateway(cli.Gateway):
            name = "fixture"
            model = "offline-model"
            def complete(self, prompt):
                return self._call_with_attempts("fixture_stage", lambda: SimpleNamespace(
                    id="msg_fixture1", model="resolved-provider-model", stop_reason="max_tokens", usage=SimpleNamespace(input_tokens=25,
                    output_tokens=10, cache_read_input_tokens=12), headers={"Authorization": "Bearer never-store"}))
        g = Gateway()
        ops.attach(g, self.op["op_id"])
        g.complete("fixture_stage\nPRIVATE REQUEST BODY")
        del g
        # Separate process reads the authority; no in-memory ledger or result.
        script = "import sqlite3,json,sys; c=sqlite3.connect(sys.argv[1]+'?mode=ro',uri=True); print(json.dumps(c.execute('select kind,detail from operation_events order by seq').fetchall()))"
        raw = subprocess.check_output([sys.executable, "-c", script, ops.db_path().as_uri()], text=True)
        events = [(kind, json.loads(detail)) for kind, detail in json.loads(raw)]
        start = next(d for kind, d in events if kind == "attempt_intent")
        end = next(d for kind, d in events if kind == "attempt_end")
        self.assertEqual(start["call_id"], end["call_id"])
        self.assertEqual(start["attempt_id"], end["attempt_id"])
        self.assertEqual(end["provider_run_id"], "msg_fixture1")
        self.assertEqual(end["model"], "offline-model")
        self.assertEqual(end["provider_model"], "resolved-provider-model")
        self.assertEqual(set(end["sdk"]), {"anthropic", "transport", "transport_version"})
        self.assertEqual(end["stop_reason"], "max_tokens")
        self.assertEqual({r["category"]: r["count"] for r in end["usage_categories"]},
                         {"input_tokens": 25, "output_tokens": 10, "cache_read_input_tokens": 12})
        self.assertNotIn("PRIVATE REQUEST BODY", raw)
        self.assertNotIn("Authorization", raw)
        self.assertNotIn("never-store", raw)

    def test_partial_usage_and_error_are_durable_without_credentials(self):
        class Gateway(cli.Gateway):
            name = "fixture"
            def complete(self, prompt):
                def call():
                    raise cli.StreamInterrupted("Bearer secret-must-never-appear", True, "ReadError",
                        response_record={"response_id": "msg_partial", "usage": {"input_tokens": 3, "output_tokens": 2},
                                         "response": {"model": "observed-model-version"}})
                return self._call_with_attempts("fixture_stage", call, max_attempts=1)
        g = Gateway();ops.attach(g, self.op["op_id"])
        with self.assertRaises(cli.StreamInterrupted):g.complete("fixture_stage")
        events = ops.events(self.op["op_id"])
        end = next(e["detail"] for e in events if e["kind"] == "attempt_end")
        self.assertFalse(end["usage_complete"])
        self.assertEqual(end["provider_run_id"], "msg_partial")
        self.assertEqual(end["provider_model"], "observed-model-version")
        self.assertNotIn("secret-must-never-appear", json.dumps(events))

    def test_hook_accepts_only_typed_usage_and_metadata(self):
        ops._hook(self.op["op_id"], "attempt_end", provider="fixture", model="sk-secret-not-a-model",
                  usage_categories=[{"category": "input_tokens", "count": 3},
                    {"category": "authorization", "count": 99}, {"category": "output_tokens", "count": True},
                    {"category": "cache_read_input_tokens", "count": -1}],
                  request_headers={"Cookie": "never-store"}, response={"secret": "never-store"})
        detail = ops.events(self.op["op_id"])[-1]["detail"]
        self.assertEqual(detail["usage_categories"], [{"category": "input_tokens", "count": 3}])
        self.assertIsNone(detail["model"])
        self.assertIsNone(detail["usage_complete"])
        self.assertNotIn("never-store", json.dumps(detail))

    def test_each_attempt_has_durable_intent_and_call_identity_before_dispatch(self):
        class Transient(Exception): pass
        op_id = self.op["op_id"]
        outer = self
        class Gateway(cli.Gateway):
            name = "fixture"
            BACKOFF_BASE_S = 0
            def _retryable(self): return ((), (Transient,))
            def complete(self, prompt):
                def call():
                    events = ops.events(op_id)
                    outer.assertEqual(events[-1]["kind"], "attempt_intent")
                    if events[-1]["attempt"] == 1: raise Transient("fixture transient")
                    return SimpleNamespace(id="msg_recovered",usage=None)
                return self._call_with_attempts("fixture_stage", call)
        g = Gateway();ops.attach(g, op_id)
        g.complete("fixture_stage");g.complete("fixture_stage")
        intents = [e for e in ops.events(op_id) if e["kind"] == "attempt_intent"]
        ends = [e for e in ops.events(op_id) if e["kind"] == "attempt_end"]
        self.assertEqual(len(intents),4)
        self.assertEqual(len({e["detail"]["call_id"] for e in intents}),2)
        self.assertEqual(len({e["detail"]["attempt_id"] for e in intents}),4)
        self.assertEqual({e["detail"]["attempt_id"] for e in intents},{e["detail"]["attempt_id"] for e in ends})
        failures = [e["detail"] for e in ends if e["outcome"] == "error"]
        self.assertTrue(all(e["usage_complete"] is None and e["usage_categories"] == [] and e["response_observed"] is False for e in failures))
        successes = [e["detail"] for e in ends if e["outcome"] == "ok"]
        self.assertTrue(all(e["usage_complete"] is None and e["usage_categories"] == [] and e["response_observed"] is True for e in successes))



if __name__ == "__main__":
    unittest.main()
