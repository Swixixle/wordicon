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
                  for different data — or, since the versioned request
                  fingerprint, for the same data under a different
                  checkpoint reason, base or origin — is an error, not a
                  second write. Rows from before that column compare by
                  content, as they always did.
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
import document_schema as ds  # noqa: E402  (workspace-v2 slice C: schema v1, projection v1, the versioned fingerprint)

SCHEMA_VERSION = 2   # v2 (workspace-v2 slice C): structure beside the exact text, additively
DB_NAME = "notebook.sqlite3"
BUSY_TIMEOUT_S = 5.0
ID_RX = re.compile(r"^[A-Za-z0-9_\-]{8,64}$")
TITLE_MAX = 200
REASONS = ("save", "new", "interval", "replace", "open", "migration", "recovery", "restore")
EVENT_KINDS = ("format_converted", "restored", "plain_copy", "applied")
UNTITLED = "Untitled"


class NotebookError(Exception):
    """A request the store refuses. `status` is the HTTP status the route
    answers with; `head` (on a conflict) is the current document."""

    def __init__(self, message: str, status: int = 400, head: dict | None = None, error_class: str = ""):
        super().__init__(message)
        self.status = status
        self.head = head
        self.error_class = error_class


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
        CREATE TABLE IF NOT EXISTS document_events (
            event_id    TEXT PRIMARY KEY,
            doc_id      TEXT NOT NULL,
            kind        TEXT NOT NULL,
            revision    INTEGER,
            detail      TEXT NOT NULL DEFAULT '',
            created_at  TEXT NOT NULL
        );
        CREATE INDEX IF NOT EXISTS document_events_doc ON document_events (doc_id, created_at);
        CREATE TABLE IF NOT EXISTS index_outbox (
            seq         INTEGER PRIMARY KEY AUTOINCREMENT,
            doc_id      TEXT NOT NULL,
            revision    INTEGER NOT NULL,
            at          TEXT NOT NULL,
            done        INTEGER NOT NULL DEFAULT 0
        );
        INSERT OR IGNORE INTO meta (key, value) VALUES ('schema', '1');
    """)
    # v2, additive and idempotent: the structure beside the exact text, on the
    # head and on every checkpoint, with its versions; the fingerprint's own
    # version so a v1 fingerprint is never rehashed in place.
    for table in ("documents", "checkpoints"):
        have = {r[1] for r in conn.execute(f"PRAGMA table_info({table})").fetchall()}
        for col, decl in (("doc_json", "TEXT"), ("doc_schema", "INTEGER"), ("projection_version", "INTEGER"),
                          ("fp_version", "INTEGER NOT NULL DEFAULT 1")):
            if col not in have:
                conn.execute(f"ALTER TABLE {table} ADD COLUMN {col} {decl}")
    # the review of 6e5b59c: a repeat is the same REQUEST, not only the same
    # content — the checkpoint reason, base, origin and the presence of
    # structure are part of what was asked. Additive: a row written before
    # this column has NULL and compares by content, as it always did.
    have = {r[1] for r in conn.execute("PRAGMA table_info(save_requests)").fetchall()}
    for col, decl in (("request_fp", "TEXT"), ("request_fp_version", "INTEGER")):
        if col not in have:
            conn.execute(f"ALTER TABLE save_requests ADD COLUMN {col} {decl}")
    conn.execute("UPDATE meta SET value = ? WHERE key = 'schema' AND CAST(value AS INTEGER) < ?",
                 (str(SCHEMA_VERSION), SCHEMA_VERSION))
    # The guard against a binary that does not know the structure: an older
    # notebook.py updates body/revision/fingerprint and leaves doc_json as it
    # was, which would make the structure lie about the text; and it would
    # checkpoint a structured head without its structure. Both are refused
    # by the database itself, so rolling the code back cannot corrupt what
    # the new code wrote — the old code can still read every document.
    conn.executescript("""
        CREATE TRIGGER IF NOT EXISTS documents_keep_structure BEFORE UPDATE OF body ON documents
        WHEN OLD.doc_json IS NOT NULL AND NEW.body IS NOT OLD.body AND NEW.doc_json IS OLD.doc_json
        BEGIN SELECT RAISE(ABORT, 'this document carries structure; a body-only write would leave the structure describing other text — refused'); END;
        CREATE TRIGGER IF NOT EXISTS checkpoints_keep_structure BEFORE INSERT ON checkpoints
        WHEN NEW.doc_json IS NULL AND (SELECT doc_json FROM documents WHERE doc_id = NEW.doc_id) IS NOT NULL
             AND (SELECT body FROM documents WHERE doc_id = NEW.doc_id) IS NEW.body
        BEGIN SELECT RAISE(ABORT, 'a checkpoint of a structured head must carry its structure — refused'); END;
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


REQUEST_FP_VERSION = 1


def request_fingerprint(doc_id: str, content_fp: str, base_revision: int, base_fingerprint: str,
                        checkpoint_reason: str | None, origin: str, structured: bool) -> str:
    """What a save request ASKED, canonical: the document, the content
    fingerprint (title, its manual flag, the exact body and, for a rich
    document, the structure and its versions), the base it was made from,
    the checkpoint reason it carried (or none), its origin and whether
    structure was sent. Two requests under one id that differ in any of
    these are two intents, and the second is refused — a retry carries the
    same request. Versioned so a later form is never compared to this one."""
    canon = json.dumps({"v": REQUEST_FP_VERSION, "d": doc_id, "fp": content_fp, "br": int(base_revision),
                        "bf": base_fingerprint or "", "cr": checkpoint_reason, "o": origin or "", "s": bool(structured)},
                       ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return f"rq{REQUEST_FP_VERSION}_" + hashlib.sha256(canon.encode("utf-8")).hexdigest()[:32]


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
    keys = row.keys()
    d["doc_schema"] = int(row["doc_schema"]) if "doc_schema" in keys and row["doc_schema"] is not None else None
    d["projection_version"] = int(row["projection_version"]) if "projection_version" in keys and row["projection_version"] is not None else None
    d["fp_version"] = int(row["fp_version"]) if "fp_version" in keys and row["fp_version"] is not None else 1
    d["rich"] = bool("doc_json" in keys and row["doc_json"])
    if with_body:
        d["body"] = row["body"]
        d["doc_json"] = json.loads(row["doc_json"]) if d["rich"] else None
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
            "created_at, length(body) AS chars, (doc_json IS NOT NULL) AS rich, doc_schema, projection_version "
            "FROM checkpoints WHERE doc_id = ? "
            "ORDER BY revision DESC, created_at DESC", (doc_id,)).fetchall()
        return [{"checkpoint_id": r["checkpoint_id"], "doc_id": r["doc_id"], "revision": int(r["revision"]),
                 "reason": r["reason"], "title": r["title"], "title_is_manual": bool(r["title_is_manual"]),
                 "fingerprint": r["fingerprint"], "created_at": r["created_at"], "chars": int(r["chars"]),
                 "rich": bool(r["rich"]), "doc_schema": r["doc_schema"], "projection_version": r["projection_version"]}
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
                "body": r["body"], "fingerprint": r["fingerprint"], "created_at": r["created_at"],
                "doc_json": json.loads(r["doc_json"]) if r["doc_json"] else None,
                "doc_schema": r["doc_schema"], "projection_version": r["projection_version"],
                "fp_version": r["fp_version"] if r["fp_version"] is not None else 1}
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
        "fingerprint, created_at, doc_json, doc_schema, projection_version, fp_version) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        (cid, row["doc_id"], row["revision"], reason, row["title"], row["title_is_manual"],
         row["body"], row["fingerprint"], now, row["doc_json"], row["doc_schema"], row["projection_version"],
         row["fp_version"] if row["fp_version"] is not None else 1))
    return {"checkpoint_id": cid, "revision": int(row["revision"]), "reason": reason,
            "created_at": now, "created": True}


def _event(conn, doc_id: str, kind: str, revision, detail: dict, now: str) -> str:
    assert kind in EVENT_KINDS
    eid = "ev_" + uuid.uuid4().hex[:20]
    conn.execute("INSERT INTO document_events (event_id, doc_id, kind, revision, detail, created_at) VALUES (?, ?, ?, ?, ?, ?)",
                 (eid, doc_id, kind, revision, json.dumps(detail, ensure_ascii=False, sort_keys=True), now))
    return eid


def list_events(doc_id: str, limit: int = 100) -> list[dict]:
    _check_id(doc_id, "document id")
    conn = _connect()
    try:
        rows = conn.execute("SELECT * FROM document_events WHERE doc_id = ? ORDER BY created_at DESC LIMIT ?",
                            (doc_id, int(limit))).fetchall()
        out = []
        for r in rows:
            try:
                detail = json.loads(r["detail"] or "{}")
            except json.JSONDecodeError:
                detail = {}
            out.append({"event_id": r["event_id"], "doc_id": r["doc_id"], "kind": r["kind"], "revision": r["revision"],
                        "detail": detail, "created_at": r["created_at"]})
        return out
    finally:
        conn.close()


def _structure_in(body: str, doc_json, doc_schema, projection_version):
    """Validate an incoming structure against its exact text. Returns
    (canonical_json_text or None, schema, projection, fingerprint_version)."""
    if doc_json is None:
        return None, None, None, 1
    if not isinstance(doc_json, dict):
        raise NotebookError("doc_json must be an object (the document's structure)", 400, error_class="schema_invalid")
    if doc_schema is None or projection_version is None:
        raise NotebookError("a structured save names doc_schema and projection_version", 400, error_class="schema_invalid")
    if not isinstance(doc_schema, int) or isinstance(doc_schema, bool) or not isinstance(projection_version, int) or isinstance(projection_version, bool):
        raise NotebookError("doc_schema and projection_version are integers", 400, error_class="schema_invalid")
    try:
        canon_doc = ds.validate(doc_json, doc_schema)
        projected = ds.project(canon_doc, projection_version)
    except ds.SchemaError as e:
        status = 422 if e.error_class in ("schema_unsupported", "projection_unsupported") else 400
        raise NotebookError(str(e), status, error_class=e.error_class)
    if projected != body:
        raise NotebookError("the structure does not project to the exact text sent with it — nothing was saved; "
                            f"the projection differs at code point {_first_diff(projected, body)}",
                            422, error_class="projection_mismatch")
    return ds.canonical(canon_doc), doc_schema, projection_version, 2


def _first_diff(a: str, b: str) -> int:
    n = min(len(a), len(b))
    for i in range(n):
        if a[i] != b[i]:
            return i
    return n


def save(doc_id: str, *, title: str, title_is_manual: bool, body: str, base_revision: int,
         base_fingerprint: str, request_id: str, checkpoint_reason: str | None = None,
         origin: str = "", doc_json=None, doc_schema=None, projection_version=None,
         flatten_marker=None) -> dict:
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
    doc_text, sch, proj, fpv = _structure_in(body, doc_json, doc_schema, projection_version)
    # the one fingerprint for the whole document: v2 covers the structure and
    # its versions; a plain document keeps the v1 form so nothing old is rehashed
    fp = ds.fingerprint_v2(title, title_is_manual, body, json.loads(doc_text), sch, proj) if doc_text is not None \
        else fingerprint(title, title_is_manual, body)
    rq = request_fingerprint(doc_id, fp, base_revision, base_fingerprint, checkpoint_reason, origin, doc_text is not None)
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
                # the same content under the same id, but a different request: another
                # checkpoint reason, base or origin (a row from before the request
                # fingerprint existed has none and compares by content, as it did)
                if prior["request_fp"] is not None and prior["request_fp"] != rq:
                    raise NotebookError("this request id was already used for a different request — the same words, "
                                        "but another checkpoint reason, base or origin; a retry must carry the same "
                                        "request, and a new intent gets a new request id", 400,
                                        error_class="request_intent_differs")
                head = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
                conn.execute("COMMIT")
                return {"doc_id": doc_id, "request_id": request_id, "revision": int(prior["revision"]),
                        "fingerprint": prior["fingerprint"], "saved_at": prior["saved_at"],
                        "created": False, "repeated": True, "checkpoint": None,
                        "head_revision": int(head["revision"]) if head else None,
                        "request_fp_version": prior["request_fp_version"]}
            head = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            checkpoint = None
            events = []
            if head is None:
                if base_revision != 0:
                    raise NotebookError("no such document — a new one is created from base_revision 0", 404)
                conn.execute(
                    "INSERT INTO documents (doc_id, title, title_is_manual, body, revision, fingerprint, "
                    "created_at, saved_at, origin, doc_json, doc_schema, projection_version, fp_version) "
                    "VALUES (?, ?, ?, ?, 1, ?, ?, ?, ?, ?, ?, ?, ?)",
                    (doc_id, title, int(title_is_manual), body, fp, now, now, origin, doc_text, sch, proj, fpv))
                revision, created = 1, True
                if doc_text is not None:
                    events.append(_event(conn, doc_id, "format_converted", 1, {"from": "new", "to_schema": sch, "projection": proj}, now))
            else:
                if int(head["revision"]) != base_revision or head["fingerprint"] != base_fingerprint:
                    raise NotebookError("the document has changed since this copy was taken — nothing was "
                                        "overwritten; the current head is returned", 409, head=_head_dict(head))
                # a body-only save may not flatten a rich head: headings, emphasis,
                # lists and links would vanish in silence. A deliberate plain copy
                # is a new document (plain_copy); this save is refused by name.
                if doc_text is None and head["doc_json"]:
                    raise NotebookError("this document carries structure (headings, emphasis, lists or links) that a "
                                        "plain-text save would silently drop — nothing was saved. Open it in the "
                                        "structured editor, or make a plain copy as a new document.",
                                        422, head=_head_dict(head), error_class="structure_would_be_lost")
                if head["fingerprint"] == fp:
                    revision, created = int(head["revision"]), False     # nothing changed: no bump
                else:
                    revision, created = int(head["revision"]) + 1, False
                    if doc_text is not None and not head["doc_json"]:
                        # the first structured save of a plain document: the plain head
                        # is checkpointed as it stood, and the conversion is an event
                        _insert_checkpoint(conn, head, "migration", now)
                        events.append(_event(conn, doc_id, "format_converted", revision,
                                             {"from": "plain", "from_revision": int(head["revision"]), "to_schema": sch, "projection": proj}, now))
                    conn.execute(
                        "UPDATE documents SET title = ?, title_is_manual = ?, body = ?, revision = ?, "
                        "fingerprint = ?, saved_at = ?, doc_json = ?, doc_schema = ?, projection_version = ?, fp_version = ? "
                        "WHERE doc_id = ?",
                        (title, int(title_is_manual), body, revision, fp, now, doc_text, sch, proj, fpv, doc_id))
            conn.execute(
                "INSERT INTO save_requests (request_id, doc_id, fingerprint, revision, saved_at, request_fp, request_fp_version) "
                "VALUES (?, ?, ?, ?, ?, ?, ?)", (request_id, doc_id, fp, revision, now, rq, REQUEST_FP_VERSION))
            if checkpoint_reason is not None:
                row = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
                checkpoint = _insert_checkpoint(conn, row, checkpoint_reason, now)
            # slice E: the index learns of this save from a row written in the
            # SAME transaction — a crash after the commit and before the index
            # is repaired by draining this; an index failure cannot touch the save
            conn.execute("INSERT INTO index_outbox (doc_id, revision, at) VALUES (?, ?, ?)", (doc_id, revision, now))
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
        return {"doc_id": doc_id, "request_id": request_id, "revision": revision, "fingerprint": fp,
                "saved_at": now, "created": created, "repeated": False, "checkpoint": checkpoint,
                "head_revision": revision, "rich": doc_text is not None, "fp_version": fpv, "events": events,
                "request_fp_version": REQUEST_FP_VERSION}
    finally:
        conn.close()


def restore(doc_id: str, *, checkpoint_id: str, base_revision: int, base_fingerprint: str, request_id: str) -> dict:
    """A checkpoint becomes the head as a NEW revision — history is never
    rewritten, the checkpoint stays. Structure comes back whole; a plain
    checkpoint restores a plain head. The head must be where the caller
    thinks it is (409 otherwise), and the head as it stands is checkpointed
    first with reason 'restore'."""
    cp = get_checkpoint(doc_id, checkpoint_id)
    if cp is None:
        raise NotebookError("no such checkpoint", 404)
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        try:
            head = conn.execute("SELECT * FROM documents WHERE doc_id = ?", (doc_id,)).fetchone()
            if head is None:
                raise NotebookError("no such document", 404)
            if int(head["revision"]) != base_revision or head["fingerprint"] != base_fingerprint:
                raise NotebookError("the document has changed since this copy was taken — nothing was restored", 409, head=_head_dict(head))
            _insert_checkpoint(conn, head, "restore", _now())
            conn.execute("COMMIT")
        except Exception:
            conn.execute("ROLLBACK")
            raise
    finally:
        conn.close()
    doc_json, sch, proj = cp.get("doc_json"), cp.get("doc_schema"), cp.get("projection_version")
    if doc_json is None and head["doc_json"]:
        # a plain checkpoint over a rich head: nothing is lost by giving the
        # restored text its paragraphs, and the rich head was checkpointed
        # above; a body the schema cannot hold is refused by name instead
        ok, why = ds.convertible(cp["body"])
        if not ok:
            raise NotebookError(f"this checkpoint is plain text the structured schema cannot hold ({why}); "
                                "make a plain copy instead of restoring over a structured document", 422,
                                error_class="structure_would_be_lost")
        doc_json, sch, proj = ds.parse_plain(cp["body"]), ds.SCHEMA_VERSION, ds.PROJECTION_VERSION
    ack = save(doc_id, title=cp["title"], title_is_manual=cp["title_is_manual"], body=cp["body"],
               base_revision=base_revision, base_fingerprint=base_fingerprint, request_id=request_id,
               doc_json=doc_json, doc_schema=sch, projection_version=proj, origin="restore")
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _event(conn, doc_id, "restored", ack["revision"], {"checkpoint_id": checkpoint_id, "from_revision": cp["revision"]}, _now())
        conn.execute("COMMIT")
    finally:
        conn.close()
    ack["restored_from"] = checkpoint_id
    return ack


def plain_copy(doc_id: str, *, request_id: str) -> dict:
    """A deliberate plain-text copy: a NEW document with the exact body and
    no structure. The original keeps its id and its structure."""
    src = get(doc_id)
    if src is None:
        raise NotebookError("no such document", 404)
    new_id_ = new_id()
    ack = save(new_id_, title=src["title"], title_is_manual=src["title_is_manual"], body=src["body"],
               base_revision=0, base_fingerprint="", request_id=request_id, origin="plain-copy")
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        _event(conn, new_id_, "plain_copy", ack["revision"], {"from_doc_id": doc_id, "from_revision": src["revision"]}, _now())
        conn.execute("COMMIT")
    finally:
        conn.close()
    ack["from_doc_id"] = doc_id
    return ack


def record_application(doc_id: str, *, result_ref: dict, kind: str, from_revision, from_seq, to_seq, range_: dict, committed_revision=None) -> dict:
    """Application of a textual suggestion to the draft, as its own event
    linked to the immutable result and the document versions. An unsaved
    local application has committed_revision None; the save that carries it
    is recorded when it commits (see mark_application_committed)."""
    _check_id(doc_id, "document id")
    if kind not in ("insert", "replace", "undo", "redo"):
        raise NotebookError("kind must be insert, replace, undo or redo", 400)
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        eid = _event(conn, doc_id, "applied", committed_revision,
                     {"kind": kind, "result": result_ref, "from_revision": from_revision, "from_seq": from_seq,
                      "to_seq": to_seq, "range": range_, "committed_revision": committed_revision}, _now())
        conn.execute("COMMIT")
        return {"event_id": eid}
    finally:
        conn.close()


def mark_application_committed(doc_id: str, event_id: str, committed_revision: int) -> bool:
    conn = _connect()
    try:
        conn.execute("BEGIN IMMEDIATE")
        r = conn.execute("SELECT detail FROM document_events WHERE event_id = ? AND doc_id = ? AND kind = 'applied'", (event_id, doc_id)).fetchone()
        if not r:
            conn.execute("ROLLBACK")
            return False
        detail = json.loads(r["detail"] or "{}")
        detail["committed_revision"] = int(committed_revision)
        conn.execute("UPDATE document_events SET detail = ?, revision = ? WHERE event_id = ?",
                     (json.dumps(detail, ensure_ascii=False, sort_keys=True), int(committed_revision), event_id))
        conn.execute("COMMIT")
        return True
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
