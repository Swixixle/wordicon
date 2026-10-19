"""Incremental edge and ruling projections inside the existing work index.

The source logs remain authoritative. Rows are keyed by their byte position,
not by an id that may repeat, and carry the original JSON. A refresh advances
its watermark only after every complete line in the new prefix was read. A
bad line or value shape raises with its location; the caller rolls back this
family and marks the index incomplete.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import sqlite3
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[1]))
from work_history import endpoints  # noqa: E402


class HistoryReadError(Exception):
    """The source cannot support an exhaustive relationship answer."""


DDL = (
    """CREATE TABLE IF NOT EXISTS history_edges (
        gen INTEGER NOT NULL, line_offset INTEGER NOT NULL,
        edge_id TEXT NOT NULL, rel TEXT NOT NULL,
        source_key TEXT, source_kind TEXT, source_label TEXT, source_concept_id TEXT,
        target_key TEXT, target_kind TEXT, target_label TEXT, target_concept_id TEXT,
        source_gap TEXT, target_gap TEXT,
        basis TEXT NOT NULL, producer_kind TEXT, producer_id TEXT, producer_stage TEXT,
        producer_gap TEXT,
        verdict TEXT, created_at TEXT, run_trace_id TEXT,
        search_text TEXT NOT NULL, raw TEXT NOT NULL,
        PRIMARY KEY (gen, line_offset))""",
    """CREATE TABLE IF NOT EXISTS history_rulings (
        gen INTEGER NOT NULL, line_offset INTEGER NOT NULL,
        judgment_id TEXT NOT NULL, decision TEXT NOT NULL,
        decision_source TEXT NOT NULL, aspect_scope TEXT NOT NULL,
        concept_id TEXT, originating_operation TEXT,
        candidate_text TEXT, reason TEXT, failure_axis TEXT, ruled_at TEXT,
        search_text TEXT NOT NULL, raw TEXT NOT NULL,
        PRIMARY KEY (gen, line_offset))""",
    "CREATE INDEX IF NOT EXISTS history_edges_source ON history_edges (gen, source_key)",
    "CREATE INDEX IF NOT EXISTS history_edges_target ON history_edges (gen, target_key)",
    "CREATE INDEX IF NOT EXISTS history_rulings_concept ON history_rulings (gen, concept_id, aspect_scope)",
)

EDGE_COLUMNS = (
    "gen", "line_offset", "edge_id", "rel", "source_key", "source_kind",
    "source_label", "source_concept_id", "target_key", "target_kind",
    "target_label", "target_concept_id", "source_gap", "target_gap",
    "basis", "producer_kind", "producer_id", "producer_stage", "producer_gap",
    "verdict", "created_at", "run_trace_id", "search_text", "raw",
)


def ensure_schema(conn: sqlite3.Connection) -> None:
    """Add the projection atomically to a schema-1 index or verify schema 2."""
    row = conn.execute("SELECT value FROM meta WHERE key = 'schema'").fetchone()
    schema = row[0] if row else None
    if schema not in ("1", "2"):
        raise HistoryReadError(f"unsupported work index schema {schema!r}; no migration attempted")
    if schema == "2":
        tables = {row[0] for row in conn.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table' AND name IN ('history_edges', 'history_rulings')")}
        if tables != {"history_edges", "history_rulings"}:
            raise HistoryReadError("work index schema 2 is missing a history table")
        columns = {row[1] for row in conn.execute("PRAGMA table_info(history_edges)")}
        if "producer_gap" not in columns:
            conn.execute("BEGIN IMMEDIATE")
            try:
                conn.execute("ALTER TABLE history_edges ADD COLUMN producer_gap TEXT")
                for gen, offset, raw in conn.execute(
                        "SELECT gen, line_offset, raw FROM history_edges"):
                    producer = endpoints.declaring_producer(json.loads(raw).get("producer"))
                    if producer and producer["reason"]:
                        conn.execute("UPDATE history_edges SET producer_gap = ? "
                                     "WHERE gen = ? AND line_offset = ?",
                                     (producer["reason"], gen, offset))
                conn.execute("COMMIT")
            except Exception:
                conn.execute("ROLLBACK")
                raise
        return
    conn.execute("BEGIN IMMEDIATE")
    try:
        for sql in DDL:
            conn.execute(sql)
        conn.execute("UPDATE meta SET value = '2' WHERE key = 'schema'")
        conn.execute("COMMIT")
    except Exception:
        conn.execute("ROLLBACK")
        raise


def _string(value, field, *, optional=False):
    if value is None and optional:
        return None
    if not isinstance(value, str) or (not optional and not value.strip()):
        raise ValueError(f"{field} must be a nonempty string" if not optional else
                         f"{field}, when present, must be a string")
    return value


def _nullable_str(row, field):
    return _string(row.get(field), field, optional=True)


def _edge(row):
    edge_id = _string(row.get("edge_id"), "edge_id")
    rel = _string(row.get("rel"), "rel")
    source = endpoints.identify(row.get("source"), "edges", "source")
    target = endpoints.identify(row.get("target"), "edges", "target")
    producer = endpoints.declaring_producer(row.get("producer"))
    basis = "source_declared" if producer and producer["identity"] else "unknown"
    producer_gap = producer["reason"] if producer and producer["reason"] else None
    verdict = _nullable_str(row, "verdict") or None
    created = _nullable_str(row, "created_at")
    trace = _nullable_str(row, "run_trace_id")
    for side, endpoint in (("source", source), ("target", target)):
        for field in ("kind", "label"):
            value = endpoint[field]
            if value is not None and not isinstance(value, str):
                raise ValueError(f"{side}.{field}, when present, must be a string")
    for field in ("kind", "stage"):
        if producer and producer[field] is not None and not isinstance(producer[field], str):
            raise ValueError(f"producer.{field}, when present, must be a string")
    search = " ".join(str(value or "") for value in (
        source["label"], source["identity"], target["label"], target["identity"],
        rel, verdict, row.get("detail") if isinstance(row.get("detail"), str) else ""))
    return (edge_id, rel, source["identity"], source["kind"], source["label"],
            source["concept_id"], target["identity"], target["kind"], target["label"],
            target["concept_id"], source["reason"] or None, target["reason"] or None,
            basis, producer["kind"] if basis != "unknown" else None,
            producer["identity"] if basis != "unknown" else None,
            producer["stage"] if basis != "unknown" else None,
            producer_gap, verdict, created, trace, search)


def _ruling(row):
    judgment_id = _string(row.get("id"), "id")
    decision = _string(row.get("decision"), "decision")
    source = _string(row.get("decision_source"), "decision_source")
    if source not in ("owner", "validator"):
        raise ValueError("decision_source must be owner or validator")
    scope = _string(row.get("scope"), "scope")
    concept = _nullable_str(row, "concept_id")
    operation = _nullable_str(row, "originating_operation")
    candidate = _nullable_str(row, "candidate_text")
    reason = _nullable_str(row, "reason")
    failure = _nullable_str(row, "failure_axis")
    ruled_at = _nullable_str(row, "ruled_at")
    search = " ".join(value or "" for value in
                      (concept, candidate, reason, failure, decision, scope))
    return (judgment_id, decision, source, scope, concept, operation, candidate,
            reason, failure, ruled_at, search)


def scan(conn, gen: int, full: bool, family: str, path: pathlib.Path,
         watermark_get, watermark_set):
    """Scan one append log in the caller's transaction; return rows indexed.

    Offset and SHA of the consumed prefix detect replacement as well as
    truncation. No malformed row is skipped, including an unexpected optional
    field shape. An unfinished trailing line waits for the next refresh.
    """
    if family not in ("edges", "judgments"):
        raise ValueError(f"unknown history family {family!r}")
    path = pathlib.Path(path)
    if not path.is_file():
        raise HistoryReadError(f"{family}: required input {path} could not be read")
    try:
        data = path.read_bytes()
    except OSError as error:
        raise HistoryReadError(f"{family}: {path}: {error}") from error
    offset = 0 if full else int(watermark_get(conn, gen, family, "offset", "0") or 0)
    old_digest = "" if full else watermark_get(conn, gen, family, "prefix_sha256", "")
    if offset > len(data) or (offset and old_digest != hashlib.sha256(data[:offset]).hexdigest()):
        # A replaced log invalidates offsets and all its old projections.
        conn.execute("DELETE FROM history_edges WHERE gen = ?" if family == "edges" else
                     "DELETE FROM history_rulings WHERE gen = ?", (gen,))
        offset = 0
    if data and not data.endswith(b"\n"):
        last_newline = data.rfind(b"\n", offset)
        end = last_newline + 1 if last_newline >= offset else offset
    else:
        end = len(data)
    table = "history_edges" if family == "edges" else "history_rulings"
    n = 0
    position = offset
    for line in data[offset:end].splitlines(keepends=True):
        try:
            decoded = json.loads(line)
            if not isinstance(decoded, dict):
                raise ValueError("row is not an object")
            values = _edge(decoded) if family == "edges" else _ruling(decoded)
        except (UnicodeError, ValueError, TypeError) as error:
            line_number = data.count(b"\n", 0, position) + 1
            raise HistoryReadError(f"{family}: {path}:{line_number}: {error}") from error
        if family == "edges":
            conn.execute("INSERT INTO history_edges (" + ",".join(EDGE_COLUMNS) + ") VALUES (" +
                         ",".join("?" * len(EDGE_COLUMNS)) + ")",
                         (gen, position, *values, json.dumps(decoded, ensure_ascii=False, sort_keys=True)))
        else:
            conn.execute("INSERT INTO history_rulings VALUES (" + ",".join("?" * 14) + ")",
                         (gen, position, *values, json.dumps(decoded, ensure_ascii=False, sort_keys=True)))
        n += 1
        position += len(line)
    watermark_set(conn, gen, family, "offset", end)
    watermark_set(conn, gen, family, "prefix_sha256", hashlib.sha256(data[:end]).hexdigest())
    return n, end == len(data)


def pending_bytes(conn, gen: int, family: str, path: pathlib.Path, watermark_get):
    """Return unread bytes, or None if a consumed prefix has changed.

    A same-length rewrite is a pending change as surely as an append. The
    source remains authoritative until scan replaces the old projection.
    """
    data = pathlib.Path(path).read_bytes()
    offset = int(watermark_get(conn, gen, family, "offset", "0") or 0)
    digest = watermark_get(conn, gen, family, "prefix_sha256", "")
    if offset > len(data) or (offset and digest != hashlib.sha256(data[:offset]).hexdigest()):
        return None
    return len(data) - offset


def matches(conn: sqlite3.Connection, gen: int, query: str, limit: int = 50):
    """Literal topic match. Separate families are never joined by similarity."""
    terms = [term.casefold() for term in query.split() if term.strip()][:12]
    if not terms:
        return {"edges": [], "rulings": []}
    limit = max(1, min(int(limit), 100))
    # SQLite's built-in lower() folds ASCII only. Register the same Python
    # Unicode folding for stored text and query terms, including old rows.
    conn.create_function("history_casefold", 1,
                         lambda value: value.casefold() if isinstance(value, str) else "")
    out = {}
    for family, table in (("edges", "history_edges"), ("rulings", "history_rulings")):
        clause = " OR ".join("history_casefold(search_text) LIKE ? ESCAPE '\\'" for _ in terms)
        args = [gen] + ["%" + term.replace("\\", "\\\\").replace("%", "\\%")
                         .replace("_", "\\_") + "%" for term in terms] + [limit]
        rows = conn.execute(f"SELECT * FROM {table} WHERE gen = ? AND ({clause}) "
                            "ORDER BY line_offset DESC LIMIT ?", args).fetchall()
        out[family] = [{k: v for k, v in dict(row).items()
                        if k not in ("gen", "search_text", "raw")} for row in rows]
    return out
