"""One signed producer-shaped record through the actual saved-view boundary."""
import base64
import copy
import hashlib
import json
import unittest
from unittest.mock import patch

from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PrivateKey
from cryptography.hazmat.primitives import serialization

from test_opencase_grounding import record
import test_opencase_synthesis as synthesis_fixtures
from test_opencase_workflow import ROOT, federation, opencase, ops, producers


class GroundedSavedViewTests(unittest.TestCase):
    def setUp(self):
        # Reuse the actual authenticated scratch-store and fake-provider harness
        # without inheriting and rerunning its entire test population.
        self.workflow = synthesis_fixtures.SynthesisTests("test_opt_in_and_exact_receipts")
        self.workflow.setUp()

    def tearDown(self):
        self.workflow.tearDown()

    def test_signed_fields_still_show_after_answer_hold_without_replacing_original(self):
        w = self.workflow
        key = Ed25519PrivateKey.generate()
        public = key.public_key().public_bytes(serialization.Encoding.Raw, serialization.PublicFormat.Raw)
        federation.pin_key("case-test", base64.b64encode(public).decode(), label="ephemeral fixture authority")
        package = json.loads((ROOT / "tests/fixtures/federation/open_case.exemplar.deposition.json").read_text())
        w.case_id = package["object"]["id"]
        sealed = package["payload"]["evidence"][0]
        public_record = record(str(sealed["id"]))
        metadata = {key: public_record[key] for key in ("evidence_kind", "semantic_record", "source_identity")}
        metadata.update(evidence_label="Official primary record", semantics_version="open_case.evidence_semantics.v1",
                        kind_note="Record kind describes provenance, not the truth of every claim.")
        sealed.update(title="FJC record fixture", body=public_record["body"], source_name="FJC",
                      source_url=public_record["source_url"], entry_type="court_record", is_absence=False,
                      epistemic_level="REPORTED", classification_basis="official_biographical_record",
                      source_type="agency_record", producer_semantics=metadata)
        digest = federation.payload_sha256(package["payload"])
        package["payload_sha256"] = digest
        package["signature"].update(trusted_key_id="ed25519:sha256:" + hashlib.sha256(public).hexdigest(),
                                    value=base64.b64encode(key.sign(digest.encode())).decode())
        producer_fixture = w.fixture

        def source(*args, **kwargs):
            response = producer_fixture(*args, **kwargs)
            if args[2].endswith("/result"):
                result = response["json"]
                result.update(findings=[{**sealed, **metadata}], deposition=package,
                              deposition_json=json.dumps(package), dimensions={"acquisition": {"status": "ready", "required_ready": True}})
                response["raw"] = json.dumps(result).encode()
            return response

        with patch.object(w, "fixture", side_effect=source):
            operation = w.run_prepared(w.prepare_model(task_profile="judicial_biography", subject_type="federal_judge_scotus"))
        self.assertTrue(operation["result_ref"]["custody"]["verification"]["ok"])
        reference_before = copy.deepcopy(operation["result_ref"])
        artifact_bytes = {item["name"]: opencase.artifact(operation, item["name"]) for item in reference_before["kept"]}
        response_sha = reference_before["synthesis"]["response_artifact"]["sha256"]
        held = w.client.post("/api/open-case/operations/" + operation["op_id"] + "/answer-review", json={
            "reason": "The cited clerkship does not establish a service overlap between the two justices.", "response_sha256": response_sha})
        self.assertEqual(held.status_code, 200, held.json)
        self.assertEqual(held.json["status"], "complete")  # attempt lifecycle remains finished
        self.assertEqual(held.json["dimensions"]["display_status"], "Answer held")
        self.assertFalse(held.json["dimensions"]["completed"])
        self.assertEqual(held.json["synthesis"]["held_answer"], reference_before["synthesis"]["answer"])
        chronology = held.json["record_chronology"]
        self.assertEqual(chronology["readiness"], "record_facts_available")
        self.assertFalse(chronology["question_answered"])
        self.assertEqual(len(chronology["appointments"]), 3)
        for appointment in chronology["appointments"]:
            original = metadata["semantic_record"]["appointments"][appointment["source_index"]]
            for row in appointment["rows"]:
                self.assertEqual(row["value"], original.get(row["field_path"].rsplit("/", 1)[-1]))
                self.assertEqual(row["source_ref"]["result_artifact"]["sha256"], hashlib.sha256(artifact_bytes["result.json"]).hexdigest())
        self.assertNotIn("Breyer", chronology["text"])
        with patch.object(producers, "_request", side_effect=AssertionError("reopen must remain local")):
            reopened = w.client.get("/api/open-case/operations/" + operation["op_id"])
        self.assertEqual(reopened.status_code, 200, reopened.json)
        self.assertEqual(reopened.json["record_chronology"], chronology)
        saved = ops.get(operation["op_id"])
        self.assertEqual(saved["result_ref"], reference_before)
        for name, original in artifact_bytes.items():
            self.assertEqual(opencase.artifact(saved, name), original)
        self.assertEqual(len(w.model.calls), 1)


if __name__ == "__main__":
    unittest.main()
