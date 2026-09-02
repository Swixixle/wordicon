"""The shelf as a projection (block 104; docs/adr-record-primitives.md).

  python scripts/shelf_projection.py --check       # does the shelf file equal what the events rebuild?
  python scripts/shelf_projection.py --baseline    # one labeled baseline event per entry that has none
  python scripts/shelf_projection.py --baseline --dry-run

--check reads only. --baseline appends, once, one event per shelf entry
that has no definition event yet: for an entry whose concept_id a
Recovery Review ruling minted, the event is RECONSTRUCTED MECHANICALLY
from that ruling (its clock, its judgment id, the definition the owner
supplied — all read from files, nothing inferred); for every other entry
it is a BASELINE SNAPSHOT — the entry as found, labeled as such, dated
now, carrying the entry's own accepted_at as an observed fact and no
history that the record does not hold. Entries that already have an event
are skipped, so running it twice appends nothing. The shelf file is never
written by this script."""
from __future__ import annotations

import argparse
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

import wordicon_cli as cli  # noqa: E402
import recovery  # noqa: E402


def _entries() -> list[dict]:
    if not cli.ACCEPTED_CONCEPTS_PATH.exists():
        return []
    try:
        return json.loads(cli.ACCEPTED_CONCEPTS_PATH.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return []


def baseline(dry_run: bool = False) -> dict:
    have = {ev.get("entry_id") for ev in cli.load_definition_events()}
    rulings_by_concept = {r.get("concept_id"): r for r in recovery.load_rulings()
                          if r.get("concept_id") and r.get("shelf_entry_added")}
    out = {"reconstructed": [], "baselined": [], "skipped": 0}
    for e in _entries():
        eid = e.get("id") or ""
        if not eid:
            continue
        if eid in have:
            out["skipped"] += 1
            continue
        ruling = rulings_by_concept.get(e.get("concept_id") or "")
        if ruling:
            # every value below is read from the ruling row or the entry
            accepted_jid = ""
            for jid in ruling.get("judgment_ids") or []:
                j = recovery._judgment_row(jid)
                if j.get("decision") == "accepted":
                    accepted_jid = jid
            if not dry_run:
                cli.record_definition_event(
                    "defined", e, origin="reconstructed_recovery", judgment_id=accepted_jid,
                    at=ruling.get("ruled_at") or "",
                    note="reconstructed mechanically from the Recovery Review ruling; nothing inferred",
                    extra={"reconstructed_from": ruling.get("ruling_id", ""), "reconstructed": True})
            out["reconstructed"].append({"entry_id": eid, "ruling_id": ruling.get("ruling_id", "")})
        else:
            if not dry_run:
                cli.record_definition_event(
                    "defined", e, origin="baseline_snapshot",
                    note="baseline snapshot of the shelf as found; no event history survives before this",
                    extra={"baseline": True, "entry_accepted_at": e.get("accepted_at") or "",
                           "entry_accepted_from": e.get("accepted_from") or ""})
            out["baselined"].append(eid)
    return out


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--check", action="store_true")
    ap.add_argument("--baseline", action="store_true")
    ap.add_argument("--dry-run", action="store_true")
    ap.add_argument("--state", default="", help="another local_state directory (read-only checks of a copy)")
    a = ap.parse_args()
    if a.state:
        root = pathlib.Path(a.state).resolve()
        cli.LOCAL_STATE = root
        cli.ACCEPTED_CONCEPTS_PATH = root / "accepted_concepts.json"
        cli.DEFINITION_EVENTS_LOG = root / "definition_events.jsonl"
        cli.JUDGMENTS_LOG = root / "judgments.jsonl"
    if not a.check and not a.baseline:
        a.check = True
    if a.baseline:
        r = baseline(dry_run=a.dry_run)
        print(f"{'would reconstruct' if a.dry_run else 'reconstructed'} {len(r['reconstructed'])} "
              f"from Recovery Review rulings; {'would baseline' if a.dry_run else 'baselined'} "
              f"{len(r['baselined'])}; skipped {r['skipped']} that already have events")
    c = cli.shelf_projection_check()
    print(f"shelf file: {c['file_entries']} entries · events: {c['events']} · projected: {c['projected_entries']} · "
          f"{'MATCH' if c['matches'] else 'MISMATCH'}")
    if not c["matches"]:
        print(json.dumps({k: c[k] for k in ("only_in_file", "only_in_events", "differ")}, indent=2))
    return 0 if c["matches"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
