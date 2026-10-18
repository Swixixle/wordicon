"""Named capture losses preserve successful actions and never log secrets."""
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest
from unittest import mock

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
os.environ["WORDICON_TEST_MODE"] = "1"
import wordicon_cli as cli
import capture
import ledger


class CaptureGapTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.old = cli.LOCAL_STATE
        cli.LOCAL_STATE = Path(self.temp.name)

    def tearDown(self):
        cli.LOCAL_STATE = self.old
        self.temp.cleanup()

    def test_queries_are_durable_and_repeated_queries_distinct(self):
        a = capture.query("work", "a useful question", 2)
        b = capture.query("work", "a useful question", 2)
        self.assertTrue(a["kept"] and b["kept"])
        self.assertNotEqual(a["query_id"], b["query_id"])
        rows = capture.read_queries()["queries"]
        self.assertEqual([r["q"] for r in rows], ["a useful question"] * 2)

    def test_failed_query_has_named_durable_gap_and_action_status(self):
        real = capture._append
        def write(name, row):
            if name.startswith("queries-"):
                raise OSError("private failure message must not enter gap")
            return real(name, row)
        with mock.patch.object(capture, "_append", side_effect=write):
            out = capture.query("library", "private text", 0)
        self.assertFalse(out["kept"])
        self.assertTrue(out["capture_gap"]["durable"])
        rows = capture.read_gaps()["gaps"]
        self.assertEqual(rows[0]["kind"], "query_write_failed")
        self.assertNotIn("private", json.dumps(rows))

    def test_credential_query_is_refused_whole_and_gap_excludes_value(self):
        secret = "sk-ant-api03-fixture-secret-value-123456789"
        out = capture.query("work", "search " + secret, 0)
        self.assertEqual(out["why"], "credential_like_query_not_retained")
        self.assertEqual(capture.read_queries()["queries"], [])
        self.assertNotIn(secret, json.dumps(capture.read_gaps()))

    def test_off_preserves_history_and_stops_gap_or_query_capture(self):
        capture.query("work", "before off", 1)
        ledger.set_enabled(False)
        self.assertFalse(capture.query("work", "after off", 1)["kept"])
        self.assertEqual(capture.gap("input_write_failed")["why"], "recording_off")
        self.assertEqual(len(capture.read_queries()["queries"]), 1)

    def test_broken_gap_storage_does_not_claim_durability(self):
        with mock.patch.object(capture, "_append", side_effect=OSError("disk unavailable")):
            result = capture.gap("input_write_failed", {"job_id": "op_test"})
        self.assertFalse(result["durable"])
        self.assertEqual(result["why"], "capture_gap_store_unavailable")

    def test_off_committed_after_early_check_prevents_append(self):
        with mock.patch.object(capture, "enabled", side_effect=[True, False]):
            out = capture.query("work", "racing off", 1)
        self.assertEqual(out["why"], "recording_off")
        self.assertEqual(capture.read_queries()["queries"], [])

    def test_malformed_prior_tail_preserved_and_disclosed(self):
        capture.query("work", "before crash", 1)
        path = next(capture._dir().glob("queries-*.jsonl"))
        original = path.read_bytes() + b'{"incomplete'
        path.write_bytes(original)
        capture.query("work", "after crash", 1)
        self.assertTrue(path.read_bytes().startswith(original + b"\n"))
        read = capture.read_queries()
        self.assertEqual(len(read["queries"]), 2)
        self.assertEqual(read["read_gaps"][0]["kind"], "malformed_record")

    def test_gap_metadata_is_closed_and_read_only(self):
        capture.gap("edge_write_failed", {"op_id": "op_1", "body": "private", "job_id": "sk-secret-12345678", "source_id": "ghp_thisisnotarealkey123456"}, "OSError")
        before = {str(p): p.read_bytes() for p in Path(self.temp.name).rglob("*") if p.is_file()}
        data = capture.read_gaps()
        after = {str(p): p.read_bytes() for p in Path(self.temp.name).rglob("*") if p.is_file()}
        self.assertEqual(before, after)
        self.assertEqual(data["gaps"][0]["references"], {"op_id": "op_1"})


if __name__ == "__main__":
    unittest.main()
