#!/usr/bin/env python3
"""Read-only. What a component run's stored verdicts say, in two modes.

Block 120, under the owner's ruling. Block 119 shipped one mode and it
failed closed on every real record: it refused if any 40-character run of
the passage reached its output, and an ANCHOR IS SUCH A RUN, so it blocked
the exact case it was built for. The repair is not to weaken the guard.
It is to have two outputs with different audiences.

  DEFAULT (share-safe). Identifiers, labels, verdict classes, support
  classes, error metadata, counts. No passage, no anchors, no candidate
  prose, no model sentences about the passage — those quote it. Safe to
  paste into a chat, a ruling, or a bug report, and safe when redirected
  into a file, because safety is a property of what is rendered and not of
  where it goes.

  --show-anchors (LOCAL ONLY). Adds the anchors and the critics' own
  sentences, for the owner reading his own material on his own machine. It
  prints a private-output banner, refuses to run when its output is not a
  terminal, and is never used by tests, fixtures or reports.

Neither mode writes a file. Nothing here goes into the repository.

    python3 scripts/inspect_component.py <trace_id|path>
    python3 scripts/inspect_component.py --latest-failed
    python3 scripts/inspect_component.py --latest-failed --show-anchors
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "local_state" / "results"

# Fields whose content is, or quotes, the owner's writing. The share-safe
# render never reads them; the guard below re-checks the rendered text
# against them anyway, so a future field carrying his prose under a new
# name is caught by the check rather than by someone remembering it here.
PASSAGE_FIELDS = ("input_text", "source_text", "forge_input", "gist", "anchor",
                  "constraints", "summary", "hostile_read", "reason",
                  "source_contradiction", "note", "definition",
                  "deciding_anchor_words", "deciding_claim_words")

PRIVATE_BANNER = (
    "════ PRIVATE — LOCAL READING ONLY ════\n"
    "This output contains your passage's anchors and the critics' sentences\n"
    "about them. It is for you, on this machine. Do not paste it into a\n"
    "chat, a report or a ruling; run without --show-anchors for that.\n"
    "══════════════════════════════════════")


def _load(arg: str) -> "tuple[Path, dict]":
    p = Path(arg)
    if not p.exists():
        p = RESULTS / (arg if arg.endswith(".json") else f"{arg}.json")
    if not p.exists():
        raise SystemExit(f"no such record: {arg}")
    return p, json.loads(p.read_text())


def _latest_failed() -> str:
    best = None
    for f in RESULTS.glob("*.json"):
        try:
            d = json.loads(f.read_text())
        except Exception:  # noqa: BLE001
            continue
        if d.get("mode") in ("deep", "decompose") and d.get("partial"):
            if best is None or str(d.get("created_at", "")) > str(best[1].get("created_at", "")):
                best = (f, d)
    if best is None:
        raise SystemExit("no partial deep/decompose run in the results store")
    return str(best[0])


def render(record: dict, show_anchors: bool = False) -> str:
    out: "list[str]" = []
    w = out.append
    if show_anchors:
        w(PRIVATE_BANNER)
        w("")
    w(f"record       {record.get('trace_id','')}  ({record.get('mode','')})")
    w(f"created      {record.get('created_at','')}")
    n = record.get("n_components")
    done = record.get("n_completed")
    if n is None:
        groups = record.get("groups") or []
        n = len(groups)
        done = n - sum(1 for g in groups if g.get("failed"))
        w(f"completion   {record.get('completion','')}  ·  {done} of {n} components analysed "
          f"(counted here; this record predates the scoped counts)")
    else:
        w(f"completion   {record.get('completion','')}  ·  {done} of {n} components analysed")
    att = record.get("attempt_summary") or {}
    if att:
        w(f"attempts     {att.get('http_attempts','?')} HTTP attempt(s), "
          f"{att.get('attempts_failed','?')} failed, {att.get('retries','?')} retries")
        w(f"             population: {att.get('population','')}")
    else:
        w("attempts     NOT RECORDED — this run predates the attempt ledger, so the "
          "number of requests it made cannot be recovered")
    pid = record.get("prompt_identities") or []
    if pid:
        w("prompt renders (NOT a request count; worker-thread stages are absent "
          "from pre-block-119 records): "
          + ", ".join(f"{p.get('stage')}={p.get('calls')}" for p in pid))
        models = sorted({p.get("model", "") for p in pid if p.get("model")})
        if models:
            w(f"model(s)     {', '.join(models)}")
    w("")

    for g in record.get("groups") or []:
        label = g.get("label", "")
        w(f"── {label}")
        if g.get("failed"):
            w("     NOT ANALYSED")
            w(f"     stored error class/text: {str(g.get('error',''))[:200]}")
            w("")
            continue
        w(f"     anchor_verified={g.get('anchor_verified')} "
          f"near_miss={g.get('anchor_near_miss')} grounding={g.get('grounding','')}")
        cba = g.get("constraint_beyond_anchor") or []
        if cba:
            w(f"     MALFORMED PACKET — constraint requires words the anchor lacks: {', '.join(map(str, cba))}")
        if show_anchors and g.get("anchor"):
            w(f"     anchor: “{g['anchor']}”")
        cands = g.get("candidates") or []
        if not cands and g.get("trace_id"):
            w(f"     candidates live in this component's own run: {g['trace_id']}")
        for c in cands:
            b = c.get("bone_flesh_friction") or c.get("bff") or {}
            f = b.get("friction") or {}
            sup = b.get("claim_support") or b.get("support") or {}
            w(f"     • {b.get('title','')}")
            w(f"         friction verdict     {f.get('verdict','')}")
            w(f"         contradicts_anchor   {bool(f.get('contradicts_anchor'))}")
            w(f"         support class        {sup.get('support','')}")
            if show_anchors:
                for key, lbl in (("source_contradiction", "source_contradiction"),
                                 ("reason", "reason"), ("hostile_read", "hostile_read")):
                    if f.get(key):
                        w(f"         {lbl:20} {f[key]}")
                if sup.get("note"):
                    w(f"         support note         {sup['note']}")
        w("")
    if not show_anchors:
        w("(verdict CLASSES only. The critics' sentences quote your passage, so they "
          "are omitted here; run with --show-anchors on your own machine to read them.)")
    return "\n".join(out)


def _all_values(node, key):
    if isinstance(node, dict):
        for k, v in node.items():
            if k == key:
                yield v
            else:
                yield from _all_values(v, key)
    elif isinstance(node, list):
        for v in node:
            yield from _all_values(v, key)


def _chunks(text: str, size: int = 40):
    t = " ".join((text or "").split())
    for i in range(0, max(0, len(t) - size + 1)):
        yield t[i:i + size]


def refuse_if_passage_leaked(text: str, record: dict) -> "str | None":
    """The share-safe render, checked AGAINST THE RECORD rather than against
    a list of keys someone remembered to skip."""
    flat = " ".join((text or "").split())
    for field in PASSAGE_FIELDS:
        for value in _all_values(record, field):
            if not isinstance(value, str) or len(" ".join(value.split())) < 40:
                continue
            for chunk in _chunks(value):
                if chunk and chunk in flat:
                    return f"{field} (a 40-character run of it)"
    return None


def main(argv: "list[str]") -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("target", nargs="?", default="--latest-failed")
    ap.add_argument("--show-anchors", action="store_true",
                    help="LOCAL ONLY: also print anchors and the critics' sentences. "
                         "Refuses to run unless output is a terminal.")
    args = ap.parse_args(argv[1:])

    if args.show_anchors and not sys.stdout.isatty():
        print("REFUSING: --show-anchors prints your passage's anchors and is for reading "
              "on screen, not for redirecting into a file, a pipe or a report. Run it in "
              "a terminal, or drop the flag for the share-safe output.", file=sys.stderr)
        return 2

    target = _latest_failed() if args.target == "--latest-failed" else args.target
    path, record = _load(target)
    text = render(record, show_anchors=args.show_anchors)

    if not args.show_anchors:
        leaked = refuse_if_passage_leaked(text, record)
        if leaked:
            print("REFUSING TO PRINT: the share-safe report contains the owner's "
                  f"{leaked}. Nothing was written. This is the guard failing closed — "
                  "the share-safe render has a bug, and weakening the guard is not the fix.")
            return 2
    print(f"# {path}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
