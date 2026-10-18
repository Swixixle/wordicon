"""The bounded Open Case workflow. Proposals and GET views are entirely local.

An explicit Start sends one idempotent request to the configured producer.
After that only its recorded job is polled; an uncertain Start is never replayed.
Every response is kept by hash and the result remains readable without a producer.
"""
from __future__ import annotations

import hashlib
import base64
import copy
from pathlib import Path
import json
import re
import threading
import time

import federation
import operations as ops
import producers
import snapshots
import testmode
import vault
import wordicon_cli as cli
import opencase_synthesis as synthesis
import opencase_grounding

ACTION = "investigate.opencase.question"
CONTRACT = "open-case-investigation-v1"
ALLOWANCE = {"max_cost_usd": 0, "paid_models": False}
SUBJECT_TYPES = ("federal_judge_district", "federal_judge_circuit", "federal_judge_scotus", "senator")
TERMINAL = ("completed", "partial", "failed", "interrupted")
_workers = set()
_lock = threading.Lock()


def _mark(*args, **kwargs):
    with vault.corpus_write():
        vault.mark_dirty()
        return ops.mark(*args, **kwargs)


def _event(*args, **kwargs):
    with vault.corpus_write():
        vault.mark_dirty()
        return ops.event(*args, **kwargs)


class WorkflowError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def connector(cid=None):
    return federation.get_connector(cid) if cid else producers._connector_for("open_case")


def _identity(c):
    return {k: c.get(k) for k in ("connector_id", "producer", "base_url", "origin", "credential_ref", "dev_loopback")}


def readiness(cid=None):
    c = connector(cid)
    rows = [r for r in federation._rows(federation.connectors_log())
            if r.get("kind") == "open_case_workflow_enabled" and c and r.get("connector_id") == c["connector_id"]]
    ruling = rows[-1] if rows else {}
    authorized = bool(ruling.get("enabled") and ruling.get("contract") == CONTRACT and ruling.get("connector") == _identity(c)) if c else False
    fixture = bool(c and testmode.active() and c.get("dev_loopback"))
    reason = ("No Open Case connector is registered." if not c else
              "The Open Case connector is disabled." if not c.get("enabled") else
              "The Open Case credential is missing." if not c.get("credential_configured") else
              "The bounded investigation deployment has not been enabled." if not authorized and not fixture else "")
    return {"available": not reason, "reason": reason, "connector_id": (c or {}).get("connector_id", ""),
            "contract": CONTRACT, "authorized": authorized, "fixture_only": fixture,
            "allowance": ALLOWANCE, "subject_types": list(SUBJECT_TYPES), "synthesis": synthesis.configuration()}


def authorize(cid, enabled, note):
    c = federation.get_connector(cid)
    if not c or c.get("producer") != "open_case":
        raise WorkflowError("No Open Case connector with that id.", 404)
    if enabled and not str(note or "").strip():
        raise WorkflowError("Record who verified this deployment and the authorization for live use.")
    return federation._append(federation.connectors_log(), {"kind": "open_case_workflow_enabled", "connector_id": cid,
        "enabled": bool(enabled), "note": str(note or "")[:500], "by": "owner", "contract": CONTRACT, "connector": _identity(c)})


def _bounded_text(value, name, limit, required=True):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise WorkflowError(f"{name} must be {'nonempty ' if required else ''}text of at most {limit} characters.")
    return value.strip()


def _origin(origin, question):
    if not origin:
        return {"kind": "question", "text": question}
    if not isinstance(origin, dict):
        raise WorkflowError("The origin must be a record.")
    kind = origin.get("kind")
    if kind in ("document", "selection", "description"):
        text = _bounded_text(origin.get("text", ""), "Origin text", 200000)
        doc_id = str(origin.get("doc_id") or "")
        if doc_id:
            import notebook
            if notebook.get(doc_id) is None:
                raise WorkflowError("The originating document is not in this store.", 404)
        snap = snapshots.make(kind=kind, text=text, doc_id=doc_id, revision=origin.get("revision"), seq=origin.get("seq"),
            range_=origin.get("range"), units=origin.get("units", "codepoint"), title=str(origin.get("title") or ""),
            editor_session=str(origin.get("editor_session") or ""))
        snapshots.write(snap)
        return {**snapshots.summary(snap), "title": str(origin.get("title") or "")[:200], "text": text}
    if kind == "deposition":
        import deeper
        root = deeper._deposition_root(origin.get("deposition_id"), origin.get("item_ref"))
        return {"kind": kind, **root}
    if kind == "reading":
        import moira
        rid = str(origin.get("reading_id") or "")
        record = moira.load_reading(rid)
        if not record:
            raise WorkflowError("The originating reading is not in this store.", 404)
        return {"kind": kind, "reading_id": rid, "text": record.get("input_text", ""), "document": record.get("document"),
                "snapshot": record.get("snapshot"), "title": "Reading " + rid}
    if kind == "question":
        return {"kind": kind, "text": _bounded_text(origin.get("text", question), "Origin question", 4000)}
    raise WorkflowError("An origin can be a document, selection, reading, imported Deflate item, or question.")


def prepare(question, inputs):
    if not isinstance(inputs, dict):
        raise WorkflowError("Investigation inputs must be a record.")
    question = _bounded_text(question, "Question", 4000)
    name = _bounded_text(inputs.get("subject_name"), "Public subject name", 200)
    typ = str(inputs.get("subject_type") or "federal_judge_district")
    typ = {"federal_judge": "federal_judge_district", "scotus": "federal_judge_scotus"}.get(typ, typ)
    if typ not in SUBJECT_TYPES:
        raise WorkflowError("Choose a supported federal judge or senator profile.")
    jurisdiction = _bounded_text(inputs.get("jurisdiction", "United States"), "Jurisdiction", 120)
    for key, pattern in (("bioguide_id", r"[A-Za-z][0-9]{6}"), ("fec_committee_id", r"C[0-9]{8}")):
        if key in inputs and not re.fullmatch(pattern, str(inputs[key] or "")):
            raise WorkflowError(f"Invalid {key}.")
    allowance = inputs.get("allowance", ALLOWANCE)
    if not isinstance(allowance, dict) or type(allowance.get("max_cost_usd")) not in (int, float) or allowance.get("max_cost_usd") != 0 or allowance.get("paid_models") is not False:
        raise WorkflowError("The public-record collection stage requires $0 with paid enrichment disabled; optional model synthesis has a separate allowance.")
    parent_id = str(inputs.get("follow_up_of") or "")
    parent = ops.get(parent_id) if parent_id else None
    if parent_id and (not parent or parent.get("action_id") != ACTION):
        raise WorkflowError("The follow-up must name an Open Case investigation in this store.", 404)
    origin = _origin(inputs.get("origin"), question) if not parent else (parent.get("execution") or {}).get("plan", {}).get("origin")
    if parent and not origin:
        raise WorkflowError("The earlier investigation has no saved origin.", 409)
    task_profile = str(inputs.get("task_profile") or "public_records")
    if task_profile not in ("public_records", "judicial_biography") or (task_profile == "judicial_biography" and typ == "senator"):
        raise WorkflowError("Choose an applicable investigation purpose: judicial biography or broad public records.")
    reuse = str(inputs.get("reuse_evidence_from") or "")
    if reuse and (not parent or reuse != parent_id or question != parent["execution"]["plan"]["question"]):
        raise WorkflowError("Answer recovery must keep the previous question and name its saved investigation.")
    receipts_continuation = None
    if inputs.get("receipts_continuation") is not None:
        import receipts_projection
        receipts_continuation = receipts_projection.freeze_continuation(parent, inputs["receipts_continuation"])
    model_plan = synthesis.prepare(inputs.get("synthesis"), parent)
    if reuse and not model_plan.get("enabled"):
        raise WorkflowError("Answer recovery needs an explicitly enabled model allowance.")
    if reuse:
        model_plan["recovery_of"] = reuse
    source_scope = (["Federal Judicial Center biographies", "CourtListener (availability depends on credentials)", "USAspending", "Indiana campaign finance"] if typ != "senator" else
                    ["FEC campaign finance", "Senate roll call records", "Congress.gov", "Lobbying Disclosure Act records", "USAspending", "Other existing Open Case public-record adapters"])
    if task_profile == "judicial_biography":
        source_scope = ["Required: Federal Judicial Center biography", "Optional: CourtListener, if credentials are available",
                        "Inapplicable: campaign finance, contracts, lobbying and regulatory records",
                        "Unimplemented sources are disclosed by the producer and are not counted as failed attempts"]
    if reuse:
        source_scope = ["Saved evidence from " + reuse + "; no new source collection"]
    c = connector(inputs.get("connector_id"))
    if inputs.get("connector_id") and (not c or c.get("producer") != "open_case"):
        raise WorkflowError("No Open Case connector with that id.", 404)
    outbound_origin = {k: origin[k] for k in ("kind", "doc_id", "snapshot_id", "revision", "seq", "range", "text_sha256", "reading_id", "deposition_id", "item_ref", "title") if k in origin}
    outbound_origin["origin_sha256"] = hashlib.sha256(json.dumps(origin, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()
    outbound_origin["storage"] = "The complete frozen origin is retained in Nikodemus."
    parent_plan = (parent.get("execution") or {}).get("plan") or {} if parent else {}
    return {"contract": CONTRACT, "question": question, "root_question": parent_plan.get("root_question") or parent_plan.get("question") or question,
        "subject_name": name, "subject_type": typ, "jurisdiction": jurisdiction, "task_profile": task_profile, "reuse_evidence_from": reuse,
        "origin": origin, "outbound_origin": outbound_origin, "follow_up_of": parent_id, "allowance": dict(ALLOWANCE), "connector": _identity(c) if c else None,
        "source_scope": source_scope, "synthesis": model_plan, "receipts_continuation": receipts_continuation,
        "source_capabilities": json.loads(Path(__file__).with_name("opencase_capabilities.json").read_text())["profiles"][typ][task_profile] if not reuse else [],
        "steps": (["Verify the frozen saved evidence and corrections", "Make one model answer attempt under the reviewed allowance", "Keep this attempt beside its original question and history"] if reuse else
                  ["Create a case for this question", "Check the public records supported by the selected profile",
                   "Keep findings, source checks, failures and a signed case export", "Save a local copy in Nikodemus"]),
        "limitations": ["The question is saved as the investigation's purpose; it is not a model instruction to search arbitrary topics.",
                        "Coverage is limited to the selected public-record profile; source failures and empty results remain visible.",
                        "Producer model enrichment is disabled. An optional model answer uses only the saved source records when explicitly selected."],
        "cost": ("Public-source collection: $0. " + model_plan["cost"] if model_plan["enabled"] else "$0 maximum; no model request or paid plugin is enabled."),
        **{k: _bounded_text(inputs[k], k, 100, False) for k in ("bioguide_id", "fec_committee_id") if k in inputs}}


def is_ours(op):
    return bool(op and op.get("action_id") == ACTION)


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get("contract") != CONTRACT or plan.get("allowance") != ALLOWANCE:
        raise WorkflowError("The frozen Open Case plan is not supported; prepare again.", 409)
    if plan.get("reuse_evidence_from"):
        parent = ops.get(plan["reuse_evidence_from"])
        if not is_ours(parent) or plan.get("follow_up_of") != parent["op_id"]:
            raise WorkflowError("The recovery's saved investigation is unavailable.", 409)
        frozen = (plan.get("synthesis") or {}).get("follow_up_context") or {}
        raw = artifact(parent, (frozen.get("result_artifact") or {}).get("name", ""))
        if hashlib.sha256(raw).hexdigest() != (frozen.get("result_artifact") or {}).get("sha256"):
            raise WorkflowError("The recovery evidence differs from its proposal.", 409)
        synthesis.validate(plan)
        return None
    c = connector((plan.get("connector") or {}).get("connector_id"))
    if not c or plan.get("connector") != _identity(c):
        raise WorkflowError("The Open Case connection changed since this proposal; prepare again.", 409)
    rd = readiness(c["connector_id"])
    if not rd["available"]:
        raise WorkflowError(rd["reason"], 409)
    synthesis.validate(plan)
    return c


def _correlate(remote_plan, plan):
    if not isinstance(remote_plan, dict):
        raise WorkflowError("The producer reply has no investigation plan to check.", 502)
    expected = {k: plan.get(k) for k in ("question", "subject_name", "subject_type", "jurisdiction", "allowance", "bioguide_id", "fec_committee_id")}
    if "task_profile" in plan:
        expected["task_profile"] = plan["task_profile"]
    expected["origin"] = plan["outbound_origin"]
    expected["follow_up_of"] = plan.get("follow_up_of") or ""
    for key, value in expected.items():
        actual = remote_plan.get(key)
        if key == "follow_up_of":
            actual = actual or ""
        if actual != value:
            raise WorkflowError(f"The producer returned a different {key}; its bytes are kept but not accepted as this investigation.", 502)


def _keep(op_id, name, raw):
    # One guard covers the artifact and its index update. The vault read lock is
    # not reentrant, so raw store methods are used inside this guard.
    with vault.corpus_write():
        vault.mark_dirty()
        kept = producers.keep_artifact(op_id, name, raw)
        op = ops.get(op_id)
        ref = dict(op.get("result_ref") or {})
        all_kept = list(ref.get("kept") or [])
        if not any(k.get("name") == kept["name"] and k.get("sha256") == kept["sha256"] for k in all_kept):
            all_kept.append(kept)
        ref["kept"] = all_kept
        ops.mark(op_id, result_ref=ref, event_kind="note", detail={"artifact": kept})
        return kept


def _request(op_id, c, method, path, body=None):
    stage = method + " " + path
    _event(op_id, "stage_intent", stage=stage, detail={"contract": CONTRACT, "paid_models": False})
    r = producers._request(c, method, path, body, auth="bearer")
    kept = _keep(op_id, "start-reply.json" if method == "POST" else ("result.json" if path.endswith("/result") else "status.json"), r["raw"]) if r.get("raw") else None
    _event(op_id, "stage_end", stage=stage, outcome="ok" if r.get("ok") else "error",
              detail={"delivery": r.get("delivery"), "outcome": r.get("outcome"), "http_status": r.get("status"), "kept": kept})
    return r, kept


def _job_id(value):
    if not isinstance(value, str) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", value):
        raise WorkflowError("The producer answered with no safe investigation id.", 502)
    return value


def launch(op_id, resume=False):
    with _lock:
        if op_id in _workers:
            return False
        _workers.add(op_id)
    threading.Thread(target=_run, args=(op_id, resume), daemon=True, name="opencase-" + op_id).start()
    return True


def _run(op_id, resume=False):
    try:
        op = ops.get(op_id)
        plan = (op.get("execution") or {}).get("plan") or {}
        if (op.get("result_ref") or {}).get("result_artifact"):
            synthesis.run(op_id)
            return
        c = validate_plan(plan)
        if plan.get("reuse_evidence_from"):
            parent = ops.get(plan["reuse_evidence_from"])
            original = parent["result_ref"]
            source = _keep(op_id, "result.json", artifact(parent, original["result_artifact"]["name"]))
            frozen_corrections = (plan.get("synthesis") or {}).get("follow_up_context", {}).get("corrections", [])
            correction_names = {r["name"] for r in frozen_corrections}
            for kept in original.get("kept", []):
                if kept["name"] == "deposition.json" or kept["name"] in correction_names:
                    _keep(op_id, kept["name"], artifact(parent, kept["name"]))
            ref = dict(ops.get(op_id).get("result_ref") or {})
            ref.update(result_artifact=source, artifact=source, custody=original.get("custody"),
                       upstream_status=original.get("upstream_status"), case_id=original.get("case_id"),
                       evidence_reused_from=parent["op_id"], corrections=frozen_corrections)
            _mark(op_id, "running", result_ref=ref, local_state="Reusing the saved evidence; preparing one new model answer.")
            synthesis.run(op_id)
            return
        job_id = (op.get("result_ref") or {}).get("upstream_id")
        if not job_id:
            if resume:
                raise WorkflowError("No upstream job id was recorded; the Start is not repeated.", 409)
            body = {k: plan[k] for k in ("question", "subject_name", "subject_type", "jurisdiction", "allowance", "origin", "follow_up_of", "bioguide_id", "fec_committee_id", "task_profile") if k in plan}
            body["origin"] = plan["outbound_origin"]
            body["request_key"] = op_id
            r, kept = _request(op_id, c, "POST", "/api/v1/investigations", body)
            if not r.get("ok"):
                outcome, delivery, detail = producers._outcome_of_failure(r)
                _mark(op_id, "failed" if outcome in ("not_sent", "refused") else "unknown", local_state=detail, last_error=detail,
                         producer_state={"outcome": outcome, "delivery": delivery})
                return
            reply = r.get("json") or {}
            job_id = _job_id(reply.get("job_id"))
            _correlate(reply.get("plan"), plan)
            ref = dict(ops.get(op_id).get("result_ref") or {})
            ref.update({"upstream_id": job_id, "case_id": reply.get("case_id"), "reply_kept": kept})
            _mark(op_id, "running", local_state="Open Case accepted the investigation", result_ref=ref,
                     producer_state={"status": reply.get("status"), "delivery": "delivered"})
        _job_id(job_id)
        deadline = time.monotonic() + 1800
        last = None
        while time.monotonic() < deadline:
            r, kept = _request(op_id, c, "GET", "/api/v1/investigations/" + job_id)
            if not r.get("ok"):
                _mark(op_id, "unknown", local_state="The investigation status could not be read; the known job can be checked again.",
                         last_error=federation._scrub(str(r.get("detail") or r.get("outcome"))))
                return
            status = r.get("json") or {}
            if status.get("job_id") != job_id:
                raise WorkflowError("The producer returned another investigation's status; its bytes are kept.", 502)
            _correlate(status.get("plan"), plan)
            word = status.get("status")
            stamp = json.dumps([word, status.get("progress"), status.get("events")], sort_keys=True)
            if stamp != last:
                progress = status.get("progress")
                progress_text = progress if isinstance(progress, str) else (progress or {}).get("message", "")
                ref = dict(ops.get(op_id).get("result_ref") or {})
                if status.get("case_id"):
                    if ref.get("case_id") and ref["case_id"] != status["case_id"]:
                        raise WorkflowError("The producer changed the investigation case id.", 502)
                    ref["case_id"] = status["case_id"]
                _mark(op_id, "running", local_state=progress_text or str(word), producer_state=status, result_ref=ref,
                         event_kind="stage", detail={"upstream_status": word, "progress": progress, "events": status.get("events", [])})
                last = stamp
            if word in TERMINAL:
                _result(op_id, c, job_id, word)
                return
            time.sleep(1.5)
        _mark(op_id, "unknown", local_state="Status checking paused after 30 minutes. Check this existing job to continue.", last_error="Polling time limit reached.")
    except Exception as e:
        _mark(op_id, "unknown", local_state="Investigation needs attention", last_error=federation._scrub(str(e))[:500])
    finally:
        with _lock:
            _workers.discard(op_id)
        vault.mark_dirty()


def _result(op_id, c, job_id, status):
    r, kept = _request(op_id, c, "GET", "/api/v1/investigations/" + job_id + "/result")
    if not r.get("ok"):
        _mark(op_id, "unknown", local_state="The investigation finished but its result could not be copied. Check the existing job again.", last_error=str(r.get("outcome")))
        return
    result = r.get("json") or {}
    if result.get("job_id") != job_id:
        raise WorkflowError("The producer returned another investigation's result; its bytes are kept.", 502)
    plan = (ops.get(op_id).get("execution") or {}).get("plan") or {}
    _correlate(result.get("plan"), plan)
    if (result.get("question") != plan.get("question") or result.get("allowance") != ALLOWANCE
            or result.get("origin") != plan["outbound_origin"] or result.get("model_runs") != []
            or type(result.get("actual_cost_usd")) not in (int, float) or result.get("actual_cost_usd") != 0):
        raise WorkflowError("The producer result does not match the frozen context and zero-paid-model allowance.", 502)
    known_case = (ops.get(op_id).get("result_ref") or {}).get("case_id")
    if known_case and result.get("case_id") != known_case:
        raise WorkflowError("The producer result names another case; its bytes are kept.", 502)
    dep = result.get("deposition")
    custody = None
    if isinstance(dep, dict):
        if (dep.get("object") or {}).get("id") != result.get("case_id"):
            raise WorkflowError("The case export names another case; its bytes are kept.", 502)
        supplied = result.get("deposition_json")
        if not isinstance(supplied, str):
            raise WorkflowError("The producer did not supply the original case-export bytes.", 502)
        raw = supplied.encode("utf-8")
        if json.loads(raw) != dep:
            raise WorkflowError("The original case-export bytes differ from the result's source package.", 502)
        _keep(op_id, "deposition.json", raw)
        with vault.corpus_write():
            vault.mark_dirty()
            custody = federation.import_package(c, raw, how="open_case_investigation", object_id_hint=str(result.get("case_id") or ""))
    semantic_keys = ("evidence_kind", "evidence_label", "semantics_version", "kind_note", "semantic_record", "source_identity")
    if any(any(k in f for k in semantic_keys) for f in result.get("findings", [])):
        if not custody or not (custody.get("verification") or {}).get("ok"):
            raise WorkflowError("The new evidence identities need a source package verified against the pinned key.", 409)
        signed = {str(e.get("id")): e for e in (dep.get("payload") or {}).get("evidence", [])}
        for finding in result.get("findings", []):
            sealed = signed.get(str(finding.get("id"))) or {}
            meta = sealed.get("producer_semantics") or {}
            if not meta or {k: finding[k] for k in semantic_keys if k in finding} != {k: meta[k] for k in semantic_keys if k in meta}:
                raise WorkflowError("The source semantics differ from the signed evidence package.", 409)
            for key in ("id", "title", "body", "source_url", "source_name", "is_absence", "entry_type", "epistemic_level", "classification_basis", "source_type"):
                actual = (finding.get(key) or "") if key in ("source_url", "source_name") else finding.get(key)
                if key in sealed and actual != sealed[key]:
                    raise WorkflowError("The source text or classification differs from the signed evidence package.", 409)
    ref = dict(ops.get(op_id).get("result_ref") or {})
    ref.update({"artifact": kept, "result_artifact": kept, "case_id": result.get("case_id"), "custody": custody, "upstream_status": status})
    enabled = plan.get("synthesis", {}).get("enabled")
    _mark(op_id, "running" if enabled else ("complete" if status in ("completed", "partial") else "failed"),
             local_state={"completed": "Findings and sources saved locally", "partial": "Partial investigation saved; review source failures and coverage",
                          "failed": "Investigation failed; the failure record is saved locally", "interrupted": "Investigation interrupted; the available record is saved locally"}[status],
             last_error="" if status in ("completed", "partial") else "; ".join(str(f) for f in result.get("failures", []))[:500], result_ref=ref)
    import operation_costs
    operation_costs.reconcile(ops.get(op_id))
    if enabled:
        synthesis.run(op_id)


def artifact(op, name):
    if not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", name) or name in (".", ".."):
        raise WorkflowError("Invalid artifact name.", 404)
    kept = next((k for k in (op.get("result_ref") or {}).get("kept", []) if k.get("name") == name), None)
    if not kept:
        raise WorkflowError("No such artifact was recorded for this investigation.", 404)
    raw = producers.artifact_bytes(op["op_id"], name)
    if hashlib.sha256(raw).hexdigest() != kept.get("sha256"):
        raise WorkflowError("The saved artifact no longer matches its recorded hash.", 409)
    return raw


def view(op):
    if not is_ours(op):
        raise WorkflowError("No Open Case investigation with that id.", 404)
    plan = (op.get("execution") or {}).get("plan") or {}
    ref = op.get("result_ref") or {}
    result = None
    error = op.get("last_error")
    name = (ref.get("result_artifact") or {}).get("name")
    if name:
        try:
            result = json.loads(artifact(op, name))
        except (WorkflowError, ValueError) as e:
            error = str(e)
    events = ops.events(op["op_id"], limit=-1)
    import evidence_lineage
    import operation_costs
    findings = findings_for(op, result) if result else []
    dimensions = result_dimensions(op, result)
    saves = [e for e in events if e["kind"] == "note" and e.get("detail", {}).get("saved")]
    return {"operation_id": op["op_id"], "action_id": ACTION, "kind": "investigation", "producer": "open_case",
        "status": op["status"], "progress": op.get("local_state"), "error": error,
        "created_at": op["created_at"], "updated_at": op["updated_at"], "finished_at": op.get("finished_at"),
        "prepared_id": op.get("prepared_id"), "snapshot_id": op.get("snapshot_id"), "plan": plan,
        "question": plan.get("question"), "origin": plan.get("origin"), "follow_up_of": plan.get("follow_up_of"),
        "result": result, "result_ref": ref, "producer_state": op.get("producer_state"), "events": events,
        "synthesis": synthesis.view(op), "dimensions": dimensions,
        "findings": findings, "evidence_groups": evidence_lineage.group(findings),
        "record_chronology": opencase_grounding.build_record_chronology(plan, findings, operation_id=op['op_id'], result_artifact=ref.get('result_artifact')),
        "costs": operation_costs.total(op), "thread_costs": operation_costs.total(op, ancestry=True),
        "custody": ref.get("custody"), "deposition_id": (ref.get("custody") or {}).get("deposition_id"),
        "saved": bool(saves), "saved_at": saves[-1]["at"] if saves else None, "autosaved": True,
        "artifacts": [{**k, "url": f"/api/open-case/operations/{op['op_id']}/artifacts/{k['name']}"} for k in ref.get("kept", [])],
        "investigation": {"start": "ok" if ref.get("upstream_id") else "not confirmed", "upstream_id": ref.get("upstream_id"),
                          "artifact_summary": "Findings and sources saved locally" if result else "Awaiting results", "kept": ref.get("kept", [])}}


def list_views():
    return [view(op) for op in ops.list_ops(limit=200, kind="investigation")["operations"] if is_ours(op)]


def save(op):
    if not is_ours(op):
        raise WorkflowError("No Open Case investigation with that id.", 404)
    # The authenticated mutating route already holds the corpus write guard.
    ops.event(op["op_id"], "note", detail={"saved": True, "by": "owner"})
    return view(ops.get(op["op_id"]))


def recover(op):
    if not is_ours(op):
        raise WorkflowError("No Open Case investigation with that id.", 404)
    if (op.get("result_ref") or {}).get("result_artifact"):
        if synthesis.needs_resume(op):
            launch(op["op_id"], resume=True)
        return view(op)
    if not (op.get("result_ref") or {}).get("upstream_id"):
        raise WorkflowError("No upstream job id was recorded. An uncertain Start is never repeated; prepare a new investigation explicitly.", 409)
    launch(op["op_id"], resume=True)
    return view(ops.get(op["op_id"]))


def resume_known():
    resumed = []
    for op in ops.list_ops(limit=200, kind="investigation")["operations"]:
        ref = op.get("result_ref") or {}
        same_store = (op.get("config") or {}).get("state_root") == str(cli.LOCAL_STATE.resolve())
        pending = not ref.get("result_artifact") or synthesis.needs_resume(op)
        if is_ours(op) and same_store and (ref.get("upstream_id") or ((op.get("execution") or {}).get("plan", {}).get("reuse_evidence_from"))) and pending and op["status"] in ("running", "claimed", "unknown"):
            if launch(op["op_id"], resume=True):
                resumed.append(op["op_id"])
    return resumed


def _verified_correction(op, envelope, result):
    """Verify the correction against pinned authority and exact original record."""
    if envelope.get('schema') != 'open_case.investigation.correction.v1':
        raise WorkflowError('Unsupported evidence correction.', 409)
    payload, sig = envelope.get('payload') or {}, envelope.get('signature') or {}
    digest = federation.payload_sha256(payload)
    c = connector(((op.get('execution') or {}).get('plan', {}).get('connector') or {}).get('connector_id'))
    pinned = next((k for k in (c or {}).get('trusted_keys', []) if k.get('key_id') == sig.get('trusted_key_id')), None)
    try:
        valid = (sig.get('algorithm') == 'Ed25519' and sig.get('canonicalization') == 'RFC8785'
                 and sig.get('signed_bytes') == 'utf8(hex(sha256(jcs(payload))))'
                 and digest == envelope.get('payload_sha256') and pinned
                 and federation.verify_ed25519(base64.b64decode(pinned['public_key_b64'], validate=True),
                     digest.encode('utf-8'), base64.b64decode(sig['value'], validate=True)))
    except (ValueError, KeyError):
        valid = False
    if not valid:
        raise WorkflowError('The evidence correction does not verify against the pinned Open Case key.', 409)
    if (envelope.get('job_id') != result.get('job_id') or payload.get('job_id') != result.get('job_id')
            or payload.get('original_result_sha256') != federation.payload_sha256(result)
            or payload.get('original_deposition_payload_sha256') != (result.get('deposition') or {}).get('payload_sha256')):
        raise WorkflowError('The correction does not refer to these exact original source records.', 409)
    originals = {str(f.get('id')): f for f in result.get('findings', [])}
    for change in payload.get('evidence', []):
        original = originals.get(str(change.get('evidence_id')))
        if original is None or change.get('original_finding_sha256') != federation.payload_sha256(original):
            raise WorkflowError('The correction names a different original finding.', 409)
    return payload


def findings_for(op, result):
    """Derived view only: never mutate the immutable result or its signed seal."""
    import evidence_lineage
    findings = copy.deepcopy(result.get('findings', []))
    by_id = {str(f.get('id')): f for f in findings}
    for ref in (op.get('result_ref') or {}).get('corrections', []):
        raw = artifact(op, ref['name'])
        if hashlib.sha256(raw).hexdigest() != ref.get('sha256'):
            raise WorkflowError('The correction artifact differs from its recorded hash.', 409)
        envelope = json.loads(raw)
        payload = _verified_correction(op, envelope, result)
        for change in payload.get('evidence', []):
            finding = by_id[str(change['evidence_id'])]
            for key in ('evidence_kind', 'evidence_label', 'semantics_version', 'kind_note', 'semantic_record', 'source_identity'):
                if key in change:
                    finding[key] = change[key]
            finding['correction'] = {'correction_id': envelope['correction_id'], 'payload_sha256': envelope['payload_sha256'],
                                     'original_finding_sha256': change['original_finding_sha256'], 'basis': change.get('correction_basis')}
    for index, finding in enumerate(findings):
        finding['lineage'] = evidence_lineage.for_finding(finding, capture_id=op['op_id'])
        finding['lineage']['capture_sha256'] = hashlib.sha256(json.dumps(result['findings'][index], ensure_ascii=False, sort_keys=True, indent=2).encode()).hexdigest()
    return findings


def correct_saved_evidence(op):
    """Explicit migration, one idempotent non-model producer request."""
    if not is_ours(op):
        raise WorkflowError('No Open Case investigation with that id.', 404)
    ref = op.get('result_ref') or {}
    if not ref.get('upstream_id') or not ref.get('result_artifact'):
        raise WorkflowError('A saved producer result is required for evidence corrections.', 409)
    result = json.loads(artifact(op, ref['result_artifact']['name']))
    c = connector(((op.get('execution') or {}).get('plan', {}).get('connector') or {}).get('connector_id'))
    stage = 'open_case.evidence_correction'
    _event(op['op_id'], 'stage_intent', stage=stage, detail={'upstream_id':ref['upstream_id'], 'billable':False})
    response = producers._request(c, 'POST', '/api/v1/investigations/' + _job_id(ref['upstream_id']) + '/corrections', {}, auth='bearer')
    raw = response.get('raw')
    kept = _keep(op['op_id'], 'correction-' + hashlib.sha256(raw).hexdigest()[:24] + '.json', raw) if raw else None
    _event(op['op_id'], 'stage_end', stage=stage, outcome='received' if response.get('ok') else 'error',
           detail={'artifact':kept,'delivery':response.get('delivery'),'http_status':response.get('status')})
    if not response.get('ok') or not kept:
        raise WorkflowError('The producer correction could not be retrieved; saved originals are unchanged.', 502)
    envelope = response.get('json') or {}
    try:
        _verified_correction(op, envelope, result)
    except WorkflowError as exc:
        _event(op['op_id'], 'note', detail={'correction_rejected':str(exc),'artifact':kept})
        raise
    updated = dict(ops.get(op['op_id']).get('result_ref') or {})
    corrections = list(updated.get('corrections') or [])
    if not any(c['sha256'] == kept['sha256'] for c in corrections):
        corrections.append(kept)
        updated['corrections'] = corrections
        _mark(op['op_id'], result_ref=updated, event_kind='note', detail={'evidence_correction': kept, 'originals_preserved': True})
    return kept


def result_dimensions(op, result):
    plan = (op.get('execution') or {}).get('plan') or {}
    ref = op.get('result_ref') or {}
    syn = synthesis.view(op)
    acquisition = copy.deepcopy((result or {}).get('dimensions', {}).get('acquisition') or {})
    if not acquisition:
        acquisition = {'status': 'legacy_unassessed' if result else 'pending', 'required_ready': None,
                       'reason': 'This older proposal did not declare required and optional sources; its original status is preserved.'}
    answer_status = syn.get('answer_status') or ('legacy_unassessed' if syn.get('answer') else 'not_generated')
    if syn.get('status') in ('failed', 'rejected', 'truncated', 'unknown'):
        answer_status = 'held'
    completed = bool(acquisition.get('required_ready') and acquisition.get('status') == 'ready'
                     and syn.get('status') == 'complete' and answer_status == 'answered')
    label = ('Completed' if completed else 'Answer held' if answer_status == 'held' else
             'Answer partially supported' if answer_status == 'partial' else 'More evidence needed' if answer_status == 'insufficient' else
             'Answer saved · adequacy unassessed' if answer_status == 'legacy_unassessed' else
             'Sources saved · no answer generated' if result and not plan.get('synthesis', {}).get('enabled') else
             'Investigation in progress' if op.get('status') in ('running', 'claimed', 'reserved') else 'Needs review')
    return {'lifecycle': op.get('status'), 'acquisition': acquisition,
            'answer': {'status': answer_status, 'hold': syn.get('hold_reason'), 'adequacy': syn.get('adequacy_reason'), 'adequacy_basis': syn.get('adequacy_basis'),
                       'support_verification': syn.get('support_verification')},
            'completed': completed, 'display_status': label}
