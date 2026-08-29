#!/usr/bin/env python3
"""Is the constrained archetype better than just asking for one?

    python3 scripts/blind.py make  --n 12     # build the pairs, labels hidden
    python3 scripts/blind.py sheet            # print the rating sheet
    python3 scripts/blind.py score            # after you fill it in

Nothing in this project has ever been compared against the trivial
alternative. Every check inside Wordicon answers "is this claim supported";
none answers "is this pipeline better than a one-line prompt." The archetype
stage is the place that question bites hardest, because it is the one stage
with no external check on its output — so it ships with this.

THE ONE RULE: you must not be able to tell which is which while rating.
The bare version and the constrained version are written to the same shape,
stripped of every tell — no rests_on labels, no code notes, no findings, no
"unfalsifiable" banner — and the order within each pair is shuffled on a
seed you do not see until you score. What survives that is a preference for
the writing, which is the only thing worth measuring here.

Standalone, like digest.py and export.py: an experiment that can break the
tool it is measuring is not an experiment.
"""
import argparse
import json
import os
import pathlib
import random
import sys
import textwrap

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

LOCAL_STATE = pathlib.Path(
    os.environ.get("WORDICON_STATE")
    or (pathlib.Path(__file__).resolve().parent.parent / "local_state"))
TRIAL_PATH = LOCAL_STATE / "blind_archetype_trial.json"

BARE_PROMPT = """Give me the archetype behind this concept — the recognisable
human figure a person would have to be living for this concept to be about
them.

Title: {title}
Definition: {definition}

Return JSON: {{"figure": "<short name>", "facets": [{{"text": "..."}}],
"excludes": "<the nearest figure this is not>", "falsifier": "<a concrete
case this archetype fails to describe>"}}"""


def _load(p):
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return None


def accepted_with_definitions(limit):
    """Real concepts from the corpus, not invented test cases: the question
    is whether this helps on HIS words, not on convenient ones."""
    rows = _load(LOCAL_STATE / "accepted_concepts.json") or []
    out = [r for r in rows if (r.get("name") or "").strip()
           and len((r.get("definition") or "").strip()) > 40]
    random.shuffle(out)
    return out[:limit]


def _has_body(text):
    """A rendered arm counts only if it actually says something: a figure
    named, and at least one facet under it."""
    lines = [l.strip() for l in (text or "").splitlines()]
    figure = next((l[len("FIGURE:"):].strip() for l in lines if l.startswith("FIGURE:")), "")
    facets = [l for l in lines if l.startswith("- ") and len(l) > 4]
    return bool(figure) and bool(facets)


def flatten(arch):
    """Both arms rendered identically. Every tell the constrained version
    carries — the support labels, the demotion notes, the code findings —
    is dropped here on purpose. Leaving one in would measure whether you can
    spot the machinery, not whether the machinery helped."""
    lines = [f"FIGURE: {(arch.get('figure') or '').strip()}", ""]
    for f in (arch.get("facets") or []):
        t = (f.get("text") if isinstance(f, dict) else str(f)) or ""
        if t.strip():
            lines.append("- " + t.strip())
    lines += ["", "NOT: " + (arch.get("excludes") or "").strip(),
              "FAILS ON: " + (arch.get("falsifier") or "").strip()]
    return "\n".join(lines).strip()


def make(n, gateway_name, model):
    import wordicon_cli as cli
    cli.LOCAL_STATE = LOCAL_STATE
    cli.RESULTS_DIR = LOCAL_STATE / "results"
    cli.ACCEPTED_CONCEPTS_PATH = LOCAL_STATE / "accepted_concepts.json"
    cli.JUDGMENTS_LOG = LOCAL_STATE / "judgments.jsonl"
    cli.EDGES_LOG = LOCAL_STATE / "edges.jsonl"
    gw = cli.make_gateway(gateway_name, model)

    concepts = accepted_with_definitions(n)
    if not concepts:
        print("No accepted words with definitions to test on.")
        return 1
    seed = random.randrange(1, 10 ** 9)
    rnd = random.Random(seed)
    pairs = []
    for i, c in enumerate(concepts, 1):
        cand = {"title": c["name"], "definition": c.get("definition", ""),
                "central_contradiction": "", "axiom": ""}
        print(f"[{i}/{len(concepts)}] {c['name']}")
        try:
            constrained = cli.run_archetype(cand, gw)["archetype"]
        except Exception as e:
            print(f"    constrained arm failed: {e}"); continue
        try:
            bare = cli._extract_json(gw.complete(BARE_PROMPT.format(
                title=c["name"], definition=c.get("definition", ""))))
        except Exception as e:
            print(f"    bare arm failed: {e}"); continue
        c_text, b_text = flatten(constrained), flatten(bare)
        # An arm that came back empty is not a weak answer, it is a TELL:
        # a rater seeing one blank panel knows exactly which side failed and
        # the pair stops measuring anything. Drop it rather than blind a
        # comparison that is no longer blind.
        if not _has_body(c_text) or not _has_body(b_text):
            print("    dropped: one arm came back empty, which would give the pair away")
            continue
        arms = [("constrained", c_text), ("bare", b_text)]
        rnd.shuffle(arms)
        pairs.append({"n": len(pairs) + 1, "title": c["name"],
                      "definition": c.get("definition", ""),
                      "a_arm": arms[0][0], "a_text": arms[0][1],
                      "b_arm": arms[1][0], "b_text": arms[1][1]})
    LOCAL_STATE.mkdir(parents=True, exist_ok=True)
    TRIAL_PATH.write_text(json.dumps(
        {"seed": seed, "gateway": gw.name, "pairs": pairs, "ratings": {}}, indent=2),
        encoding="utf-8")
    if not pairs:
        print("\nNo usable pairs — every one had an arm come back empty. On the mock "
              "gateway that is expected; the bare prompt has no fixture behind it.")
        return 1
    print(f"\n{len(pairs)} pair(s) written to {TRIAL_PATH}")
    print("Now run:  python3 scripts/blind.py sheet")
    return 0


def sheet():
    d = _load(TRIAL_PATH)
    if not d:
        print("No trial yet — run `blind.py make` first.")
        return 1
    w = textwrap.TextWrapper(width=78, initial_indent="   ", subsequent_indent="   ")
    for p in d["pairs"]:
        print("=" * 78)
        print(f"{p['n']}. {p['title']}")
        print(w.fill(p["definition"]))
        for side in ("A", "B"):
            print(f"\n--- {side} " + "-" * 70)
            for line in p[f"{side.lower()}_text"].splitlines():
                print(w.fill(line) if line.strip() else "")
        print()
    print("=" * 78)
    print("For each number write A or B — whichever figure you would actually use.")
    print("Write '=' if neither is better. Then:")
    print("  python3 scripts/blind.py score --picks 1=A,2=B,3=A,…")
    print("\nNothing above says which arm is which. Do not open the JSON first.")
    return 0


def score(picks):
    d = _load(TRIAL_PATH)
    if not d:
        print("No trial yet.")
        return 1
    got = {}
    for part in (picks or "").split(","):
        if "=" not in part:
            continue
        k, v = part.split("=", 1)
        got[k.strip()] = v.strip().upper()
    by_n = {str(p["n"]): p for p in d["pairs"]}
    tally = {"constrained": 0, "bare": 0, "tie": 0}
    unrated = []
    for n, p in by_n.items():
        pick = got.get(n)
        if pick not in ("A", "B", "="):
            unrated.append(n)
            continue
        if pick == "=":
            tally["tie"] += 1
        else:
            tally[p["a_arm"] if pick == "A" else p["b_arm"]] += 1
    d["ratings"] = got
    TRIAL_PATH.write_text(json.dumps(d, indent=2), encoding="utf-8")

    rated = tally["constrained"] + tally["bare"] + tally["tie"]
    print(f"rated {rated} of {len(by_n)} pair(s)"
          + (f" · unrated: {', '.join(unrated)}" if unrated else ""))
    print(f"  constrained {tally['constrained']}"
          f"   bare {tally['bare']}   no preference {tally['tie']}")
    decided = tally["constrained"] + tally["bare"]
    if decided < 6:
        print("\nToo few decided pairs to read anything into. This is a sample size, "
              "not a result.")
        return 0
    # The honest reading of a small sample: how surprising is this under a
    # coin flip? No p-value theatre — the count either clears chance
    # comfortably or it does not, and at n<20 it usually does not.
    from math import comb
    k = max(tally["constrained"], tally["bare"])
    tail = sum(comb(decided, i) for i in range(k, decided + 1)) / (2 ** decided)
    winner = "constrained" if tally["constrained"] > tally["bare"] else "bare"
    print(f"\n{winner} won {k} of {decided} decided pairs.")
    print(f"A coin lands {k}-or-better this often: {tail * 100:.1f}% of the time.")
    if tail > 0.10:
        print("That is inside what chance produces. This does not show a difference — "
              "with this many pairs it mostly cannot, whichever way it fell.")
    else:
        print("That is outside what chance comfortably produces at this sample size. "
              "It is one sitting by one rater, so treat it as a reason to look harder, "
              "not as a settled result.")
    return 0


def main(argv=None):
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("what", choices=["make", "sheet", "score"])
    ap.add_argument("--n", type=int, default=12)
    ap.add_argument("--gateway", default=None)
    ap.add_argument("--model", default=None)
    ap.add_argument("--picks", default="")
    a = ap.parse_args(argv)
    if a.what == "make":
        gw = a.gateway or ("anthropic" if os.environ.get("ANTHROPIC_API_KEY") else "mock")
        model = a.model or os.environ.get("WORDICON_MODEL")
        if gw == "mock":
            print("NOTE: running on the mock gateway — both arms return canned text, "
                  "so the comparison is meaningless. Set ANTHROPIC_API_KEY and "
                  "WORDICON_MODEL for a real trial.\n")
        return make(a.n, gw, model)
    if a.what == "sheet":
        return sheet()
    return score(a.picks)


if __name__ == "__main__":
    raise SystemExit(main())
