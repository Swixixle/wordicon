#!/usr/bin/env python3
"""One page of decisions from a run that produced two thousand lines.

Reads results already on disk. Makes NO model calls and asks nothing new of
anyone — every line here is a re-reading of a verdict some stage already
reached. If this page and the full run ever disagree, the full run is right
and this is the bug.

    python3 scripts/digest.py --last 15
    python3 scripts/digest.py --since 2026-08-27T04:00
    python3 scripts/digest.py trace_cli_eed0283f33 trace_cli_bc14c3815d

Written as its own script on purpose. A summary that can crash the tool it
summarises is worse than no summary, so it imports nothing from the CLI and
touches no state.
"""
import argparse
import json
import os
import pathlib
import re
import sys

LOCAL_STATE = pathlib.Path(
    os.environ.get("WORDICON_STATE")
    or (pathlib.Path(__file__).resolve().parent.parent / "local_state"))

# ---------------------------------------------------------------------------
# Vocabulary, taken from what is actually written to disk rather than from
# what the prompts ask for — those two drift apart and disk wins.
SUPPORT_CLEARED = ("supported",)
SUPPORT_WEAK = ("partial",)
SUPPORT_FAILED = ("topical", "contradicted")
SUPPORT_NOT_DONE = ("not_run", "undetermined", None, "")
VERDICT_FLAGGED = ("reject", "existing", "contradicted")

# A fidelity note saying one of these beside a passing verdict is the
# mismatch that keeps recurring: the critic writes the objection down in
# prose and then returns "keep" anyway. Detected mechanically, reported as a
# mismatch to look at — never as a verdict of its own. The critic may have
# meant it; the point is that you get to see the pair.
_CONTRADICTION_MARKS = (
    "severe outrun", "outruns", "outrun ", "not licensed", "imported wholesale",
    "invention of scenario", "without ever declaring itself", "not self-declared",
    "in tension with", "explicitly forbids", "violat", "the candidate discards",
    "is not licensed by", "nowhere in the anchor", "never appears in the",
)
# Trap avoided the hard way. The first cut matched "outruns" inside "not a
# claim that outruns the anchor" — a note SAYING THE OPPOSITE — and reported
# a clean candidate as a mismatch. Any mark preceded by a negation inside the
# same clause is dropped. This is the eighth substring trap in this project's
# history and it will not be the last, so the test suite gets the sentence.
_NEGATED = re.compile(
    r"\b(?:not|never|doesn'?t|does not|isn'?t|is not|nothing that|no claim that)\b"
    r"[^.;]{0,40}$", re.I)

_NO_SEARCH = re.compile(
    r"search (?:was |attempts? )?(?:un|not )available|tool[- ](?:call )?limit"
    r"|quota exhausted|limit (?:reached|exceeded)|no live search|search unavailable",
    re.I)


def _load(path):
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def load_runs(trace_ids=None, since=None, last=None):
    """Runs are returned oldest first, with the file size kept: the size is
    the only honest measure of what this page is standing in for."""
    out = []
    for p in sorted((LOCAL_STATE / "results").glob("*.json")):
        d = _load(p)
        if not isinstance(d, dict) or not d.get("trace_id"):
            continue
        d["_bytes"] = p.stat().st_size
        out.append(d)
    if trace_ids:
        want = set(trace_ids)
        out = [d for d in out if d["trace_id"] in want]
    if since:
        out = [d for d in out if (d.get("created_at") or "") >= since]
    out.sort(key=lambda d: d.get("created_at") or "")
    if last:
        out = out[-last:]
    return out


def load_judgments():
    ruled = {}
    p = LOCAL_STATE / "judgments.jsonl"
    if not p.exists():
        return ruled
    for line in p.read_text(encoding="utf-8").splitlines():
        try:
            j = json.loads(line)
        except Exception:
            continue
        t = (j.get("candidate_text") or "").strip()
        if t:
            ruled[t.lower()] = j
    return ruled


def _cand_rows(runs):
    for d in runs:
        for c in (d.get("candidates") or []):
            b = c.get("bff") or {}
            if not b.get("title"):
                continue
            yield {
                "run": d, "title": b["title"],
                "support": ((b.get("claim_support") or {}).get("support")),
                "support_note": ((b.get("claim_support") or {}).get("note") or ""),
                "anchor": ((b.get("anchor_integrity") or {}).get("status")),
                "verdict": ((b.get("friction") or {}).get("verdict") or ""),
                "register": ((b.get("friction") or {}).get("register") or ""),
                "fidelity": ((b.get("friction") or {}).get("source_fidelity_note") or ""),
                "contradicts": bool((b.get("friction") or {}).get("contradicts_anchor")),
                "redundancy": ((b.get("friction") or {}).get("redundancy_note") or ""),
                "gloss": ((b.get("flesh") or {}).get("plain_gloss") or ""),
            }


def digest_runs(runs, ruled):
    cands = list(_cand_rows(runs))
    for c in cands:
        c["ruled"] = ruled.get(c["title"].lower())

    def bucket(c):
        # A compressed word-form carries no anchor of its own — it inherits the
        # parent term's frozen flesh, which is the whole point of the mode. The
        # first cut filed the owner's own accepted coin under "extraction
        # faults" for having no anchor, which is a lie told by a bucket.
        if (c["run"].get("mode") in ("revise", "refract")) and c["support"] in SUPPORT_NOT_DONE:
            return "form"
        if c["support"] in SUPPORT_NOT_DONE or c["anchor"] in ("near", "absent"):
            return "fault"
        if c["verdict"] in VERDICT_FLAGGED:
            return "flagged"
        if c["support"] in SUPPORT_CLEARED:
            return "cleared"
        if c["support"] in SUPPORT_FAILED:
            return "ungrounded"
        return "partial"

    for c in cands:
        c["bucket"] = bucket(c)

    # the mismatch check — mechanical, advisory, and reported as a pair
    mismatches = []
    for c in cands:
        if c["verdict"] != "keep":
            continue
        low = c["fidelity"].lower()
        hit = None
        for m in _CONTRADICTION_MARKS:
            i = low.find(m)
            while i != -1:
                if not _NEGATED.search(low[:i]):
                    hit = m
                    break
                i = low.find(m, i + 1)
            if hit:
                break
        if hit or c["contradicts"]:
            mismatches.append({**c, "mark": hit or "contradicts_anchor flag set"})

    # lateral threads: the same anchor written up more than once
    threads = {}
    no_search = both = 0
    doors, citations = [], 0
    for d in runs:
        for t in (d.get("threads") or []):
            name = (t.get("anchor_name") or "").strip()
            if not name:
                continue
            threads.setdefault(name.lower(), []).append({
                "name": name, "from": (d.get("source") or {}).get("title", ""),
                "verdict": t.get("review_verdict", ""),
                "joint": t.get("joint_check") or {},
                "note": t.get("review_note") or "",
            })
            both += 1
            if _NO_SEARCH.search(t.get("review_note") or ""):
                no_search += 1
        citations += len(d.get("citations") or [])
        for dr in (d.get("doors") or []):
            txt = (dr.get("prompt") or dr.get("text") or dr.get("door") or
                   json.dumps(dr) if isinstance(dr, dict) else str(dr))
            doors.append(txt.strip())

    repeats = []
    for key, group in threads.items():
        if len(group) < 2:
            continue
        joints = [tuple(sorted((g["joint"] or {}).items())) for g in group]
        verdicts = {g["verdict"] for g in group}
        repeats.append({
            "name": group[0]["name"], "n": len(group),
            "parents": [g["from"] for g in group],
            "agrees": len(set(joints)) == 1 and len(verdicts) == 1,
            "joints": [dict(g["joint"] or {}) for g in group],
            "verdicts": [g["verdict"] for g in group],
        })

    calls = sum(((r.get("metrics") or {}).get("total_calls") or 0) for r in runs)
    secs = sum(((r.get("metrics") or {}).get("total_seconds") or 0) for r in runs)
    return {
        "runs": runs, "candidates": cands, "mismatches": mismatches,
        "repeats": repeats, "threads_total": both, "threads_no_search": no_search,
        "citations": citations,
        "doors": sorted(set(d for d in doors if d and len(d) > 20)),
        "calls": calls, "seconds": secs,
        "bytes": sum(r.get("_bytes", 0) for r in runs),
    }


def _wrap(s, width, indent):
    words, line, out = s.split(), "", []
    for w in words:
        if len(line) + len(w) + 1 > width:
            out.append(line)
            line = w
        else:
            line = (line + " " + w).strip()
    if line:
        out.append(line)
    return ("\n" + " " * indent).join(out)


def format_digest(dg, width=84):
    R, C = dg["runs"], dg["candidates"]
    L = []
    add = L.append
    span = ""
    if R:
        span = f'{R[0].get("created_at","")[:16]} → {R[-1].get("created_at","")[:16]}'
    add("=" * width)
    add("DECISION DIGEST")
    add(f'{len(R)} run(s) · {span}')
    add(f'{dg["calls"]} model call(s) · {int(dg["seconds"])}s · '
        f'{dg["bytes"]//1024} KB of raw result on disk')
    add("Every line below is a re-reading of a verdict already recorded. "
        "Nothing here was")
    add("newly judged, and where this page and the full run disagree, the "
        "full run is right.")
    add("=" * width)

    def section(title, rows, render, note=""):
        add("")
        add(f'── {title}  ({len(rows)})')
        if note:
            add("   " + _wrap(note, width - 3, 3))
        if not rows:
            add("   none")
            return
        for r in rows:
            for ln in render(r):
                add(ln)

    def cand_line(c, why=""):
        mark = {"accepted": "✓ you accepted", "rejected": "✗ you rejected",
                "revised": "↻ you revised"}.get(
                    (c.get("ruled") or {}).get("decision", ""), "· not yet ruled")
        out = [f'   {c["title"]}   [{mark}]']
        if why:
            out.append("      " + _wrap(why, width - 6, 6))
        return out

    cleared = [c for c in C if c["bucket"] == "cleared"]
    section("CLEARED BOTH CHECKS — look at these first", cleared,
            lambda c: cand_line(c, f'{c["register"] or "—"} · the quote supports the claim'),
            "The anchor is in your text and a reader judged that the anchor "
            "licenses what the candidate claims. Friction raised no decisive "
            "objection.")

    partial = [c for c in C if c["bucket"] == "partial"]
    section("HALF-GROUNDED — the anchor carries some of the claim", partial,
            lambda c: cand_line(c, c["support_note"][:150]))

    ungrounded = [c for c in C if c["bucket"] == "ungrounded"]
    section("THE ANCHOR DOES NOT LICENSE THIS", ungrounded,
            lambda c: cand_line(c, c["support_note"][:150]),
            "Keeping one of these is a normal outcome — it means you liked it "
            "on its own terms. It is not the same as it having survived.")

    flagged = [c for c in C if c["bucket"] == "flagged"]
    section("FRICTION OBJECTED", flagged,
            lambda c: cand_line(c, f'{c["verdict"]} — ' + (c["redundancy"] or c["fidelity"])[:150]))

    forms = [c for c in C if c["bucket"] == "form"]
    section("NEW WORD-FORMS — same meaning, no anchor of their own", forms,
            lambda c: cand_line(c, "inherits the parent term's grounding; only the "
                                   "word itself is new"))

    faults = [c for c in C if c["bucket"] == "fault"]
    section("EXTRACTION FAULTS — not the candidate's fault", faults,
            lambda c: cand_line(c, f'anchor {c["anchor"]}, support {c["support"]}'),
            "The anchor was missing, inexact, or never checked. A weak "
            "grounding verdict here is the extraction's doing.")

    section("VERDICT / NOTE MISMATCH — mechanical, advisory", dg["mismatches"],
            lambda c: [f'   {c["title"]}   verdict: keep',
                       "      note says: " + _wrap(c["fidelity"][:260], width - 6, 6),
                       f'      (matched on {c["mark"]!r})'],
            "Friction returned a passing verdict while its own note recorded an "
            "objection. A word-match, not a judgment — it may be deliberate. It "
            "is shown so the pair is visible in one place.")

    if dg["repeats"]:
        def rep(r):
            out = [f'   {r["name"]}  — written up {r["n"]}× '
                   f'({" / ".join(p or "?" for p in r["parents"])})']
            out.append("      " + ("AGREED" if r["agrees"] else "DISAGREED") + ": " +
                       " vs ".join(
                           f'{v}·' + ",".join(f'{k[:4]}={x}' for k, x in sorted(j.items()))
                           for v, j in zip(r["verdicts"], r["joints"])))
            return out
        section("RATED MORE THAN ONCE — free reliability check", dg["repeats"], rep,
                "The same source was evaluated against the same definition more "
                "than once in this run. Where the two disagree, the difference "
                "is the size of the noise in a verdict.")

    add("")
    add(f'── LATERAL THREADS')
    if dg["threads_total"]:
        add(f'   {dg["threads_total"]} thread(s) · {dg["citations"]} search result(s) '
            f'came back at generation')
        add(f'   {dg["threads_no_search"]} of {dg["threads_total"]} reviewer(s) '
            f'reported NO SEARCH AVAILABLE and ran on recall alone.')
        if dg["threads_no_search"]:
            add("   " + _wrap(
                "The result count above belongs to the generation stage. It is "
                "not evidence any reviewer could check anything.", width - 3, 3))
    else:
        add("   none")

    add("")
    add(f'── DOORS OPENED  ({len(dg["doors"])})')
    if dg["doors"]:
        shown = dg["doors"][:6]
        for d in shown:
            add("   • " + _wrap(d[:150], width - 5, 5))
        rest = len(dg["doors"]) - len(shown)
        if rest:
            # Named, not silently dropped: a digest that truncates quietly is
            # the same failure as a run that omits a concept without saying so.
            add(f'   … and {rest} more, not shown here. `--doors` prints all of them.')
    else:
        add("   none")

    add("")
    add("=" * width)
    return "\n".join(L)


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("traces", nargs="*", help="trace ids to digest")
    ap.add_argument("--last", type=int, help="the N most recent runs")
    ap.add_argument("--since", help="ISO timestamp; runs at or after it")
    ap.add_argument("--width", type=int, default=84)
    ap.add_argument("--doors", action="store_true",
                    help="print every door instead of the first six")
    a = ap.parse_args(argv)
    if not (a.traces or a.last or a.since):
        a.last = 10
    runs = load_runs(a.traces or None, a.since, a.last)
    if not runs:
        print("no runs matched", file=sys.stderr)
        return 1
    dg = digest_runs(runs, load_judgments())
    print(format_digest(dg, a.width))
    if a.doors and dg["doors"]:
        print("\nALL DOORS")
        for d in dg["doors"]:
            print("   • " + _wrap(d, a.width - 5, 5))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
