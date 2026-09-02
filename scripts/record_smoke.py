"""Read-only counts of the record primitives (block 104) over a store.

  python scripts/record_smoke.py                 # the repo's local_state
  python scripts/record_smoke.py --state PATH    # a copy

Writes nothing. Reports what the store holds: edges by origin (rows with
none are legacy_unknown — labeled by the reader, never rewritten),
definition events by origin and whether the shelf equals their
projection, the encounter switch and its rows, receipts by operation and
how many carry prompt identities or a composite block, and the Recovery
Review's open / unresolved / ruled counts."""
from __future__ import annotations

import argparse
import hashlib
import json
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent / "src"))

import wordicon_cli as cli  # noqa: E402
import recovery  # noqa: E402


def _point(root: pathlib.Path) -> None:
    cli.LOCAL_STATE = root
    cli.JUDGMENTS_LOG = root / "judgments.jsonl"
    cli.RECEIPTS_DIR = root / "receipts"
    cli.RESULTS_DIR = root / "results"
    cli.ACCEPTED_CONCEPTS_PATH = root / "accepted_concepts.json"
    cli.EDGES_LOG = root / "edges.jsonl"
    cli.DEFINITION_EVENTS_LOG = root / "definition_events.jsonl"
    cli.ENCOUNTER_SWITCH_LOG = root / "encounter_switch.jsonl"
    cli.ENCOUNTERS_LOG = root / "encounters.jsonl"


def store_digest(root: pathlib.Path) -> str:
    """One hash over every file's path and bytes — the byte-identity proof."""
    h = hashlib.sha256()
    for p in sorted(root.rglob("*")):
        if p.is_file():
            h.update(str(p.relative_to(root)).encode()); h.update(b"\0")
            h.update(p.read_bytes()); h.update(b"\0")
    return h.hexdigest()


def report(root: pathlib.Path) -> dict:
    edges = cli.load_edges()
    by_origin: dict[str, int] = {}
    with_producer = 0
    for e in edges:
        by_origin[e.get("origin", "legacy_unknown")] = by_origin.get(e.get("origin", "legacy_unknown"), 0) + 1
        if isinstance(e.get("producer"), dict) and e["producer"].get("id"):
            with_producer += 1
    events = cli.load_definition_events()
    ev_by_origin: dict[str, int] = {}
    for ev in events:
        ev_by_origin[ev.get("origin", "")] = ev_by_origin.get(ev.get("origin", ""), 0) + 1
    receipts = []
    if cli.RECEIPTS_DIR.exists():
        for p in cli.RECEIPTS_DIR.glob("*.json"):
            try:
                receipts.append(json.loads(p.read_text(encoding="utf-8")))
            except (ValueError, OSError):
                continue
    ops: dict[str, int] = {}
    for r in receipts:
        ops[r.get("operation", "")] = ops.get(r.get("operation", ""), 0) + 1
    return {
        "store": str(root),
        "edges": {"total": len(edges), "by_origin": dict(sorted(by_origin.items())), "with_producer": with_producer},
        "definition_events": {"total": len(events), "by_origin": dict(sorted(ev_by_origin.items())),
                              "projection": cli.shelf_projection_check()},
        "encounters": {"switch": cli.encounter_recording(), "rows": len(cli.load_encounters())},
        "receipts": {"total": len(receipts), "by_operation": dict(sorted(ops.items())),
                     "with_prompt_identities": sum(1 for r in receipts if r.get("prompt_identities")),
                     "with_composite": sum(1 for r in receipts if isinstance(r.get("composite"), dict))},
        "recovery": {"open": len(recovery.open_cases()), "unresolved": len(recovery.unresolved_cases()),
                     "ruled": len(recovery.load_rulings())},
        "digest": store_digest(root),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--state", default="")
    ap.add_argument("--json", action="store_true")
    a = ap.parse_args()
    root = pathlib.Path(a.state).resolve() if a.state else cli.LOCAL_STATE
    _point(root)
    before = store_digest(root)
    r = report(root)
    if store_digest(root) != before:
        print("ERROR: the smoke changed the store", file=sys.stderr)
        return 2
    if a.json:
        print(json.dumps(r, indent=2))
        return 0
    e, d, en, rc, rv = r["edges"], r["definition_events"], r["encounters"], r["receipts"], r["recovery"]
    print(f"store {root}")
    print(f"edges {e['total']} · by origin {e['by_origin']} · with producer {e['with_producer']}")
    print(f"definition events {d['total']} · by origin {d['by_origin']} · shelf {d['projection']['file_entries']} entries, "
          f"projection {d['projection']['projected_entries']} · {'MATCH' if d['projection']['matches'] else 'MISMATCH'}")
    print(f"encounter recording {'on' if en['switch']['on'] else 'off'} · flips {en['switch']['flips']} · rows {en['rows']}")
    print(f"receipts {rc['total']} · by operation {rc['by_operation']} · with prompt identities {rc['with_prompt_identities']} · "
          f"composite {rc['with_composite']}")
    print(f"recovery review: open {rv['open']} · unresolved {rv['unresolved']} · ruled {rv['ruled']}")
    print(f"digest {r['digest'][:16]}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
