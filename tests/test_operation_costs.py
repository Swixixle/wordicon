"""Offline accounting tests. No network, provider, or owner store is used."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
import json
import os
from pathlib import Path
import sys
import tempfile
import unittest

ROOT = Path(__file__).resolve().parents[1]
sys.path[:0] = [str(ROOT), str(ROOT / "scripts")]
os.environ["WORDICON_TEST_MODE"] = "1"
import wordicon_cli as cli
import operations as ops
import operation_costs as costs
import producers


class CostTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="nk-cost-", dir=Path(tempfile.gettempdir()).resolve())
        self.before_root = cli.LOCAL_STATE
        cli.LOCAL_STATE = Path(self.temp.name)
        self.op = self.new_op("first")

    def tearDown(self):
        cli.LOCAL_STATE = self.before_root
        self.temp.cleanup()

    def new_op(self, key, parent=""):
        op, _ = ops.reserve(request_key=key, kind="investigation", action_id="investigate.opencase.question",
            execution={"plan": {"synthesis": {"enabled": True, "provider": "anthropic", "model": "claude-sonnet-5", "tools": False}, "follow_up_of": parent}})
        return op

    def receipt(self, input_count=7646, output_count=2048, **usage):
        raw_usage = {"input_tokens": input_count, "output_tokens": output_count,
                     "cache_read_input_tokens": 0, "cache_creation_input_tokens": 0, **usage}
        return {"provider": "anthropic", "model": "claude-sonnet-5", "response": {
            "response_id": "message-one", "stop_reason": "max_tokens", "usage_complete": True,
            "usage": raw_usage, "response": {"id": "message-one", "model": "claude-sonnet-5", "usage": raw_usage}}}

    def source_and_receipt(self, op, receipt=None):
        kept = producers.keep_artifact(op["op_id"], "result.json", json.dumps({"model_runs": [], "actual_cost_usd": 0}).encode())
        refs = {"result_artifact": kept, "kept": [kept]}
        if receipt:
            refs["kept"].append(producers.keep_artifact(op["op_id"], "synthesis-receipt.json", json.dumps(receipt).encode()))
        ops.mark(op["op_id"], result_ref=refs)
        return ops.get(op["op_id"])

    def test_verified_rates_exclude_other_models_and_proposal_bound(self):
        self.assertIsNone(costs.rate_card("anthropic", "claude-sonnet-5-5"))
        self.assertIsNone(costs.rate_card("unknown", "claude-sonnet-5"))
        self.assertEqual(costs.rate_card("anthropic", "claude-sonnet-5-20261001")["checked_at"], "2026-10-18")
        proposal = costs.proposal_estimate("anthropic", "claude-sonnet-5", max_output_tokens=8192)
        self.assertLess(proposal["max_estimated_cost_usd"], .50)
        self.assertIsNone(proposal["actual_cost_usd"])

    def test_free_collection_plus_truncated_model_is_estimate_not_zero(self):
        op = self.source_and_receipt(self.op)
        reservation = costs.reserve(op["op_id"], "synthesis", "synthesis:1", "question", 4096)
        self.assertGreater(reservation["reserved_usd"], 0)
        costs.settle(op["op_id"], "synthesis", "synthesis:1", self.receipt())
        got = costs.total(ops.get(op["op_id"]))
        self.assertEqual(got["accounting_status"], "estimated")
        self.assertEqual(got["estimated_cost_usd"], .035772)
        self.assertIsNone(got["actual_cost_usd"])
        self.assertEqual({x["component"] for x in got["components"]}, {"collection", "synthesis"})
        saved = costs._events(op["op_id"])[-1]
        self.assertEqual(saved["usage"][0]["count"], 7646)  # Not redacted by the operations secret scrubber.
        self.assertEqual(saved["stop_reason"], "max_tokens")

    def test_unknown_price_and_usage_keep_known_subtotal(self):
        with self.assertRaises(costs.CostError):
            costs.reserve(self.op["op_id"], "synthesis", "a", "question", 4096, model="unknown-model")
        receipt = self.receipt(cache_creation_input_tokens=100)
        row = costs.settle(self.op["op_id"], "synthesis", "a", receipt)
        self.assertEqual(row["accounting_status"], "unknown")
        self.assertIsNone(row["estimated_cost_usd"])
        self.assertEqual(row["known_estimated_subtotal_usd"], .035772)
        self.assertTrue(any("duration" in x for x in row["unknown_reasons"]))
        unknown = self.receipt(); unknown["model"] = "unknown-model"; unknown["response"]["response"]["model"] = "unknown-model"
        other = self.new_op("unknown")
        row = costs.settle(other["op_id"], "synthesis", "a", unknown)
        self.assertIsNone(row["rate_card"])
        self.assertIsNone(row["estimated_cost_usd"])

    def test_cache_duration_categories_and_server_tools(self):
        receipt = self.receipt(100, 200, cache_read_input_tokens=1000, cache_creation_input_tokens=300,
                              cache_creation={"ephemeral_5m_input_tokens": 100, "ephemeral_1h_input_tokens": 200})
        row = costs.settle(self.op["op_id"], "synthesis", "a", receipt)
        self.assertEqual(row["estimated_cost_usd"], .00345)
        self.assertEqual(len(row["usage"]), 5)
        receipt["response"]["response"]["usage"]["server_tool_use"] = {"web_search_requests": 1}
        row = costs.settle(self.op["op_id"], "synthesis", "a", receipt)
        self.assertIsNone(row["estimated_cost_usd"])
        self.assertEqual(row["known_estimated_subtotal_usd"], .00345)

    def test_reservation_is_atomic_idempotent_and_checks_remaining(self):
        with ThreadPoolExecutor(max_workers=2) as pool:
            rows = list(pool.map(lambda _: costs.reserve(self.op["op_id"], "synthesis", "a", "text", 4096), range(2)))
        self.assertEqual(rows[0], rows[1])
        self.assertEqual(len(costs._events(self.op["op_id"])), 1)
        with self.assertRaises(costs.CostError):
            costs.reserve(self.op["op_id"], "synthesis", "a", "changed", 4096)
        with self.assertRaises(costs.CostError):
            costs.reserve(self.op["op_id"], "synthesis", "b", "text", 8192, allowance_usd=.10)
        with self.assertRaises(costs.CostError):
            costs.reserve(self.op["op_id"], "synthesis", "b", "text", 4096, allowance_usd=True)

    def test_legacy_reopen_is_read_only_reconciliation_append_only(self):
        op = self.source_and_receipt(self.op, self.receipt())
        db = ops.db_path()
        before = db.read_bytes()
        raw_before = {r["name"]: producers.artifact_bytes(op["op_id"], r["name"]) for r in op["result_ref"]["kept"]}
        got = costs.total(op)
        self.assertTrue(got["provisional"])
        self.assertEqual(got["estimated_cost_usd"], .035772)
        self.assertEqual(db.read_bytes(), before)
        costs.reconcile(op)
        count = len(costs._events(op["op_id"]))
        costs.reconcile(op)
        self.assertEqual(len(costs._events(op["op_id"])), count)
        self.assertFalse(costs.total(op)["provisional"])
        self.assertEqual(costs.ledger_summary()["estimated_cost_usd"], .035772)
        for name, raw in raw_before.items():
            self.assertEqual(producers.artifact_bytes(op["op_id"], name), raw)

    def test_lost_response_keeps_reservation_and_unknown_never_zero(self):
        op = self.source_and_receipt(self.op)
        costs.reserve(op["op_id"], "synthesis", "a", "text", 4096)
        costs.settle(op["op_id"], "synthesis", "a", {"provider": "anthropic", "model": "claude-sonnet-5", "error": "lost response"})
        got = costs.total(op)
        self.assertIsNone(got["estimated_cost_usd"])
        self.assertIsNone(got["actual_cost_usd"])
        self.assertGreater(got["reserved_usd"], 0)
        other = self.source_and_receipt(self.new_op("legacy-lost"))
        ops.event(other["op_id"], "stage_intent", stage="open_case.synthesis")
        self.assertIsNone(costs.total(other)["estimated_cost_usd"])

    def test_pending_child_does_not_disappear_from_thread_total(self):
        first = self.source_and_receipt(self.op, self.receipt())
        pending = self.new_op('pending-child', first['op_id'])
        got = costs.total(pending, ancestry=True)
        self.assertIsNone(got['estimated_cost_usd'])
        self.assertEqual(got['known_estimated_subtotal_usd'], .035772)
        self.assertEqual(got['unaccounted_operation_ids'], [pending['op_id']])

    def test_failed_then_successful_followup_ancestry_and_duplicate_import(self):
        first = self.source_and_receipt(self.op, self.receipt())
        second = self.new_op("second", first["op_id"])
        receipt = self.receipt(8485, 928)
        receipt["response"]["response_id"] = "message-two"
        receipt["response"]["response"]["id"] = "message-two"
        second = self.source_and_receipt(second, receipt)
        self.assertEqual(costs.total(second)["estimated_cost_usd"], .02625)
        self.assertEqual(costs.total(second, ancestry=True)["estimated_cost_usd"], .062022)
        duplicate = self.source_and_receipt(self.new_op("duplicate"), receipt)
        self.assertEqual(costs.ledger_summary()["estimated_cost_usd"], .062022)
        costs.reconcile(second); costs.reconcile(duplicate)
        self.assertEqual(costs.ledger_summary()["estimated_cost_usd"], .062022)


if __name__ == "__main__":
    unittest.main()
