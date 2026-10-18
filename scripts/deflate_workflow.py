"""Deflate readings on Nikodemus's proposal, operation and custody spine.

Local views never call the producer. Prepare may ask the bridge to freeze its
configuration, but sends no upload bytes and starts no acquisition or model.
Only the reserved Start stages the chosen upload and launches that plan. A lost
Start is reconciled by GET request identity, never by repeating the POST.
"""
from __future__ import annotations

import copy
import hashlib
import ipaddress
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import threading
import time
from urllib.parse import urlsplit, quote
import urllib.error
import urllib.request

import federation
import operation_capture
import operation_costs as costs
import operations as ops
import producers
import snapshots
import testmode
import vault
import wordicon_cli as cli
import workspace_identity

ACTION = "investigate.deflate.read"
CONTRACT = "deflate.bridge.v1"
MAX_UPLOAD_BYTES = 100 * 1024 * 1024
DEFAULT_ALLOWANCE = 0.50
TERMINAL = {"completed", "partial", "failed", "interrupted", "unknown", "needs_selection"}
_workers, _worker_lock = set(), threading.Lock()


class WorkflowError(ValueError):
    def __init__(self, message, status=400):
        super().__init__(message)
        self.status = status


def _digest(value):
    return hashlib.sha256(json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode()).hexdigest()


def _safe_metadata(value):
    if not operation_capture.sanitize_body(value)["exact"]:
        raise WorkflowError("Remove credentials or session information from the link and file metadata. Browser-session access stays in Deflate's own settings.")
    return value


def _text(value, name, limit, required=False):
    if not isinstance(value, str) or len(value) > limit or (required and not value.strip()):
        raise WorkflowError(f"{name} must be {'nonempty ' if required else ''}text of at most {limit} characters.")
    return value.strip()


def connector(cid=None):
    if cid:
        c = federation.get_connector(cid)
        return c if c and c.get("producer") == "deflate" else None
    rows = [c for c in federation.load_connectors(include_disabled=True) if c.get("producer") == "deflate"]
    return sorted(rows, key=lambda c: (not c.get("enabled"), c["connector_id"]))[0] if rows else None


def _identity(c):
    return {k: c.get(k) for k in ("connector_id", "producer", "base_url", "origin", "credential_ref", "dev_loopback")}


def readiness(cid=None):
    c = connector(cid)
    rules = [r for r in federation._rows(federation.connectors_log()) if c and r.get("kind") == "deflate_workflow_enabled" and r.get("connector_id") == c["connector_id"]]
    rule = rules[-1] if rules else {}
    authorized = bool(c and rule.get("enabled") and rule.get("contract") == CONTRACT and rule.get("connector") == _identity(c))
    fixture = bool(c and testmode.active() and c.get("dev_loopback"))
    reason = ("No Deflate connection is registered." if not c else "The Deflate connection is disabled." if not c.get("enabled") else
              "The bounded Deflate deployment has not been enabled." if not authorized and not fixture else
              "Pin Deflate's existing signing key in Connections before starting a reading." if not c.get("trusted_keys") and not fixture else "")
    return {"available": not reason, "reason": reason, "contract": CONTRACT, "connector_id": (c or {}).get("connector_id"),
            "authorized": authorized, "fixture_only": fixture, "max_upload_bytes": MAX_UPLOAD_BYTES,
            "default_allowance_usd": DEFAULT_ALLOWANCE, "reading_default": False,
            "disclosure": "Prepare checks the configured bridge without fetching the source. Upload bytes stay here until Start. Cloud transcription is not enabled by this bridge."}


def authorize(cid, enabled, note):
    c = connector(cid)
    if not c:
        raise WorkflowError("No Deflate connection with that id.", 404)
    note = _text(note or "", "Deployment verification note", 500, bool(enabled))
    return federation._append(federation.connectors_log(), {"kind": "deflate_workflow_enabled", "connector_id": cid,
        "enabled": bool(enabled), "note": note, "by": "owner", "contract": CONTRACT, "connector": _identity(c)})


def _uploads_dir():
    root = Path(cli.LOCAL_STATE).resolve()
    directory = root / "deflate-inputs"
    if directory.is_symlink() or (directory.exists() and not directory.resolve().is_relative_to(root)):
        raise WorkflowError("The local upload store resolves outside this workspace.", 409)
    return directory


def _format(head):
    if head.startswith(b"RIFF") and head[8:12] == b"WAVE": return "wav"
    if head.startswith(b"fLaC"): return "flac"
    if head.startswith(b"OggS"): return "ogg"
    if head.startswith(b"ID3") or (len(head) >= 2 and head[0] == 255 and head[1] & 224 == 224): return "mp3"
    if head[4:8] == b"ftyp": return "mp4"
    if head.startswith(b"\x1a\x45\xdf\xa3"): return "webm"
    raise WorkflowError("Choose an MP3 file with a recognizable audio header.", 415)


def stage_upload(stream, name, declared_size=None):
    """Explicit local chosen-file intake. Route already holds the vault guard."""
    name = _safe_metadata(_text(name, "File name", 200, True))
    if "/" in name or "\\" in name or name in (".", ".."):
        raise WorkflowError("Use a file name without its local path.")
    if declared_size is not None and (type(declared_size) is not int or not 0 < declared_size <= MAX_UPLOAD_BYTES):
        raise WorkflowError("The chosen file exceeds the 100 MiB intake limit or is empty.", 413)
    directory = _uploads_dir(); directory.mkdir(parents=True, exist_ok=True, mode=0o700)
    fd, temporary = tempfile.mkstemp(prefix=".chosen-", dir=directory)
    size, digest, head = 0, hashlib.sha256(), b""
    try:
        with os.fdopen(fd, "wb") as out:
            os.fchmod(out.fileno(), 0o600)
            while True:
                chunk = stream.read(min(65536, MAX_UPLOAD_BYTES + 1 - size))
                if not chunk: break
                size += len(chunk)
                if size > MAX_UPLOAD_BYTES: raise WorkflowError("The chosen file exceeds the 100 MiB intake limit.", 413)
                if len(head) < 64: head += chunk[:64-len(head)]
                digest.update(chunk); out.write(chunk)
            if size < 12 or (declared_size is not None and size != declared_size):
                raise WorkflowError("The chosen upload was incomplete. Choose the file again.", 409)
            format_ = _format(head)
            if format_ != "mp3": raise WorkflowError("This bounded Deflate workflow currently takes MP3 uploads. Other formats remain available through Deflate's own supported intake.", 415)
            out.flush(); os.fsync(out.fileno())
        sha = digest.hexdigest(); blob = directory / (sha + ".bin")
        try: os.link(temporary, blob)
        except FileExistsError:
            if blob.is_symlink() or hashlib.sha256(blob.read_bytes()).hexdigest() != sha:
                raise WorkflowError("The saved upload differs from its immutable source hash.", 409)
        descriptor = {"kind": "upload", "name": name, "sha256": sha, "bytes": size, "format": format_}
        upload_id = "upload_" + _digest(descriptor)[:32]
        record = {**descriptor, "upload_id": upload_id, "retention": "Exact chosen bytes retained locally in this Nikodemus workspace; sent only to its configured Deflate producer after Start."}
        encoded = json.dumps(record, sort_keys=True, ensure_ascii=False).encode()
        record_path = directory / (upload_id + ".json")
        if not record_path.exists():
            fd2, meta_tmp = tempfile.mkstemp(prefix=".meta-", dir=directory)
            try:
                with os.fdopen(fd2, "wb") as out:
                    os.fchmod(out.fileno(), 0o600); out.write(encoded); out.flush(); os.fsync(out.fileno())
                try: os.link(meta_tmp, record_path)
                except FileExistsError: pass
            finally: os.unlink(meta_tmp)
        if record_path.is_symlink() or record_path.read_bytes() != encoded:
            raise WorkflowError("The saved upload metadata differs from its immutable identity.", 409)
        dfd = os.open(directory, os.O_RDONLY)
        try: os.fsync(dfd)
        finally: os.close(dfd)
        return record
    finally:
        if os.path.exists(temporary): os.unlink(temporary)


def load_upload(upload_id, *, verify=True):
    if not re.fullmatch(r"upload_[a-f0-9]{32}", str(upload_id or "")):
        raise WorkflowError("No such chosen upload.", 404)
    directory = _uploads_dir(); meta = directory / (upload_id + ".json")
    try:
        if meta.is_symlink(): raise ValueError("symlink")
        record = json.loads(meta.read_text())
        if not re.fullmatch(r"[a-f0-9]{64}", str(record.get("sha256") or "")) or type(record.get("bytes")) is not int or not 0 < record["bytes"] <= MAX_UPLOAD_BYTES:
            raise ValueError("source descriptor")
        expected = {k: record[k] for k in ("kind", "name", "sha256", "bytes", "format")}
        if "upload_" + _digest(expected)[:32] != upload_id or record.get("upload_id") != upload_id:
            raise ValueError("identity")
        blob = directory / (record["sha256"] + ".bin")
        if blob.is_symlink() or not blob.is_file() or blob.stat().st_size != record["bytes"]:
            raise ValueError("bytes")
        if verify and hashlib.sha256(blob.read_bytes()).hexdigest() != record["sha256"]:
            raise ValueError("hash")
        return record, blob
    except (OSError, ValueError, TypeError, KeyError) as exc:
        raise WorkflowError("The chosen upload is unavailable or no longer matches its recorded hash.", 409) from exc


def _url(value):
    value = _safe_metadata(_text(value, "Media URL", 2000, True))
    u = urlsplit(value)
    if u.scheme not in ("https", "http") or not u.hostname or u.username or u.password or u.fragment:
        raise WorkflowError("Use a public HTTP or HTTPS media URL without credentials.")
    host = u.hostname.lower().rstrip(".")
    if host in ("localhost", "localhost.localdomain") or host.endswith((".localhost", ".local")):
        raise WorkflowError("Use a public media URL, not a local service address.")
    try: address = ipaddress.ip_address(host)
    except ValueError: address = None
    if address and not address.is_global: raise WorkflowError("Use a public media URL, not a private network address.")
    return value


def _read_operation(op_id):
    path = ops.db_path()
    if not path.is_file(): return None
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        return ops._row(conn.execute("SELECT * FROM operations WHERE op_id=?", (op_id,)).fetchone())
    finally: conn.close()


def _events(op_id):
    path = ops.db_path()
    if not path.is_file(): return []
    conn = sqlite3.connect(path.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        conn.row_factory = sqlite3.Row
        return [{**dict(row), "detail": json.loads(row["detail"])} for row in conn.execute("SELECT * FROM operation_events WHERE op_id=? ORDER BY seq", (op_id,))]
    finally: conn.close()


def is_ours(op):
    return bool(op and op.get("action_id") == ACTION)


def _mark(*args, **kwargs):
    with vault.corpus_write():
        vault.mark_dirty(); return ops.mark(*args, **kwargs)


def _event(*args, **kwargs):
    with vault.corpus_write():
        vault.mark_dirty(); return ops.event(*args, **kwargs)


def _keep(op_id, name, raw):
    with vault.corpus_write():
        vault.mark_dirty()
        kept = producers.keep_artifact(op_id, name, raw)
        # Existing artifact helper gives immutable numbered names. Flush the
        # completed bytes before linking them from the operation event spine.
        with (producers.artifact_dir(op_id) / kept["name"]).open("rb") as stream: os.fsync(stream.fileno())
        directory_fd = os.open(producers.artifact_dir(op_id), os.O_RDONLY)
        try: os.fsync(directory_fd)
        finally: os.close(directory_fd)
        op = ops.get(op_id); ref = dict(op.get("result_ref") or {})
        all_kept = list(ref.get("kept") or [])
        if kept not in all_kept: all_kept.append(kept)
        ref["kept"] = all_kept
        ops.mark(op_id, result_ref=ref, event_kind="note", detail={"artifact": kept})
        return kept


def artifact(op, name):
    if not is_ours(op) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,100}", str(name or "")) or name in (".", ".."):
        raise WorkflowError("No such saved reading artifact.", 404)
    ref = next((r for r in (op.get("result_ref") or {}).get("kept", []) if r.get("name") == name), None)
    if not ref: raise WorkflowError("No such saved reading artifact.", 404)
    raw = producers.artifact_bytes(op["op_id"], name)
    if hashlib.sha256(raw).hexdigest() != ref.get("sha256"):
        raise WorkflowError("The saved reading artifact differs from its recorded hash.", 409)
    return raw


def _origin(value, question):
    if isinstance(value, dict) and value.get("kind") == "operation":
        parent = _read_operation(str(value.get("operation_id") or ""))
        import opencase
        if not (is_ours(parent) or opencase.is_ours(parent)):
            raise WorkflowError("The originating investigation is not in this workspace.", 404)
        plan = (parent.get("execution") or {}).get("plan") or {}
        kept = (parent.get("result_ref") or {}).get("result_artifact")
        if not kept:
            raise WorkflowError("The originating investigation has no saved source result.", 409)
        try: raw = (artifact if is_ours(parent) else opencase.artifact)(parent, kept["name"])
        except opencase.WorkflowError as exc: raise WorkflowError(str(exc),exc.status) from exc
        result = {"kind":"operation", "operation_id":parent["op_id"], "action_id":parent.get("action_id"),
            "question":plan.get("question"), "result_artifact":copy.deepcopy(kept),
            "result_sha256":hashlib.sha256(raw).hexdigest(), "parent_origin":copy.deepcopy(plan.get("origin"))}
        if value.get("receipts_continuation") is not None:
            if not opencase.is_ours(parent):
                raise WorkflowError("This source-gap reference does not name an Open Case investigation.", 409)
            import receipts_projection
            try: result["receipts_continuation"] = receipts_projection.freeze_continuation(parent, value["receipts_continuation"])
            except receipts_projection.ProjectionError as exc: raise WorkflowError(str(exc),getattr(exc,"status",409)) from exc
        return result
    import opencase
    try:
        return opencase._origin(value, question)
    except opencase.WorkflowError as exc:
        raise WorkflowError(str(exc), exc.status) from exc


def prepare(question, inputs):
    """Freeze the producer's non-acquiring plan inside the ordinary proposal."""
    if not isinstance(inputs, dict): raise WorkflowError("Reading inputs must be a record.")
    question = _text(question or "Read this source", "Reading question", 4000, True)
    c = connector(inputs.get("connector_id"))
    rd = readiness((c or {}).get("connector_id"))
    if not c or not rd["available"]: raise WorkflowError(rd["reason"] or "No such Deflate connection.", 409)
    try: workspace_id = workspace_identity.read()["workspace_id"]
    except workspace_identity.IdentityError as exc: raise WorkflowError(str(exc),409) from exc
    origin = _origin(inputs.get("origin"), question)
    if inputs.get("upload_id"):
        upload, _ = load_upload(inputs["upload_id"])
        source = {k: upload[k] for k in ("kind", "name", "sha256", "bytes", "format")}
    else:
        upload = None; source = {"kind":"url", "url":_url(inputs.get("url"))}
    enabled = inputs.get("reading_enabled", False)
    if type(enabled) is not bool: raise WorkflowError("Choose whether to include the optional model reading.")
    allowance = inputs.get("allowance_usd", DEFAULT_ALLOWANCE) if enabled else 0
    if type(allowance) not in (int, float) or not 0 <= allowance <= 10 or (enabled and not allowance > 0):
        raise WorkflowError("Choose a reading estimate allowance greater than $0 and at most $10, or disable model reading.")
    outbound_origin = {k: str(origin[k]) for k in ("doc_id", "snapshot_id", "revision") if origin.get(k) is not None}
    outbound_origin.update(origin_sha256=_digest(origin), storage="Full origin retained in Nikodemus")
    context = {"title": _safe_metadata(_text(inputs.get("title", ""), "Source title", 200)),
        "sourceLabel": _safe_metadata(_text(inputs.get("source_label", ""), "Source label", 200)),
        "sourceDate": _text(inputs.get("source_date", ""), "Source date", 40)}
    context = {k:v for k,v in context.items() if v}
    body = {"input":source, "context":context, "question":question, "origin":outbound_origin,
            "engine":"local", "reading_enabled":enabled, "allowance_usd":allowance,
            "max_model_calls":24, "max_output_tokens":8192, "max_prompt_bytes":80000}
    response = producers._request(c, "POST", "/api/bridge/prepare", body, auth="none")
    if not response.get("ok"):
        raise WorkflowError("Deflate could not prepare this reading. No source was fetched or model started: " + str(response.get("outcome") or "unavailable"), 502)
    remote = response.get("json") or {}
    if not isinstance(remote.get("plan"), dict) or not re.fullmatch(r"[a-f0-9]{64}", str(remote.get("plan_sha256") or "")) or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", str(remote.get("plan_id") or "")):
        raise WorkflowError("Deflate returned an unsupported proposal; nothing was started.", 502)
    remote_plan = remote["plan"]
    if federation.payload_sha256(remote_plan) != remote["plan_sha256"] or remote["plan_id"] != "p_" + remote["plan_sha256"] or remote_plan.get("contract") != CONTRACT:
        raise WorkflowError("Deflate's proposal does not match its declared immutable hash.", 502)
    for key in ("input", "context", "origin", "question", "reading_enabled", "engine", "allowance_usd", "max_model_calls", "max_output_tokens", "max_prompt_bytes"):
        if remote_plan.get(key) != body[key]:
            raise WorkflowError("Deflate proposed a different " + key + "; nothing was started.", 502)
    model = remote_plan.get("model") or {}
    if enabled:
        rate = costs.rate_card(model.get("provider"),model.get("model"))
        categories = {r["category"]:r["usd_per_million"] for r in (rate or {}).get("categories",[])}
        if not rate or not model.get("priced") or model.get("mock") or categories != (model.get("rate_card") or {}).get("per_million"):
            raise WorkflowError("The configured reading model has no reviewed matching price card. Keep model reading off or review the bridge configuration before Start.",409)
    return {"contract":CONTRACT, "workspace_id":workspace_id, "question":question, "origin":origin, "follow_up_of":origin.get("operation_id") or "",
        "connector":_identity(c), "input":source, "upload_id":upload["upload_id"] if upload else None,
        "producer_request":body, "producer_plan":remote_plan, "plan_id":remote["plan_id"], "plan_sha256":remote["plan_sha256"],
        "producer_prepare_artifact":{"sha256":hashlib.sha256(response["raw"]).hexdigest(),"bytes":len(response["raw"])},
        "producer_prepare_bytes":response["raw"].decode("utf-8"),
        "producer_prepare_response":remote, "ready":remote.get("ready") is True, "blockers":remote.get("blockers") or [],
        "reading_enabled":enabled, "allowance_usd":allowance,
        "cost":(f"Up to ${allowance:.2f} in estimated model usage under the reviewed rate card. Provider billing is confirmed separately. Local transcription has no model API charge." if enabled else
                "No paid model reading. Captions or local transcription only; no model API charge is authorized."),
        "calls":"One acquisition, then bounded model reading with no automatic paid retry" if enabled else "One acquisition; no model reading",
        "outbound":["Chosen public URL or selected upload bytes, after Start", "Reading purpose and limited origin references", "Transcript to the configured model provider only when model reading is enabled"],
        "retention":upload["retention"] if upload else "Original URL, acquired transcript, reading attempts and signed result remain in this Nikodemus workspace.",
        "limitations":["The question is retained as the purpose of this reading; Deflate's existing reading does not promise to answer every question.",
            "Model readings and speaker assignments remain attributed interpretations. A valid signature establishes package custody, not factual truth.",
            "Cloud transcription is unavailable in this bounded bridge. Browser-session access stays in Deflate's established local setting."]}


def validate_plan(plan):
    if not isinstance(plan, dict) or plan.get("contract") != CONTRACT or not plan.get("ready"):
        raise WorkflowError("Prepare a ready Deflate proposal before Start.", 409)
    try: current_workspace = workspace_identity.read()["workspace_id"]
    except workspace_identity.IdentityError as exc: raise WorkflowError(str(exc),409) from exc
    if current_workspace != plan.get("workspace_id"):
        raise WorkflowError("This proposal belongs to another workspace identity.",409)
    c = connector((plan.get("connector") or {}).get("connector_id"))
    if not c or plan.get("connector") != _identity(c):
        raise WorkflowError("The Deflate connection changed. Prepare again before Start.", 409)
    rd = readiness(c["connector_id"])
    if not rd["available"]: raise WorkflowError(rd["reason"], 409)
    if plan.get("upload_id"):
        upload, _ = load_upload(plan["upload_id"])
        if {k: upload[k] for k in ("kind", "name", "sha256", "bytes", "format")} != plan.get("input"):
            raise WorkflowError("The chosen upload changed after the proposal.", 409)
    return c


def _request(op_id, c, method, path, body=None, *, name="reply.json"):
    stage = "deflate.start" if method == "POST" and path == "/api/bridge/start" else method + " " + path
    if method == "POST":
        _keep(op_id, "start-request.json", json.dumps(body, sort_keys=True, ensure_ascii=False).encode())
    _event(op_id, "stage_intent", stage=stage, detail={"method":method,"path":path,"contract":CONTRACT})
    r = producers._request(c, method, path, body, auth="none")
    kept = _keep(op_id, name, r["raw"]) if r.get("raw") else None
    _event(op_id, "stage_end", stage=stage, outcome="ok" if r.get("ok") else "error",
        detail={"delivery":r.get("delivery"),"outcome":r.get("outcome"),"http_status":r.get("status"),"artifact":kept})
    return r, kept


def _upload_request(c, upload, path):
    """One streamed upload to the configured origin; no redirects or retry."""
    target = c["base_url"].rstrip("/") + "/api/bridge/uploads?name=" + quote(upload["name"], safe="") + "&sha256=" + upload["sha256"]
    if federation._origin_of(target) != c.get("origin"):
        return {"ok":False,"delivery":"not_sent","outcome":"origin_refused"}
    try:
        with path.open("rb") as source:
            req = urllib.request.Request(target, data=source, method="POST", headers={"Content-Type":"audio/mpeg",
                "Content-Length":str(upload["bytes"]),"Accept":"application/json","User-Agent":"Nikodemus-connector/2"})
            with urllib.request.build_opener(federation._NoRedirect()).open(req, timeout=120) as reply:
                raw = federation._read_bounded(reply, producers.MAX_BYTES)
                return {"ok":True,"raw":raw,"json":json.loads(raw),"status":reply.status,"delivery":"delivered"}
    except urllib.error.HTTPError as exc:
        return {"ok":False,"delivery":"delivered","outcome":"refused" if 400 <= exc.code < 500 else "producer_error","status":exc.code}
    except (OSError, ValueError, federation._Oversized) as exc:
        return {"ok":False,"delivery":"unknown","outcome":"upload_outcome_unknown","detail":type(exc).__name__}


def _stage_remote_upload(op_id, c, plan):
    upload, path = load_upload(plan["upload_id"])
    _event(op_id, "stage_intent", stage="deflate.upload", detail={"sha256":upload["sha256"],"bytes":upload["bytes"],"format":upload["format"]})
    reply = _upload_request(c, upload, path)
    kept = _keep(op_id, "upload-reply.json", reply["raw"]) if reply.get("raw") else None
    _event(op_id, "stage_end", stage="deflate.upload", outcome="ok" if reply.get("ok") else "error",
        detail={"delivery":reply.get("delivery"),"outcome":reply.get("outcome"),"artifact":kept})
    if not reply.get("ok"):
        raise WorkflowError("The upload's producer outcome is unknown or was refused. No reading Start was sent; the chosen bytes remain here.", 502)
    remote = (reply.get("json") or {}).get("upload") or {}
    if remote.get("id") != "u_" + upload["sha256"] or any(remote.get(k) != upload[k] for k in ("name","sha256","bytes","format")):
        raise WorkflowError("Deflate's upload acknowledgement differs from the frozen source; no reading Start was sent.", 502)
    return remote["id"]


def _check_job(job, op):
    plan = op["execution"]["plan"]
    if not isinstance(job, dict) or job.get("contract") != CONTRACT or job.get("request_id") != op["op_id"] or job.get("plan_id") != plan["plan_id"] or job.get("plan_sha256") != plan["plan_sha256"] or job.get("plan") != plan["producer_plan"]:
        raise WorkflowError("Deflate returned a different reading or plan. Its reply is kept, but it cannot replace this operation.", 502)
    bid = job.get("bridge_id")
    if not isinstance(bid, str) or not re.fullmatch(r"b_[a-f0-9]{32}", bid):
        raise WorkflowError("Deflate returned an invalid reading identity.", 502)
    known = (op.get("result_ref") or {}).get("upstream_id")
    if known and known != bid: raise WorkflowError("Deflate returned another reading identity.", 502)
    if job.get("state") not in TERMINAL | {"starting","acquiring","importing","reading","exporting","finishing","running","queued"}:
        raise WorkflowError("Deflate returned an unsupported lifecycle state.", 502)
    return bid


def launch(op_id, resume=False):
    with _worker_lock:
        if op_id in _workers: return False
        _workers.add(op_id)
    threading.Thread(target=_run, args=(op_id,resume), daemon=True, name="deflate-"+op_id).start()
    return True


def _run(op_id, resume=False):
    try:
        op = _read_operation(op_id)
        if not is_ours(op): return
        if (op.get("result_ref") or {}).get("result_artifact"): return
        plan = op["execution"]["plan"]; c = validate_plan(plan)
        bid = (op.get("result_ref") or {}).get("upstream_id")
        if not bid:
            # A GET by our durable request id is the only recovery after intent.
            # Even a 404 never grants permission to replay an uncertain Start.
            started = any(e.get("kind") == "stage_intent" and e.get("stage") == "deflate.start" for e in _events(op_id))
            if resume or started:
                reply, _ = _request(op_id, c, "GET", "/api/bridge/requests/"+quote(op_id,safe=""), name="recovery.json")
                if not reply.get("ok"):
                    _mark(op_id,"unknown",local_state="The original Start could not be confirmed. No request was repeated.",last_error="Recover the original request identity when Deflate is available; do not press a new Start to repair a lost reply.")
                    return
            else:
                raw = plan["producer_prepare_bytes"].encode()
                if hashlib.sha256(raw).hexdigest() != plan["producer_prepare_artifact"]["sha256"]:
                    raise WorkflowError("The saved producer proposal no longer verifies.",409)
                _keep(op_id,"producer-plan.json",raw)
                remote_upload = _stage_remote_upload(op_id,c,plan) if plan.get("upload_id") else ""
                body = {"plan_id":plan["plan_id"],"plan_sha256":plan["plan_sha256"],"request_id":op_id}
                if remote_upload: body["upload_id"] = remote_upload
                reply, _ = _request(op_id,c,"POST","/api/bridge/start",body,name="start-reply.json")
                if not reply.get("ok"):
                    outcome, delivery, detail = producers._outcome_of_failure(reply)
                    _mark(op_id,"failed" if outcome in ("not_sent","refused") else "unknown",local_state=detail,last_error=detail,
                          producer_state={"delivery":delivery,"outcome":outcome})
                    return
            job = reply.get("json") or {}; bid = _check_job(job,op)
            ref = dict((_read_operation(op_id).get("result_ref") or {})); ref["upstream_id"] = bid
            _mark(op_id,"running",result_ref=ref,local_state="Deflate accepted the saved reading plan.")
        deadline = time.monotonic() + 1800
        last = None
        while time.monotonic() < deadline:
            reply, kept = _request(op_id,c,"GET","/api/bridge/jobs/"+bid,name="status.json")
            if not reply.get("ok"):
                _mark(op_id,"unknown",local_state="The existing reading could not be checked. Its saved request identity remains available.",last_error="Deflate status unavailable; no new reading was started.")
                return
            op = _read_operation(op_id); job = reply.get("json") or {}; _check_job(job,op)
            issues = _ingest_attempts(op,c,job)
            if issues:
                ref = dict(_read_operation(op_id).get("result_ref") or {})
                ref["accounting_issues"] = issues
                _mark(op_id,result_ref=ref)
            stamp = _digest([job.get("state"),job.get("progress"),job.get("acquisition"),job.get("reading")])
            if stamp != last:
                last = stamp
                ref = dict(_read_operation(op_id).get("result_ref") or {})
                ref.update(status_artifact=kept,run_id=job.get("runId"),acquisition=job.get("acquisition"),reading=job.get("reading"))
                _mark(op_id,"running",result_ref=ref,producer_state={"status":job.get("state")},
                    local_state={"starting":"Starting the approved reading","acquiring":"Obtaining the source transcript","reading":"Reading and checking the transcript","exporting":"Keeping the signed result"}.get(job.get("state"),"Keeping Deflate's progress"))
            if job["state"] in TERMINAL and job.get("finished_at"):
                _finish(op_id,c,job,kept)
                return
            time.sleep(2)
        _mark(op_id,"unknown",local_state="The observation window ended. Check the same reading again; no new work will be started.")
    except Exception as exc:
        _mark(op_id,"unknown",local_state="The reading stopped at a recorded boundary; no request will be repeated automatically.",
              last_error=operation_capture.sanitize_body(str(exc))["value"][:600])
    finally:
        with _worker_lock: _workers.discard(op_id)


def _remote_artifact(op, c, bid, ref):
    if not isinstance(ref, dict) or not re.fullmatch(r"[A-Za-z0-9_.-]{1,80}", str(ref.get("name") or "")) or not re.fullmatch(r"[a-f0-9]{64}", str(ref.get("sha256") or "")):
        raise WorkflowError("Deflate returned an invalid artifact reference.",502)
    expected_path = "/api/bridge/jobs/"+bid+"/artifacts/"+ref["name"]
    if ref.get("path") != expected_path:
        raise WorkflowError("A reading artifact would leave its recorded operation path.",502)
    local_name = "producer-"+ref["name"]
    old = next((r for r in (op.get("result_ref") or {}).get("kept",[]) if r.get("sha256") == ref["sha256"] and r.get("name","").startswith("producer-")),None)
    if old:
        return old, artifact(op,old["name"])
    response, kept = _request(op["op_id"],c,"GET",expected_path,name=local_name)
    if not response.get("ok") or not kept:
        raise WorkflowError("A saved Deflate artifact could not be copied. Check the same reading again; no model request is repeated.",502)
    raw = response["raw"]
    if hashlib.sha256(raw).hexdigest() != ref["sha256"] or (ref.get("bytes") is not None and len(raw) != ref["bytes"]):
        raise WorkflowError("The producer artifact does not match its declared bytes/hash. The received bytes remain in custody.",502)
    return kept, raw


def _account_reservation(op, job, attempt):
    """Mirror the producer's before-call reservation; do not invent NK dispatch."""
    aid = attempt.get("attempt_id"); remote_model = job["plan"].get("model") or {}
    if not isinstance(aid,str) or not re.fullmatch(r"model_[0-9]{3}",aid):
        raise WorkflowError("Deflate returned an invalid model-attempt identity.",502)
    if attempt.get("provider") != remote_model.get("provider") or attempt.get("model") != remote_model.get("model") or attempt.get("rate_card") != remote_model.get("rate_card"):
        raise WorkflowError("A model attempt differs from the frozen provider, model or price card.",502)
    rate = costs.rate_card(attempt["provider"],attempt["model"])
    remote_rate = attempt.get("rate_card") or {}
    if not rate or {r["category"]:r["usd_per_million"] for r in rate["categories"]} != remote_rate.get("per_million"):
        raise WorkflowError("The producer's model price categories are not supported by the common cost ledger.",502)
    reserved = attempt.get("reserved_usd")
    if type(reserved) not in (int,float) or not math.isfinite(reserved) or not 0 <= reserved <= job["plan"]["allowance_usd"]:
        raise WorkflowError("The producer's model reservation exceeds the disclosed allowance.",502)
    request = attempt.get("request") or {}
    fingerprint = _digest({"plan_sha256":job["plan_sha256"],"attempt_id":aid,"request":request,"reserved_usd":reserved,"rate_card":remote_rate})
    row = {"schema":costs.SCHEMA,"event_type":"reservation","operation_id":op["op_id"],"component":"deflate.reading","attempt_id":aid,
        "provider":attempt["provider"],"model":attempt["model"],"rate_card":rate,"producer_rate_card":remote_rate,
        "request_fingerprint":fingerprint,"producer_request_artifact":request,"prompt_cache":"not_requested","tools":False,
        "accounting_status":"reserved","basis":"producer_before_dispatch_reservation_observed_in_saved_bridge_status",
        "currency":"USD","allowance_usd":job["plan"]["allowance_usd"],"reserved_usd":reserved,"estimated_cost_usd":None,
        "actual_cost_usd":None,"known_estimated_subtotal_usd":0.0,"usage":[]}
    row["entry_id"] = _digest([op["op_id"],"deflate.reading",aid,"reservation"])
    def check(rows):
        previous = next((r for r in rows if r.get("entry_id") == row["entry_id"]),None)
        if previous and previous.get("request_fingerprint") != fingerprint:
            raise WorkflowError("The producer changed an earlier model reservation.",502)
        return previous
    costs._append(op["op_id"],row,check=check)


def _ingest_attempts(op,c,job):
    attempts = job.get("attempts") or []
    if not isinstance(attempts,list) or len(attempts) > job["plan"]["max_model_calls"]:
        raise WorkflowError("Deflate returned more model attempts than this proposal permits.",502)
    seen, issues = set(), []
    for attempt in attempts:
        if not isinstance(attempt,dict) or attempt.get("attempt_id") in seen:
            raise WorkflowError("Deflate returned duplicate or malformed model attempts.",502)
        seen.add(attempt.get("attempt_id")); _account_reservation(op,job,attempt)
        if attempt.get("request"):
            _remote_artifact(_read_operation(op["op_id"]),c,job["bridge_id"],attempt["request"])
        if not attempt.get("response"): continue
        kept, raw = _remote_artifact(_read_operation(op["op_id"]),c,job["bridge_id"],attempt["response"])
        receipt = json.loads(raw)
        if receipt.get("attempt_id") != attempt["attempt_id"]:
            raise WorkflowError("A provider receipt differs from the recorded model attempt.",502)
        usage = receipt.get("usage")
        if usage != attempt.get("usage") or (receipt.get("request_id") or "") != (attempt.get("provider_response_id") or ""):
            raise WorkflowError("The model usage or provider identity differs from its preserved receipt.",502)
        raw_response = receipt.get("provider_response")
        if isinstance(raw_response,dict) and (raw_response.get("model") not in (None,receipt.get("model")) or raw_response.get("usage") not in (None,usage) or raw_response.get("id") not in (None,receipt.get("request_id"))):
            raise WorkflowError("The exact provider response differs from its model, usage or response identity metadata.",502)
        drifted = receipt.get("model") != attempt["model"]
        if drifted: issues.append({"attempt_id":attempt["attempt_id"],"kind":"provider_model_changed", "detail":"The provider returned a different model. Its receipt and source remain saved, but the charge is unresolved under this proposal."})
        normalized = {"provider":attempt["provider"],"model":receipt.get("model"),"error":receipt.get("error"),
            "response":{"response_id":receipt.get("request_id"),"response":receipt.get("provider_response"),"usage":usage,
                "stop_reason":receipt.get("stop_reason"),"usage_complete":bool(not drifted and isinstance(usage,dict) and all(type(usage.get(k)) is int and usage[k]>=0 for k in ("input_tokens","output_tokens")))}}
        costs.settle(op["op_id"],"deflate.reading",attempt["attempt_id"],normalized,kept["sha256"],receipt_artifact=kept)
    return issues


def _finish(op_id,c,job,kept):
    op = _read_operation(op_id); state = job["state"]
    acquisition = job.get("acquisition") or {}
    if acquisition.get("artifact"):
        _remote_artifact(op,c,job["bridge_id"],acquisition["artifact"])
    if job.get("source_artifact"):
        _remote_artifact(_read_operation(op_id),c,job["bridge_id"],job["source_artifact"])
    remote_result = job.get("result") or {}
    custody, deposition_artifact = None, None
    if remote_result.get("deposition"):
        deposition_artifact, raw = _remote_artifact(_read_operation(op_id),c,job["bridge_id"],remote_result["deposition"])
        envelope = json.loads(raw)
        if (envelope.get("object") or {}).get("id") != job.get("runId") or remote_result.get("runId") != job.get("runId"):
            raise WorkflowError("The signed export names another Deflate reading.",502)
        transcript = (envelope.get("payload") or {}).get("transcript") or {}
        if not isinstance(transcript.get("text"),str) or hashlib.sha256(transcript["text"].encode()).hexdigest() != transcript.get("sha256") or transcript.get("sha256") != remote_result.get("transcript_sha256"):
            raise WorkflowError("The retained transcript differs from the producer's completed reading hash.",502)
        with vault.corpus_write():
            vault.mark_dirty()
            custody = federation.import_package(c,raw,how="deflate_reading",object_id_hint=job["runId"])
        if not (custody.get("verification") or {}).get("ok"):
            state = "partial"
    elif state in ("completed","partial") and not job.get("export_gap"):
        raise WorkflowError("Deflate has not supplied its settled reading export. Check the same operation again.",502)
    ref = dict(_read_operation(op_id).get("result_ref") or {})
    ref.update(result_artifact=kept,artifact=kept,deposition_artifact=deposition_artifact,custody=custody,
        upstream_status=job["state"],run_id=job.get("runId"),acquisition=acquisition,reading=job.get("reading"))
    if ref.get("accounting_issues"): state = "unknown"
    word = "unknown" if state == "unknown" else "failed" if state in ("failed","interrupted","needs_selection") else "complete"
    label = ("Transcript saved; model reading was not requested." if state == "completed" and not job["plan"]["reading_enabled"] else
             "Reading and signed source saved locally." if state == "completed" else
             "Partial reading saved. Review the held passages and source gaps." if state == "partial" else
             "The source needs an episode choice. The acquisition record is saved; no model reading was started." if state == "needs_selection" else
             "The reading was interrupted; the retained source and attempts remain available." if state == "interrupted" else
             "The model outcome is unknown; retained attempts remain and no request will be repeated." if state == "unknown" else
             "The source could not be read. Its failure and available artifacts are saved.")
    # The bridge disables all cloud transcription and paid acquisition. This
    # explicit producer report is separate from every model attempt's ledger.
    if ((job.get("costs") or {}).get("acquisition") or {}).get("paid_cost_usd") == 0:
        row={"schema":costs.SCHEMA,"event_type":"source_cost","entry_id":_digest([op_id,"deflate.acquisition",kept["sha256"]]),
            "operation_id":op_id,"component":"deflate.acquisition","attempt_id":"acquisition:1","provider":"deflate.local",
            "accounting_status":"reported_zero","basis":"settled_bridge_local_transcription_no_paid_acquisition_contract","currency":"USD",
            "estimated_cost_usd":0.0,"known_estimated_subtotal_usd":0.0,"actual_cost_usd":0.0,"receipt_sha256":kept["sha256"],"usage":[]}
        costs._append(op_id,row)
    _mark(op_id,word,local_state=label,last_error=str((job.get("error") or {}).get("message") or job.get("export_gap") or (ref.get("accounting_issues") or [{}])[0].get("detail") or ""),result_ref=ref)


def original_upload(op):
    """Return only this operation's explicitly chosen, hash-verified local source."""
    if not is_ours(op): raise WorkflowError("No saved Deflate reading with that id.",404)
    plan = op["execution"]["plan"]
    if not plan.get("upload_id"): raise WorkflowError("This reading did not use a chosen local upload.",404)
    record,path=load_upload(plan["upload_id"])
    if {k:record[k] for k in ("kind","name","sha256","bytes","format")} != plan.get("input"):
        raise WorkflowError("The retained original differs from this operation's frozen source.",409)
    return record,path


def _current_deposition(op, ref, result):
    """Recheck local custody without importing, settling or changing the record.

    The captured custody verdict remains historical. A removed pin or a signed
    but inconsistent source cannot be promoted by a later ordinary local read.
    """
    verdict = {"basis":"current_local_pins_and_exact_saved_source", "ok":False}
    try:
        if not ((ref.get("custody") or {}).get("verification") or {}).get("ok"):
            raise WorkflowError("The saved export did not pass its original custody verification.")
        envelope = json.loads(artifact(op, ref["deposition_artifact"]["name"]))
        plan = op["execution"]["plan"]
        c = connector((plan.get("connector") or {}).get("connector_id"))
        if not c or (envelope.get("producer") or {}).get("id") != "deflate":
            raise WorkflowError("The saved source no longer has its configured Deflate connection.")
        check = federation.verify_envelope(envelope, c.get("trusted_keys", []))
        if not check.get("ok"):
            raise WorkflowError("Current pinned-key verification is unavailable: " + str(check.get("why") or "unverified export"))
        remote = (result or {}).get("result") or {}
        payload = envelope.get("payload") or {}; claims = payload.get("claims") or {}; run = claims.get("run") or {}
        if (payload.get("schema") != "deflate-lens/deposition@1" or claims.get("schema") != "deflate-lens/claims@0.7"
                or (result or {}).get("request_id") != op["op_id"]
                or (result or {}).get("plan_sha256") != plan.get("plan_sha256")
                or (result or {}).get("bridge_id") != ref.get("upstream_id")
                or not run.get("id")
                or run["id"] != (envelope.get("object") or {}).get("id")
                or run["id"] != (result or {}).get("runId") or run["id"] != remote.get("runId")
                or (remote.get("deposition") or {}).get("sha256") != ref["deposition_artifact"].get("sha256")):
            raise WorkflowError("The saved export does not match this operation's source and frozen proposal.")
        transcript = payload.get("transcript") or {}; text = transcript.get("text")
        if (transcript.get("included") is not True or not isinstance(text, str) or not text.strip()
                or hashlib.sha256(text.encode()).hexdigest() != transcript.get("sha256")
                or transcript.get("sha256") != (run.get("transcript") or {}).get("sha256")
                or transcript.get("sha256") != remote.get("transcript_sha256")):
            raise WorkflowError("The saved transcript, signed run and captured result hashes do not agree.")
        verdict.update(ok=True, why="The retained export verifies under current local pins and matches the captured source.")
        return envelope, verdict
    except (WorkflowError, ValueError, TypeError, KeyError, AttributeError, OSError) as exc:
        verdict["why"] = str(exc)
        return None, verdict


def view(op):
    if not is_ours(op): raise WorkflowError("No saved Deflate reading with that id.",404)
    plan = op["execution"]["plan"]; ref = op.get("result_ref") or {}; events = _events(op["op_id"])
    result = None; error = op.get("last_error"); envelope = None; current_verification = None
    if ref.get("result_artifact"):
        try: result = json.loads(artifact(op,ref["result_artifact"]["name"]))
        except (WorkflowError,ValueError) as exc: error = str(exc)
    if ref.get("deposition_artifact"):
        envelope, current_verification = _current_deposition(op, ref, result)
        if not current_verification["ok"]:
            error = current_verification["why"]
    saves = [e for e in events if (e.get("detail") or {}).get("saved")]
    return {"operation_id":op["op_id"],"action_id":ACTION,"kind":"investigation","producer":"deflate","status":op["status"],
        "progress":op.get("local_state"),"error":error,"created_at":op["created_at"],"updated_at":op.get("updated_at"),
        "question":plan["question"],"origin":plan["origin"],"follow_up_of":plan.get("follow_up_of"),
        "plan":{k:v for k,v in plan.items() if k not in ("producer_prepare_bytes",)},"result":result,"result_ref":ref,
        "deposition":envelope,"deposition_id":(ref.get("custody") or {}).get("deposition_id"),"custody":ref.get("custody"),
        "current_verification":current_verification,
        "costs":costs.total(op),"thread_costs":costs.total(op,ancestry=True),"events":events,
        "saved":bool(saves),"saved_at":saves[-1]["at"] if saves else None,"autosaved":True,
        "original_upload":({**plan["input"],"upload_id":plan["upload_id"],"media_type":"audio/mpeg",
            "url":f"/api/deflate/operations/{op['op_id']}/original"} if plan.get("upload_id") else None),
        "artifacts":[{**r,"url":f"/api/deflate/operations/{op['op_id']}/artifacts/{r['name']}"} for r in ref.get("kept",[])]}


def list_views():
    path=ops.db_path()
    if not path.is_file(): return []
    conn=sqlite3.connect(path.resolve().as_uri()+"?mode=ro",uri=True);conn.row_factory=sqlite3.Row
    try: rows=[ops._row(r) for r in conn.execute("SELECT * FROM operations WHERE action_id=? ORDER BY created_at DESC LIMIT 200",(ACTION,))]
    finally: conn.close()
    return [view(row) for row in rows]


def save(op):
    if not is_ours(op): raise WorkflowError("No saved Deflate reading with that id.",404)
    ops.event(op["op_id"],"note",detail={"saved":True,"by":"owner"})
    return view(_read_operation(op["op_id"]))


def recover(op):
    if not is_ours(op): raise WorkflowError("No saved Deflate reading with that id.",404)
    if not (op.get("result_ref") or {}).get("result_artifact"): launch(op["op_id"],resume=True)
    return view(op)


def resume_known():
    resumed=[]
    for item in list_views():
        op=_read_operation(item["operation_id"])
        if op["status"] in ("running","claimed","unknown") and (op.get("config") or {}).get("state_root")==str(cli.LOCAL_STATE.resolve()) and (op.get("execution") or {}).get("plan",{}).get("workspace_id")==workspace_identity.read()["workspace_id"] and not (op.get("result_ref") or {}).get("result_artifact"):
            if launch(op["op_id"],resume=True): resumed.append(op["op_id"])
    return resumed
