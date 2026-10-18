"""Offline optional-model tests using the real one-attempt gateway boundary."""
import json
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_opencase_workflow import WorkflowTests, opencase, ops, cli, producers
import opencase_synthesis as synthesis


class Receipt(SimpleNamespace):
    def model_dump(self, mode=None):
        return {"id": self.id, "stop_reason": self.stop_reason, "content": [{"type": "text", "text": self.content[0].text}],
                "usage": vars(self.usage)}


class ModelFixture(cli.AnthropicAPIGateway):
    def __init__(self):
        self.model = "fixture-model"
        self.calls = []
        self.mode = "complete"
        self.MAX_OUTPUT_TOKENS = 24000

    def _retryable(self):
        return ((), (TimeoutError,))

    def _create(self, prompt, tools=None, *, allow_truncated=False):
        self.calls.append((prompt, self.MAX_OUTPUT_TOKENS, tools, allow_truncated))
        if self.mode == "lost":
            raise TimeoutError("fixture response lost after dispatch")
        payload = json.loads(prompt.split("SOURCE_DATA\n", 1)[1].rsplit("\nEND_SOURCE_DATA", 1)[0])
        rid = payload["records"][0]["record_id"]
        answer_id = "invented-record" if self.mode == "inline" else rid
        cited_id = "invented-record" if self.mode == "citation" else rid
        text = json.dumps({"answer": f"The source supplies a biography [{answer_id}]. It does not establish misconduct.", "citations": [{"record_id": cited_id}]})
        return Receipt(id="fixture-message", stop_reason="max_tokens" if self.mode == "truncated" else "end_turn",
                       content=[SimpleNamespace(text=text)], usage=SimpleNamespace(input_tokens=123, output_tokens=45))


class SynthesisTests(WorkflowTests):
    def setUp(self):
        super().setUp()
        self.model = ModelFixture()
        self.gateway_patch = patch.object(synthesis, "gateway", return_value=self.model)
        self.gateway_patch.start()

    def tearDown(self):
        self.gateway_patch.stop()
        super().tearDown()

    def prepare_model(self, **extra):
        return self.prepare(synthesis={"enabled": True, "max_requests": 1, "max_output_tokens": 2048, "max_input_chars": 40000}, **extra)

    def run_prepared(self, p, key="synthesis"):
        with patch.object(producers, "_request", side_effect=self.fixture):
            started = self.start(p, key)
        self.assertEqual(started.status_code, 200, started.json)
        return ops.get(started.json["operation_id"])

    def test_opt_in_and_exact_receipts(self):
        ordinary = self.run_prepared(self.prepare(), "plain")
        self.assertEqual(self.model.calls, [])
        self.assertEqual(opencase.view(ordinary)["synthesis"]["status"], "not_requested")
        p = self.prepare_model(origin={"kind": "description", "text": "PRIVATE_ORIGIN_STAYS_LOCAL"})
        self.assertEqual(self.model.calls, [])
        self.assertIsNone(p["inputs"]["plan"]["synthesis"]["actual_cost_usd"])
        op = self.run_prepared(p)
        got = opencase.view(op)
        self.assertEqual(got["status"], "complete", got)
        self.assertEqual(got["synthesis"]["status"], "complete", got["synthesis"])
        self.assertEqual(len(self.model.calls), 1)
        prompt, tokens, tools, truncated = self.model.calls[0]
        self.assertEqual(tokens, 2048)
        self.assertIsNone(tools)
        self.assertTrue(truncated)
        self.assertLessEqual(len(prompt), 40000)
        self.assertNotIn("PRIVATE_ORIGIN_STAYS_LOCAL", prompt)
        self.assertEqual(got["synthesis"]["usage"], {"input_tokens": 123, "output_tokens": 45})
        self.assertEqual(got["synthesis"]["model_runs"][0]["attempt"], 1)
        self.assertEqual(got["synthesis"]["model_runs"][0]["usage"]["output_tokens"], 45)
        self.assertEqual(got["result"]["model_runs"], [])
        self.assertEqual(got["result"]["actual_cost_usd"], 0)
        self.assertEqual(got["result"]["findings"][0]["id"], "e1")
        self.assertIsNone(got["synthesis"]["actual_cost_usd"])
        with patch.object(producers, "_request", side_effect=AssertionError("local reopen")):
            opencase._run(op["op_id"], resume=True)
        self.assertEqual(len(self.model.calls), 1)

    def test_ambiguous_request_never_replays_after_restart(self):
        self.model.mode = "lost"
        op = self.run_prepared(self.prepare_model())
        self.assertEqual(op["status"], "unknown")
        self.assertEqual(opencase.view(op)["synthesis"]["status"], "unknown")
        self.assertEqual(len(self.model.calls), 1)
        self.assertTrue(opencase.view(op)["result"]["findings"])
        # Reconcile twice, including a process that lost the final local state.
        ref = dict(op["result_ref"])
        ref.pop("synthesis")
        ops.mark(op["op_id"], "unknown", result_ref=ref)
        opencase._run(op["op_id"], resume=True)
        opencase._run(op["op_id"], resume=True)
        self.assertEqual(len(self.model.calls), 1)
        self.assertEqual(opencase.view(ops.get(op["op_id"]))["synthesis"]["status"], "unknown")

    def test_intent_without_receipt_never_dispatches(self):
        p = self.prepare_model()
        with patch.object(synthesis, "run"):
            op = self.run_prepared(p)
        for index in range(505):
            ops.event(op["op_id"], "note", detail={"source_poll": index})
        ops.event(op["op_id"], "stage_intent", stage=synthesis.STAGE, detail={"fixture": "crash after intent"})
        opencase._run(op["op_id"], resume=True)
        self.assertEqual(self.model.calls, [])
        self.assertEqual(ops.get(op["op_id"])["status"], "unknown")

    def test_preintent_restart_and_configuration_drift(self):
        p = self.prepare_model()
        with patch.object(synthesis, "run"):
            op = self.run_prepared(p)
        self.model.model = "changed-model"
        opencase._run(op["op_id"], resume=True)
        self.assertEqual(self.model.calls, [])
        self.assertEqual(opencase.view(ops.get(op["op_id"]))["synthesis"]["status"], "failed")
        self.model.model = "fixture-model"
        with patch.object(synthesis, "run"):
            pending = self.run_prepared(self.prepare_model(), "pending")
        opencase._run(pending["op_id"], resume=True)
        self.assertEqual(len(self.model.calls), 1)

    def test_citation_and_inline_mismatch_rejected_truncation_retained(self):
        for mode in ("citation", "inline", "truncated"):
            self.model.mode = mode
            op = self.run_prepared(self.prepare_model(), mode)
            view = opencase.view(op)
            self.assertEqual(view["status"], "complete")
            self.assertEqual(view["synthesis"]["status"], "truncated" if mode == "truncated" else "rejected")
            self.assertEqual(view["synthesis"]["answer"], "")
            self.assertEqual(view["synthesis"]["usage"]["output_tokens"], 45)
            self.assertTrue(view["result"]["findings"])
            response = json.loads(opencase.artifact(op, view["synthesis"]["response_artifact"]["name"]))
            self.assertTrue(response["response"]["text"])
        self.assertEqual(len(self.model.calls), 3)

    def test_followup_binds_previous_question_evidence_and_origin(self):
        first = self.run_prepared(self.prepare(origin={"kind": "description", "text": "original passage"}), "first")
        follow = self.run_prepared(self.prepare_model(follow_up_of=first["op_id"]), "follow")
        state = opencase.view(follow)["synthesis"]
        manifest = json.loads(opencase.artifact(follow, state["manifest_artifact"]["name"]))
        self.assertEqual(manifest["origin"]["text"], "original passage")
        self.assertEqual(manifest["previous_question"], first["execution"]["plan"]["question"])
        self.assertEqual(manifest["sources"][1]["result_artifact"]["sha256"], first["result_ref"]["result_artifact"]["sha256"])
        self.assertTrue(any(r["operation_id"] == first["op_id"] for r in manifest["records"]))
        # A copied biography in a follow-up is lineage, not a second witness.
        self.assertEqual(manifest["records"][1]["duplicate_of"], manifest["records"][0]["record_id"])
        self.assertEqual(manifest["records"][1]["content_sha256"], manifest["records"][0]["content_sha256"])


if __name__ == "__main__":
    unittest.main()
