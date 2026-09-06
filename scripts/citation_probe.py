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
import hashlib
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


# Fields that must never leave this machine in the artifact or on screen.
# `encrypted_content` and `encrypted_index` are the provider's opaque payloads;
# prose is the owner's business and not evidence of anything here.
REDACTED_FIELDS = ("encrypted_content", "encrypted_index", "content", "text",
                   "api_key", "authorization")


def _sha8(x) -> str:
    return hashlib.sha256(str(x).encode("utf-8", "replace")).hexdigest()[:8]


def _count_citations_in_dump(node, out) -> None:
    """Walk a serialized response counting `citations` WITHOUT keeping any of
    it. Nothing from the dump is stored — only counts, types and lengths."""
    if isinstance(node, dict):
        for k, v in node.items():
            if k in ("encrypted_content", "encrypted_index"):
                out["opaque_fields_seen"][k] = out["opaque_fields_seen"].get(k, 0) + 1
                out["opaque_lengths"].append(len(str(v)))
                continue
            if k == "citations" and isinstance(v, list):
                out["n"] += len(v)
                for c in v:
                    if isinstance(c, dict):
                        out["citation_keys"] |= set(c.keys())
                        if c.get("cited_text"):
                            out["n_with_cited_text"] += 1
                            out["cited_text_lengths"].append(len(str(c["cited_text"])))
                continue
            _count_citations_in_dump(v, out)
    elif isinstance(node, list):
        for v in node:
            _count_citations_in_dump(v, out)


def _serialized_view(response) -> dict:
    """THE THIRD ACCESS FORM. If citations exist in the serialized response but
    the collector missed them, that is conclusively a collector or SDK-access
    defect and not a finding about the provider. Nothing from the dump is
    kept: counts, key names, types and lengths only."""
    out = {"available": False, "n": 0, "n_with_cited_text": 0,
           "citation_keys": set(), "cited_text_lengths": [],
           "opaque_fields_seen": {}, "opaque_lengths": [], "how": ""}
    dump = None
    for how in ("model_dump", "dict", "to_dict"):
        fn = getattr(response, how, None)
        if callable(fn):
            try:
                dump = fn()
                out["how"] = how
                break
            except Exception:
                continue
    if dump is None:
        out["how"] = "unavailable — the response object exposes no serializer"
        return {k: (sorted(v) if isinstance(v, set) else v) for k, v in out.items()}
    out["available"] = True
    _count_citations_in_dump(dump, out)
    return {k: (sorted(v) if isinstance(v, set) else v) for k, v in out.items()}


def _usage(response) -> dict:
    """Actual usage as the response reports it, when it reports it. Never
    estimated, never inferred from elapsed time."""
    u = getattr(response, "usage", None)
    if u is None:
        return {"reported": False,
                "why": "the response object exposed no usage field"}
    d = {}
    for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
              "cache_read_input_tokens"):
        v = getattr(u, k, None)
        if v is not None:
            d[k] = v
    sr = getattr(u, "server_tool_use", None)
    if sr is not None:
        d["web_search_requests"] = getattr(sr, "web_search_requests", None)
    return {"reported": bool(d), **d}


def _raw_shape(response) -> dict:
    """What the response carried, by ATTRIBUTE and by MAPPING KEY.

    The collector reads `citations` as an attribute. If a build exposes it as
    a mapping key instead, "no citations arrived" and "we could not see them"
    are indistinguishable from outside — the same shape as the bug this block
    began with. The serialized view above is the third, decisive form.

    No prose, no opaque payloads: block types, booleans and counts only."""
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
            "stop_reason": getattr(response, "stop_reason", None),
            "serialized": _serialized_view(response),
            "usage": _usage(response)}


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
        # ONE SEARCH USE PER CALL. The app's own tool allows five; a probe
        # that is measuring whether citations appear at all has no business
        # spending five searches to find out, and a capped probe is the only
        # honest thing to quote a price for.
        one_use = dict(gw.WEB_SEARCH_TOOL, max_uses=1)
        raw = gw._create(question, tools=[one_use])
        out["search_cap"] = 1
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
    ser = (out.get("raw") or {}).get("serialized") or {}
    out["n_cited"] = len(cited)
    out["n_excerpts"] = excerpts
    # PER-CALL OUTCOME. The decisive one is the serialized view: citations
    # present there but absent through the collector is conclusively a defect
    # HERE, and must never be filed as a finding about the provider.
    if ser.get("n") and not cited:
        out.update(outcome="collector_defect",
                   why="The serialized response carries citation objects and the collector "
                       "returned none. That is a defect in this client's access path, not a "
                       "fact about the provider.")
    elif cited:
        out.update(outcome="native_citation_observed",
                   why="The provider emitted citation objects and the collector kept them.")
    else:
        out.update(outcome="ran_no_native_citation_observed",
                   why="A capped search-enabled call completed and no citation object appeared "
                       "in the serialized response by any access path. A finding about this "
                       "response, not about the collector.")
    return out


def verdict(paraphrasing: dict, quoting: dict | None) -> dict:
    """The narrow reading, across both calls. Nothing wider is licensed by two
    calls — in particular, citations appearing only on the quote-demanding
    question does NOT establish that the provider cites only quotations. It
    establishes that this probe's result was prompt-sensitive."""
    if paraphrasing.get("outcome") == "not_run_missing_credential":
        return {"verdict": "not_run_missing_credential",
                "why": paraphrasing.get("why", ""),
                "licensed": "Nothing about the provider. No call was made."}
    if quoting is None:
        return {"verdict": "incomplete", "why": "the second call did not run"}
    a, b = paraphrasing.get("outcome"), quoting.get("outcome")
    if "collector_defect" in (a, b):
        return {"verdict": "collector_defect",
                "why": "Citations exist in the serialized response and the collector did not "
                       "return them.",
                "licensed": "This is a defect in this client. It says nothing about the "
                            "provider's behaviour, and the 3,781 historical rows remain "
                            "unexplained by it."}
    if a == b == "native_citation_observed":
        return {"verdict": "native_capture_confirmed",
                "why": "Both calls produced citation objects and the collector kept them.",
                "licensed": "Production citation capture works for this account and model, on "
                            "these two questions."}
    if b == "native_citation_observed":
        return {"verdict": "capability_confirmed_prompt_sensitive",
                "why": "Citations appeared on the question that demanded a verbatim quotation "
                       "and not on the one that allowed a paraphrase.",
                "licensed": "The capability exists here. NOT licensed: that the provider cites "
                            "only quotations. Two calls cannot establish a provider rule, and "
                            "the documentation describes citations as attached to grounded "
                            "response text rather than to literal quotation."}
    if a == "native_citation_observed":
        return {"verdict": "capability_confirmed_prompt_sensitive",
                "why": "Citations appeared on the paraphrasing question and not on the quoting "
                       "one, which is the reverse of the expected direction.",
                "licensed": "The capability exists here. The direction of the difference is "
                            "unexplained by two calls."}
    return {"verdict": "ran_no_native_citation_observed",
            "why": "Neither call produced a citation object in the serialized response by any "
                   "access path.",
            "licensed": "A finding about this account and model on these two questions. NOT "
                        "licensed: that the provider never emits citations, or that the "
                        "collector is at fault."}


def _no_secrets(doc) -> list:
    """Nothing leaves this machine that should not. Walks the artifact before
    it is written and names any field that must never appear in it."""
    bad = []

    def walk(node, path=""):
        if isinstance(node, dict):
            for k, v in node.items():
                if k in ("encrypted_content", "encrypted_index", "api_key",
                         "authorization", "cited_text"):
                    bad.append(f"{path}.{k}")
                walk(v, f"{path}.{k}")
        elif isinstance(node, list):
            for i, v in enumerate(node):
                walk(v, f"{path}[{i}]")
    walk(doc)
    return bad


if __name__ == "__main__":
    r = probe(quoting=False)
    r2 = probe(quoting=True) if r.get("outcome") != "not_run_missing_credential" else None
    v = verdict(r, r2)
    doc = {"probe": "citation_capture.v2", "at": cli._now(),
           "paraphrasing": r, "quoting": r2, "verdict": v}

    leaked = _no_secrets(doc)
    if leaked:
        # Refuse rather than write it. A probe that leaks the thing it was
        # told not to carry is worse than a probe that did not run.
        print("REFUSING TO WRITE: the artifact carries fields it must not: "
              + ", ".join(leaked))
        raise SystemExit(4)

    print(json.dumps(doc, indent=2, ensure_ascii=False))
    print()
    print(f"paraphrasing call : {r.get('outcome')}")
    if r2:
        print(f"quote-demanding   : {r2.get('outcome')}")
    print()
    print(f"VERDICT: {v['verdict']}")
    print(v.get("why", ""))
    print()
    print("What this licenses: " + v.get("licensed", ""))
    print()
    print("And what it never licenses, whatever it says — this is provenance, "
          "not verification: a provider-returned result "
          "or a native citation is DISCOVERY AND PROVENANCE METADATA. A claim becomes "
          "Nikodemus-verified only after the source is admitted, retrieved through "
          "Nikodemus, and bound to an exact Library anchor. Perfect native citation "
          "capture is still not verification.")

    # Never into local_state: the probe measures the provider, it is not an
    # event in the owner's corpus, and a measurement filed as a record would
    # be the first thing to confuse the two.
    dest = pathlib.Path.home() / "Downloads" / "citation-probe.json"
    try:
        dest.write_text(json.dumps(doc, indent=2, ensure_ascii=False))
        print(f"\nSaved to {dest}")
    except OSError:
        pass
    raise SystemExit(0 if r.get("outcome") != "not_run_missing_credential" else 3)
