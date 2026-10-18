"""Read-only Receipts views over locally verified Open Case artifacts.

No model, network, database writes, source edits, or title/URL deduplication.
The pure builder accepts already verified correction projections; from_operation
is the trust boundary that verifies exact saved bytes and signed corrections.
"""
from __future__ import annotations

import copy
from datetime import date
import hashlib
import json
import re
import sqlite3

import pure_receipts as receipts

SCHEMA = "nikodemus.receipts.projection.v1"
UPSTREAM = "daf17d57a09b26ed82695a836c437453cb945474"
MAX_ANCESTORS = 20
DATE_FIELDS = ("nomination_date", "confirmation_date", "commission_date", "recess_appointment_date", "termination_date", "oath_date")


class ProjectionError(ValueError):
    pass


def _sha(value):
    return hashlib.sha256(value).hexdigest()


def _digest(value):
    # A derived object digest, explicitly distinct from exact artifact custody.
    return _sha(json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode())


def _id(kind, value):
    return kind + "_" + _digest(value)[:24]


def _trace(row):
    return {k: row[k] for k in ("record_id", "operation_id", "finding_id", "result_artifact", "original_record_sha256",
        "body_sha256", "lineage", "corrections")}


def _items(value):
    if isinstance(value, list):
        return [(str(i), v) for i, v in enumerate(value)]
    if isinstance(value, dict):
        return [(str(k), v) for k, v in value.items()]
    return []


def _valid_date(value):
    text = str(value or "").strip()
    if not re.fullmatch(r"\d{4}-\d{2}-\d{2}|\d{1,2}/\d{1,2}/\d{4}|[A-Za-z]+\s+\d{1,2},?\s+\d{4}", text):
        return None
    parsed, _, _, _, _ = receipts.extract_best_datetime(text, None)
    try:
        return date.fromisoformat(parsed).isoformat() if parsed else None
    except ValueError:
        return None


def _state(record):
    if record.get("is_absence") or record.get("evidence_kind") == "acquisition_notice":
        return "coverage_notice"
    if not record.get("body"):
        return "metadata_only"
    return "source_text_available"


def _coverage_state(item):
    status = str(item.get("status") or "").lower()
    role = item.get("role")
    if role == "inapplicable" or status in ("inapplicable", "not_applicable"):
        return "not_applicable", "No retry is proposed for an inapplicable source."
    if role == "unimplemented" or status in ("planned_stub", "unimplemented", "not_implemented"):
        return "not_implemented", "This adapter is not implemented; adding it is separate work."
    if status in ("ok", "clean", "cached", "ready", "success", "completed", "available", "searched_with_evidence"):
        if item.get("ready") is False:
            return "evidence_not_ready", "The source check returned, but the producer did not mark its required evidence ready."
        return "available", "A source check completed; that alone does not establish answer support."
    if status in ("not_attempted", "skipped"):
        return "not_attempted", "No source attempt was recorded; review the declared role and access requirements."
    if status in ("network_failure", "rate_limited"):
        return "transient_failure", "Review a bounded retry only after the source becomes available."
    text = " ".join(str(item.get(k) or "") for k in ("status", "detail", "message", "error", "reason")).lower()
    if any(x in text for x in ("inapplicable", "not_applicable", "not applicable")):
        return "not_applicable", "No retry is proposed for an inapplicable source."
    if any(x in text for x in ("not_implemented", "not implemented", "unimplemented")):
        return "not_implemented", "This adapter is not implemented; adding it is separate work."
    if any(x in text for x in ("credential", "unauthorized", "authentication", "api key", "api_key", "401", "403")):
        return "setup_required", "Configure authorized source access before considering another collection."
    if any(x in text for x in ("429", "rate limit", "timeout", "timed out", "transient", "connection", "5xx")):
        return "transient_failure", "Review a bounded retry only after the source becomes available."
    if status in ("ok", "clean", "ready", "success", "completed", "available"):
        return "available", "A source check completed; that alone does not establish answer support."
    if status in ("empty", "no_results", "no results", "not_found", "searched_empty"):
        return "empty_result", "A check returned no matching records; this is not proof the records do not exist."
    if status in ("pending", "not_started", "queued", "running"):
        return "pending", "The saved check has no final outcome."
    return "unresolved_failure", "Inspect the saved failure and identify a different source or a concrete repair before retrying."


def _coverage(bundle, result):
    rows = []
    capabilities = (result.get("dimensions") or {}).get("acquisition", {}).get("capabilities") or []
    cap_by_id = {c.get("id"): c for c in capabilities if isinstance(c, dict)}
    sources = [("dimensions/acquisition/capabilities", capabilities)] + [(field, result.get(field)) for field in ("source_statuses", "source_checks", "failures")]
    for field, value in sources:
        for key, item in _items(value):
            original = item
            if not isinstance(item, dict):
                item = {"status" if field == "source_statuses" else "detail": str(item)}
            cap = cap_by_id.get(item.get("adapter") or item.get("id") or key) or {}
            item = {**cap, **item}
            state, next_action = _coverage_state(item)
            row_id = _id("coverage", [bundle["operation_id"], field, key])
            rows.append({"id": row_id, "operation_id": bundle["operation_id"], "source_pointer": "/" + field + "/" + key.replace("~", "~0").replace("/", "~1"),
                "result_artifact": bundle["result_artifact"], "record_sha256": _digest(original),
                "source": str(item.get("display_name") or item.get("adapter") or item.get("source") or item.get("source_name") or item.get("name") or key),
                "state": state, "reason": str(item.get("detail") or item.get("message") or item.get("error") or item.get("reason") or item.get("status") or "No typed reason recorded."),
                "required": item.get("required", item.get("role") == "required" if item.get("role") else None),
                "role": item.get("role"), "next_action": next_action,
                "capability_id": cap.get("id"),
                "continuation_candidate": field == "dimensions/acquisition/capabilities" or not cap,
                "original": copy.deepcopy(original)})
    return rows


def _typed_events(row, finding):
    typed = finding.get("semantic_record") or {}
    events, absent = [], []
    if typed.get("schema") not in ("fjc.judicial_biography.v1", "fjc.judicial_biography.observed.v1"):
        return events, absent
    appointments = typed.get("appointments")
    if not isinstance(appointments, list):
        return events, absent
    identity = finding.get("source_identity") or {}
    subject_id = identity.get("subject_id")  # Never infer same person from a name.
    for index, appointment in enumerate(appointments):
        if not isinstance(appointment, dict):
            continue
        court = appointment.get("court_name") or "Unnamed court"
        # Same field is comparable only within this authoritative subject and
        # court/seat/title. Ambiguous repeat appointments are withheld below.
        appointment_key = [subject_id, appointment.get("court_name"), appointment.get("court_type"),
                           appointment.get("seat_id"), appointment.get("appointment_title")]
        for field in DATE_FIELDS:
            value = appointment.get(field)
            pointer = f"/semantic_record/appointments/{index}/{field}"
            target_identity = {"family": row["lineage"].get("provenance_family_id"), "subject_id": subject_id,
                "appointment": appointment_key, "field": field} if subject_id and row["lineage"].get("identity_status") == "resolved" \
                and row["lineage"].get("provenance_family_id") and appointment.get("court_name") \
                and sum(1 for other in appointments if isinstance(other, dict) and [subject_id, other.get("court_name"), other.get("court_type"), other.get("seat_id"), other.get("appointment_title")] == appointment_key) == 1 else None
            if value is None or value == "":
                if field == "oath_date":
                    absent.append({"id": _id("gap", [row["record_id"], pointer]), "kind": "typed_field_not_supplied",
                        "state": "not_supplied", "title": f"Oath date is not supplied for {court}",
                        "reason": "The commission date is a different field; this record does not establish an oath date.",
                        "source_pointer": pointer, "trace": _trace(row), "action": "provide_official_source",
                        "target_identity": target_identity})
                continue
            day = _valid_date(value)
            events.append({"id": _id("event", [row["record_id"], pointer]), "type": field.removesuffix("_date"),
                "date": day, "original_date": value, "precision": "date" if day else "invalid_date",
                "title": str(court) + " · " + field.replace("_", " "), "source_pointer": pointer,
                "status": "typed_source_field" if day else "needs_date_review", "trace": _trace(row),
                "subject_id": subject_id, "appointment_key": appointment_key,
                "target_identity": target_identity,
                "comparison_key": _digest([appointment_key, field]) if subject_id and appointment.get("court_name") and day else None,
                "historical_coverage": (typed.get("historical_capture") or {}).get("coverage", "captured_typed_record")})
    return events, absent


def _references(row):
    # This detects mentions; it cannot establish that a separate attachment is
    # absent. No URL/title matching is used to manufacture a resolved match.
    if row["state"] != "source_text_available" or row["evidence_kind"] == "derived_interpretation":
        return []
    text, found = row["excerpt"], []
    seen = set()
    for rule in receipts._rules():
        for match in rule.pattern.finditer(text):
            if receipts._negates_near(text, match.span()):
                continue
            before = text[max(0, match.start() - 50):match.start()]
            if re.search(r"\b(?:maybe|might|could|perhaps|no|without)\b[^.!?]*$", before, re.I):
                continue
            key = (rule.item_type, match.start(), match.end())
            if key in seen:
                continue
            seen.add(key)
            found.append({"id": _id("gap", [row["record_id"], list(key)]), "kind": "referenced_material",
                "state": "linkage_unresolved", "title": "Referenced " + rule.referenced_label,
                "reason": "A saved passage mentions this material. No explicit record linkage establishes whether it is included; review is required.",
                "excerpt": text[max(0, match.start()-70):min(len(text), match.end()+70)],
                "mention": match.group(0), "body_range": {"start": match.start(), "end": match.end(), "unit": "unicode_code_points"},
                "trace": _trace(row), "action": "identify_or_provide_source", "rule_confidence": rule.confidence})
    return found


def _comparisons(events):
    groups = {}
    for e in events:
        if e["comparison_key"]:
            groups.setdefault(e["comparison_key"], []).append(e)
    rows = []
    for key, group in groups.items():
        # Multiple appointments in one captured row with the same court/seat/
        # title may be separate terms. Do not fabricate a conflict between them.
        by_record = {}
        for event in group:
            by_record.setdefault(event["trace"]["record_id"], []).append(event)
        ambiguous = any(len(values) > 1 for values in by_record.values())
        dates = sorted({e["date"] for e in group})
        if len(group) < 2:
            continue
        families = {e["trace"]["lineage"].get("provenance_family_id") for e in group}
        revisions = {e["trace"]["lineage"].get("substantive_revision_id") for e in group}
        if ambiguous:
            kind, reason = "ambiguous_event_match", "Repeated appointments cannot be matched safely without a stronger event identifier."
        elif len(dates) == 1:
            kind, reason = "matching_field", "The typed date agrees. Copies, imports and revisions are retained separately; agreement does not establish independent corroboration."
        elif None in families:
            kind, reason = "unresolved_provenance", "Typed dates differ, but source provenance is unresolved. Review the original records."
        elif len(families) == 1:
            kind, reason = "same_source_variation", "Typed dates differ within one source family. This may be a revision or extraction issue, not independent conflicting testimony."
        else:
            kind, reason = "candidate_conflict", "Distinct source families report different typed dates for this subject and appointment. Event identity and meaning still require human review."
        rows.append({"id": _id("comparison", [key, [e["id"] for e in group]]), "type": kind,
            "field": group[0]["type"], "title": group[0]["title"], "dates": dates,
            "reason": receipts._neutral_guard(reason), "events": [e["id"] for e in group],
            "traces": [e["trace"] for e in group], "source_families": sorted(x for x in families if x),
            "substantive_revisions": sorted(x for x in revisions if x),
            "independence": "not_assessed", "semantic_contradiction": "not_established"})
    return rows


def _continuations(root, gaps, coverage, conflicts, source_manifest):
    plan = root["plan"]
    proposals = []
    # Collapse equivalent next actions, never original records or gap history.
    # A same-name/URL resemblance is insufficient: only resolved family +
    # authoritative subject + unambiguous typed appointment/field can group.
    grouped = {}
    for gap in gaps:
        if gap.get("related_supplied_fields"):
            continue
        key = _id("gap_group", gap["target_identity"]) if gap.get("target_identity") else gap["id"]
        if key not in grouped:
            grouped[key] = {"id": key, "title": gap["title"], "action": gap["action"], "reason": gap["reason"],
                            "source_refs": [], "gap_ids": [], "group_basis": "resolved_family_and_typed_field" if gap.get("target_identity") else "single_gap"}
        grouped[key]["source_refs"].append(gap["trace"])
        grouped[key]["gap_ids"].append(gap["id"])
    targets = [(g["id"], g["title"], g["action"], g["reason"], g["source_refs"], g["gap_ids"], g["group_basis"]) for g in grouped.values()]
    for c in coverage:
        if c["operation_id"] == root["operation_id"] and c["continuation_candidate"] and c["state"] not in ("available", "not_applicable", "not_implemented", "pending"):
            targets.append((c["id"], "Coverage from " + c["source"], c["state"], c["next_action"], [c], [c["id"]], "selected_operation_coverage"))
    for c in conflicts:
        if c["type"] != "matching_field":
            targets.append((c["id"], c["title"], "compare_saved_records", c["reason"], c["traces"], [c["id"]], "comparison"))
    for gap_id, title, action, reason, refs, gap_ids, group_basis in targets:
        # Questions can guide the existing collector/model, but cannot select a
        # new provider, upload a file, repair credentials or force a scoped retry.
        question = f"For {plan.get('subject_name') or 'this subject'}, what does the saved evidence establish about {title[:600].lower()}? Identify the exact missing record or verification needed and distinguish it from the available evidence."
        proposals.append({"id": _id("continuation", [root["operation_id"], gap_id]), "gap_id": gap_id,
            "title": title, "action": action, "reason": reason, "question": question,
            "follow_up_of": root["operation_id"], "origin_preserved": True,
            "source_refs": refs, "gap_ids": gap_ids, "group_basis": group_basis, "source_manifest_sha256": _digest(source_manifest),
            "dispatch": "manual_proposal_only", "auto_retry": False, "supported_next_step": "fill_follow_up_question",
            "limitation": "Review the existing source profile and allowance before Start. This question does not repair access or limit collection to one adapter."})
    return proposals


def build_projection(bundles, *, omissions=None):
    """Pure deterministic projection. First bundle is selected operation.

    Each bundle: operation_id, plan, result_artifact, raw_result:bytes,
    findings: verified enriched records in original order, corrections, synthesis.
    Raw artifact digest and record membership are checked again here.
    """
    if not bundles:
        raise ProjectionError("A saved investigation is required.")
    matrix, coverage, timeline, gaps, inputs, unknown_dates = [], [], [], [], [], []
    selected_answer = bundles[0].get("synthesis") or {}
    cited = {c.get("record_id") for c in selected_answer.get("citations", [])} if selected_answer.get("status") == "complete" else set()
    seen_ops = set()
    for bundle in bundles:
        op_id = bundle["operation_id"]
        if op_id in seen_ops:
            raise ProjectionError("A projection cannot include the same operation twice.")
        seen_ops.add(op_id)
        raw = bundle["raw_result"]
        if _sha(raw) != bundle["result_artifact"].get("sha256"):
            raise ProjectionError("A saved result no longer matches its recorded hash.")
        result = json.loads(raw)
        original = result.get("findings") or []
        enriched = bundle["findings"]
        if len(original) != len(enriched) or any(str(a.get("id")) != str(b.get("id")) for a,b in zip(original,enriched)):
            raise ProjectionError("The projected records differ from the saved result membership.")
        ids = [str(f.get("id")) for f in original]
        if len(set(ids)) != len(ids) or any(x in ("", "None") for x in ids):
            raise ProjectionError("Saved findings need distinct stable record identifiers.")
        inputs.append({"operation_id": op_id, "result_artifact": bundle["result_artifact"],
                       "corrections": bundle.get("corrections", []), "question_sha256": _digest(bundle["plan"].get("question")),
                       "origin_sha256": _digest(bundle["plan"].get("origin"))})
        for index, (captured, finding) in enumerate(zip(original, enriched)):
            correction_fields = {"evidence_kind", "evidence_label", "semantics_version", "kind_note", "semantic_record", "source_identity", "lineage", "correction"}
            if any(finding.get(key) != value for key, value in captured.items() if key not in correction_fields):
                raise ProjectionError("A projection cannot rewrite captured source fields.")
            body = str(finding.get("body") or "")
            row = {"record_id": op_id + ":" + str(finding["id"]), "operation_id": op_id,
                "finding_id": str(finding["id"]), "title": finding.get("title") or str(finding["id"]),
                "source_name": finding.get("source_name"), "source_url": finding.get("source_url"),
                "state": _state(finding), "evidence_kind": finding.get("evidence_kind") or "unclassified",
                "epistemic_level": finding.get("epistemic_level"), "lineage": copy.deepcopy(finding.get("lineage") or {}),
                "result_artifact": bundle["result_artifact"], "source_pointer": f"/findings/{index}",
                "original_record_sha256": _digest(captured), "record_hash_basis": "sha256 compact sorted UTF-8 JSON of original finding; not original transport bytes",
                "body_sha256": _sha(body.encode()), "excerpt": body,
                "excerpt_range": {"start": 0, "end": len(body), "unit": "unicode_code_points", "field": "body"},
                "corrections": copy.deepcopy(bundle.get("corrections", [])), "used_in_answer": op_id + ":" + str(finding["id"]) in cited,
                "answer_operation_id": bundles[0]["operation_id"], "citation_basis": "structural_reference_only",
                "support_for_question": "not_assessed", "source_truth": "not_certified_by_signature"}
            matrix.append(row)
            if row["state"] == "coverage_notice":
                gaps.append({"id": _id("gap", row["record_id"]), "kind": "producer_coverage_notice", "state": "recorded_notice",
                    "title": row["title"], "reason": body or "The producer recorded a coverage notice.", "trace": _trace(row), "action": "review_notice"})
                continue
            if row["state"] == "metadata_only":
                gaps.append({"id": _id("gap", row["record_id"]), "kind": "metadata_only", "state": "text_unavailable",
                    "title": "Source text not retained: " + row["title"], "reason": "Metadata cannot supply a quoted passage.",
                    "trace": _trace(row), "action": "provide_authorized_copy"})
                continue
            typed_events, absent = _typed_events(row, finding)
            timeline.extend(typed_events); gaps.extend(absent); gaps.extend(_references(row))
            if not typed_events:
                parsed, time, precision, approximate, span = receipts.extract_best_datetime(body, None)
                unknown_dates.append({"record_id": row["record_id"], "trace": _trace(row),
                    "state": "untyped_date_mention" if parsed or time else "no_typed_event_date",
                    "date": _valid_date(parsed), "time": time, "matched_text": span, "precision": precision,
                    "reason": "Text mentions are not promoted to event dates; the adapter has no supported typed event schema for this record."})
        coverage.extend(_coverage(bundle, result))
    timeline.sort(key=lambda e: (e["date"] or "9999", e["id"]))
    supplied = {}
    for event in timeline:
        if event.get("target_identity") and event.get("date"):
            supplied.setdefault(_digest(event["target_identity"]), []).append(event["trace"])
    for gap in gaps:
        related = supplied.get(_digest(gap["target_identity"])) if gap.get("target_identity") else None
        if related:
            gap["related_supplied_fields"] = related
            gap["reason"] += " Another saved record in this resolved source family supplies this typed field; this original gap remains in history, without a new missing-field collection suggestion. Conflicting values still require review."
    conflicts = _comparisons(timeline)
    root = bundles[0]
    payload = {"schema": SCHEMA, "operation_id": root["operation_id"], "question": root["plan"].get("question"),
        "manifest": {"adapter_version": SCHEMA, "receipts_commit": UPSTREAM, "inputs": inputs,
                     "source_manifest_sha256": _digest(inputs), "omissions": omissions or [],
                     "scope": "Selected operation and locally saved ancestors, at most 20; all captures retained.",
                     "transformation": "Derived local JSON projection; source text not redacted or rewritten; no URL/title deduplication."},
        "evidence_matrix": matrix, "missing_evidence": gaps, "coverage": coverage, "timeline": timeline,
        "unplaced_records": unknown_dates, "comparisons": conflicts,
        "continuations": _continuations(root, gaps, coverage, conflicts, inputs),
        "limitations": ["Reference detection identifies mentions, not proof that material is missing or concealed.",
            "Evidence presence and producer labels do not establish support for every part of the question.",
            "Timeline events are typed source fields; prose dates remain unplaced. Only supported FJC appointment fields are compared in this slice.",
            "Different source families alone do not establish independent corroboration. Candidate conflicts require review.",
            "Continuation questions group only resolved same-family typed field gaps; all original gaps remain visible. Coverage suggestions use the selected operation, while older coverage stays in history.",
            "Continuation suggestions fill a question only; source setup, uploads and targeted adapter retries are not implemented here."],
        "network_requests": 0, "model_requests": 0, "writes": 0}
    payload["projection_sha256"] = _digest(payload)
    return payload


def freeze_continuation(parent, request):
    """Resolve a displayed suggestion again before freezing the local proposal."""
    import opencase
    if not isinstance(request, dict) or not parent or request.get("operation_id") != parent["op_id"]:
        raise opencase.WorkflowError("A Receipts continuation must name its saved parent investigation.", 409)
    projection = from_operation(parent)
    if projection["projection_sha256"] != request.get("projection_sha256"):
        raise opencase.WorkflowError("The saved evidence review changed. Rebuild it before preparing this continuation.", 409)
    suggestion = next((r for r in projection["continuations"] if r["id"] == request.get("id")), None)
    if not suggestion:
        raise opencase.WorkflowError("No such continuation is in the saved evidence review.", 409)
    return {**copy.deepcopy(suggestion), "projection_sha256": projection["projection_sha256"]}


def _answer_usage(op):
    """Read-only citation membership and exact-receipt review overlay.

    The full synthesis view calls the mutating operations connection helper.
    This projection needs only complete/held citation membership, not a newly
    normalized answer. Any saved non-complete state remains non-complete.
    """
    import opencase
    import operations as ops
    state = (op.get("result_ref") or {}).get("synthesis") or {}
    if state.get("status") != "complete" or state.get("answer_status") == "held":
        return {"status": state.get("status", "not_requested"), "citations": []}
    if not (state.get("response_artifact") or {}).get("name"):
        return {"status": "unverified_receipt", "citations": []}
    for key in ("manifest_artifact", "response_artifact", "prompt_artifact"):
        if state.get(key):
            opencase.artifact(op, state[key]["name"])
    path = ops.db_path()
    if not path.is_file():
        raise ProjectionError("The saved answer review history is unavailable.")
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        rows = conn.execute("SELECT detail FROM operation_events WHERE op_id = ? ORDER BY seq ASC", (op["op_id"],)).fetchall()
        for (detail,) in rows:
            event_detail = json.loads(detail or "{}") or {}
            if not isinstance(event_detail, dict):
                raise ProjectionError("The saved answer review history is malformed.")
            review = event_detail.get("answer_review") or {}
            if not isinstance(review, dict):
                raise ProjectionError("The saved answer review history is malformed.")
            if review.get("schema") == "nikodemus.open_case.answer_review.v1" and review.get("response_artifact") == (state.get("response_artifact") or {}):
                return {"status": "rejected", "citations": []}
    finally:
        conn.close()
    return {"status": "complete", "citations": copy.deepcopy(state.get("citations") or [])}


def _from_operation(op):
    import opencase
    if not opencase.is_ours(op):
        raise opencase.WorkflowError("No Open Case investigation with that id.", 404)
    bundles, seen, omissions = [], set(), []
    current = op
    while current and len(seen) < MAX_ANCESTORS:
        if current["op_id"] in seen:
            omissions.append({"operation_id": current["op_id"], "reason": "Ancestry cycle; traversal stopped."}); break
        seen.add(current["op_id"])
        ref = current.get("result_ref") or {}
        artifact = ref.get("result_artifact")
        if artifact:
            raw = opencase.artifact(current, artifact["name"])
            result = json.loads(raw)
            bundles.append({"operation_id": current["op_id"], "plan": (current.get("execution") or {}).get("plan") or {},
                "result_artifact": artifact, "raw_result": raw, "findings": opencase.findings_for(current, result),
                "corrections": copy.deepcopy(ref.get("corrections", [])), "synthesis": _answer_usage(current)})
        elif current is op:
            raise opencase.WorkflowError("The investigation has no saved source result to project yet.", 409)
        else:
            omissions.append({"operation_id": current["op_id"], "reason": "Ancestor has no saved result."})
        parent = ((current.get("execution") or {}).get("plan") or {}).get("follow_up_of")
        if not parent:
            break
        if len(seen) >= MAX_ANCESTORS:
            omissions.append({"operation_id": parent, "reason": "Ancestry limit reached."}); break
        current = load_operation(parent)
        if not opencase.is_ours(current):
            omissions.append({"operation_id": parent, "reason": "Saved ancestor is unavailable."}); break
    try:
        return build_projection(bundles, omissions=omissions)
    except (ProjectionError, ValueError, TypeError) as e:
        raise opencase.WorkflowError("The saved evidence projection could not be verified: " + str(e), 409) from e


def from_operation(op):
    """Integration boundary: only read NK operations and hash-verified artifacts."""
    import opencase
    try:
        return _from_operation(op)
    except opencase.WorkflowError:
        raise
    except (ValueError, TypeError, KeyError, sqlite3.Error) as e:
        raise opencase.WorkflowError("The saved evidence projection could not be verified: " + str(e), 409) from e


def load_operation(op_id):
    """Read the existing operation spine without initializing or migrating it."""
    import operations as ops
    path = ops.db_path()
    if not path.is_file():
        return None
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        return ops._row(conn.execute("SELECT * FROM operations WHERE op_id = ? OR legacy_job_id = ?", (op_id, op_id)).fetchone())
    finally:
        conn.close()
