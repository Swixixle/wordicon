"""Carry Back — the bridge from a workup to the writing room. Block 123.

Nikodemus excavates and does not return. A dense first draft goes into Go
Deep; readings, objections, comparisons and doors come out, nine hundred
lines of them; and the owner carries what he wants back to the paragraph
by hand, or loses it under the dig. This is the bridge, and it is only a
bridge.

CARRY MEANS: "this may be useful while revising". It does not mean accepted,
supported, verified, true, written by the owner, or approved. Carrying an
item creates no judgment, changes no standing, repairs no warrant, admits
no source and alters no concept. A contradicted candidate carried for
inspiration is still contradicted. An invented example is still invented.
A recall-only parallel is still recall-only. Every carry keeps those labels
on it, in the store and on the screen and in copied text.

WHAT IS STORED: an exact excerpt, its standing as the result recorded it,
enough identity to find it again after the interface changes (trace,
component, candidate, field — never a card position), and the identity of
the text the analysis examined. NOT the whole result, and NOT the owner's
draft: the draft lives in his browser and stays there. The one piece of
owner prose a carry may hold is a note he types into it on purpose, kept
verbatim, which is the same class of act as a judgment note.

APPEND-ONLY, like every other log here. Dismissing or using a carry records
that it was dismissed or used; nothing is rewritten. Retargeting a carry to
a draft that differs from the one analysed is an explicit owner choice and
is recorded as one.

No model. No network. File I/O only.
"""
from __future__ import annotations

import json
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wordicon_cli as cli  # noqa: E402

CARRIES_LOG = cli.LOCAL_STATE / "carries.jsonl"

CARRY_KINDS = ("carried", "dismissed", "used", "retargeted", "noted")

# The result material a carry may point at. A kind names WHERE the excerpt
# came from, so a later interface can find it by identity rather than by
# card order. Adding a kind is adding a stable identity, and is a decision.
CARRY_SOURCE_KINDS = (
    "component",        # a component/reading of the passage
    "candidate",        # a candidate concept (definition, tension, mechanism, axiom, boundary)
    "friction",         # the critic's objection on a candidate
    "anchor_fit",       # the anchor-fit deciding difference on a candidate
    "thread",           # a lateral (sprout) comparison
    "door",             # an investigative road a rabbithole opened
    "refraction",       # a linguistic proposal
    "archetype",        # a figure or facet
    "verify",           # a verification question
)

# Standing labels a carry preserves. Each is a fact the result recorded, and
# a carry copies the fact rather than deciding anything about it.
STANDING_KEYS = ("route", "friction_verdict", "anchor_fit", "invented",
                 "unverified", "provider_returned", "contradicted", "recall_only")


def _log_path() -> Path:
    # read through the module so the suite's redirect is honoured
    return Path(cli.LOCAL_STATE) / "carries.jsonl"


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
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def source_key_for(text: str) -> str:
    """The identity of the text an analysis examined — the same key the
    Map uses for a source node, so a carry and an edge agree about which
    passage they mean. A hash, never the text."""
    return cli.node_source(text or "")["key"]


def record_carry(*, trace_id: str, source_key: str, source_kind: str,
                 source_ref: dict, excerpt: str, standing: dict | None = None,
                 analyzed_head: str = "", analyzed_words: int = 0,
                 target_source_key: str = "", note: str = "") -> dict:
    """One carry. `source_ref` is the stable identity inside the result
    (component label, candidate concept_id/title, thread index+title, door
    text, field name) — whatever the result itself uses, never a DOM
    position. `excerpt` is the exact text at that moment."""
    if source_kind not in CARRY_SOURCE_KINDS:
        raise ValueError(f"unknown carry source kind {source_kind!r}")
    if not (trace_id or "").strip():
        raise ValueError("a carry needs the trace of the run it came from")
    if not (source_key or "").strip():
        raise ValueError("a carry needs the identity of the text the run examined")
    excerpt = (excerpt or "").strip()
    if not excerpt:
        raise ValueError("a carry with no excerpt carries nothing")
    st = {k: standing.get(k) for k in STANDING_KEYS if standing and standing.get(k) is not None}
    row = {
        "kind": "carried",
        "carry_id": "carry_" + uuid.uuid4().hex[:12],
        "at": cli._now(),
        "epoch": cli.current_epoch(),
        "source": {"trace_id": trace_id, "kind": source_kind,
                   "ref": dict(source_ref or {})},
        "analyzed": {"source_key": source_key, "head": (analyzed_head or "")[:80],
                     "words": int(analyzed_words or 0)},
        "target": {"source_key": target_source_key or source_key,
                   "draft": "browser_session"},
        "excerpt": excerpt[:4000],
        "standing": st,
        "note": (note or "")[:2000],
        # what a carry is NOT, said in the record and not only on the page
        "means": "may be useful while revising",
        "is_not": ["accepted", "supported", "verified", "true", "owner_authored", "approved"],
    }
    return _append(row)


def dismiss_carry(carry_id: str, why: str = "") -> dict:
    return _append({"kind": "dismissed", "carry_id": carry_id, "at": cli._now(),
                    "why": (why or "")[:400]})


def mark_used(carry_id: str) -> dict:
    return _append({"kind": "used", "carry_id": carry_id, "at": cli._now()})


def note_carry(carry_id: str, note: str) -> dict:
    """The owner's note, verbatim. Appended, so an earlier note is history."""
    return _append({"kind": "noted", "carry_id": carry_id, "at": cli._now(),
                    "note": (note or "")[:2000]})


def retarget_carry(carry_id: str, new_source_key: str, owner_choice: str) -> dict:
    """The owner chose to carry notes made about one draft to a different
    one. Recorded as HIS choice, with what he chose; never done silently."""
    if owner_choice not in ("carry_to_current_anyway",):
        raise ValueError(f"unknown retarget choice {owner_choice!r}")
    return _append({"kind": "retargeted", "carry_id": carry_id, "at": cli._now(),
                    "new_target_source_key": new_source_key, "owner_choice": owner_choice})


def fold() -> "dict[str, dict]":
    """Every carry ever made, with its later events applied. Nothing is
    deleted from this view; `state` says where it stands."""
    carries: "dict[str, dict]" = {}
    for r in _rows():
        k = r.get("kind")
        cid = r.get("carry_id")
        if k == "carried":
            c = dict(r); c["state"] = "active"; c["history"] = []
            carries[cid] = c
        elif cid in carries:
            c = carries[cid]
            c["history"].append({"kind": k, "at": r.get("at")})
            if k == "dismissed":
                c["state"] = "dismissed"; c["dismissed_why"] = r.get("why", "")
            elif k == "used":
                c["state"] = "used"
            elif k == "noted":
                c["note"] = r.get("note", "")
            elif k == "retargeted":
                c["target"] = dict(c.get("target") or {})
                c["target"]["source_key"] = r.get("new_target_source_key", "")
                c["target"]["retargeted_by_owner"] = r.get("owner_choice", "")
    return carries


def active(target_source_key: str = "") -> "list[dict]":
    """Carries still in the tray. With a target key, only those bound to
    that draft — plus, separately flagged, those bound to a DIFFERENT draft
    so the page can say so rather than mixing them in."""
    out = []
    for c in fold().values():
        if c.get("state") != "active":
            continue
        tk = (c.get("target") or {}).get("source_key", "")
        c = dict(c)
        c["matches_target"] = (not target_source_key) or (tk == target_source_key)
        out.append(c)
    out.sort(key=lambda c: c.get("at", ""))
    return out


def summary() -> dict:
    f = fold()
    return {"population": "every carry ever recorded in this store, by its latest state",
            "active": sum(1 for c in f.values() if c["state"] == "active"),
            "used": sum(1 for c in f.values() if c["state"] == "used"),
            "dismissed": sum(1 for c in f.values() if c["state"] == "dismissed"),
            "total": len(f)}
