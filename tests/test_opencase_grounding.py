"""Pure saved-record display fixtures: no provider, network, or NK store."""
import copy
import hashlib
import json
from pathlib import Path
import sys
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import opencase_grounding as grounding

PLAN = {"task_profile": "judicial_biography", "subject_type": "federal_judge_scotus", "question": "Did this judge serve alongside another justice?"}
ARTIFACT = {"name": "result.json", "sha256": "a" * 64}


def record(fid="finding-1", nid="1394151", jid="3464", observed=False):
    suffix = f"nid:{nid}:jid:{jid}"
    family = "fjc:judicial_biography:" + suffix
    typed = {"schema": "fjc.judicial_biography.observed.v1" if observed else "fjc.judicial_biography.v1",
        "upstream_record": {"nid": nid, "jid": jid}, "appointments": [
            {"court_name": "Supreme Court of the United States", "court_type": "Supreme Court",
             "appointment_title": "Associate Justice", "commission_date": "04/08/2022", "oath_date": None,
             "termination_date": None, "appointing_president": "Joseph R. Biden"},
            {"court_name": "U.S. District Court for the District of Columbia", "court_type": "District Court",
             "appointment_title": "Judge", "commission_date": "03/26/2013", "oath_date": None,
             "termination_date": "06/17/2021"},
            {"court_name": "U.S. Court of Appeals for the District of Columbia Circuit", "court_type": "Court of Appeals",
             "appointment_title": "Judge", "commission_date": "06/17/2021", "oath_date": None,
             "termination_date": "06/29/2022"}]}
    if observed:
        typed["historical_capture"] = {"coverage": "rendered_fields_only", "unobserved_upstream_fields": "unknown"}
    return {"id": fid, "body": "Law clerk for Justice Stephen G. Breyer, 1999–2000. This prose is not an appointment field.",
        "source_name": "FJC", "source_url": "https://www.fjc.gov/sites/default/files/history/judges.csv",
        "source_hash": "producer-rendered-body-hash", "evidence_kind": "official_primary_record", "semantic_record": typed,
        "source_identity": {"status": "resolved", "namespace": "fjc", "upstream_record_id": suffix,
            "subject_id": "fjc:judge:" + suffix, "record_identity": family, "provenance_family_id": family,
            "substantive_revision_sha256": None if observed else "b" * 64},
        "lineage": {"identity_status": "resolved", "provenance_family_id": family,
            "substantive_revision_id": None if observed else "b" * 64},
        "correction": {"correction_id": "correction-fixture", "payload_sha256": "c" * 64} if observed else None}


def build(records=None, plan=None):
    return grounding.build_record_chronology(plan or PLAN, [record()] if records is None else records,
        operation_id="op_fixture", result_artifact=ARTIFACT)


class GroundingTests(unittest.TestCase):
    def test_verbatim_cited_chronology_has_three_recorded_appointments(self):
        result = build()
        self.assertEqual(result["readiness"], "record_facts_available")
        self.assertEqual(result["status"], "available")
        self.assertEqual(len(result["appointments"]), 3)
        commissions = [next(r for r in a["rows"] if r["label"] == "Commission date") for a in result["appointments"]]
        self.assertEqual([r["value"] for r in commissions], ["03/26/2013", "06/17/2021", "04/08/2022"])
        self.assertEqual([a["source_index"] for a in result["appointments"]], [1, 2, 0])
        for row in commissions:
            self.assertEqual(row["value"], row["display_value"])
            self.assertEqual(row["source_ref"]["record_id"], "op_fixture:finding-1")
            self.assertEqual(row["source_ref"]["result_artifact"], ARTIFACT)
            self.assertTrue(row["field_path"].endswith("/commission_date"))

    def test_question_prose_and_clerkship_never_become_appointment_facts(self):
        result = build()
        self.assertFalse(result["question_answered"])
        self.assertEqual(result["answer_adequacy"], "not_assessed")
        self.assertNotIn("Breyer", result["text"])
        self.assertNotIn("1999", result["text"])
        self.assertNotIn(PLAN["question"], result["text"])
        self.assertIn("do not by themselves establish who was replaced", result["text"])

    def test_missing_termination_is_not_current_service_and_commission_is_not_oath(self):
        result = build()
        final = result["appointments"][-1]
        fields = {r["label"]: r for r in final["rows"]}
        self.assertEqual(fields["Oath date"]["display_value"], grounding.MISSING)
        self.assertEqual(fields["Termination date"]["display_value"], grounding.MISSING)
        self.assertIsNone(fields["Oath date"]["value"])
        self.assertIn("does not establish present service", result["text"])
        self.assertIn("does not establish an oath date or the date service began", result["text"])
        self.assertNotIn("–present", result["text"])

    def test_observed_history_preserves_unknown_revision_and_correction(self):
        result = build([record(observed=True)])
        row = result["records"][0]
        self.assertEqual(row["historical_coverage"], "rendered_fields_only")
        self.assertEqual(row["complete_historical_revision"], "unknown")
        self.assertIsNone(row["source_ref"]["source_identity"]["substantive_revision_sha256"])
        self.assertEqual(row["source_ref"]["correction"]["correction_id"], "correction-fixture")
        self.assertIn("complete historical row and revision remain unknown", result["text"])

    def test_same_family_captures_stay_separate_and_different_ids_never_merge(self):
        result = build([record(), record("finding-2", observed=True), record("finding-3", nid="999", jid="888")])
        self.assertEqual(len(result["records"]), 3)
        self.assertEqual(result["source_family_count"], 2)
        self.assertEqual(len({c["record_id"] for c in result["citations"]}), 3)
        self.assertIn("do not establish independent corroboration", result["text"])

    def test_unsupported_profile_and_record_schema_cannot_claim_readiness(self):
        result = build(plan={**PLAN, "task_profile": "public_records"})
        self.assertEqual(result["status"], "unsupported")
        self.assertFalse(result["appointments"])
        f = record(); f["semantic_record"]["schema"] = "other.appointments.v1"
        result = build([f])
        self.assertEqual(result["status"], "unavailable")
        self.assertFalse(result["appointments"])

    def test_mismatched_or_unresolved_identities_are_excluded(self):
        for mutation in ("typed_id", "unresolved", "nonprimary", "notice", "missing_id"):
            with self.subTest(mutation=mutation):
                f = record()
                if mutation == "typed_id": f["semantic_record"]["upstream_record"]["nid"] = "999"
                if mutation == "unresolved": f["source_identity"]["status"] = "unresolved"
                if mutation == "nonprimary": f["evidence_kind"] = "allegation"
                if mutation == "notice": f["is_absence"] = True
                if mutation == "missing_id": f["id"] = None
                result = build([f])
                self.assertFalse(result["appointments"])
                self.assertEqual(len(result["excluded_records"]), 1)

    def test_malformed_fields_and_false_full_historical_revision_are_excluded(self):
        for mutation in ("fields", "historical_shape", "historical_revision"):
            with self.subTest(mutation=mutation):
                f = record(observed=True)
                if mutation == "fields": f["semantic_record"]["appointments"][0]["commission_date"] = {"bad": "shape"}
                if mutation == "historical_shape": f["semantic_record"]["historical_capture"] = []
                if mutation == "historical_revision": f["source_identity"]["substantive_revision_sha256"] = "fake-full-revision"
                self.assertFalse(build([f])["appointments"])

    def test_invalid_date_is_preserved_and_never_ordered_as_a_valid_date(self):
        f = record(); f["semantic_record"]["appointments"][0]["commission_date"] = "02/30/2022"
        result = build([f])
        row = next(r for r in result["appointments"][-1]["rows"] if r["label"] == "Commission date")
        self.assertEqual(row["value"], "02/30/2022")
        self.assertEqual(row["date_validity"], "invalid_or_unsupported")
        self.assertIn("no date relationship is inferred", result["text"])

    def test_hash_kinds_determinism_and_input_immutability(self):
        f = record(observed=True); before = copy.deepcopy(f)
        one, two = build([f]), build([f])
        self.assertEqual(one, two); self.assertEqual(f, before)
        ref = one["citations"][0]
        self.assertEqual(ref["body_sha256"], hashlib.sha256(f["body"].encode()).hexdigest())
        self.assertNotEqual(ref["derived_finding_sha256"], ARTIFACT["sha256"])
        self.assertIn("not original transport bytes", ref["derived_hash_basis"])
        self.assertEqual(ref["result_artifact_url"], "/api/open-case/operations/op_fixture/artifacts/result.json")
        self.assertEqual((one["network_requests"], one["model_requests"], one["writes"]), (0, 0, 0))
        self.assertEqual(build([])["status"], "unavailable")


if __name__ == "__main__":
    unittest.main()
