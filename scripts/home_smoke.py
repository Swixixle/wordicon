"""Home against a real store, read-only, counts only.

    python scripts/home_smoke.py                 # the tree's own local_state
    python scripts/home_smoke.py --state DIR     # another store (the suite's scratch)
    python scripts/home_smoke.py --limit 200     # classify every ruled concept, not only the six Home paints

Prints one JSON line: what Home would paint, as numbers — how many
Continue cards of each kind, how each concept card reaches the shelf
(by id / through an older title-keyed record / ambiguous / absent), the
exclusion categories, the ruling band's counts, what is saved for later
— and a proof the store was not changed by the read (every file's size
and mtime, snapshotted before and after). It never prints a concept's
words, a meaning, or an owner's text; it opens nothing for writing.
Backlog item 41: the real-corpus proof GPT asked for, made repeatable."""
import sys
import json
import pathlib
import argparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))

REDIRECT = ("JUDGMENTS_LOG", "RECEIPTS_DIR", "RESULTS_DIR", "ACCEPTED_CONCEPTS_PATH", "EDGES_LOG", "WARPS_LOG",
            "WARP_NOTES_LOG", "BENCH_CORRECTIONS", "CONCEPT_NAMES_LOG", "BENCH_DIR", "INPUTS_LOG", "WAYFINDER_LOG")


def snapshot(state: pathlib.Path) -> dict:
    out = {}
    if not state.exists():
        return out
    for f in sorted(state.rglob("*")):
        if f.is_file():
            st = f.stat()
            out[str(f.relative_to(state))] = (st.st_size, int(st.st_mtime))
    return out


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--state", default="", help="store to read (default: the tree's local_state)")
    ap.add_argument("--limit", type=int, default=6, help="how many concept cards to classify (Home paints 6)")
    args = ap.parse_args()
    import wordicon_cli as cli
    if args.state:
        state = pathlib.Path(args.state)
        for n in REDIRECT:
            setattr(cli, n, state / str(getattr(cli, n)).split("/")[-1])
        cli.LOCAL_STATE = state
    state = pathlib.Path(cli.LOCAL_STATE)
    before = snapshot(state)
    import server
    concepts, excluded = server._home_concepts(limit=args.limit)
    rooms = server._home_rooms()
    docs = server._home_documents()
    recs = server._home_recordings()
    pend = server._home_pending()
    try:
        ks = server.keeper.status()
    except Exception as e:                      # the Keeper may be absent
        ks = {"active": False, "error": type(e).__name__}
    after = snapshot(state)
    shelf = {"concept_id": 0, "legacy_bridge": 0, "ambiguous": 0, "title_fallback": 0, "none": 0}
    for c in concepts:
        via = (c.get("shelf") or {}).get("via", "none")
        shelf[{"concept_id": "concept_id", "legacy_title": "legacy_bridge", "ambiguous": "ambiguous",
               "title_fallback": "title_fallback"}.get(via, "none")] += 1
    report = {
        "state_dir": state.name, "limit": args.limit,
        "continue": {"concepts": len(concepts), "rooms": len(rooms), "documents": len(docs), "recordings": len(recs),
                     "concepts_dated": sum(1 for c in concepts if c.get("when")),
                     "concepts_with_door": sum(1 for c in concepts if (c.get("open") or {}).get("type") and (c.get("open") or {}).get("id"))},
        "shelf": shelf,
        "excluded": {k: (v if isinstance(v, int) else len(v)) for k, v in (excluded or {}).items()},
        "pending": {"total": pend.get("total", 0), "counts": pend.get("counts", {}),
                    "saved": [{"source": s.get("source"), "count": s.get("count")} for s in pend.get("saved", [])]},
        "keeper_active": bool(ks.get("active")),
        "store_changed_by_this_read": sorted(k for k in set(before) | set(after) if before.get(k) != after.get(k)),
    }
    print(json.dumps(report, sort_keys=True))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
