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


# ---- exact identity: WHICH text did the run examine? ----------------------
#
# Block 123b. A candidate card inside a Go Deep result is built with the
# COMPONENT'S trace, and the component's record holds as its input_text the
# dissection's gist for that component ("The part of the mechanism the input
# states outright…"), not the owner's draft. A carry bound to that hash was
# bound to the wrong text: the tray would compare the draft in the room
# against a sentence the pipeline wrote, find them different every time, and
# offer to "open the analyzed version" of a paragraph the owner never wrote.
# A sprout's record is worse — its input_text is "sprout of 'Title': …".
#
# So the analysed text is found by climbing RECORDED links only: a composite
# run (deep, decompose) lists its components' traces in its own record; a
# sprout records the parent_trace_id it was opened from. Each hop is written
# into the carry so the record says how the identity was established. A run
# with no recorded road back to owner text is refused — a derived sentence
# is not a draft, and a reconstruction is not a record.

COMPOSITE_MODES = ("deep", "decompose")
# the modes run() writes with the owner's own text as input_text — unless a
# composite's record lists the run as one of its components
DIRECT_MODES = ("forge", "crack", "riff", "play")
_MAX_HOPS = 12
_COMPOSITE_CACHE: "dict[str, tuple[float, int, list[str], str]]" = {}


def _load_record(trace_id: str) -> "dict | None":
    p = Path(cli.RESULTS_DIR) / f"{trace_id}.json"
    if not trace_id or not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None


def composite_listing(trace_id: str) -> str:
    """The composite run whose OWN record lists this trace among its
    components — '' when none does. Every record is read once (a record's
    `mode` says whether it is a composite; the file name is only a
    convention) and remembered by mtime and size, so a carry costs a stat
    per record after the first."""
    rd = Path(cli.RESULTS_DIR)
    for p in sorted(rd.glob("*.json")):
        try:
            st = p.stat()
        except OSError:
            continue
        key = str(p)
        hit = _COMPOSITE_CACHE.get(key)
        if not hit or hit[0] != st.st_mtime or hit[1] != st.st_size:
            members: "list[str]" = []
            own = p.stem
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
                if isinstance(d, dict) and d.get("mode") in COMPOSITE_MODES:
                    members = [str(c.get("trace_id") or "") for c in (d.get("components") or [])
                               if isinstance(c, dict)]
                    members = [m for m in members if m]
                    own = str(d.get("trace_id") or p.stem)
            except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                members = []
            hit = (st.st_mtime, st.st_size, members, own)
            _COMPOSITE_CACHE[key] = hit
        if trace_id in hit[2]:
            return hit[3]
    return ""


def draft_of(trace_id: str) -> dict:
    """The owner's text a run examined, by recorded links only.

    Returns {"text", "trace_id" (the root run that held the text),
    "chain": [{"trace_id", "mode", "link"}, …]} where link is how the hop
    was established: "component_of" (the composite's record lists it),
    "parent_trace_id" (the sprout's record names it), or "root".
    Raises ValueError when no recorded road leads to owner text."""
    chain: "list[dict]" = []
    seen: "set[str]" = set()
    tid = (trace_id or "").strip()
    while True:
        if not tid:
            raise ValueError("a carry needs the trace of the run it came from")
        if tid in seen or len(chain) >= _MAX_HOPS:
            raise ValueError("the run's recorded lineage loops or runs too deep to follow")
        seen.add(tid)
        rec = _load_record(tid)
        if rec is None:
            if chain:
                raise ValueError(f"the run this came from names {tid!r} as its parent, but no "
                                 f"record of that run exists — there is no draft to bind to")
            raise ValueError("no run record for that trace; a carry must bind to the text a "
                             "run actually examined")
        mode = str(rec.get("mode") or "")
        if mode in COMPOSITE_MODES:
            text = rec.get("input_text") or rec.get("source_text") or ""
            if not text.strip():
                raise ValueError("that run recorded no input text, so there is no draft "
                                 "identity to bind a carry to")
            chain.append({"trace_id": tid, "mode": mode, "link": "root"})
            return {"text": text, "trace_id": tid, "chain": chain}
        if mode in DIRECT_MODES:
            parent = composite_listing(tid)
            if parent:
                chain.append({"trace_id": tid, "mode": mode, "link": "component_of"})
                tid = parent
                continue
            text = rec.get("input_text") or rec.get("source_text") or ""
            if not text.strip():
                raise ValueError("that run recorded no input text, so there is no draft "
                                 "identity to bind a carry to")
            chain.append({"trace_id": tid, "mode": mode, "link": "root"})
            return {"text": text, "trace_id": tid, "chain": chain}
        if mode == "sprout":
            parent = str(rec.get("parent_trace_id") or "").strip()
            if not parent:
                raise ValueError("this rabbithole records no run it was opened from, so there "
                                 "is no draft to carry back to")
            chain.append({"trace_id": tid, "mode": mode, "link": "parent_trace_id"})
            tid = parent
            continue
        raise ValueError(f"a {mode or 'record of unknown kind'!r} run records no road back to "
                         f"the text it examined; carries from it cannot be bound to a draft yet")


# ---- server authority: the record decides what a carry says ---------------
#
# Block 123b. The first cut took the excerpt and the standing FROM THE PAGE.
# That let the page decide what a carry claims — a buggy or dishonest client
# could carry a contradicted candidate as "supported" and the server would
# have written it down. So the request now names an object, and the server
# resolves that name against the run's own record, takes the excerpt and the
# standing from there, and refuses anything that does not resolve to exactly
# one thing. A carry's standing is a fact the record holds, never a claim
# the client makes.

CANDIDATE_FIELDS = ("definition", "plain_gloss", "central_contradiction", "mechanism",
                    "axiom", "boundary", "example_sentence")


def _candidates_of(record: dict) -> "list[dict]":
    out = []
    for c in record.get("candidates") or []:
        out.append(c)
    for g in record.get("groups") or []:
        for c in g.get("candidates") or []:
            out.append(c)
    return out


def _bff(c: dict) -> dict:
    return c.get("bone_flesh_friction") or c.get("bff") or {}


def _one(matches: list, what: str) -> dict:
    if len(matches) != 1:
        raise ValueError(f"{what} resolves to {len(matches)} object(s) in the record; a carry "
                         f"must name exactly one")
    return matches[0]


def resolve_ref(record: dict, source_kind: str, ref: dict) -> "tuple[str, dict, dict]":
    """(excerpt, standing, resolved_ref) — all three FROM THE RECORD.

    The excerpt is the record's own text for the named field. The standing is
    what the record says about that object. The resolved ref is the identity
    the server settled on, which is what gets stored — never the client's."""
    ref = dict(ref or {})
    kind = source_kind

    if kind in ("candidate", "friction", "anchor_fit"):
        cands = _candidates_of(record)
        cid = (ref.get("concept_id") or "").strip()
        title = (ref.get("title") or "").strip()
        if cid:
            m = [c for c in cands if (_bff(c).get("concept_id") or "") == cid]
        elif title:
            m = [c for c in cands if (_bff(c).get("title") or c.get("title") or "") == title]
        else:
            raise ValueError("a candidate ref needs a concept_id or a title")
        c = _one(m, f"candidate {cid or title!r}")
        b = _bff(c)
        fr = b.get("friction") or {}
        cs = b.get("claim_support") or {}
        title = b.get("title") or c.get("title") or ""
        base_standing = {"anchor_fit": cs.get("support") or "",
                         "friction_verdict": fr.get("verdict") or "",
                         "contradicted": bool(fr.get("contradicts_anchor"))}
        resolved = {"concept_id": b.get("concept_id") or "", "title": title}
        if kind == "candidate":
            field = (ref.get("field") or "definition").strip()
            if field not in CANDIDATE_FIELDS:
                raise ValueError(f"unknown candidate field {field!r}")
            text = ((b.get("flesh") or {}).get(field) or "").strip()
            if not text:
                raise ValueError(f"the record holds no {field!r} for {title!r}")
            standing = dict(base_standing)
            if field == "example_sentence":
                # The anchor-fit stage read the title, definition, tension
                # and axiom against the anchor — not the example, which is
                # the model's own sentence. So the example carries INVENTED,
                # the candidate's Friction verdict (Friction reviewed the
                # whole candidate) and whether the candidate is contradicted,
                # but not an anchor fit it was never given.
                standing.pop("anchor_fit", None)
                standing.update({"invented": True, "route": "model-written example"})
                excerpt = text
            else:
                standing["route"] = "candidate concept"
                excerpt = f"{title}: {text}" if field == "definition" else f"{title} — {field}: {text}"
            resolved["field"] = field
            return excerpt, standing, resolved
        if kind == "friction":
            text = (fr.get("hostile_read") or "").strip()
            if not text:
                raise ValueError(f"the record holds no Friction objection on {title!r}")
            standing = {"friction_verdict": fr.get("verdict") or "",
                        "contradicted": bool(fr.get("contradicts_anchor")),
                        "route": "critic\u2019s objection \u2014 advisory"}
            resolved["field"] = "hostile_read"
            return f"Friction on \u201c{title}\u201d: {text}", standing, resolved
        # anchor_fit
        sup = cs.get("support") or ""
        if sup not in ("partial", "topical", "contradicted"):
            raise ValueError(f"anchor fit on {title!r} is {sup or 'unrecorded'!r}; only a partial, "
                             f"topical or contradicted result carries a deciding difference")
        why = (cs.get("note") or "").strip() or " \u00b7 ".join(
            x for x in (("anchor: " + cs["deciding_anchor_words"]) if cs.get("deciding_anchor_words") else "",
                        ("claim: " + cs["deciding_claim_words"]) if cs.get("deciding_claim_words") else "") if x)
        if not why:
            raise ValueError(f"the record holds no deciding difference for {title!r}")
        standing = {"anchor_fit": sup,
                    "route": "anchor-fit difference \u2014 reviewer-selected words, not a proof"}
        resolved["field"] = "claim_support"
        return f"Anchor fit ({sup}) on \u201c{title}\u201d: {why}", standing, resolved

    if kind == "thread":
        threads = record.get("threads") or []
        idx = ref.get("index")
        if not isinstance(idx, int) or not (0 <= idx < len(threads)):
            raise ValueError("a thread ref needs the index of a thread that exists in this run")
        t = threads[idx]
        if ref.get("title") and (t.get("anchor_name") or "") != ref.get("title"):
            raise ValueError("the thread at that index is not the thread named")
        parts = [t.get("anchor_name") or "", t.get("culture_or_work") or "",
                 t.get("reading") or t.get("parallel") or "",
                 ("Where it breaks: " + t["divergence"]) if t.get("divergence") else ""]
        excerpt = " \u2014 ".join(x for x in parts if x)
        if not excerpt.strip():
            raise ValueError("that thread holds no text to carry")
        cited = len(record.get("citations") or [])
        standing = {"route": "lateral thread \u00b7 " + (t.get("review_verdict") or "unreviewed"),
                    "recall_only": not cited, "unverified": True}
        return excerpt, standing, {"index": idx, "title": t.get("anchor_name") or "",
                                   "work": t.get("culture_or_work") or ""}

    if kind == "door":
        doors = record.get("doors") or []
        did = (ref.get("door_id") or "").strip()
        text = (ref.get("text") or "").strip()
        norm = lambda d: d if isinstance(d, dict) else {"text": d, "door_id": ""}
        ds = [norm(d) for d in doors]
        m = [d for d in ds if did and d.get("door_id") == did] or \
            [d for d in ds if text and (d.get("text") or "") == text]
        d = _one(m, f"door {did or text!r}")
        if not (d.get("text") or "").strip():
            raise ValueError("that door holds no text")
        return d["text"], {"route": "investigative road, not yet walked", "unverified": True}, \
               {"door_id": d.get("door_id") or "", "text": d["text"]}

    raise ValueError(f"the server cannot resolve carries of kind {source_kind!r} yet")


def record_carry(*, trace_id: str, source_key: str, source_kind: str,
                 source_ref: dict, excerpt: str, standing: dict | None = None,
                 analyzed_head: str = "", analyzed_words: int = 0,
                 analyzed_trace_id: str = "", chain: "list[dict] | None" = None,
                 target_source_key: str = "", note: str = "") -> dict:
    """One carry. `source_ref` is the stable identity inside the result
    (component label, candidate concept_id/title, thread index+title, door
    text, field name) — whatever the result itself uses, never a DOM
    position. `excerpt` is the exact text at that moment. `analyzed_trace_id`
    is the run that HELD the examined text (the composite, for a card inside
    a Go Deep result) and `chain` is the recorded road from the source run to
    it, so the record says how that identity was established."""
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
                     "words": int(analyzed_words or 0),
                     "trace_id": analyzed_trace_id or trace_id,
                     "chain": [dict(h) for h in (chain or [])]},
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
