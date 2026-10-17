# Go deeper: evidence and contingencies

This extends the first Go deeper slice. A search citation or a model saying it
checked something is insufficient. The live lane now obtains source bytes,
extracts text, and locates the starting quotation with the existing Moira
matcher. The result shows the passage, URL, section offsets, match method and
body SHA-256. This proves wording presence in those retrieved bytes. It does
not certify authorship, an edition's authority, or an interpretation. Existing
source-admission and support-ruling rules remain in force.

Revision two repairs a premature stopping rule reported in a live quoteless
follow-up. Revision one stopped after any readable page, even an audiobook
landing page. It also chose candidates in return order and let rediscovering
a saved URL finish a new question. Revision two separates acquisition status
from the condition that ends the pass. Only an actual quotation match can
stop research early; a question without a quotation target continues through
the approved search/read allowance. The only reuse shortcut is retrying a
failed final answer from a completed revision-two pass whose useful saved
excerpts pass current hash, extraction and lexical checks again.

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
feature. A frozen revision-one research proposal is refused before dispatch;
prepare a new revision-two proposal. Quoteless work may therefore use more
of the same disclosed allowance than the faulty early-stop path did. Other
lanes retain their existing search allowances.

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
passage search. Later requests receive actual earlier failures. The whole
pending queue is ranked by distinct meaningful work/question terms and
text/catalog metadata hints; newer strategies win ties. Domains receive no
reputation bonus. A model saying
"every search failed" cannot cancel the mechanical source checks. An empty
discovery explanation cannot discard otherwise usable returned citations.

Actual returned URLs, not model-authored JSON citation fields, supply the
candidate queue. Retrieved bodies, extraction metadata and step outcomes are
saved before the explanation is requested. An exact or normalized match is
marked `quote_located`. A paraphrase or absent quotation can reach
`candidate_passages_found` only after its bounded research pass has ended,
with explicitly unverified meaning. Readability or keyword matches never
finish that question. All-weak passages and unmatched quotations remain
`needs_more_evidence`, even if readable text was obtained.
Absence from one retrieved edition does not prove a quotation false.

The final model receives up to 12,000 source-excerpt characters. Matched
passages and current-question sources take priority over older material.
For other passages, deterministic term overlap selects a bounded window from
the complete extracted text, including later chapters. Generic terms such as
chapter, ever and his no longer count as substantive overlap. Concept words
such as will are retained. That selection is
labeled with offsets and method and does not verify relevance. Omitted text
is disclosed. Generated prose remains advisory and may still be wrong; the
mechanical evidence panel is independent of it.

Excerpt screening records meaningful question/work matches and generic
catalog or access-page hints. A useful passage merely mentioning a catalog
is not rejected for that noun alone. Weak excerpts are held out of final
answer grounding, with their bytes and reasons retained. This is a lexical
heuristic: translations, synonyms and difficult questions can be falsely
excluded. Passing it does not certify a passage as the work itself or as
support for the answer. Saved references prefer useful earlier excerpts over
later weak reads so continuation retains the best available source.
If a generic question such as "explain more" has no meaningful terms, the
frozen subject supplies the screening terms. The record names that fallback;
the owner's actual question is preserved and no completion shortcut is added.

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
answer also performs fresh discovery. Retrying an unavailable final answer
can reuse a completed revision-two pass with revalidated useful excerpts
without another search. An older landing-page result has no such shortcut.

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

The stop reason is separate: quotation located, source-read allowance reached,
search allowance reached, or completed-pass reuse for an answer retry.
`retrieval_pass_complete` records that the bounded pass ended; it never means
the question was proved or resolved. Final-answer availability is independent.

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
  tests/test_evidence_research.py tests/test_evidence_quality.py \
  tests/test_quoteless_research.py tests/test_producer_launch.py \
  tests/test_connect_instruments.py -q
python tests/test_global_constraints.py
PYTHON=python bash tests/journeys/run-deeper.sh
node tests/journeys/deeper-evidence.js
```

Revision two is prepared against `1abc1ecc9eb4be8a766e428e0b0aa05053d124e3`.
The original evidence package was based on `38b94207cbcf9f1e6d40249df08cc10e215558a1`.
Apply the incremental patch
on a branch of the current Mac checkout, preserving newer Ledger, backup,
Deflate and front-door changes. No schema file or migration is changed. This
cloud build has not changed the Mac launcher or proved live retrieval/Safari
behavior. Final check counts and patch application instructions accompany the
delivery package.
