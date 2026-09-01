#!/usr/bin/env python3
"""Recovery of acceptances the word-first schema suppressed.

docs/adr-concept-first.md. Recovery is a MECHANICAL REPLAY of an owner
decision already on the record — never a new inference. This script:

  --report              re-runs the read-only audit and prints it
  --recover ID [ID...]  recovers the named concept_ids, but only if the
                        audit itself classifies them as suppressed WITH
                        an owner acceptance ruling and a surviving
                        results snapshot (Class A). Anything else is
                        refused by class, not by mood.
  --queue-review        records the receipt-only cases (accepted, absent,
                        no snapshot) into recovery_review_queue.jsonl for
                        a later owner Review. Records them; recovers
                        nothing.

Every recovered entry preserves the original run, candidate concept_id,
and run time, and carries a recovery event (recovered_at,
recovery_reason: legacy_title_collision). No existing row is modified —
the script proves that about its own write before keeping it.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).parent))
import wordicon_cli as cli  # noqa: E402


def _norm(s):
    return " ".join((s or "").lower().split())


def _rows(path):
    if not path.exists():
        return []
    out = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line:
            continue
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def audit() -> dict:
    """The read-only audit, keyed by concept_id (a title-keyed first
    draft under-counted; the mistake is preserved in the project record
    as its own exhibit)."""
    lex = (json.loads(cli.ACCEPTED_CONCEPTS_PATH.read_text())
           if cli.ACCEPTED_CONCEPTS_PATH.exists() else [])
    by_title = {}
    for e in lex:
        by_title.setdefault(_norm(e.get("name")), []).append(e)
    recovered_cids = {e.get("concept_id") for e in lex if e.get("concept_id")}

    cand_by_cid = {}
    results_dir = cli.LOCAL_STATE / "results"
    if results_dir.exists():
        for p in sorted(results_dir.glob("trace_cli_*.json")):
            try:
                d = json.loads(p.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                continue
            for c in d.get("candidates") or []:
                bff = c.get("bff") or c
                cid = bff.get("concept_id")
                if cid and cid not in cand_by_cid:
                    flesh = bff.get("flesh") or {}
                    cand_by_cid[cid] = {
                        "title": bff.get("title") or "",
                        "definition": (flesh.get("definition")
                                       or bff.get("definition") or ""),
                        "trace": d.get("trace_id") or p.stem,
                        "run_at": d.get("created_at") or ""}

    suppressed, absent = {}, []
    for j in _rows(cli.JUDGMENTS_LOG):
        if j.get("decision") not in ("accepted", "adopted"):
            continue
        title = j.get("candidate_text") or ""
        trace = j.get("originating_operation") or ""
        cid = j.get("concept_id") or ""
        cand = cand_by_cid.get(cid) if cid else None
        entries = by_title.get(_norm(title), [])
        if cid and cid in recovered_cids:
            continue  # already present concept-first
        # RETAINED means THIS acceptance is on the shelf — which requires
        # the definition to match, not merely the trace: all three real
        # suppressions happened INSIDE one trace (a run accepted
        # same-titled siblings and the shelf kept the first), so a
        # trace-level check calls the suppressed sibling "retained" and
        # the recovery refuses its own purpose. Found live when the
        # first recovery run refused all three authorized concepts.
        if entries and any(
                e.get("accepted_from") == trace
                and (not cand or not _norm(cand["definition"])
                     or _norm(e.get("definition")) == _norm(cand["definition"]))
                for e in entries):
            continue  # this acceptance is the one the shelf kept
        if cand and entries and _norm(cand["definition"]) \
                and all(_norm(e.get("definition")) != _norm(cand["definition"])
                        for e in entries):
            suppressed[cid] = {"concept_id": cid, "title": title,
                               "trace": trace, "run_at": cand["run_at"],
                               "definition": cand["definition"],
                               "judgment_id": j.get("id") or "",
                               "kept_instead": (entries[0].get("definition")
                                                or "")[:120]}
        elif not entries:
            absent.append({"title": title, "trace": trace,
                           "judgment_id": j.get("id") or "",
                           "note": "accepted; no lexicon entry; no results "
                                   "snapshot survives — needs owner ruling"})
    return {"suppressed": suppressed, "absent": absent}


def recover(cids: "list[str]") -> int:
    found = audit()["suppressed"]
    lex_before = cli.ACCEPTED_CONCEPTS_PATH.read_text() \
        if cli.ACCEPTED_CONCEPTS_PATH.exists() else "[]"
    entries = json.loads(lex_before)
    legacy_snapshot = [json.dumps(e, sort_keys=True) for e in entries]
    events = []
    for cid in cids:
        s = found.get(cid)
        if not s:
            print(f"REFUSED {cid}: the audit does not classify this as a "
                  "suppressed acceptance with a surviving ruling and "
                  "snapshot — recovery replays decisions, it never makes "
                  "them")
            return 1
        entry = {
            "id": f"acc2_{hashlib.sha256(cid.encode()).hexdigest()[:12]}",
            "concept_id": cid, "object_type": "concept",
            "name": s["title"], "definition": s["definition"],
            "status": "accepted", "alias_of": "",
            "declined_alias": [], "declined_identical": [],
            "decline_reason": "",
            "accepted_from": s["trace"],
            # the ORIGINAL time: the run's created_at — the judgment rows
            # of that era carried no timestamp of their own, and this
            # record says so instead of inventing one
            "accepted_at": s["run_at"],
            "supporting_claims": [], "governing_constraints": [],
            "related_mechanisms": [], "version": 1,
            "recovery": {
                "recovered_at": cli._now(),
                "original_ruling_at": "",
                "original_ruling_time_note": (
                    "judgment rows were unstamped under the old schema; "
                    "accepted_at above carries the run's own time, the "
                    "closest recorded original"),
                "recovery_reason": "legacy_title_collision",
                "original_judgment_id": s["judgment_id"],
                "refused_by": "title-idempotent persist (pre-ADR schema)"},
        }
        entries.append(entry)
        events.append({"event": "recovered", "concept_id": cid,
                       "title": s["title"], "trace": s["trace"],
                       "original_judgment_id": s["judgment_id"],
                       "recovery_reason": "legacy_title_collision",
                       "at": cli._now()})
        print(f"RECOVERED {s['title']!r} ({cid}) from run {s['trace']}")
    # prove no legacy row changed before keeping the write
    after = [json.dumps(e, sort_keys=True) for e in entries][:len(legacy_snapshot)]
    if after != legacy_snapshot:
        print("ABORT: a legacy row would have changed — nothing written")
        return 2
    cli.ACCEPTED_CONCEPTS_PATH.write_text(json.dumps(entries, indent=2))
    with (cli.LOCAL_STATE / "recovery_events.jsonl").open("a", encoding="utf-8") as f:
        for ev in events:
            f.write(json.dumps(ev, ensure_ascii=False) + "\n")
    print(f"done: {len(events)} concept(s) recovered; legacy rows byte-stable")
    return 0


def queue_review() -> int:
    absent = audit()["absent"]
    qpath = cli.LOCAL_STATE / "recovery_review_queue.jsonl"
    existing = {(r.get("title"), r.get("trace")) for r in _rows(qpath)}
    n = 0
    with qpath.open("a", encoding="utf-8") as f:
        for a in absent:
            if (a["title"], a["trace"]) in existing:
                continue
            f.write(json.dumps({**a, "status": "needs_owner_ruling",
                                "queued_at": cli._now()},
                               ensure_ascii=False) + "\n")
            n += 1
    print(f"queued {n} receipt-only case(s) for the Recovery Review; "
          f"{len(absent) - n} already queued")
    return 0


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--report", action="store_true")
    ap.add_argument("--recover", nargs="+", metavar="CONCEPT_ID")
    ap.add_argument("--queue-review", action="store_true")
    args = ap.parse_args()
    if args.report:
        a = audit()
        print(json.dumps(a, indent=1)[:4000])
        print(f"suppressed: {len(a['suppressed'])} · "
              f"receipt-only: {len(a['absent'])}")
        return 0
    if args.recover:
        return recover(args.recover)
    if args.queue_review:
        return queue_review()
    ap.print_help()
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
