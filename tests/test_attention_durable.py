"""Attention raw-store durability fixtures; no provider or live store."""
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest import mock
from concurrent.futures import ThreadPoolExecutor

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
os.environ["WORDICON_TEST_MODE"] = "1"
SCRATCH = tempfile.TemporaryDirectory(prefix="nk-attention-fixture-", dir="/private/tmp")
os.environ["WORDICON_STATE"] = str(Path(SCRATCH.name) / "state")
import wordicon_cli as cli
import ledger


class AttentionTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nk-attention-test-", dir="/private/tmp")
        self.old = cli.LOCAL_STATE
        cli.LOCAL_STATE = Path(self.temp.name)

    def tearDown(self):
        cli.LOCAL_STATE = self.old
        self.temp.cleanup()

    def event(self, event_id="event_visit_1"):
        return {"event_id": event_id, "session_id": "session_1", "scope_id": ledger.scope_id(),
                "type": "document_opened", "at": "2026-10-18T09:00:00-04:00", "subject": {"id": "doc_1", "title": "A fixture"}}

    def test_ack_loss_restart_and_simultaneous_delivery_keep_one_visit(self):
        event = self.event()
        first = ledger.append([event])
        self.assertEqual(first["acknowledged"], [event["event_id"]])
        # Simulate losing the acknowledgement and restarting the server process.
        script = "import sys,json;sys.path.insert(0,sys.argv[1]);import wordicon_cli as c,ledger;from pathlib import Path;c.LOCAL_STATE=Path(sys.argv[2]);print(json.dumps(ledger.append(json.loads(sys.argv[3]))))"
        again = json.loads(subprocess.check_output([sys.executable, "-c", script, str(ROOT / "scripts"), str(cli.LOCAL_STATE), json.dumps([event])], text=True))
        self.assertEqual((again["kept"], again["duplicates"]), (0, 1))
        with ThreadPoolExecutor(max_workers=6) as pool:
            results = list(pool.map(lambda _: ledger.append([event]), range(12)))
        self.assertTrue(all(r["acknowledged"] == [event["event_id"]] and r["kept"] == 0 for r in results))
        rows = ledger.read()["events"]
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["at"], event["at"])
        self.assertNotEqual(rows[0]["received_at"], event["at"])

    def test_distinct_intentional_visits_survive_and_conflicting_id_is_refused(self):
        a, b = self.event(), self.event("event_visit_2")
        result = ledger.append([a, a, b])
        self.assertEqual((result["kept"], result["duplicates"]), (2, 1))
        changed = {**a, "subject": {"id": "different"}}
        self.assertEqual(ledger.append([changed])["code"], "event_id_conflict")
        self.assertEqual(len(ledger.read()["events"]), 2)

    def test_interrupted_tail_preserved_and_observable_without_hiding_good_rows(self):
        ledger.append([self.event()])
        path = next(ledger._dir().glob("events-*.jsonl"))
        original = path.read_bytes() + b'{"event_id":"unfinished'
        path.write_bytes(original)
        result = ledger.append([self.event("event_after_crash")])
        self.assertEqual(result["kept"], 1)
        self.assertEqual(result["capture_gaps"][0]["kind"], "malformed_record")
        self.assertTrue(path.read_bytes().startswith(original + b"\n"))
        recovered = ledger.read()
        self.assertEqual(len(recovered["events"]), 2)
        self.assertEqual(recovered["capture_gaps"], result["capture_gaps"])

    def test_failed_fsync_does_not_ack_and_retry_deduplicates_existing_bytes(self):
        with mock.patch.object(ledger.os, "fsync", side_effect=OSError("fixture disk failure")):
            with self.assertRaises(OSError):
                ledger.append([self.event()])
        retry = ledger.append([self.event()])
        self.assertEqual((retry["kept"], retry["duplicates"]), (0, 1))
        self.assertEqual(len(ledger.read()["events"]), 1)

    def test_off_and_corrupt_switch_refuse_new_capture_preserving_existing(self):
        ledger.append([self.event()])
        ledger.set_enabled(False)
        self.assertEqual(ledger.append([self.event("event_off")])["code"], "recording_off")
        self.assertEqual(len(ledger.read()["events"]), 1)
        ledger._config_path().write_text("{incomplete", encoding="utf-8")
        self.assertFalse(ledger.enabled())
        self.assertEqual(ledger.append([self.event("event_unknown_switch")])["code"], "recording_off")
        ledger.set_enabled(True)
        self.assertEqual(ledger.append([self.event("event_on")])["kept"], 1)

    def test_wrong_store_unreadable_raw_and_legacy_idempotency_are_explicit(self):
        event = self.event()
        event["scope_id"] = "ledger_wrong"
        self.assertEqual(ledger.append([event])["code"], "scope_mismatch")
        legacy = {"type": "page_shown", "subject": {"page": "work", "body": "PRIVATE BODY"}}
        ledger.append([legacy]); ledger.append([legacy])
        rows = ledger.read()["events"]
        self.assertEqual(len(rows), 2)
        self.assertTrue(all(r["delivery_idempotency"] == "unavailable_legacy_client" for r in rows))
        self.assertNotIn("PRIVATE BODY", json.dumps(rows))
        path = ledger._dir() / "events-2020-01.jsonl"
        path.write_bytes(b"\xff")
        result = ledger.append([self.event()])
        self.assertEqual(result["code"], "store_unreadable")
        self.assertNotIn("acknowledged", result)


if __name__ == "__main__":
    unittest.main()
