"""Offline projection/continuation regression tests. No NK store is opened."""
import copy
import hashlib
import json
from pathlib import Path
import sys
from types import SimpleNamespace
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import receipts_projection as p


def finding(fid="f1", *, subject="fjc:judge:nid:1:jid:2", family="fjc:record:1", revision="revision-one", day="01/02/2003", body="A biography."):
    return {"id": fid, "title": "Judge Same Name", "body": body, "source_url": "https://example.test/shared",
        "source_name": "FJC", "evidence_kind": "official_primary_record", "source_identity": {"subject_id": subject},
        "lineage": {"source_record_id": family, "identity_status": "resolved", "provenance_family_id": family,
                    "substantive_revision_id": revision, "substantive_revision_status": "identified" if revision else "unknown"},
        "semantic_record": {"schema":"fjc.judicial_biography.v1", "appointments": [{"court_name": "Court One", "court_type": "district", "seat_id": "seat-1",
            "appointment_title": "Judge", "commission_date": day, "oath_date": None}]}}


def bundle(op_id="op_a", records=None, *, corrections=None, **result_fields):
    records = records if records is not None else [finding()]
    result = {"findings": records, **result_fields}
    raw = json.dumps(result).encode()
    return {"operation_id": op_id, "plan": {"question": "When was the commission issued?", "subject_name": "Fixture Judge", "origin": {"kind": "selection", "text": "Original private passage", "doc_id": "doc-1", "revision": 3}},
        "raw_result": raw, "result_artifact": {"name": "result.json", "sha256": hashlib.sha256(raw).hexdigest()},
        "findings": copy.deepcopy(records), "corrections": corrections or [], "synthesis": {}}


class ProjectionTests(unittest.TestCase):
    def test_same_url_keeps_captures_revisions_and_source_families(self):
        one = bundle(); two = bundle("op_b", [finding(body="Different rendering.")])
        three = bundle("op_c", [finding(day="01/03/2003", revision="revision-two")])
        result = p.build_projection([one, two, three])
        self.assertEqual(len(result["evidence_matrix"]), 3)
        comparison = result["comparisons"][0]
        self.assertEqual(comparison["type"], "same_source_variation")
        self.assertEqual(len(comparison["source_families"]), 1)
        self.assertEqual(len(comparison["substantive_revisions"]), 2)
        self.assertEqual(comparison["independence"], "not_assessed")

    def test_same_name_is_not_same_subject_and_unknown_identity_not_guessed(self):
        result = p.build_projection([bundle(records=[finding(), finding("f2", subject="different-subject", family="other", day="01/04/2003")])])
        self.assertFalse(result["comparisons"])
        f = finding("f3", subject=None, family=None)
        result = p.build_projection([bundle(records=[finding(), f])])
        self.assertFalse(result["comparisons"])

    def test_two_families_only_generate_candidate_not_proof(self):
        result = p.build_projection([bundle(), bundle("op_b", [finding(family="court:appointment:1", day="01/03/2003")])])
        c = result["comparisons"][0]
        self.assertEqual(c["type"], "candidate_conflict")
        self.assertEqual(c["semantic_contradiction"], "not_established")

    def test_unknown_historical_revision_never_invented(self):
        f = finding(revision=None)
        f["semantic_record"]["historical_capture"] = {"coverage": "rendered_fields_only"}
        result = p.build_projection([bundle(records=[f])])
        self.assertIsNone(result["evidence_matrix"][0]["lineage"]["substantive_revision_id"])
        self.assertEqual(result["timeline"][0]["historical_coverage"], "rendered_fields_only")

    def test_commission_is_not_oath_or_source_capture_date(self):
        result = p.build_projection([bundle(records=[finding(body="Captured October 18, 2026. Commission (oath) date: 01/02/2003.")])])
        self.assertEqual([(e["type"],e["date"]) for e in result["timeline"]], [("commission","2003-01-02")])
        self.assertTrue(any(g["state"] == "not_supplied" for g in result["missing_evidence"]))

    def test_invalid_typed_dates_and_prose_mentions_are_not_promoted(self):
        f=finding(day="02/30/2003")
        other={"id":"note", "body":"A newspaper dated 2004-05-06 mentions an event.", "title":"News"}
        result=p.build_projection([bundle(records=[f,other])])
        self.assertIsNone(result["timeline"][0]["date"])
        self.assertEqual(result["timeline"][0]["status"],"needs_date_review")
        self.assertEqual(result["unplaced_records"][0]["state"],"untyped_date_mention")
        self.assertEqual(len(result["timeline"]),1)

    def test_unsupported_typed_schema_is_not_interpreted_as_fjc(self):
        f=finding();f["semantic_record"]["schema"]="unsupported.future-schema"
        result=p.build_projection([bundle(records=[f])])
        self.assertFalse(result["timeline"])
        self.assertEqual(result["unplaced_records"][0]["state"],"no_typed_event_date")

    def test_repeated_appointments_require_event_identity(self):
        f=finding();f["semantic_record"]["appointments"].append({**f["semantic_record"]["appointments"][0],"commission_date":"01/03/2003"})
        result=p.build_projection([bundle(records=[f])])
        self.assertEqual(result["comparisons"][0]["type"],"ambiguous_event_match")

    def test_reference_mentions_are_unresolved_not_concealment(self):
        f=finding(body="See Exhibit A and the search warrant return. No bodycam footage exists. Maybe a witness statement was requested.")
        result=p.build_projection([bundle(records=[f])])
        refs=[g for g in result["missing_evidence"] if g["kind"]=="referenced_material"]
        self.assertTrue(any(g["mention"]=="Exhibit A" for g in refs))
        self.assertFalse(any("bodycam" in g["mention"].lower() or "witness" in g["mention"].lower() for g in refs))
        for g in refs:
            self.assertEqual(g["state"],"linkage_unresolved")
            r=g["body_range"];self.assertEqual(f["body"][r["start"]:r["end"]],g["mention"])

    def test_coverage_distinguishes_setup_retry_inapplicable_and_unimplemented(self):
        b=bundle(source_statuses={"courtlistener":{"status":"credential_failure","detail":"API key missing"},
            "remote":{"status":"timeout"},"fec":{"status":"inapplicable"},"other":{"status":"unimplemented"}})
        result=p.build_projection([b]);states={r["source"]:r["state"] for r in result["coverage"]}
        self.assertEqual(states,{"courtlistener":"setup_required","remote":"transient_failure","fec":"not_applicable","other":"not_implemented"})
        self.assertFalse(any(c["title"] in ("Coverage from fec","Coverage from other") for c in result["continuations"]))
        self.assertTrue(all(not c["auto_retry"] for c in result["continuations"]))

    def test_held_answer_not_counted_as_used(self):
        b=bundle();b["synthesis"]={"status":"truncated","citations":[{"record_id":"op_a:f1"}]}
        self.assertFalse(p.build_projection([b])["evidence_matrix"][0]["used_in_answer"])
        b["synthesis"]["status"]="complete"
        self.assertTrue(p.build_projection([b])["evidence_matrix"][0]["used_in_answer"])

    def test_selected_answer_can_cite_ancestor_without_inheriting_old_answer_usage(self):
        current=bundle();parent=bundle("op_parent")
        current["synthesis"]={"status":"complete","citations":[{"record_id":"op_parent:f1"}]}
        parent["synthesis"]={"status":"complete","citations":[{"record_id":"op_a:f1"}]}
        rows=p.build_projection([current,parent])["evidence_matrix"]
        self.assertFalse(rows[0]["used_in_answer"]);self.assertTrue(rows[1]["used_in_answer"])
        self.assertEqual(rows[1]["support_for_question"],"not_assessed")

    def test_real_producer_cached_and_planned_capabilities(self):
        b=bundle(source_statuses=[{"adapter":"fjc_biographical","status":"cached"},{"adapter":"stub","status":"planned_stub","detail":"adapter planned, not yet implemented"}],
            dimensions={"acquisition":{"capabilities":[{"id":"fjc_biographical","name":"FJC","role":"required","status":"cached","ready":True},
                {"id":"stub","name":"Stub","role":"unimplemented","status":"planned_stub"}]}})
        result=p.build_projection([b]);self.assertEqual([r["state"] for r in result["coverage"]],["available","not_implemented","available","not_implemented"])
        self.assertFalse(any(c["title"].startswith("Coverage from") for c in result["continuations"]))

    def test_actual_source_checks_keep_name_success_and_empty_distinct(self):
        checks = [{"id":"check-1", "source_name":"FJC", "query_string":"fixture judge", "result_count":1,
            "result_hash":"fixture_cached", "checked_at":"2026-10-18T12:00:00Z", "checked_by":"fjc_biographical", "status":"searched_with_evidence"},
            {"id":"check-2", "source_name":"FEC", "status":"searched_empty", "result_count":0}]
        result = p.build_projection([bundle(source_checks=checks)])
        self.assertEqual([(r["source"], r["state"]) for r in result["coverage"]], [("FJC","available"),("FEC","empty_result")])
        self.assertFalse(any(c["title"] == "Coverage from FJC" or c["title"] == "Coverage from 0" for c in result["continuations"]))
        self.assertEqual(result["coverage"][0]["original"], checks[0])

    def test_repeated_typed_gaps_group_targets_but_keep_each_capture(self):
        result = p.build_projection([bundle(), bundle("op_b"), bundle("op_c")])
        self.assertEqual(len(result["evidence_matrix"]), 3)
        self.assertEqual(len(result["missing_evidence"]), 3)
        self.assertEqual(len(result["continuations"]), 1)
        target = result["continuations"][0]
        self.assertEqual(len(target["source_refs"]), 3)
        self.assertEqual(len(target["gap_ids"]), 3)
        self.assertEqual(target["group_basis"], "resolved_family_and_typed_field")

    def test_gap_targets_never_group_by_name_or_url(self):
        result = p.build_projection([bundle(records=[finding(), finding("different-person", subject="fjc:other"),
            finding("different-family", family="court:other"), finding("unknown", family=None)])])
        self.assertEqual(len(result["continuations"]), 4)
        self.assertTrue(all(len(c["source_refs"]) == 1 for c in result["continuations"]))

    def test_ancestor_coverage_kept_but_only_selected_coverage_suggested(self):
        checks = {"courtlistener":{"status":"credential_failure", "detail":"API key missing"}}
        result = p.build_projection([bundle(source_statuses=checks), bundle("op_parent", source_statuses=checks)])
        self.assertEqual(len(result["coverage"]), 2)
        suggestions = [c for c in result["continuations"] if c["title"].startswith("Coverage from")]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["source_refs"][0]["operation_id"], "op_a")

    def test_supplied_field_elsewhere_retains_old_gap_without_collection_suggestion(self):
        newer = finding(revision="newer")
        newer["semantic_record"]["appointments"][0]["oath_date"] = "01/03/2003"
        result = p.build_projection([bundle(records=[newer]), bundle("op_older")])
        self.assertEqual(len(result["evidence_matrix"]), 2)
        self.assertEqual(len(result["missing_evidence"]), 1)
        self.assertEqual(result["missing_evidence"][0]["related_supplied_fields"][0]["record_id"], "op_a:f1")
        self.assertFalse(result["continuations"])
        self.assertEqual(result["missing_evidence"][0]["state"], "not_supplied")

    def test_projection_deterministic_does_not_mutate_inputs_and_traces_every_row(self):
        b=bundle();before=copy.deepcopy(b)
        first=p.build_projection([b]);second=p.build_projection([b])
        self.assertEqual(b,before);self.assertEqual(first,second)
        self.assertEqual(first["network_requests"],0);self.assertEqual(first["writes"],0)
        r=first["evidence_matrix"][0]
        self.assertEqual(r["result_artifact"]["sha256"],hashlib.sha256(b["raw_result"]).hexdigest())
        self.assertEqual(r["body_sha256"],hashlib.sha256(r["excerpt"].encode()).hexdigest())
        self.assertEqual(first["continuations"][0]["follow_up_of"],"op_a")
        self.assertNotIn("Original private passage",json.dumps(first))

    def test_tamper_duplicate_ids_or_changed_membership_fail_closed(self):
        b=bundle();b["raw_result"]+=b" "
        with self.assertRaises(p.ProjectionError):p.build_projection([b])
        b=bundle(records=[finding(),finding()])
        with self.assertRaises(p.ProjectionError):p.build_projection([b])
        b=bundle();b["findings"][0]["id"]="changed"
        with self.assertRaises(p.ProjectionError):p.build_projection([b])

    def test_identical_deflate_imports_remain_derived_captures(self):
        f={"id":"d1","title":"Reading","body":"A reading of Exhibit A", "evidence_kind":"derived_interpretation",
           "lineage":{"provenance_family_id":"deflate:reading:1","content_duplicate_group":"transcript-sha256:abc","independence":"derived_interpretation"}}
        result=p.build_projection([bundle(records=[f]),bundle("op_b",[f])])
        self.assertEqual(len(result["evidence_matrix"]),2)
        self.assertFalse(result["comparisons"]);self.assertFalse(result["missing_evidence"])

    def test_saved_boundary_and_continuation_rebuild_are_read_only(self):
        b=bundle();stored={"op_id":"op_a","execution":{"plan":b["plan"]},"result_ref":{"result_artifact":b["result_artifact"]}}
        class WorkflowError(Exception):
            def __init__(self,message,status=400):super().__init__(message);self.status=status
        case=SimpleNamespace(WorkflowError=WorkflowError,is_ours=lambda op:bool(op),
            artifact=lambda op,name:b["raw_result"],findings_for=lambda op,r:b["findings"],synthesis=SimpleNamespace(view=lambda op:{}))
        with patch.dict(sys.modules,{"opencase":case,"operations":SimpleNamespace(get=lambda oid:None)}):
            first=p.from_operation(stored);second=p.from_operation(copy.deepcopy(stored))
            self.assertEqual(first,second)
            request={"operation_id":"op_a","id":first["continuations"][0]["id"],"projection_sha256":first["projection_sha256"]}
            frozen=p.freeze_continuation(stored,request)
            self.assertEqual(frozen["source_refs"][0]["result_artifact"],b["result_artifact"])
            with self.assertRaises(WorkflowError):p.freeze_continuation(stored,{**request,"projection_sha256":"stale"})


if __name__ == "__main__":
    unittest.main()
