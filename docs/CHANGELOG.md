# Changelog — Wordicon Sovereign Corpus Blueprint

## v1.16.0 — anchor fit, drawn as five things (block 122)

A run over the owner's own writing produced three candidates that all silently
narrowed a **mid-day** interval into an after-school-to-dinner one the anchor
never contained. The tier that exists to catch exactly that *did* catch it —
and said so in the same row it says almost everything in.

A census of 539 candidate rows in the real corpus: `partial` 54.2%, `topical`
25.0%, `not_run` 11.5%, `supported` 6.3%, `contradicted` 2.4%, `undetermined`
0.6%. A first reading of that called the evaluator nearly vacuous. **That
reading was wrong and is corrected here**: a five-state distribution with a
large modal class establishes no such thing. The evaluator, its thresholds, its
prompts and its stored vocabulary are untouched by this block. What failed was
the drawing.

**The row is named for what it measures.** It was `GROUNDED`, which claims
grounding in the source, or in the world. It compares one claim against **one
quoted span** and nothing else. It is `ANCHOR FIT` now.

**Five states, five marks.** `supported`, `partial`, `topical`, `contradicted`
and `not_run` each say something different and each draw something different.
Before, `contradicted` — the strongest negative the tier can produce — shared a
hollow circle with `topical`, which merely means off-target. The first cut of
this repair gave it the same *filled* circle as `supported` and coloured it
red, which draws the worst result as the best one for anyone not seeing colour;
the journey caught it because the check reads the drawn mark rather than the
state token. A state table can be five-valued underneath and four-valued on the
screen.

**The deciding difference is on the card.** For `partial`, `topical` and
`contradicted`, one compact line names what the claim adds or what is missing —
the reviewer's recorded reason where one exists, otherwise the words it keyed
on, labelled as *words the reviewer selected, not a mechanical proof*. On the
owner's run this would have read: *the reviewer keyed on "mid-day, cradle" in
the anchor and "school, dinner" in the claim.* The methodology and the full
note stay behind the disclosure. Hide explanation; never hide state.

**Advisory, said once.** A first-time reader of this interface asked for a
"speculative mode that lets you play with ideas before they are grounded" —
which is the only mode there is; nothing here has ever blocked a ruling. A row
of circles had read as a gate. The non-gating status is now stated once above
the cards rather than repeated into wallpaper, and the browser proves that
partial, topical and contradicted candidates all still offer Keep, Set aside
and Revise.

The synthetic fixture carries the same structural failure as the run that
prompted this — a broad midday interval narrowed to a school boundary — and the
owner's paragraph is not in the repository. Generation, anchors, owner rulings
and candidate ranking are unchanged.

## v1.15.2 — four laws filed under the wrong heading (block 121c)

Relocation only. Not one word of any law changed, and their attribution to the
blocks that wrote them travelled with them.

Blocks 119 and 120 amended the constitution by appending near a convenient
paragraph, so four laws came to rest inside **The Library — where kept things
live**:

| Law | Now under |
| --- | --- |
| A partial workup is not a reading | **What it will not claim** |
| A failure to run is not a finding | **What it will not claim** |
| What a run cost, in requests rather than renders | **What a run cost, and what it retried** |
| A broken answer is not retried behind your back | **What a run cost, and what it retried** |

A partial run is not an overall reading — that is a refusal to claim, and it
belongs with the refusals. What a run cost and what it retried is execution
provenance; no section under *Where the work happens* covered that, so the two
laws got a subsection there. The five movements were checked for an honest home
before anything was invented, and a sixth movement was not needed.

Three things are pinned that nothing could see before: each law appears
**exactly once** in the constitution, each resolves inside its intended region,
and none remains under the Library heading. A relocation done by copying leaves
two laws that can disagree and a reader who cannot tell which binds; that is now
a named failure. Both modes were sabotaged — wrong heading, and duplicated
rather than moved — and both fail by name.

The compact panel's excerpt for "A failure to run is not a finding" followed its
law. That is the case block 121b's check could not have caught on its own: the
wording stayed verbatim while the destination went stale.

## v1.15.0 — the constitution left the controls (block 121)

The law had reached about nine thousand words on one scroll, inside the home
page's controls, because a standing law amends it every time a wing ships. It
accumulates by design and the interface had no shape that survived that.

The whole of it now lives at **`/constitution`**: five movements in canonical
order, a table of contents, stable anchors, a plain statement opening each
movement, the detail behind a native `<details>`, and one button that opens
everything for reading straight through or printing. The What-is panel became
an orientation — what Nikodemus is, what it refuses to pretend, and the state
of this machine right now — at 405 words instead of 8,979.

The rule the split obeys: **hide explanation when necessary; never hide state.**
The first cut of this block ignored it and moved the provider status, the epoch
control, the encounter switch, the speech instrument and the connected-
instruments readout onto an inert page along with the prose. Those report what
the machine is doing; a document cannot report anything. The suite caught it.

The panel is not a second constitution and cannot quietly become one. It
carries no movement heading and no restatement: each promise is a link with a
`data-canon` attribute, and the suite fails if any of them does not resolve to
a real clause. The binding words exist in one place.

**Every pin moved deliberately.** Twelve groups of constitutional assertions
followed the law to its new file rather than being softened, and the movements
and their order are still pinned — now parsed from the markup the law actually
ships with. Three pins turned out to be fixed-byte windows after a heading
(`[:3000]`, `[:4000]`, `[:6000]`) that had been silently shrinking their
guarded region every time the prose above them grew. They are bounded by the
section's own structure now, and that class of pin is retired.

A new browser journey testifies to the two things source review cannot see: the
disclosure controls open **by keyboard** — a `<div>` styled to look like a
`<summary>` passes every grep and is unreachable without a mouse — and no
runtime state went to the inert page. Both were sabotaged and both fail by name.

**The README is a front door again**: 2,514 words to 1,046, with the rename
moved out of the opening. The legacy name stays wherever it is the real name of
a real thing — the repository, `scripts/wordicon_cli.py`, `WORDICON_MODEL`,
`WORDICON_LAN`, `src/wordicon_corpus/` — because renaming a working command to
tidy a logo is how a setup guide starts lying. One instruction in the first
draft told readers to copy a `.env.example` that does not exist; it was checked
and corrected before this shipped.

**`docs/README.md` is the complete index**, grouped by purpose, and a check
fails if any maintained document in `docs/` is classified by nothing — a new
file cannot become unreachable because someone forgot to link it. The three
pre-rename Sovereign Corpus documents are marked historical with their bodies
untouched, and the capability census now says it is a snapshot rather than a
standing description of runtime truth.

Nothing constitutional was deleted, no epistemic rule was altered while being
reorganised, and no unrelated runtime finding was repaired here.

## v1.14.0 — one retry authority, and two kinds of broken stream (block 120)

Block 119 gave Nikodemus an attempt ledger. This block asks the question the
ledger made askable: **is what it counts actually the number of requests?**

**It is, and now that is proven rather than asserted.** The SDK retries
connection errors, timeouts, 429s and 5xx twice by default; Nikodemus makes
three attempts of its own. Both live would mean up to nine physical requests
per logical call with three in the record. The app has passed `max_retries=0`
since the first tracked commit — but a keyword argument is a claim, so the
suite now counts sends at the transport with an injected fault and asserts
that the recorded number IS the physical number. It is. There is exactly one
retry authority and the declared ceiling equals the real one.

That also settles the arithmetic on the failed workup: twelve application
attempts across the four connection-failure components were twelve physical
sends, not thirty-six.

**A stream can break in two different ways and they are not the same event.**
A response that dies before a single delta arrived produced nothing and may be
retried inside the budget. A response that dies *after* content began was
generated and billed, and we hold a fragment of an answer — retrying that
silently spends the money twice and can return a substantively different reply
with nothing on the page saying so.

The SDK cannot tell them apart. It raises the same `APIConnectionError` either
way, and retries both. So the gateway now walks the stream itself instead of
asking for the finished message, records `partial_stream_failure` or
`stream_failed_before_content`, retries only the second, and hands the first
back to the owner the way a rate limit is handed back. The concrete transport
class is what lands in the record; `StreamInterrupted` is a carrier for the
distinction, not a diagnosis.

**The historical timeout is explained, by exact match.** A raw transport
exception raised mid-stream escapes the SDK unwrapped, was not in the old
retry loop's transient tuple, and reached the soft-fail handler with its own
message intact — `"The read operation timed out"`, character for character
the string in that run's record, on both anthropic 1.0.0 and 1.4.0. That
component made **one attempt, not three**. It is now retried like any other
pre-content failure.

A correction worth keeping: an earlier pass reported this hypothesis
*refuted*. That measurement used a bare iterator as the response body; httpx
asserts on anything that is not a `SyncByteStream`, and the assertion
surfaced as a pre-request `APIConnectionError` — so every "stream failure" it
measured was really a connection failure, and the streaming path was never
exercised. A transport test that does not use a real transport type is
testing its own mock. The fixture subclasses `SyncByteStream` for that reason.

**Every attempt now names its client.** `requirements.txt` declares
`anthropic>=0.40`, unpinned, so the owner's Mac (1.0.0), the build container
(1.4.0) and CI (newest on the day) each resolve a different one. Behaviour was
measured identical across 1.0.0 and 1.4.0 for every injected fault — but
"identical today" is a measurement, not a guarantee, and a networking record
that does not name its client cannot be compared with one taken elsewhere. The
version is not pinned; instead the behavioural assertions themselves run
against whatever is installed, so a future SDK that changes any of this fails
the suite on the owner's machine and in CI independently. That is a stronger
guarantee than a pin, which would only have frozen one environment.

**The connection failures are still not attributed.** Four consecutive
pre-header connection-establishment failures after one successful component
locate the failure *phase*, not the responsible party. DNS, TCP/TLS, local
networking, an intermediary, pool state, or a remote close before headers all
remain possible. `APIConnectionError` says where the failure surfaced. The
shared client was not replaced and pooling was not touched.

**The inspector has two modes now, because it had none that worked.** Block
119 shipped one, and it refused on every real record: it forbade any
40-character run of the passage, and an anchor *is* such a run, so it blocked
the exact case it was built for. The repair is not a weaker guard. The default
is share-safe — identifiers, labels, verdict classes, support classes, error
metadata, and nothing that quotes the passage, safe even when redirected into
a file. `--show-anchors` adds the anchors and the critics' own sentences, is
marked private, refuses to run when its output is not a terminal, and is used
by no test, fixture or report. Neither mode writes a file.

**The real-store guard now says when it cannot tell.** It measures the store,
not the writer, so it cannot distinguish a leak from the owner's own server
writing while the suite ran — and it had caught the latter three times.
Exempting the writes it recognises would trade false alarms for blind spots.
Instead: the corpus lease is tested live (an `flock` attempt, not a read of the
lease file, whose text outlives the process that wrote it), the baseline is
only meaningful when nothing holds it, and any change to owner state ends the
run as **`INCONCLUSIVE — CONCURRENT OWNER ACTIVITY`** with the exact paths
named and a clean rerun required. It is never reported as unchanged when it
changed, however legitimate the write. CI is stated as structurally unable to
prove this guard at all: a fresh checkout has no owner store to compare.

**The two defects under the failed component are recorded separately**, and
neither erases the other:

- a **malformed component packet** — the constraint required a word the chosen
  anchor did not contain, so every candidate under it was measured against a
  span too short to carry what the same component demanded (this fired on four
  of the six components, not one);
- a **candidate-generation defect** — all three candidates converted two
  negatively described states into a good/bad binary, which is a factual
  inversion of the source independent of the anchor's length.

Friction and the anchor-support tier both found the polarity inversion on all
three. They are recorded as **convergent** evaluations, not independent
evidence: they ran on the same model over the same packet. Their convergence
still matters, and it is what the owner's original objection said — the
surviving output distorted the passage toward one description and did not
engage what was underneath. The critic agreed with the substance of that
complaint. The interface, before block 119, made none of it legible.

## v1.13.0 — a partial workup may not impersonate a whole reading (block 119)

The owner ran his own writing through a deep workup and argued with the
result: it read as fixated on one word and blind to what was underneath.
He was right about the page and wrong about the cause, and the page is why.

**One component of six completed. Five never ran.** The four that would have
carried what was underneath — the reinterpreted hell, the critique of moral
performance, the labor-and-complicity thread, the slow descent — are exactly
the ones that died on the model call. What read as a lopsided judgment was
one surviving component doing all the work, and the page did nothing to say
so. It said the opposite: a coverage line at the top claiming every part of
the passage had been assigned to a concept, the surviving component's own
summary beneath it, and only then, third, a reassurance that five had failed
but nothing was lost.

Three different things had been allowed to blur into one. **Extraction
coverage** — how much of the passage was split into components; the extractor
claimed all of it and was right. **Analysis completion** — how many of those
components were actually forged and judged; one of six. **Custody** — what
survived the failure; everything, and irrelevant to whether a reading exists.
The old banner reported custody in the place where completion belonged, and
reported it last. Every sentence on that page was locally true. Together they
composed a claim no part of the system had made.

So partiality now renders **first**, above every coverage and result banner,
in the page's own voice:

> PARTIAL WORKUP — 1 of 6 components completed. No overall reading exists.

Not behind a mark. Block 116 put the *explanation* of a fact behind a
disclosure control; this is the fact, and a fact that changes what the whole
page means is not something a reader should have to open something to find.
The coverage line no longer speaks for the analysis ("six components were
proposed from the passage; one completed analysis"), every component count
says how many were analysed, failed components keep their cards and their
own retry doors, and the trial's verdict on the input is scoped in words to
the input — never suppressed, because an objection that was raised stays
raised, but never again readable as a verdict on a workup that did not happen.

**The run could not say what had happened to it.** Asked to classify the five
failures, the record could answer five of twelve questions. The failing
stage, the attempt number, the exception class, the elapsed time, the call
count, whether attempts overlapped, and whether any usage was billed on a
failed call were stored nowhere: the retry loop printed them to the server's
stdout and discarded them.

Worse, the one number that looked like a call count was not one.
`prompt_identities[].calls` counted prompt **renders** — a retried call
renders once and attempts three times — and it lived on `threading.local()`.
The adversarial and anchor-support passes build their prompts inside pool
workers, so those renders landed in each worker's own ledger and never
reached the parent. Proven, not inferred: three adversarial renders through
a three-worker pool, and the parent drained `[('attack', 1)]`. The two stages
that fan out, and therefore most of the traffic, were structurally invisible
to the run's own record. A count that cannot name its population is the
defect block 117 already ruled on; this was the same defect one layer down.

**So: one event per real HTTP attempt, at the gateway boundary.** Run and
component identity, stage, provider and model, attempt number, start time and
duration, outcome, exception class, sanitized message, provider status,
`Retry-After`, usage on success, and whether another attempt was in flight
during its interval — derived from the timestamps, not asserted. The ledger
is a locked list on the gateway, which is the one thing every worker thread
already shares, so a pool worker three frames down still lands in the
parent's record exactly once. A failed attempt flushes its event **before**
the exception leaves, because a run that produced nothing is precisely the
run whose attempts nobody can otherwise reconstruct. What may never enter an
event: the prompt, the passage, the API key, or the provider's payload — a
closed whitelist, enforced against a real forge driving the real passage
through, and credential-shaped runs are scrubbed from provider messages
rather than hoped against.

`prompt_identities[].calls` remains what it always was and is never again
read as a count of requests.

**A rate limit is no longer treated as transient.** Three attempts at three
and six seconds cannot honour a per-minute limit: a bucket that refills on
the minute is untouched nine seconds later, so the old loop's only effect on
a 429 was to spend the whole budget inside a window the limit could not have
cleared, and then report a failure it had helped cause. Now: if the provider
supplies `Retry-After` and it fits the disclosed budget, Nikodemus waits
exactly that long, once. Otherwise the run stops and says so, and the retry
belongs to the owner — who is the only one who can decide whether the work is
still worth the money, given that a timed-out request may have cost money
without returning an answer.

**What this block deliberately does not do.** It does not touch anchor
selection or candidate judgment. The malformed evidence packet on the one
component that ran is proven — its constraint required a word its own anchor
did not contain, which is the documented failure mode where every candidate
underneath is measured against a span too short to carry it — but whether
those candidates *also* overreached on their own is unresolved, and answering
it means reading the stored verdicts, not changing how anchors are picked.
`scripts/inspect_component.py` reads them, and refuses to print if the
owner's passage reaches its own output.

It also does not act on the theory that a shared client connection caused the
five failures. That theory has no evidence. The rate-limit defect above is
independent of it and true on its own, and instrumentation comes before
diagnosis.

**The historical run stays unclassified** unless the server's scrollback
survives. `APITimeoutError` stringifies to a message that conflates a network
timeout, a dropped connection and a request cancellation — the SDK says so
itself — so even a recovered exception class cannot separate provider
timeout from client concurrency without the elapsed times. Reconstructing it
from anything less would be inventing the finding.

**A failure to run is not a finding.** Nothing on that page judged the five
components that never completed, in either direction, and the banner now says
so. The owner's observation stands as recorded: the visible output felt
disproportionately fixated on one description and failed to engage what was
underneath. The execution failure explains that experience. It does not
invalidate it.

## v1.12.0 — one search, and the provider's own numbers (block 118)

The probe closed its gate and turned up two things. One of them I read wrong.

**The code-execution blocks are expected, and I overstated them.** I called
them a second tool firing unasked. They are the provider running its own code
to filter its own search results — from `web_search_20260209` onward
`allowed_callers` defaults to `["code_execution_20260120"]`, and Nikodemus
configures no override. Inspected and confirmed: the tool is
`web_search_20260318`, and `allowed_callers` appears nowhere in the codebase.
They are recorded as **`provider_internal_dynamic_filtering`** — counted and
typed, never parsed as evidence. Not local execution, not an undeclared
capability, not something Nikodemus gathered.

**The cost is the real finding.** Two capped calls consumed **39,865 and
63,359 input tokens** for a one-sentence answer and a one-sentence quote,
because search-result content counts toward input. The app allowed five
searches per ordinary review stage. It now allows **one**. A Research
operation that genuinely needs more discloses and confirms its maximum,
its model and its provider first; it does not inherit a higher default from
an ordinary review.

**What gets recorded is what the provider reported.** `web_search_requests`,
input, output and cache tokens, the tool version, and whether dynamic
filtering ran — carried into every search-enabled run's snapshot. Where the
response reports no usage, the record says so instead of filling in a zero.
And the count of code-execution blocks is **never** read as a count of
billable calls: that number is the provider filtering its own results, and
only the usage fields say how many searches happened.

**Two wording corrections, both mine.** The collector is exonerated **for
these two observed calls**, not universally across every provider, model and
configuration. And encrypted search content means **opaque provider search
state** was returned so the provider can carry it across turns — it never
means Nikodemus fetched, read or anchored the underlying pages.

**The durable law**, in the contract rather than in a probe that may be
deleted: provider search results are **leads**; native citations, when
present, are **provenance metadata**; a claim becomes Nikodemus-verified only
after the source is admitted through Nikodemus and tied to an exact Library
anchor.

**And a seventh self-matching check, caught in its own first run.** The new
pin for "no `allowed_callers` override without a ruling" greped for the word
and fired on the comment explaining why it is not set. It looks for the key
now. Seven times in three days; the pattern is no longer a surprise, it is a
review step.

Suite OK, 2 skipped. Five sabotage mutations caught by name — one restores
five searches, one renders unreported usage as zero, one stops recording the
acquisition, one drops the sentence forbidding the billable-call inference,
and one reads the block count as the search count (that last caught by crash,
then by name).

## v1.11.1 — the stabilisation pass, part two (block 117)

The rest of the ruling. After this, the building stops.

**The Vault strip, proved against the real producer.** Seven journeys mocked
`/api/vault/status` with the same healthy literal, so the red path had never
rendered in a browser and a renamed field would have left the strip green
forever — on the guarantee that is meant to be the floor. The strip's
*decision* is now a pure function of the status object, and the fixtures
capture five states **from `vault.status()` itself**, in a throwaway directory
the owner's vault never touches: uninitialised, healthy, dirty, stale, failed.

The journey feeds each to the decision and checks the interface changes.
`dirty` deliberately renders exactly like `healthy` — under the staleness
ceiling the debounce says this is not yet an alarm — and the first version of
that check demanded five distinct sentences and failed on that intended
equality. A test that would have introduced a real defect.

**And the general form of the fixture problem, fixed by derivation.** The suite
reads the keys `vault.status()` actually emits, reads the keys the strip
actually consults, and requires the second to be a subset of the first. Rename
a field in the producer and it fails the same day, in the reader's own words.

**Every count names its population.** "Every word — 932" stood in for three
defensible and different numbers: 932 shelf rows that lead a family, 1,303
distinct titles across every result file including sprout thread anchors, and
107 lexicon entries. Two careful readers computed two different ratios from one
screen. The shelf and the counted panel now name what they are counting, with
the distinction behind a mark.

**The doorless routes are classified**, in code rather than in a document, from
the ruled set: intentionally internal, compatibility entry point, external
integration surface, dormant capability, accidental orphan. The two Keeper
mutations — the only mutating routes whose capability is dormant — refuse with
`keeper_inactive` / `no_owner_action_reaches_this`. The other two mutating
orphans belong to capabilities that are active and reachable, and their
boundary is the session gate every route sits behind.

**The citation probe is landed.** `scripts/citation_probe.py` makes one
search-enabled call, writes nothing into the corpus, and reports one of three
outcomes that must stay three: `not_run_missing_credential` (says nothing about
the provider), `ran_no_native_citation_observed` (a finding about the provider,
not the collector), `native_citation_observed`. **A call that failed is
recorded as not-run, never as an absence of citations** — a call that did not
complete observed nothing.

**A fourth presence-not-reachability pin, caught by its own sabotage.** The
probe's outcome check grepped for three strings that also appear in its
docstring, so a mutation making one unreachable passed. The suite now drives
the probe with a stubbed gateway, once per outcome, including the failure path.
Four times in two days that shape has surfaced; it is now the first thing to
suspect in any new check.

Suite OK, 2 skipped. Fourteen journeys, 467 checks. Five sabotage mutations,
all caught by name: one makes the strip read a key the producer does not emit,
one leaves the Keeper's second mutation unguarded, and two collapse the probe's
outcomes in opposite directions.

**The building stops here.** What is left belongs to the owner: the manual
writing-room pass, the real citation probe, one real-model Inquiry reading, one
real Open Case or EthicalAlt import, and one complete outside-research
investigation.

## v1.11.0 — the stabilisation pass, part one (block 117)

Four of the census findings, repaired. Not all of them: the ruling was one
bounded pass, not a month of archaeology.

**A row the owner did not author is nonfinal.** The audit ran read-only first,
as ordered, and the premise turned out different from the ruling's assumption.
The six `decision_source: "validator"` rows are **not** procedural rejections of
malformed input. They are semantic craft verdicts a model wrote — *"the central
axiom is false"*, *"decorative restatement"* — filed as `rejected` at confidence
0.6, with no timestamp, from a code path that no longer exists anywhere in the
repository. `latest_decisions()` never read `decision_source`, so the shelf has
been showing all six as the owner's own rulings.

They are preserved exactly as written, shown with *"Not your ruling"* and what
the model said, and they no longer stand: the word goes back to unruled, which
is what it has been all along. A model's verdict does not count as the owner
coming back to something, and where he later ruled over one, his ruling wins and
the model's is kept as context on his row. The counted panel counts them apart —
a panel about how he rules that includes six decisions a model made is a panel
that lies about him.

**Storing is not reading.** A `paste` listener bound to the whole document sent
any pasted file to `/api/upload`, which called the gateway. Text and PDF derive
locally — no model, nothing to authorise. An image does not: reading it is a
vision call, and it fired from a keystroke with the label saying a model had read
it rendering afterwards. The artifact is now stored either way and **nothing is
sent**; the card says so, and the vision call happens on a button that names its
lane, its model, one call, and *cost unknown* — because the provider prices by
image size and reply length, neither known in advance, and inventing a number
would be worse than admitting the shape of what is unknown.

**A mutating model route with no door refuses by name.** `/api/keeper/renarrate`
spends a model call and nothing in the app presses it. It is not deleted — its
contract is what an activated Keeper will need — and it now answers
`keeper_inactive` / `no_owner_action_reaches_this` rather than staying quietly
callable.

**The shelf is derivable, or the claim is retracted.** Accepting and retracting
have recorded definition events since block 104. The owner rewriting a meaning by
hand did not — the one change he makes himself was the one the record could not
account for. Now it does. Beside it, a dated **baseline** with a hash: the event
log began at block 104, so everything accepted before it has no event and never
will, and the honest repair is not to fabricate the missing history but to say
*this is the state on this date* and account for everything after. Reconstruction
is proved in a temporary store, never against the owner's corpus, and
`verify_definition_projection()` returns named outcomes — `matches`,
`no_baseline`, or `drift` naming the entries that differ.

**And a timestamp trap, caught by its own check.** The first version decided
which events were already inside the baseline by comparing timestamps, and
`_now()` has one-second resolution — so an edit made in the same second as the
baseline read as already included and the projection reported drift against
itself. Membership is by **event id** now. This is the third time a whole-second
clock has been asked to order two things it cannot.

**A skip is a third outcome.** Two checks are gated on the owner's real corpus,
which is gitignored — in CI they evaluated to nothing and the run printed OK,
which is indistinguishable from passing. The suite now prints a SKIPPED section
naming each one and why.

**Two dead checks removed, and four claims that did not verify.** Two `if …:
pass` blocks read like guards and were not; they are gone, with a note saying so.
The census reported eight vacuous pins; on inspection **four of the eight did not
hold** — two were legitimate `except: pass` and class bodies the collecting pass
misread, one pins a comment that backs a behavioural pin directly above it, and
one cited a byte-window match that does not exist in the file. Reported rather
than "fixed", because repairing a check that was never broken is how a suite
grows noise.

Suite OK, 2 skipped. Fourteen journeys. Three sabotage mutations, all caught by
name: one lets a model's verdict stand as the owner's, one lets a paste spend a
vision call, one puts the baseline back on a whole-second clock.

## v1.10.0 — the mark, and the live door (block 116)

Two changes, both about the same complaint: the page is exhausting to read and
it never tells you what to do next.

**The mark.** Fifteen blocks of honest labelling produced a card that teaches
the same lesson on the hundredth reading as on the first. The split is not the
same as hiding a finding, and the entire risk of this block was that it became
one: **the fact stays on the face, the explanation of the fact goes behind a
mark.** *The quote is not in your text* is a fact. *Checked mechanically against
your source, not judged by the model* is a lesson about what kind of fact it is
— true, worth having once, and not worth re-reading forever.

The mark is a button with `aria-expanded` and `aria-controls`, not a `title`
tooltip. A tooltip needs a pointer, does not exist on a phone, and its text
never enters the accessible tree; this project has already shipped meaning a
screen reader could not reach and is not doing it again.

**The live door.** Eight buttons rendered on every card, identically, whatever
the card was — fifteen cards is a hundred and twenty buttons with no order among
them. The card already knows which of them could change its own rows, so it says
so, and the rest fold behind one line. This is arithmetic on values already
rendered above it, not a preference inferred about anybody.

What was checked rather than assumed: Verify's prompt takes Friction's **own**
recorded claims and tests them, so it genuinely is the door that can overturn a
craft objection. Sprout, Refract and Archetype travel *from* a candidate and
change nothing about it — block 111's inherited-verdict machinery exists
precisely because they carry the problem forward.

**And the finding that fell out of building it.** `check_anchor_integrity` is
called from exactly one place, inside `run()`, and **nothing on a card re-runs
it**. Revise freezes the meaning and re-forges only the word-form. The Bench
works on structure and names. So a candidate whose anchor is not in the source
has **no door here that repairs it**, and the card now says that instead of
offering five buttons none of which can. A door that cannot do the job is a
capability claim the app cannot honour, which is the same failure as a number
nobody measured.

**Two vacuous checks of my own, caught before they shipped.** The suite pin for
this split greps `index.html` — and moving a sentence into a `whyHtml('…')`
argument leaves it in `index.html`, so every older pin for those sentences still
passes and can no longer tell the face from the mark. The new pin reads the
`whyHtml` arguments specifically. And the first journey check named three
lessons that all live inside a closed `show the case` disclosure, so `innerText`
excluded them whether the mark worked or not — a check that could not fail. It
now names the live door's own explanation, which sits in the card with nothing
above it.

**A correction from GPT's review, taken before this shipped.** The warning was
that a suggested door must genuinely repair the card's present problem. The
anchor branch already satisfied it — Verify is never offered as an anchor
repair — but the review exposed the case pointed the other way: a card can carry
a failed warrant **and** a craft objection at once, and those take different
doors. The first version named the warrant, said nothing repairs it, and folded
Verify away — true of the warrant, false of the objection. Burying the door to
the second row is the same error as offering a door for the first. It now says
both, and Verify's own label says which row it cannot move.

The suite could not catch that. Its pin asked whether the branch existed, and a
mutation that makes the branch unreachable leaves its text in the file — the
third time this project has shipped a pin checking presence rather than
reachability. The journey now calls `liveDoor()` directly across every
combination, which is the only thing that can tell reachable from present.

Suite OK. Fourteen journeys, 460 checks. Six sabotage mutations, all caught by name: one
turns the mark into a tooltip, one moves a finding behind it, one stops it
hiding anything, one has the door promise a repair the app cannot perform, one
pulls a lesson back onto the face, and one makes the both-rows branch
unreachable — which only the journey saw.

## v1.9.0 — what the record counted (block 115)

The first tier of *it should remember me*, and deliberately the dull one.
Every number in the new panel is a **count over rows already on the shelf**.
Nothing is predicted, nothing is suggested, and the suite checks that — on the
function and on the panel it feeds — because a recommendation is a claim about
a person made by the machine that gains from him accepting it. That is the same
class as reviewer prose, which carries `MODEL SELF-REPORT — UNVERIFIED` for
exactly that reason. The tier that may advise arrives with a label; this is not
that tier.

What it counts that no single row shows is the **disagreements**, and the two
directions are counted apart: words **kept over the critic's objection**, and
words **set aside with no objection on record**. Folding them into one
"divergence" number would assert something neither half says — overruling an
objection and setting aside an unopposed word are different acts. Beside them:
words **kept with nothing checked** (no critic verdict, no anchor, no support
check — usually forged from a brief with no source, which is a different fact
from a check that ran and passed), and the **unruled backlog**, oldest first,
because *waiting longest* is a fact and every other ordering is a priority.

An unrecognised ruling is counted under its own name rather than folded into
"undecided", which would invent a ruling the owner never made.

**Where it lives, and why not yet on Home.** The counts ride on `/api/library`,
which is the only place the shelf is assembled — each row already carries the
owner's ruling and the flags the run recorded, so this is arithmetic and not a
new join. Putting it on Home would mean either scanning the whole store on
every first paint (**7.5 MB across 480 result files today, growing linearly**)
or extracting the shelf assembly out of a 150-line endpoint. That extraction is
its own change with its own tests, and doing it under cover of a feature is how
a Library gets refactored by accident. It is in the backlog with the number
attached.

Suite OK. Fourteen journeys, 446 checks — the epistemic journey opens the shelf and reads
the panel's own text. Three sabotage mutations, all caught by name: one blurs
the two disagreements into one count, one turns a sentence in the panel into
advice, and one folds an unrecognised ruling into "undecided".

## v1.8.0 — the result comes first (block 114)

Shown to another person for the first time, a run opened with a paragraph about
how the extractor had parsed the question — the anchor it chose, the constraint
it derived from that anchor, the background it recalled, the stance it read —
and the answer was somewhere below all of it. Every one of those lines was added
by a block that was right to add it. The sum was a report about the machine.

**The rule: a passing check may be quiet. A failing check may not.**

That is *silence is not success* read the other way round. The original forbids
an **absence** from rendering as a pass — a review that searched nothing has to
say so. It never said a pass has to shout. So an anchor that was found collapses
behind a disclosure that names what it holds; an anchor that was **not** found
stays on the page. A source check that came back supported collapses; one that
came back *contradicted* does not. The critic's read of the owner's own input
collapses when it raised no objection and stays open when it did, because an
objection he has to scroll past is one he will miss, and every candidate below
it inherits the problem.

The two component headers — decompose's and deep's — were separate copies of the
same markup, and every correction to them has had to be made twice. They are one
function now, and the suite pins that both views delegate to it rather than
counting how many times a line appears.

**Two defects found while writing the journey for that rule, both worse than it.**

**The reopened run was not the run.** A decompose parent snapshot was written
from the *receipt* projection — six fields, where the live run carries thirteen.
The grounding tag, the source check's verdict, and all three mechanical warnings
were dropped on the way to disk. A component flagged *your passage DENIES this*
showed that warning while it ran and showed a clean page when it was reopened
from Recent. Collapsing a warning would have been bad; never storing one is
worse, and the two were about to ship in the same block. The pin for this is
**derived, not restated**: it reads which fields the component header actually
renders and requires the persisted projection to carry every one, so a field
added tomorrow fails until it is carried.

**And a reopened decompose run rendered nothing at all.** There was no branch
for it in `loadPastResult`. It fell into the generic candidate list, which reads
`d.candidates` — a key a decompose parent does not have, because a parent holds
groups and each group's candidates live in that component's own run. So
reopening a decompose run showed the input text, the word "decompose", a
timestamp, and an empty page. The deep branch beside it has had this since block
103. Decompose never got one. The candidates are still not copied into the
parent — there is one record of them, in the component's own run, and the parent
now shows a door to it rather than an empty component.

**Stated plainly, and not fixed here:** deep and decompose now persist their
parents differently — deep embeds each component's candidates, decompose links
to them. Deep's copy has worked since block 103 and unifying the two is a
separate change with its own risk, so it is recorded in the backlog rather than
folded in quietly.

Suite OK. Fourteen journeys, 443 checks — the epistemic journey now opens the reopened
parent and reads `innerText`, because a closed disclosure contributes nothing to
it and source review cannot tell a collapsed line from a deleted one. Five
sabotage mutations, all caught by name: one drops a warning out of the findings
list, one shrinks the persisted projection by a single field (the check names
which field), one hides the critic's objection, one removes the reopen route,
and one pulls the machinery back above the results.

## v1.7.0 — the Epistemic Presentation, phase 1 (block 113): what a call can say it acquired

A census of the store found **3,781 citation rows across 470 result files, every
one of them `searched` and not one `cited`.** The cause was deterministic, not
occasional. The provider's documented response puts the search-result block
*before* the text block that cites it; the collector walked the response once
and deduplicated on URL keeping the first label it saw; so the citation
observation was thrown away on every run this app has ever made. Beside it sat a
second loss: a citation object carries `cited_text` — the passage the model says
it cited — and the collector never read it.

The collector is now a **pure module-level function**, extracted out of the
gateway method on purpose: the claim being made about it is that *block order
cannot change the result*, and that is only provable by a function that runs
with no provider present. It makes two passes, associates by exact URL only —
two URLs that merely look alike stay two sources, because a false merge is worse
than a duplicate and the provider gives no canonical id — and writes `observed`
as a **list**, because a source can be both returned and cited at once. The old
scalar `used` is kept, documented as lossy, and is the field no new surface may
read.

**Nothing is backfilled.** The 3,781 stored rows carry no `observed`, and the
app now reads them as *citation not recorded* rather than as proof the prose
cited nothing. A row that says "searched" was written by a collector that would
have said "searched" either way.

**Three of the five acquisition facts cannot be observed at all**, and they are
printed as words, never as zero: *Fetched by Nikodemus — not applicable, the
search ran inside the provider*; *Examined — unknown, what entered the model's
context is opaque to this client, and opaque is not the same as unrecorded*;
*Anchored in your Library — none*. A zero is a measurement. Claiming a
measurement nobody took is the failure the panel exists to prevent.

**Reviewer prose is labelled `MODEL SELF-REPORT — UNVERIFIED`.** It is the model
describing its own work, produced by the same call it describes. Where the prose
claims a search and the record shows nothing came back, the panel says the
record wins. That test is deliberately one-directional: it fires only when the
record is empty, so it can miss a contradiction and cannot invent one.

**An invented example is labelled in text.** The model-written example sentence
rendered in italics inside curly quotation marks directly under the definition —
this app's three visual conventions for a *quotation*. It now carries
`INVENTED EXAMPLE — NOT IN YOUR TEXT:` as a real sentence, with the quotation
marks gone, and the same label goes into the packet handed to Friction, which
was previously given the sentence under the bare heading "Example:" with no way
to know whether the owner wrote it. The label is text and not a colour, an icon,
a tooltip or CSS `::before` content, because all four vanish exactly when the
reader selects, copies or listens.

**Warrant dominates craft.** A filled *Well-made* row beside an empty *Grounded*
row read as an endorsement. Where the warrant is absent or failed, the craft row
now says which of the two questions it answered: *craft coherent; source warrant
ABSENT*. The dot is not downgraded — filled means good-on-this-row on every card,
and a dot that sometimes means the row and sometimes the card would be worse than
the problem.

**A defect found while wiring the fixture, and it ran the wrong way.** The
checker emits five anchor statuses. `absent` means *no quote was offered*;
`not_found` means *a quote was offered and is not in your source*. The card
header read `absent` as "the quote is not in your text" and did not mention
`not_found` at all — so **the strongest negative result the mechanical tier can
produce was rendering as an empty circle meaning nothing had happened.** Both
directions are fixed, and the new journey calls the pure function directly with
every status rather than pinning a sentence.

**The suite could not report what it already knew.** Two block-113 sabotages
were caught *by crash rather than by name*: the broken collector returned no
text, a caller five thousand lines earlier raised, and the run died before the
checks that name the defect ever ran. The failure list now outlives `main()`,
the crash path prints what was already found before the traceback, and the
collector's pure checks run at the top of the run instead of the bottom. The
audit that protects this is at **import time and reads the parse tree** — the
first version lived inside the very block whose call site the sabotage deletes,
and the version before that asked whether the string `except BaseException:`
appeared in the file, which it always did, because the check's own line
contained it. That is the fifth self-satisfying pin this suite has produced and
the pattern is now named: *a source-text guard that quotes what it looks for is
not a guard.*

**Stated plainly, and not proved here:** no provider is reachable from where
this was built, by standing law, so **production citation capture is still
unconfirmed**. The collector is proved against the documented response shape and
against fixtures; a live run on the owner's machine is what would settle whether
a real call emits native citations at all. Until that probe runs, the honest
reading of the new record is *this is what the client would capture*, not *this
is what the provider sends*.

Suite OK. Fourteen journeys, 436 checks — a new **epistemic** journey calls the
pure functions in a real browser and strips every stylesheet to prove the labels
are text. **Twelve sabotage mutations, all caught by name.** Seven against the
suite, including the two that previously only crashed, one that narrows the
crash guard, and one that moves the pure checks back to the end of the run; and
five against the journey through a new harness (`sabj.sh`) that mutates a
throwaway tree and runs one journey against it — because a browser check that
cannot fail is theatre, and source review cannot tell the difference. Those five
re-cross the anchor states, turn the invented-example label into CSS `::before`
content, print a zero where a word belongs, drop the self-report label, and
backfill the historical rows.

## v1.6.0 — the Inquiry, phase 2 (block 112): the Question Reader

A tangled question usually means two or three different things at once, and
those things need **different evidence**. So the first thing an inquiry
returns is not an answer: it is two to four ways the question could be read,
the assumptions sitting inside it, and the terms that could go either way.
Take one, take all, reword any of them, or write your own. Taking several
makes **separate sibling branches**, never one blended question.

**The guarantee is structural, not a promise in a prompt.** A model told to
read a question will cheerfully answer it instead and slip what it thinks the
sources say into a field labelled "reading" — no wording reliably stops that.
So the output shape has nowhere for a fact to live. A reading is a label, a
scope, and *what evidence it would require*. An assumption is a span of **his
own question** plus why it is an assumption. An ambiguity is a term from his
own question plus the senses it could take. Every field is either a
requirement or a pointer back into his own sentence.

Then the pointers are checked. `check_readings` requires every quoted span to
appear in the question; one that does not is **dropped, counted, and shown to
him**. A model that wants to smuggle in a finding has to put it in a field
that does not exist.

An edit does not overwrite its proposal: it **descends** from it, and the
standing changes honestly with the authorship — the model's wording stays
`model_proposal` and visible in the graph, his becomes `owner_stated`. That is
what the two axes were separated for.

**Meta-questions are structurally apart.** A question about the question is
marked `world_directed: false` on every node the page sees, and `add_node`
refuses to hang an answer or an attack off one. Pinned now, before answers
exist — the only moment it is free.

One model call, and the panel names the lane and the model before the button
that spends it, reporting the **Reader's own lane** rather than whichever lane
a run would take. Reading a question writes no judgment.

The Reader has one seam, the same shape as `speech.ENGINE`: `READER_GATEWAY`,
`None` in every real run and assigned only by the journey server, so the whole
server path — mechanical check, recorded run, adoption into siblings —
executes offline against `cli.MockReader`. The suite pins that nothing else
assigns it, that it is `None` in the suite's own process, and that the
stand-in returns something the check will drop, so the journey's drop check
cannot be theatre.

**Stated plainly, and not proved here:** no provider is reachable from where
this was built, by standing law. The suite proves the mechanical check, the
recorded identity and the structural guarantees; the journey proves the whole
client-and-server path against a deterministic stand-in. Neither proves that a
real model returns *good* readings. That is a limit of where this ran, not a
claim the tests make.

Suite OK. Thirteen journeys, 408 checks, exit 0. Twelve sabotage mutations,
all caught by name — including one that lets the Reader carry a finding
through, one that keeps an invented quotation, one that chains the readings
instead of forking them, and one that leaves the stand-in seam switched on.

## v1.5.1 — the evidence vocabulary, corrected before it was used

The flat `evidence_kind` list shipped one block ago put `allegation`,
`regulatory_allegation`, `charge`, `settlement_no_admission`,
`adjudicated_finding` and `conviction` beside `testimony`, `measured_datum`
and `company_assertion`, as though they answered one question. They answer
three: what the material **is**, who **issued** it, and where it stands
**procedurally**. A settlement is not a kind of evidence — it is a state a
document can be in, and that same document holds allegations, the company's
own assertions and stipulated facts at once. Flattened into one label,
procedural movement silently becomes proof: a charge reads as a finding, a
settlement reads as an admission. Worse, the list had nowhere at all to put
a dismissal, an acquittal or a reversal.

Corrected while still unwritten by any row, into four axes: **nature**
(assertion, testimony, allegation, measured datum, documented event, analysis,
owner judgment), **issuer role** (company, regulator, court, journalist,
researcher, whistleblower, owner, model, other), **procedural posture** (none,
investigation, complaint or charge, settlement, adjudication, conviction,
dismissal or acquittal, appeal, reversal), **admission status** (not
applicable, explicit, limited, none, not stated), and **finality** (pending,
interim, final, appealed, overturned).

A classification is attached to one claim or answer element, never to a whole
document, and `classify()` raises on an unknown term rather than coercing it
to a default — a silently defaulted posture is the exact failure the axis
exists to prevent. The vocabulary is versioned (`inquiry.vocab.v1`) and every
classification carries the version it was made under, so a later extension is
a recorded migration rather than a redefinition of what old rows meant.

Suite OK. Five sabotage mutations, all caught by name — including one that
restores the flat list and one that removes `dismissal_or_acquittal`, on the
grounds that an investigation which can record a charge but not its dismissal
is a machine for accumulating suspicion.

## v1.5.0 — the Inquiry, phase 1 (block 111): a question, kept

A durable place for one question. It can be opened, listed, reopened and
navigated; the question is kept verbatim and nothing in the module can change
it; every later act is a node hanging off another node, so a clarified
question is a descendant rather than a correction. Reopen it in a year and it
is standing where you left it.

**The name, first, because the obvious one was taken.** Block 107 already
shipped an "Investigation Room" — `inv_` ids at `/investigation`, fixed seats,
holding depositions Open Case and EthicalAlt signed. That room seats what
*other instruments* deposited; this one holds a question the owner is
*working*. Two different objects. Overloading one name would blur two
constitutional meanings and break the ledger that pins the first, so this is
an **Inquiry** (`inq_`, `/inquiry`, `local_state/inquiry/`) and the federation
room keeps its name.

`scripts/inquiry.py` follows the house conventions rather than inventing new
ones: call-time paths off `cli.LOCAL_STATE`, one append-only log, federation's
clock discipline (`recorded_at`, `clock_regression`), minted ids salted so two
inquiries opened on identical words in the same second are two inquiries.
Zero model calls, and the suite reads the source to prove it.

Three vocabularies are declared in full now, unused until later phases, so
they slot into a pinned shape instead of being widened under pressure.
**Route** — how an element was produced. **Standing** — what warrant it
currently has; separate from route, because collapsing them is how a model
proposal becomes a fact. **Evidence kind** — what kind of assertion it is:
allegation, regulatory allegation, charge, settlement without admission,
adjudicated finding, conviction, testimony, company assertion, measured datum,
model inference, owner judgment. That third axis exists to keep an accusation
from becoming a finding, and a settlement from becoming a conviction.

Branch dispositions are open, parked, abandoned, kept-supported,
kept-generative, kept-unresolved, promoted. **Only promotion may ever lead to
a judgment, and this module writes none** — the suite proves that opening and
branching an inquiry leaves the judgments log byte-identical. Abandoning keeps
the reason *and what the failure revealed*, because the throw that did not
stick is the half of the record most worth having.

The chooser gains a seventh door — *Open an inquiry*, beside *Save as an open
question* — and the shell gains `/inquiry` as a place, so walking there and
back never rebuilds the writing room. The constitution is amended in the same
block and says plainly what this phase cannot do; the room names every later
phase on its own face as an unbuilt door, dashed and inert with its reason,
rather than implying a capability it does not have.

**Not built here, and named as such:** readings of a messy question,
meta-questions, ask-my-record, research outside, trial, comparison, synthesis.

Suite OK. Thirteen journeys, 397 checks, exit 0. Seven sabotage mutations, all
caught by name.

## v1.4.4 — two defects in the suite itself

Neither of these was in the application. Both were in the file that is
supposed to be able to prove the application, which makes them worse than
their size.

**The flake, and it was the test.** Block 103 asserted that a recovered
concept appears as a Continue card by reading `/api/home`, whose `continue`
list is the top eight cards by time, built from at most six concepts. Seven
concept cards compete for those six slots in that fixture state — block 94's
twin, block 99's pair, and block 103's own four rulings. All four rulings are
issued within a few milliseconds and therefore normally share one wall-clock
second, which left them tied and kept the Accept at the head of its group.
When a run happened to straddle a second tick between the Accept and the three
rulings after it, the Accept became a second older than its siblings, dropped
below the fixtures that carry microseconds — a microsecond stamp sorts above a
whole-second one, because these are compared as strings and `.` outranks `+` —
and fell off the six. The card was never missing; it was ranked seventh.
Reproduced deterministically by inserting a one-second pause between the
Accept and the rulings that follow it. The assertion now runs against the card
builder, uncapped, which is where the claim actually lives; whether Home has
room to show the card today is a question about how much else was ruled on
that afternoon and was never what the block was about. No retries, no sleeps,
and nothing weakened: the check is strictly more specific than it was.

**The date bomb.** The same check asserted `startswith("2026-09")` — the month
the block was written in. It would have gone red on 1 October whatever the
code did. The card is now compared to the ruling's own recorded clock, taken
from the judgment row the block has already proved carries one, so the
assertion is true in any month, year or timezone; it also narrowed from a
thirty-day window to a single value. A sweep of the rest of the file found no
other assertion pinned to a live clock — the other fourteen date literals are
fixture inputs, which is the fixed-clock pattern this repair moves toward.

**Block 110** pins both: block 103's card check must read the builder rather
than the capped view, must compare to the ruling's own clock, and no line of
this file may assert that a timestamp begins with the month the suite is
currently running in. All four guards were verified by mutation, including one
that plants a live month literal and confirms the guard finds it by line
number.

Recorded but not repaired, because it is runtime behaviour and outside this
cleanup: Home compares ISO timestamps of mixed precision as strings, so a
record written with microseconds always outranks one written with whole
seconds inside the same second. It changes only the order of same-second
cards, and no manual check depends on it.

## v1.4.3 — the four defects the owner's manual pass found

The manual writing-room pass did not pass. Four defects, all in work that had
already shipped green, and one of them was the test rather than the code.

**Tab left the writing.** There was no handler at all, so the browser did its
default and moved focus out of the room. Tab now inserts a plain two-space
indent at the caret; a selection that spans lines indents every line it
touches; Shift takes one level back off from each line that has one; the
selection survives; and the whole edit is a single entry on the textarea's
NATIVE undo stack, which is why it goes in through `execCommand('insertText')`
— assigning to `.value` empties that stack, which would trade an indent for
every keystroke before it. Escape arms an exit and the very next Tab is handed
to the browser untouched, so nobody is trapped; that behaviour is described on
the textarea itself with `aria-describedby` and shown as a dim line on first
use, rather than printed on the wall.

**The room's progress line never moved.** `roomRunProgress` compared
`job.job_id`; the job record returned by `GET /api/jobs/<id>` carries its id
under `id` — `job_id` is what the POST answers with. The comparison was
`undefined !== "job_..."` on every poll, so the function returned on its first
line forever and the line stayed at "sending the workup…". It now reads `id`
and walks honest states: submitted, working, the component count with the
call-budget estimate still named as an estimate, completed, and failure with
its real class rather than a euphemism.

**The test proved a fixture that the application never emitted.** The deep
journey mocked that GET with a body carrying `job_id`, so thirty-one checks
went green against a shape the server has never sent once. Recorded here as
test-was-wrong. The fixture now answers the server's shape, and block 108 is a
contract test that reads the real serializer out of `server.py` with `ast` and
requires every `job.` key the room reads to exist in it — rename the key in the
server and it fails, read a key the server does not send and it fails. The
sabotage battery mutates each side independently and both are caught.

**A finished workup needed you to leave the room and come back.** Every deep
invocation now records routing identity — job id, which surface asked, the
scope requested, where the answer belongs, whether it has been revealed — and
nothing else: not a character of the draft, because the server's job record is
the source of truth and this is only the thread back to it. The room open and
in front of you splits on arrival without taking the caret; away, the answer
waits and offers itself, and entering the room or returning from a place finds
it; a full reload picks the run back up from the stored reference; a run
started from the page belongs to the page and never hijacks a draft; and a job
the server no longer has says so instead of leaving a frozen line.

Also in this block: the arrival styles are named — **Settle** (the motion that
has been shipping unnamed since the room existed), **Ink** (splatter during
arrival only; the letter is plain settled text the moment the class comes off),
and **Plain** — behind `Aa` beside the face, size and view; and the View
preference, which was being written to storage and never read back, now
survives a reload. The constitution is amended in the same block.

## v1.4.0 — connected instruments (block 107: Open Case and EthicalAlt as a federation)

Block 107 (`docs/adr-federation.md`, `docs/connectors.md`,
`schemas/deposition.schema.json`, `scripts/federation.py`, `/investigation`).
Open Case and EthicalAlt are connected as sovereign instruments, not merged:
each keeps its database, code, interface, vocabulary and signing key. The
boundary is a versioned evidence-export contract — `nikodemus.deposition.v1`,
a transport-and-custody envelope around the producer's native payload — that
each producer signs (Open Case: its stored seal, `open_case.seal.v1`, never
re-signed on read; EthicalAlt: a new v2 export, `ethicalalt.export.v2`, over
RFC 8785 canonical bytes) and Nikodemus verifies under a public key the owner
pinned on the connector out of band; a key inside a package is ignored. The
exact bytes go into the Library's blob store by content hash with a
deposition row and a derived representation; the same bytes twice are an
import event; different bytes for the same object are a new version linked
to the prior with `supersession: unknown`. Source-native labels, ids, gaps
and the allegation/response pairing survive unchanged; an unreachable
producer is a failure with its class, never "nothing found". The registry
is appended events with credential references (`env:NAME`) only. One
Investigation Room seats depositions apart by instrument and kind; the one
proposer is an exact name match; only the owner declares, rejects or leaves
unresolved; convergence (a two-instrument timeline and 90-day overlaps in a
mechanical sentence) appears only after a declaration. The chooser reads a
single web address as a shape and offers the matching import when a
connector is configured — dashed when not. Manual pull only: no polling, no
refresh, no background comparison, no model on any path. The anatomy gains
Connected Instruments outside the membrane and Instrument Commands as unbuilt
tissue; About & proof gains the registry line and the constitution paragraph.
Open Case gains `GET /api/v1/cases/{id}/export` and `/cases/exportable`
(authenticated, side-effect-free, tested); EthicalAlt gains
`GET /api/profiles/:slug/export/v2` and `/export-key` with a hand-written
RFC 8785 canonicalizer and an offline test. Deferred and shown as unbuilt:
every command toward a producer.

## v1.3.7 — the ear, governed (block 106b: the reviewer's rulings on Speak)

Block 106b (`docs/adr-speak.md`, amendment). "Newest 39" is rejected as
the vocabulary rule. The engine is told, in order of standing: the
visible name and the words the owner declared it must hear right; the
names of what he has open (a concept, a Room, a document, a work — by
id, resolved from the record, never named by the request); the shelf
titles he pinned for speech; then the shelf as space remains, in a
deterministic order that is not newness (rarest first under the
engine's own tokenizer, alphabetical when there is no model). The cap
is 190 of the engine's tokens when they can be counted — Whisper keeps
the last 223, and the real shelf's coinages had pushed the hint to 251,
cutting the owner's own words off the front — with a per-title ceiling
for the fallback. Every transcript cites a content-addressed hint manifest — the exact terms,
each with its tier and source id, what did not fit, the rule, the model
— written once at Send or Keep (never by transcribing) and readable
back at `/api/speak/hints/<sha>`. The declared and pinned words are
appended events (`speech_vocabulary_events.jsonl`); the projection is
a plain file rebuilt from them; a block-106 file is migrated into
events by the owner's next save. The model's fetch is recorded
(`speech_models.jsonl`): source, revision, every file's hash, the
composite hash the transcripts cite, and the license from the card in
the snapshot; an already-cached model is recorded as observed without
the network. The raw-body routes refuse by type, declared length and
deadline before a byte is read, then read bounded — never past the cap,
never past 30 seconds, never a body shorter than declared. The
correction law is pinned on the parrot-books specimen: what the engine
heard stays visible beside the owner's edit, the edit is what is sent,
the record never claims the engine heard the correction, and editing
retrains nothing. A later, optional "Teach this correction" is named
and not built.

## v1.3.6 — Speak to Nikodemus, Mac-local (the first doorway that is not a keyboard)

Block 106 (`docs/adr-speak.md`). A recording instrument beside the
attachment doorway: press to record (the microphone opens only on the
press), stop visibly, a local engine transcribes, the transcript lands
in the box editable, and the edited box goes to the destination chooser
with provenance `spoken` and the transcription's identity beside it —
engine, version, model and its file hash, compute type, the vocabulary
hint's count and hash (the shelf's own accepted titles, read at call
time, recorded because they bias), `external: false`, the machine's own
text and whether the owner edited it. The engine is faster-whisper
(MIT) with base.en int8, decoding from memory; the model is fetched
once by a visible button in About & proof, never by transcribing. The
routes take the recording as a raw body, capped, and refuse multipart
(which Werkzeug spools to disk). Transcribing writes nothing; Discard
leaves nothing; a failure holds the audio in the page and offers Retry
/ Download / Discard; Keep recording stores it byte-intact through the
Media wing with the machine transcript as a time-anchored version and
the owner's correction as a second one. On a page that is not a secure
context (the phone over HTTP) the control says so and names the
trusted-LAN-HTTPS block. `requirements-speech.txt` is optional; an
absent engine is reported, never mocked. Names ruled: Read aloud (item
49's control), Speak to Nikodemus, Conversation. The anatomy's Sensory
Tissue now says what is built. No Conversation, TTS, or vision.

## v1.3.5 — the destination chooser (the intent layer, fixed once)

Block 105 (`docs/adr-nikodemus.md`, amendment). Words brought into Home
now go where the owner sends them: a mechanical, zero-model reading of
their shape highlights one destination and the owner's click summons a
lane — Research outside Nikodemus, Search my record, Develop the idea,
Start a Room, Write from this, Save as an open question, and for a name
with a date, Study the name / Create a private portrait / Save
owner-declared facts. Nothing runs until the owner chooses; Run it /
Go deep and the gesture chooser are unchanged but appear only under
Develop the idea; unbuilt destinations are shown as unbuilt and do
nothing. Open questions are a new small object (`open_questions.jsonl`,
verbatim, with provenance; withdraw appends a status), in the Library
with a quiet count on Home. `spoken` joins the input provenance
vocabulary ahead of the microphone; typed and spoken versions of one
sentence receive the same destinations by construction. The job route
records the destination chosen and the chooser's reading on the input
row. Pinned by the cats sentence and an invented name with birth data.

## v1.3.4 — the record primitives (measuring instruments before ordinary use)

Block 104, held for inspection (`docs/adr-record-primitives.md`).
Every receipt names the prompt templates behind it — stage, template
hash from the builder's own source, renderer revision, model, settings
— never the assembled prompt and never a hash of private text; every
`build_*_prompt` is registered and ledgered. Every new edge on the Map
carries an origin (`mechanical`, `owner_declared`, `model_proposed`,
`imported`) and cites the receipt, judgment or declaration that
produced it; rows written before this read as `legacy_unknown` and are
not rewritten. Every shelf write is first a definition event
(`definition_events.jsonl`: exact definition, concept, time, origin,
judgment, what it supersedes); the shelf is a checked projection, and
`scripts/shelf_projection.py --baseline` gives older entries one
labeled baseline, reconstructing the Recovery Review's acceptances
mechanically from their rulings. Deep and decompose runs write
schema-validated receipts (`operation` deep / decompose, a `composite`
block naming the component runs) and a deep run reopens from its
receipt alone. Encounter recording exists behind an owner switch,
visibly off by default: nothing is written while off, ids and event
types only when on, and each flip is itself recorded. An unresolved
Recovery Review case stays findable and reopenable by a later ruling
that cites it. `scripts/record_smoke.py` reports all of it, read-only.
No Observatory, trend, convergence, chooser or Portrait work.

## v1.3.3 — the Recovery Review, and the record's clocks

The six receipt-only acceptances of v1.2.3 have their surface
(`/recovery`, amendment in `docs/adr-concept-first.md`): each case as
the record holds it — the acceptance, the receipt's titles, sources and
time, and the explicit fact that no definition survives — and the
owner's ruling as new judgment events. Accept needs the owner's own
definition and mints the concept's identity at that ruling; Revise the
same with a corrected title; Reject is a rejection. Every ruling cites
the old judgment and receipt, carries its own clock and the epoch, and
appends to `recovery_review_rulings.jsonl`; the queue is never
rewritten; Home lists queue minus rulings, with a door. Four primitives
ride along: `ruled_at`, `epoch` and `origin` on every new judgment; the
owner-declared epoch (`epochs.jsonl`; the existing corpus is
`development_and_calibration`, begun otherwise only by a visible owner
action in About & proof); a record for every deep run with its
dissection, gesture, trial outcome and completion state; and input
provenance (typed / attached / door / connector / unstated). Legacy
rows keep their missing clocks. The Recovery Review and the deep
record are reopenable from the record; nothing here calls a model.

## v1.3.2 — the legacy shelf bridge: Home stops calling accepted concepts absent

Found on the first look at the real store: Home's Continue cards called
accepted concepts "not on the shelf" whenever the shelf entry predated
concept ids (35 of 39). Block 101 adds a read-only compatibility bridge,
Home's alone (amendment in `docs/adr-nikodemus.md`): exact stored title,
exactly one legacy entry, no concept-aware entry, no second entry of any
kind — used only to describe and open that persisted entry by its own
`acc_` id, said on the card as "On the shelf through an older
title-keyed record." Nothing is written, stamped, merged or resolved for
any other lane. Zero or many matches stay unresolved and say so. A
title-only row the loader shows back is named as that. A title-only
ruling is never tied to a concept by its title. The excluded line counts
the older rulings by what they are. `/api/library` carries each shelf
entry's own id. `scripts/home_smoke.py` reports Home against a store as
counts only, read-only by construction, with a before/after snapshot.
The one-time reconciliation (option B) is recorded with its evidence
ladder, not built.

## v1.3.1 — Needs your ruling holds only what has a door; the recovery queue is saved, not due

The reviewer's one correction to v1.3.0, owner-ruled (amendment in
`docs/adr-nikodemus.md`). "Needs your ruling" now admits an item only
when Home has a page to rule on it — a document, a recording, a room,
the Keeper; the rule is declared in the server and enforced
structurally, not by taste. The recovery review queue — the
accepted-but-absent, receipt-only concepts of v1.2.3, whose review is a
ruled step with no surface yet — is carried beneath the band as a quiet
"Saved for later" line: counted, named on hover, never a link, never in
the ruling count, hidden when empty. The queue file is read as before
and never rewritten; only its classification on Home changed. No review
surface was built; the suite pins its absence until the day it is ruled.

## v1.3.0 — the entrance: Nikodemus (formerly Wordicon), continuation-first Home

Effective 2026-09-02T08:20:00Z, by owner ruling (`docs/adr-nikodemus.md`).
The visible name of the environment is now **Nikodemus**; the change is
presentation-level and lives in one source, `config/brand.json`. Under the
naming law adopted with it — a new name begins when it is ruled;
historical records keep the identity they were created under; nothing is
rewritten to make the new name look older than it is — every entry below
this one, every route, identifier, environment variable, storage key, and
stored record keeps the name Wordicon. This changelog keeps its title.

Home is continuation-first: Continue (stored objects through stable ids;
a run alone never earns a card; ambiguous legacy titles excluded and
counted), Needs your ruling (five structured sources, never an alarm),
Bring something in (the original phrase box, one band down), then the
places — Concepts, Rooms, Library, Map, Write. Home paints with the
model gateway poisoned; healthy infrastructure is a quiet dot; the
provider's name moved to About & proof. The writing room is untouched.
Two navigation defects from the reconnaissance are closed: the concept
door resolves by id and asks when a title names two; the Bench hand-off
sends the id first. The Clinic is reachable from Home (Rooms) and takes
`?room=<id>`.


## v1.2.3 — concept-first identity migration (landed in the application; blueprint text now trails it)

The application is now concept-first and coinage-optional
(`docs/adr-concept-first.md`): an idea may exist without a coined name; a
name is a handle attached to a concept, never the concept itself; and no
persistent identity derives solely from a mutable human-readable title.
Concepts carry minted ids; names live as satellite records with their own
rulings and supersession history; the growth lanes, the Map, the Bench,
exports, and the Library all address concepts by id, with legacy
word-keyed records served through a read-only compatibility layer —
nothing historical rewritten. A read-only audit found the old title-keyed
schema had silently suppressed three distinct accepted concepts; they
were recovered by mechanical replay of the owner rulings on record, with
the original refusal evidence preserved; six receipt-only acceptances
wait in a Recovery Review queue for the owner rather than being inferred.

Closed and proven 2026-09-01: the 94-block suite green in the container,
on the owner's machine against the real corpus, and in CI; a
twelve-target sabotage battery (12/12 caught, byte-exact restores) and a
ten-step real-browser journey (10/10); and the closing acceptance ran
BACKWARD — the post-migration system restored and served the sealed
pre-migration vault, hash-verified byte-identical, with counts, anchors,
search, and the pairing gate intact under the new identity code.

Known drift, recorded rather than hidden (the v1.2.1 standard): the
blueprint text below still describes word-first identity in places.
Revising it is an owner-scheduled editorial pass; until then,
`docs/adr-concept-first.md` plus this entry are the accurate description
of identity in the running system.

## v1.2.2 — a real (non-mocked) usable loop

Not a blueprint change — no new object types, ADRs, or permission profiles, per explicit instruction. Adds `scripts/wordicon_cli.py`: a standalone CLI running Forge/Crack against a small static seed corpus (kernel_v1 + dc_000091 + the five public fixtures), with a real Already-Named heuristic (word-overlap, not full retrieval — a deliberate, disclosed simplification), a pluggable gateway (`mock` for offline testing, `anthropic` for a real Messages API call given your own `ANTHROPIC_API_KEY`), mechanical Bone-claim filtering (a claim survives only if it cites an admitted fragment id — checked in code against `validators.validate_bone_claim`, not trusted from the prompt), and judgment + receipt persistence across runs in `local_state/` so the anti-corpus and kernel signals actually accumulate.

Also fixes a real bug this surfaced: `operations.py`'s receipts were never actually validated against `receipt.schema.json` (only against the looser `validate_receipt_invariants`), and would have failed that schema check had anyone run it — `sources[].public_quote_cleared` wasn't in the schema. Added the field to `receipt.schema.json` (private-receipt-only bookkeeping, never copied into a public receipt) and added the missing `schema_loader.validate` call to both `operations.py` and the new CLI, so receipts are now actually schema-checked, not just invariant-checked.

Demonstrated live, end to end, with real (non-mocked) generation: three Forge candidates for "the quiet dishonesty of agreeing with someone just to end a conversation," a real adversarial pass that rejected two of them with substantive reasoning (one relied on a pre-existing eggcorn rather than a fresh coinage, one restated real pre-existing terms — "internal exile," "inner emigration" — more precisely than the candidate did), a winner grounded in one admitted public fragment, and a schema-valid private and public receipt. See the delivery message for the full transcript.

## v1.2.1 — documentation-drift fix

§20 previously said the package "implements and passes the twelve acceptance tests," which was imprecise: the twelve required *behaviors* are exercised by 26 pytest *test functions* (several behaviors have more than one test case), plus two additional schema/documentation tests not among the original twelve, plus the independent 15-step vertical slice. Corrected in §20 to state the actual count and why it differs from twelve. Caught by an external review pass; fixed the same day rather than left as drift, per the project's own stated standard that a provenance-oriented system's documentation should not be casual about discrepancies like this.

Also in this pass:

- **Fixed a real permission-model gap**, not just a doc issue: `derived_only` was blocking external send of a Derived Constraint's *resolved text*, contradicting the design stated in §4.6 and ADR-002 that reviewed constraint text (never its source) should eventually be sendable to an approved vendor. Added a dedicated profile, `constraint_text_external_approved`, scoped exclusively to Derived Constraint objects — a Source assigned this profile is now refused at ingestion (`CorpusService.ingest`). Covered by `tests/schema/test_adr002_egress_policy.py` (10 new test cases; suite is now 36/36).
- **ADR-002 updated** with the profile fix and a new section proposing the minimal closure needed to unblock a benchmark (one vendor, two sensitivity tiers, explicit sign-off required) — distinct from full production closure, and not itself authorizing anything.
- **Added `docs/benchmark-plan.md`**: the four-condition (raw model / model + static prompt / model + naive vector memory / Sovereign Corpus Wordicon) comparison test plan, with a heterogeneous 12-prompt set, dimension-by-dimension measurement types (checkable vs. blind-rated vs. owner-only), and an explicit statement of what a 12-prompt run can and can't prove. Not run — blocked on ADR-002's minimal closure.

## v1.2 — consolidated canonical specification

Merges v1.0 and the v1.1 synthesis addendum into one authoritative document (`Wordicon_Sovereign_Corpus_Blueprint_v1.2.md`). v1.0 and v1.1 are retained below as history; do not edit them further. All future changes land in v1.2 and get a new entry here.

Adds, relative to v1.0:

- `Derived Constraint` as a first-class corpus object type, with its own schema, provenance (`derived_from` with per-edge `materiality`), review status, and revocation lifecycle (§4.1, §4.6).
- Dependency tracking that generalizes across all derived artifacts — constraints, Personality Kernel versions, chamber summaries, concepts, generated outputs, and receipts — instead of one-off revocation logic per object type (§13a).
- Revocation propagation into Personality Kernel versions: kernels are immutable, and a revoked essential dependency marks the kernel version invalid/review-required rather than silently patching it (§6.3, §13a.4).
- Revocation propagation into chamber summaries, which are now versioned objects with automatic regeneration queued on revocation, rather than an unversioned cache (§5, §8.4, §13a.4).
- Human-facing permission profiles (`private_raw`, `private_retrieval`, `derived_only`, `private_citation`, `public_source`, `training_approved`, `sealed`) as named bundles of the existing granular, machine-enforced flags — explicitly **not** modeled as an ordinal ladder, since the categories are independent capability sets, not levels of one scale (§4.5a, `config/permission-profiles.yaml`).
- Automatic capture of rejected candidates as unreviewed Judgment + negative Style example objects, staged separately from the canonical anti-corpus until reviewed, with an explicit distinction between "rejected for this concept" and "rejected everywhere" (§10.2a).
- A defined (proposed, not yet implemented) key-loss and recovery policy — `ADR-001-key-custody-and-recovery.md`.
- A defined (proposed, not yet implemented) model-egress boundary policy — `ADR-002-model-egress-boundaries.md`.
- Clarification that public-receipt exclusion of private material is a hard boundary (nothing private, not even redacted), and that historical receipts are annotated on revocation, never rewritten (§12.1, §12.3, §13a.4).
- A `revocation_event` object type recording every revocation and its blast radius (§4.1, §13a.5).

Correction applied during consolidation (per owner instruction, relayed via GPT, correcting the v1.1 addendum): permission profiles are named presets/bundles, not an ascending ladder. The v1.1 draft's seven-row table implied ordinal escalation; v1.2 explicitly rejects that framing in §4.5a.

## v1.1 — synthesis addendum (superseded by v1.2, retained as history)

`Wordicon_Sovereign_Corpus_Synthesis_v1.1.md`. Reconciled v1.0 against a parallel Gemini exchange on the same architecture. Identified: missing `Derived Constraint` object type; revocation not reaching Personality Kernel or chamber summaries; missing administrative layer above the granular permission flags; unformalized rejection capture; open key-custody question. All five points carried into v1.2, with the permission-profile framing corrected as noted above.

## v1.0 — initial blueprint (superseded by v1.2, retained as history)

`Wordicon_Sovereign_Corpus_Technical_Blueprint_v1.md` (as uploaded). Defined the base architecture: trust zones, corpus object model, epistemic/sensitivity classes, Personality Kernel, ingestion pipeline, hybrid retrieval, Crack/Forge/Crossbreed pipelines, Bone/Flesh/Friction contract, private/public/forensic receipts, mathematical scoring layer, API blueprint, security blueprint, deployment topologies, implementation stack, repository layout, eight-phase implementation plan, testing strategy, MVP definition, and the ten pre-implementation decisions.
