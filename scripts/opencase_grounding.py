"""Deterministic FJC record display, not a generated answer to a question.

The caller supplies findings from opencase.findings_for after saved-artifact and
signed-correction checks. This pure module adds no facts from prose, the clock,
models, or external sources. Source field values remain verbatim. The supplied
artifact hash identifies original saved bytes; derived finding/body hashes are
separately named and never substituted for custody verification.
"""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import json
import re
from urllib.parse import quote

SCHEMA = "nikodemus.open_case.record_chronology.v1"
FJC_SCHEMAS = {"fjc.judicial_biography.v1", "fjc.judicial_biography.observed.v1"}
JUDICIAL_TYPES = {"federal_judge_district", "federal_judge_circuit", "federal_judge_scotus"}
FIELDS = (
    ("court_name", "Court"), ("court_type", "Court type"),
    ("appointment_title", "Appointment title"), ("seat_id", "Seat identifier"),
    ("appointing_president", "Appointing president"),
    ("nomination_date", "Nomination date"), ("confirmation_date", "Confirmation date"),
    ("commission_date", "Commission date"), ("recess_appointment_date", "Recess appointment date"),
    ("termination_date", "Termination date"), ("termination_reason", "Termination reason"),
    ("oath_date", "Oath date"),
)
MISSING = "Not provided in this captured record"
LIMITS = [
    "These are fields recorded by the FJC, not an automatically validated answer to the question.",
    "Commission and oath dates are distinct. A commission date does not establish an oath date or the date service began.",
    "A missing termination date does not establish present service, continuing tenure, or an open-ended service interval.",
    "The records do not by themselves establish who was replaced, a vacancy's timing, or whether two people served together.",
    "Captures from one source family remain one provenance family; additional captures do not establish independent corroboration.",
    "Appointments are ordered by valid recorded commission dates within each capture; missing or invalid dates remain unsorted at the end.",
]


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _date_key(value):
    """Validate known FJC date spellings for ordering only; never rewrite them."""
    if not isinstance(value, str):
        return None
    text = value.strip()
    try:
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", text):
            return date.fromisoformat(text).isoformat()
        match = re.fullmatch(r"(\d{1,2})/(\d{1,2})/(\d{4})", text)
        if match:
            month, day, year = map(int, match.groups())
            return date(year, month, day).isoformat()
    except ValueError:
        pass
    return None


def _supported(finding):
    if not isinstance(finding, dict) or finding.get("evidence_kind") != "official_primary_record" or finding.get("is_absence"):
        return "This finding is not a producer-classified primary record."
    typed = finding.get("semantic_record")
    identity = finding.get("source_identity")
    if not isinstance(typed, dict) or typed.get("schema") not in FJC_SCHEMAS:
        return "No supported full or observed FJC typed schema is available."
    if not isinstance(identity, dict) or identity.get("namespace") != "fjc" or identity.get("status") != "resolved":
        return "The producer has not resolved an authoritative FJC source identity."
    ids = typed.get("upstream_record")
    if not isinstance(ids, dict) or any(not isinstance(ids.get(k), str) or not re.fullmatch(r"[0-9]+", ids[k]) for k in ("nid", "jid")):
        return "Both authoritative FJC upstream identifiers are required."
    suffix = f"nid:{ids['nid']}:jid:{ids['jid']}"
    expected = {"upstream_record_id": suffix, "subject_id": "fjc:judge:" + suffix,
                "record_identity": "fjc:judicial_biography:" + suffix,
                "provenance_family_id": "fjc:judicial_biography:" + suffix}
    if any(identity.get(k) != value for k, value in expected.items()):
        return "The typed FJC identifiers differ from the producer's source identity."
    if not isinstance(typed.get("appointments"), list):
        return "The supported record has no typed appointment list."
    for appointment in typed["appointments"]:
        if not isinstance(appointment, dict) or any(appointment.get(field) is not None and not isinstance(appointment.get(field), str) for field, _ in FIELDS):
            return "An appointment field has an unsupported shape."
    if typed["schema"].endswith(".observed.v1"):
        historical = typed.get("historical_capture")
        if not isinstance(historical, dict) or historical.get("coverage") != "rendered_fields_only" or identity.get("substantive_revision_sha256"):
            return "The historical observed schema must retain partial coverage and an unknown complete revision."
    return ""


def build_record_chronology(plan, findings, *, operation_id, result_artifact=None):
    """Build a conservative evidence view from previously verified findings.

    Availability describes this display only. It never upgrades model answer
    validity, operation completion, or question adequacy. Unsupported records are
    named rather than repaired or inferred from their prose.
    """
    out = {"schema": SCHEMA, "operation_id": str(operation_id), "status": "unavailable",
        "readiness": "no_supported_record_facts", "title": "Recorded judicial appointments",
        "answer_adequacy": "not_assessed", "question_answered": False,
        "introduction": "Source-attributed fields from saved Federal Judicial Center records. This record view is separate from any model answer.",
        "records": [], "appointments": [], "citations": [], "excluded_records": [],
        "source_family_count": 0, "text": "", "limitations": list(LIMITS),
        "network_requests": 0, "model_requests": 0, "writes": 0}
    if not isinstance(plan, dict) or plan.get("task_profile") != "judicial_biography" or plan.get("subject_type") not in JUDICIAL_TYPES:
        out.update(status="unsupported", readiness="unsupported_scope")
        out["reason"] = "This deterministic display supports the explicit judicial_biography profile for federal judges only."
        return out
    if not isinstance(findings, list):
        out["reason"] = "No verified finding list was supplied."
        return out
    seen_ids, families, text = set(), set(), [out["introduction"]]
    for finding in findings:
        fid = str(finding.get("id") or "") if isinstance(finding, dict) else ""
        reason = _supported(finding)
        if not fid or fid in seen_ids:
            reason = "A distinct finding identifier is required for every capture."
        if reason:
            out["excluded_records"].append({"finding_id": fid or None, "reason": reason})
            continue
        seen_ids.add(fid)
        typed, identity = finding["semantic_record"], finding["source_identity"]
        record_id = str(operation_id) + ":" + fid
        artifact = copy.deepcopy(result_artifact) if isinstance(result_artifact, dict) else None
        source_ref = {"record_id": record_id, "operation_id": str(operation_id), "finding_id": fid,
            "source_url": finding.get("source_url"), "source_name": finding.get("source_name"),
            "result_artifact": artifact, "result_artifact_url": None,
            "derived_finding_sha256": _digest(finding), "derived_hash_basis": "SHA256 compact sorted UTF-8 JSON of the verified finding with correction and lineage overlays; not original transport bytes",
            "body_sha256": hashlib.sha256(str(finding.get("body") or "").encode()).hexdigest(),
            "producer_source_hash": finding.get("source_hash"), "source_identity": copy.deepcopy(identity),
            "lineage": copy.deepcopy(finding.get("lineage") or {}), "correction": copy.deepcopy(finding.get("correction"))}
        if artifact and isinstance(artifact.get("name"), str):
            source_ref["result_artifact_url"] = "/api/open-case/operations/" + quote(str(operation_id), safe="") + "/artifacts/" + quote(artifact["name"], safe="")
        coverage = "rendered_fields_only" if typed["schema"].endswith(".observed.v1") else "captured_typed_record"
        record = {"record_id": record_id, "source_ref": source_ref, "semantic_schema": typed["schema"],
            "historical_coverage": coverage, "complete_historical_revision": "unknown" if coverage == "rendered_fields_only" else identity.get("substantive_revision_sha256") or "unknown",
            "appointments": []}
        families.add(identity["provenance_family_id"])
        text.append(f"\nSaved FJC record {identity['upstream_record_id']} [{record_id}]")
        if coverage == "rendered_fields_only":
            text.append("Only fields supported by the preserved rendering are reconstructed; the complete historical row and revision remain unknown.")
        indexed = list(enumerate(typed["appointments"]))
        indexed.sort(key=lambda item: (_date_key(item[1].get("commission_date")) or "9999-99-99", item[0]))
        for index, appointment in indexed:
            rows = []
            for field, label in FIELDS:
                value = appointment.get(field)
                available = isinstance(value, str) and bool(value.strip())
                row = {"record_id": record_id, "field_path": f"/semantic_record/appointments/{index}/{field}",
                    "label": label, "value": value, "display_value": value if available else MISSING,
                    "status": "recorded" if available else "not_supplied", "source_ref": copy.deepcopy(source_ref)}
                if field.endswith("_date"):
                    row["date_validity"] = "valid" if _date_key(value) else "invalid_or_unsupported" if available else "not_supplied"
                rows.append(row)
            entry = {"record_id": record_id, "source_index": index, "field_path": f"/semantic_record/appointments/{index}",
                "rows": rows, "source_ref": copy.deepcopy(source_ref), "historical_coverage": coverage}
            record["appointments"].append(entry)
            out["appointments"].append(entry)
            text.append("\nAppointment fields recorded by the FJC:")
            for row in rows:
                text.append(f"{row['label']}: {row['display_value']} [{record_id}]")
                if row.get("date_validity") == "invalid_or_unsupported":
                    text.append("This recorded date spelling was not validated; no date relationship is inferred.")
        out["records"].append(record)
        out["citations"].append(source_ref)
    out["source_family_count"] = len(families)
    if out["appointments"]:
        out.update(status="available", readiness="record_facts_available")
        out["text"] = "\n".join(text + ["\nLimits:"] + out["limitations"])
    else:
        out["reason"] = "No supported typed FJC appointment fields are available in the supplied findings."
    out["projection_sha256"] = _digest(out)
    return out
