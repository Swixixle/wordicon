#!/usr/bin/env python3
"""
Bone-citation concentration diagnostic.

This is the "did the contamination actually go away" check we talked about
after the parole/exile/quarantine monoculture run — but as a local,
deterministic report over your own accumulated receipts instead of a live
model call. It costs nothing to run, gives the same answer every time for
the same receipts, and reflects your actual usage instead of one staged
prompt.

It does NOT call the Anthropic API and does NOT re-run any generation. It
only reads what's already on disk in local_state/receipts/ and reports,
across every receipt you've ever produced, which admitted source fragments
keep getting cited and how concentrated that reuse is. If one or two
fixture words dominate every run regardless of topic, that's the same
grounding-driven-generation problem showing up in your real usage, not just
in one test passage.

Run it any time:
  python3 scripts/bone_diagnostics.py
"""
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
RECEIPTS_DIR = REPO_ROOT / "local_state" / "receipts"
FRAGMENTS_PATH = REPO_ROOT / "fixtures" / "public" / "fragments.json"


def _fragment_word(fragment_id: str) -> str:
    """frag_pub_exile_01 -> exile. Falls back to the raw id if the naming
    convention doesn't hold — better to show something odd than crash on a
    fragment_id that doesn't fit the pattern this script assumes."""
    parts = fragment_id.split("_")
    if len(parts) >= 3 and parts[0] == "frag" and parts[1] == "pub":
        return "_".join(parts[2:-1]) if parts[-1].isdigit() else "_".join(parts[2:])
    return fragment_id


def main() -> int:
    if not FRAGMENTS_PATH.exists():
        print(f"no fragments file at {FRAGMENTS_PATH}", file=sys.stderr)
        return 1
    all_fragments = json.loads(FRAGMENTS_PATH.read_text())
    all_words = sorted({_fragment_word(f["id"]) for f in all_fragments})

    if not RECEIPTS_DIR.exists() or not any(RECEIPTS_DIR.glob("*.json")):
        print("No receipts yet in local_state/receipts/ — run a Forge, Crack, "
              "or Decompose first, then come back and run this.")
        return 0

    receipts = [json.loads(p.read_text()) for p in sorted(RECEIPTS_DIR.glob("*.json"))]

    total_candidates = sum(len(r.get("candidates", [])) for r in receipts)
    total_claims = sum(len(r.get("sources", [])) for r in receipts)
    word_counts = Counter()
    for r in receipts:
        for s in r.get("sources", []):
            word_counts[_fragment_word(s.get("fragment_id", "?"))] += 1

    receipts_with_any_citation = sum(1 for r in receipts if r.get("sources"))

    print(f"Bone-citation concentration report — {len(receipts)} receipt(s), "
          f"{total_candidates} candidate(s) total, {total_claims} accepted "
          f"Bone claim(s) across all of them.\n")

    print(f"Fixture pool: {len(all_words)} source word(s) available "
          f"({', '.join(all_words)}).\n")

    if total_claims == 0:
        print("Zero Bone claims cited across every receipt on record. Given "
              "the fixture pool is still narrow relative to arbitrary input "
              "topics, that's a plausible and healthy outcome, not "
              "necessarily a bug — but if you were expecting some grounded "
              "candidates and got none, that's worth a manual look too.")
        return 0

    print(f"{receipts_with_any_citation}/{len(receipts)} receipts "
          f"({receipts_with_any_citation / len(receipts):.0%}) cited at "
          f"least one Bone claim.\n")

    print("Citation share by fixture word (accepted claims, not candidates):")
    unused = [w for w in all_words if w not in word_counts]
    for word, count in word_counts.most_common():
        share = count / total_claims
        flag = "  <-- concentrated" if share > 0.30 and len(word_counts) > 1 else ""
        print(f"  {word:<14} {count:>3}  ({share:.0%}){flag}")
    if unused:
        print(f"\nNever cited: {', '.join(unused)}")

    top_word, top_count = word_counts.most_common(1)[0]
    top_share = top_count / total_claims
    print()
    if len(word_counts) == 1 and total_claims > 2:
        print(f"Every single cited claim traces to one word ('{top_word}') — "
              f"that's the monoculture pattern from the Douglass run, not "
              f"resolved. If this holds up over more runs across genuinely "
              f"different topics, the two-call split isn't doing its job "
              f"and the prompt wording needs another look.")
    elif top_share > 0.5:
        print(f"'{top_word}' alone accounts for {top_share:.0%} of all "
              f"citations. Worth watching — that's a real concentration, "
              f"though not yet the total lock-in the pre-fix run showed.")
    else:
        print(f"No single word dominates (top: '{top_word}' at {top_share:.0%}) "
              f"— citation looks distributed rather than concentrated, which "
              f"is what the two-call split and the expanded fragment pool "
              f"were meant to produce. This is the signal you're looking for.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
