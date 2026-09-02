#!/usr/bin/env python3
"""The medical wing — Room One (docs/adr-medical-wing.md).

Custody of medical sources by INSTITUTIONAL ROLE, with declared —
never inferred — version and supersession relations, one Clinical
Topic Room, and Ask This Room v1: questions about admitted documents,
never orders about patients.

The laws this module enforces in code:
- Roles, status, dates, family membership, and supersession become
  permanent only through the owner's visible ruling. Extraction may
  PROPOSE; proposals live in their own file and grant nothing.
- Metadata may be unknown ("unknown") or inapplicable
  ("not_applicable"); it may never be silently blank and never
  invented to complete a form.
- Code computes coverage, absence, status, and side-by-side anchored
  passages. Code never concludes that two sources DISAGREE — that is
  a model proposal or an owner ruling, with exact passages attached.
- Absence is "No admitted source of this role is present." — absent
  from the admitted room, never from medicine.
- THE PHI NON-RETENTION LAW (constitutional amendment, ADR wording):
  an input that appears patient-identifying is refused before model
  transmission and before any persistent write; only a content-free
  refusal event {time, lane, rule} is kept. Ask This Room v1 goes
  further: it persists NOTHING about any question, accepted or
  refused, beyond that event — compliance by construction. Detection
  is a heuristic backstop and says so; the lane shape (questions
  about documents, not patients) is the primary control.
"""
from __future__ import annotations

import hashlib
import json
import pathlib
import re
import sys
import uuid

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import wordicon_cli as cli  # noqa: E402
import library  # noqa: E402

UNKNOWN = "unknown"
NOT_APPLICABLE = "not_applicable"

MEDICAL_ROLES = ("hospital_policy", "department_procedure",
                 "professional_guideline", "fda_label",
                 "device_documentation", "manufacturer_claim",
                 "independent_study", "credentialing_body",
                 "owner_record")

SOURCE_STATUSES = ("current", "retired", "superseded", UNKNOWN)

RELATION_KINDS = ("supersedes", "retired_by", "same_family")

# Room One's ruled composition — deliberately mixed, separated by
# design. A seat names which roles can fill it and, where the ruling
# says so, which status.
ROOM_ONE_TITLE = "Adult Ventilator Liberation: Readiness, SBTs, and Extubation"
ROOM_ONE_SEATS = (
    {"seat": "the institution", "accepts_roles": ["hospital_policy",
                                                   "department_procedure"]},
    {"seat": "current professional guidance",
     "accepts_roles": ["professional_guideline"],
     "requires_status": "current"},
    {"seat": "retired or superseded guidance",
     "accepts_roles": ["professional_guideline"],
     "requires_status_in": ["retired", "superseded"]},
    {"seat": "label or device information",
     "accepts_roles": ["fda_label", "device_documentation"]},
    {"seat": "independent study", "accepts_roles": ["independent_study"]},
    {"seat": "manufacturer", "accepts_roles": ["manufacturer_claim"]},
)

ABSENT_ROLE_SENTENCE = "No admitted source of this role is present."
ABSENT_ANSWER_SENTENCE = "No admitted source answered this question."

# Date-like fields: every one must be an explicit value, UNKNOWN, or
# NOT_APPLICABLE. Silence is not a value; the form is never completed
# by invention.
DATE_FIELDS = ("published_at", "effective_from", "review_or_expiry")


def clinic_dir() -> pathlib.Path:
    return cli.LOCAL_STATE / "clinic"


def _path(name: str) -> pathlib.Path:
    return clinic_dir() / name


def _rows(name: str) -> "list[dict]":
    p = _path(name)
    if not p.exists():
        return []
    out = []
    for line in p.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def _append(name: str, row: dict) -> dict:
    clinic_dir().mkdir(parents=True, exist_ok=True)
    with _path(name).open("a", encoding="utf-8") as f:
        f.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _date_value(v) -> str:
    """A date field is an explicit value, 'unknown', or 'not_applicable'.
    Empty is refused: the record never carries invented certainty AND
    never carries silent blanks — the owner says which of the three it
    is."""
    v = (v or "").strip() if isinstance(v, str) else ""
    if v in (UNKNOWN, NOT_APPLICABLE):
        return v
    if not v:
        raise ValueError(
            "every date field must be a value, 'unknown', or "
            "'not_applicable' — a blank would either invent certainty "
            "or hide its absence, and this record does neither")
    if len(v) > 40:
        raise ValueError("that does not look like a date")
    return v


# ---------------------------------------------------------------------------
# sources — owner-declared custody records

def declare_source(document_id: str, representation_id: str, blob_id: str,
                    role: str, issuer: str, title: str,
                    published_at: str = "", effective_from: str = "",
                    review_or_expiry: str = "", status: str = UNKNOWN,
                    jurisdiction_or_facility: str = "",
                    population_scope: str = "",
                    acquired_from: str = "", supersedes_uid: str = "") -> dict:
    if role not in MEDICAL_ROLES:
        raise ValueError(f"role must be one of {MEDICAL_ROLES}")
    if status not in SOURCE_STATUSES:
        raise ValueError(f"status must be one of {SOURCE_STATUSES} — "
                         "'unknown' is allowed; invention is not")
    if not (document_id and representation_id and blob_id):
        raise ValueError("a source is declared over an admitted document: "
                         "document, representation, and blob ids are all "
                         "required")
    row = {
        "source_id": "src_" + uuid.uuid4().hex[:16],
        "document_id": document_id,
        "representation_id": representation_id,
        "blob_id": blob_id,
        "role": role,
        "issuer": (issuer or "").strip() or UNKNOWN,
        "title": (title or "").strip(),
        "published_at": _date_value(published_at),
        "effective_from": _date_value(effective_from),
        "review_or_expiry": _date_value(review_or_expiry),
        "status": status,
        "jurisdiction_or_facility":
            (jurisdiction_or_facility or "").strip() or UNKNOWN,
        "population_scope": (population_scope or "").strip() or UNKNOWN,
        "acquired_from": (acquired_from or "").strip() or UNKNOWN,
        "declared_by": "owner",
        "supersedes_declaration": supersedes_uid or "",
        "declared_at": cli._now(),
    }
    return _append("sources.jsonl", row)


def load_sources() -> "list[dict]":
    """Latest declaration per source_id; corrected declarations
    supersede by link, never by rewrite."""
    rows = _rows("sources.jsonl")
    superseded = {r.get("supersedes_declaration") for r in rows
                  if r.get("supersedes_declaration")}
    out, seen = [], set()
    for r in reversed(rows):
        sid = r.get("source_id")
        if not sid or sid in seen:
            continue
        seen.add(sid)
        out.append(r)
    return [r for r in reversed(out)
            if r.get("source_id") not in superseded]


def propose_metadata(rep: dict) -> "list[dict]":
    """Code may PROPOSE dates it can see in the text; it grants nothing.
    Proposals are logged with their origin and wait for the owner."""
    text = " ".join(sec.get("text", "") for sec in rep.get("sections", []))
    found = set()
    for m in re.finditer(
            r"\b(19|20)\d{2}\b|"
            r"\b(?:January|February|March|April|May|June|July|August|"
            r"September|October|November|December)\s+(?:19|20)\d{2}\b",
            text[:20000]):
        found.add(m.group(0))
    proposals = []
    for v in sorted(found)[:8]:
        proposals.append(_append("proposals.jsonl", {
            "proposal_id": "prop_" + uuid.uuid4().hex[:12],
            "kind": "date_candidate",
            "representation_id": rep.get("representation_id", ""),
            "value": v, "origin": "code_scan",
            "status": "awaiting_owner", "at": cli._now()}))
    return proposals


# ---------------------------------------------------------------------------
# relations and families — permanent only through the owner's ruling.
# Family identity obeys the concept-first identity law: a family id is
# minted, and membership is RULED — there is deliberately no code path
# from a title match to a family row.

def rule_relation(kind: str, from_source_id: str, to_source_id: str,
                   proposed_by: str = "") -> dict:
    if kind not in ("supersedes", "retired_by"):
        raise ValueError("relation kind must be supersedes or retired_by "
                         "(families have their own ruling)")
    srcs = {s["source_id"] for s in load_sources()}
    if from_source_id not in srcs or to_source_id not in srcs:
        raise ValueError("both ends of a relation must be declared sources "
                         "in this corpus — a relation to a source that is "
                         "not admitted is fiction")
    return _append("relations.jsonl", {
        "relation_id": "rel_" + uuid.uuid4().hex[:12],
        "kind": kind, "from_source_id": from_source_id,
        "to_source_id": to_source_id,
        "proposed_by": proposed_by or "owner",
        "ruled_by": "owner", "at": cli._now()})


def rule_family(member_source_ids: "list[str]",
                 family_id: str = "", label: str = "") -> dict:
    srcs = {s["source_id"] for s in load_sources()}
    missing = [m for m in member_source_ids if m not in srcs]
    if missing:
        raise ValueError(f"family members must be declared sources; "
                         f"missing: {missing}")
    if len(member_source_ids) < 2 and not family_id:
        raise ValueError("a family ruling names at least two members or "
                         "extends an existing family")
    return _append("relations.jsonl", {
        "relation_id": "rel_" + uuid.uuid4().hex[:12],
        "kind": "same_family",
        "family_id": family_id or ("fam_" + uuid.uuid4().hex[:12]),
        "member_source_ids": list(member_source_ids),
        "label": (label or "").strip(),
        "ruled_by": "owner", "at": cli._now()})


def load_relations() -> "list[dict]":
    return _rows("relations.jsonl")


# ---------------------------------------------------------------------------
# rooms

def create_room(title: str, seats=None) -> dict:
    room = {
        "room_id": "room_" + uuid.uuid4().hex[:12],
        "title": (title or "").strip(),
        "seats": list(seats if seats is not None else ROOM_ONE_SEATS),
        "member_source_ids": [],
        "created_at": cli._now(),
    }
    rooms = load_rooms()
    rooms[room["room_id"]] = room
    clinic_dir().mkdir(parents=True, exist_ok=True)
    _path("rooms.json").write_text(json.dumps(rooms, indent=1))
    return room


def load_rooms() -> dict:
    p = _path("rooms.json")
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def add_to_room(room_id: str, source_id: str) -> dict:
    rooms = load_rooms()
    room = rooms.get(room_id)
    if not room:
        raise ValueError("no such room")
    if source_id not in {s["source_id"] for s in load_sources()}:
        raise ValueError("only a declared source can join a room")
    if source_id not in room["member_source_ids"]:
        room["member_source_ids"].append(source_id)
    _path("rooms.json").write_text(json.dumps(rooms, indent=1))
    return room


def _seat_filled_by(seat: dict, member: dict) -> bool:
    if member.get("role") not in seat.get("accepts_roles", []):
        return False
    if "requires_status" in seat and \
            member.get("status") != seat["requires_status"]:
        return False
    if "requires_status_in" in seat and \
            member.get("status") not in seat["requires_status_in"]:
        return False
    return True


def room_state(room_id: str) -> dict:
    """Computed, and only what code may compute: membership, seat
    coverage, absence (in the ruled phrasing), and each member's
    declared status — never a semantic conclusion."""
    room = load_rooms().get(room_id)
    if not room:
        raise ValueError("no such room")
    by_id = {s["source_id"]: s for s in load_sources()}
    members = [by_id[m] for m in room["member_source_ids"] if m in by_id]
    seats = []
    for seat in room["seats"]:
        filled = [m["source_id"] for m in members if _seat_filled_by(seat, m)]
        seats.append({**seat, "filled_by": filled,
                      "absent": ABSENT_ROLE_SENTENCE if not filled else ""})
    return {"room_id": room_id, "title": room["title"],
            "members": members, "seats": seats,
            "relations": [r for r in load_relations()
                          if r.get("from_source_id") in by_id
                          or r.get("to_source_id") in by_id
                          or set(r.get("member_source_ids", []))
                          & set(by_id)]}


# ---------------------------------------------------------------------------
# the PHI boundary and the lane guard

PHI_RULES = (
    ("mrn_pattern", re.compile(r"\b(?:mrn|medical record(?: number)?)\b"
                                r"[\s:#]*\d", re.I)),
    ("ssn_pattern", re.compile(r"\b\d{3}-\d{2}-\d{4}\b")),
    ("dob_pattern", re.compile(r"\b(?:dob|date of birth)\b[\s:]*\S", re.I)),
    ("bed_identifier", re.compile(r"\b(?:bed|room)\s*#?\s*\d+[A-Za-z]?\b"
                                   r".{0,80}\b(?:patient|pt)\b|"
                                   r"\b(?:patient|pt)\b.{0,80}"
                                   r"\b(?:bed|room)\s*#?\s*\d+", re.I | re.S)),
    ("patient_narrative", re.compile(
        r"\b(?:my|the|this|a)\s+(?:patient|pt)\b.{0,120}?"
        r"\b(?:admitted|presents?|presented|is on|was placed|intubated|"
        r"year[- ]old|y/?o)\b", re.I | re.S)),
    ("age_case_pattern", re.compile(r"\b\d{1,3}\s*(?:year[- ]old|y/?o)\b"
                                     r".{0,120}\b(?:male|female|man|woman|"
                                     r"patient|pt)\b", re.I | re.S)),
)

ORDER_LANE_RULES = (
    ("treatment_order", re.compile(
        r"\b(?:what should i do|should i (?:extubate|intubate|wean|"
        r"increase|decrease|start|stop|give)|which (?:treatment|therapy|"
        r"mode|setting) should)\b", re.I)),
    ("patient_safety_verdict", re.compile(
        r"\bis (?:this|my|the) (?:patient|pt) (?:safe|ready|stable)\b",
        re.I)),
    ("override_request", re.compile(
        r"\bcan i override\b|\boverride (?:the|an?) (?:order|policy)\b",
        re.I)),
)


def phi_screen(text: str) -> "tuple[bool, str]":
    """Heuristic backstop, and it says so. (True, '') means nothing
    matched — NOT a guarantee; the lane shape is the primary control."""
    t = text or ""
    for rule, rx in PHI_RULES:
        if rx.search(t):
            return False, rule
    return True, ""


def order_lane_screen(question: str) -> "tuple[bool, str]":
    for rule, rx in ORDER_LANE_RULES:
        if rx.search(question or ""):
            return False, rule
    return True, ""


def record_refusal(lane: str, rule: str) -> dict:
    """Content-free by law: time, lane, rule. Nothing else exists to
    leak — not into logs, snapshots, Keeper packets, or the Vault."""
    return _append("phi_refusals.jsonl",
                   {"at": cli._now(), "lane": lane, "rule": rule})


ORDER_REFUSAL_SENTENCE = (
    "This room answers questions about its admitted documents. It does "
    "not advise on a patient, choose a treatment, or overrule an order "
    "or policy — that judgment belongs to the clinician and the "
    "institution, on purpose.")

PHI_REFUSAL_SENTENCE = (
    "That looks like it may contain patient-identifying information, so "
    "it was refused before any model saw it and before anything was "
    "stored. Nothing about the question was kept beyond the fact of "
    "this refusal. Ask about the documents — policies, guidelines, "
    "labels — not about a patient.")


# ---------------------------------------------------------------------------
# Ask This Room v1 — deterministic retrieval; no model call anywhere in
# this function. Questions are never persisted, accepted or not.

def ask_room(room_id: str, question: str) -> dict:
    q = (question or "").strip()
    if not q:
        raise ValueError("ask something")
    ok, rule = phi_screen(q)
    if not ok:
        record_refusal("clinic_question", rule)
        return {"refused": True, "why": PHI_REFUSAL_SENTENCE,
                "rule": rule}
    ok, rule = order_lane_screen(q)
    if not ok:
        record_refusal("clinic_order_lane", rule)
        return {"refused": True, "why": ORDER_REFUSAL_SENTENCE,
                "rule": rule}
    state = room_state(room_id)
    rep_to_src = {m["representation_id"]: m for m in state["members"]}
    hits = library.search_terms(q, limit=200)
    blocks = {}
    for h in hits:
        rep_id = h["anchor_id"].split(":", 1)[0]
        src = rep_to_src.get(rep_id)
        if not src:
            continue  # outside the admitted room — not this room's voice
        b = blocks.setdefault(src["source_id"], {
            "source_id": src["source_id"], "role": src["role"],
            "title": src["title"], "issuer": src["issuer"],
            "status": src["status"],
            "published_at": src["published_at"],
            "effective_from": src["effective_from"],
            "passages": []})
        if len(b["passages"]) < 6:
            b["passages"].append({"anchor_id": h["anchor_id"],
                                   "heading": h["heading"],
                                   "snippet": h["snippet"]})
    answered_roles = {b["role"] for b in blocks.values()}
    silent = []
    for m in state["members"]:
        if m["source_id"] not in blocks:
            silent.append({"source_id": m["source_id"], "role": m["role"],
                           "title": m["title"],
                           "note": ABSENT_ANSWER_SENTENCE})
    return {"refused": False, "question_persisted": False,
            "room_id": room_id, "title": state["title"],
            "blocks": sorted(blocks.values(), key=lambda b: b["role"]),
            "silent_members": silent,
            "empty_seats": [s for s in state["seats"] if s["absent"]],
            "note": ("Passages are retrieved mechanically and shown side "
                     "by side. Whether two sources DISAGREE is a judgment "
                     "— propose it to the model or rule it yourself; this "
                     "answer makes no such claim.")}


# ---------------------------------------------------------------------------
# disagreement — the ONLY model doorway in the wing, summoned on two
# owner-chosen anchored passages; the output is a PROPOSAL.

def propose_disagreement(room_id: str, anchor_a: str, anchor_b: str,
                          gateway) -> dict:
    state = room_state(room_id)
    reps = {m["representation_id"] for m in state["members"]}
    for a in (anchor_a, anchor_b):
        if a.split(":", 1)[0] not in reps:
            raise ValueError("both passages must belong to this room's "
                             "admitted sources")

    def _passage(anchor: str) -> dict:
        rep_id, path = anchor.split(":", 1)
        rep = library.load_representation(rep_id)
        if not rep:
            raise ValueError(f"no such representation: {rep_id}")
        for sec in rep["sections"]:
            for par in sec["paragraphs"]:
                for s in par["sentences"]:
                    if s["path"] == path:
                        return {"anchor_id": anchor, "text": s["text"],
                                "heading": sec["heading"]}
        raise ValueError(f"anchor {anchor} does not resolve")

    pa, pb = _passage(anchor_a), _passage(anchor_b)
    raw = gateway.complete(
        "You are comparing two exact passages from two admitted medical "
        "sources. Say whether they conflict on a specific point, and name "
        "the point in one sentence. If they do not conflict, say so. "
        "Answer as JSON: {\"disagree\": true|false, \"point\": \"...\"}.\n\n"
        f"PASSAGE A ({pa['heading']}): {pa['text']}\n\n"
        f"PASSAGE B ({pb['heading']}): {pb['text']}")
    try:
        parsed = cli._extract_json(raw)
    except Exception:
        parsed = {}
    return _append("proposals.jsonl", {
        "proposal_id": "prop_" + uuid.uuid4().hex[:12],
        "kind": "disagreement",
        "room_id": room_id,
        "passage_a": pa, "passage_b": pb,
        "model_says": {"disagree": bool(parsed.get("disagree")),
                        "point": str(parsed.get("point") or "")[:400]},
        "raw_response": raw,
        "origin": "model_proposal", "status": "awaiting_owner",
        "at": cli._now()})


def rule_disagreement(proposal_id: str, ruling: str, note: str = "") -> dict:
    if ruling not in ("accepted", "rejected"):
        raise ValueError("ruling must be accepted or rejected")
    props = {p.get("proposal_id"): p for p in _rows("proposals.jsonl")
             if p.get("kind") == "disagreement"}
    p = props.get(proposal_id)
    if not p:
        raise ValueError("no such disagreement proposal")
    return _append("disagreements.jsonl", {
        "disagreement_id": "dis_" + uuid.uuid4().hex[:12],
        "proposal_id": proposal_id,
        "passage_a": p["passage_a"], "passage_b": p["passage_b"],
        "point": p.get("model_says", {}).get("point", ""),
        "ruling": ruling, "note": (note or "")[:400],
        "ruled_by": "owner", "at": cli._now()})
