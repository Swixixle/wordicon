#!/usr/bin/env python3
"""Read-only. Print the per-candidate Friction reasons and anchor-support
notes from ONE component's run record, and nothing else.

Block 119, under the owner's ruling: the malformed evidence packet is
proven (a constraint requiring a word the chosen anchor does not contain),
but whether the candidates ALSO overreached on their own is unresolved.
That question is answered by reading the stored verdicts, not by changing
anchor selection — which this script cannot do and must not.

WHAT THIS REFUSES TO PRINT, by construction rather than by care:
`input_text` and `source_text` — the owner's passage — never leave the
file. The anchor is printed because it is the span the verdicts are ABOUT
and the whole question is whether it can carry them; nothing wider is.
The refusal is enforced after rendering, against the rendered text, so a
future field that smuggles the passage in under another name is caught by
the same check rather than by remembering to exclude it.

    python3 scripts/inspect_component.py <trace_id|path>
    python3 scripts/inspect_component.py --latest-failed
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
RESULTS = ROOT / "local_state" / "results"

# Never rendered. Not a filter over what we happened to build — the check
# below re-reads the record for these and refuses to print if any survived.
FORBIDDEN_FIELDS = ("input_text", "source_text", "forge_input", "gist")


def _load(arg: str) -> "tuple[Path, dict]":
    p = Path(arg)
    if not p.exists():
        p = RESULTS / (arg if arg.endswith(".json") else f"{arg}.json")
    if not p.exists():
        raise SystemExit(f"no such record: {arg}")
    return p, json.loads(p.read_text())


def _latest_failed() -> str:
    """The most recent composite run that did not complete. Named by its
    own record, not guessed from filenames."""
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


def render(d: dict) -> str:
    out: "list[str]" = []
    w = out.append
    mode = d.get("mode", "")
    w(f"record       {d.get('trace_id','')}  ({mode})")
    w(f"completion   {d.get('completion','')}  ·  "
      f"{d.get('n_completed','?')} of {d.get('n_components','?')} components analysed")
    att = d.get("attempt_summary") or {}
    if att:
        w(f"attempts     {att.get('http_attempts','?')} HTTP attempt(s), "
          f"{att.get('attempts_failed','?')} failed  ·  {att.get('population','')}")
    else:
        w("attempts     not recorded — this run predates the attempt ledger")
    w("")

    groups = d.get("groups") or d.get("components") or []
    for g in groups:
        label = g.get("label", "")
        if g.get("failed"):
            w(f"── {label}  —  NOT ANALYSED")
            w(f"     {g.get('failure_explanation','')}")
            w(f"     stored error: {str(g.get('error',''))[:300]}")
            w("")
            continue
        w(f"── {label}")
        anchor = g.get("anchor", "")
        if anchor:
            w(f"     anchor        “{anchor}”")
            w(f"     anchor_verified {g.get('anchor_verified')}")
        beyond = g.get("constraint_beyond_anchor") or []
        if beyond:
            w(f"     CONSTRAINT REQUIRES, ANCHOR LACKS: {', '.join(map(str, beyond))}")
            w("     (the packet is malformed here; verdicts below inherit that)")
        cands = g.get("candidates") or []
        if not cands:
            w(f"     candidates live in this component's own run: {g.get('trace_id','')}")
            w("     re-run this script against that trace id for the verdicts")
        for c in cands:
            bff = c.get("bff") or c
            fr = bff.get("friction") or {}
            w(f"     • {bff.get('title','')}")
            w(f"         friction verdict     {fr.get('verdict','')}")
            if fr.get("contradicts_anchor"):
                w("         contradicts_anchor   True")
            if fr.get("source_contradiction"):
                w(f"         source_contradiction {fr['source_contradiction']}")
            if fr.get("reason"):
                w(f"         reason               {fr['reason']}")
            if fr.get("hostile_read"):
                w(f"         hostile_read         {fr['hostile_read']}")
            sup = bff.get("claim_support") or bff.get("support") or {}
            if sup:
                w(f"         support              {sup.get('support','')}")
                if sup.get("note"):
                    w(f"         support note         {sup['note']}")
                if sup.get("deciding_anchor_words"):
                    w(f"         deciding anchor words {sup['deciding_anchor_words']}")
        w("")
    return "\n".join(out)


def refuse_if_passage_leaked(text: str, record: dict) -> "str | None":
    """Rendered output is checked AGAINST THE RECORD, not against a list of
    keys we remembered to skip. If any run of the owner's prose made it
    into the page, this says so and prints nothing."""
    for field in FORBIDDEN_FIELDS:
        for value in _all_values(record, field):
            if not isinstance(value, str):
                continue
            for chunk in _chunks(value):
                if chunk and chunk in text:
                    return f"{field} (a {len(chunk)}-character run of it)"
    return None


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
    for i in range(0, max(0, len(t) - size + 1), size):
        yield t[i:i + size]


def main(argv: "list[str]") -> int:
    arg = argv[1] if len(argv) > 1 else "--latest-failed"
    if arg == "--latest-failed":
        arg = _latest_failed()
    path, record = _load(arg)
    text = render(record)
    leaked = refuse_if_passage_leaked(text, record)
    if leaked:
        print("REFUSING TO PRINT: the rendered report contains the owner's "
              f"{leaked}. Nothing was written. This is the script's own guard "
              "failing closed, not a problem with the record.")
        return 2
    print(f"# {path}")
    print(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
