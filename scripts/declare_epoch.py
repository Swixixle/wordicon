"""Declare the corpus epoch (block 103; backlog items 46, 47).

    python scripts/declare_epoch.py development_and_calibration --by owner --note "..."

Appends one row to local_state/epochs.jsonl; earlier rows are never
touched. The first declaration records, as an observed fact, the
earliest receipt time in the store (`first_record_at`) — the material
the declaration covers — without rewriting anything. Refuses to
re-declare the epoch the record is already in."""
import sys
import json
import pathlib
import argparse

ROOT = pathlib.Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT))
sys.path.insert(0, str(ROOT / "scripts"))
import wordicon_cli as cli  # noqa: E402

KNOWN = ("development_and_calibration", "ordinary_use")


def earliest_receipt() -> str:
    best = ""
    if cli.RECEIPTS_DIR.exists():
        for p in cli.RECEIPTS_DIR.glob("*.json"):
            try:
                t = json.loads(p.read_text(encoding="utf-8")).get("created_at") or ""
            except (ValueError, OSError):
                continue
            if t and (not best or t < best):
                best = t
    return best


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("epoch", choices=KNOWN)
    ap.add_argument("--by", default="owner")
    ap.add_argument("--note", default="")
    ap.add_argument("--state", default="", help="another store (tests); default: the tree's local_state")
    args = ap.parse_args()
    if args.state:
        cli.LOCAL_STATE = pathlib.Path(args.state)
        cli.RECEIPTS_DIR = cli.LOCAL_STATE / "receipts"
    if cli.current_epoch() == args.epoch:
        print(json.dumps({"declared": False, "reason": f"the record is already in {args.epoch}"}))
        return 1
    first = earliest_receipt() if not cli.load_epochs() else ""
    row = cli.declare_epoch(args.epoch, declared_by=args.by, note=args.note, first_record_at=first)
    print(json.dumps({"declared": True, "row": row}))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
