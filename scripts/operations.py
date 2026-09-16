"""The operations store (workspace-v2 slice D, instructions §8).

SQLite is the authority on every operation the application starts — a
model run through /api/jobs or a Start from the workspace, a reading by
the readers, later a producer investigation. The in-process JOBS table in
server.py is a projection of it (progress and the shaped result while the
process lives); nothing decides an operation's fate from JOBS alone.

One row per operation: its id, the request key that reserved it (unique —
the same key with the same execution fingerprint returns the same row, the
same key with a different one is refused), the action and the registry
version it was started under, the frozen proposal and snapshot it was
built from, the fingerprint of the FULL execution request (action, scope,
inputs, lane, model, adapter version — not just the selected text), its
configuration (never a secret: a credential is a reference), its status,
local state, what the producer said when known, the ids of its results,
the attempt it retries and its last error.

One row per event, in the order they happened: reserved, claimed, resumed,
a stage reached, a DISPATCH INTENT persisted before every potentially
billed stage and every actual HTTP attempt, the end of each with its
outcome, the result, completion or failure — so that after an interruption
the record can say which of the six cases it is in (the recovery table in
§8) instead of guessing, and never replays work that may have been sent.

One dispatcher per store: a process lock (fcntl) on operations.lock; a
process that cannot take it does not dispatch, and says so. queued →
claimed is one atomic UPDATE. Transactions are short; no lock is held
across a network wait.
"""
from __future__ import annotations

import hashlib
import json
import os
import socket
import sqlite3
import threading
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import wordicon_cli as cli

DB_NAME = "operations.sqlite3"
LOCK_NAME = "operations.lock"
SCHEMA_VERSION = 1
BUSY_TIMEOUT_S = 5.0

STATUSES = ("queued", "claimed", "running", "complete", "failed", "unknown")
KINDS = ("job", "reading", "lookup", "investigation")
EVENT_KINDS = ("reserved", "claimed", "resumed", "stage", "stage_intent", "stage_end", "attempt_intent", "attempt_end",
               "result", "complete", "failed", "unknown", "recover", "reconciled", "attempt_from", "note")

# The recovery table (§8), by name. A reader of an operation sees one of
# these, derived from the persisted events — never from memory.
RECOVERY = {
    "never_dispatched": "Reserved and never dispatched: nothing was sent. It can be resumed under its unchanged plan.",
    "delivery_unknown": "A dispatch was recorded and its outcome was not: it may have been sent and may even have run. It is not sent again by itself.",
    "reply_received_result_missing": "The provider answered and the result was not persisted before the interruption: outcome unknown; not sent again by itself.",
    "result_persisted_link_missing": "A result was persisted and the operation was not marked complete: reconciled from the result's own stable id.",
    "component_persisted": "Some components persisted their results; the operation as a whole did not complete. What is persisted is kept; the whole is not repeated by itself.",
    "complete": "Complete; its result is on disk under its own id.",
    "failed": "Failed; the reason is recorded.",
}


class OperationsError(Exception):
    def __init__(self, message: str, status: int = 400, existing: dict | None = None):
        super().__init__(message)
        self.status = status
        self.existing = existing


# ---- the file -------------------------------------------------------------------

def db_path() -> Path:
    return Path(cli.LOCAL_STATE) / DB_NAME


def lock_path() -> Path:
    return Path(cli.LOCAL_STATE) / LOCK_NAME


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_S, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # the rollback journal, not WAL: the Vault copies the tree with writers
    # drained, and a read of the store (a Home paint, a listing) must change
    # no byte of it — opening a WAL database rewrites its header
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=%d" % int(BUSY_TIMEOUT_S * 1000))
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS operations (
            op_id            TEXT PRIMARY KEY,
            kind             TEXT NOT NULL,
            request_key      TEXT NOT NULL UNIQUE,
            action_id        TEXT NOT NULL DEFAULT '',
            registry_version TEXT NOT NULL DEFAULT '',
            prepared_id      TEXT NOT NULL DEFAULT '',
            snapshot_id      TEXT NOT NULL DEFAULT '',
            fingerprint      TEXT NOT NULL,
            execution        TEXT NOT NULL,
            config           TEXT NOT NULL DEFAULT '{}',
            status           TEXT NOT NULL,
            local_state      TEXT NOT NULL DEFAULT '',
            producer_state   TEXT,
            result_ref       TEXT,
            retry_parent     TEXT,
            last_error       TEXT,
            dispatcher       TEXT,
            legacy_job_id    TEXT,
            created_at       TEXT NOT NULL,
            updated_at       TEXT NOT NULL,
            claimed_at       TEXT,
            finished_at      TEXT
        );
        CREATE INDEX IF NOT EXISTS operations_created ON operations (created_at DESC, op_id);
        CREATE INDEX IF NOT EXISTS operations_status ON operations (status, created_at DESC);
        CREATE TABLE IF NOT EXISTS operation_events (
            seq         INTEGER PRIMARY KEY AUTOINCREMENT,
            op_id       TEXT NOT NULL,
            at          TEXT NOT NULL,
            kind        TEXT NOT NULL,
            stage       TEXT NOT NULL DEFAULT '',
            attempt     INTEGER,
            upstream_id TEXT NOT NULL DEFAULT '',
            outcome     TEXT NOT NULL DEFAULT '',
            detail      TEXT NOT NULL DEFAULT '{}'
        );
        CREATE INDEX IF NOT EXISTS operation_events_op ON operation_events (op_id, seq);
        INSERT OR IGNORE INTO meta (key, value) VALUES ('schema', '1');
    """)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def canonical(obj) -> str:
    return json.dumps(obj, sort_keys=True, ensure_ascii=False, separators=(",", ":"))


def fingerprint(execution: dict) -> str:
    """The FULL execution request: what will run, on what, with which
    material options, through which lane and adapter version. Two requests
    with the same fingerprint would do the same work; a request key may
    return an operation only for the same fingerprint."""
    return "xf_" + hashlib.sha256(canonical(execution).encode("utf-8")).hexdigest()[:32]


def new_op_id() -> str:
    return "op_" + uuid.uuid4().hex[:16]


def _row(r) -> dict:
    if r is None:
        return None
    d = dict(r)
    for k in ("execution", "config", "producer_state", "result_ref"):
        v = d.get(k)
        if v:
            try:
                d[k] = json.loads(v)
            except json.JSONDecodeError:
                pass
    return d


# ---- reservation and claim ------------------------------------------------------

def reserve(*, request_key: str, kind: str, execution: dict, config: dict | None = None, op_id: str | None = None,
            action_id: str = "", registry_version: str = "", prepared_id: str = "", snapshot_id: str = "",
            retry_parent: str | None = None, legacy_job_id: str | None = None) -> tuple[dict, bool]:
    """One row per request key. Returns (row, created). The same key with
    the same execution fingerprint returns the existing row (a retry of a
    lost reply); the same key with a different fingerprint is refused, with
    the existing row, because the meaning of the request changed."""
    if kind not in KINDS:
        raise OperationsError(f"unknown operation kind {kind!r}", 400)
    request_key = str(request_key or "")[:120]
    if not request_key:
        raise OperationsError("an operation is reserved under a request key", 400)
    fp = fingerprint(execution)
    op_id = op_id or new_op_id()
    now = _now()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            prior = conn.execute("SELECT * FROM operations WHERE request_key = ?", (request_key,)).fetchone()
            if prior is not None:
                conn.execute("COMMIT")
                if prior["fingerprint"] != fp:
                    raise OperationsError("this request key was already used for a different request — a retry must carry "
                                          "the same one, and a changed request needs a new key", 409, existing=_row(prior))
                return _row(prior), False
            conn.execute(
                "INSERT INTO operations (op_id, kind, request_key, action_id, registry_version, prepared_id, snapshot_id, "
                "fingerprint, execution, config, status, retry_parent, legacy_job_id, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'queued', ?, ?, ?, ?)",
                (op_id, kind, request_key, action_id, registry_version, prepared_id, snapshot_id, fp, canonical(execution),
                 canonical(config or {}), retry_parent, legacy_job_id, now, now))
            _event(conn, op_id, "reserved", detail={"fingerprint": fp, "retry_parent": retry_parent}, now=now)
            if retry_parent:
                _event(conn, retry_parent, "attempt_from", detail={"new_op_id": op_id}, now=now)
            conn.execute("COMMIT")
        except Exception:
            try:
                conn.execute("ROLLBACK")
            except sqlite3.OperationalError:
                pass
            raise
        return _row(conn.execute("SELECT * FROM operations WHERE op_id = ?", (op_id,)).fetchone()), True
    finally:
        conn.close()


def claim(op_id: str, dispatcher: str) -> bool:
    """queued → claimed, atomically; false when it was not queued (someone
    else has it, or it is past that)."""
    now = _now()
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        cur = conn.execute("UPDATE operations SET status = 'claimed', dispatcher = ?, claimed_at = ?, updated_at = ? "
                           "WHERE op_id = ? AND status = 'queued'", (dispatcher, now, now, op_id))
        if cur.rowcount == 1:
            _event(conn, op_id, "claimed", detail={"dispatcher": dispatcher}, now=now)
        conn.execute("COMMIT")
        return cur.rowcount == 1
    finally:
        conn.close()


def _event(conn, op_id: str, kind: str, *, stage: str = "", attempt=None, upstream_id: str = "", outcome: str = "",
           detail: dict | None = None, now: str | None = None) -> int:
    assert kind in EVENT_KINDS, kind
    cur = conn.execute("INSERT INTO operation_events (op_id, at, kind, stage, attempt, upstream_id, outcome, detail) "
                       "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (op_id, now or _now(), kind, str(stage or "")[:80], attempt, str(upstream_id or "")[:200],
                        str(outcome or "")[:40], canonical(_scrub(detail or {}))))
    return int(cur.lastrowid)


_SECRET_KEYS = ("key", "token", "secret", "password", "authorization", "cookie", "credential")


def _scrub(detail: dict) -> dict:
    """No secret enters the record: a key that looks like one becomes a
    reference to the fact that it was there."""
    out = {}
    for k, v in (detail or {}).items():
        lk = str(k).lower()
        if any(s in lk for s in _SECRET_KEYS) and not lk.endswith("_ref") and lk != "request_key":
            out[k] = "<credential reference>"
        elif isinstance(v, dict):
            out[k] = _scrub(v)
        elif isinstance(v, str):
            out[k] = v[:2000]
        else:
            out[k] = v
    return out


def event(op_id: str, kind: str, **fields) -> int:
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        seq = _event(conn, op_id, kind, **fields)
        conn.execute("UPDATE operations SET updated_at = ? WHERE op_id = ?", (_now(), op_id))
        conn.execute("COMMIT")
        return seq
    finally:
        conn.close()


def mark(op_id: str, status: str | None = None, *, local_state: str | None = None, result_ref: dict | None = None,
         last_error: str | None = None, producer_state: dict | None = None, event_kind: str | None = None,
         detail: dict | None = None) -> None:
    """A short transaction: the row's state and, when named, the event that
    explains it."""
    if status is not None and status not in STATUSES:
        raise OperationsError(f"unknown status {status!r}", 400)
    now = _now()
    sets, args = ["updated_at = ?"], [now]
    if status is not None:
        sets.append("status = ?"); args.append(status)
        if status in ("complete", "failed", "unknown"):
            sets.append("finished_at = ?"); args.append(now)
    if local_state is not None:
        sets.append("local_state = ?"); args.append(str(local_state)[:500])
    if result_ref is not None:
        sets.append("result_ref = ?"); args.append(canonical(result_ref))
    if last_error is not None:
        sets.append("last_error = ?"); args.append(str(last_error)[:2000])
    if producer_state is not None:
        sets.append("producer_state = ?"); args.append(canonical(_scrub(producer_state)))
    args.append(op_id)
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        conn.execute(f"UPDATE operations SET {', '.join(sets)} WHERE op_id = ?", args)
        kind = event_kind or ({"complete": "complete", "failed": "failed", "unknown": "unknown", "running": "stage"}.get(status or "") or None)
        if kind:
            _event(conn, op_id, kind, detail=detail or ({"error": last_error} if last_error else {}), now=now)
        conn.execute("COMMIT")
    finally:
        conn.close()


# ---- reads ------------------------------------------------------------------------

def get(op_id: str) -> dict | None:
    conn = _connect()
    try:
        r = conn.execute("SELECT * FROM operations WHERE op_id = ? OR legacy_job_id = ?", (op_id, op_id)).fetchone()
        if r is None:
            return None
        d = _row(r)
        d["events_count"] = int(conn.execute("SELECT COUNT(*) FROM operation_events WHERE op_id = ?", (d["op_id"],)).fetchone()[0])
        return d
    finally:
        conn.close()


def events(op_id: str, limit: int = 500) -> list[dict]:
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM operation_events WHERE op_id = ? ORDER BY seq ASC LIMIT ?", (op_id, int(limit))).fetchall()
        out = []
        for r in rows:
            d = dict(r)
            try:
                d["detail"] = json.loads(d["detail"] or "{}")
            except json.JSONDecodeError:
                d["detail"] = {}
            out.append(d)
        return out
    finally:
        conn.close()


def list_ops(limit: int = 50, cursor: str = "", status: str | None = None, kind: str | None = None) -> dict:
    limit = max(1, min(int(limit or 50), 200))
    conn = _connect()
    try:
        where, args = [], []
        if status:
            where.append("status = ?"); args.append(status)
        if kind:
            where.append("kind = ?"); args.append(kind)
        if cursor:
            try:
                c_at, c_id = cursor.split("|", 1)
            except ValueError:
                raise OperationsError("bad cursor", 400)
            where.append("(created_at < ? OR (created_at = ? AND op_id < ?))"); args += [c_at, c_at, c_id]
        sql = "SELECT * FROM operations" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY created_at DESC, op_id DESC LIMIT ?"
        args.append(limit + 1)
        rows = [_row(r) for r in conn.execute(sql, args).fetchall()]
        more = len(rows) > limit
        rows = rows[:limit]
        total = int(conn.execute("SELECT COUNT(*) FROM operations").fetchone()[0])
        return {"operations": rows, "total": total, "population": "every operation this store holds",
                "next_cursor": (f"{rows[-1]['created_at']}|{rows[-1]['op_id']}" if more and rows else None)}
    finally:
        conn.close()


def counts() -> dict:
    conn = _connect()
    try:
        out = {s: 0 for s in STATUSES}
        for r in conn.execute("SELECT status, COUNT(*) AS n FROM operations GROUP BY status").fetchall():
            out[r["status"]] = int(r["n"])
        return out
    finally:
        conn.close()


# ---- the dispatch boundary --------------------------------------------------------

def attach(gateway, op_id: str) -> None:
    """Puts the operation's boundary on a gateway INSTANCE: every stage
    call (complete, complete_with_search, complete_with_image) leaves an
    intent event before it goes and an end event after; the attempt loop
    of a provider gateway leaves the same pair per real HTTP attempt. The
    text never enters the record — the stage's name (the prompt's own first
    line), the attempt number, the outcome and the exception class do."""
    gateway.dispatch_hook = lambda kind, **f: _hook(op_id, kind, **f)
    for name in ("complete", "complete_with_search", "complete_with_image"):
        original = getattr(gateway, name, None)
        if original is None or getattr(original, "_op_wrapped", False):
            continue

        def wrapped(*args, _orig=original, _name=name, **kwargs):
            prompt = args[0] if args else kwargs.get("prompt", "")
            stage = _stage_of(prompt)
            seq = event(op_id, "stage_intent", stage=stage, detail={"call": _name})
            try:
                out = _orig(*args, **kwargs)
            except BaseException as e:  # noqa: BLE001 — the record first, then the same exception
                event(op_id, "stage_end", stage=stage, outcome="error", detail={"call": _name, "intent_seq": seq, "exception": type(e).__name__, "message": str(e)[:300]})
                raise
            event(op_id, "stage_end", stage=stage, outcome="ok", detail={"call": _name, "intent_seq": seq})
            return out
        wrapped._op_wrapped = True
        setattr(gateway, name, wrapped)


def _stage_of(prompt) -> str:
    first = str(prompt or "").split("\n", 1)[0].strip()
    return first[:80]


def _hook(op_id: str, kind: str, **f) -> None:
    if kind == "attempt_intent":
        event(op_id, "attempt_intent", stage=f.get("stage", ""), attempt=f.get("attempt"), detail={"started_at": f.get("started_at", "")})
    elif kind == "attempt_end":
        event(op_id, "attempt_end", stage=f.get("stage", ""), attempt=f.get("attempt"), outcome=f.get("outcome", ""),
              detail={k: v for k, v in f.items() if k in ("exception", "status_code", "duration_s", "outcome_detail", "retry_after_s", "run_id", "component")})


# ---- the recovery table: what the events say happened -----------------------------------

def analyse(op: dict, evs: list[dict], results_dir: Path | None = None, receipts_dir: Path | None = None) -> dict:
    """Which row of the recovery table an interrupted operation is in,
    derived from persisted events and persisted result files only."""
    intents = [e for e in evs if e["kind"] in ("stage_intent", "attempt_intent")]
    ends = [e for e in evs if e["kind"] in ("stage_end", "attempt_end")]
    run_ids = sorted({str(e["detail"].get("run_id") or "") for e in ends} - {""})
    persisted = []
    if results_dir is not None:
        for rid in run_ids:
            if (Path(results_dir) / f"{rid}.json").exists():
                persisted.append(rid)
    if receipts_dir is not None:
        for rid in run_ids:
            if (Path(receipts_dir) / f"receipt_{rid}.json").exists() and rid not in persisted:
                persisted.append(rid)
    if op["status"] == "complete":
        return {"case": "complete", "why": RECOVERY["complete"], "persisted": persisted}
    if op["status"] == "failed":
        return {"case": "failed", "why": RECOVERY["failed"], "persisted": persisted}
    if not intents:
        return {"case": "never_dispatched", "why": RECOVERY["never_dispatched"], "persisted": []}
    # an intent whose end never came: per (call kind, stage, attempt), more intents than ends
    from collections import Counter
    n_int = Counter((e["kind"].replace("_intent", ""), e["stage"], e["attempt"]) for e in intents)
    n_end = Counter((e["kind"].replace("_end", ""), e["stage"], e["attempt"]) for e in ends)
    open_intents = sum(max(0, n - n_end.get(k, 0)) for k, n in n_int.items())
    if open_intents:
        return {"case": "delivery_unknown", "why": RECOVERY["delivery_unknown"], "persisted": persisted, "open_intents": open_intents}
    if persisted:
        return {"case": "result_persisted_link_missing" if op["kind"] == "job" and len(persisted) == 1 else "component_persisted",
                "why": RECOVERY["result_persisted_link_missing" if len(persisted) == 1 else "component_persisted"], "persisted": persisted}
    return {"case": "reply_received_result_missing", "why": RECOVERY["reply_received_result_missing"], "persisted": []}


def reconcile(dispatcher: str, results_dir: Path | None = None, receipts_dir: Path | None = None) -> list[dict]:
    """At startup: every operation a dead process left claimed or running is
    placed in its row of the recovery table, from the record. Nothing is
    dispatched here; a resumable operation goes back to queued and the
    dispatcher decides. Returns what changed."""
    changed = []
    conn = _connect()
    try:
        rows = [_row(r) for r in conn.execute("SELECT * FROM operations WHERE status IN ('claimed', 'running')").fetchall()]
    finally:
        conn.close()
    for op in rows:
        evs = events(op["op_id"])
        a = analyse(op, evs, results_dir, receipts_dir)
        now = _now()
        conn = _connect()
        try:
            conn.execute("BEGIN IMMEDIATE")
            if a["case"] == "never_dispatched":
                conn.execute("UPDATE operations SET status = 'queued', dispatcher = NULL, claimed_at = NULL, local_state = ?, updated_at = ? WHERE op_id = ?",
                             ("Queued again after an interruption — nothing had been sent", now, op["op_id"]))
                new = "queued"
            elif a["case"] in ("result_persisted_link_missing",):
                conn.execute("UPDATE operations SET status = 'complete', result_ref = ?, local_state = ?, finished_at = ?, updated_at = ? WHERE op_id = ?",
                             (canonical({"trace_ids": a["persisted"], "reconciled": True}), "Reconciled from the persisted result after an interruption", now, now, op["op_id"]))
                new = "complete"
            else:
                conn.execute("UPDATE operations SET status = 'unknown', last_error = ?, local_state = ?, finished_at = ?, updated_at = ? WHERE op_id = ?",
                             (a["why"], "Interrupted", now, now, op["op_id"]))
                new = "unknown"
            _event(conn, op["op_id"], "reconciled", detail={"by": dispatcher, "case": a["case"], "persisted": a.get("persisted", []), "was": op["status"], "now": new}, now=now)
            conn.execute("COMMIT")
        finally:
            conn.close()
        changed.append({"op_id": op["op_id"], "was": op["status"], "now": new, "case": a["case"], "persisted": a.get("persisted", [])})
    return changed


def queued(kind: str | None = None) -> list[dict]:
    conn = _connect()
    try:
        sql = "SELECT * FROM operations WHERE status = 'queued'" + (" AND kind = ?" if kind else "") + " ORDER BY created_at ASC"
        return [_row(r) for r in conn.execute(sql, (kind,) if kind else ()).fetchall()]
    finally:
        conn.close()


# ---- the dispatcher lock ------------------------------------------------------------

class DispatcherLock:
    """One dispatcher per store. The lock is a file the process holds for its
    lifetime; a second process on the same store sees it held and does not
    dispatch. The token names the holder in every claim it makes."""

    def __init__(self):
        self.fd = None
        self.token = f"{socket.gethostname()}:{os.getpid()}:{uuid.uuid4().hex[:8]}"
        self.held = False
        self.attempted = False
        self.why = "not attempted yet: this process has not dispatched anything"

    def acquire(self) -> bool:
        """Taken when a process is about to dispatch, never merely on import:
        a process that only reads the store (a Home paint, a listing) must
        leave the store's directory as it found it."""
        self.attempted = True
        if self.held:
            return True
        try:
            import fcntl
        except ImportError:  # pragma: no cover — not a POSIX platform
            self.why = "no file locking on this platform"
            return False
        path = lock_path()
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            self.fd = os.open(str(path), os.O_RDWR | os.O_CREAT, 0o600)
            fcntl.flock(self.fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as e:
            self.why = f"another process holds the dispatcher lock ({path.name}): {e.__class__.__name__}"
            if self.fd is not None:
                os.close(self.fd)
                self.fd = None
            return False
        os.ftruncate(self.fd, 0)
        os.write(self.fd, (self.token + "\n" + _now() + "\n").encode("utf-8"))
        self.held = True
        return True

    def release(self) -> None:
        if self.fd is not None:
            try:
                import fcntl
                fcntl.flock(self.fd, fcntl.LOCK_UN)
            except Exception:  # noqa: BLE001
                pass
            os.close(self.fd)
            self.fd = None
        self.held = False

    def status(self) -> dict:
        return {"held": self.held, "token": self.token if self.held else "", "why": self.why, "path": str(lock_path())}
