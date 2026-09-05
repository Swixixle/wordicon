"""The Inquiry — a question, kept, branched and returnable (phase 1).

NAMING, first, because the obvious name was taken. Block 107 already
shipped an "Investigation Room": `inv_` ids at /investigation, fixed
seats, holding depositions that Open Case and EthicalAlt signed. That
room seats what OTHER instruments deposited. This one holds a question
the owner is working. Two different objects; overloading one name would
blur two constitutional meanings and break the ledger that pins the
first. So this is an Inquiry, and the federation room keeps its name.

What phase 1 is, exactly. An Inquiry is a durable place for one root
question. It can be created, listed, reopened, and navigated; the root
question is kept verbatim and is never rewritten; every later act is a
NODE hanging off another node, so a clarified question is a descendant
rather than a correction. Nothing here proposes readings, searches
anything, calls a model, or produces a finding — those are the phases
after this one. This module exists so that when they arrive they have
somewhere to be kept.

Laws enforced here in code:
- The original is preserved. The root question's text is written once,
  in the creation row, and no operation in this module can change it. A
  narrowed or corrected question is a new node citing its parent.
- Identity is minted, never derived from a title. Two inquiries with the
  same words are two inquiries; the title is a label and can change
  without the object changing.
- Append-only, with the ruled clock discipline: rows carry recorded_at,
  and a row whose clock precedes the log's last row is labeled rather
  than silently taken.
- Nothing is a judgment. A node is a place where thinking happened; only
  an explicit promotion elsewhere in the record makes a ruling, and this
  module writes none.
- The record is not the world. Nothing here establishes an external
  fact; a node carries a route and a standing, and phase 1 only ever
  writes the owner's own words with route "owner".
- No model anywhere in this module.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib

import wordicon_cli as cli

# The node vocabulary, declared once and in full, so the phases that
# follow slot into a shape that is already pinned rather than widening it
# later. Phase 1 writes only "root".
NODE_TYPES = (
    "root",         # the question as it arrived, verbatim
    "reading",      # one defensible way of reading the root (phase 2)
    "meta",         # a question ABOUT the question (phase 2)
    "answer",       # what a route returned (phases 3-4)
    "attack",       # a challenge aimed at a specific node (phase 5)
    "comparison",   # an owner-selected comparison of branches (phase 6)
    "synthesis",    # an owner-summoned snapshot (phase 6)
)

# How an element was produced. Written on the node, never inferred from
# how confident the prose sounds.
ROUTES = ("owner", "memory", "source", "compute", "research", "develop")

# What kind of warrant it currently has. Deliberately separate from the
# route: how it was produced and what it is worth are two questions, and
# collapsing them is how a model proposal becomes a fact.
STANDINGS = (
    "owner_stated",
    "directly_anchored",
    "mechanically_derived",
    "source_supported_interpretation",
    "model_proposal",
    "relied_upon_not_checked",
    "disputed",
    "unresolved",
    "source_unavailable",
)

# WHAT A THING IS — and it takes four axes, not one label.
#
# The first cut of this was a single flat list with `allegation`, `charge`,
# `settlement_no_admission`, `adjudicated_finding` and `conviction` sitting
# beside `testimony` and `measured_datum`. That mixed three different
# questions: what the material IS, who ISSUED it, and where it stands
# PROCEDURALLY. A settlement is not a kind of evidence — it is a state a
# document can be in, and that document contains allegations, company
# assertions and stipulated facts at the same time. Flattened into one label,
# procedural movement silently becomes proof: a charge reads as a finding, a
# settlement reads as an admission, and the exculpatory outcomes — dismissal,
# acquittal, reversal — have nowhere to live at all.
#
# So: four axes, and a classification is attached to ONE claim or answer
# element, never to a whole document.
#
# The vocabulary is VERSIONED. "Declared in full" means complete for this
# schema version, not sealed: a later phase may extend it through a recorded
# migration, and every classification carries the version it was made under.
VOCAB_VERSION = "inquiry.vocab.v1"

# What the material is.
EVIDENCE_NATURE = (
    "assertion",         # someone states it
    "testimony",         # a first-hand account
    "allegation",        # an accusation, unadjudicated
    "measured_datum",    # a number from a named dataset or filing
    "documented_event",  # a thing that demonstrably happened, with a record of it
    "analysis",          # a reading of other material, human or model
    "owner_judgment",    # the owner ruled it
)

# Who is speaking. A regulator asserting a thing and a company asserting the
# same thing are the same NATURE and very different weight, and that
# difference belongs on its own axis rather than inside the word.
ISSUER_ROLES = ("company", "regulator", "court", "journalist", "researcher",
                "whistleblower", "owner", "model", "other")

# Where it stands. Exculpatory outcomes are first-class here, which the flat
# list could not express at all.
PROCEDURAL_POSTURE = (
    "none",                   # not a legal matter
    "investigation",          # being looked into
    "complaint_or_charge",    # formally alleged
    "settlement",             # resolved by agreement
    "adjudication",           # decided by a tribunal
    "conviction",             # criminal, decided
    "dismissal_or_acquittal", # decided the other way
    "appeal",                 # under review
    "reversal",               # the decision was undone
)

# What, if anything, was admitted — because "settled" says nothing about this
# on its own, and the difference is the whole argument.
ADMISSION_STATUS = ("not_applicable", "explicit", "limited", "none", "not_stated")

# Whether it is over. An adjudicated finding under appeal is not a settled
# fact, and a reversal is not a footnote on the finding it undid.
FINALITY = ("pending", "interim", "final", "appealed", "overturned")


def classify(nature: str, issuer: str = "other", posture: str = "none",
             admission: str = "not_applicable", finality: str = "pending",
             note: str = "") -> dict:
    """One classification, for ONE claim or answer element.

    Never for a whole document: a single settlement carries allegations, the
    company's own assertions, stipulated facts and procedural terms, and one
    label over all of it is how the procedural movement becomes the proof.
    Unknown terms raise rather than being coerced to a default, because a
    silently defaulted posture is exactly the failure this axis exists for."""
    for _v, _allowed, _name in ((nature, EVIDENCE_NATURE, "nature"),
                                (issuer, ISSUER_ROLES, "issuer"),
                                (posture, PROCEDURAL_POSTURE, "posture"),
                                (admission, ADMISSION_STATUS, "admission"),
                                (finality, FINALITY, "finality")):
        if _v not in _allowed:
            raise ValueError(f"unknown {_name} {_v!r}")
    return {"vocab_version": VOCAB_VERSION, "nature": nature, "issuer": issuer,
            "posture": posture, "admission": admission, "finality": finality,
            "note": str(note or "")[:400]}


# What became of a branch. Only "promoted" is ever allowed to lead to a
# judgment event, and phase 1 writes no judgments at all.
DISPOSITIONS = ("open", "parked", "abandoned", "kept_supported",
                "kept_generative", "kept_unresolved", "promoted")


def inq_dir() -> pathlib.Path:
    """Resolved at call time off cli.LOCAL_STATE, never at import — that is
    what lets the suite and the --state harnesses redirect the store."""
    return cli.LOCAL_STATE / "inquiry"


def log_path() -> pathlib.Path:
    return inq_dir() / "inquiry.jsonl"


def _rows(p: pathlib.Path) -> "list[dict]":
    if not p.exists():
        return []
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _append(p: pathlib.Path, row: dict) -> dict:
    """Append-only, with the ruled clock discipline (item 58): every row
    gets recorded_at from this machine's clock; a row whose clock precedes
    the log's last row is labeled clock_regression, never silently taken."""
    inq_dir().mkdir(parents=True, exist_ok=True)
    row = dict(row)
    row.setdefault("recorded_at", cli._now())
    last = _rows(p)[-1:] if p.exists() else []
    if last and str(last[0].get("recorded_at", "")) > str(row["recorded_at"]):
        row["clock_regression"] = {"previous_recorded_at": last[0].get("recorded_at")}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _hid(prefix: str, *parts) -> str:
    """Minted, not derived. The instant and a salt are in the hash, so two
    inquiries opened on the same words in the same second are two
    inquiries — identity is the act of opening one, never the spelling."""
    return prefix + hashlib.sha256(
        "|".join(str(x) for x in parts).encode("utf-8")).hexdigest()[:12]


# ---- creating and reading ---------------------------------------------

def create_inquiry(question: str, title: str = "", provenance: str = "typed",
                   shape: str = "", opened_from: str = "") -> dict:
    """Open an inquiry on a question, exactly as it was asked.

    `question` is stored verbatim and is the one field nothing in this
    module can rewrite. `title` is a label for the shelf and may be
    anything; it is not identity, and an empty one is filled from the
    question's first words purely for display."""
    q = str(question or "").strip()
    if not q:
        raise ValueError("an inquiry needs a question")
    q = q[:8000]
    prov = provenance if provenance in cli.INPUT_PROVENANCE else "unstated"
    iid = _hid("inq_", q, cli._now(), os.urandom(6).hex())
    label = str(title or "").strip()[:160] or (q[:70] + ("…" if len(q) > 70 else ""))
    row = _append(log_path(), {
        "kind": "inquiry",
        "object_type": "inquiry",
        "inquiry_id": iid,
        "title": label,
        "root_question": q,
        "provenance": prov,
        "shape": shape or cli.input_shape(q).get("shape", ""),
        "opened_from": str(opened_from or "")[:64],
        "at": cli._now(),
        "epoch": cli.current_epoch(),
    })
    # The root node exists from the first instant, so there is never a
    # moment when the question is in the record but has nowhere to hang
    # its descendants.
    node = add_node(iid, "", "root", q, route="owner", standing="owner_stated")
    set_active(iid, node["node_id"])
    return {**row, "root_node_id": node["node_id"]}


def add_node(inquiry_id: str, parent_id: str, node_type: str, text: str,
             route: str = "owner", standing: str = "owner_stated",
             extra: "dict | None" = None) -> dict:
    """One node, hanging off another. A node is a place where thinking
    happened — it is not a finding, and it is never a judgment."""
    if node_type not in NODE_TYPES:
        raise ValueError(f"unknown node type {node_type!r}")
    if route not in ROUTES:
        raise ValueError(f"unknown route {route!r}")
    if standing not in STANDINGS:
        raise ValueError(f"unknown standing {standing!r}")
    if not get_raw(inquiry_id):
        raise ValueError("no inquiry with that id")
    if parent_id and parent_id not in {n["node_id"] for n in nodes_of(inquiry_id)}:
        raise ValueError("the parent is not a node of this inquiry")
    nid = _hid("iqn_", inquiry_id, parent_id, node_type, cli._now(), os.urandom(6).hex())
    return _append(log_path(), {
        "kind": "node",
        "object_type": "inquiry_node",
        "inquiry_id": inquiry_id,
        "node_id": nid,
        "parent_id": parent_id or "",
        "node_type": node_type,
        "text": str(text or "")[:8000],
        "route": route,
        "standing": standing,
        "extra": dict(extra or {}),
        "at": cli._now(),
        "epoch": cli.current_epoch(),
    })


def set_active(inquiry_id: str, node_id: str) -> dict:
    """Where the owner is standing. Appended, so where he stood last month
    is still in the record — navigation is history, not a mutable field."""
    if not get_raw(inquiry_id):
        raise ValueError("no inquiry with that id")
    if node_id and node_id not in {n["node_id"] for n in nodes_of(inquiry_id)}:
        raise ValueError("that node is not part of this inquiry")
    return _append(log_path(), {
        "kind": "active",
        "inquiry_id": inquiry_id,
        "node_id": node_id,
        "at": cli._now(),
    })


def set_disposition(inquiry_id: str, node_id: str, disposition: str,
                    reason: str = "", revealed: str = "") -> dict:
    """What became of a branch, in the owner's words.

    Abandoning keeps the reason AND what the failure revealed, because the
    throw that did not stick is the half of the record most worth having.
    Nothing here writes a judgment: "promoted" records that the owner
    intends one, and the ruling itself is made in the record's own
    judgment machinery, not here."""
    if disposition not in DISPOSITIONS:
        raise ValueError(f"unknown disposition {disposition!r}")
    if node_id not in {n["node_id"] for n in nodes_of(inquiry_id)}:
        raise ValueError("that node is not part of this inquiry")
    return _append(log_path(), {
        "kind": "disposition",
        "inquiry_id": inquiry_id,
        "node_id": node_id,
        "disposition": disposition,
        "reason": str(reason or "")[:2000],
        "revealed": str(revealed or "")[:2000],
        "at": cli._now(),
        "epoch": cli.current_epoch(),
    })


def rename(inquiry_id: str, title: str) -> dict:
    """A label, changed. The question is untouched — that is the whole
    point of keeping identity off the title."""
    if not get_raw(inquiry_id):
        raise ValueError("no inquiry with that id")
    return _append(log_path(), {
        "kind": "rename",
        "inquiry_id": inquiry_id,
        "title": str(title or "").strip()[:160],
        "at": cli._now(),
    })


# ---- projections ------------------------------------------------------

def get_raw(inquiry_id: str) -> dict:
    for r in _rows(log_path()):
        if r.get("kind") == "inquiry" and r.get("inquiry_id") == inquiry_id:
            return r
    return {}


def nodes_of(inquiry_id: str) -> "list[dict]":
    return [r for r in _rows(log_path())
            if r.get("kind") == "node" and r.get("inquiry_id") == inquiry_id]


def load_inquiries() -> "list[dict]":
    """Every inquiry, newest first, with just enough to choose one."""
    rows = _rows(log_path())
    made = [r for r in rows if r.get("kind") == "inquiry"]
    titles, counts, last, actives = {}, {}, {}, {}
    for r in rows:
        iid = r.get("inquiry_id", "")
        if not iid:
            continue
        k = r.get("kind")
        if k == "rename":
            titles[iid] = r.get("title", "")
        elif k == "node":
            counts[iid] = counts.get(iid, 0) + 1
        elif k == "active":
            actives[iid] = r.get("node_id", "")
        if r.get("at"):
            last[iid] = max(last.get(iid, ""), str(r.get("at")))
    out = []
    for r in made:
        iid = r["inquiry_id"]
        out.append({"inquiry_id": iid,
                    "title": titles.get(iid, r.get("title", "")),
                    "root_question": r.get("root_question", ""),
                    "opened_at": r.get("at", ""),
                    "last_touched": last.get(iid, r.get("at", "")),
                    "nodes": counts.get(iid, 0),
                    "active_node_id": actives.get(iid, ""),
                    "provenance": r.get("provenance", ""),
                    "shape": r.get("shape", "")})
    out.sort(key=lambda x: x["last_touched"], reverse=True)
    return out


def get_inquiry(inquiry_id: str) -> dict:
    """One inquiry, whole: the question as asked, every node with its
    parent, the dispositions the owner recorded, and where he was
    standing when he left. This is what "reopen" reads."""
    base = get_raw(inquiry_id)
    if not base:
        return {}
    rows = [r for r in _rows(log_path()) if r.get("inquiry_id") == inquiry_id]
    title = base.get("title", "")
    active = ""
    disp = {}
    nodes = []
    for r in rows:
        k = r.get("kind")
        if k == "rename":
            title = r.get("title", "")
        elif k == "active":
            active = r.get("node_id", "")
        elif k == "disposition":
            disp[r.get("node_id", "")] = {"disposition": r.get("disposition", ""),
                                          "reason": r.get("reason", ""),
                                          "revealed": r.get("revealed", ""),
                                          "at": r.get("at", "")}
        elif k == "node":
            nodes.append({"node_id": r.get("node_id", ""),
                          "parent_id": r.get("parent_id", ""),
                          "node_type": r.get("node_type", ""),
                          "text": r.get("text", ""),
                          "route": r.get("route", ""),
                          "standing": r.get("standing", ""),
                          "extra": r.get("extra", {}),
                          "at": r.get("at", "")})
    root = next((n for n in nodes if n["node_type"] == "root"), None)
    for n in nodes:
        n["disposition"] = disp.get(n["node_id"], {"disposition": "open"})
    if active and active not in {n["node_id"] for n in nodes}:
        active = ""
    return {"inquiry_id": inquiry_id,
            "title": title,
            # Said twice on purpose: the root question is the one field
            # the whole object exists to keep, and a reader should not
            # have to walk the node list to find out what was asked.
            "root_question": base.get("root_question", ""),
            "root_node_id": root["node_id"] if root else "",
            "opened_at": base.get("at", ""),
            "provenance": base.get("provenance", ""),
            "shape": base.get("shape", ""),
            "opened_from": base.get("opened_from", ""),
            "active_node_id": active or (root["node_id"] if root else ""),
            "nodes": nodes,
            # What phase 1 deliberately cannot do yet, said on the object
            # rather than left for the page to imply.
            "unbuilt": ["readings", "meta-questions", "ask my record",
                        "research outside", "trial", "comparison", "synthesis"]}


def status() -> dict:
    rows = _rows(log_path())
    return {"inquiries": len([r for r in rows if r.get("kind") == "inquiry"]),
            "nodes": len([r for r in rows if r.get("kind") == "node"]),
            "log": str(log_path()),
            "exists": log_path().exists()}
