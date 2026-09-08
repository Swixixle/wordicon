"""Map · focus — the served projection behind one concept's ring.

From the concept in hand, show where it came from, what it touched, who or
what drew each road, and exactly what the record can and cannot establish.

Four things are kept apart on every road, and none may stand in for another:
  provenance basis — what record produced or reconstructs the road;
  evidence support — whether an admitted source and exact span support a
                     claim (no road carries this today; the field is explicit);
  review standing  — what a reviewing stage said, in a named run;
  owner standing   — what the owner explicitly ruled or declared.
A receipt proves an event was recorded, not that the relationship is true.

ISSUERS. A road recorded with an origin (block 104) says "recorded · …". A
road from before origins were recorded may say "derived · …" only on
mechanically exclusive custody evidence, never from its relation's name:
  derived from snapshot  — the run's own snapshot reproduces the road's EXACT
                           identity (relation, both keys, run trace) through
                           the same node constructors the writers use;
  derived by writer invariant — the row was created inside the tracked
                           history, throughout which the relation had exactly
                           one writing function (audited per commit);
  issuer not recorded    — neither holds.
Every derived label carries its rule, its basis and a derivation version.
Derivation happens here, in the served view; edges.jsonl is never rewritten.

Read-only. No model. No network. No write. Vault untouched.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import wordicon_cli as cli  # noqa: E402

DERIVATION_VERSION = "issuer-derivation/1"

# The first tracked commit (caf07c9, 2026-08-29T23:43:11Z). Across every
# tracked commit since, each relation below has had exactly one writing
# function; the suite re-audits this against the repository when a .git is
# present. Rows created BEFORE this instant have no repository history to
# vouch for their writer and cannot qualify by invariant.
TRACKED_SINCE = "2026-08-29T23:43:11+00:00"

# The writer invariant, as audited: relation → (writer function, the origin
# that writer stamps today, the issuer class that origin means). The class
# is what the WRITER is, established by the audit; it is applied only to rows
# the invariant covers, never to a row merely because of its relation name.
WRITER_INVARIANT = {
    "produced":        ("run",           "mechanical",     "pipeline"),
    "forged_as":       ("run_decompose/run_deep", "mechanical", "pipeline"),
    "decomposed_into": ("run_decompose/run_deep", "model_proposed", "model stage (dissect)"),
    "renamed_as":      ("run_revise",    "mechanical",     "pipeline"),
    "compressed_as":   ("run_revise",    "mechanical",     "pipeline"),
    "reworked_into":   ("run_revise",    "mechanical",     "pipeline"),
    "continued_from":  ("run_sprout",    "mechanical",     "pipeline"),
    "parallels":       ("run_sprout",    "model_proposed", "model stage (sprout)"),
    "translated_as":   ("run_refract",   "model_proposed", "model stage (refract)"),
    "english_fossil":  ("run_refract",   "model_proposed", "model stage (refract)"),
    "archetype_of":    ("run_archetype", "model_proposed", "model stage (archetype)"),
    "declared_road":   ("declare_road",  "owner_declared", "owner declaration"),
}

ORIGIN_WORDS = {"mechanical": "pipeline", "model_proposed": "model proposal",
                "owner_declared": "owner declaration", "imported": "import"}

# what a reviewing stage is called, per relation, when a verdict rides on it
REVIEW_BY = {"produced": "Friction at forge", "forged_as": "Friction at forge",
             "reworked_into": "Friction at revise", "renamed_as": "Friction at revise",
             "compressed_as": "Friction at revise", "parallels": "sprout review",
             "translated_as": "refract review", "english_fossil": "refract review",
             "archetype_of": "archetype stage", "decomposed_into": "", "continued_from": "",
             "declared_road": ""}

GROUP_THRESHOLD = 12
ORDER_RULE = "roads with a recorded creation time first, oldest first, then by edge id; roads with no recorded time after them, by edge id"

_REVISE_RX = re.compile(r"^(revise|wordify|reconsider) of '([^']+)'")
DIRECT_MODES = ("forge", "crack", "riff", "play")      # run() — the owner's text is the input
COMPOSITE_MODES = ("deep", "decompose")                # the composite lists its components


def _identity(rel: str, src: dict, tgt: dict, run_trace_id: str) -> tuple:
    return (rel, (src or {}).get("key", ""), (tgt or {}).get("key", ""), run_trace_id or "")


def _recorded_key(endp: dict) -> str:
    """The key the row was written against. The served map resolves a legacy
    title key onto today's concept box for display (build_overworld's
    concept-first post-pass) and keeps the original as recorded_key; the
    exact identity a snapshot must reproduce is the row AS RECORDED."""
    endp = endp or {}
    return endp.get("recorded_key") or endp.get("key", "")


def recorded_identity(edge: dict) -> tuple:
    return (edge.get("rel") or "", _recorded_key(edge.get("source")), _recorded_key(edge.get("target")),
            edge.get("run_trace_id") or "")


# ---------------------------------------------------------------------------
# exact edge identities, reproduced from a snapshot
# ---------------------------------------------------------------------------

def edge_specs_from_snapshot(snap: dict, by_trace: "dict[str, dict] | None" = None) -> "list[dict]":
    """Every road the CURRENT writers would have recorded for this snapshot,
    with its exact identity, built through the same node constructors the
    writers use. `by_trace` supplies component snapshots for composites.
    Anything the snapshot does not hold (an original's concept id an older
    revise snapshot never stored) is not guessed: the road is simply not
    reproduced, and a legacy row that needs it falls to the next rule."""
    if not isinstance(snap, dict):
        return []
    by_trace = by_trace or {}
    mode = snap.get("mode") or ""
    trace = snap.get("trace_id") or ""
    out: "list[dict]" = []

    def spec(rel, src, tgt, issuer, run_trace=trace):
        out.append({"rel": rel, "source": src, "target": tgt, "run_trace_id": run_trace,
                    "identity": _identity(rel, src, tgt, run_trace), "issuer": issuer})

    if mode in DIRECT_MODES:
        run_node = cli._node("run", trace, (snap.get("input_text") or "")[:80])
        for c in snap.get("candidates") or []:
            bff = c.get("bff") or {}
            title = bff.get("title") or c.get("title") or ""
            if not title:
                continue
            spec("produced", run_node, cli.node_concept(bff.get("concept_id", "") or "", title), "pipeline")
        return out

    if mode == "revise":
        m = _REVISE_RX.match(snap.get("input_text") or "")
        src_meta = snap.get("source") or {}
        orig_title = src_meta.get("title") or (m.group(2) if m else "")
        if not orig_title:
            return out
        steered = bool(src_meta.get("steered")) if "steered" in src_meta else bool(m and m.group(1) == "reconsider")
        wordify = bool(src_meta.get("wordify")) if "wordify" in src_meta else bool(m and m.group(1) == "wordify")
        for c in snap.get("candidates") or []:
            bff = c.get("bff") or {}
            title = bff.get("title") or c.get("title") or ""
            if not title:
                continue
            if steered:
                # the writer keys the original by its concept id when it had
                # one; an older snapshot never stored that id, and then the
                # road is not reproducible from the snapshot — by design
                if "concept_id" not in src_meta:
                    continue
                spec("reworked_into", cli.node_concept(src_meta.get("concept_id") or "", orig_title),
                     cli.node_concept(bff.get("concept_id", "") or "", title), "pipeline")
            else:
                spec("compressed_as" if wordify else "renamed_as",
                     cli.node_word(orig_title), cli.node_word(title), "pipeline")
        return out

    if mode == "sprout":
        src_meta = snap.get("source") or {}
        title = src_meta.get("title") or ""
        seed = cli.node_concept(src_meta.get("concept_id") or "", title) if "concept_id" in src_meta \
            else cli.node_concept("", title)   # older snapshots: the writer keyed by title when the candidate had no id
        for t in snap.get("threads") or []:
            if t.get("anchor_name"):
                spec("parallels", seed, cli.node_external(t["anchor_name"], t.get("culture_or_work", "")),
                     "model stage (sprout)")
        if snap.get("parent_trace_id"):
            spec("continued_from", cli._node("run", snap["parent_trace_id"], ""),
                 cli._node("run", trace, title), "pipeline")
        return out

    if mode == "refract":
        src_meta = snap.get("source") or {}
        title = src_meta.get("title") or ""
        seed = cli.node_concept(src_meta.get("concept_id") or "", title) if "concept_id" in src_meta \
            else cli.node_concept("", title)
        for r in snap.get("refractions") or []:
            term = (r.get("romanization") or r.get("term") or "").strip()
            if term:
                spec("translated_as", seed, cli.node_translation(r.get("language", ""), term),
                     "model stage (refract)")
        fossil = (snap.get("english_fossil") or "").strip()
        if fossil:
            spec("english_fossil", seed, cli.node_external(fossil[:60], "English etymology"), "model stage (refract)")
        return out

    if mode == "archetype":
        src_meta = snap.get("source") or {}
        title = src_meta.get("title") or ""
        seed = cli.node_concept(src_meta.get("concept_id") or "", title) if "concept_id" in src_meta \
            else cli.node_concept("", title)
        fig = ((snap.get("archetype") or {}).get("figure") or "")[:60] or "unnamed figure"
        spec("archetype_of", seed, cli.node_external(fig, "archetype"), "model stage (archetype)")
        return out

    if mode in COMPOSITE_MODES:
        text = snap.get("input_text") or ""
        if not text:
            return out
        src = cli.node_source(text)
        for c in snap.get("components") or []:
            label, ctrace = c.get("label") or "", c.get("trace_id") or ""
            if not label or not ctrace or c.get("failed"):
                continue
            cmp_node = cli.node_component(src["key"], label)
            spec("decomposed_into", src, cmp_node, "model stage (dissect)", run_trace=ctrace)
            comp = by_trace.get(ctrace) or {}
            for cand in comp.get("candidates") or []:
                bff = cand.get("bff") or {}
                title = bff.get("title") or cand.get("title") or ""
                if title:
                    spec("forged_as", cmp_node, cli.node_concept(bff.get("concept_id", "") or "", title),
                         "pipeline", run_trace=ctrace)
        return out
    return out


# ---------------------------------------------------------------------------
# the issuer of one road
# ---------------------------------------------------------------------------

class SnapshotIndex:
    """Snapshots by trace, read once. Composites are also indexed by the
    component traces they list, so a road keyed to a component run can be
    tested against the composite that holds the decomposition. A component
    trace may be listed by more than one composite (trace ids are the hash
    of the input and the second, and a repeated component text within one
    second repeats the id); every composite listing it is a candidate basis,
    and the exact identity still has to be reproduced by one of them."""

    def __init__(self, results_dir: "Path | None" = None):
        self.dir = Path(results_dir or cli.RESULTS_DIR)
        self.by_trace: "dict[str, dict]" = {}
        self.composites_of: "dict[str, list[str]]" = {}
        self._specs: "dict[str, set]" = {}
        if self.dir.exists():
            for p in sorted(self.dir.glob("*.json")):
                try:
                    d = json.loads(p.read_text(encoding="utf-8"))
                except (json.JSONDecodeError, OSError, UnicodeDecodeError):
                    continue
                if isinstance(d, dict) and d.get("trace_id"):
                    self.by_trace[d["trace_id"]] = d
        for t, d in sorted(self.by_trace.items()):
            if d.get("mode") in ("deep", "decompose"):
                for c in d.get("components") or []:
                    if c.get("trace_id"):
                        self.composites_of.setdefault(c["trace_id"], []).append(t)

    def _bases(self, trace: str) -> "list[tuple[str, dict]]":
        """(basis trace, snapshot) pairs that may reproduce a road keyed to
        `trace`: its own snapshot, then every composite listing it."""
        out = []
        snap = self.by_trace.get(trace)
        if snap:
            out.append((trace, snap))
        for comp in self.composites_of.get(trace) or []:
            if comp in self.by_trace:
                out.append((comp, self.by_trace[comp]))
        return out

    def specs_for(self, trace: str) -> "set":
        """Exact identities reproducible from the snapshot for `trace`, plus
        from every composite that lists `trace` as a component."""
        if trace in self._specs:
            return self._specs[trace]
        ids: set = set()
        for _basis, snap in self._bases(trace):
            ids |= {s["identity"] for s in edge_specs_from_snapshot(snap, self.by_trace)}
        self._specs[trace] = ids
        return ids

    def reproduce(self, trace: str, ident: tuple) -> "tuple[str, str] | None":
        """(issuer class, basis trace) when the snapshot for `trace` — or a
        composite listing it — reproduces this exact identity; else None."""
        for basis, snap in self._bases(trace):
            for s in edge_specs_from_snapshot(snap, self.by_trace):
                if s["identity"] == ident:
                    return s["issuer"], basis
        return None

    def has(self, trace: str) -> bool:
        return trace in self.by_trace


def derive_issuer(edge: dict, index: SnapshotIndex, tracked_since: str = TRACKED_SINCE) -> dict:
    """{label, recorded, issuer_class, derivation} for one road."""
    origin = edge.get("origin") if edge.get("origin") in cli.EDGE_ORIGINS else "legacy_unknown"
    rel = edge.get("rel") or ""
    if edge.get("synthesized"):
        # Reconstructed by build_overworld directly from a named snapshot —
        # the ruling's second condition: the derivation names that snapshot.
        # build_overworld reads the snapshot's own candidates, threads and
        # refractions to draw these, so the snapshot is the basis; the class
        # is the operation's, from the writer table. A reconstruction whose
        # snapshot is gone has no basis to name.
        trace = edge.get("run_trace_id") or ""
        inv = WRITER_INVARIANT.get(rel)
        if inv and index.has(trace):
            cls = inv[2]
            return {"label": f"derived from snapshot · {cls}", "recorded": False, "issuer_class": cls,
                    "derivation": {"rule": "reconstruction", "basis": trace, "version": DERIVATION_VERSION}}
        return {"label": "issuer not recorded", "recorded": False, "issuer_class": "",
                "derivation": {"rule": "reconstruction", "basis": trace, "version": DERIVATION_VERSION,
                               "note": "reconstructed, but no snapshot remains to name as its basis"}}
    if origin != "legacy_unknown":
        word = ORIGIN_WORDS.get(origin, origin)
        return {"label": f"recorded · {word}", "recorded": True, "issuer_class": word, "derivation": None}
    # a legacy row: rule 1, the snapshot reproduces the exact identity of the
    # row as recorded (a display resolution of its endpoint is not the row)
    trace = edge.get("run_trace_id") or ""
    ident = recorded_identity(edge)
    hit = index.reproduce(trace, ident)
    if hit:
        cls, basis = hit
        return {"label": f"derived from snapshot · {cls}", "recorded": False, "issuer_class": cls,
                "derivation": {"rule": "snapshot", "basis": basis, "version": DERIVATION_VERSION}}
    # rule 3, the writer invariant over the tracked history
    at = edge.get("created_at") or ""
    inv = WRITER_INVARIANT.get(rel)
    if inv and at and at >= tracked_since:
        fn, _origin, cls = inv
        return {"label": f"derived by writer invariant · {cls}", "recorded": False, "issuer_class": cls,
                "derivation": {"rule": "writer-invariant", "basis": f"{fn} since {tracked_since}",
                               "version": DERIVATION_VERSION}}
    return {"label": "issuer not recorded", "recorded": False, "issuer_class": "", "derivation": None}


# ---------------------------------------------------------------------------
# provenance basis — where the displayed road came from, and whether it resolves
# ---------------------------------------------------------------------------

def resolve_provenance(edge: dict, receipts_dir: "Path | None" = None, results_dir: "Path | None" = None) -> dict:
    rd = Path(receipts_dir or cli.RECEIPTS_DIR)
    sd = Path(results_dir or cli.RESULTS_DIR)
    trace = edge.get("run_trace_id") or ""
    run_snapshot = bool(trace) and (sd / f"{trace}.json").exists()
    if edge.get("synthesized"):
        return {"kind": "reconstruction", "id": trace, "resolves": run_snapshot, "run_snapshot": trace if run_snapshot else None,
                "label": f"reconstructed from snapshot {trace}" + ("" if run_snapshot else " · snapshot not found")}
    pr = edge.get("producer") or {}
    kind, pid = pr.get("kind") or "", pr.get("id") or ""
    if kind == "receipt":
        found = (rd / f"{pid}.json").exists()
        label = pid if found else ("producer receipt cited · file not found" + (" · run snapshot available" if run_snapshot else ""))
        return {"kind": "receipt", "id": pid, "resolves": found, "run_snapshot": trace if run_snapshot else None,
                "stage": pr.get("stage") or "", "label": label}
    if kind == "result_snapshot":
        found = (sd / f"{pid}.json").exists()
        return {"kind": "result_snapshot", "id": pid, "resolves": found, "run_snapshot": trace if run_snapshot else None,
                "stage": pr.get("stage") or "",
                "label": pid if found else ("producer snapshot cited · file not found")}
    if kind in ("owner_declaration", "judgment", "import"):
        return {"kind": kind, "id": pid, "resolves": True, "run_snapshot": None, "label": pid,
                "note": "an event id; it has no file of its own"}
    return {"kind": "none", "id": "", "resolves": False, "run_snapshot": trace if run_snapshot else None,
            "label": "no citation recorded" + (" · run snapshot available" if run_snapshot else "")}


# ---------------------------------------------------------------------------
# the ring
# ---------------------------------------------------------------------------

def _sort_key(e: dict):
    at = e.get("created_at") or ""
    return (0 if at else 1, at, e.get("edge_id") or "")


def _identity_words(key: str) -> str:
    key = str(key or "")
    return "legacy title-keyed" if key.startswith("word:") else ("concept-keyed" if key.startswith("concept:") else "keyed by kind")


def _resolution(endp: dict) -> "dict | None":
    """When the served map moved this endpoint from the key the row was
    recorded against onto today's box: what was recorded, and by which rule
    it was resolved. Disclosed, never silent — a title-keyed road drawn on
    a concept box is a resolution, not a fact the row holds."""
    endp = endp or {}
    if endp.get("recorded_key") and endp.get("recorded_key") != endp.get("key"):
        return {"recorded_key": endp["recorded_key"], "resolved_by": endp.get("resolved_by") or "served-map resolution",
                "recorded_identity": _identity_words(endp["recorded_key"])}
    return None


def _dispute_by_run(d: dict) -> dict:
    """The served map's dispute, counted by RUN. build_overworld tallies
    roads, and a sprout from a concept-keyed candidate is drawn twice there
    (once recorded from the concept box, once reconstructed from the
    snapshot's title-keyed seed), so a road tally counts one review twice.
    One run reviewed the target once; that is the population named."""
    by_run: "dict[str, dict]" = {}
    for e in d.get("entries") or []:
        t = e.get("run_trace_id") or ""
        if t not in by_run:
            by_run[t] = {"run_trace_id": t, "verdict": e.get("verdict", ""), "source_label": e.get("source_label", "")}
    tally: "dict[str, int]" = {}
    for e in by_run.values():
        tally[e["verdict"]] = tally.get(e["verdict"], 0) + 1
    return {"rel": d.get("rel", ""), "target_key": d.get("target_key", ""), "tally": tally,
            "population": "runs whose review reached this target", "entries": list(by_run.values())[:20],
            "road_tally": d.get("tally", {})}


def _road(edge: dict, focus_key: str, index: SnapshotIndex, disputes: list) -> dict:
    out_dir = (edge.get("source") or {}).get("key") == focus_key
    other = edge.get("target") if out_dir else edge.get("source")
    this_end = edge.get("source") if out_dir else edge.get("target")
    rel = edge.get("rel") or ""
    verdict = edge.get("verdict") or ""
    at = edge.get("created_at") or ""
    dispute = next((d for d in disputes if d.get("rel") == rel and d.get("target_key") == (edge.get("target") or {}).get("key")), None)
    owner = None
    if rel == "declared_road":
        detail = edge.get("detail") or ""
        owner = {"declared": True, "verb": detail.split(" — ")[0], "note": detail.split(" — ", 1)[1] if " — " in detail else "",
                 "declaration_id": edge.get("declaration_id") or "", "proposed_by": edge.get("proposed_by") or "owner"}
    return {
        "edge_id": edge.get("edge_id") or "", "rel": rel,
        "rel_words": cli.TRAIL_REL_WORDS.get(rel, rel.replace("_", " ")),
        "direction": "out" if out_dir else "in",
        "run_trace_id": edge.get("run_trace_id") or "",
        "created_at": at, "time_recorded": bool(at),
        "detail": edge.get("detail") or "",
        "other": {"kind": (other or {}).get("kind", ""), "key": (other or {}).get("key", ""),
                  "label": (other or {}).get("label", ""),
                  "identity": _identity_words((other or {}).get("key", "")),
                  "resolution": _resolution(other)},
        "this_end": {"resolution": _resolution(this_end)},
        "issuer": derive_issuer(edge, index),
        "provenance": resolve_provenance(edge),
        "review_standing": ({"verdict": verdict, "by": REVIEW_BY.get(rel) or "a reviewing stage", "population": "this run"}
                            if verdict else None),
        "evidence_support": None,   # explicit: no road carries evidence support today
        "owner_standing": owner,
        "dispute": _dispute_by_run(dispute) if dispute else None,
    }


def _burden(roads: "list[dict]") -> dict:
    b = {"population": "direct roads of this node in the served map", "total": len(roads),
         "declared_by_owner": 0, "pipeline": {"recorded": 0, "derived": 0},
         "model_proposal": {"recorded": 0, "derived": 0}, "issuer_not_recorded": 0,
         "reconstructed": 0, "citation_not_found": 0, "disputes": 0,
         "evidence_support": {"population": "Library claims anchored to this concept", "count": 0}}
    for r in roads:
        iss = r["issuer"]; cls = iss.get("issuer_class") or ""
        if r["owner_standing"] and r["owner_standing"].get("declared"):
            b["declared_by_owner"] += 1
        elif iss["label"] == "issuer not recorded":
            b["issuer_not_recorded"] += 1
        elif cls.startswith("model"):
            b["model_proposal"]["recorded" if iss["recorded"] else "derived"] += 1
        elif cls == "pipeline":
            b["pipeline"]["recorded" if iss["recorded"] else "derived"] += 1
        if r["provenance"]["kind"] == "reconstruction":
            b["reconstructed"] += 1
        if r["provenance"]["kind"] in ("receipt", "result_snapshot") and not r["provenance"]["resolves"]:
            b["citation_not_found"] += 1
        if r["dispute"]:
            b["disputes"] += 1
    return b


def _group(roads: "list[dict]") -> "list[dict]":
    groups: "dict[tuple, dict]" = {}
    for r in roads:
        k = (r["rel"], r["issuer"]["label"])
        g = groups.setdefault(k, {"rel": r["rel"], "rel_words": r["rel_words"], "issuer_label": r["issuer"]["label"],
                                  "count": 0, "edge_ids": [], "open": False})
        g["count"] += 1
        g["edge_ids"].append(r["edge_id"])
    return sorted(groups.values(), key=lambda g: (g["rel"], g["issuer_label"]))


def _node_facts(key: str, ow: dict) -> "dict | None":
    items = [(r, it) for r in ow.get("runs") or [] for it in r.get("items") or [] if it.get("key") == key]
    if not items:
        # a node that exists only as an edge endpoint (a run, or an external
        # never boxed): still a place, with what the edges say about it
        for e in ow.get("edges") or []:
            for n in (e.get("source"), e.get("target")):
                if isinstance(n, dict) and n.get("key") == key:
                    return {"kind": n.get("kind", ""), "key": key, "label": n.get("label", ""), "display_label": n.get("label", ""),
                            "names": [], "concept_id": n.get("concept_id", ""), "short_def": "",
                            "identity": _identity_words(key),
                            "owner_standing": None, "boxed": False}
        return None
    items.sort(key=lambda ri: ri[0].get("created_at") or "")
    first_run, first = items[0]
    latest_run, latest = items[-1]
    history = [{"run_trace_id": r.get("trace_id", ""), "at": r.get("created_at", ""), "judgment": it.get("judgment", "")}
               for r, it in items if it.get("judgment")]
    owner = None
    if history:
        owner = {"judgment": history[-1]["judgment"], "ruled_in": history[-1]["run_trace_id"], "history": history}
    # The name on the box: the primary name the owner recorded when there is
    # one; otherwise the label the place was FIRST boxed under. Revise
    # variants share the original's box (the concept-first geometry) and
    # their titles ride along as other written forms, never as the name.
    primary = next((it.get("display_label") for _r, it in items if it.get("display_label")), "")
    forms: "list[str]" = []
    for _r, it in items:
        for n in [it.get("label", "")] + list(it.get("names") or []):
            if n and n not in forms:
                forms.append(n)
    # Other places carrying this same title — a concept-keyed box and its
    # title-keyed twin from before ids, or two concepts that share a word —
    # are named here with their identities, and never merged.
    norm = cli._norm_title(first.get("label", ""))
    same_title = []
    seen_same = set()
    for r in ow.get("runs") or []:
        for it in r.get("items") or []:
            k2 = it.get("key")
            if k2 and k2 != key and k2 not in seen_same and cli._norm_title(it.get("label", "")) == norm:
                seen_same.add(k2)
                same_title.append({"key": k2, "kind": it.get("kind", ""), "identity": _identity_words(k2),
                                   "short_def": it.get("short_def", ""), "concept_id": it.get("concept_id", "")})
    return {"kind": first.get("kind", ""), "key": key, "label": first.get("label", ""),
            "display_label": primary or first.get("label", ""),
            "same_title": same_title,
            "named_by": "recorded primary name" if primary else f"the run that first boxed it ({first_run.get('trace_id', '')})",
            "names": forms, "concept_id": latest.get("concept_id", "") or first.get("concept_id", ""),
            "short_def": first.get("short_def", "") or latest.get("short_def", ""),
            "identity": _identity_words(key),
            "shared_title": any(it.get("shared_title") for _r, it in items),
            "owner_standing": owner, "boxed": True,
            "appears_in_runs": len({r.get("trace_id") for r, _ in items})}


def ring(key: str, ow: dict, index: SnapshotIndex, filters: "dict | None" = None) -> dict:
    disputes = ow.get("disputes") or []
    edges = [e for e in ow.get("edges") or []
             if (e.get("source") or {}).get("key") == key or (e.get("target") or {}).get("key") == key]
    roads = [_road(e, key, index, disputes) for e in edges]
    # the facets are counted over the WHOLE ring, before any filter, so a
    # filter can be chosen and the choice can be undone from what is shown
    facets: "dict[str, dict[str, int]]" = {"rel": {}, "issuer": {}, "standing": {}}
    rel_words: "dict[str, str]" = {}
    for r in roads:
        facets["rel"][r["rel"]] = facets["rel"].get(r["rel"], 0) + 1
        rel_words[r["rel"]] = r["rel_words"]
        facets["issuer"][r["issuer"]["label"]] = facets["issuer"].get(r["issuer"]["label"], 0) + 1
        if r["review_standing"]:
            vd = r["review_standing"]["verdict"]
            facets["standing"][vd] = facets["standing"].get(vd, 0) + 1
    whole = len(roads)
    f = {k: v for k, v in (filters or {}).items() if v}
    if f.get("rel"):
        roads = [r for r in roads if r["rel"] == f["rel"]]
    if f.get("issuer"):
        roads = [r for r in roads if r["issuer"]["label"] == f["issuer"]]
    if f.get("standing"):
        roads = [r for r in roads if (r["review_standing"] or {}).get("verdict", "") == f["standing"]]
    roads.sort(key=_sort_key)
    total = len(roads)
    bounded = total >= GROUP_THRESHOLD
    burden = _burden(roads)
    if f:
        burden["population"] = ("direct roads of this node in the served map matching the filters "
                                + ", ".join(f"{k}={v}" for k, v in sorted(f.items())))
    return {"roads": roads, "burden": burden,
            "groups": _group(roads) if bounded else [],
            "facets": {k: dict(sorted(v.items())) for k, v in facets.items()}, "facets_total": whole,
            "rel_words": rel_words,
            "presentation": {"degree": total, "bounded": bounded, "threshold": GROUP_THRESHOLD, "order": ORDER_RULE,
                             "time_unavailable": sum(1 for r in roads if not r["time_recorded"])}}


def focus_view(key: str, expand: str = "", filters: "dict | None" = None, ow: "dict | None" = None) -> dict:
    """The whole response for one concept, from the served map. Read-only."""
    ow = ow or cli.build_overworld()
    index = SnapshotIndex()
    node = _node_facts(key, ow)
    if node is None:
        return {"error": "no place on the map has that key", "key": key}
    r = ring(key, ow, index, filters)
    expanded = None
    if expand:
        road = next((x for x in r["roads"] if x["edge_id"] == expand), None)
        if road:
            other = road["other"]["key"]
            r2 = ring(other, ow, index, None)
            expanded = {"from_edge_id": expand, "other": _node_facts(other, ow), **r2}
    return {"focus": node, **r, "expanded": expanded, "filters": dict(filters or {}),
            "derivation_version": DERIVATION_VERSION, "tracked_since": TRACKED_SINCE,
            "standing_rule": ("provenance basis, evidence support, review standing and owner standing are "
                              "separate fields; none stands in for another; a receipt proves an event was "
                              "recorded, not that the relationship is true"),
            "limits": list(ow.get("limits") or []) + [
                "Issuers marked derived rest on the snapshot reproducing the road's exact identity, or on the "
                "writer invariant of the tracked history; never on the relation's name.",
                "No road carries evidence support today; the Library's crossings are where a claim's support lives."]}


def issuer_census(edges: "list[dict] | None" = None) -> dict:
    """Counts by issuer label over the served map — for the census, never the
    constitution. Every count names its population."""
    ow = cli.build_overworld()
    index = SnapshotIndex()
    counts: "dict[str, int]" = {}
    for e in (edges if edges is not None else ow.get("edges") or []):
        lab = derive_issuer(e, index)["label"]
        counts[lab] = counts.get(lab, 0) + 1
    return {"population": "every road in the served map (recorded and reconstructed)",
            "counts": dict(sorted(counts.items(), key=lambda kv: -kv[1])),
            "derivation_version": DERIVATION_VERSION, "tracked_since": TRACKED_SINCE}


# ---------------------------------------------------------------------------
# the picker — every place on the served map, so a focus is chosen, never
# assumed
# ---------------------------------------------------------------------------

def places(ow: "dict | None" = None) -> dict:
    """Every place a focus can be put on: each distinct key among the served
    runs' items (concepts and words, sources, components, foreign terms,
    externals) with its kind, its identity and the count of its direct roads.
    Ordered by label, then key — nothing is ranked by degree, recency or
    judgment; the count is there to be read, not to sort by."""
    ow = ow or cli.build_overworld()
    degree: "dict[str, int]" = {}
    for e in ow.get("edges") or []:
        for n in (e.get("source"), e.get("target")):
            if isinstance(n, dict) and n.get("key"):
                degree[n["key"]] = degree.get(n["key"], 0) + 1
    seen: "dict[str, dict]" = {}
    for r in ow.get("runs") or []:
        for it in r.get("items") or []:
            k = it.get("key")
            if not k:
                continue
            p = seen.get(k)
            if p is None:
                p = seen[k] = {"key": k, "kind": it.get("kind", ""), "label": it.get("label", ""),
                               "display_label": it.get("display_label") or it.get("label", ""),
                               "identity": _identity_words(k), "concept_id": it.get("concept_id", ""),
                               "short_def": it.get("short_def", ""),
                               "shared_title": bool(it.get("shared_title")), "degree": degree.get(k, 0),
                               "runs": 0}
            p["runs"] += 1
            if it.get("display_label"):
                p["display_label"] = it["display_label"]
            if it.get("short_def") and not p["short_def"]:
                p["short_def"] = it["short_def"]
            if it.get("shared_title"):
                p["shared_title"] = True
    out = sorted(seen.values(), key=lambda p: (cli._norm_title(p["display_label"] or p["label"]), p["key"]))
    return {"population": "every distinct key among the served runs' items",
            "count": len(out), "places": out,
            "order": "by label, then key — not by degree, recency or judgment"}


# ---------------------------------------------------------------------------
# the census, from the command line — read-only, every count with its population
# ---------------------------------------------------------------------------

def census() -> dict:
    """The served map counted under the exact derivation rule: issuers,
    provenance resolution, degree. Read-only; the store is hashed before and
    after so the report itself proves nothing was written. For the census
    document and the changelog — never for the constitution."""
    import hashlib
    from datetime import datetime, timezone

    def store_hash() -> str:
        h = hashlib.sha256()
        root = Path(cli.LOCAL_STATE)
        for f in sorted(p for p in root.rglob("*") if p.is_file()):
            h.update(str(f.relative_to(root)).encode()); h.update(f.read_bytes())
        return h.hexdigest()

    before = store_hash()
    ow = cli.build_overworld()
    index = SnapshotIndex()
    edges = ow.get("edges") or []
    raw = cli.load_edges()
    issuers: "dict[str, int]" = {}
    by_rel_legacy: "dict[str, dict[str, int]]" = {}
    prov: "dict[str, int]" = {}
    for e in edges:
        d = derive_issuer(e, index)
        issuers[d["label"]] = issuers.get(d["label"], 0) + 1
        if not e.get("synthesized") and (e.get("origin") not in cli.EDGE_ORIGINS or e.get("origin") == "legacy_unknown"):
            rule = (d.get("derivation") or {}).get("rule") or "none"
            by_rel_legacy.setdefault(e.get("rel", ""), {})
            by_rel_legacy[e["rel"]][rule] = by_rel_legacy[e["rel"]].get(rule, 0) + 1
        p = resolve_provenance(e)
        if p["resolves"]:
            pk = p["kind"] + " · resolves"
        elif p["kind"] == "reconstruction":
            pk = "reconstruction · snapshot not found"
        else:
            pk = p["label"]          # the state, in the words the page uses
        prov[pk] = prov.get(pk, 0) + 1
    degree: "dict[str, int]" = {}
    for e in edges:
        for n in (e.get("source"), e.get("target")):
            if isinstance(n, dict) and n.get("key"):
                degree[n["key"]] = degree.get(n["key"], 0) + 1
    high = sorted(degree.values(), reverse=True)
    after = store_hash()
    legacy_rows = sum(1 for r in raw if r.get("origin") not in cli.EDGE_ORIGINS or r.get("origin") == "legacy_unknown")
    return {
        "date": datetime.now(timezone.utc).replace(microsecond=0).isoformat(),
        "method": "scripts/map_focus.py census: build_overworld() served map, derive_issuer per road under "
                  + DERIVATION_VERSION + " (exact recorded identity against the run's snapshot or a composite listing "
                  "it; writer invariant only for rows created at or after TRACKED_SINCE); resolve_provenance per road",
        "derivation_version": DERIVATION_VERSION, "tracked_since": TRACKED_SINCE,
        "store": str(cli.LOCAL_STATE), "store_hash_before": before, "store_hash_after": after,
        "read_only": before == after,
        "populations": {
            "rows in edges.jsonl": len(raw),
            "rows in edges.jsonl without a recorded origin (legacy)": legacy_rows,
            "roads in the served map (recorded and reconstructed)": len(edges),
            "places (distinct endpoint keys in the served map)": len(degree),
        },
        "issuers (population: roads in the served map)": dict(sorted(issuers.items(), key=lambda kv: -kv[1])),
        "legacy rows by relation and derivation rule (population: rows in edges.jsonl without a recorded origin)":
            {k: dict(sorted(v.items())) for k, v in sorted(by_rel_legacy.items())},
        "provenance (population: roads in the served map)": dict(sorted(prov.items(), key=lambda kv: -kv[1])),
        "degree (population: places in the served map)": {
            "places with 12 or more direct roads": sum(1 for d in high if d >= GROUP_THRESHOLD),
            "highest": high[0] if high else 0,
        },
    }


def rebind_state(root: "str | Path") -> None:
    """Point every store path the CLI holds at another root (the way the
    suite and the journeys' scratch server do) — so the census can be run
    against a store other than the repository's own, read-only."""
    root = Path(root)
    for name in ("JUDGMENTS_LOG", "RECEIPTS_DIR", "RESULTS_DIR", "ACCEPTED_CONCEPTS_PATH", "EDGES_LOG", "WARPS_LOG",
                 "WARP_NOTES_LOG", "BENCH_CORRECTIONS", "CONCEPT_NAMES_LOG", "BENCH_DIR", "INPUTS_LOG", "WAYFINDER_LOG",
                 "DEFINITION_EVENTS_LOG", "ENCOUNTER_SWITCH_LOG", "ENCOUNTERS_LOG", "OPEN_QUESTIONS_LOG", "CARRIES_LOG"):
        if hasattr(cli, name):
            setattr(cli, name, root / Path(str(getattr(cli, name))).name)
    cli.LOCAL_STATE = root


if __name__ == "__main__":
    import argparse
    import os
    ap = argparse.ArgumentParser(description="Map · focus — read-only projections of the served map")
    ap.add_argument("--state", default=os.environ.get("WORDICON_STATE", ""),
                    help="the local_state directory to read (default: the repository's own, or WORDICON_STATE)")
    ap.add_argument("--census", action="store_true", help="count the served map under the exact derivation rule and print JSON")
    ap.add_argument("--focus", default="", help="print the focus view for one key")
    args = ap.parse_args()
    if args.state:
        rebind_state(args.state)
    if args.census:
        print(json.dumps(census(), indent=2, ensure_ascii=False))
    elif args.focus:
        print(json.dumps(focus_view(args.focus), indent=2, ensure_ascii=False))
    else:
        ap.print_help()
