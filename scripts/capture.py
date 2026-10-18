"""W2 — capture at revision boundaries (his ruling, 2026-10-16; built on
his "ok go", 2026-10-17). The content layer of the extraction program:
what the attention Ledger deliberately refuses to hold (bodies), kept in
its own store under the same roof, the same switch and the same seal.

This module holds the SEARCH QUERIES — the owner's own words typed into
the record's search boxes, with scope and hit count, monthly JSONL under
local_state/capture/. Draft revision bodies live where draft custody
already lives (scripts/notebook.py, content-addressed in the notebook's
own database) rather than in a second store that would split custody;
this module reads nothing from there and only answers for queries.

The laws it keeps: the Ledger's visible switch governs capture too — off
means nothing new is kept and everything already written stays (a stop,
never an eraser); a malformed entry refuses by name rather than being
repaired; a query longer than the cap is refused whole, never truncated
into something the owner did not type; everything here is timestamped
twice (the page's clock and the store's), retrievable by day, exportable,
and sealed into the encrypted Vault with the rest of the store. An edit
is CANDIDATE FEEDBACK: nothing in this store or the notebook's revisions
labels an earlier wording "rejected" — original, edit and context are
kept together and judged only under review, never by a pipeline.
"""
from __future__ import annotations

import json
import fcntl
import os
import pathlib
import re
import uuid
from contextlib import contextmanager
from datetime import datetime, timezone

import ledger
import wordicon_cli as cli

SCOPES = ("library", "work")      # the search boxes that reach the server today
MAX_QUERY = 500
GAP_REFS = {"job_id", "op_id", "run_trace_id", "source_id", "target_id", "scope",
            "prepared_id", "snapshot_id", "doc_id", "attempt_id"}


@contextmanager
def _recording_guard():
    # Same lock as the visible switch: no body or gap can be appended after
    # an acknowledged Off, even if its request passed an earlier check.
    directory = ledger._dir()
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "append.lock", "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        yield enabled()


def _append(name, row):
    """Keep a complete fsynced line, preserving an interrupted prior tail."""
    with _recording_guard() as recording:
        if not recording:
            return False
        _append_enabled(name, row)
    return True


def _append_enabled(name, row):
    directory = _dir()
    directory.mkdir(parents=True, exist_ok=True)
    with open(directory / "append.lock", "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = directory / name
        fd = os.open(path, os.O_RDWR | os.O_CREAT | os.O_APPEND, 0o600)
        with os.fdopen(fd, "a+b") as f:
            f.seek(0, os.SEEK_END)
            size = f.tell()
            if size:
                f.seek(-1, os.SEEK_END)
                if f.read(1) != b"\n":
                    f.write(b"\n")
            f.write((json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n").encode())
            f.flush(); os.fsync(f.fileno())
        fd = os.open(directory, os.O_RDONLY)
        try:
            os.fsync(fd)
        finally:
            os.close(fd)


def gap(kind: str, references: dict = None, error_class: str = "") -> dict:
    """A failed capture is visible without copying its content or exception."""
    if not enabled():
        return {"kept": False, "durable": False, "why": "recording_off"}
    from operation_capture import sanitize_body
    refs = {}
    for key, value in (references or {}).items():
        if (key in GAP_REFS and isinstance(value, str)
                and re.fullmatch(r"[A-Za-z0-9_.:/+-]{1,200}", value)
                and not sanitize_body(value)["redactions"]):
            refs[key] = value
    kind = kind if isinstance(kind, str) and re.fullmatch(r"[a-z_]{1,80}", kind) else "capture_failed"
    error_class = error_class if isinstance(error_class, str) and re.fullmatch(r"[A-Za-z_]{0,80}", error_class) else ""
    row = {"schema": "nikodemus.capture_gap.v1", "gap_id": "gap_" + uuid.uuid4().hex,
           "at": _now(), "kind": kind, "references": refs, "error_class": error_class}
    try:
        if _append(f"gaps-{row['at'][:7]}.jsonl", row) is False:
            return {"kept": False, "durable": False, "why": "recording_off"}
        return {"kept": True, "durable": True, "gap_id": row["gap_id"]}
    except OSError:
        # The caller must surface this return: a broken disk cannot promise a
        # durable record of its own failure, and must not erase the original.
        return {"kept": False, "durable": False, "why": "capture_gap_store_unavailable", "kind": kind}


def _read_lines(paths):
    rows, gaps = [], []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as e:
            gaps.append({"kind": "unreadable_file", "file": path.name, "error_class": type(e).__name__})
            continue
        for index, line in enumerate(text.splitlines(), 1):
            try:
                row = json.loads(line)
                if not isinstance(row, dict):
                    raise ValueError("not an object")
            except (ValueError, TypeError):
                gaps.append({"kind": "malformed_record", "file": path.name, "line": index})
                continue
            rows.append(row)
    return rows, gaps


def read_gaps(limit: int = 2000) -> dict:
    rows, gaps = _read_lines(sorted(_dir().glob("gaps-*.jsonl")))
    limit = max(1, min(int(limit), 2000))
    return {"gaps": rows[-limit:], "read_gaps": gaps, "truncated": len(rows) > limit, "enabled": enabled()}


def _dir() -> pathlib.Path:
    return pathlib.Path(cli.LOCAL_STATE) / "capture"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def enabled() -> bool:
    """One recording switch for the whole self-data layer: the Ledger's."""
    return ledger.enabled()


def query(scope: str, q: str, hits) -> dict:
    """Keep one search the owner performed. Called by the search routes
    themselves, so every caller of the route is covered; nothing here is
    guessed from the page."""
    if not enabled():
        return {"kept": False, "why": "recording is off (the Ledger switch in Settings governs capture too)"}
    if scope not in SCOPES:
        return {"kept": False, "refused": True, "why": f"capture does not hold a {scope!r} search"}
    q = str(q or "").strip()
    if not q:
        return {"kept": False, "why": "an empty search is not kept"}
    if len(q) > MAX_QUERY:
        return {"kept": False, "refused": True,
                "why": f"a query is kept whole or not at all; this one is {len(q)} characters (cap {MAX_QUERY})",
                "capture_gap": gap("query_over_limit", {"scope": scope})}
    from operation_capture import sanitize_body
    if sanitize_body(q)["redactions"]:
        return {"kept": False, "refused": True, "why": "credential_like_query_not_retained",
                "capture_gap": gap("query_credential_excluded", {"scope": scope})}
    at = _now()
    row = {"at": at, "scope": scope, "q": q, "query_id": "query_" + uuid.uuid4().hex,
           "hits": hits if type(hits) is int and hits >= 0 else None}
    try:
        # This hook rides inside the search route itself: a store that cannot
        # write must never break the search the owner just performed. The
        # failure is reported in the return, not raised into the room.
        if _append(f"queries-{at[:7]}.jsonl", row) is False:
            return {"kept": False, "why": "recording_off"}
    except OSError as e:
        return {"kept": False, "why": f"the capture store could not be written ({e.__class__.__name__}); the search itself is unaffected",
                "capture_gap": gap("query_write_failed", {"scope": scope}, type(e).__name__)}
    return {"kept": True, "query_id": row["query_id"]}


def read_queries(day: str = "", limit: int = 2000) -> dict:
    """The owner's searches back, oldest first, capped and saying so."""
    out = []
    paths = sorted(_dir().glob("queries-*.jsonl")) if day else sorted(_dir().glob("queries-*.jsonl"))[-1:]
    rows, gaps = _read_lines(paths)
    for row in rows:
        if not day or str(row.get("at", "")).startswith(day):
            out.append(row)
    truncated = len(out) > limit
    return {"queries": out[-limit:], "truncated": truncated, "enabled": enabled(), "read_gaps": gaps,
            "population": f"the capture file(s) read whole from the store; {len(out)} search(es) matched"
                          + (f", the newest {limit} returned" if truncated else "")}
