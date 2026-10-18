"""Exact available gateway bodies on the existing operation/artifact spine.

SDK arguments and SDK response bodies are captured, not transport wire bytes.
Sanitization is a declared transform, not proof that arbitrary text has no secret.
Writers run inside the existing operation worker's corpus guard; never acquire a
nested guard here. Reads and the sanitizer do not create files or send requests.
"""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import sqlite3
import tempfile
from urllib.parse import unquote

SCHEMA = "nikodemus.operation-capture.v1"
TRANSPORT_KEYS = frozenset({"headers", "request_headers", "response_headers", "http_headers", "cookies", "cookie", "set_cookie", "authorization", "proxy_authorization", "environment", "environ", "env"})
SECRET_KEYS = frozenset({"api_key", "apikey", "x_api_key", "access_token", "refresh_token", "id_token", "auth_token", "token", "password", "passwd", "secret", "client_secret", "credential", "credentials", "private_key", "secret_access_key", "session_key"})
_CREDENTIAL = re.compile(r"\b(?:sk-(?:ant-)?[A-Za-z0-9_-]{8,}|xox[baprs]-[A-Za-z0-9-]{8,}|gh[pousr]_[A-Za-z0-9]{8,}|github_pat_[A-Za-z0-9_]{8,}|AKIA[A-Z0-9]{16})\b")
_BEARER = re.compile(r"(?i)\bBearer\s+[^\s\"'<>\\]+")
_ASSIGNMENT = re.compile(r"(?i)(\b(?:api[_-]?key|x-api-key|access[_-]?token|refresh[_-]?token|password|client[_-]?secret|authorization|cookie)[\"']?\s*[:=]\s*[\"']?)([^\s\"'<>;&,}]+)")
_QUERY = re.compile(r"([?&])([^=&#\s]+)=([^&#\s\"'<>]*)")
_USERINFO = re.compile(r"(?i)(https?://)([^\s/@]+)@")
_SAFE_ID = re.compile(r"[A-Za-z0-9_.:/+-]{1,200}")


class CaptureError(RuntimeError):
    """Persistence failed; no automatic retry of a potentially billed call."""


def _key(value):
    return re.sub(r"[^a-z0-9]+", "_", str(value).lower()).strip("_")


def sanitize_body(value):
    """Pure deterministic projection: {value, redactions, exact, policy}.

    Redaction descriptors contain only JSON pointers and rule names, never the
    removed value. Unknown Python objects are unavailable, never repr()-dumped.
    This excludes transport/env fields even if nested inside a provider body.
    """
    redactions, active = [], set()
    def changed(path, kind):
        redactions.append({"path": path or "/", "kind": kind})
    def string(text, path):
        def sub(pattern, replacement, kind):
            nonlocal text
            updated, count = pattern.subn(replacement, text)
            if count:
                changed(path, kind)
                text = updated
        sub(_CREDENTIAL, "[redacted]", "credential_pattern")
        sub(_BEARER, "Bearer [redacted]", "bearer_credential")
        sub(_ASSIGNMENT, lambda m: m[1] + "[redacted]", "credential_assignment")
        def query(m):
            name = _key(unquote(m[2]))
            if name in SECRET_KEYS or name in {"key", "auth", "signature", "sig", "session", "session_id", "x_amz_credential", "x_amz_signature", "x_amz_security_token"}:
                changed(path, "url_credential_parameter")
                return m[1] + m[2] + "=[redacted]"
            return m[0]
        text = _QUERY.sub(query, text)
        sub(_USERINFO, lambda m: m[1] + "[redacted]@", "url_userinfo")
        return text
    def walk(obj, path):
        if obj is None or type(obj) in (bool, int):
            return obj
        if type(obj) is float:
            if math.isfinite(obj):
                return obj
            changed(path, "nonfinite_unavailable")
            return None
        if isinstance(obj, str):
            return string(obj, path)
        if isinstance(obj, (list, tuple, dict)):
            if id(obj) in active:
                changed(path, "cycle_unavailable")
                return None
            active.add(id(obj))
            try:
                return container(obj, path)
            finally:
                active.remove(id(obj))
        changed(path, "unsupported_value_unavailable")
        return None
    def container(obj, path):
        if isinstance(obj, (list, tuple)):
            return [walk(v, f"{path}/{i}") for i, v in enumerate(obj)]
        if isinstance(obj, dict):
            result = {}
            for k, v in obj.items():
                if not isinstance(k, str):
                    changed(path, "nonstring_key_unavailable")
                    continue
                safe = string(k, path + "/<key>")
                pointer = path + "/" + safe.replace("~", "~0").replace("/", "~1")
                if safe in result:
                    changed(path, "redacted_key_collision_unavailable")
                    continue
                name = _key(k)
                if name in TRANSPORT_KEYS or name in SECRET_KEYS:
                    changed(pointer, "transport_excluded" if name in TRANSPORT_KEYS else "credential_field")
                    result[safe] = "[redacted]"
                else:
                    result[safe] = walk(v, pointer)
            return result
    clean = walk(value, "")
    return {"value": clean, "redactions": redactions, "exact": not redactions,
            "policy": "credential-and-transport-exclusion.v1",
            "limitation": "Pattern-based body redaction does not prove arbitrary content contains no secret; HTTP headers, cookies, environment and unknown object representations are excluded."}


def _json(value):
    return json.dumps(value, sort_keys=True, ensure_ascii=False, separators=(",", ":"), allow_nan=False).encode("utf-8")


def _dump_response(response):
    if response is None:
        return None, "unavailable"
    if isinstance(response, (dict, list, str, int, float, bool)):
        return response, "structured_value"
    dump = getattr(response, "model_dump", None)
    if callable(dump):
        try:
            return dump(mode="json"), "sdk_model_dump"
        except Exception:
            pass
    # Preserve only named provider fields; never serialize __dict__, a request,
    # headers, client objects, or repr() of an unknown SDK/transport object.
    out = {}
    for key in ("id", "model", "type", "role", "stop_reason", "stop_sequence", "content", "usage"):
        value = getattr(response, key, None)
        if value is not None:
            if key == "usage" and not isinstance(value, dict):
                value = {k: getattr(value, k) for k in ("input_tokens", "output_tokens", "cache_read_input_tokens", "cache_creation_input_tokens", "cache_creation", "server_tool_use", "service_tier", "inference_geo") if getattr(value, k, None) is not None}
            out[key] = value
    return out or None, "known_fields_projection" if out else "unavailable"


def response_record(response=None, error=None):
    """Available body and provider measurements; no transport object traversal."""
    partial = getattr(error, "response_record", None)
    if isinstance(partial, dict):
        return {k: partial.get(k) for k in ("text", "response_id", "stop_reason", "usage", "response", "stream_complete", "usage_complete")}, "partial_sdk_snapshot"
    body, source = _dump_response(response)
    if isinstance(body, dict):
        usage = body.get("usage")
        complete = isinstance(usage, dict) and all(type(usage.get(k)) is int and usage[k] >= 0 for k in ("input_tokens", "output_tokens"))
        return {"response_id": body.get("id"), "stop_reason": body.get("stop_reason"), "usage": usage,
                "response": body, "stream_complete": True, "usage_complete": True if complete else None}, source
    # Existing gateway adapters may add a friendly message around the SDK
    # exception. Follow only its explicit cause, never transport attributes.
    cause = error
    for _ in range(4):
        error_body = getattr(cause, "body", None)
        if isinstance(error_body, (dict, list, str)):
            break
        cause = getattr(cause, "__cause__", None)
        if cause is None:
            break
    if isinstance(error_body, (dict, list, str)):
        return {"response": None, "error_body": error_body, "response_id": None, "stop_reason": None,
                "usage": None, "stream_complete": False, "usage_complete": False}, "sdk_error_body"
    return {"response": {"value": body} if body is not None else None, "response_id": None, "stop_reason": None, "usage": None,
            "stream_complete": None, "usage_complete": None}, source


def _links(op):
    plan = (op.get("execution") or {}).get("plan") or {}
    origin = plan.get("origin") or {}
    out = {"operation_id": op["op_id"]}
    for key in ("prepared_id", "snapshot_id", "retry_parent", "action_id"):
        if op.get(key):
            out[key] = op[key]
    for key in ("doc_id", "revision", "deposition_id", "reading_id", "item_ref"):
        if isinstance(origin.get(key), (str, int)):
            out[key] = origin[key]
    return out


def _keep(op_id, phase, attempt_id, body):
    """Atomic immutable artifact, then idempotent note; no result_ref overwrite.

    A crash after rename but before note leaves a complete, hash-named orphan
    with its own operation/attempt linkage. inspect() can report it read-only.
    """
    import operations as ops
    import producers
    import vault
    raw = _json(body)
    digest = hashlib.sha256(raw).hexdigest()
    # The digest binds operation/call/attempt inside the record and stays
    # within existing artifact name bounds. Never overwrite an earlier body.
    name = f"capture-{phase}-{digest}.json"
    directory = producers.artifact_dir(op_id)
    if not directory.resolve().is_relative_to(Path(ops.cli.LOCAL_STATE).resolve()):
        raise CaptureError("Capture storage resolves outside the operation store.")
    directory.mkdir(parents=True, exist_ok=True)
    path = directory / name
    fd, temporary = tempfile.mkstemp(prefix=".capture-", dir=directory)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(raw); stream.flush(); os.fsync(stream.fileno())
        try:
            os.link(temporary, path)
        except FileExistsError:
            if path.is_symlink() or path.read_bytes() != raw:
                raise CaptureError("An immutable capture artifact differs from its content hash.")
        os.unlink(temporary)
        fd_dir = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd_dir)
        finally:
            os.close(fd_dir)
        for parent in (directory.parent, directory.parent.parent):
            fd_parent = os.open(parent, os.O_RDONLY)
            try:
                os.fsync(fd_parent)
            finally:
                os.close(fd_parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)
    kept = {"name": name, "sha256": digest, "bytes": len(raw)}
    capture = {"schema": SCHEMA, "phase": phase, "call_id": body["call_id"], "attempt_id": attempt_id,
               "artifact": kept, "outcome": body.get("outcome"), "request_artifact": body.get("request_artifact")}
    conn = ops._connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        duplicate = False
        for row in conn.execute("SELECT detail FROM operation_events WHERE op_id=? AND kind='note'", (op_id,)):
            existing = json.loads(row[0]).get("capture") or {}
            if existing.get("artifact") == kept:
                duplicate = True; break
        if not duplicate:
            ops._event(conn, op_id, "note", detail={"capture": capture})
            conn.execute("UPDATE operations SET updated_at=? WHERE op_id=?", (ops._now(), op_id))
        conn.execute("COMMIT")
        vault.mark_dirty()
    except BaseException:
        if conn.in_transaction:
            conn.execute("ROLLBACK")
        raise
    finally:
        conn.close()
    return kept


class Attempt:
    def __init__(self, op_id, **metadata):
        import operations as ops
        self.op = ops.get(op_id)
        if not self.op:
            raise CaptureError("The operation must exist before request capture.")
        self.meta = {k: v for k, v in metadata.items() if k in ("call_id", "attempt_id", "stage", "provider", "model", "started_at", "component")}
        if not all(_SAFE_ID.fullmatch(str(self.meta.get(k, ""))) for k in ("call_id", "attempt_id")):
            raise CaptureError("Stable call and attempt identities are required.")
        self.request_artifact = None
        self.blocked_before_dispatch = False

    def _body(self, phase, **fields):
        metadata = sanitize_body({**self.meta, "links": _links(self.op)})
        return {"schema": SCHEMA, "phase": phase, **metadata["value"], **fields,
                "metadata_redactions": metadata["redactions"]}

    def request(self, body):
        projected = sanitize_body(body)
        record = self._body("request", outcome="prepared", body_format="sdk_request_arguments",
                            body=projected["value"], capture={k: v for k, v in projected.items() if k != "value"},
                            unavailable=["http_wire_bytes", "transport_headers"],
                            cost_authorization="existing_operation_contract; capture grants no spending authority")
        try:
            self.request_artifact = _keep(self.op["op_id"], "request", self.meta["attempt_id"], record)
            return self.request_artifact
        except BaseException as exc:
            self.blocked_before_dispatch = True
            raise CaptureError("The exact available request could not be persisted; no SDK dispatch is permitted.") from exc

    def finish(self, response=None, error=None):
        import wordicon_cli as cli
        observed, source = response_record(response, error)
        projected = sanitize_body(observed)
        response_data = projected["value"]
        outcome = ("not_sent" if self.blocked_before_dispatch else "received" if error is None
                   else "partial" if observed.get("response") is not None or observed.get("text") else "unknown")
        receipt = self._body("response" if error is None else "failure", outcome=outcome,
            response=response_data, body_format=source, request_artifact=self.request_artifact,
            capture={k: v for k, v in projected.items() if k != "value"},
            error=sanitize_body(cli.sanitize_attempt_message(error))["value"] if error else None,
            error_class=type(error).__name__ if error else None,
            unavailable=[name for name, value in (("request_body", self.request_artifact), ("provider_response_id", observed.get("response_id")), ("usage", observed.get("usage"))) if value is None])
        try:
            kept = _keep(self.op["op_id"], receipt["phase"], self.meta["attempt_id"], receipt)
            if self.meta.get("provider") != "mock" and not self.blocked_before_dispatch:
                # OpenCase's explicit owner has its own bounded reservation and
                # settlement. Body capture can coexist without another charge.
                action = self.op.get("action_id") or ""
                if action != "investigate.opencase.question":
                    import operation_costs as costs
                    costs.settle(self.op["op_id"], "gateway", self.meta["attempt_id"], receipt,
                                 kept["sha256"], receipt_artifact=kept, guarded=False)
            return kept
        except BaseException as exc:
            failure = CaptureError("The provider outcome was not fully persisted or accounted; automatic replay is unsafe.")
            failure.response_record = observed
            raise failure from exc


def inspect(op_id):
    """Read-only artifact reconstruction, including fully written unlinked files."""
    import operations as ops
    import producers
    directory = producers.artifact_dir(op_id)
    indexed, gaps = {}, []
    db = ops.db_path()
    if db.is_file():
        conn = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
        try:
            for row in conn.execute("SELECT detail FROM operation_events WHERE op_id=? AND kind='note'", (op_id,)):
                value = json.loads(row[0]).get("capture") or {}
                if value.get("schema") == SCHEMA and isinstance(value.get("artifact"), dict):
                    name = value["artifact"].get("name")
                    if isinstance(name, str) and re.fullmatch(r"capture-(request|response|failure)-[0-9a-f]{64}\.json", name):
                        indexed[name] = value
                    else:
                        gaps.append({"kind": "invalid_capture_reference"})
        finally:
            conn.close()
    records = []
    for path in sorted(directory.glob("capture-*.json")) if directory.exists() else []:
        try:
            if not path.resolve().is_relative_to(directory.resolve()) or path.is_symlink():
                raise ValueError("capture path not owned")
            raw = path.read_bytes(); digest = hashlib.sha256(raw).hexdigest(); data = json.loads(raw)
            expected = (indexed.get(path.name, {}).get("artifact") or {}).get("sha256")
            if (expected and digest != expected) or not path.name.endswith("-" + digest + ".json") or data.get("links", {}).get("operation_id") != op_id or data.get("schema") != SCHEMA:
                raise ValueError("capture hash or identity mismatch")
            records.append({"artifact": {"name": path.name, "sha256": digest, "bytes": len(raw)}, "linked": path.name in indexed, "record": data})
            if path.name not in indexed:
                gaps.append({"kind": "artifact_link_missing", "name": path.name})
        except Exception:
            gaps.append({"kind": "artifact_unreadable_or_changed", "name": path.name})
    for name in indexed:
        if not (directory / name).is_file():
            gaps.append({"kind": "artifact_missing", "name": name})
    outcomes = {r["record"].get("attempt_id") for r in records if r["record"].get("phase") in ("response", "failure")}
    for row in records:
        record = row["record"]
        if record.get("phase") == "request" and record.get("attempt_id") not in outcomes:
            gaps.append({"kind": "request_outcome_unavailable", "name": row["artifact"]["name"],
                         "attempt_id": record.get("attempt_id"), "delivery": "unknown; no automatic replay"})
    return {"operation_id": op_id, "records": records, "gaps": gaps,
            "replay": "never; inspection performs no dispatch or accounting mutation"}
