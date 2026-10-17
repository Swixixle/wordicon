# Go deeper: evidence and contingencies

This extends the first Go deeper slice. A search citation or a model saying it
checked something is insufficient. The live lane now obtains source bytes,
extracts text, and locates the starting quotation with the existing Moira
matcher. The result shows the passage, URL, section offsets, match method and
body SHA-256. This proves wording presence in those retrieved bytes. It does
not certify authorship, an edition's authority, or an interpretation. Existing
source-admission and support-ruling rules remain in force.

## The plan is approved before work

New proposals freeze a research plan with at most:

- Three search requests, with one provider search allowed in each.
- Six credential-free public source reads, each limited to 2 MiB and three
  revalidated redirects. Redirects can make additional HTTP GETs within that
  read allowance. Only public HTML and plain text are supported.
- Four model requests total: up to three discovery requests and one tool-free
  explanation. Each has one HTTP attempt; SDK retries are disabled. The
  ordinary model output ceiling remains 24,000 tokens per request. That is
  an output limit, not a limit on billable input or total price.

Search, model input and model output can all incur charges. Provider-internal
search processing can substantially increase input tokens. The proposal says
the total price is unknown; this is a bounded-work plan, not a dollar cap.
There are no background runs. The mock lane remains one offline fixture and
does not fetch sources. Previously frozen proposals without a research plan
retain the original single-call behavior; prepare a new proposal to use this
feature. Other lanes retain their existing search allowances.

The configured model receives the focused record, recent context, failure
summaries and bounded source excerpts. Public source hosts receive GETs for
their URLs. Browser cookies, credentials and producer connector secrets are
not sent. The fetcher rejects private and mixed-address DNS answers and pins
the validated address; TLS verifies the original host. Redirects are checked
again. PDF, images, archives, login pages and JavaScript-only shells are named
gaps, never passed off as primary text. Mislabeled binary bytes are refused.
Connection/read timeouts apply; DNS uses the operating system resolver's
timeout. Provider streaming timeouts are inactivity limits, not a wall-clock
completion guarantee.

## What happens when a route fails

The controller first considers saved, unused leads. Discovery then tries a
readable primary text, a different edition/archive, and a more precise
passage search. Later requests receive actual earlier failures. Newly returned
alternate leads take priority over unused earlier leads. A model saying
"every search failed" cannot cancel the mechanical source checks. An empty
discovery explanation cannot discard otherwise usable returned citations.

Actual returned URLs, not model-authored JSON citation fields, supply the
candidate queue. Retrieved bodies, extraction metadata and step outcomes are
saved before the explanation is requested. An exact or normalized match is
marked `quote_located`; a paraphrase or absent quotation can only reach
`source_text_obtained`. An unmatched quote remains `needs_more_evidence`.
Absence from one retrieved edition does not prove a quotation false.

The final model receives up to 12,000 source-excerpt characters. Matched
passages and current-question sources take priority over older material.
For other passages, deterministic term overlap selects a bounded window from
the complete extracted text, including later chapters. That selection is
labeled with offsets and method and does not verify relevance. Omitted text
is disclosed. Generated prose remains advisory and may still be wrong; the
mechanical evidence panel is independent of it.

## Continue without losing the work

`Continue checking` creates another proposal bound to the saved result and
the same evidence target. It rechecks source hashes, reuses saved bytes and
avoids repeating completed reads. A new approved pass can retry transient
timeouts, rate limits or server failures once per URL. Permanent failed
routes remain recorded while other candidates are tried.

An ordinary new follow-up has its own question-focused discovery. An old
quotation match cannot finish that new question. If the provider returns a
previously saved full-work URL again, its bytes can supply a newly selected
excerpt without another download. A source-only continuation with an available
answer also performs fresh discovery; retrying an unavailable final answer
can reuse evidence without another search.

If the final model request fails or returns unusable JSON, a deterministic
status card keeps the evidence and offers continuation. The run does not
invent a completed scholarly answer. No source is automatically admitted to
the owner's Library, and no writing or keeper judgment changes.

## Records and limitations

Each live pass writes `local_state/deeper_evidence/<trace_id>/` beneath the
configured local state: content-addressed bodies, extraction records, separate
step events and a checkpoint with the frozen context and exact model prompts
and returned prose. The result includes source references, per-request
acquisition records, model-call identities and the evidence status.

Search records distinguish provider-reported usage, named search attempts,
result-block outcomes and error codes, including empty results and cap errors.
Provider-internal code-execution blocks are recorded separately. These fields
do not assert what the model read and are not an independent billing invoice.
Unknown usage remains unknown after an ambiguous failure.

Completed-result continuation is wired. Checkpoints also preserve work from
an interrupted process, but there is no UI for resuming an interrupted
checkpoint that never produced a result. The existing uncertain-operation
handling remains in force and does not automatically replay spending.
This build does not add PDF/OCR, authenticated browsing, a second provider,
cryptographic signing of fetched pages, or a claim that arbitrary research
questions can be conclusively proved. Source hashes establish byte identity,
not source authority.

## Verification

All automated checks use fixtures, synthetic HTTP transports or mocked
source retrieval. They exercise the real controller, extractor, matcher,
file persistence and UI without live model calls. Failed-source/alternate-
success scenarios, misleading discovery prose, budgets, cached-byte tampering,
late-chapter selection and final-answer failure have explicit checks.

```sh
python -m pytest tests/test_deeper.py tests/test_deeper_integration.py \
  tests/test_acquisition_usage.py tests/test_evidence_fetch.py \
  tests/test_evidence_research.py tests/test_producer_launch.py \
  tests/test_connect_instruments.py -q
python tests/test_global_constraints.py
PYTHON=python bash tests/journeys/run-deeper.sh
node tests/journeys/deeper-evidence.js
```

Prepared against `38b94207cbcf9f1e6d40249df08cc10e215558a1`. Apply the patch
on a branch of the current Mac checkout, preserving newer Ledger, backup,
Deflate and front-door changes. No schema file or migration is changed. This
cloud build has not changed the Mac launcher or proved live retrieval/Safari
behavior. Final check counts and patch application instructions accompany the
delivery package.
