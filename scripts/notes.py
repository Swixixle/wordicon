"""The owner's own notes, beside the work — one scratchpad per document.

What this is: prose ALEX TYPES, kept apart from everything a model
produced. A carry (scripts/carry.py) is the model's words travelling
under the label "may be useful while revising"; a note here is his own,
and the record says so on every row (`owner_authored: True`). The two are
never merged, never counted together, and never rendered as one list.

Shape, deliberately the same as carries: an append-only log folded into a
view. A note is written once, edited by appending, and removed by
appending — nothing in notes.jsonl is ever rewritten, so a change of mind
is kept rather than overwritten (his standing law). `state` says where a
note stands; `revision` counts the writes the record actually holds.

Duplicate protection: every write carries the client's request id. The
same id twice is the SAME write — the second returns what the first
recorded and appends nothing. A save that failed on the wire and is
retried therefore cannot become two notes, which is the difference
between "retry is safe" and "retry costs you a duplicate".

Concurrency: an edit names the revision it was made against. If the note
moved since (another tab, another device), the edit is REFUSED with both
bodies in the refusal, so the tab that has unsent words keeps them and
can decide. Nothing is silently merged and nothing is silently lost.

Paths derive from cli.LOCAL_STATE at call time, so the suite's redirect
and a preview root keep their own notes and the owner's real store is
never touched by a test.
"""
import json
import pathlib
import uuid

import wordicon_cli as cli

BODY_LIMIT = 20000          # a note is prose beside the work, not a corpus
LIST_LIMIT = 500


class NoteRefused(Exception):
    """A write the record would not accept, with the reason and, for a
    conflict, what the record actually holds."""

    def __init__(self, message: str, *, code: str = "refused", detail: dict | None = None):
        super().__init__(message)
        self.code = code
        self.detail = detail or {}


def _log_path() -> pathlib.Path:
    # read through the module so the suite's redirect is honoured
    return pathlib.Path(cli.LOCAL_STATE) / "notes.jsonl"


def _append(row: dict) -> dict:
    p = _log_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    with p.open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _rows() -> "list[dict]":
    p = _log_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            r = json.loads(line)
        except json.JSONDecodeError:
            continue           # a torn last line never hides the notes before it
        if isinstance(r, dict):
            out.append(r)
    return out


def _clean_body(body: str) -> str:
    body = (body if isinstance(body, str) else "")
    if len(body) > BODY_LIMIT:
        raise NoteRefused(
            f"the note is {len(body)} characters and the limit is {BODY_LIMIT} — "
            "nothing was saved and your words are still in the box",
            code="too_long",
            detail={"field": "body", "actual": len(body), "limit": BODY_LIMIT})
    return body


def fold() -> "dict[str, dict]":
    """Every note ever written in this store, with its later events applied.
    Nothing is dropped from this view; `state` says where each one stands."""
    notes: "dict[str, dict]" = {}
    for r in _rows():
        kind, nid = r.get("kind"), r.get("note_id")
        if not nid:
            continue
        if kind == "written":
            n = dict(r)
            n["state"] = "active"
            n["revision"] = 1
            n["updated_at"] = r.get("at", "")
            n["history"] = [{"kind": "written", "at": r.get("at", ""), "request_id": r.get("request_id", "")}]
            notes[nid] = n
        elif nid in notes:
            n = notes[nid]
            n["history"].append({"kind": kind, "at": r.get("at", ""), "request_id": r.get("request_id", "")})
            if kind == "edited":
                n["body"] = r.get("body", "")
                n["revision"] = int(n.get("revision", 1)) + 1
                n["updated_at"] = r.get("at", "")
            elif kind == "removed":
                n["state"] = "removed"
                n["removed_at"] = r.get("at", "")
                n["updated_at"] = r.get("at", "")
    return notes


def _seen_request(request_id: str) -> "dict | None":
    """The note a given request id already wrote, if it wrote one. The id is
    the client's; an empty one is not a claim of identity and never matches."""
    if not (request_id or "").strip():
        return None
    for r in _rows():
        if r.get("request_id") == request_id and r.get("kind") in ("written", "edited"):
            return fold().get(r.get("note_id"))
    return None


def _view(n: dict) -> dict:
    """What a caller sees. The body, where it belongs, how many writes the
    record holds, and — always — that these are the owner's own words."""
    return {"note_id": n.get("note_id", ""), "doc_id": n.get("doc_id", ""),
            "body": n.get("body", ""), "at": n.get("at", ""),
            "updated_at": n.get("updated_at", n.get("at", "")),
            "revision": int(n.get("revision", 1)), "state": n.get("state", "active"),
            "epoch": n.get("epoch", ""), "tab_id": n.get("tab_id", ""),
            "owner_authored": True,
            "means": "the owner's own words, typed beside the work",
            "is_not": ["a model result", "a carry", "accepted", "supported", "verified"]}


def write_note(*, doc_id: str, body: str, request_id: str = "", tab_id: str = "") -> dict:
    """A new note on a document. The same request id twice is one note."""
    doc_id = (doc_id or "").strip()
    if not doc_id:
        raise NoteRefused("a note needs the document it belongs beside", code="no_document")
    body = _clean_body(body)
    if not body.strip():
        raise NoteRefused("an empty note says nothing and is not written", code="empty")
    seen = _seen_request(request_id)
    if seen is not None:
        return _view(seen)                      # the retry of a write that landed
    row = {
        "kind": "written",
        "note_id": "note_" + uuid.uuid4().hex[:12],
        "doc_id": doc_id,
        "body": body,
        "at": cli._now(),
        "epoch": cli.current_epoch(),
        "request_id": (request_id or "")[:120],
        "tab_id": (tab_id or "")[:60],
        # what a note IS, said in the record and not only on the page
        "owner_authored": True,
        "means": "the owner's own words, typed beside the work",
        "is_not": ["a model result", "a carry", "accepted", "supported", "verified"],
    }
    _append(row)
    return _view(fold()[row["note_id"]])


def edit_note(*, note_id: str, body: str, base_revision: int = 0,
              request_id: str = "") -> dict:
    """Change a note's words. `base_revision` is the revision the writer had
    in front of them; if the record has moved past it the edit is refused
    with both bodies, so the words in hand are never lost to a race."""
    notes = fold()
    n = notes.get((note_id or "").strip())
    if n is None:
        raise NoteRefused("no note by that id in this store", code="no_such_note")
    if n.get("state") == "removed":
        raise NoteRefused("that note was removed; its words stay in the record and a new note is a new note",
                          code="removed")
    body = _clean_body(body)
    seen = _seen_request(request_id)
    if seen is not None and seen.get("note_id") == n["note_id"]:
        return _view(seen)                      # the retry of an edit that landed
    have = int(n.get("revision", 1))
    if base_revision and int(base_revision) != have:
        raise NoteRefused(
            "this note changed somewhere else while you were writing — nothing was overwritten",
            code="conflict",
            detail={"note_id": n["note_id"], "revision_here": have,
                    "your_base_revision": int(base_revision),
                    "body_here": n.get("body", "")})
    row = {"kind": "edited", "note_id": n["note_id"], "body": body,
           "at": cli._now(), "request_id": (request_id or "")[:120]}
    _append(row)
    return _view(fold()[n["note_id"]])


def remove_note(note_id: str) -> dict:
    """Take a note out of the list. Appended, never erased: the words stay
    in the record and the removal has its own time."""
    n = fold().get((note_id or "").strip())
    if n is None:
        raise NoteRefused("no note by that id in this store", code="no_such_note")
    _append({"kind": "removed", "note_id": n["note_id"], "at": cli._now()})
    return _view(fold()[n["note_id"]])


def for_document(doc_id: str, limit: int = LIST_LIMIT) -> "list[dict]":
    """This document's notes, newest first — the order they are read in,
    with the newest under the box that wrote it."""
    doc_id = (doc_id or "").strip()
    out = [_view(n) for n in fold().values()
           if n.get("state") == "active" and n.get("doc_id") == doc_id]
    out.sort(key=lambda n: (n.get("updated_at") or n.get("at") or ""), reverse=True)
    return out[:max(1, int(limit or LIST_LIMIT))]


def summary(doc_id: str = "") -> dict:
    f = fold()
    scoped = [n for n in f.values() if not doc_id or n.get("doc_id") == doc_id]
    return {"population": ("every note ever written in this store, by its latest state"
                           if not doc_id else
                           "every note ever written beside this document, by its latest state"),
            "doc_id": doc_id,
            "active": sum(1 for n in scoped if n.get("state") == "active"),
            "removed": sum(1 for n in scoped if n.get("state") == "removed"),
            "total": len(scoped)}
