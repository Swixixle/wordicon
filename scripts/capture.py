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
import pathlib
from datetime import datetime, timezone

import ledger
import wordicon_cli as cli

SCOPES = ("library", "work")      # the search boxes that reach the server today
MAX_QUERY = 500


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
                "why": f"a query is kept whole or not at all; this one is {len(q)} characters (cap {MAX_QUERY})"}
    at = _now()
    row = {"at": at, "scope": scope, "q": q,
           "hits": int(hits) if isinstance(hits, int) and hits >= 0 else None}
    try:
        # This hook rides inside the search route itself: a store that cannot
        # write must never break the search the owner just performed. The
        # failure is reported in the return, not raised into the room.
        _dir().mkdir(parents=True, exist_ok=True)
        with open(_dir() / f"queries-{at[:7]}.jsonl", "a", encoding="utf-8") as f:
            f.write(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n")
    except OSError as e:
        return {"kept": False, "why": f"the capture store could not be written ({e.__class__.__name__}); the search itself is unaffected"}
    return {"kept": True}


def read_queries(day: str = "", limit: int = 2000) -> dict:
    """The owner's searches back, oldest first, capped and saying so."""
    out = []
    paths = sorted(_dir().glob("queries-*.jsonl")) if day else sorted(_dir().glob("queries-*.jsonl"))[-1:]
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            try:
                row = json.loads(line)
            except json.JSONDecodeError:
                continue
            if day and not str(row.get("at", "")).startswith(day):
                continue
            out.append(row)
    truncated = len(out) > limit
    return {"queries": out[-limit:], "truncated": truncated, "enabled": enabled(),
            "population": f"the capture file(s) read whole from the store; {len(out)} search(es) matched"
                          + (f", the newest {limit} returned" if truncated else "")}
