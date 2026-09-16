#!/usr/bin/env python3
"""The action registry (workspace-v2, slice B; instructions §5).

One definition per action, and everything that presents an action — the
Tools panel, the selection menu, Ask, the proposal card — is generated
from it. The server stays the authority: a client may propose only what
the registry allows for the subject it holds, and a Start is revalidated
against the frozen proposal, never against what the client says now.

Each action carries: a stable id; a plain label and the legacy names it
answers to; the group it is shown in; its kind (a view that opens, work
that is dispatched, a note or ruling that is recorded, a lookup that reads
a producer, an apply that edits the draft locally); the subject types it
accepts; the mutation class; what leaves this machine and to whom; the
provider or producer, and how many calls; the result type; and the handler
— for dispatched work the `/api/jobs` mode, for views a route. Readiness is
computed at request time from the record (gateway lane, connectors), never
stored as a constant.

Two rules the registry encodes rather than the pages:
- opening a view is not starting work. A view starts no model, research or
  producer operation. Only `dispatch` and `lookup` reach anything.
- a selection may start only what accepts a selection. Sprout wants a
  concept; a selection is offered Analyze this passage first, never a
  fabricated concept id."""
from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import wordicon_cli as cli
import snapshots

REGISTRY_VERSION = 1

# The complete /api/jobs mode inventory at 17894e3, kept whole (§5).
JOB_MODES = ("auto", "deep", "forge", "crack", "decompose", "riff", "play", "revise",
             "sprout", "refract", "verify", "archetype", "recheck", "etymon")

GROUPS = ("on_draft", "explore", "investigate", "more", "record")
KINDS = ("view", "dispatch", "lookup", "note", "ruling", "apply")
SUBJECTS = ("document", "selection", "concept", "word", "description", "candidate", "result", "source", "none")


def _a(id_, label, *, group, kind, subjects, handler, aliases=(), inputs=(), mutation="none",
       outbound_fields=(), recipient="none", provider="none", calls=0, result_type="", mode=None,
       route=None, note="", legacy_entry="", dormant=False):
    assert group in GROUPS and kind in KINDS
    assert all(s in SUBJECTS for s in subjects), subjects
    if mode is not None:
        assert mode in JOB_MODES, mode
    return {"id": id_, "label": label, "aliases": list(aliases), "group": group, "kind": kind,
            "subjects": list(subjects), "inputs": list(inputs), "mutation": mutation,
            "outbound": {"fields": list(outbound_fields), "recipient": recipient},
            "provider": provider, "calls": calls, "result_type": result_type, "handler": handler,
            "mode": mode, "route": route, "note": note, "legacy_entry": legacy_entry, "dormant": dormant}


ACTIONS = [
    # ---- on this draft -------------------------------------------------------
    _a("feedback.readers", "Get feedback", group="on_draft", kind="dispatch",
       subjects=("document", "selection"), handler="moira", aliases=("readers", "three readers", "moira", "feedback", "professor moira"),
       inputs=("text",), mutation="record", outbound_fields=("text",), recipient="model", provider="model",
       calls="3 (one per reader)", result_type="reading", legacy_entry="the room's Get feedback button",
       note="three separate readings, one call each; advisory; nothing here combines them"),
    _a("analyze.decompose", "Analyze this passage", group="on_draft", kind="dispatch",
       subjects=("selection", "document"), handler="job", mode="decompose",
       aliases=("decompose", "take apart the passage", "analyze", "analyse", "analyse this passage"),
       inputs=("text",), mutation="record", outbound_fields=("text",), recipient="model", provider="model",
       calls="several (a dissection, then one per concept found)", result_type="run",
       legacy_entry="the chooser's Analyze this passage / decompose"),
    _a("attach.source", "Attach a file or a source", group="on_draft", kind="view",
       subjects=("none",), handler="view", route="/#bring", aliases=("attach", "upload", "bring something in", "add a source", "library intake"),
       result_type="source", legacy_entry="Home → Bring something in", note="opens the intake; nothing is read by a model on admission"),
    # ---- explore -------------------------------------------------------------
    _a("explore.sprout", "Explore related ideas", group="explore", kind="dispatch",
       subjects=("concept",), handler="job", mode="sprout", aliases=("sprout", "related ideas", "explore parallels", "lateral"),
       inputs=("concept",), mutation="record", outbound_fields=("concept title", "concept definition"), recipient="model",
       provider="model", calls="1", result_type="run", legacy_entry="a candidate card's Sprout door",
       note="wants a concept; from a selection, Analyze this passage comes first"),
    _a("explore.refract", "Find related words", group="explore", kind="dispatch",
       subjects=("selection", "concept", "description"), handler="job", mode="refract",
       aliases=("refract", "related words", "explore other languages", "synonyms", "antonyms", "other languages", "find related words and contrasts"),
       inputs=("meaning or selection",), mutation="record", outbound_fields=("the selection, or the meaning and its gloss",),
       recipient="model", provider="model", calls="2", result_type="run", legacy_entry="Find related words (Refract)"),
    _a("explore.forge", "Build a concept", group="explore", kind="dispatch",
       subjects=("selection", "document", "description"), handler="job", mode="forge",
       aliases=("forge", "coin", "name this", "build a concept"), inputs=("text",), mutation="record",
       outbound_fields=("text",), recipient="model", provider="model", calls="several (generation, critique)", result_type="run",
       legacy_entry="the chooser's Develop the idea / forge"),
    _a("explore.crack", "Take this apart", group="explore", kind="dispatch",
       subjects=("selection", "word", "document"), handler="job", mode="crack",
       aliases=("crack", "take apart", "take this apart"), inputs=("text",), mutation="record",
       outbound_fields=("text",), recipient="model", provider="model", calls="several", result_type="run",
       legacy_entry="crack"),
    _a("explore.deep", "Full workup", group="explore", kind="dispatch",
       subjects=("document", "selection"), handler="job", mode="deep",
       aliases=("go deep", "deep", "full workup", "workup", "the whole draft"), inputs=("text",), mutation="record",
       outbound_fields=("text",), recipient="model", provider="model",
       calls="several (a dissection, then generation and review per component)", result_type="run",
       legacy_entry="⌘⇧P / Full workup"),
    _a("explore.map", "Connect on the Map", group="explore", kind="view",
       subjects=("concept", "none"), handler="view", route="/map/focus",
       aliases=("map", "map focus", "connect on the map", "the map"), result_type="view",
       legacy_entry="Map · focus", note="opens the visual Map as a place; starts nothing"),
    _a("explore.archetype", "Explore character patterns", group="explore", kind="dispatch",
       subjects=("concept",), handler="job", mode="archetype", aliases=("archetype", "character patterns"),
       inputs=("concept",), mutation="record", outbound_fields=("concept title", "definition", "contradiction", "axiom", "gloss"),
       recipient="model", provider="model", calls="1", result_type="run", legacy_entry="a candidate card's Archetype door"),
    _a("explore.riff", "Riff on this", group="explore", kind="dispatch",
       subjects=("selection", "document", "description"), handler="job", mode="riff", aliases=("riff",),
       inputs=("text",), mutation="record", outbound_fields=("text",), recipient="model", provider="model",
       calls="several", result_type="run", legacy_entry="riff"),
    _a("explore.play", "Play", group="explore", kind="dispatch",
       subjects=("selection", "document", "description"), handler="job", mode="play", aliases=("play", "play lane"),
       inputs=("text",), mutation="record", outbound_fields=("text",), recipient="model", provider="model",
       calls="several", result_type="run", legacy_entry="the Play lane"),
    _a("explore.etymon", "Trace the word's roots", group="explore", kind="dispatch",
       subjects=("word", "selection"), handler="job", mode="etymon", aliases=("etymon", "etymology", "roots", "word roots"),
       inputs=("text",), mutation="record", outbound_fields=("text",), recipient="model", provider="model",
       calls="1", result_type="run", legacy_entry="etymon"),
    _a("explore.revise", "Revise this concept", group="explore", kind="dispatch",
       subjects=("concept",), handler="job", mode="revise", aliases=("revise", "rework", "wordify"),
       inputs=("concept",), mutation="record", outbound_fields=("concept", "claims", "owner note"), recipient="model",
       provider="model", calls="several", result_type="run", legacy_entry="revise"),
    _a("explore.recheck", "Re-check this concept", group="explore", kind="dispatch",
       subjects=("concept",), handler="job", mode="recheck", aliases=("recheck", "re-check"),
       inputs=("concept",), mutation="record", outbound_fields=("concept",), recipient="model", provider="model",
       calls="1", result_type="run", legacy_entry="recheck"),
    _a("explore.verify", "Verify a candidate", group="explore", kind="dispatch",
       subjects=("candidate",), handler="job", mode="verify", aliases=("verify",),
       inputs=("candidate",), mutation="record", outbound_fields=("candidate",), recipient="model", provider="model",
       calls="1", result_type="run", legacy_entry="verify"),
    _a("explore.auto", "Let Nikodemus choose the route", group="explore", kind="dispatch",
       subjects=("selection", "document", "description"), handler="job", mode="auto", aliases=("auto", "route it", "let nikodemus choose"),
       inputs=("text",), mutation="record", outbound_fields=("text",), recipient="model", provider="model",
       calls="several", result_type="run", legacy_entry="the chooser's routed run", note="the router proposes a mode; the record says which"),
    # ---- investigate ---------------------------------------------------------
    _a("investigate.ethicalalt.lookup", "Look up existing profiles", group="investigate", kind="lookup",
       subjects=("none",), handler="federation", aliases=("ethicalalt", "ethical alt", "ethical alternatives", "profiles"),
       mutation="record", outbound_fields=("nothing — a read of the producer's index",), recipient="producer:ethicalalt",
       provider="producer:ethicalalt", calls="1 read", result_type="deposition", legacy_entry="Investigation Rooms → EthicalAlt connector"),
    _a("investigate.ethicalalt.start", "Start an investigation (EthicalAlt)", group="investigate", kind="dispatch",
       subjects=("description",), handler="adapter", aliases=("investigate a company", "ethicalalt investigation", "investigate"),
       inputs=("a company or brand name",), mutation="record", outbound_fields=("the name, and a session id minted here",), recipient="producer:ethicalalt",
       provider="producer:ethicalalt", calls="1 POST (the start), then 1 read of the unsigned export, then 1 POST for the signed receipt — which the producer stores",
       result_type="investigation", legacy_entry="none (not connected)",
       note="the contract is pinned from the producer's main at 1a71460 (read from source); live starts wait for the owner's ruling that the deployment runs that revision"),
    _a("investigate.opencase.list", "List cases", group="investigate", kind="lookup",
       subjects=("none",), handler="federation", aliases=("open case", "opencase", "cases"),
       mutation="record", outbound_fields=("your key, to the configured origin",), recipient="producer:open_case",
       provider="producer:open_case", calls="1 read", result_type="deposition", legacy_entry="Investigation Rooms → Open Case connector"),
    _a("investigate.opencase.start", "Start an investigation (Open Case)", group="investigate", kind="dispatch",
       subjects=("description",), handler="adapter", aliases=("open case investigation",),
       inputs=("a case id, your investigator handle, and the subject's name",), mutation="record",
       outbound_fields=("the case id, your handle, the subject's name, and your key to the configured origin",), recipient="producer:open_case",
       provider="producer:open_case", calls="1 POST (the start), then 1 read of the report — a read the producer counts as a view; the producer's own enrichment calls providers on its side",
       result_type="investigation", legacy_entry="none (not connected)",
       note="the contract is pinned from the producer's origin/main at 4dc1709 (read from source); live starts wait for the owner's ruling that the deployment runs that revision; "
            "a signed snapshot is a separate act (Take a signed snapshot)"),
    _a("investigate.opencase.snapshot", "Take a signed snapshot (Open Case)", group="investigate", kind="dispatch",
       subjects=("description",), handler="adapter", aliases=("open case snapshot", "snapshot the case", "signed snapshot"),
       inputs=("a case id, your investigator handle, and an optional label",), mutation="record",
       outbound_fields=("the case id, your handle, the label, and your key to the configured origin",), recipient="producer:open_case",
       provider="producer:open_case", calls="1 POST — a MUTATION on the producer: a snapshot row is created, the case file re-signed, your handle credited",
       result_type="investigation", legacy_entry="none (not connected)",
       note="never part of a start; proposed and started on its own, disclosed as the mutation it is; the snapshot's signature is verified here under the pinned key"),
    _a("investigate.publiceye.start", "Start an investigation (PUBLIC EYE)", group="investigate", kind="dispatch",
       subjects=("none",), handler="adapter", aliases=("public eye", "publiceye", "frame"),
       inputs=("an article or podcast URL",), mutation="record", outbound_fields=("the URL",), recipient="producer:public_eye",
       provider="producer:public_eye", calls="unknown", result_type="investigation", legacy_entry="none (no connector kind)"),
    _a("investigate.rabbithole.connect", "Connect Rabbit Hole", group="investigate", kind="view",
       subjects=("none",), handler="unavailable", aliases=("rabbit hole", "rabbithole"), result_type="view",
       legacy_entry="none", note="your separate application; its repository is not named, so nothing can be shown"),
    # ---- more tools (the specialist places, opened inside the shell) --------
    _a("more.bench", "Bench", group="more", kind="view", subjects=("none",), handler="view", route="/bench",
       aliases=("the bench", "rework a word"), result_type="view", legacy_entry="/bench"),
    _a("more.clinic", "Clinic", group="more", kind="view", subjects=("none",), handler="view", route="/clinic",
       aliases=("the clinic", "medical wing"), result_type="view", legacy_entry="/clinic"),
    _a("more.recovery", "Recovery review", group="more", kind="view", subjects=("none",), handler="view", route="/recovery",
       aliases=("recovery", "recovery review"), result_type="view", legacy_entry="/recovery"),
    _a("more.rooms", "Investigation rooms", group="more", kind="view", subjects=("none",), handler="view", route="/investigation",
       aliases=("rooms", "investigation rooms", "depositions", "connectors"), result_type="view", legacy_entry="/investigation"),
    _a("more.inquiry", "Inquiry", group="more", kind="view", subjects=("none",), handler="view", route="/inquiry",
       aliases=("inquiry", "open questions", "a question kept"), result_type="view", legacy_entry="/inquiry"),
    _a("more.trails", "Map · trails", group="more", kind="view", subjects=("none",), handler="view", route="/map/trails",
       aliases=("trails", "map trails"), result_type="view", legacy_entry="/map/trails"),
    _a("more.world", "Map · world", group="more", kind="view", subjects=("none",), handler="view", route="/map/world",
       aliases=("world", "overworld", "map world", "wayfinder"), result_type="view", legacy_entry="/map/world"),
    _a("more.speak", "Speak to Nikodemus", group="more", kind="view", subjects=("none",), handler="view", route="/#speak",
       aliases=("speak", "dictate", "microphone", "speak to nikodemus"), result_type="view", legacy_entry="Home → Speak"),
    _a("more.readaloud", "Read aloud", group="more", kind="view", subjects=("none",), handler="unavailable",
       aliases=("read aloud", "read it to me"), result_type="view", legacy_entry="named by /api/speak/status only", dormant=True,
       note="named by a status response; not proven implemented — shown as not available until it is"),
    _a("more.constitution", "What is Nikodemus", group="more", kind="view", subjects=("none",), handler="view", route="/constitution",
       aliases=("constitution", "what is nikodemus", "the law"), result_type="view", legacy_entry="/constitution"),
    _a("more.anatomy", "Anatomy", group="more", kind="view", subjects=("none",), handler="standalone", route="/anatomy",
       aliases=("anatomy",), result_type="view", legacy_entry="/anatomy (standalone)"),
    _a("more.legacy", "The previous interface", group="more", kind="view", subjects=("none",), handler="standalone", route="/",
       aliases=("legacy", "old interface", "previous interface", "home"), result_type="view", legacy_entry="/"),
    # ---- recorded on a result, a word, a draft (not shown in Tools) ----------
    _a("note.carry", "Add to revision notes", group="record", kind="note", subjects=("result",), handler="carry",
       aliases=("carry", "carry back", "revision notes"), inputs=("trace_id", "source_ref"), mutation="record",
       result_type="carry", legacy_entry="Carry Back", note="means 'may be useful while revising' and nothing more"),
    _a("word.bookmark", "Bookmark this word", group="record", kind="note", subjects=("word",), handler="related_save",
       aliases=("bookmark", "save word", "keep this word"), inputs=("word", "trace_id"), mutation="record", result_type="saved_word",
       legacy_entry="a related-word card's save"),
    _a("word.sources", "Check sources", group="record", kind="dispatch", subjects=("word",), handler="word_sources",
       aliases=("check sources", "sources for this word"), inputs=("word", "language", "period"), mutation="record",
       outbound_fields=("the word, its language and period — nothing else",), recipient="model", provider="model", calls="1",
       result_type="word_sources", legacy_entry="a related-word card's Check sources"),
    _a("rule.judge", "Rule on this", group="record", kind="ruling", subjects=("result", "candidate"), handler="judge",
       aliases=("rule", "accept", "reject", "revise the ruling", "judge"), inputs=("candidate", "ruling"), mutation="record",
       result_type="judgment", legacy_entry="/api/judge", note="the owner's ruling; the panel never rules by itself"),
    _a("apply.insert", "Insert below the selection", group="record", kind="apply", subjects=("result",), handler="editor",
       aliases=("insert",), inputs=("suggested text", "target"), mutation="draft", result_type="application",
       legacy_entry="none", note="local to the editor; one undo step; only for an actual textual suggestion with a valid target"),
    _a("apply.replace", "Replace the selection", group="record", kind="apply", subjects=("result",), handler="editor",
       aliases=("replace",), inputs=("suggested text", "target"), mutation="draft", result_type="application",
       legacy_entry="none", note="local to the editor; one undo step; refused when the target moved"),
]
BY_ID = {a["id"]: a for a in ACTIONS}
assert len(BY_ID) == len(ACTIONS), "duplicate action id"
assert {a["mode"] for a in ACTIONS if a["mode"]} == set(JOB_MODES), "the registry must name every /api/jobs mode"


# ---- readiness, from the record -----------------------------------------------

def _lane(server_gateway) -> dict:
    """The model lane the server would use right now — asked of the server,
    never assumed. The mock lane makes no provider request and incurs no
    provider charge; that is what it says, and it never claims to be local
    work because the process runs on the Mac."""
    try:
        gw = server_gateway()
        if gw.is_external:
            return {"lane": gw.name, "external": True, "model": os.environ.get("WORDICON_MODEL", ""),
                    "says": f"a live model call to {gw.name}; cost unknown until it runs"}
        return {"lane": "mock", "external": False, "model": "",
                "says": "mock lane: no provider request, no provider charge; the result is a canned fixture"}
    except Exception as e:  # noqa: BLE001 — misconfigured is a state, not a crash
        return {"lane": "misconfigured", "external": False, "model": "", "says": f"the gateway is misconfigured: {e}"}


def _producer_readiness(producer: str, wants: str) -> dict:
    """Derived per capability from the connector registry (instructions §10):
    configured · contract supported · credentials · last explicit check ·
    lookup available · start available. No remote check is made here."""
    import federation
    out = {"producer": producer, "configured": False, "enabled": False, "contract": "unsupported",
           "credential": "not required", "last_check": "never tried", "available": False, "reason": ""}
    if producer not in federation.PRODUCERS:
        out["reason"] = "no connector kind exists for this producer yet" if producer != "rabbit_hole" else "repository not named"
        out["contract"] = "unknown"
        return out
    conns = [c for c in federation.load_connectors(include_disabled=True) if c.get("producer") == producer]
    if not conns:
        out["reason"] = "no connector registered"
        out["contract"] = "read-only (locate, import, verify)" if wants == "lookup" else "starting is not part of the connector contract"
        return out
    c = sorted(conns, key=lambda x: (not x.get("enabled"), x.get("connector_id")))[0]
    out.update({"configured": True, "enabled": bool(c.get("enabled")), "connector_id": c.get("connector_id"),
                "last_check": c.get("status") or "never tried",
                "last_success_at": c.get("last_success_at") or ""})
    needs_cred = federation.PRODUCERS[producer].get("auth") == "bearer"
    if needs_cred:
        out["credential"] = "present" if c.get("credential_configured") else "missing"
    if wants == "lookup":
        out["contract"] = "read-only (locate, import, verify)"
        if not c.get("enabled"):
            out["reason"] = "the connector is disabled"
        elif needs_cred and not c.get("credential_configured"):
            out["reason"] = "the credential named on the connector is not present"
        else:
            out["available"] = True
    else:
        out["contract"] = "starting is not part of the connector contract"
        out["reason"] = "Nikodemus cannot start this here yet — the producer can, this surface cannot"
    return out


def readiness(action: dict, server_gateway) -> dict:
    """What the card may say, from the record. Never a constant."""
    a = action
    if a["kind"] == "view":
        if a["handler"] == "unavailable":
            return {"available": False, "reason": a["note"] or "not available"}
        return {"available": True, "reason": "opens a view; starts nothing"}
    if a["kind"] in ("note", "ruling", "apply"):
        return {"available": True, "reason": "recorded locally; no model, no network"}
    if a["provider"] == "model":
        lane = _lane(server_gateway)
        return {"available": lane["lane"] != "misconfigured", "reason": lane["says"], "lane": lane}
    if a["provider"].startswith("producer:"):
        prod = a["provider"].split(":", 1)[1]
        if a["handler"] == "adapter":
            # slice F: the adapter derives per capability (configured, contract, credentials,
            # last check, deployment verified) — no remote check here
            import producers
            r = producers.readiness(prod, "start")
        else:
            r = _producer_readiness(prod, "lookup" if a["kind"] == "lookup" else "start")
        return {"available": r["available"], "reason": r["reason"] or ("available" if r["available"] else "not available"),
                "producer": r}
    return {"available": False, "reason": "unknown provider"}


def listing(server_gateway) -> dict:
    """GET /api/actions: the registry with readiness, no provider call."""
    lane = _lane(server_gateway)
    items = []
    for a in ACTIONS:
        items.append({**a, "readiness": readiness(a, server_gateway)})
    return {"registry_version": REGISTRY_VERSION, "lane": lane, "actions": items,
            "groups": list(GROUPS), "population": f"every registered action ({len(items)}), including views and records; "
                                                   f"readiness is derived from the record at this request"}


# ---- Ask: deterministic matching ----------------------------------------------

def _norm(s: str) -> str:
    return re.sub(r"[^a-z0-9 ]+", " ", (s or "").lower()).strip()


def match(query: str, subject: str = "none") -> dict:
    """Ask's matcher: exact label or alias first, then every action whose
    label or aliases contain every word of the query. Ambiguity is returned
    as choices, never resolved by guessing. No model is asked."""
    q = _norm(query)
    if not q:
        return {"query": query, "matches": [], "ambiguous": False}
    exact, partial = [], []
    words = q.split()
    for a in ACTIONS:
        names = [_norm(a["label"])] + [_norm(x) for x in a["aliases"]]
        if q in names:
            exact.append(a)
            continue
        hay = " ".join(names)
        if all(w in hay for w in words):
            partial.append(a)
    found = exact or partial
    remainder = ""
    if not found:
        # slice F: "investigate Exemplar Holdings" — a plain-language request whose
        # first words name an action that takes a description, and whose rest is
        # the description. The rest goes to the proposal as the subject, verbatim
        # from the query; nothing is guessed about it.
        raw = " ".join((query or "").split())
        best = None
        for a in ACTIONS:
            if "description" not in a["subjects"]:
                continue
            for name in [a["label"]] + list(a["aliases"]):
                n = " ".join(name.split())
                if len(raw) > len(n) + 1 and raw[:len(n)].lower() == n.lower() and raw[len(n)] == " ":
                    if best is None or len(n) > len(best[1]):
                        best = (a, n)
        if best is not None:
            found = [best[0]]
            remainder = raw[len(best[1]):].strip()
    subj_ok = [a for a in found if subject in a["subjects"] or "none" in a["subjects"] or subject == "none"]
    out = [{"id": a["id"], "label": a["label"], "group": a["group"], "kind": a["kind"],
            "accepts_subject": subject in a["subjects"] or subject == "none" or bool(remainder),
            **({"remainder": remainder} if remainder else {})} for a in (subj_ok or found)]
    return {"query": query, "matches": out, "ambiguous": len(out) > 1, "exact": bool(exact)}


# ---- prepare: a frozen proposal ------------------------------------------------

def _proposals_dir() -> Path:
    return Path(cli.LOCAL_STATE) / "proposals"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


class PrepareError(ValueError):
    def __init__(self, message: str, status: int = 400, choices: list | None = None):
        super().__init__(message)
        self.status = status
        self.choices = choices or []


def prepare(action_id: str, subject: dict, inputs: dict, server_gateway) -> dict:
    """POST /api/actions/prepare. Validates the subject against the action,
    freezes the scope as an immutable snapshot, and writes the proposal the
    Start will be checked against. Starts nothing; reaches nothing."""
    a = BY_ID.get(action_id)
    if a is None:
        raise PrepareError(f"no action {action_id!r}", 404)
    if a["kind"] not in ("dispatch", "lookup"):
        raise PrepareError(f"{a['label']} is a {a['kind']}; it is opened or recorded, not started", 400)
    kind = str((subject or {}).get("kind") or "none")
    if kind not in SUBJECTS:
        raise PrepareError(f"unknown subject kind {kind!r}", 400)
    if kind not in a["subjects"]:
        if kind == "selection" and "concept" in a["subjects"]:
            raise PrepareError(f"{a['label']} wants a concept. From a selection, Analyze this passage comes first — "
                               "or choose a concept you already keep.", 409,
                               choices=[{"id": "analyze.decompose", "label": BY_ID["analyze.decompose"]["label"]}])
        if kind == "document" and "selection" in a["subjects"]:
            raise PrepareError(f"{a['label']} works on words you select — select them first"
                               + (", or choose a concept you already keep" if "concept" in a["subjects"] else "") + ".", 409)
        raise PrepareError(f"{a['label']} does not take a {kind}; it takes: {', '.join(a['subjects'])}", 409)
    rd = readiness(a, server_gateway)
    snap = None
    if kind in ("document", "selection", "description", "word"):
        text = str((subject or {}).get("text") or "")
        if not text.strip():
            raise PrepareError("nothing is selected or written yet", 400)
        rng = (subject or {}).get("range")
        snap = snapshots.make(kind=kind, text=text, doc_id=str((subject or {}).get("doc_id") or ""),
                              revision=(subject or {}).get("revision"), seq=(subject or {}).get("seq"),
                              range_=rng if isinstance(rng, dict) else None,
                              units=str((subject or {}).get("units") or "codepoint"),
                              title=str((subject or {}).get("title") or ""),
                              editor_session=str((subject or {}).get("editor_session") or ""))
        snapshots.write(snap)
    elif kind == "concept":
        c = (subject or {}).get("concept") or {}
        if not str(c.get("definition") or "").strip():
            raise PrepareError("a concept needs its definition; a title alone is a handle, not a concept", 400)
        snap = snapshots.make(kind="concept", text=str(c.get("definition") or ""), title=str(c.get("title") or ""))
        snap["concept"] = {"title": str(c.get("title") or "")[:200], "definition": str(c.get("definition") or ""),
                           "concept_id": str(c.get("concept_id") or "")[:64], "plain_gloss": str(c.get("plain_gloss") or "")}
        snapshots.write(snap)
    # what leaves, said from the registry and the snapshot, never from the client
    disclosure = {
        "scope": snapshots.summary(snap) if snap else {"kind": "none"},
        "leaves_this_machine": {"recipient": a["outbound"]["recipient"], "fields": a["outbound"]["fields"]},
        "calls": a["calls"],
        "lane": rd.get("lane") or {},
        "cost": ("none — the mock lane makes no provider request" if (rd.get("lane") or {}).get("lane") == "mock"
                 else ("unknown until it runs; the record will say" if a["provider"] != "none" else "none")),
        "available": rd["available"], "reason": rd["reason"],
    }
    extra = {}
    if a["mode"] == "refract":
        extra["entry"] = "selection" if kind == "selection" else ("description" if kind == "description" else "concept")
        extra["only_languages"] = [str(x)[:40] for x in ((inputs or {}).get("only_languages") or [])][:6]
    if a["mode"] == "deep":
        g = str((inputs or {}).get("gesture") or "trial")
        extra["gesture"] = g if g in ("trial", "interpret") else "trial"
    if a["id"] == "feedback.readers":
        extra["scope"] = "selection" if kind == "selection" else "draft"
    rec = {"prepared_id": "", "action_id": a["id"], "label": a["label"], "mode": a["mode"], "kind": a["kind"],
           "subject_kind": kind, "snapshot_id": snap["snapshot_id"] if snap else None,
           "inputs": extra, "disclosure": disclosure, "prepared_at": _now(), "registry_version": REGISTRY_VERSION}
    rec["prepared_id"] = "prep_" + hashlib.sha256(json.dumps(rec, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]
    d = _proposals_dir()
    d.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix=".prep_", dir=str(d))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        json.dump(rec, f, ensure_ascii=False, sort_keys=True)
        f.flush()
        os.fsync(f.fileno())
    os.replace(tmp, d / f"{rec['prepared_id']}.json")
    return rec


def load_prepared(prepared_id: str) -> dict | None:
    if not prepared_id or "/" in prepared_id or not prepared_id.startswith("prep_"):
        return None
    try:
        rec = json.loads((_proposals_dir() / f"{prepared_id}.json").read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    body = dict(rec)
    pid = body.pop("prepared_id", "")
    body["prepared_id"] = ""
    want = "prep_" + hashlib.sha256(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()[:20]
    if pid != want:
        return None
    return rec


def job_payload(prepared: dict) -> dict:
    """The exact /api/jobs body a Start sends, built from the frozen
    proposal and its snapshot — never from the client's request. The text
    is the snapshot's text; the mode is the registry's."""
    a = BY_ID[prepared["action_id"]]
    snap = snapshots.load(prepared["snapshot_id"]) if prepared.get("snapshot_id") else None
    if snap is None or not snapshots.verify(snap):
        raise PrepareError("the proposal's snapshot is missing or does not verify; prepare again", 409)
    mode = a["mode"]
    payload = {"mode": mode, "provenance": "typed" if snap["kind"] in ("document", "selection") else "door"}
    if mode in ("sprout", "archetype", "recheck", "revise"):
        payload["original"] = dict(snap.get("concept") or {})
    elif mode == "refract":
        entry = prepared["inputs"].get("entry", "concept")
        payload["entry"] = entry
        if entry == "selection":
            payload["passage"] = snap["text"]
            payload["original"] = {"title": "", "definition": "", "plain_gloss": ""}
        elif entry == "description":
            payload["original"] = {"title": "", "definition": snap["text"], "plain_gloss": ""}
        else:
            payload["original"] = dict(snap.get("concept") or {})
        if prepared["inputs"].get("only_languages"):
            payload["only_languages"] = prepared["inputs"]["only_languages"]
    elif mode == "verify":
        payload["candidate"] = dict(snap.get("candidate") or {})
    else:
        payload["input_text"] = snap["text"]
        if mode == "deep":
            payload["gesture"] = prepared["inputs"].get("gesture", "trial")
    return payload
