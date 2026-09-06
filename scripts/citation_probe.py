#!/usr/bin/env python3
"""The production citation probe (block 113, landed block 117).

WHY THIS EXISTS. A census of the owner's store found 3,781 citation rows, all
labelled `searched`, none `cited` — caused by a collector that walked the
provider's response once and kept the first label it saw. That collector is
fixed and proved against the documented response shape and against fixtures.

What no test here can establish is whether a REAL search-enabled call emits
native citation objects at all. Nothing in the build environment may reach a
provider, by standing law. So the claim "production citation capture works"
is unconfirmed until this runs on the owner's own machine.

THREE OUTCOMES, AND THEY MUST STAY THREE.

  not_run_missing_credential   no key was present. Says NOTHING about the
                               provider. Collapsing this into "no citations"
                               would hide the difference between not looking
                               and looking and finding nothing.
  ran_no_native_citation_observed
                               a real search-enabled call was made and the
                               response carried no citation objects. This is a
                               finding ABOUT THE PROVIDER, not about the
                               collector.
  native_citation_observed     citations came back, and the collector kept
                               them.

Run it:   .venv/bin/python scripts/citation_probe.py
It makes ONE search-enabled call and writes nothing into the corpus.
"""
import json
import os
import pathlib
import sys

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))
import wordicon_cli as cli  # noqa: E402

QUESTION = ("In one sentence, what is the current stable release version of "
            "the Python programming language? Cite your source.")


def probe() -> dict:
    out = {"probe": "citation_capture.v1", "at": cli._now(), "question": QUESTION}
    if not os.environ.get("ANTHROPIC_API_KEY"):
        out.update(outcome="not_run_missing_credential",
                   why="No ANTHROPIC_API_KEY in the environment. This says nothing "
                       "about whether the provider emits citations — only that no "
                       "call was made.")
        return out
    model = os.environ.get("WORDICON_MODEL", "")
    if not model:
        out.update(outcome="not_run_missing_credential",
                   why="A key is present but WORDICON_MODEL is not set, and this "
                       "project never guesses a model. Set it and run again.")
        return out
    # Built through the app's OWN factory, not by naming a class here. The
    # first version called AnthropicAPIGateway() with no arguments and the
    # suite's stub took none either, so the test proved the probe's logic and
    # nothing about how it constructs a gateway. It failed on the owner's
    # machine at the first real run.
    gw = cli.make_gateway("anthropic", model)
    out["gateway"] = getattr(gw, "name", "")
    try:
        text, citations = gw.complete_with_search(QUESTION)
    except Exception as e:  # noqa: BLE001 — the failure IS the finding
        out.update(outcome="not_run_missing_credential",
                   why=f"The call did not complete: {cli.explain_component_failure(str(e))[:300]}. "
                       "Recorded as not-run rather than as an absence of citations, "
                       "because a call that failed observed nothing.")
        return out

    counts = cli.acquisition_counts(citations)
    out["acquisition"] = counts
    out["n_sources"] = len(citations or [])
    out["text_chars"] = len(text or "")
    # The whole point: did any row carry the observation that the PROSE cited it?
    cited = [c for c in (citations or []) if cli.PROSE_CITED in (c.get("observed") or [])]
    excerpts = sum(len(c.get("provider_citation_excerpts") or []) for c in (citations or []))
    if cited:
        out.update(outcome="native_citation_observed",
                   n_cited=len(cited), n_excerpts=excerpts,
                   why="The provider emitted citation objects and the collector kept "
                       "them. Production citation capture is confirmed.")
    else:
        out.update(outcome="ran_no_native_citation_observed",
                   n_cited=0, n_excerpts=excerpts,
                   why="A real search-enabled call completed and no row carried a "
                       "prose citation. This is a finding about the provider's "
                       "response, not about the collector — the collector was "
                       "handed nothing to keep.")
    return out


if __name__ == "__main__":
    r = probe()
    print(json.dumps(r, indent=2, ensure_ascii=False))
    print()
    print(f"OUTCOME: {r['outcome']}")
    print(r["why"])
    # Not written into local_state: the probe is a measurement of the provider,
    # not an event in the owner's corpus.
    dest = pathlib.Path.home() / "Downloads" / "citation-probe.json"
    try:
        dest.write_text(json.dumps(r, indent=2, ensure_ascii=False))
        print(f"\nSaved to {dest}")
    except OSError:
        pass
    raise SystemExit(0 if r["outcome"] != "not_run_missing_credential" else 3)
