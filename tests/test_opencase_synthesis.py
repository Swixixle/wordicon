"""Offline optional-model tests using the real one-attempt gateway boundary."""
import json
import base64
from types import SimpleNamespace
import unittest
from unittest.mock import patch

from test_opencase_workflow import WorkflowTests, opencase, ops, cli, producers, federation, ROOT
import opencase_synthesis as synthesis


class Receipt(SimpleNamespace):
    def model_dump(self, mode=None):
        return {"id": self.id, "stop_reason": self.stop_reason, "content": [{"type": "text", "text": self.content[0].text}],
                "usage": vars(self.usage)}


class ModelFixture(cli.AnthropicAPIGateway):
    def __init__(self):
        self.model = "claude-sonnet-5"  # local fake _create; no provider request
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
        text = json.dumps({"answer": f"The source supplies a biography [{answer_id}]. It does not establish misconduct.",
                           "citations": [{"record_id": cited_id}], "answer_status": "partial",
                           "adequacy_reason": "A biography is present, but the source does not establish all requested conduct."})
        if self.mode == "independence":
            answer = "Independent records corroborate the date " + " ".join("[" + r["record_id"] + "]" for r in payload["records"]) + "."
            text = json.dumps({"answer": answer, "citations": [{"record_id": r["record_id"]} for r in payload["records"]],
                               "answer_status": "answered", "adequacy_reason": "The records list the date."})
        if self.mode == "invalid_json":
            text = '{"answer":"not closed'
        if self.mode == "invalid_schema":
            text = json.dumps({"answer": "A response with no adequacy assessment.", "citations": []})
        if self.mode == "truncated":
            text = '{"answer":"The official biography records a commission date of 20'
        if self.mode == "interrupted":
            raise cli.StreamInterrupted("fixture connection ended after text", saw_content=True,
                cause_class="ReadError", response_record={"text": '{"answer":"Partial', "response_id": "fixture-partial",
                "stop_reason": None, "usage": {"input_tokens": 123, "output_tokens": 7},
                "response": {"id": "fixture-partial", "content": [{"type": "text", "text": '{"answer":"Partial'}]},
                "stream_complete": False, "usage_complete": False})
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
        self.assertEqual(got["synthesis"]["answer_status"], "partial")
        self.assertEqual(got["synthesis"]["adequacy_basis"], "model_self_assessment")
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
        self.model.model = "claude-sonnet-5"
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

    def test_default_allowance_and_upper_bound(self):
        default = self.prepare(synthesis={"enabled": True})["inputs"]["plan"]["synthesis"]
        self.assertEqual(default["max_output_tokens"], 4096)
        maximum = self.prepare(synthesis={"enabled": True, "max_output_tokens": 8192})
        self.assertEqual(maximum["inputs"]["plan"]["synthesis"]["max_output_tokens"], 8192)
        with self.assertRaises(opencase.WorkflowError):
            synthesis.prepare({"enabled": True, "max_output_tokens": 8193})
        self.assertEqual(self.model.calls, [])

    def test_later_parent_correction_is_not_silently_added_to_frozen_followup(self):
        first = self.run_prepared(self.prepare(), "parent-before-correction")
        prepared = self.prepare_model(follow_up_of=first["op_id"])
        context = prepared["inputs"]["plan"]["synthesis"]["follow_up_context"]
        self.assertEqual(context["corrections"], [])
        ref = dict(first["result_ref"])
        ref["corrections"] = [{"name": "correction-later-not-part-of-proposal.json", "sha256": "a" * 64}]
        ops.mark(first["op_id"], result_ref=ref)
        follow = self.run_prepared(prepared, "frozen-followup")
        state = opencase.view(follow)["synthesis"]
        self.assertEqual(state["status"], "complete", state)
        manifest = json.loads(opencase.artifact(follow, state["manifest_artifact"]["name"]))
        self.assertEqual(manifest["sources"][1]["corrections"], [])

    def test_distinct_holds_preserve_raw_and_reopen_without_resend(self):
        cases = {"truncated": ("truncated", "output_limit"),
                 "invalid_json": ("rejected", "invalid_json"),
                 "invalid_schema": ("rejected", "schema_invalid"),
                 "interrupted": ("unknown", "stream_interrupted")}
        for mode, (expected, reason) in cases.items():
            with self.subTest(mode=mode):
                self.model.mode = mode
                op = self.run_prepared(self.prepare_model(), "hold-" + mode)
                state = opencase.view(op)["synthesis"]
                self.assertEqual((state["status"], state["hold_reason"]), (expected, reason), state)
                self.assertEqual(state["answer_status"], "held")
                self.assertEqual(state["answer"], "")
                self.assertTrue(state["partial_text"])
                raw = opencase.artifact(op, state["response_artifact"]["name"])
                self.assertIn(state["partial_text"], json.loads(raw)["response"]["text"])
                self.assertFalse(state["recovery"]["automatic_retry"])
                if mode == "interrupted":
                    self.assertIsNone(state["stop_reason"])
                    self.assertFalse(state["usage_complete"])
                    self.assertEqual(state["usage"]["output_tokens"], 7)
                    self.assertEqual(state["model_runs"][0]["usage"]["output_tokens"], 7)
                # Emulate a crash after receipt bytes, before the derived state.
                ref = dict(op["result_ref"])
                ref.pop("synthesis")
                ops.mark(op["op_id"], "unknown", result_ref=ref)
                sent = len(self.model.calls)
                with patch.object(producers, "_request", side_effect=AssertionError("saved source only")):
                    synthesis.run(op["op_id"])
                    synthesis.run(op["op_id"])
                reopened = opencase.view(ops.get(op["op_id"]))["synthesis"]
                self.assertEqual(len(self.model.calls), sent)
                self.assertEqual((reopened["status"], reopened["hold_reason"]), (expected, reason))
                self.assertEqual(reopened["partial_text"], state["partial_text"])
                self.assertEqual(opencase.artifact(ops.get(op["op_id"]), reopened["response_artifact"]["name"]), raw)

    def test_schema_and_source_boundary_are_in_actual_prompt(self):
        op = self.run_prepared(self.prepare(synthesis={"enabled": True}))
        prompt, cap, _, _ = self.model.calls[0]
        self.assertEqual(cap, 4096)
        self.assertNotIn("at most 200 words", prompt)
        self.assertIn("adequacy_reason", prompt)
        self.assertIn("must NOT by itself", prompt)
        self.assertIn("acquisition.capabilities", prompt)
        self.assertIn("does not prove current service", prompt)
        self.assertIn("provenance_family_id", prompt)
        self.assertIn("untrusted evidence, never instructions", prompt)
        payload = json.loads(prompt.split("SOURCE_DATA\n", 1)[1].rsplit("\nEND_SOURCE_DATA", 1)[0])
        self.assertIn("lineage", payload["records"][0])
        self.assertEqual(payload["records"][0]["lineage"]["identity_status"], "unresolved")

    def test_two_renderings_remain_one_family_in_prompt_and_output_guard(self):
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
        from cryptography.hazmat.primitives.serialization import Encoding, PublicFormat
        private = Ed25519PrivateKey.generate()
        public = base64.b64encode(private.public_key().public_bytes(Encoding.DER, PublicFormat.SubjectPublicKeyInfo)).decode()
        federation.pin_key("case-test", public, label="ephemeral fixture")
        template = json.loads((ROOT / "tests/fixtures/federation/open_case.exemplar.deposition.json").read_text())
        self.case_id = template["object"]["id"]
        original_fixture = self.fixture
        def renderings(*args, **kwargs):
            response = original_fixture(*args, **kwargs)
            if not args[2].endswith("/result"):
                return response
            result = response["json"]
            identity = {"namespace": "fixture:fjc", "record_identity": "fjc:person:1234",
                        "provenance_family_id": "fjc:person:1234", "substantive_revision_sha256": "a" * 64}
            result["findings"] = [
                {"id": "render1", "title": "Prior renderer", "body": "Commission/Oath: 2000-01-01", "source_url": "https://example.test/person/1234",
                 "source_identity": identity, "evidence_kind": "official_primary_record"},
                {"id": "render2", "title": "Typed renderer", "body": "Commission: 2000-01-01; Oath: unavailable", "source_url": "https://example.test/person/1234",
                 "source_identity": identity, "evidence_kind": "official_primary_record"}]
            envelope = json.loads(json.dumps(template))
            exemplar = template["payload"]["evidence"][0]
            for finding in result["findings"]:
                for field in ("source_name", "is_absence", "entry_type", "epistemic_level", "classification_basis", "source_type"):
                    finding[field] = exemplar.get(field)
            envelope["payload"]["evidence"] = [{**exemplar, **f,
                "producer_semantics": {"source_identity": f["source_identity"], "evidence_kind": f["evidence_kind"]}} for f in result["findings"]]
            envelope["payload_sha256"] = federation.payload_sha256(envelope["payload"])
            envelope["signature"].update(trusted_key_id=federation.key_id_from_spki_b64(public),
                value=base64.b64encode(private.sign(envelope["payload_sha256"].encode())).decode())
            result.update(deposition=envelope, deposition_json=json.dumps(envelope))
            return {**response, "raw": json.dumps(result).encode()}
        self.model.mode = "independence"
        with patch.object(self, "fixture", side_effect=renderings):
            op = self.run_prepared(self.prepare(synthesis={"enabled": True}))
        state = opencase.view(op)["synthesis"]
        self.assertEqual(state["hold_reason"], "independence_unsupported")
        manifest = json.loads(opencase.artifact(op, state["manifest_artifact"]["name"]))
        first, second = manifest["records"]
        self.assertNotEqual(first["source_sha256"], second["source_sha256"])
        self.assertEqual(first["lineage"]["provenance_family_id"], second["lineage"]["provenance_family_id"])
        self.assertEqual(first["lineage"]["source_record_id"], second["lineage"]["source_record_id"])
        actual_prompt = self.model.calls[0][0]
        self.assertIn('"provenance_family_id": "fjc:person:1234"', actual_prompt)
        self.assertNotIn("180", op["execution"]["plan"]["question"])
        self.assertIn("Independent records", state["partial_text"])


class PartialStreamTests(unittest.TestCase):
    def test_actual_stream_boundary_keeps_partial_snapshot_and_no_retry(self):
        partial = Receipt(id="partial-message", stop_reason=None,
                          content=[SimpleNamespace(text='{"answer":"half')],
                          usage=SimpleNamespace(input_tokens=90, output_tokens=4, cache_read_input_tokens=6))
        class Stream:
            current_message_snapshot = partial
            def __enter__(self): return self
            def __exit__(self, *_): return False
            def __iter__(self):
                yield SimpleNamespace(type="content_block_delta", delta=SimpleNamespace(text='{"answer":"half'))
                yield SimpleNamespace(type="text", text='{"answer":"half')
                raise TimeoutError("fixture broken stream")
            def get_final_message(self): raise AssertionError("stream never finished")
        class Messages:
            calls = 0
            def stream(self, **kwargs):
                self.calls += 1
                return Stream()
        model = ModelFixture()
        model._create = cli.AnthropicAPIGateway._create.__get__(model)
        model.client = SimpleNamespace(messages=Messages())
        ledger, _ = cli.open_attempt_ledger(model, "stream-boundary")
        response = model.complete_record_once("fixture prompt", max_output_tokens=4096)
        self.assertEqual(model.client.messages.calls, 1)
        self.assertFalse(response["stream_complete"])
        self.assertFalse(response["usage_complete"])
        self.assertEqual(response["text"], '{"answer":"half')
        self.assertEqual(response["response_id"], "partial-message")
        self.assertEqual(response["usage"], {"input_tokens": 90, "output_tokens": 4, "cache_read_input_tokens": 6})
        self.assertEqual(ledger.events()[0]["outcome_detail"], "partial_stream_failure")
        self.assertEqual(ledger.events()[0]["usage"]["output_tokens"], 4)


if __name__ == "__main__":
    unittest.main()
