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
failed final answer from a completed revision-two-or-later pass whose useful saved
excerpts pass current hash, extraction and lexical checks again.

Revision three addresses an honestly unsuccessful Dante run: two inherited
reads and four reads after two searches exhausted the allowance before the
last search strategy. All six requests failed, including a PDF the reader
could not extract and two book listings. The controller now reserves a read
for each remaining search strategy, orders likely supported text before
catalog and unsupported-format hints, and distinguishes failed retrieval
from a failed lexical screen. These are routing improvements, not a promise
that any particular source will be reachable.

Revision four addresses the first live revision-three pass: its two initial
reads went to leads inherited from an earlier, differently-aimed step, each
one recorded by the ranking itself as matching no meaningful question or
work term. When nothing pending shows any meaningful overlap, the initial
read batch now waits for the first search's fresh leads. The rule stays
defer-never-exclude: the carried leads remain saved and ranked, later
batches may still read them once discovery has had its chance, a URL the
previous pass recorded as retryable keeps its promised once-per-pass retry
whatever its lexical score, and the deferral is written into the pass's own
steps with its reason. Lexical absence is not irrelevance; this changes
when carried leads are read, never whether they may be.

Revision five addresses the reading problem's first slice, pinned from the
deployed Shakuntala records: the pass held Ryder's full translation in
custody — the Act IV departure gift and Act VI lament included — while the
final model request packed the same Act I window twice beside navigation
chrome and a references region, steered partly by the question template's
own framing words. Three repairs. Retail product routes (/dp/<id>,
/gp/product/<id>) now rank as catalog hints — URL shape only, deferred and
never excluded — and an ISBN in a title is a weak clue alone, since
legitimate full-text pages print ISBNs too. The template's framing
vocabulary (help, understand, idea, context, terms and kin) no longer
counts as question substance, so windows anchor on the question's real
terms. And a reused saved text ADVANCES: the controller passes each
capture the windows already shown to the model for that text (by body
hash, or by URL when a site re-serves changed bytes), selection prefers
any matching window not yet shown, the advancement is counted in the
record, and when only an already-shown window matches it is reselected
with that said by name. A mirror of the same work under a different URL
with different bytes is a named open limitation, not silently equated.
Advancement changes which passage is shown next; it does not verify
relevance, work identity or answer support.

Revision six gives one approved Start enough room for a larger research pass:
six searches, eighteen source reads, seven model requests and up to 60,000
source-passage characters in the answer request. It also selects several distinct
passages from each saved body for the answer request during the same pass. A whole work in custody
must not be represented only by the first locally promising window, nor should
the owner need another Continue press just to inspect its later sections.
These are work allowances, not a claim that every question can be answered or
that a particular dollar total or completion time is guaranteed.

## The plan is approved before work

New proposals freeze a research plan with at most:

- Six discovery requests, with one provider search allowed in each.
- Eighteen credential-free public source reads, each limited to 2 MiB and three
  revalidated redirects. Redirects can make additional HTTP GETs within that
  read allowance. Only public HTML and plain text are supported.
- Seven model requests total: up to six discovery requests and one tool-free
  explanation. Each has one HTTP attempt; SDK retries are disabled. The
  ordinary model output ceiling remains 24,000 tokens per request. That is
  an output limit, not a limit on billable input or total price.
- Up to six distinct 3,000-character passages per saved source body, with a
  60,000-character total source-text allowance for the final answer request.
  Reading further within saved bytes does not incur another source download.

Search, model input and model output can all incur charges. Provider-internal
search processing can substantially increase input tokens. The proposal says
the total price is unknown; this is a bounded-work plan, not a dollar cap.
There are no background runs. The mock lane remains one offline fixture and
does not fetch sources. Previously frozen proposals without a research plan
retain the original single-call behavior; prepare a new proposal to use this
feature. Frozen research proposals from an earlier revision are refused before
dispatch; prepare a new revision-six proposal so its larger allowance is
explicit before Start. A pass may use more
of the same disclosed allowance than an older stopping policy did. Other
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

The controller first considers saved, unused leads. Discovery uses the six
strategies frozen in the proposal to find readable primary texts, alternate
routes and more specific passages. Every read batch leaves at least one read
available for each remaining search strategy. Empty or failed searches do not
release later strategies' reservations early; unused reads become available
once the discovery strategies have run. Quotation matches and revalidated
answer-only retries retain their shortcuts. The larger allowance is a ceiling,
not a requirement to spend all seven model requests after the requested
wording has already been located.

Discovery is explicitly told that the reader accepts public HTML/plain text,
and to seek a supported edition when a PDF or blocked route cannot be read.
Later requests receive actual earlier failures, including a bounded summary
of outcomes carried from a previous pass. The whole pending queue first
orders possible text ahead of catalog-like links and unsupported-format
hints, then uses distinct meaningful work/question terms and text metadata;
newer strategies win ties. Catalog URL patterns and file suffixes are hints,
not hard exclusions: the links remain saved and may still be attempted if
no better candidate is pending. Domains receive no reputation bonus. A model saying
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

The final model receives up to 60,000 source-passage characters. Matched
passages and current-question sources take priority over older material.
For other passages, selection considers the complete extracted text and can
supply up to six distinct windows of at most 3,000 characters from each saved
body during this same run. Generic numbered section and chapter boundaries
help spread the selections through a work instead of exhausting the allowance
on one early scene. Each supplied passage retains its source, body hash,
section and text offsets. Identical bodies under different URLs do not consume
the answer allowance twice. Changed bytes are not assumed to share offsets
with an older body, even when the URL is unchanged.

Only passage ranges actually packed into the final answer request enter the
shown-window ledger. Later passes prefer matching unshown ranges; forced reuse
is recorded. Older revision-five records without that ledger use their recorded
excerpt selection as a compatibility assumption; that metadata does not recover
their actual final-prompt manifest. A mirror
with different bytes is still a separate body; no equivalence is invented.
Generic question-framing terms such as help, understand and context do not steer
selection. Concept words such as will remain eligible. Selection and screening
are heuristic: larger input and chapter distribution do not verify relevance,
work identity or answer support. Omitted text is disclosed. Generated prose
remains advisory and may still be wrong; the mechanical evidence panel is
independent of it.

When the recorded readable-source count is explicitly zero, the result puts
"No source text retrieved" above the explanation and identifies the model
explanation as unverified. That count cannot establish whether the model used
recall, the supplied context or inference. A failed final answer gets a separate unavailable
notice. Readable-but-excluded excerpts get a distinct warning. Missing legacy
counts are not treated as zero; reused readable sources still count as
evidence even when the current pass makes no new source requests. New records
distinguish newly readable source reads from saved reads reused, and report the
passage count, distinct saved-body count and source characters actually supplied
to the answer request. These counts do not assert model understanding. Legacy
records explicitly leave the new/reused split unknown. Fixture results keep
their fixture identification.

Excerpt screening records meaningful question/work matches and generic
catalog or access-page hints. A useful passage merely mentioning a catalog
is not rejected for that noun alone. Weak excerpts are held out of final
answer grounding, with their bytes and reasons retained. This is a lexical
heuristic: translations, synonyms and difficult questions can be falsely
excluded. Passing it does not certify a passage as the work itself or as
support for the answer. Saved references prefer useful earlier excerpts over
later weak reads so continuation retains the best available source. Up to
eighteen distinct saved bodies carry forward, with omitted-reference counts
recorded; duplicate appearances cannot displace all the other works.
Up to 128 submitted-window descriptors per carried body travel to the next
pass. Older omitted descriptors are counted; the original checkpoints remain.
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
can reuse a completed revision-two-or-later pass with revalidated useful excerpts
without another search. An older landing-page result has no such shortcut.
For revision-six records, this retries the failed answer's exact submitted
passages in their original order. Body, representation, section and passage
hashes and offsets are rechecked. A missing body, descriptor or required hash
records a replay gap and reopens discovery instead of silently substituting
weaker passages. Legacy records without a manifest re-extract their best
available passages without treating the failed request as a completed reading.

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
late-chapter selection and final-answer failure have explicit checks. Revision
six checks the actual answer prompt for distinct located passages from Acts I,
IV and VI in one pass. This proves those located passages were supplied to the
answer request; it does not prove model understanding. The browser journey checks the 6/18/7 proposal, 60,000-character
allowance, new/reused counts and supplied passage volume, while retaining the
revision-five checks for populated attempts in both stacked results.

```sh
python -m pytest tests/test_deeper.py tests/test_deeper_integration.py \
  tests/test_acquisition_usage.py tests/test_evidence_fetch.py \
  tests/test_evidence_research.py tests/test_evidence_quality.py \
  tests/test_quoteless_research.py tests/test_retrieval_routes.py \
  tests/test_producer_launch.py \
  tests/test_connect_instruments.py -q
python tests/test_global_constraints.py
PYTHON=python bash tests/journeys/run-deeper.sh
node tests/journeys/deeper-evidence.js
```

Revision six is prepared against the supplied revision-five commit `c096409`
on `candidate-r89`. Revision three was prepared against
`d329c19c7691bcfc7ce391e91e21dcc3886c2fd3`.
Revision two was based on `1abc1ecc9eb4be8a766e428e0b0aa05053d124e3`.
The original evidence package was based on `38b94207cbcf9f1e6d40249df08cc10e215558a1`.
Apply the incremental patch
on a branch of the current Mac checkout, preserving newer Ledger, backup,
Deflate and front-door changes. No schema file or migration is changed. This
cloud build has not changed the Mac launcher or proved live retrieval/Safari
behavior. Final check counts and patch application instructions accompany the
delivery package.
