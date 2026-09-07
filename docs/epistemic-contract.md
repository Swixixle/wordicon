# Epistemic Contract

Governs what Wordicon is allowed to assert, on what basis, and what it must do when it doesn't have enough basis to assert something. This is extracted and made binding from blueprint v1.2 §2 and §4.3, so it can be checked independently of the rest of the architecture.

## 1. What counts as Bone

A Bone claim is a factual proposition — linguistic, historical, scientific, or cultural — that the system asserts as documented rather than interpreted. A claim qualifies as Bone only if:

1. it cites one or more admitted corpus sources (not pretrained model knowledge);
2. it declares a claim type (historical, etymological, scientific, cultural, biographical, ...);
3. it carries a confidence score computed from the claim-support function (blueprint §13, \(Q(c)\)), not an unexplained number;
4. material disagreement between sources is disclosed rather than silently resolved in favor of one side;
5. every cited source's permission policy allows the use being made of it (quoting, summarizing, or citing without quoting).

If a claim fails any of these five, it is not Bone. It becomes Flesh (explicitly speculative), is quarantined for research, or is omitted. There is no fourth option where an unsupported claim is presented as documented because it is "probably true" or because a general-purpose model is confident about it.

## 2. What a language model is and isn't for

The model may synthesize, compress, compare, and propose candidates. It is never the source of truth for a Bone claim, regardless of how confident its output looks. Concretely: if the model gateway returns a claim with no `supporting_fragments` pointing at admitted sources, the Bone validator rejects it before it reaches a receipt. See `src/wordicon_corpus/validators.py::validate_bone_claim`.

## 3. Private influence without private disclosure

A Derived Constraint may govern an output without exposing the source it was derived from. This is not a loophole in the epistemic contract — the constraint itself is still fully accountable: it has an ID, a review status, a materiality-tagged dependency chain, and a revocation lifecycle (blueprint §13a). What's withheld from the public is the *source text*, not the *fact that private material contributed and how strongly*. The forensic receipt always has the full chain; the public receipt always discloses that a proprietary derived constraint contributed, without naming or quoting it.

## 4. Refusal is a valid output

The engine must be able to conclude, and say plainly:

- an existing word already suffices (Already Named);
- the proposed concept is not distinct from one already in the corpus;
- the evidence is inadequate to support a Bone claim;
- the requested metaphor trivializes a historical trauma;
- the output would be decorative rather than structurally meaningful;
- the requested material is not licensed for the requested use.

A refusal is not a failure state to be minimized — it's evidence the evidentiary standard is actually being enforced rather than rubber-stamped.

## 5. Verification is not a dial

Creative intensity, adversarial pressure, and register are user-adjustable. The evidentiary bar for Bone is not. There is no request parameter that lowers `Q(c)`'s threshold, and no "trust me" override — including from the owner — that admits an unsupported claim as Bone. If the owner wants to assert something as fact without a supporting fragment, that assertion belongs in Flesh, labeled as interpretation, same as anyone else's unsupported claim.

## 6. Failure modes this contract exists to prevent

- A model hallucinating an etymology and it reaching Bone because it sounded plausible.
- A private conversation's judgment leaking into a public result as if it were external scholarship.
- A rejected candidate's reasoning quietly disappearing instead of being captured as a negative example.
- A claim's confidence score being a number nobody can trace back to actual source authority, relevance, and entailment.
- The owner's own private conviction being asserted as documented fact rather than personal authority (which is a real epistemic class, §4.3, but a different one from external factual authority).

## 7. What a surface may say it acquired (block 113)

Every fact printed about how material was acquired must name the observation it
rests on, and a fact nobody observed is printed as a word, never as a number.

1. **`observed` is the record.** The acquisition record carries exactly the
   observations the client can make: that the provider's search returned a URL,
   and that the generated prose cited it. Both can be true of one source at
   once, so it is a list. Any other summary of the same rows is a convenience
   and may not be read as the authority.
2. **Opaque is not the same as unrecorded.** Where the search runs inside a
   provider, what it fetched and what the model read are opaque — there is no
   event to record, and there was never going to be one. A surface says so in
   those terms. It does not print `0`, which asserts a measurement, and it does
   not print "not recorded", which implies the event happened and was missed.
3. **No backfill.** A row written before an observation existed is displayed as
   it was written and reported as *not recorded*. It is never reinterpreted into
   a finding it never held, in either direction.
4. **A model's account of its own work is a claim, not a record.** Reviewer
   prose is labelled `MODEL SELF-REPORT — UNVERIFIED` wherever it appears. Where
   it contradicts the mechanical record, **the mechanical record wins**, and the
   surface says so rather than presenting the two side by side.
5. **A model-written illustration is labelled in the text itself.** Anything the
   system invented that could be mistaken for the owner's own words — an example
   sentence above all — carries `INVENTED EXAMPLE — NOT IN YOUR TEXT:` as real
   text, not as a colour, an icon, a tooltip or generated content, because those
   four disappear on selection, copy, export and screen reader. The label is
   never softened; if the presentation is heavy, the example collapses.
6. **Warrant outranks craft.** Where a candidate is well made and nothing
   established it, the craft verdict must say which of the two questions it
   answered. "No decisive objection" standing alone beside an empty warrant row
   reads as an endorsement, and did.

## 8. What a reader sees first (block 114)

**A passing check may be quiet. A failing check may not.** This is §7's rule
about absences read the other way round: an absence may never render as a pass,
and a pass was never required to shout. A check that succeeded may collapse
behind a disclosure that names what it holds. A check that failed, refuted, or
could not be run stays on the page.

**Nothing is collapsed that was not stored.** A warning shown while a run
executes must be in the record that run leaves behind, or reopening it shows a
clean page for a run that was not clean. The persisted projection carries every
field the surface renders; that correspondence is checked by derivation from the
surface, not maintained by hand in two places.

**One record per thing, and a door to it.** A parent run does not copy its
components' work into itself. It names each component, carries what it needs to
render the component honestly, and links to the run where that work lives — so a
judgment recorded once cannot be invisible to a second copy.

## 9. What the record may say about the owner (block 115)

The record holds a great deal about how the owner rules — what he keeps, what
he sets aside, where his judgment and the critic's went opposite ways. It may
report those, and the reporting is governed:

1. **Counting is not advice.** A surface that reports on the owner states counts
   over rows he can already open, in his own vocabulary, and stops there. It
   does not recommend, prioritise, or predict. A recommendation is a claim about
   a person produced by the machine that gains from him accepting it, and it
   belongs to the labelled tier with reviewer prose, not to the mechanical one.
2. **Disagreements are counted apart.** Overruling an objection and setting
   aside an unopposed candidate are different acts. One number covering both
   asserts something neither half says.
3. **An unrecognised ruling keeps its own name.** Folding it into a known
   category invents a ruling the owner never made.
4. **Zero is not a finding here.** The rule that an absence must be printed
   governs *checks* — a review that searched nothing has to say so. A tally with
   nothing in it has nothing to disclose, and printing it anyway trains the
   reader to skip the panel.

## 10. The face, the mark, and the door (block 116)

**A fact stays on the face; the explanation of the fact may go behind a mark.**
*The quote is not in your text* is a fact and stays. *Checked mechanically
against your source, not judged by the model* is a lesson about what kind of
fact it is, and belongs behind a mark that any reader can press once. A finding
never goes behind the mark, and §8's rule governs: a failing check may not be
quiet, and a mark is quieter than a disclosure.

**The mark is a control, not a hint.** It is announced, keyboard reachable, and
its text is in the document. A `title` tooltip is none of those and does not
exist on a touch screen.

**A door is offered only if it can do the job.** An action presented beside a
problem implies it bears on that problem. Where nothing the system can do
repairs a finding, it says so plainly and names why, rather than offering
actions that travel away from the problem while appearing to address it. An
unearned capability claim is the same class of error as a number nobody
measured.

**What is offered is computed from the record, never inferred about the owner.**
Which door is live follows from values already rendered on the surface. The
moment a proposal rests on a pattern in his behaviour rather than on the state
of the thing in front of him, it becomes a claim about a person and needs the
label §7 gives model self-report.

## 11. Provider citations are provenance, never verification (block 117)

A result the provider's search returned, and a native citation the provider
attached to generated text, are **discovery and provenance metadata**. They say
where something may have come from. They do not say that it is so.

**A claim becomes Nikodemus-verified only after the source is admitted,
retrieved through Nikodemus, and bound to an exact Library anchor.** That
sequence is the verification; nothing before it is.

This holds whatever the citation probe reports. Perfect native citation
capture would mean the provider tells us more about its own retrieval — a
better provenance record, and a better starting point for admission. It would
not move a single claim across the boundary. A surface that renders a native
citation as though it were an anchor has crossed it, and no measurement of the
provider can license that.

The probe's own readings are bounded the same way. Two calls establish what
those two calls did. They do not establish a provider rule — in particular,
citations appearing only on a question that demanded a verbatim quotation
establishes that this probe's result was prompt-sensitive, and nothing about
when the provider does or does not attach citations in general.

## 12. The research law, and what the provider's machinery is (block 118)

**Provider search results are leads.** Provider-native citations, when present,
are **provenance metadata**. A claim becomes Nikodemus-verified only after the
source is admitted through Nikodemus and tied to an exact Library anchor. This
is §11 stated as the durable rule rather than as a consequence of one probe.

**Provider-internal dynamic filtering is not a Nikodemus capability.** From
`web_search_20260209` onward the provider defaults `allowed_callers` to
`["code_execution_20260120"]` and runs its own code to filter its own search
results. Nikodemus configures no override, so those blocks are expected. They
are recorded as `provider_internal_dynamic_filtering` — counted and typed,
never parsed as evidence. They are not local execution, not an undeclared
capability, and not something Nikodemus gathered.

**Encrypted search content is opaque provider state.** It lets the provider
carry search context across turns. Its presence never means Nikodemus fetched,
read, or anchored the underlying pages, and its bytes are never retained or
printed — only presence, count and length.

**Cost and authorisation, measured rather than assumed.**

1. An ordinary web-enabled stage searches **once**. Two probe calls at one
   search each consumed 39,865 and 63,359 input tokens, because search-result
   content counts toward input tokens.
2. A Research operation that needs more discloses and confirms its maximum
   searches, model, provider and estimated token range **before** the first
   call. It does not inherit a higher default.
3. What is recorded is what the provider reported: `web_search_requests`,
   input, output and cache tokens, the tool version, and whether dynamic
   filtering ran.
4. **The number of code-execution blocks is never read as a number of billable
   calls.** Only the provider's usage fields say how many searches were made.
5. Where cost cannot be calculated it is displayed as `cost unknown`, never
   omitted and never estimated from tokens or elapsed time.
6. The owner can always cancel before the first call.
