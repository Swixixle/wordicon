"""The writer's notebook — the authoritative store for what he writes.

Notebook stage B (the owner's brief of 2026-09-09: "reliable writing, saving
and reopening come before the broader navigation and naming cleanup").

Until this module the only copy of a draft was the browser's session store:
one record, one browser, rewritten on every keystroke, gone with the profile.
Submitting a run wrote the words to the append-only inputs log — a record of
what was SENT, never a document that could be reopened and worked on. This
is the document store the room was missing.

What it is. One SQLite file, ``local_state/notebook.sqlite3``, derived from
``cli.LOCAL_STATE`` at call time so the suite's store redirection covers it
and the Vault stages it with everything else (it is not in the exclusion
list; the rollback journal is the default, so a staged copy taken with the
writers drained is consistent). Three tables:

``documents``     stable id, title, whether the title is his or derived,
                  the exact body, an integer revision, a fingerprint of the
                  stored fields, created and saved times in UTC.
``save_requests`` every save the server accepted, by the request id the
                  browser minted for it: a retry whose reply was lost gets
                  the SAME acknowledgement back, and a request id reused
                  for different data is an error, not a second write.
``checkpoints``   a copy of the document at a revision, with the reason it
                  was taken (an explicit save, a new page, a timed interval,
                  a replacement about to happen). Never pruned here.

Rules the code keeps rather than asks for. A document's identity is its id;
never its title, never a hash of its text. The body is stored exactly —
no trimming, no quote substitution, no normalization; an empty body is a
valid document. A save names the revision and fingerprint it was based on
and is refused (409) when the head has moved, with the head returned so the
browser can show both; it never overwrites. Every write is one short
``BEGIN IMMEDIATE`` transaction: the retry check, the conditional update,
the request row and the checkpoint commit together or not at all. A
checkpoint of a revision that is no longer the head is refused; a
checkpoint of the head that already exists for the same reason is returned,
not duplicated; taking one never bumps the content revision. Nothing here
calls a model.
"""
from __future__ import annotations

import hashlib
import json
import re
import sqlite3
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wordicon_cli as cli  # noqa: E402

SCHEMA_VERSION = 1
DB_NAME = "notebook.sqlite3"
BUSY_TIMEOUT_S = 5.0
ID_RX = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
TITLE_MAX = 200
REASONS = ("save", "new", "interval", "replace", "open", "migration", "recovery")
UNTITLED = "Untitled"


class NotebookError(Exception):
    """A request the store refuses. `status` is the HTTP status the route
    answers with; `head` (on a conflict) is the current document."""

    def __init__(self, message: str, status: int = 400, head: dict | None = None):
        super().__init__(message)
        self.status = status
        self.head = head


# ---- the file ---------------------------------------------------------------

def db_path() -> Path:
    return Path(cli.LOCAL_STATE) / DB_NAME


def _connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=BUSY_TIMEOUT_S, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA synchronous=FULL")
    conn.execute("PRAGMA busy_timeout=%d" % int(BUSY_TIMEOUT_S * 1000))
    _ensure_schema(conn)
    return conn


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(f"""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS documents (
            doc_id          TEXT PRIMARY KEY,
            title           TEXT NOT NULL DEFAULT '',
            title_is_manual INTEGER NOT NULL DEFAULT 0,
            body            TEXT NOT NULL DEFAULT '',
            revision        INTEGER NOT NULL,
            fingerprint     TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            saved_at        TEXT NOT NULL,
            origin          TEXT NOT NULL DEFAULT ''
        );
        CREATE INDEX IF NOT EXISTS documents_saved_at ON documents (saved_at DESC, doc_id);
        CREATE TABLE IF NOT EXISTS save_requests (
            request_id  TEXT PRIMARY KEY,
            doc_id      TEXT NOT NULL,
            fingerprint TEXT NOT NULL,
            revision    INTEGER NOT NULL,
            saved_at    TEXT NOT NULL
        );
        CREATE TABLE IF NOT EXISTS checkpoints (
            checkpoint_id   TEXT PRIMARY KEY,
            doc_id          TEXT NOT NULL,
            revision        INTEGER NOT NULL,
            reason          TEXT NOT NULL,
            title           TEXT NOT NULL,
            title_is_manual INTEGER NOT NULL,
            body            TEXT NOT NULL,
            fingerprint     TEXT NOT NULL,
            created_at      TEXT NOT NULL,
            UNIQUE (doc_id, revision, reason)
        );
        INSERT OR IGNORE INTO meta (key, value) VALUES ('schema', '{SCHEMA_VERSION}');
    """)


def _now() -> str:
    # Microseconds, on purpose: two saves inside one second are two events,
    # and "newest first" has to be able to tell them apart. ISO 8601 UTC, so
    # the strings sort as the times do.
    return cli._now_precise()


# ---- identity and fingerprint ----------------------------------------------

def new_id() -> str:
    return "doc_" + uuid.uuid4().hex


def fingerprint(title: str, title_is_manual: bool, body: str) -> str:
    """A concurrency guard over the stored fields, canonical and stable.
    Never an identity: two documents with the same words are two documents."""
    canon = json.dumps({"b": body, "m": bool(title_is_manual), "t": title},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return "fp_" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:32]


def auto_title(body: str) -> str:
    """The first non-empty line, readable, cut at TITLE_MAX; 'Untitled' for
    whitespace. Derives from the body and never alters it."""
    for line in (body or "").splitlines():
        t = " ".join(line.split())
        if t:
            return t[:TITLE_MAX]
    return UNTITLED


def display_title(row) -> str:
    t = (row["title"] or "").strip() if row is not None else ""
    return t if t else auto_title(row["body"] if row is not None else "")


def _check_id(value, what: str) -> str:
    if not isinstance(value, str) or not ID_RX.match(value):
        raise NotebookError(f"{what} must be 8–64 letters, digits, '_' or '-'", 400)
    return value


def _check_text(value, what: str, limit: int | None = None) -> str:
    if not isinstance(value, str):
        raise NotebookError(f"{what} must be text", 400)
    if limit is not None and len(value) > limit:
        raise NotebookError(f"{what} is longer than {limit} characters", 400)
    return value


def _doc_dict(row, with_body: bool = True) -> dict:
    d = {
        "doc_id": row["doc_id"],
        "title": row["title"],
        "title_is_manual": bool(row["title_is_manual"]),
        "display_title": display_title(row),
        "revision": int(row["revision"]),
        "fingerprint": row["fingerprint"],
        "created_at": row["created_at"],
        "saved_at": row["saved_at"],
        "origin": row["origin"],
    }
    if with_body:
        d["body"] = row["body"]
    else:
        body = row["body"] or ""
        first = next((" ".join(l.split()) for l in body.splitlines() if l.strip()), "")
        d["preview"] = first[:160]
        d["chars"] = len(body)
        d["words"] = len(body.split())
    return d


# ---- reads ------------------------------------------------------------------

def get(doc_id: str) -> dict | None:
    _check_id(doc_id, "document id")
    conn = _connect()
    try:
        row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
        return _doc_dict(row) if row else None
    finally:
        conn.close()


def list_documents(q: str = "", cursor: str = "", limit: int = 50) -> dict:
    """Newest saved first. `q` matches title or body, case-insensitively,
    as plain text (no wildcards from the caller). The cursor is the last
    row's saved_at and id, so a page never repeats or skips a row that was
    saved while paging."""
    limit = max(1, min(int(limit or 50), 200))
    q = _check_text(q or "", "search", 500)
    conn = _connect()
    try:
        where, args = [], []
        if q.strip():
            needle = "%" + q.strip().lower().replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_") + "%"
            where.append("(lower(title) LIKE ? ESCAPE '\\' OR lower(body) LIKE ? ESCAPE '\\')")
            args += [needle, needle]
        if cursor:
            try:
                c_saved, c_id = cursor.split("|", 1)
            except ValueError:
                raise NotebookError("bad cursor", 400)
            where.append("(saved_at < ? OR (saved_at = ? AND doc_id < ?))")
            args += [c_saved, c_saved, c_id]
        sql = "SELECT * FROM documents"
        if where:
            sql += " WHERE " + " AND ".join(where)
        sql += " ORDER BY saved_at DESC, doc_id DESC LIMIT ?"
        args.append(limit + 1)
        rows = conn.execute(sql, args).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        total = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        out = {"documents": [_doc_dict(r, with_body=False) for r in rows],
               "total": int(total), "population": "every document in this notebook",
               "query": q, "next_cursor": None}
        if more and rows:
            last = rows[-1]
            out["next_cursor"] = f"{last['saved_at']}|{last['doc_id']}"
        return out
    finally:
        conn.close()


def list_checkpoints(doc_id: str) -> list[dict]:
    _check_id(doc_id, "document id")
    conn = _connect()
    try:
        rows = conn.execute(
            "SELECT checkpoint_id, doc_id, revision, reason, title, title_is_manual, fingerprint, "
            "created_at, length(body) AS chars FROM checkpoints WHERE doc_id = ? "
            "ORDER BY revision DESC, created_at DESC", (doc_id,)).fetchall()
        return [{"checkpoint_id": r["checkpoint_id"], "doc_id": r["doc_id"], "revision": int(r["revision"]),
                 "reason": r["reason"], "title": r["title"], "title_is_manual": bool(r["title_is_manual"]),
                 "fingerprint": r["fingerprint"], "created_at": r["created_at"], "chars": int(r["chars"])}
                for r in rows]
    finally:
        conn.close()


def get_checkpoint(doc_id: str, checkpoint_id: str) -> dict | None:
    _check_id(doc_id, "document id")
    _check_id(checkpoint_id, "checkpoint id")
    conn = _connect()
    try:
        r = conn.execute("SELECT * FROM checkpoints WHERE doc_id = ? AND checkpoint_id = ?",
                         (doc_id, checkpoint_id)).fetchone()
        if not r:
            return None
        return {"checkpoint_id": r["checkpoint_id"], "doc_id": r["doc_id"], "revision": int(r["revision"]),
                "reason": r["reason"], "title": r["title"], "title_is_manual": bool(r["title_is_manual"]),
                "body": r["body"], "fingerprint": r["fingerprint"], "created_at": r["created_at"]}
    finally:
        conn.close()


# ---- writes -----------------------------------------------------------------

def _head_dict(row) -> dict:
    return _doc_dict(row)


def _insert_checkpoint(conn, row, reason: str, now: str) -> dict:
    """A copy of the head at its revision, once per (document, revision,
    reason). Returns the existing one when it is already there."""
    existing = conn.execute(
        "SELECT checkpoint_id, created_at FROM checkpoints WHERE doc_id = ? AND revision = ? AND reason = ?",
        (row["doc_id"], row["revision"], reason)).fetchone()
    if existing:
        return {"checkpoint_id": existing["checkpoint_id"], "revision": int(row["revision"]),
                "reason": reason, "created_at": existing["created_at"], "created": False}
    cid = "ckp_" + uuid.uuid4().hex[:20]
    conn.execute(
        "INSERT INTO checkpoints (checkpoint_id, doc_id, revision, reason, title, title_is_manual, body, "
        "fingerprint, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cid, row["doc_id"], row["revision"], reason, row["title"], row["title_is_manual"],
         row["body"], row["fingerprint"], now))
    return {"checkpoint_id": cid, "revision": int(row["revision"]), "reason": reason,
            "created_at": now, "created": True}


def save(doc_id: str, *, title: str, title_is_manual: bool, body: str, base_revision: int,
         base_fingerprint: str, request_id: str, checkpoint_reason: str | None = None,
         origin: str = "") -> dict:
    """One save, one transaction. Creates at revision 1 when base_revision is
    0 and the document is absent; otherwise updates only when the base
    revision AND fingerprint match the head. A repeat of an accepted
    request id with the same data returns the same acknowledgement; with
    different data it is an error. Unchanged content does not bump the
    revision. An explicit checkpoint rides in the same transaction."""
    _check_id(doc_id, "document id")
    _check_id(request_id, "request id")
    title = _check_text(title, "title", TITLE_MAX)
    body = _check_text(body, "body")
    if not isinstance(base_revision, int) or isinstance(base_revision, bool) or base_revision < 0:
        raise NotebookError("base_revision must be a non-negative integer", 400)
    base_fingerprint = _check_text(base_fingerprint or "", "base_fingerprint", 100)
    if checkpoint_reason is not None:
        if checkpoint_reason not in REASONS:
            raise NotebookError(f"unknown checkpoint reason {checkpoint_reason!r}", 400)
    origin = _check_text(origin or "", "origin", 100)
    title_is_manual = bool(title_is_manual)
    fp = fingerprint(title, title_is_manual, body)
    now = _now()

    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            prior = conn.execute("SELECT * FROM save_requests WHERE request_id = ?", (request_id,)).fetchone()
            if prior is not None:
                if prior["doc_id"] != doc_id or prior["fingerprint"] != fp:
                    raise NotebookError("this request id was already used for different data — "
                                        "a retry must carry the same payload", 400)
                head = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
                conn.execute("COMMIT")
                return {"doc_id": doc_id, "request_id": request_id, "revision": int(prior["revision"]),
                        "fingerprint": prior["fingerprint"], "saved_at": prior["saved_at"],
                        "created": False, "repeated": True, "checkpoint": None,
                        "head_revision": int(head["revision"]) if head else None}
            head = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            checkpoint = None
            if head is None:
                if base_revision != 0:
                    raise NotebookError("no such document — a new one is created from base_revision 0", 404)
                conn.execute(
                    "INSERT INTO documents (doc_id, title, title_is_manual, body, revision, fingerprint, "
                    "created_at, saved_at, origin) VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?)",
                    (doc_id, title, int(title_is_manual), body, fp, now, now, origin))
                revision, created = 1, True
            else:
                if int(head["revision"]) != base_revision or head["fingerprint"] != base_fingerprint:
                    raise NotebookError("the document has changed since this copy was taken — nothing was "
                                        "overwritten; the current head is returned", 409, head=_head_dict(head))
                if head["fingerprint"] == fp:
                    revision, created = int(head["revision"]), False     # nothing changed: no bump
                else:
                    revision, created = int(head["revision"]) + 1, False
                    conn.execute(
                        "UPDATE documents SET title = ?, title_is_manual = ?, body = ?, revision = ?, "
                        "fingerprint = ?, saved_at = ? WHERE doc_id = ?",
                        (title, int(title_is_manual), body, revision, fp, now, doc_id))
            conn.execute(
                "INSERT INTO save_requests (request_id, doc_id, fingerprint, revision, saved_at) "
                "VALUES (?, ?, ?, ?, ?)", (request_id, doc_id, fp, revision, now))
            if checkpoint_reason is not None:
                row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
                checkpoint = _insert_checkpoint(conn, row, checkpoint_reason, now)
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return {"doc_id": doc_id, "request_id": request_id, "revision": revision, "fingerprint": fp,
                "saved_at": now, "created": created, "repeated": False, "checkpoint": checkpoint,
                "head_revision": revision}
    finally:
        conn.close()


def checkpoint(doc_id: str, *, revision: int, fingerprint_: str, reason: str) -> dict:
    """An idempotent checkpoint of the head as the caller knows it. Refused
    (409) when the head has moved, so a later revision is never captured by
    accident."""
    _check_id(doc_id, "document id")
    if reason not in REASONS:
        raise NotebookError(f"unknown checkpoint reason {reason!r}", 400)
    if not isinstance(revision, int) or isinstance(revision, bool):
        raise NotebookError("revision must be an integer", 400)
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            head = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if head is None:
                raise NotebookError("no such document", 404)
            if int(head["revision"]) != revision or head["fingerprint"] != fingerprint_:
                raise NotebookError("the head is not the revision this checkpoint names — nothing was "
                                    "captured", 409, head=_head_dict(head))
            out = _insert_checkpoint(conn, head, reason, _now())
            conn.execute("COMMIT")
            return out
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()


def summary() -> dict:
    """Counts, by population, for Home and the suite. No text."""
    conn = _connect()
    try:
        n = conn.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
        c = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
        r = conn.execute("SELECT COUNT(*) FROM save_requests").fetchone()[0]
        newest = conn.execute("SELECT doc_id, title, body, saved_at, revision, title_is_manual, fingerprint, "
                              "created_at, origin FROM documents ORDER BY saved_at DESC, doc_id DESC LIMIT 1").fetchone()
        return {"documents": int(n), "checkpoints": int(c), "saves": int(r),
                "population": "every document, checkpoint and accepted save in this notebook",
                "newest": _doc_dict(newest, with_body=False) if newest else None}
    finally:
        conn.close()


if __name__ == "__main__":  # pragma: no cover — a hand check, no model
    import argparse
    ap = argparse.ArgumentParser(description="the writer's notebook (no model calls)")
    ap.add_argument("--summary", action="store_true")
    ap.add_argument("--list", action="store_true")
    a = ap.parse_args()
    if a.summary:
        print(json.dumps(summary(), indent=2, ensure_ascii=False))
    if a.list:
        for d in list_documents()["documents"]:
            print(f"{d['saved_at']}  rev {d['revision']:>3}  {d['doc_id']}  {d['display_title'][:60]}")
