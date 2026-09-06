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

# TWO QUESTIONS, BECAUSE THE FIRST RUN WAS UNDER-DETERMINED.
#
# The first probe asked for one sentence and got 271 characters of prose with
# nine results returned and nothing cited. That is a real observation and it
# does not distinguish three different worlds:
#
#   (a) this account/model never emits citation objects;
#   (b) it emits them only when the model QUOTES a source, and a one-sentence
#       paraphrase gives it nothing to attach one to;
#   (c) it emits them and this client cannot read them — the collector reads
#       `citations` as an attribute, and an SDK build that exposes it as a
#       dict key would look identical to "none arrived".
#
# So: one question that paraphrases, one that demands a verbatim quotation,
# and a raw pass that reports what the response actually carried. (c) is now
# separable from (a) and (b), and (b) from (a).
QUESTION = ("In one sentence, what is the current stable release version of "
            "the Python programming language? Cite your source.")
QUOTING_QUESTION = (
    "Find a source stating the current stable release version of Python. "
    "Quote one sentence from it VERBATIM, in quotation marks, and name the page "
    "you took it from. Do not paraphrase the sentence you quote.")


def _raw_shape(response) -> dict:
    """What the response actually carried, by both access paths.

    The collector reads `citations` as an ATTRIBUTE. If a build exposes it as
    a mapping key instead, "no citations arrived" and "we could not see them"
    are indistinguishable from the outside — which is the same shape as the
    bug this whole block began with."""
    blocks = []
    attr_seen = key_seen = 0
    for b in getattr(response, "content", None) or []:
        row = {"type": type(b).__name__,
               "block_type": getattr(b, "type", None),
               "has_text": hasattr(b, "text")}
        by_attr = getattr(b, "citations", None)
        by_key = b.get("citations") if isinstance(b, dict) else None
        row["citations_by_attribute"] = None if by_attr is None else len(by_attr)
        row["citations_by_key"] = None if by_key is None else len(by_key)
        if by_attr:
            attr_seen += len(by_attr)
        if by_key:
            key_seen += len(by_key)
        blocks.append(row)
    return {"blocks": blocks, "citations_by_attribute": attr_seen,
            "citations_by_key": key_seen,
            "stop_reason": getattr(response, "stop_reason", None)}


def probe(quoting: bool = False) -> dict:
    out = {"probe": "citation_capture.v2", "at": cli._now()}
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
    question = QUOTING_QUESTION if quoting else QUESTION
    out["question"] = question
    out["asks_for_a_verbatim_quote"] = bool(quoting)
    # The raw pass runs the same call one level lower, so the shape can be
    # reported without trusting the collector to have seen it.
    try:
        raw = gw._create(question, tools=[gw.WEB_SEARCH_TOOL])
        out["raw"] = _raw_shape(raw)
        text, citations = cli.collect_citations(raw.content)
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
    # Both questions, because one of them cannot separate (a) from (b).
    r = probe(quoting=False)
    r2 = probe(quoting=True) if r.get("outcome") != "not_run_missing_credential" else None
    both = {"paraphrasing": r, "quoting": r2}
    print(json.dumps(both, indent=2, ensure_ascii=False))
    print()
    print(f"OUTCOME (paraphrasing): {r['outcome']}")
    if r2:
        print(f"OUTCOME (verbatim quote asked for): {r2['outcome']}")
        _attr = (r2.get("raw") or {}).get("citations_by_attribute")
        _key = (r2.get("raw") or {}).get("citations_by_key")
        if _key and not _attr:
            print("\nTHE COLLECTOR CANNOT SEE THEM. Citations arrived as a mapping key and "
                  "the collector reads an attribute. That is a defect here, not at the provider.")
        elif not _attr and not _key:
            print("\nNo citation objects arrived by either access path, on either question. "
                  "That is a finding about the provider's response for this account and model.")
    r = both
    # Not written into local_state: the probe is a measurement of the provider,
    # not an event in the owner's corpus.
    dest = pathlib.Path.home() / "Downloads" / "citation-probe.json"
    try:
        dest.write_text(json.dumps(r, indent=2, ensure_ascii=False))
        print(f"\nSaved to {dest}")
    except OSError:
        pass
    raise SystemExit(0 if both["paraphrasing"]["outcome"] != "not_run_missing_credential" else 3)
