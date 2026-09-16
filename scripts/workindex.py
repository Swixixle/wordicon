"""Your work — the derived index (workspace-v2 slice E, instructions §9).

A SQLite/FTS5 index over the record, derived and rebuildable, never an
authority: every item names the store it came from, its kind and its
native id (`store:kind:native`), and says how to reopen the authoritative
record. It is excluded from the Vault, like the Library's own search file.

Adapters. Each store has one: it reads the source and yields items with a
title, the searchable text (a document's body, a run's input and result
titles, a reading's passage and answers, a note's excerpt, a concept's
definition …), created and changed times kept apart, a status, a tool, and
the reopen instruction. Incremental reading uses what the source can
promise — the notebook's and the operations store's OUTBOX rows (written in
the same transaction as the change), an append log's byte offset, a file's
size and mtime as an UPDATE SIGNAL that triggers a read of the authoritative
current record — never a wall-clock ordering of revisions.

Generations. A rebuild writes every item into a new generation, then
switches the current generation in one short transaction and drops the old
rows; a rebuild that fails leaves the last working generation current.
Readers always read the current generation.

Health. The pending count is what was MEASURED (undrained outbox rows,
files changed since the last reconcile); when a scan failed or has not run,
the index says it is incomplete, and the page says "Search is updating;
some recent work may be missing" instead of promising an exhaustive no.

Archive. A ruling in `work_archive.jsonl` (append-only, authoritative);
the index reads it. Archived items leave ordinary listings, keep their
history, and are listed under the archive filter. Nothing is erased.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
import threading
import time
from datetime import datetime, timezone
from pathlib import Path

import wordicon_cli as cli

DB_NAME = "work_index.sqlite3"
ARCHIVE_LOG = "work_archive.jsonl"
SCHEMA_VERSION = 1
BUSY_TIMEOUT_S = 5.0
KINDS = ("writing", "run", "input", "reading", "note", "concept", "word", "question", "source", "media", "room", "deposition",
         "inquiry", "recovery", "operation")
KIND_LABELS = {"writing": "writing", "run": "run", "input": "input", "reading": "readers", "note": "revision note", "concept": "concept",
               "word": "saved word", "question": "question", "source": "source", "media": "recording", "room": "room",
               "deposition": "deposition", "inquiry": "inquiry", "recovery": "recovery case", "operation": "operation"}

_LOCK = threading.RLock()         # one refresh or rebuild at a time in this process (re-entrant: a first refresh rebuilds)
_LAST = {"refresh_at": 0.0, "error": "", "incomplete_why": ""}


class IndexError_(Exception):
    pass


# ---- the file --------------------------------------------------------------------

def root() -> Path:
    return Path(cli.LOCAL_STATE)


def db_path() -> Path:
    return root() / DB_NAME


def archive_log() -> Path:
    return root() / ARCHIVE_LOG


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds").replace("+00:00", "Z")


def _connect() -> sqlite3.Connection:
    p = db_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(p), timeout=BUSY_TIMEOUT_S, isolation_level=None)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA busy_timeout=%d" % int(BUSY_TIMEOUT_S * 1000))
    _ensure_schema(conn)
    return conn


def has_fts(conn: sqlite3.Connection | None = None) -> bool:
    c = conn or sqlite3.connect(":memory:")
    try:
        c.execute("CREATE VIRTUAL TABLE IF NOT EXISTS _fts_probe USING fts5(x)")
        c.execute("DROP TABLE IF EXISTS _fts_probe")
        return True
    except sqlite3.OperationalError:
        return False
    finally:
        if conn is None:
            c.close()


def _ensure_schema(conn: sqlite3.Connection) -> None:
    conn.executescript("""
        CREATE TABLE IF NOT EXISTS meta (key TEXT PRIMARY KEY, value TEXT NOT NULL);
        CREATE TABLE IF NOT EXISTS items (
            rowid      INTEGER PRIMARY KEY,
            item_id    TEXT NOT NULL,
            gen        INTEGER NOT NULL,
            store      TEXT NOT NULL,
            kind       TEXT NOT NULL,
            native_id  TEXT NOT NULL,
            title      TEXT NOT NULL DEFAULT '',
            snippet    TEXT NOT NULL DEFAULT '',
            body       TEXT NOT NULL DEFAULT '',
            tool       TEXT NOT NULL DEFAULT '',
            status     TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL DEFAULT '',
            changed_at TEXT NOT NULL DEFAULT '',
            meta       TEXT NOT NULL DEFAULT '{}',
            meta_text  TEXT NOT NULL DEFAULT '',
            open       TEXT NOT NULL DEFAULT '{}',
            version    TEXT NOT NULL DEFAULT '',
            related    TEXT NOT NULL DEFAULT '[]',
            archived   INTEGER NOT NULL DEFAULT 0,
            UNIQUE (gen, item_id)
        );
        CREATE INDEX IF NOT EXISTS items_changed ON items (gen, changed_at DESC, item_id);
        CREATE INDEX IF NOT EXISTS items_kind ON items (gen, kind, changed_at DESC);
        CREATE TABLE IF NOT EXISTS watermarks (gen INTEGER NOT NULL, store TEXT NOT NULL, key TEXT NOT NULL, value TEXT NOT NULL, PRIMARY KEY (gen, store, key));
        INSERT OR IGNORE INTO meta (key, value) VALUES ('schema', '1');
        INSERT OR IGNORE INTO meta (key, value) VALUES ('generation', '0');
        INSERT OR IGNORE INTO meta (key, value) VALUES ('fts', '');
    """)
    fts = conn.execute("SELECT value FROM meta WHERE key = 'fts'").fetchone()[0]
    if fts == "":
        ok = has_fts(conn)
        if ok:
            conn.executescript("""
                CREATE VIRTUAL TABLE IF NOT EXISTS items_fts USING fts5(title, body, meta_text, content='items', content_rowid='rowid', tokenize='unicode61');
                CREATE TRIGGER IF NOT EXISTS items_ai AFTER INSERT ON items BEGIN
                    INSERT INTO items_fts(rowid, title, body, meta_text) VALUES (new.rowid, new.title, new.body, new.meta_text); END;
                CREATE TRIGGER IF NOT EXISTS items_ad AFTER DELETE ON items BEGIN
                    INSERT INTO items_fts(items_fts, rowid, title, body, meta_text) VALUES ('delete', old.rowid, old.title, old.body, old.meta_text); END;
                CREATE TRIGGER IF NOT EXISTS items_au AFTER UPDATE OF title, body, meta_text ON items BEGIN
                    INSERT INTO items_fts(items_fts, rowid, title, body, meta_text) VALUES ('delete', old.rowid, old.title, old.body, old.meta_text);
                    INSERT INTO items_fts(rowid, title, body, meta_text) VALUES (new.rowid, new.title, new.body, new.meta_text); END;
            """)
        conn.execute("UPDATE meta SET value = ? WHERE key = 'fts'", ("1" if ok else "0",))


def _meta(conn, key, default=""):
    r = conn.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
    return r[0] if r else default


def _set_meta(conn, key, value):
    conn.execute("INSERT INTO meta (key, value) VALUES (?, ?) ON CONFLICT(key) DO UPDATE SET value = excluded.value", (key, str(value)))


def generation(conn=None) -> int:
    c = conn or _connect()
    try:
        return int(_meta(c, "generation", "0") or 0)
    finally:
        if conn is None:
            c.close()


# ---- items ------------------------------------------------------------------------

def item_id(store: str, kind: str, native: str) -> str:
    return f"{store}:{kind}:{native}"


def _snippet(text: str, n: int = 160) -> str:
    t = " ".join(str(text or "").split())
    return t[:n] + ("…" if len(t) > n else "")


def _item(store, kind, native, *, title="", body="", tool="", status="", created_at="", changed_at="", meta=None, open_=None, version="", related=None) -> dict:
    meta = meta or {}
    return {"item_id": item_id(store, kind, native), "store": store, "kind": kind, "native_id": str(native), "title": str(title or "")[:300],
            "snippet": _snippet(body or title), "body": str(body or "")[:200000], "tool": str(tool or "")[:80], "status": str(status or "")[:60],
            "created_at": str(created_at or ""), "changed_at": str(changed_at or created_at or ""), "meta": meta,
            "meta_text": " ".join(str(v) for v in meta.values() if isinstance(v, (str, int, float)))[:2000],
            "open": open_ or {}, "version": str(version or ""), "related": related or []}


def _upsert(conn, gen: int, it: dict) -> None:
    conn.execute(
        "INSERT INTO items (item_id, gen, store, kind, native_id, title, snippet, body, tool, status, created_at, changed_at, meta, meta_text, open, version, related) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?) "
        "ON CONFLICT(gen, item_id) DO UPDATE SET title = excluded.title, snippet = excluded.snippet, body = excluded.body, tool = excluded.tool, "
        "status = excluded.status, created_at = excluded.created_at, changed_at = excluded.changed_at, meta = excluded.meta, meta_text = excluded.meta_text, "
        "open = excluded.open, version = excluded.version, related = excluded.related",
        (it["item_id"], gen, it["store"], it["kind"], it["native_id"], it["title"], it["snippet"], it["body"], it["tool"], it["status"],
         it["created_at"], it["changed_at"], json.dumps(it["meta"], ensure_ascii=False, sort_keys=True), it["meta_text"],
         json.dumps(it["open"], ensure_ascii=False, sort_keys=True), it["version"], json.dumps(it["related"])))


def _delete(conn, gen: int, iid: str) -> None:
    conn.execute("DELETE FROM items WHERE gen = ? AND item_id = ?", (gen, iid))


def _wm_get(conn, gen, store, key, default=""):
    r = conn.execute("SELECT value FROM watermarks WHERE gen = ? AND store = ? AND key = ?", (gen, store, key)).fetchone()
    return r[0] if r else default


def _wm_set(conn, gen, store, key, value):
    conn.execute("INSERT INTO watermarks (gen, store, key, value) VALUES (?, ?, ?, ?) ON CONFLICT(gen, store, key) DO UPDATE SET value = excluded.value",
                 (gen, store, key, str(value)))


def _jsonl_rows(path: Path, offset: int = 0) -> tuple[list[dict], int, bool]:
    """Rows after a byte offset; (rows, new_offset, truncated). A file
    shorter than the offset was replaced or truncated: the caller rereads
    from zero."""
    if not path.exists():
        return [], 0, False
    size = path.stat().st_size
    if size < offset:
        return [], 0, True
    rows = []
    with open(path, "rb") as f:
        f.seek(offset)
        data = f.read()
    end = offset + len(data)
    # only whole lines: a partial trailing line waits for its newline
    if data and not data.endswith(b"\n"):
        cut = data.rfind(b"\n")
        data = data[:cut + 1] if cut >= 0 else b""
        end = offset + len(data)
    for line in data.decode("utf-8", errors="replace").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            rows.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return rows, end, False


def _file_version(p: Path) -> str:
    try:
        st = p.stat()
        return f"{st.st_mtime_ns}:{st.st_size}"
    except OSError:
        return ""


def _read_json(p: Path):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None


# ---- adapters ---------------------------------------------------------------------
# Each returns (items_to_upsert, ids_to_delete, complete) and updates the watermarks it owns.

def _scan_notebook(conn, gen, full: bool):
    """The writer's notebook: one item per document; the body is the exact
    text; the version is the native revision. Incremental through the
    notebook's own outbox."""
    import notebook as nbk
    items, deletes = [], []
    p = nbk.db_path()
    if not p.exists():
        return items, deletes, True
    src = sqlite3.connect(str(p), timeout=BUSY_TIMEOUT_S)
    src.row_factory = sqlite3.Row
    try:
        cols = {r[1] for r in src.execute("PRAGMA table_info(documents)").fetchall()}
        rich = "doc_json" in cols
        if full:
            rows = src.execute("SELECT * FROM documents").fetchall()
            pending = []
        else:
            have_outbox = src.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'index_outbox'").fetchone() is not None
            if not have_outbox:
                return items, deletes, True
            pending = src.execute("SELECT seq, doc_id FROM index_outbox WHERE done = 0 ORDER BY seq ASC LIMIT 500").fetchall()
            ids = sorted({r["doc_id"] for r in pending})
            rows = [src.execute("SELECT * FROM documents WHERE doc_id = ?", (d,)).fetchone() for d in ids]
        for r in rows:
            if r is None:
                continue
            title = r["title"] if r["title_is_manual"] and r["title"] else nbk.auto_title(r["body"])
            items.append(_item("notebook", "writing", r["doc_id"], title=title, body=r["body"], tool="notebook",
                               status=("formatted" if (rich and r["doc_json"]) else "plain") + (" · " + r["origin"] if r["origin"] else ""),
                               created_at=r["created_at"], changed_at=r["saved_at"], version=str(r["revision"]),
                               meta={"revision": int(r["revision"]), "origin": r["origin"], "chars": len(r["body"]), "words": len(r["body"].split())},
                               open_={"document": r["doc_id"]}))
        if pending:
            src.execute("BEGIN IMMEDIATE")
            src.execute("UPDATE index_outbox SET done = 1 WHERE seq <= ?", (max(r["seq"] for r in pending),))
            src.execute("COMMIT")
        elif full and src.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'index_outbox'").fetchone() is not None:
            # a full read covers every row the outbox names
            src.execute("BEGIN IMMEDIATE")
            src.execute("UPDATE index_outbox SET done = 1 WHERE done = 0")
            src.execute("COMMIT")
    finally:
        src.close()
    return items, deletes, True


def _scan_operations(conn, gen, full: bool):
    """The operations store: one item per operation, incremental by its
    event sequence; the searchable text is the frozen snapshot's."""
    import operations as ops
    import snapshots
    items, deletes = [], []
    p = ops.db_path()
    if not p.exists():
        return items, deletes, True
    src = sqlite3.connect(str(p), timeout=BUSY_TIMEOUT_S)
    src.row_factory = sqlite3.Row
    try:
        last = int(_wm_get(conn, gen, "operations", "event_seq", "0") or 0) if not full else 0
        top = src.execute("SELECT COALESCE(MAX(seq), 0) FROM operation_events").fetchone()[0]
        if full:
            rows = src.execute("SELECT * FROM operations").fetchall()
        else:
            ids = [r[0] for r in src.execute("SELECT DISTINCT op_id FROM operation_events WHERE seq > ?", (last,)).fetchall()]
            rows = [src.execute("SELECT * FROM operations WHERE op_id = ?", (i,)).fetchone() for i in ids]
        for r in rows:
            if r is None:
                continue
            snap = snapshots.load(r["snapshot_id"]) if r["snapshot_id"] else None
            text = (snap or {}).get("text") or ""
            ref = json.loads(r["result_ref"]) if r["result_ref"] else {}
            title = _action_label(r["action_id"] or "") or (r["action_id"] or "operation").replace("legacy:/api/jobs:", "a run: ")
            head = " ".join(text.split())[:80]
            items.append(_item("operations", "operation", r["op_id"], title=title + (" — " + head if head else ""), body=text, tool=r["action_id"] or "",
                               status=r["status"], created_at=r["created_at"], changed_at=r["updated_at"], version=str(top),
                               meta={"kind": r["kind"], "request_key": r["request_key"], "retry_parent": r["retry_parent"] or "", "last_error": r["last_error"] or "",
                                     "trace_id": ref.get("trace_id") or "", "component_trace_ids": ref.get("component_trace_ids") or []},
                               open_={"operation": r["op_id"]},
                               related=[item_id("results", "run", t) for t in ([ref.get("trace_id")] if ref.get("trace_id") else []) + list(ref.get("component_trace_ids") or [])]))
        _wm_set(conn, gen, "operations", "event_seq", int(top))
    finally:
        src.close()
    return items, deletes, True


def _scan_results(conn, gen, full: bool):
    """Runs: results/*.json. A file's size and mtime are the update signal;
    the item is read from the file, never from a queued copy. A file that
    is gone drops its item."""
    items, deletes = [], []
    d = cli.RESULTS_DIR
    known = {} if full else json.loads(_wm_get(conn, gen, "results", "versions", "{}") or "{}")
    seen = {}
    if d.exists():
        for p in sorted(d.glob("*.json")):
            if p.name.startswith("."):
                continue
            v = _file_version(p)
            seen[p.name] = v
            if not full and known.get(p.name) == v:
                continue
            snap = _read_json(p)
            if not isinstance(snap, dict):
                continue
            trace = snap.get("trace_id") or p.stem
            mode = str(snap.get("mode") or "")
            titles = [c.get("title", "") for c in (snap.get("candidates") or []) if isinstance(c, dict) and c.get("title")]
            for g in (snap.get("groups") or []):
                titles += [c.get("title", "") for c in (g.get("candidates") or []) if isinstance(c, dict) and c.get("title")]
            src_ = snap.get("source") or {}
            text = snap.get("input_text") or snap.get("source_text") or src_.get("passage") or src_.get("definition") or ""
            defs = [c.get("definition", "") for c in (snap.get("candidates") or []) if isinstance(c, dict) and c.get("definition")]
            title = (" · ".join(titles[:3]) if titles else (src_.get("title") or snap.get("summary") or trace))
            status = "partial" if snap.get("partial") else ("complete" if (titles or snap.get("summary") or mode == "refract") else "recorded")
            items.append(_item("results", "run", trace, title=(mode + ": " if mode else "") + str(title)[:200], body=(text + "\n\n" + "\n".join(defs)).strip(),
                               tool=mode, status=status, created_at=snap.get("created_at") or "", changed_at=snap.get("created_at") or "",
                               version=v, meta={"trace_id": trace, "titles": titles[:12], "receipt_id": snap.get("receipt_id") or "", "gateway": snap.get("gateway") or ""},
                               open_={"place": "/?trace=" + trace}))
    for name in set(known) - set(seen):
        deletes.append(item_id("results", "run", name[:-5]))
    _wm_set(conn, gen, "results", "versions", json.dumps(seen, sort_keys=True))
    return items, deletes, True


def _scan_inputs(conn, gen, full: bool):
    """What was typed or attached for every run, by append offset."""
    items, deletes = [], []
    p = cli.INPUTS_LOG
    off = 0 if full else int(_wm_get(conn, gen, "inputs", "offset", "0") or 0)
    rows, new_off, truncated = _jsonl_rows(p, off)
    if truncated:
        rows, new_off, _ = _jsonl_rows(p, 0)
    for r in rows:
        if r.get("object_type") != "input":
            continue
        jid = r.get("job_id") or ""
        text = r.get("text") or ""
        items.append(_item("inputs", "input", jid or hashlib.sha256(json.dumps(r, sort_keys=True).encode()).hexdigest()[:12],
                           title=(str(r.get("mode") or "run")) + ": " + _snippet(text, 80), body=text, tool=str(r.get("mode") or ""),
                           status=str(r.get("provenance") or ""), created_at=r.get("created_at") or "", changed_at=r.get("created_at") or "",
                           version=str(new_off), meta={"job_id": jid, "parent_trace_id": r.get("parent_trace_id") or "", "chars": r.get("chars")},
                           open_={"operation": jid} if jid else {}, related=[item_id("operations", "operation", jid)] if jid else []))
    _wm_set(conn, gen, "inputs", "offset", new_off)
    return items, deletes, True


def _scan_receipts(conn, gen, full: bool):
    """Receipt-only runs: a receipt whose run has no result snapshot (the
    recovery cases) is still a run in the record."""
    items, deletes = [], []
    d = cli.RECEIPTS_DIR
    known = {} if full else json.loads(_wm_get(conn, gen, "receipts", "versions", "{}") or "{}")
    seen = {}
    if d.exists():
        for p in sorted(d.glob("*.json")):
            if p.name.startswith("."):
                continue
            v = _file_version(p)
            seen[p.name] = v
            if not full and known.get(p.name) == v:
                continue
            rec = _read_json(p)
            if not isinstance(rec, dict):
                continue
            trace = rec.get("trace_id") or p.stem.replace("receipt_", "")
            if (cli.RESULTS_DIR / f"{trace}.json").exists():
                continue
            titles = [c.get("title", "") for c in (rec.get("candidates") or []) if isinstance(c, dict) and c.get("title")]
            items.append(_item("receipts", "run", trace, title=(str(rec.get("operation") or "run") + ": " + (" · ".join(titles[:3]) or trace)), body="\n".join(titles),
                               tool=str(rec.get("operation") or ""), status="receipt only", created_at=rec.get("created_at") or "", changed_at=rec.get("created_at") or "",
                               version=v, meta={"trace_id": trace, "receipt_id": rec.get("receipt_id") or "", "titles": titles[:12]}, open_={"place": "/?trace=" + trace}))
    for name in set(known) - set(seen):
        deletes.append(item_id("receipts", "run", name[:-5].replace("receipt_", "")))
    _wm_set(conn, gen, "receipts", "versions", json.dumps(seen, sort_keys=True))
    return items, deletes, True


def _scan_readings(conn, gen, full: bool):
    """The readers' readings: the passage read and what each reader said."""
    import moira
    items, deletes = [], []
    d = moira.readings_dir()
    known = {} if full else json.loads(_wm_get(conn, gen, "readings", "versions", "{}") or "{}")
    seen = {}
    if d.exists():
        for p in sorted(d.glob("*.json")):
            v = _file_version(p)
            # a reading changes as its responses land: the version includes the responses' presence
            rd = _read_json(p)
            if not isinstance(rd, dict):
                continue
            rid = rd.get("reading_id") or p.stem
            resp_text, statuses = [], {}
            for r in rd.get("readers") or []:
                res = moira.load_response(r.get("response_id") or "") if r.get("response_id") else None
                statuses[r.get("reader")] = (res or {}).get("status") or r.get("status") or ""
                for s in ((res or {}).get("segments") or [])[:40]:
                    if s.get("text"):
                        resp_text.append(str(s["text"]))
            v2 = v + ":" + hashlib.sha256(json.dumps(statuses, sort_keys=True).encode()).hexdigest()[:8]
            seen[p.name] = v2
            if not full and known.get(p.name) == v2:
                continue
            pending = sum(1 for s in statuses.values() if s not in ("complete", "done", "failed", "unusable"))
            items.append(_item("moira", "reading", rid, title="Readers: " + _snippet(rd.get("input_text") or "", 80), body=(rd.get("input_text") or "") + "\n\n" + "\n".join(resp_text),
                               tool="readers", status=("waiting for " + str(pending)) if pending else "all readers answered", created_at=rd.get("created_at") or "",
                               changed_at=rd.get("created_at") or "", version=v2, meta={"reading_id": rid, "statuses": json.dumps(statuses, sort_keys=True), "document": json.dumps(rd.get("document") or {})},
                               open_={"reading": rid}))
    for name in set(known) - set(seen):
        deletes.append(item_id("moira", "reading", name[:-5]))
    _wm_set(conn, gen, "readings", "versions", json.dumps(seen, sort_keys=True))
    return items, deletes, True


def _scan_carries(conn, gen, full: bool):
    """Revision notes (carries), by append offset; a note's standing is the
    latest row about it."""
    items, deletes = [], []
    p = root() / "carries.jsonl"
    off = 0 if full else int(_wm_get(conn, gen, "carries", "offset", "0") or 0)
    rows, new_off, truncated = _jsonl_rows(p, off)
    if truncated:
        rows, new_off, _ = _jsonl_rows(p, 0)
    for r in rows:
        cid = r.get("carry_id") or ""
        if not cid:
            continue
        src_ = r.get("source") or {}
        an = r.get("analyzed") or {}
        excerpt = str(r.get("excerpt") or (src_.get("ref") or {}).get("title") or "")
        items.append(_item("carries", "note", cid, title="Note: " + _snippet(excerpt or r.get("note") or "", 80), body=(excerpt + "\n" + str(r.get("note") or "")).strip(),
                           tool="revision notes", status=str(r.get("kind") or ""), created_at=r.get("at") or "", changed_at=r.get("at") or "", version=str(new_off),
                           meta={"trace_id": src_.get("trace_id") or "", "standing": r.get("standing") or "", "draft_head": an.get("head") or ""},
                           open_={"place": "/?trace=" + str(src_.get("trace_id") or "")} if src_.get("trace_id") else {}))
    _wm_set(conn, gen, "carries", "offset", new_off)
    return items, deletes, True


def _scan_concepts(conn, gen, full: bool):
    """Accepted concepts: the shelf as ruled — name, definition, status —
    with the count of rulings on record, from the file as a whole (its
    version is the update signal)."""
    items, deletes = [], []
    p = cli.ACCEPTED_CONCEPTS_PATH if hasattr(cli, "ACCEPTED_CONCEPTS_PATH") else root() / "accepted_concepts.json"
    v = _file_version(p)
    if not full and _wm_get(conn, gen, "concepts", "version", "") == v:
        return items, deletes, True
    rows = _read_json(p) if p.exists() else []
    rulings = {}
    jp = root() / "judgments.jsonl"
    if jp.exists():
        for j in _jsonl_rows(jp, 0)[0]:
            cid = j.get("concept_id") or ""
            if cid:
                rulings[cid] = rulings.get(cid, 0) + 1
    seen = set()
    for r in rows if isinstance(rows, list) else []:
        cid = r.get("concept_id") or r.get("id") or ""
        if not cid:
            continue
        seen.add(cid)
        items.append(_item("concepts", "concept", cid, title=str(r.get("name") or r.get("title") or cid), body=str(r.get("definition") or "") + "\n" + str(r.get("plain_gloss") or ""),
                           tool="shelf", status=str(r.get("status") or ""), created_at=r.get("accepted_at") or "", changed_at=r.get("accepted_at") or "",
                           version=v, meta={"concept_id": cid, "accepted_from": r.get("accepted_from") or "", "rulings": rulings.get(cid, 0), "version": r.get("version")},
                           open_={"place": "/?trace=" + str(r.get("accepted_from") or "")} if r.get("accepted_from") else {"place": "/#concepts"}))
    known = set(json.loads(_wm_get(conn, gen, "concepts", "ids", "[]") or "[]"))
    for cid in known - seen:
        deletes.append(item_id("concepts", "concept", cid))
    _wm_set(conn, gen, "concepts", "version", v)
    _wm_set(conn, gen, "concepts", "ids", json.dumps(sorted(seen)))
    return items, deletes, True


def _scan_jsonl_simple(store: str, kind: str, path: Path, id_key: str, title_of, body_of, tool: str, status_of, when_key: str, open_of):
    def scan(conn, gen, full: bool):
        items, deletes = [], []
        off = 0 if full else int(_wm_get(conn, gen, store, "offset", "0") or 0)
        rows, new_off, truncated = _jsonl_rows(path, off)
        if truncated:
            rows, new_off, _ = _jsonl_rows(path, 0)
        for r in rows:
            nid = r.get(id_key) or ""
            if not nid:
                continue
            items.append(_item(store, kind, nid, title=title_of(r), body=body_of(r), tool=tool, status=status_of(r), created_at=r.get(when_key) or "",
                               changed_at=r.get(when_key) or "", version=str(new_off), meta={k: v for k, v in r.items() if isinstance(v, (str, int, float)) and k not in (id_key,)}, open_=open_of(r)))
        _wm_set(conn, gen, store, "offset", new_off)
        return items, deletes, True
    return scan


def _scan_json_map(store: str, kind: str, path_fn, rows_of, native_of, title_of, body_of, tool: str, status_of, when_of, open_of):
    def scan(conn, gen, full: bool):
        items, deletes = [], []
        p = path_fn()
        v = _file_version(p)
        if not full and _wm_get(conn, gen, store, "version", "") == v:
            return items, deletes, True
        data = _read_json(p) if p.exists() else None
        seen = set()
        for r in rows_of(data):
            nid = native_of(r)
            if not nid:
                continue
            seen.add(nid)
            items.append(_item(store, kind, nid, title=title_of(r), body=body_of(r), tool=tool, status=status_of(r), created_at=when_of(r), changed_at=when_of(r),
                               version=v, meta={k: v_ for k, v_ in r.items() if isinstance(v_, (str, int, float))}, open_=open_of(r)))
        known = set(json.loads(_wm_get(conn, gen, store, "ids", "[]") or "[]"))
        for nid in known - seen:
            deletes.append(item_id(store, kind, nid))
        _wm_set(conn, gen, store, "version", v)
        _wm_set(conn, gen, store, "ids", json.dumps(sorted(seen)))
        return items, deletes, True
    return scan


def _adapters() -> list[tuple[str, callable]]:
    lib = root() / "library"
    fed = root() / "federation"
    return [
        ("notebook", _scan_notebook),
        ("operations", _scan_operations),
        ("results", _scan_results),
        ("receipts", _scan_receipts),
        ("inputs", _scan_inputs),
        ("readings", _scan_readings),
        ("carries", _scan_carries),
        ("concepts", _scan_concepts),
        ("saved_words", _scan_jsonl_simple("saved_words", "word", root() / "saved_words.jsonl", "saved_id",
                                           lambda r: f"{r.get('word', '')} ({r.get('language', '')})", lambda r: str(r.get("intended_meaning") or "") + "\n" + str(r.get("intended_title") or ""),
                                           "related words", lambda r: "removed" if r.get("removed") else "saved", "at",
                                           lambda r: {"place": "/?trace=" + str(r.get("trace_id") or "")} if r.get("trace_id") else {"place": "/#library"})),
        ("questions", _scan_jsonl_simple("questions", "question", root() / "open_questions.jsonl", "question_id",
                                         lambda r: _snippet(r.get("text") or "", 100), lambda r: str(r.get("text") or ""), "questions",
                                         lambda r: str(r.get("status") or "open"), "created_at", lambda r: {"place": "/#questions"})),
        ("library", _scan_json_map("library", "source", lambda: lib / "documents.json", lambda d: [dict(v, _id=k) for k, v in (d or {}).items()] if isinstance(d, dict) else [],
                                   lambda r: r.get("_id"), lambda r: str(r.get("title") or r.get("_id")), lambda r: "", "library",
                                   lambda r: str(r.get("kind") or ""), lambda r: str(r.get("created_at") or ""), lambda r: {"place": "/#library"})),
        ("media", _scan_jsonl_simple("media", "media", lib / "media.jsonl", "media_id", lambda r: str(r.get("title") or r.get("media_id")), lambda r: "",
                                     "recordings", lambda r: str(r.get("kind") or ""), "created_at", lambda r: {"place": "/#library"})),
        ("rooms", _scan_json_map("rooms", "room", lambda: root() / "clinic" / "rooms.json", lambda d: list((d or {}).values()) if isinstance(d, dict) else [],
                                 lambda r: r.get("room_id"), lambda r: str(r.get("title") or r.get("room_id")), lambda r: "", "clinic",
                                 lambda r: f"{len(r.get('member_source_ids') or [])} of {len(r.get('seats') or [])} seats filled", lambda r: str(r.get("created_at") or ""),
                                 lambda r: {"place": "/clinic?room=" + str(r.get("room_id") or "")})),
        ("investigation_rooms", _scan_jsonl_simple("investigation_rooms", "room", fed / "investigation_rooms.jsonl", "room_id", lambda r: str(r.get("title") or r.get("room_id")),
                                                   lambda r: "", "investigations", lambda r: "investigation room", "recorded_at", lambda r: {"place": "/rooms"})),
        ("depositions", _scan_jsonl_simple("depositions", "deposition", fed / "depositions.jsonl", "deposition_id",
                                           lambda r: f"{r.get('producer', '')}: {r.get('object_type', '')} {r.get('object_id', '')}", lambda r: str(r.get("subject") or ""),
                                           "investigations", lambda r: str(r.get("verification") or r.get("status") or "in custody"), "imported_at", lambda r: {"place": "/rooms"})),
        ("inquiry", _scan_jsonl_simple("inquiry", "inquiry", root() / "inquiry" / "inquiry.jsonl", "inquiry_id", lambda r: str(r.get("title") or r.get("inquiry_id")),
                                       lambda r: str(r.get("root_question") or ""), "inquiry", lambda r: str(r.get("status") or ""), "created_at", lambda r: {"place": "/inquiry"})),
        ("recovery", _scan_jsonl_simple("recovery", "recovery", root() / "recovery_review_queue.jsonl", "judgment_id", lambda r: "Recovery case: " + str(r.get("title") or ""),
                                        lambda r: str(r.get("note") or ""), "recovery review", lambda r: str(r.get("status") or ""), "queued_at", lambda r: {"place": "/recovery"})),
    ]


# ---- archive rulings --------------------------------------------------------------

def archive(item_id_: str, on: bool, by: str = "owner") -> dict:
    row = {"item_id": item_id_, "archived": bool(on), "at": _now(), "by": by}
    p = archive_log()
    p.parent.mkdir(parents=True, exist_ok=True)
    with open(p, "a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    conn = _connect()
    try:
        conn.execute("UPDATE items SET archived = ? WHERE item_id = ?", (1 if on else 0, item_id_))
    finally:
        conn.close()
    return row


def _apply_archive(conn, gen, full: bool) -> None:
    p = archive_log()
    off = 0 if full else int(_wm_get(conn, gen, "archive", "offset", "0") or 0)
    rows, new_off, truncated = _jsonl_rows(p, off)
    if truncated:
        rows, new_off, _ = _jsonl_rows(p, 0)
    for r in rows:
        conn.execute("UPDATE items SET archived = ? WHERE gen = ? AND item_id = ?", (1 if r.get("archived") else 0, gen, r.get("item_id") or ""))
    _wm_set(conn, gen, "archive", "offset", new_off)


# ---- refresh and rebuild ------------------------------------------------------------

def refresh(max_age_s: float = 0.0) -> dict:
    """Incremental: every adapter reads what changed since its watermark
    into the current generation. Short transactions per adapter. A failing
    adapter marks the index incomplete and is retried next time; the others
    proceed."""
    if max_age_s and time.time() - _LAST["refresh_at"] < max_age_s:
        return {"skipped": True, **health()}
    if not _LOCK.acquire(timeout=10):
        return {"skipped": True, "busy": True, **health()}
    try:
        conn = _connect()
        try:
            gen = generation(conn)
            if gen == 0:
                conn.close()
                return rebuild()
            failed = []
            n_up = n_del = 0
            for name, scan in _adapters():
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    items, deletes, complete = scan(conn, gen, False)
                    for it in items:
                        _upsert(conn, gen, it)
                    for iid in deletes:
                        _delete(conn, gen, iid)
                    conn.execute("COMMIT")
                    n_up += len(items); n_del += len(deletes)
                    if not complete:
                        failed.append(name + ": incomplete")
                except Exception as e:  # noqa: BLE001
                    try:
                        conn.execute("ROLLBACK")
                    except sqlite3.OperationalError:
                        pass
                    failed.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            try:
                conn.execute("BEGIN IMMEDIATE")
                _apply_archive(conn, gen, False)
                conn.execute("COMMIT")
            except Exception as e:  # noqa: BLE001
                try:
                    conn.execute("ROLLBACK")
                except sqlite3.OperationalError:
                    pass
                failed.append(f"archive: {type(e).__name__}: {str(e)[:120]}")
            _set_meta(conn, "last_refresh_at", _now())
            _set_meta(conn, "incomplete", "; ".join(failed))
        finally:
            conn.close()
        _LAST["refresh_at"] = time.time()
        _LAST["incomplete_why"] = "; ".join(failed)
        return {"upserted": n_up, "deleted": n_del, "failed": failed, **health()}
    finally:
        _LOCK.release()


def rebuild() -> dict:
    """Everything again, into a new generation; the switch is one short
    transaction; a failure leaves the last working generation current."""
    if not _LOCK.acquire(timeout=60):
        return {"skipped": True, "busy": True, **health()}
    try:
        conn = _connect()
        try:
            old = generation(conn)
            new = old + 1
            failed = []
            n = 0
            for name, scan in _adapters():
                try:
                    conn.execute("BEGIN IMMEDIATE")
                    items, _deletes, complete = scan(conn, new, True)
                    for it in items:
                        _upsert(conn, new, it)
                    conn.execute("COMMIT")
                    n += len(items)
                    if not complete:
                        failed.append(name + ": incomplete")
                except Exception as e:  # noqa: BLE001
                    try:
                        conn.execute("ROLLBACK")
                    except sqlite3.OperationalError:
                        pass
                    failed.append(f"{name}: {type(e).__name__}: {str(e)[:120]}")
            if any(not f.endswith(": incomplete") for f in failed) and n == 0:
                # nothing built and something broke: the old generation stays
                conn.execute("DELETE FROM items WHERE gen = ?", (new,))
                conn.execute("DELETE FROM watermarks WHERE gen = ?", (new,))
                _set_meta(conn, "last_error", "; ".join(failed))
                return {"rebuilt": False, "failed": failed, **health()}
            conn.execute("BEGIN IMMEDIATE")
            _apply_archive(conn, new, True)
            _set_meta(conn, "generation", new)
            _set_meta(conn, "built_at", _now())
            _set_meta(conn, "last_refresh_at", _now())
            _set_meta(conn, "incomplete", "; ".join(failed))
            conn.execute("DELETE FROM items WHERE gen != ?", (new,))
            conn.execute("DELETE FROM watermarks WHERE gen != ?", (new,))
            conn.execute("COMMIT")
            _LAST["refresh_at"] = time.time()
            _LAST["incomplete_why"] = "; ".join(failed)
            return {"rebuilt": True, "generation": new, "items": n, "failed": failed, **health()}
        finally:
            conn.close()
    finally:
        _LOCK.release()


def health() -> dict:
    """What the page may say about the index: measured pending counts, the
    generation, when it was built and refreshed, and whether it is
    incomplete — never a promise it cannot keep."""
    out = {"generation": 0, "items": 0, "built_at": "", "last_refresh_at": "", "incomplete": "", "fts": False, "pending": {}, "population": ""}
    try:
        conn = _connect()
    except sqlite3.Error as e:
        return {**out, "incomplete": f"the index cannot be opened: {e}"}
    try:
        gen = generation(conn)
        out.update({"generation": gen, "items": int(conn.execute("SELECT COUNT(*) FROM items WHERE gen = ?", (gen,)).fetchone()[0]),
                    "built_at": _meta(conn, "built_at", ""), "last_refresh_at": _meta(conn, "last_refresh_at", ""),
                    "incomplete": _meta(conn, "incomplete", ""), "fts": _meta(conn, "fts", "0") == "1"})
        pending = {}
        try:
            import notebook as nbk
            if nbk.db_path().exists():
                src = sqlite3.connect(str(nbk.db_path()), timeout=BUSY_TIMEOUT_S)
                try:
                    if src.execute("SELECT name FROM sqlite_master WHERE type = 'table' AND name = 'index_outbox'").fetchone():
                        pending["notebook"] = int(src.execute("SELECT COUNT(*) FROM index_outbox WHERE done = 0").fetchone()[0])
                finally:
                    src.close()
        except Exception:  # noqa: BLE001
            pending["notebook"] = None
        try:
            import operations as ops
            if ops.db_path().exists():
                src = sqlite3.connect(str(ops.db_path()), timeout=BUSY_TIMEOUT_S)
                try:
                    top = src.execute("SELECT COALESCE(MAX(seq), 0) FROM operation_events").fetchone()[0]
                    pending["operations"] = max(0, int(top) - int(_wm_get(conn, gen, "operations", "event_seq", "0") or 0))
                finally:
                    src.close()
        except Exception:  # noqa: BLE001
            pending["operations"] = None
        out["pending"] = pending
        out["updating"] = any((v or 0) > 0 for v in pending.values()) or bool(out["incomplete"])
        out["population"] = f"{out['items']} items from {len(_adapters())} stores, generation {gen}" + (" (incomplete)" if out["incomplete"] else "")
        return out
    finally:
        conn.close()


# ---- search --------------------------------------------------------------------------

_TERM = re.compile(r"[\wÀ-￿']+", re.UNICODE)


def _fts_query(q: str) -> str:
    """The user's words as literal FTS terms, quoted and ANDed — no operator
    syntax reaches the engine, so no query is malformed by construction."""
    terms = _TERM.findall(q or "")
    return " AND ".join('"' + t.replace('"', '""') + '"' for t in terms[:12])


def search(q: str = "", *, kind: str = "", tool: str = "", status: str = "", since: str = "", until: str = "", archived: str = "no",
           cursor: str = "", limit: int = 30) -> dict:
    """Local search over the current generation. Filters are exact fields;
    paging is stable (changed_at, item_id); user text is bound as a
    parameter, never spliced. FTS when the engine has it, a literal LIKE
    fallback when it does not or the match fails."""
    limit = max(1, min(int(limit or 30), 100))
    conn = _connect()
    try:
        gen = generation(conn)
        where, args = ["i.gen = ?"], [gen]
        if kind:
            where.append("i.kind = ?"); args.append(kind)
        if tool:
            where.append("i.tool = ?"); args.append(tool)
        if status:
            where.append("i.status LIKE ?"); args.append(status + "%")
        if since:
            where.append("i.changed_at >= ?"); args.append(since)
        if until:
            where.append("i.changed_at <= ?"); args.append(until + ("￿" if len(until) <= 10 else ""))
        if archived == "no":
            where.append("i.archived = 0")
        elif archived == "only":
            where.append("i.archived = 1")
        if cursor:
            try:
                c_at, c_id = cursor.split("|", 1)
            except ValueError:
                raise IndexError_("bad cursor")
            where.append("(i.changed_at < ? OR (i.changed_at = ? AND i.item_id < ?))"); args += [c_at, c_at, c_id]
        mode = "recent"
        fq = _fts_query(q)
        rows = []
        if fq and _meta(conn, "fts", "0") == "1":
            try:
                rows = conn.execute(
                    "SELECT i.*, snippet(items_fts, 1, '[', ']', '…', 14) AS hit FROM items_fts JOIN items i ON i.rowid = items_fts.rowid "
                    "WHERE items_fts MATCH ? AND " + " AND ".join(where) + " ORDER BY i.changed_at DESC, i.item_id DESC LIMIT ?",
                    [fq] + args + [limit + 1]).fetchall()
                mode = "fts"
            except sqlite3.OperationalError:
                rows = []
                mode = "like"
        if fq and mode != "fts":
            like = "%" + (q or "").strip() + "%"
            rows = conn.execute("SELECT i.*, '' AS hit FROM items i WHERE (i.title LIKE ? OR i.body LIKE ? OR i.meta_text LIKE ?) AND " + " AND ".join(where) +
                                " ORDER BY i.changed_at DESC, i.item_id DESC LIMIT ?", [like, like, like] + args + [limit + 1]).fetchall()
            mode = "like"
        elif not fq:
            rows = conn.execute("SELECT i.*, '' AS hit FROM items i WHERE " + " AND ".join(where) + " ORDER BY i.changed_at DESC, i.item_id DESC LIMIT ?", args + [limit + 1]).fetchall()
        more = len(rows) > limit
        rows = rows[:limit]
        items = [_public(r) for r in rows]
        h = health()
        return {"items": items, "query": q or "", "mode": mode, "next_cursor": (f"{rows[-1]['changed_at']}|{rows[-1]['item_id']}" if more and rows else None),
                "filters": {"kind": kind, "tool": tool, "status": status, "since": since, "until": until, "archived": archived},
                "health": h, "population": ("every indexed item" + (" matching the words" if fq else "")) + (", archived only" if archived == "only" else (", archive excluded" if archived == "no" else "")),
                "exhaustive": not h.get("updating") and not h.get("incomplete"),
                "kinds": {r["kind"]: int(r["n"]) for r in conn.execute("SELECT kind, COUNT(*) AS n FROM items WHERE gen = ? AND archived = 0 GROUP BY kind", (gen,)).fetchall()}}
    finally:
        conn.close()


def _action_label(action_id: str) -> str:
    """The registry's label for an action id (the review of 6e5b59c: the page
    shows labels; the ids stay in details). Empty when the id is not in the
    registry, so the caller keeps the id."""
    if not action_id:
        return ""
    try:
        import actions as _ac
        a = _ac.BY_ID.get(action_id)
        return str(a["label"]) if a else ""
    except Exception:  # noqa: BLE001
        return ""


def _public(r) -> dict:
    d = dict(r)
    d.pop("body", None); d.pop("meta_text", None); d.pop("rowid", None); d.pop("gen", None)
    d["tool_label"] = _action_label(d.get("tool") or "") or (d.get("tool") or "")
    for k in ("meta", "open", "related"):
        try:
            d[k] = json.loads(d.get(k) or ("[]" if k == "related" else "{}"))
        except json.JSONDecodeError:
            d[k] = [] if k == "related" else {}
    d["kind_label"] = KIND_LABELS.get(d["kind"], d["kind"])
    d["archived"] = bool(d.get("archived"))
    if d.get("hit"):
        d["snippet"] = d["hit"]
    d.pop("hit", None)
    return d


def resolve(item_id_: str) -> dict | None:
    """One item, typed, with how to reopen it — read from the index and,
    for what the index only points at, verified against the store."""
    conn = _connect()
    try:
        gen = generation(conn)
        r = conn.execute("SELECT i.*, '' AS hit FROM items i WHERE gen = ? AND item_id = ?", (gen, item_id_)).fetchone()
        if r is None:
            return None
        d = _public(r)
        d["body"] = r["body"]
        exists = True
        try:
            if d["store"] == "notebook":
                import notebook as nbk
                exists = nbk.get(d["native_id"]) is not None
            elif d["store"] in ("results",):
                exists = (cli.RESULTS_DIR / f"{d['native_id']}.json").exists()
            elif d["store"] == "operations":
                import operations as ops
                exists = ops.get(d["native_id"]) is not None
        except Exception:  # noqa: BLE001
            exists = True
        d["exists"] = exists
        return d
    finally:
        conn.close()


# ---- periodic reconciliation ---------------------------------------------------------

_PERIODIC = {"thread": None, "stop": False, "interval": 60.0}


def start_periodic(interval_s: float = 60.0) -> None:
    """A serving process reconciles the file stores on a timer; the SQLite
    stores reach the index through their outboxes on the same timer and on
    every read of Your work."""
    if _PERIODIC["thread"] is not None:
        return
    _PERIODIC["interval"] = interval_s

    def loop():
        while not _PERIODIC["stop"]:
            try:
                refresh()
            except Exception as e:  # noqa: BLE001
                _LAST["error"] = str(e)
            for _ in range(int(interval_s * 10)):
                if _PERIODIC["stop"]:
                    break
                time.sleep(0.1)
    t = threading.Thread(target=loop, daemon=True, name="work-index")
    _PERIODIC["thread"] = t
    t.start()
