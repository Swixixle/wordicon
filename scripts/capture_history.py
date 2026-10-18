"""Read-only reconstruction from explicit local capture references.

No schema initialization, reconciliation, network, model, or live-store write.
Bodies stay behind authenticated source links. Missing references are gaps,
never inferred from titles, URLs, nearby timestamps, or matching wording.
"""
from __future__ import annotations

from contextlib import contextmanager
import copy
import hashlib
import json
from pathlib import Path
import re
import sqlite3
from urllib.parse import quote

import wordicon_cli as cli

SCHEMA = "nikodemus.capture_history.v1"
ID = re.compile(r"^[A-Za-z0-9_-]{1,100}$")
NAME = re.compile(r"^[A-Za-z0-9_.-]{1,100}$")
MAX_SCAN = 10000
KINDS = ("documents", "revisions", "snapshots", "proposals", "operations", "attempts", "artifacts", "evidence", "answers", "attention", "source_checks")
ATTEMPT_FIELDS = ("call_id", "attempt_id", "provider", "model", "provider_model", "provider_run_id", "stop_reason", "usage_categories", "usage_complete", "response_observed", "stream_complete", "exception", "message", "sdk", "intent_seq", "duration_s", "capture")


class HistoryError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _sha(raw):
    return hashlib.sha256(raw if isinstance(raw, bytes) else raw.encode("utf-8")).hexdigest()


def _digest(obj):
    return _sha(json.dumps(obj, ensure_ascii=False, sort_keys=True, separators=(",", ":")))


def _mapping(value):
    return value if isinstance(value, dict) else {}


def _list(value):
    return value if isinstance(value, list) else []


def _message(value):
    return cli.sanitize_attempt_message(str(value or ""))[:1000]


def _capture_gap_metadata(value):
    """A recovery status is metadata, never a place for a lost body/error dump."""
    value = _mapping(value)
    clean = {key: value[key] for key in ("kept", "durable") if type(value.get(key)) is bool}
    for key in ("why", "kind", "gap_id", "error_class"):
        if isinstance(value.get(key), str):
            clean[key] = _message(value[key])[:200]
    if isinstance(value.get("capture_gap"), dict):
        clean["capture_gap"] = {k: v for k, v in _capture_gap_metadata({k: v for k, v in value["capture_gap"].items() if k != "capture_gap"}).items()}
    return clean


@contextmanager
def _db(root, name):
    path = root / name
    conn = None
    if path.is_file():
        if not path.resolve().is_relative_to(root.resolve()):
            raise HistoryError("A saved database resolves outside this workspace store.", 409)
        conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA query_only=ON")
    try:
        yield conn
    finally:
        if conn:
            conn.close()


def _decode(row):
    item = dict(row)
    for key in ("execution", "config", "producer_state", "result_ref", "detail"):
        if isinstance(item.get(key), str):
            try:
                item[key] = json.loads(item[key])
            except ValueError:
                item[key] = {"capture_parse_error": True}
    return item


def _load_operation(root, operation_id):
    with _db(root, "operations.sqlite3") as db:
        return _decode(row) if db and (row := db.execute("SELECT * FROM operations WHERE op_id=?", (operation_id,)).fetchone()) else None


def _events(root, operation_id):
    with _db(root, "operations.sqlite3") as db:
        return [_decode(r) for r in db.execute("SELECT * FROM operation_events WHERE op_id=? ORDER BY seq LIMIT ?", (operation_id, MAX_SCAN + 1))] if db else []


def _artifact_refs(op, events):
    refs = [r for r in _list(_mapping(op.get("result_ref")).get("kept")) if isinstance(r, dict)]
    for event in events:
        capture = _mapping(_mapping(event.get("detail")).get("capture"))
        if capture.get("schema") == "nikodemus.operation-capture.v1":
            refs += [capture[key] for key in ("artifact", "request_artifact") if isinstance(capture.get(key), dict)]
    return refs


def _read_artifact(root, operation_id, ref):
    name = ref.get("name")
    if not isinstance(name, str) or not NAME.fullmatch(name) or name in (".", ".."):
        raise HistoryError("A recorded artifact name is invalid.", 409)
    path = root / "operation_artifacts" / operation_id / name
    if not path.resolve().is_relative_to(root.resolve()):
        raise HistoryError("A saved artifact resolves outside this workspace store.", 409)
    try:
        raw = path.read_bytes()
    except OSError as exc:
        raise HistoryError("A recorded artifact is unavailable.", 409) from exc
    if _sha(raw) != ref.get("sha256") or (ref.get("bytes") is not None and len(raw) != ref["bytes"]):
        raise HistoryError("A saved artifact differs from its recorded bytes.", 409)
    return raw


def artifact(operation_id, name):
    """Paired route may return these exact bytes; arbitrary paths are refused."""
    if not isinstance(operation_id, str) or not ID.fullmatch(operation_id):
        raise HistoryError("Invalid operation identity.")
    root = Path(cli.LOCAL_STATE)
    op = _load_operation(root, operation_id)
    if not op:
        raise HistoryError("No such saved operation.", 404)
    refs = [r for r in _artifact_refs(op, _events(root, operation_id)) if r.get("name") == name]
    if not refs:
        raise HistoryError("No such artifact reference was recorded.", 404)
    if len({r.get("sha256") for r in refs}) != 1:
        raise HistoryError("Conflicting artifact references require review.", 409)
    return _read_artifact(root, operation_id, refs[0])


class _History:
    def __init__(self, root, kind, identity, limit):
        self.root, self.kind, self.identity, self.limit = root, kind, identity, limit
        self.nodes = {key: {} for key in KINDS}
        self.links, self.gaps, self.snaps, self.props, self.documents = [], [], {}, {}, set()
        self.seen_links = set()

    def gap(self, kind, identity, reason):
        gap = {"kind": kind, "record_id": identity, "reason": reason}
        if gap not in self.gaps:
            self.gaps.append(gap)

    def node(self, category, identity, **values):
        self.nodes[category][identity] = {"id": identity, **values}
        return identity

    def link(self, source, target, relation, basis):
        key = source, target, relation, basis
        if key not in self.seen_links:
            self.links.append({"from": source, "to": target, "relation": relation, "basis": basis})
            self.seen_links.add(key)

    def json_file(self, folder, identity):
        if not isinstance(identity, str) or not ID.fullmatch(identity):
            self.gap("invalid_reference", str(identity)[:100], "Saved reference is not a supported local identity.")
            return None
        path = self.root / folder / (identity + ".json")
        try:
            if not path.resolve().is_relative_to(self.root.resolve()):
                raise ValueError("outside store")
            raw = path.read_bytes()
            record = json.loads(raw)
            if not isinstance(record, dict):
                raise ValueError("not an object")
            return record, _sha(raw)
        except (OSError, ValueError, UnicodeError):
            self.gap("missing_or_invalid_" + folder, identity, "The recorded local file is unavailable or unreadable; no substitute was used.")
            return None

    def snapshot(self, sid):
        if sid in self.snaps:
            return self.snaps[sid]
        loaded = self.json_file("snapshots", sid)
        if not loaded:
            return None
        record, digest = loaded
        canonical = {k: v for k, v in record.items() if k not in ("snapshot_id", "created_at")}
        valid = record.get("snapshot_id") == sid == "snap_" + _digest(canonical)[:24] and isinstance(record.get("text"), str) and record.get("text_sha256") == _sha(record["text"])
        self.node("snapshots", sid, snapshot_id=sid, verification="verified" if valid else "mismatch", file_sha256=digest,
                  kind=record.get("kind"), doc_id=record.get("doc_id"), revision=record.get("revision"), range=record.get("range"),
                  text_sha256=record.get("text_sha256"), chars=record.get("chars"), created_at=record.get("created_at"), url="/api/snapshots/" + quote(sid))
        if not valid:
            self.gap("snapshot_integrity", sid, "Snapshot content address or text hash does not verify; captured text is withheld.")
            return None
        self.snaps[sid] = record
        if record.get("doc_id"):
            did, revision = record["doc_id"], record.get("revision")
            self.document(did, revisions=[revision] if type(revision) is int else [])
            rid = f"revision:{did}:{revision}"
            if rid in self.nodes["revisions"]:
                body = self._revision_body(did, revision)
                try:
                    from_body = body
                    if record.get("kind") == "selection":
                        rng = _mapping(record.get("range")); start, end = rng.get("start"), rng.get("end")
                        if type(start) is not int or type(end) is not int or not 0 <= start <= end:
                            raise ValueError("invalid range")
                        if rng.get("units") == "codepoint" and end <= len(body):
                            from_body = body[start:end]
                        elif rng.get("units") == "utf16" and end * 2 <= len(body.encode("utf-16-le")):
                            from_body = body.encode("utf-16-le")[start * 2:end * 2].decode("utf-16-le")
                        else:
                            raise ValueError("unsupported range")
                    matches = from_body == record["text"]
                except (TypeError, ValueError, UnicodeError):
                    matches = False
                self.nodes["snapshots"][sid]["committed_revision_match"] = matches
                self.link(rid, sid, "captured_as", "saved doc_id/revision/range; exact text " + ("matches" if matches else "does not match"))
                if not matches:
                    self.gap("revision_capture_mismatch", sid, "The frozen input does not match the referenced committed revision/range; both records remain separate.")
        return record

    def proposal(self, pid):
        if pid in self.props:
            return self.props[pid]
        loaded = self.json_file("proposals", pid)
        if not loaded:
            return None
        record, digest = loaded
        valid = record.get("prepared_id") == pid == "prep_" + _sha(json.dumps({**record, "prepared_id": ""}, ensure_ascii=False, sort_keys=True))[:20]
        self.node("proposals", pid, prepared_id=pid, action_id=record.get("action_id"), prepared_at=record.get("prepared_at"),
                  snapshot_id=record.get("snapshot_id"), verification="verified" if valid else "mismatch", file_sha256=digest,
                  status="prepared", dispatch="No dispatch is inferred from a proposal.")
        if not valid:
            self.gap("proposal_integrity", pid, "Proposal no longer matches its content address; no execution is inferred.")
            return None
        self.props[pid] = record
        if record.get("snapshot_id"):
            self.snapshot(record["snapshot_id"])
            self.link(record["snapshot_id"], pid, "proposed_on", "proposal.snapshot_id")
        return record

    def _revision_body(self, did, revision):
        with _db(self.root, "notebook.sqlite3") as db:
            row = db.execute("SELECT b.body FROM revisions r JOIN revision_bodies b ON b.fingerprint=r.fingerprint WHERE r.doc_id=? AND r.revision=?", (did, revision)).fetchone() if db else None
        return row[0] if row else None

    def document(self, did, revisions=(), all_revisions=False):
        if not isinstance(did, str) or not ID.fullmatch(did):
            self.gap("invalid_document", str(did)[:100], "Document reference is invalid.")
            return
        with _db(self.root, "notebook.sqlite3") as db:
            head = db.execute("SELECT doc_id,title,revision,fingerprint,saved_at FROM documents WHERE doc_id=?", (did,)).fetchone() if db else None
            if head:
                self.node("documents", did, **dict(head), url="/work?doc=" + quote(did))
                self.documents.add(did)
            else:
                self.gap("missing_document", did, "The referenced document head is unavailable.")
            query = "SELECT r.revision,r.fingerprint,r.saved_at,b.body,b.doc_json,b.chars FROM revisions r LEFT JOIN revision_bodies b ON b.fingerprint=r.fingerprint WHERE r.doc_id=?"
            args = [did]
            if not all_revisions:
                revisions = [r for r in revisions if type(r) is int]
                if not revisions:
                    return
                query += " AND r.revision IN (" + ",".join("?" for _ in revisions) + ")"; args += revisions
            rows = list(db.execute(query + " ORDER BY r.revision LIMIT ?", (*args, self.limit + 1))) if db else []
        if len(rows) > self.limit:
            self.gap("revision_limit", did, "Additional revisions exist outside this bounded view.")
        available = set()
        for row in rows[:self.limit]:
            row = dict(row); revision = row["revision"]; available.add(revision)
            rid = f"revision:{did}:{revision}"
            self.node("revisions", rid, doc_id=did, revision=revision, fingerprint=row["fingerprint"], saved_at=row["saved_at"], chars=row["chars"],
                      body_sha256=_sha(row["body"]) if isinstance(row["body"], str) else None,
                      structure_sha256=_sha(row["doc_json"]) if row["doc_json"] is not None else None,
                      status="retained" if isinstance(row["body"], str) else "body_missing",
                      url=f"/api/notebook/documents/{quote(did)}/revisions/{revision}")
            self.link(did, rid, "has_revision", "revisions.doc_id/revision")
            if not isinstance(row["body"], str):
                self.gap("missing_revision_body", rid, "The revision index exists but its content-addressed body is unavailable.")
        for revision in revisions:
            if revision not in available:
                self.gap("unretained_revision", f"revision:{did}:{revision}", "No retained body exists for this explicit revision; recording may have been off or retention may predate capture.")

    def scan_files(self, folder):
        paths = sorted((self.root / folder).glob("*.json"))
        if len(paths) > MAX_SCAN:
            self.gap("scan_limit", folder, "The local file scan was bounded; additional relationships may be absent.")
        for path in paths[:MAX_SCAN]:
            if not path.resolve().is_relative_to(self.root.resolve()):
                continue
            try:
                item = json.loads(path.read_bytes())
                if isinstance(item, dict):
                    yield path.stem, item
            except (OSError, ValueError, UnicodeError):
                continue  # unrelated malformed files cannot be assigned to this trace

    def collect_operation(self, op):
        oid = op["op_id"]; plan = _mapping(_mapping(op.get("execution")).get("plan")); ref = _mapping(op.get("result_ref"))
        execution = _mapping(op.get("execution"))
        self.node("operations", oid, operation_id=oid, action_id=op.get("action_id"), kind=op.get("kind"), status=op.get("status"),
                  question=plan.get("question"), created_at=op.get("created_at"), finished_at=op.get("finished_at"),
                  error=_message(op.get("last_error")), url=("/investigation?operation=" if op.get("action_id") == "investigate.opencase.question" else "/deflate-reading?operation=" if op.get("action_id") == "investigate.deflate.read" else "/api/operations/") + quote(oid))
        for key, method, relation in (("prepared_id", self.proposal, "started_from"), ("snapshot_id", self.snapshot, "captured_input")):
            identity = op.get(key) or execution.get(key)
            if identity:
                method(identity); self.link(identity, oid, relation, "operation." + key)
        origin = _mapping(plan.get("origin"))
        if origin.get("doc_id"):
            self.document(origin["doc_id"], revisions=[origin.get("revision")])
            target = f"revision:{origin['doc_id']}:{origin['revision']}" if type(origin.get("revision")) is int else origin["doc_id"]
            self.link(target, oid, "originated_from", "plan.origin explicit document/revision")
        events = _events(self.root, oid)
        if len(events) > MAX_SCAN:
            self.gap("event_limit", oid, "Additional operation events exist outside this bounded view.")
        events = events[:MAX_SCAN]
        artifacts = {}
        for kept in _artifact_refs(op, events):
            aid = "artifact:" + oid + ":" + str(kept.get("name"))
            if aid in self.nodes["artifacts"]:
                if self.nodes["artifacts"][aid]["sha256"] != kept.get("sha256"):
                    self.nodes["artifacts"][aid]["verification"] = "conflicting_references"
                    artifacts.pop(kept.get("name"), None)
                    self.gap("artifact_reference_conflict", aid, "Recorded references disagree about this artifact's exact hash.")
                continue
            item = {k: kept.get(k) for k in ("name", "sha256", "bytes")}
            try:
                raw = _read_artifact(self.root, oid, kept); artifacts[kept["name"]] = raw
                item["verification"] = "verified"
            except HistoryError as exc:
                item["verification"] = "unavailable_or_mismatch"; self.gap("artifact_integrity", aid, str(exc))
            self.node("artifacts", aid, operation_id=oid, **item, url=f"/api/capture/operations/{quote(oid)}/artifacts/{quote(str(kept.get('name')))}")
            self.link(oid, aid, "retained_artifact", "recorded kept/capture reference")
        # A completed immutable file can survive a crash before its event note.
        # Report the self-linked recovery record without repairing the journal
        # or promoting its body to evidence/answer output.
        try:
            directory = self.root / "operation_artifacts" / oid
            if not directory.resolve().is_relative_to(self.root.resolve()):
                raise ValueError("capture directory outside store")
            import operation_capture
            recovered = operation_capture.inspect(oid)
            for item in _list(recovered.get("records")):
                if item.get("linked"):
                    continue
                kept, record = _mapping(item.get("artifact")), _mapping(item.get("record"))
                aid = "artifact:" + oid + ":" + str(kept.get("name"))
                self.node("artifacts", aid, operation_id=oid, **{k: kept.get(k) for k in ("name", "sha256", "bytes")},
                          verification="verified_unindexed", linked=False, phase=record.get("phase"),
                          call_id=record.get("call_id"), attempt_id=record.get("attempt_id"),
                          recovery="Exact hash-named artifact survived without its operation note; no journal repair or output substitution was performed.")
                self.link(oid, aid, "unindexed_capture", "verified artifact.links.operation_id; operation event reference missing")
            for item in _list(recovered.get("gaps")):
                name = str(item.get("name") or "")[:100]
                self.gap("gateway_" + str(item.get("kind") or "capture_gap"), "artifact:" + oid + ":" + name,
                         "A gateway capture file or its journal reference needs review; exact retained files were not repaired or replayed.")
        except (ValueError, OSError, sqlite3.Error, TypeError, KeyError):
            self.gap("gateway_capture_inspection", oid, "Gateway recovery artifacts could not be inspected; their absence is not asserted.")
        for event in events:
            detail = _mapping(event.get("detail")); eid = f"event:{oid}:{event['seq']}"
            capture_gap = _capture_gap_metadata(detail.get("capture_gap"))
            if capture_gap:
                supplemental = _mapping(capture_gap.get("capture_gap"))
                reason = "The authoritative operation records a capture failure."
                if supplemental.get("durable") is False:
                    reason += " Its supplemental gap record was not confirmed durable; this saved operation note preserves the failure status."
                self.gap("operation_capture_failure", eid, reason)
            if event.get("kind") in ("stage_intent", "stage_end", "attempt_intent", "attempt_end", "failed", "unknown") or detail.get("capture") or capture_gap:
                safe = {k: copy.deepcopy(detail[k]) for k in ATTEMPT_FIELDS if k in detail}
                if capture_gap:
                    safe["capture_gap"] = capture_gap
                if "message" in safe:
                    safe["message"] = _message(safe["message"])
                if "capture" in safe:
                    capture = _mapping(safe["capture"])
                    safe["capture"] = {k: capture[k] for k in ("schema", "phase", "call_id", "attempt_id", "gap_id", "durable", "status") if k in capture}
                    for key in ("artifact", "request_artifact"):
                        if isinstance(capture.get(key), dict):
                            safe["capture"][key] = {k: capture[key].get(k) for k in ("name", "sha256", "bytes")}
                self.node("attempts", eid, operation_id=oid, seq=event["seq"], at=event.get("at"), kind=event.get("kind"),
                          stage=event.get("stage"), outcome=event.get("outcome"), attempt=event.get("attempt"), detail=safe,
                          record_sha256=_digest(event), identity_status="explicit_attempt_id" if detail.get("attempt_id") else "event_only_no_attempt_identity")
                self.link(oid, eid, "recorded_attempt_event", "operation_events.op_id/seq")
                capture = _mapping(detail.get("capture"))
                for key in ("artifact", "request_artifact"):
                    if isinstance(capture.get(key), dict):
                        self.link(eid, "artifact:" + oid + ":" + str(capture[key].get("name")), "captured_" + key, "event.detail.capture." + key)
                if capture.get("schema") == "nikodemus.operation-capture.v1" and capture.get("phase") in ("response", "failure"):
                    kept = _mapping(capture.get("artifact")); name = kept.get("name")
                    answer_id = "captured-output:" + oid + ":" + str(event["seq"])
                    self.node("answers", answer_id, operation_id=oid, call_id=capture.get("call_id"), attempt_id=capture.get("attempt_id"),
                              kind="captured_provider_output", phase=capture["phase"],
                              current_status="captured" if name in artifacts else "capture_unavailable", receipt_verified=name in artifacts,
                              answer_available=False, source_refs=[kept],
                              interpretation_support="Captured provider output is not automatically a completed or supported answer.")
                    self.link(eid, answer_id, "captured_output", "event.detail.capture.phase")
                    if name:
                        self.link(answer_id, "artifact:" + oid + ":" + name, "retained_as", "event.detail.capture.artifact")
        try:
            import operation_costs
            self.nodes["operations"][oid]["costs"] = operation_costs.total(op)
        except (ValueError, OSError, sqlite3.Error, KeyError, TypeError):
            self.nodes["operations"][oid]["costs"] = {"accounting_status": "unknown", "actual_cost_usd": None}
            self.gap("accounting_unavailable", oid, "Saved accounting could not be reconstructed; missing amounts are not zero.")
        result_ref = _mapping(ref.get("result_artifact"))
        result = None
        if result_ref.get("name") in artifacts:
            raw = artifacts[result_ref["name"]]
            if _sha(raw) != result_ref.get("sha256"):
                self.gap("result_reference_mismatch", oid, "The result pointer and retained artifact disagree about the exact bytes; evidence is withheld.")
            else:
                try:
                    result = json.loads(raw)
                except (ValueError, UnicodeError):
                    self.gap("result_parse", oid, "The exact result bytes are retained but are not readable JSON.")
        elif result_ref:
            self.gap("result_artifact_unavailable", oid, "The saved result pointer does not resolve to a verified retained artifact.")
        if op.get("action_id") == "investigate.deflate.read":
            self.collect_deflate(op, result, artifacts)
        if isinstance(result, dict):
            findings = _list(result.get("findings"))
            if ref.get("corrections"):
                try:
                    import opencase
                    findings = opencase.findings_for(op, result)
                except (ValueError, OSError, KeyError, TypeError):
                    self.gap("correction_verification", oid, "The linked correction did not verify; the original source records remain referenced and no replacement semantics are asserted.")
                    findings = _list(result.get("findings"))
            for index, finding in enumerate(findings[:200]):
                if not isinstance(finding, dict):
                    continue
                fid = str(finding.get("id") or "index-" + str(index)); record_id = oid + ":" + fid
                self.node("evidence", record_id, operation_id=oid, finding_id=fid, evidence_kind=finding.get("evidence_kind"),
                          title=finding.get("title"), source_url=finding.get("source_url"), source_name=finding.get("source_name"),
                          source_identity=finding.get("source_identity"), correction=finding.get("correction"),
                          is_absence=finding.get("is_absence"), body_sha256=_sha(str(finding.get("body") or "")),
                          derived_record_sha256=_digest(finding), source_pointer="/findings/" + str(index),
                          result_artifact_sha256=result_ref.get("sha256"), artifact_id="artifact:" + oid + ":" + result_ref["name"])
                self.link("artifact:" + oid + ":" + result_ref["name"], record_id, "contains_record", "saved result /findings/" + str(index))
            if len(findings) > 200:
                self.gap("evidence_limit", oid, "Additional source records remain in the linked complete result artifact.")
            for field in ("source_statuses", "source_checks", "failures"):
                values = result.get(field)
                values = list(values.items()) if isinstance(values, dict) else list(enumerate(_list(values)))
                for key, value in values[:200]:
                    sid = f"source-check:{oid}:{field}:{key}"; item = _mapping(value)
                    self.node("source_checks", sid, operation_id=oid, kind=field, source=item.get("display_name") or item.get("source_name") or item.get("source") or item.get("adapter") or str(key),
                              status=item.get("status") or (str(value) if not item else None),
                              reason=_message(item.get("message") or item.get("error") or item.get("detail") or item.get("reason")),
                              original_record_sha256=_digest(value), source_pointer="/" + field + "/" + str(key).replace("~", "~0").replace("/", "~1"),
                              artifact_id="artifact:" + oid + ":" + result_ref["name"])
                    self.link(oid, sid, "recorded_source_outcome", "saved result." + field)
            capabilities = _list(_mapping(_mapping(result.get("dimensions")).get("acquisition")).get("capabilities"))
            for index, item in enumerate(capabilities[:200]):
                if not isinstance(item, dict):
                    continue
                sid = f"source-capability:{oid}:{index}"
                self.node("source_checks", sid, operation_id=oid, kind="declared_source_capability", source=item.get("name") or item.get("id"),
                          role=item.get("role"), status=item.get("availability"), ready=item.get("ready"), reason=_message(item.get("reason")),
                          attempt_inferred=False, original_record_sha256=_digest(item), source_pointer=f"/dimensions/acquisition/capabilities/{index}",
                          artifact_id="artifact:" + oid + ":" + result_ref["name"])
                self.link(oid, sid, "declared_source_capability", "saved acquisition capability; not an attempt event")
        state = _mapping(ref.get("synthesis"))
        if state:
            answer_id = "answer:" + oid
            references = [_mapping(state.get(k)) for k in ("response_artifact", "manifest_artifact", "prompt_artifact") if state.get(k)]
            integrity = bool(references) and all(r.get("name") in artifacts and _sha(artifacts[r["name"]]) == r.get("sha256") for r in references)
            reviews = [dict(_mapping(e["detail"])["answer_review"], recorded_at=e.get("at")) for e in events
                       if _mapping(_mapping(e.get("detail")).get("answer_review")).get("schema") == "nikodemus.open_case.answer_review.v1"
                       and _mapping(e["detail"])["answer_review"].get("response_artifact") == state.get("response_artifact")]
            status = "held" if reviews else state.get("answer_status", state.get("status"))
            self.node("answers", answer_id, operation_id=oid, recorded_status=state.get("status"), current_status=status if integrity else "integrity_unavailable",
                      answer_format=state.get("answer_format"), receipt_verified=integrity, reviews=reviews,
                      answer_available=bool(state.get("answer")) and integrity and not reviews,
                      text_sha256=_sha(str(state.get("answer") or "")),
                      display_url="/investigation?operation=" + quote(oid), source_refs=references,
                      error=_message(state.get("error")), interpretation_support="not_independently_verified")
            self.link(oid, answer_id, "recorded_answer_outcome", "result_ref.synthesis")
            for citation in _list(state.get("citations")):
                if isinstance(citation, dict) and citation.get("record_id"):
                    self.link(answer_id, citation["record_id"], "cites_record", "saved synthesis citation; not an entailment verdict")
            if not integrity and state.get("status") in ("complete", "rejected", "truncated"):
                self.gap("answer_artifact_unavailable", answer_id, "Saved answer metadata exists but its linked artifacts do not all verify; no usable answer is asserted.")

    def collect_deflate(self, op, result, artifacts):
        """Project saved bridge links and signed text, without reopening a producer.

        A source transcript is evidence of the acquired words. Model readings are
        attributed interpretations; neither their gate nor custody answers an
        arbitrary question. Every body remains in its exact protected artifact.
        """
        oid = op["op_id"]; ref = _mapping(op.get("result_ref"))
        plan = _mapping(_mapping(op.get("execution")).get("plan"))
        if not isinstance(result, dict):
            return
        import federation
        frozen = _mapping(plan.get("producer_plan"))
        try:
            valid = (result.get("contract") == "deflate.bridge.v1" and result.get("request_id") == oid
                     and result.get("plan_id") == plan.get("plan_id") and result.get("plan_sha256") == plan.get("plan_sha256")
                     and result.get("plan") == frozen and federation.payload_sha256(frozen) == plan.get("plan_sha256"))
        except (ValueError, TypeError, UnicodeError):
            valid = False
        bid = result.get("bridge_id")
        if not valid or not isinstance(bid, str) or not re.fullmatch(r"b_[a-f0-9]{32}", bid) or ref.get("upstream_id") != bid:
            self.gap("deflate_result_identity", oid, "The retained bridge result does not match this operation and frozen plan; no source or reading is promoted.")
            return
        result_ref = _mapping(ref.get("result_artifact")); result_aid = "artifact:" + oid + ":" + result_ref.get("name", "")
        local_refs = _list(ref.get("kept"))

        def captured(remote, label):
            remote = _mapping(remote); name, digest = remote.get("name"), remote.get("sha256")
            if (not isinstance(name, str) or not NAME.fullmatch(name) or name in (".", "..")
                    or not isinstance(digest, str) or not re.fullmatch(r"[a-f0-9]{64}", digest)
                    or remote.get("path") != f"/api/bridge/jobs/{bid}/artifacts/{name}"):
                self.gap("deflate_capture_reference", oid, "The saved " + label + " reference is missing or invalid; no replacement is inferred.")
                return None
            matches = [r for r in local_refs if isinstance(r, dict) and r.get("sha256") == digest and r.get("name") in artifacts
                       and _sha(artifacts[r["name"]]) == digest and (remote.get("bytes") is None or len(artifacts[r["name"]]) == remote["bytes"])]
            if not matches:
                self.gap("deflate_capture_missing", oid, "The saved " + label + " names exact bytes that are not available in this operation's retained artifacts.")
                return None
            kept = matches[0]
            if remote.get("exact") is False:
                self.gap("deflate_capture_redacted", "artifact:" + oid + ":" + kept["name"], "The producer explicitly redacted this " + label + "; its original unredacted bytes are not claimed to be retained.")
            return kept

        acquisition = _mapping(result.get("acquisition"))
        sid = "source-check:" + oid + ":deflate-acquisition"
        source_ref = captured(acquisition.get("artifact"), "acquisition") if acquisition.get("artifact") else None
        self.node("source_checks", sid, operation_id=oid, kind="acquisition", source="Deflate source acquisition",
                  status=acquisition.get("status") or "unknown", reason=_message(_mapping(acquisition.get("error")).get("message")),
                  original_record_sha256=_digest(acquisition), source_pointer="/acquisition", artifact_id=result_aid,
                  source_artifact=source_ref, result_kind=acquisition.get("result_kind"), attempt_inferred=False)
        self.link(oid, sid, "recorded_source_outcome", "saved bridge acquisition")
        for flag in ("export_gap", "cleanup_gap"):
            if result.get(flag):
                self.gap("deflate_" + flag, oid, _message(result[flag]))
        for label, remote in (("acquisition", acquisition.get("artifact")), ("source page", result.get("source_artifact"))):
            kept = source_ref if label == "acquisition" else captured(remote, label) if remote else None
            if kept:
                self.link(sid, "artifact:" + oid + ":" + kept["name"], "captured_source", "saved bridge " + label + " artifact reference")
        attempts = _list(result.get("attempts")); seen = set()
        for index, attempt in enumerate(attempts[:200]):
            attempt = _mapping(attempt); aid = attempt.get("attempt_id")
            if not isinstance(aid, str) or not re.fullmatch(r"model_[0-9]{3}", aid) or aid in seen:
                self.gap("deflate_attempt_identity", oid, "A producer model attempt has a missing or duplicate identity; separate calls are not inferred.")
                continue
            seen.add(aid); node_id = "deflate-attempt:" + oid + ":" + aid
            detail = {k: _message(attempt[k]) for k in ("provider", "model", "purpose", "producer_call_id") if isinstance(attempt.get(k), str)}
            detail["attempt_id"] = aid
            detail["message"] = _message(_mapping(attempt.get("error")).get("message"))
            self.node("attempts", node_id, operation_id=oid, kind="producer_model_attempt", stage=detail.get("purpose"),
                      at=attempt.get("started_at"), outcome=attempt.get("status") or "unknown", detail=detail,
                      record_sha256=_digest(attempt), source_pointer=f"/attempts/{index}", artifact_id=result_aid,
                      identity_status="explicit_attempt_id", attribution="Producer's saved attempt, not an inferred Nikodemus dispatch")
            self.link(oid, node_id, "recorded_attempt_event", "saved bridge attempt_id")
            self.link(node_id, result_aid, "captured_status", "saved bridge result /attempts/" + str(index))
            for phase in ("request", "response"):
                if not attempt.get(phase):
                    if phase == "request" or attempt.get("status") in ("completed", "failed"):
                        self.gap("deflate_attempt_capture_missing", node_id, "The recorded attempt has no " + phase + " capture reference. Missing response or usage is not a free call.")
                    continue
                kept = captured(attempt[phase], "model " + phase)
                if kept:
                    self.link(node_id, "artifact:" + oid + ":" + kept["name"], "captured_" + phase, "saved bridge attempt." + phase)
        if len(attempts) > 200:
            self.gap("deflate_attempt_limit", oid, "Additional producer attempts remain in the complete retained result.")
        remote = _mapping(result.get("result")); dep = _mapping(ref.get("deposition_artifact"))
        dep_ref = captured(remote.get("deposition"), "signed deposition") if remote.get("deposition") else None
        envelope = None; verified = False
        if dep_ref and dep.get("name") in artifacts and dep.get("sha256") == dep_ref.get("sha256") and _sha(artifacts[dep["name"]]) == dep.get("sha256"):
            try:
                envelope = json.loads(artifacts[dep["name"]])
                connector = federation.get_connector(_mapping(plan.get("connector")).get("connector_id")) or {}
                verified = (connector.get("producer") == "deflate" and _mapping(envelope.get("producer")).get("id") == "deflate"
                            and _mapping(envelope.get("object")).get("id") == result.get("runId") == remote.get("runId")
                            and _mapping(_mapping(ref.get("custody")).get("verification")).get("ok") is True
                            and federation.verify_envelope(envelope, connector.get("trusted_keys", []))["ok"])
            except (ValueError, TypeError, KeyError, OSError, AttributeError):
                verified = False
        answer_id = "answer:" + oid; reading = _mapping(result.get("reading"))
        self.node("answers", answer_id, operation_id=oid, kind="deflate_reading_outcome", current_status=(reading.get("status") or "unknown") if verified else "integrity_unavailable",
                  recorded_status=reading.get("status"), receipt_verified=verified, answer_available=False,
                  display_url="/deflate-reading?operation=" + quote(oid), source_refs=[dep] if dep_ref else [],
                  interpretation_support="Deflate records a reading of source material. Its model and review gates do not establish that the originating question has been answered.")
        self.link(oid, answer_id, "recorded_answer_outcome", "saved bridge reading status")
        if not verified:
            self.gap("deflate_deposition_unverified", oid, "A current pinned-key verification and exact operation-linked deposition are unavailable. Captured attempts remain visible; no signed transcript or reading is promoted.")
            return
        payload = _mapping(envelope.get("payload")); claims = _mapping(payload.get("claims")); run = _mapping(claims.get("run"))
        if payload.get("schema") != "deflate-lens/deposition@1" or claims.get("schema") != "deflate-lens/claims@0.7" or run.get("id") != result.get("runId"):
            self.gap("deflate_payload_schema", oid, "The signed payload schema or run identity is unsupported; exact bytes remain available.")
            self.nodes["answers"][answer_id]["current_status"] = "integrity_unavailable"
            return
        dep_aid = "artifact:" + oid + ":" + dep["name"]; transcript = _mapping(payload.get("transcript")); body = transcript.get("text")
        transcript_valid = (transcript.get("included") is True and isinstance(body, str) and bool(body.strip()) and _sha(body) == transcript.get("sha256")
                            == _mapping(run.get("transcript")).get("sha256") == remote.get("transcript_sha256"))
        source_id = "deflate-transcript:" + oid
        if transcript_valid:
            source = _mapping(run.get("source"))
            self.node("evidence", source_id, operation_id=oid, finding_id=run["id"], title=_message(run.get("title")) or "Captured source transcript",
                      evidence_kind="captured_source_text", source_name=_message(source.get("label")) or "Deflate acquired text", source_url=source.get("url"),
                      source_identity=copy.deepcopy(run.get("sourceIdentity")), body_sha256=transcript["sha256"],
                      derived_record_sha256=_digest(transcript), source_pointer="/payload/transcript", artifact_id=dep_aid,
                      result_artifact_sha256=dep["sha256"], signed_payload_sha256=envelope.get("payload_sha256"),
                      interpretation_support="Exact captured words; transcription and source identity are attributed to Deflate, not independently validated.")
            self.link(dep_aid, source_id, "contains_record", "signed payload /transcript")
            self.link(sid, source_id, "yielded_captured_text", "matching result transcript SHA-256 and signed transcript hash")
        else:
            self.gap("deflate_transcript_integrity", oid, "The signed transcript text and its declared source hashes do not all agree; no source text or usable reading is asserted.")
        held_ids = {p.get("id") for p in _list(claims.get("passagesHeld")) if isinstance(p, dict)}
        passage_counts = {}
        for passage in _list(claims.get("passages")):
            if isinstance(passage, dict):
                pid = str(passage.get("id") or "")
                passage_counts[pid] = passage_counts.get(pid, 0) + 1
        for field in ("passages", "passagesHeld"):
            passages = _list(claims.get(field))
            for index, passage in enumerate(passages[:200]):
                if not isinstance(passage, dict):
                    continue
                pid = str(passage.get("id") or "index-" + str(index)); reading_id = f"deflate-reading:{oid}:{field}:{index}"
                held = field == "passagesHeld" or pid in held_ids or _mapping(passage.get("readingGate")).get("status") == "held"
                ambiguous = field == "passages" and passage_counts.get(str(passage.get("id") or ""), 0) != 1
                text_match = not ambiguous and transcript_valid and _mapping(passage.get("basedOn")).get("inputHash") == transcript.get("sha256")
                prose = _mapping(_mapping(passage.get("reading")).get("deflated")).get("hs")
                has_prose = isinstance(prose, str) and bool(prose.strip())
                status = "held" if held else "identity_ambiguous" if ambiguous else "stale" if passage.get("stale") else ("reading_available" if has_prose else "reading_metadata_only") if text_match and _mapping(passage.get("readingGate")).get("status") == "ready" else "basis_unverified"
                self.node("answers", reading_id, operation_id=oid, kind="deflate_passage_reading", passage_id=pid,
                          current_status=status, receipt_verified=True, reading_available=status == "reading_available", answer_available=False,
                          reading_metadata_available=True,
                          title=_message(passage.get("title")), source_refs=[dep], source_pointer=f"/payload/claims/{field}/{index}",
                          derived_record_sha256=_digest(passage), signed_payload_sha256=envelope.get("payload_sha256"),
                          based_on_text_sha256=_mapping(passage.get("basedOn")).get("inputHash"), transcript_match=bool(text_match),
                          display_url="/deflate-reading?operation=" + quote(oid),
                          interpretation_support="Deflate's model reading, checked by its own gate. A held or stale reading is not a finished answer; gate acceptance is not independent factual validation.")
                self.link(dep_aid, reading_id, "contains_reading", f"signed payload /claims/{field}/{index}")
                if text_match:
                    self.link(reading_id, source_id, "read_from", "signed passage basedOn.inputHash matches retained transcript SHA-256")
            if len(passages) > 200:
                self.gap("deflate_reading_limit", oid, "Additional passage readings remain in the complete signed deposition.")
        for index, gap in enumerate(_list(envelope.get("gaps"))[:200]):
            gap = _mapping(gap); gid = f"source-check:{oid}:deflate-envelope-gap:{index}"
            self.node("source_checks", gid, operation_id=oid, kind="producer_declared_gap", source="Deflate export limitation",
                      status=_message(gap.get("kind")) or "not_recorded", reason=_message(gap.get("detail")),
                      attribution="Producer's envelope metadata; describes Deflate's custody, not whether Nikodemus retained an uploaded original.",
                      source_pointer=f"/gaps/{index}", original_record_sha256=_digest(gap), artifact_id=dep_aid)
            self.link(oid, gid, "recorded_source_outcome", "retained deposition envelope gap; outside signed payload")

    def attention(self):
        known = set(self.nodes["operations"]) | set(self.nodes["documents"]) | set(self.nodes["snapshots"]) | set(self.nodes["proposals"])
        count = 0
        for path in sorted((self.root / "ledger").glob("events-*.jsonl")):
            if not path.resolve().is_relative_to(self.root.resolve()):
                continue
            try:
                stream = path.open("rb")
            except OSError:
                self.gap("unreadable_attention", path.name, "An attention file cannot be read; no missing activity is reconstructed.")
                continue
            with stream:
                for index, raw in enumerate(stream, 1):
                    try:
                        item = json.loads(raw)
                    except (ValueError, UnicodeError):
                        continue
                    if not isinstance(item, dict):
                        continue
                    subject = _mapping(item.get("subject"))
                    if subject.get("id") not in known:
                        continue
                    count += 1
                    if count > 1000:
                        self.gap("attention_limit", "ledger", "More than 1,000 explicitly linked attention records exist; this view is bounded.")
                        return
                    identity = "attention:" + path.name + ":" + str(index)
                    interval = None
                    if item.get("type") == "activity_interval":
                        try:
                            import ledger
                            interval = ledger._interval(item.get("interval"))
                        except (ValueError, TypeError):
                            self.gap("invalid_activity_interval", identity, "The retained activity estimate is invalid; its duration is not inferred.")
                    self.node("attention", identity, event_id=item.get("event_id"), session_id=item.get("session_id"), scope_id=item.get("scope_id"),
                              type=item.get("type"), at=item.get("at"), received_at=item.get("received_at"),
                              interval=interval,
                              subject={k: subject[k] for k in ("id", "kind", "revision", "scope") if k in subject},
                              identity_status="explicit_event_id" if item.get("event_id") else "legacy_unverifiable",
                              file=path.name, line=index, line_sha256=_sha(raw))
                    self.link(identity, subject["id"], "observed_attention", "ledger.subject.id; does not establish reading, agreement or execution")


def view(*, operation_id=None, doc_id=None, prepared_id=None, limit=100):
    roots = [(kind, identity) for kind, identity in (("operation", operation_id), ("document", doc_id), ("proposal", prepared_id)) if identity is not None]
    if len(roots) != 1 or not isinstance(roots[0][1], str) or not ID.fullmatch(roots[0][1]):
        raise HistoryError("Choose exactly one valid operation_id, doc_id, or prepared_id.")
    if type(limit) is not int or not 1 <= limit <= 100:
        raise HistoryError("History limit must be between 1 and 100.")
    root = Path(cli.LOCAL_STATE); kind, identity = roots[0]
    h = _History(root, kind, identity, limit)
    with _db(root, "operations.sqlite3") as db:
        rows = list(db.execute("SELECT * FROM operations ORDER BY created_at,op_id LIMIT ?", (MAX_SCAN + 1,))) if db else []
    if len(rows) > MAX_SCAN:
        h.gap("operation_scan_limit", identity, "Some operations are outside the bounded scan; unobserved relationships are not inferred.")
    operations = {r["op_id"]: _decode(r) for r in rows[:MAX_SCAN]}
    chosen = set()
    if kind == "operation":
        op = _load_operation(root, identity)
        if not op:
            raise HistoryError("No such saved operation.", 404)
        operations[identity] = op; chosen.add(identity)
    elif kind == "document":
        h.document(identity, all_revisions=True)
        if identity not in h.nodes["documents"]:
            raise HistoryError("No such saved document.", 404)
        for sid, rec in h.scan_files("snapshots"):
            if rec.get("doc_id") == identity:
                h.snapshot(sid)
        for pid, rec in h.scan_files("proposals"):
            if rec.get("snapshot_id") in h.snaps:
                h.proposal(pid)
        chosen = {oid for oid, op in operations.items() if op.get("snapshot_id") in h.snaps or op.get("prepared_id") in h.props or
                  _mapping(_mapping(_mapping(op.get("execution")).get("plan")).get("origin")).get("doc_id") == identity}
    else:
        if not h.proposal(identity):
            raise HistoryError("The saved proposal is unavailable or does not verify.", 409)
        chosen = {oid for oid, op in operations.items() if op.get("prepared_id") == identity}
    relationships = []
    for oid, op in operations.items():
        plan = _mapping(_mapping(op.get("execution")).get("plan"))
        for relation, parent, basis in (("follow_up", plan.get("follow_up_of"), "plan.follow_up_of"), ("retry", op.get("retry_parent"), "operation.retry_parent"), ("reuses_evidence", plan.get("reuse_evidence_from"), "plan.reuse_evidence_from")):
            if isinstance(parent, str) and parent:
                relationships.append((parent, oid, relation, basis))
    changed = True
    while changed and len(chosen) < limit:
        previous = set(chosen)
        for parent, child, _, _ in relationships:
            if parent in chosen or child in chosen:
                if parent in operations and len(chosen) < limit:
                    chosen.add(parent)
                if child in operations and len(chosen) < limit:
                    chosen.add(child)
        changed = chosen != previous
    if len(chosen) > limit:
        chosen = set(sorted(chosen, key=lambda oid: (operations[oid].get("created_at") or "", oid))[:limit])
        h.gap("operation_limit", identity, "Additional explicitly linked operations remain outside this bounded view.")
    for parent, child, relation, basis in relationships:
        if parent in chosen or child in chosen:
            h.link(parent, child, relation, basis)
            for missing in (parent, child):
                if missing not in chosen:
                    h.gap("operation_link_unavailable", missing, "An explicit operation relationship is missing locally or outside the selected limit.")
    for oid in sorted(chosen, key=lambda value: (operations[value].get("created_at") or "", value)):
        h.collect_operation(operations[oid])
    h.attention()
    workspace = None
    try:
        import workspace_identity
        workspace = workspace_identity.read()
    except (ImportError, OSError, ValueError):
        pass
    if not workspace:
        h.gap("legacy_workspace_identity", "workspace", "No persistent workspace identity is available; this read did not create one.")
    capture_gaps = {"gaps": [], "read_gaps": [], "truncated": False}
    try:
        import capture
        read = capture.read_gaps()
        known = set().union(*(set(h.nodes[key]) for key in ("operations", "documents", "snapshots", "proposals")))
        capture_gaps = {"gaps": [r for r in _list(read.get("gaps")) if any(v in known for v in _mapping(r.get("references")).values() if isinstance(v, str))],
                        "read_gaps": read.get("read_gaps", []), "truncated": read.get("truncated", False), "enabled": read.get("enabled")}
        for item in capture_gaps["gaps"]:
            h.gap("recorded_capture_failure", item.get("gap_id", "unknown"), "A saved capture failure is linked to this trace; inspect capture_gaps for its recorded class and references.")
    except (AttributeError, OSError, ValueError, TypeError):
        h.gap("capture_gap_reader_unavailable", "capture", "Recorded capture gaps cannot currently be read; their absence is not asserted.")
    data = {"schema": SCHEMA, "root": {"kind": kind, "id": identity}, "workspace": workspace,
            "capture_gaps": capture_gaps,
            "nodes": {key: list(value.values()) for key, value in h.nodes.items()}, "links": h.links, "gaps": h.gaps,
            "limits": {"operations": limit, "operation_scan": MAX_SCAN, "attention": 1000},
            "scope": "Only explicit saved IDs/references related to this root; no title, URL, wording or time-based relationship inference.",
            "limitations": ["Attention records establish observed UI activity, not reading or agreement.",
                "Private source bodies remain behind authenticated local source links.", "Missing capture is not reconstructed from a current document or later model response.",
                "Source labels, citation identity and exact hashes do not independently establish claim support."],
            "side_effects": {"writes": 0, "network": 0, "models": 0}}
    data["projection_sha256"] = _digest(data)
    return data
