# Backlog — post-launch observations (not implemented)

Captured verbatim from your first real usage session (the "species chrysalis" /
"Jesus" Crack run), 2026-08-22, per your own instruction: don't build any of
this yet, use the tool aggressively first and see what actually breaks. This
file exists so none of it gets lost between now and whenever that's done.

## UI/labeling fixes (small, whenever you're ready)

- `3 candidate(s) · 0 rejected` is misleading — "rejected" currently means
  *your* recorded judgment, not Friction's disposition. Two of three
  candidates got a Friction "reject" in the run that produced this count.
  Reword to something like `3 candidates · 2 Friction rejects · 0 curator
  judgments`, or `1 survived Friction · awaiting your judgment`.
- `critique: reject` next to a title reads like a debug console. Separate
  it visually and semantically from "YOUR JUDGMENT" — two different
  authorities: Wordicon's assessment (advisory) vs. your judgment
  (authoritative). E.g. "Friction finding: structurally weak" /
  "System disposition: reject", kept visually distinct from the
  accept/reject/revise controls.
- Rename "keep" → "survives" (or similar). "Keep" reads as arbitrary
  preference; the actual claim is that the candidate survived an attack.

## Bone presentation

Right now Bone shows `2 claim(s) grounded in admitted public sources` and
then a raw claim + fragment ID — provenance for the machine, not for the
person. Idea: render the claim as fact + confidence + why-it-matters, with
the fragment ID behind a disclosure panel rather than inline.

Also: some claim text currently blends the grounded historical fact with
Wordicon's own interpretive move in one sentence (e.g. "Exile removed a
person... — Jesus establishes a counter-community that functions as...").
Those are two epistemic layers and should probably be split: the Bone
claim stays purely the sourced fact; the interpretive application moves to
Flesh. The contract (nothing becomes Bone without a citable source) is
already stricter than the current display — this is a presentation gap,
not a contract violation.

## Friction attack taxonomy (candidate list, unvalidated)

Structural metaphor vs. illustrative metaphor was the key distinction that
came out of this session: a successful coinage's metaphor should reveal a
mechanism, not just supply a mood — "mapping A onto B reveals a mechanism
in A that was harder to perceive before the mapping." (Worth noting this
maps onto Lakoff & Johnson's structural-vs-conventional metaphor
distinction in cognitive linguistics — not inventing the concept from
scratch, just operationalizing it as a Friction check, which is a point in
its favor.)

Candidate recurring failure modes to eventually formalize and let the
anti-corpus learn from:
- metaphorical smuggling (rhetoric introduces ontology the argument hasn't earned)
- contradiction by definitional fiat
- false universality
- aesthetic redundancy
- conceptual redundancy
- historical overreach
- mechanism mismatch
- category error
- unsupported necessity
- axiom inflation
- ornamental profundity

## "Why this fooled me" feature

A button on a rejected candidate that generates a short diagnostic: what
gave it surface plausibility (elegant phrase, mirrored syntax, recognizable
motif) vs. what actually failed (no new mechanism, redundant, axiom adds
drama not explanatory power). Framed as a teaching tool for conceptual
discrimination, not just curation.

**Caution to carry into that feature, not just note here:** this is exactly
the kind of output that needs the same skepticism Friction itself exists to
apply. An LLM explaining "why it fooled itself" doesn't have privileged
introspective access to its own generation process — it would be producing
another plausible narrative, not a verified account. If this ships, it
should probably be labeled with the same epistemic caution as Flesh (an
interpretation, not a Bone claim), not treated as ground truth about the
model's own reasoning.

## Concept lifecycle / ancestry view

Draft → Provisional → Canonical → Contested → Deprecated, with Revoked
possibly separate (a provenance state, not an intellectual one). Opening a
concept would show its full ancestry: N candidates generated, N redundancy
failures, N historical distortions, N metaphor failures, N curator
rejections, N accepted. This has a real seed already in the original
blueprint's revocation/versioning design (kernel versioning, chamber
summary regeneration, `revocation_event` objects) — not starting from zero
when this gets built.

## RECENT section

Currently just prompt + operation type. Idea: show intellectual events
instead — "3 candidates · 1 survived · judgment pending", "accepted · 2
sources · kernel influenced", "rejected · redundancy" — so the home screen
shows the corpus evolving, not just a log of inputs.

## Forge/Crack semantic differentiation

Forge: "I have an experience that isn't named yet — help me form it."
Crack: "I already have a concept/word/argument — attack it, see if it
survives." Current UI doesn't make this distinction obvious at a glance.
Eventual product loop: Forge → Crack → Canonize.

## The thing to actually watch for, per your own framing

Not "does Flesh sound good" — LLMs are very good defense attorneys for
their own candidates. The real metric: how often does Friction destroy
something that initially sounded excellent? If that number stays high,
that's the system working, not failing.

## Open questions from your message, worth tracking answers to as you use it

Does Friction get repetitive or develop pet criticisms? Does it reject too
much? Does Already-Named actually work? Do sourced claims hold up under
inspection? Does the private constraint meaningfully change output? Are
three candidates enough? Do you ever strongly disagree with the system's
implicit read? Does recording judgments measurably change later output?
Does the corpus produce things a fresh Claude conversation wouldn't?

---

# Block 113 — what phase 1 did not close

## The live capability probe (blocked here; needs the owner's machine)

Production citation capture is **unconfirmed**. Everything phase 1 proves is
proved against the documented response shape and against fixtures, because no
provider is reachable from where it was built. The probe has three distinct
outcomes and they must stay three:

- `not_run_missing_credential` — no key was present. Says nothing about the
  provider.
- `ran_no_native_citation_observed` — a real search-enabled call was made and
  the response carried no citation objects. This is a finding about the
  provider, not about the collector.
- `native_citation_observed` — citations came back, and the collector kept them.

Collapsing the first two into "no citations" would hide the difference between
*we did not look* and *we looked and there was nothing*, which is the same
class of error as printing zero for a measurement nobody took.

## The suite has no census of its own blocks

A sabotage that deletes a block's **call site** — `pass` where
`_check_acquisition_record()` used to be — is missed by every check inside that
block, because the check that would notice never runs. Phase 1 fixed this for
one block by auditing at import time. It is a general hole: any block whose
call `main()` stops making disappears silently, and the suite still prints OK.
A census — every `_passNNN` defined must be called, checked structurally — is
the fix, and it is a block of its own.

## Still open in the Epistemic Presentation ruling

- **Quarantine.** Unanchored candidates are named as unanchored on their own
  cards, but not yet *grouped* under *Lateral possibility — not established by
  this text.*
- **Refuse malformed extraction.** An unnamed component (`component 2`) can
  still forge. The ruling requires a usable identity plus either a valid anchor
  set or an explicit `lateral_only`, and an extraction failure with Retry/Edit
  where those are missing.
- **Multi-span anchors.** An anchor is still one span. The ruling requires an
  anchor *set* that is never concatenated into a false continuous quotation,
  reporting which element each span carries, which remain absent, and whether
  the relationship between spans is textual or interpretive. This is a schema
  migration and wants its own phase.
- **Ranked initial view.** 3–5 central candidates first with the deterministic
  basis shown, remainder collapsed by component, expand-all available.
- **Cost receipt.** Operation, model, successful calls, input/cache/output
  tokens, elapsed, estimate before, actual after, parent run — and never a
  price inferred from elapsed time.

## The synthetic public fixture

Still to build, in Git, carrying the same structural traps as the owner's own
passage: an emotional reversal; one idea distributed over several sentences; an
unnamed or malformed component; a literal statement followed by an attractive
unsupported interpretation; and a relationship between distant spans that is
lost under independent decomposition. The owner's real passage stays outside
Git.

## Deep and decompose persist their parents differently (block 114)

A **deep** parent snapshot embeds each component's full candidates. A
**decompose** parent snapshot does not — it carries the component's display
fields and a link to that component's own run, so each candidate exists in
exactly one record.

Deep's shape has worked since block 103 and its reopen path depends on it. The
duplication is real though: the same candidate exists in the parent and in the
component run, and the two copies can drift — a judgment recorded against one is
invisible to the other. Unifying them is a schema migration with a real risk of
breaking reopen for every deep run already on the shelf, so it is written down
here rather than folded quietly into a block about presentation.

The decompose direction is the one to converge on: one record per thing, and a
door to it.

## The counted panel wants to be on Home, and can't be yet (block 115)

The counts ride on `/api/library` because that endpoint is the only place the
shelf is assembled — 150 lines that read every result snapshot, every receipt
and the judgments log, interwoven with the runs list and the lineage graph.

Home is deliberately light: it paints from `_home_concepts()` and does not even
ask `/api/config` on load, and the suite pins that. Putting the counts there
means one of two things:

- scanning the whole store on every first paint — **7.5 MB across 480 result
  files today**, and the scan is linear in runs; or
- extracting the shelf assembly out of `api_library` into a function two
  endpoints can call.

The second is right and it is a real change: it needs its own tests, because
every number on the Library page comes out of that block. Doing it inside a
block about presentation would be refactoring the Library by accident.

Until then the panel lives on the shelf, one click from Home.

## An outside assessment, reconciled — and deliberately not built (2026-09-08)

An outside assessment of Nikodemus recommended, among other things, ranking
ambiguities so the owner rules only on the "high value" ones, another generic
source-ingest door, and early pilots with users "who cannot afford
hallucinations". The assessment itself was not pasted into the build session;
what follows is the owner's reviewer's reconciliation of it, relayed by the
owner and recorded here verbatim because it is a ruling, and because its
strongest instruction is *build nothing merely because another product has it*.
Nothing below creates a block. The order at the end is the standing order.

> **SELECTIVE RESPONSE — DO NOT CHANGE THE CURRENT BUILD ORDER**
>
> The interface diagnosis is accepted. The ruling-burden and pilot conclusions
> are not yet established.
>
> **CORRECTION 1 — RULING BURDEN.** Nikodemus does not require a ruling on every
> ambiguity. Its historical record has had almost no deferred ruling queue; the
> owner usually rules inline or leaves proposals provisional. The prospective
> risk is narrower: Inquiry and Research may generate branching decisions faster
> than the owner can understand their consequences. Do not optimize an unmeasured
> burden. Establish this triage rule for future surfaces:
>
> *Blocking ambiguity* — ask immediately only when the answer changes: privacy or
> governed lane; source or person identity; what data leaves the machine; whether
> a paid/model/network act begins; which text or version is modified; whether
> something becomes an owner ruling or durable fact.
>
> *Material but nonblocking ambiguity* — proceed with separate labelled
> alternatives. Do not blend them. Offer a later ruling with the consequence
> stated.
>
> *Cosmetic or descriptive ambiguity* — preserve it as unknown or as a proposal.
> Do not interrupt the owner merely to complete metadata.
>
> "High value" must be defined by downstream consequence, not by a model's
> confidence that the question feels important. Do not build an
> ambiguity-ranking model. Measure actual interruption demand during real use
> first.
>
> **CORRECTION 2 — SOURCE INGEST.** Local-file ingest already supports EPUB,
> HTML, TXT, PDF, and DOCX. Media admission and institutional source admission
> also exist. Do not build another generic upload door. The missing capability
> is the acquisition-to-admission bridge: (1) the owner asks an outside-research
> question; (2) search returns leads, explicitly not evidence; (3) the owner
> selects a lead; (4) Nikodemus acquires or receives the actual source; (5) the
> Library records exact bytes, acquisition origin, extractor identity, access
> status, and failures; (6) exact passages become stable anchors; (7) claims
> cite those anchors; (8) support is proposed or owner-ruled separately;
> (9) search result, acquired source, cited passage, and owner conclusion never
> collapse into one object. That is the future Research door. Do not begin it
> inside the Carry Back, semantic-recall, or Markdown-export blocks.
>
> A browser capture mechanism may eventually help this bridge, but it must
> preserve: original URL and retrieval time; redirected/final URL; content hash;
> media type; what was actually saved; reader/extractor revision; paywall,
> login, inaccessible, dynamic, or partial-capture state; whether the page is a
> source, an index, or merely a lead; no claim that a saved page remains
> current; a later retraction or correction as a new event, never a rewritten
> original.
>
> GitHub/code is not another universal intake type. Debrief remains an external
> instrument whose signed, inspectable report may cross through federation. Do
> not fuse a code parser into the Library.
>
> **CORRECTION 3 — PILOTS.** Migration receipts prove that migrations preserved
> what their tests measured. They do not prove: product usefulness; reduced
> hallucination; comprehensive research; source quality; user comprehension;
> clinical safety; readiness for strangers. Do not recruit healthcare users who
> "cannot afford hallucinations." Nikodemus is explicitly not clinical decision
> support, and the Clinic has not completed shadow validation.
>
> Before any external pilot, the owner should complete five real workflows:
> (1) raw personal paragraph → Go Deep → Carry Back → owner-written second
> draft; (2) historical or cultural question → multiple readings → outside
> sources → exact admitted anchors → revised conclusion; (3) public healthcare
> or insurance-company investigation using organizational documents only, with
> no patient information; (4) one real Open Case deposition imported and
> inspected; (5) one real EthicalAlt deposition imported and inspected.
>
> For each workflow, record operational measurements rather than personality
> conclusions: time to first useful result; number of explicit interruptions;
> number of model and search calls; approximate cost; sources returned,
> acquired, admitted, and actually anchored; proposals corrected or discarded;
> owner rulings made; whether the work could be reopened the following day
> without reconstruction; which interface element caused confusion. No ambient
> behavioral interpretation is authorized. Only after those workflows should a
> small pilot begin, using public, reversible material and no patient-specific
> or legally sensitive unpublished data.
>
> **INTERFACE PRINCIPLE.** The daily product should feel like: a writing room; a
> question; the source beside the claim; one next useful action; the record
> waiting underneath. Rooms, receipts, Friction, Vault state, schemas, and
> provenance remain available contextually. They should not all compete on the
> first surface. Continue applying: *hide machinery; never hide material state.*
> Partiality, failed warrant, unverified standing, source absence, model spend,
> and privacy consequences remain visible. General explanations and internal
> anatomy may fold.
>
> **ORDER.** Do not create a new block from the quoted recommendation. Current
> order remains: (1) close Carry Back's server-authority and exact-identity
> repair; (2) manually prove the first-draft → excavation → Carry Back loop;
> (3) build and test optional local Semantic Leads; (4) build the portable
> Markdown projection; (5) run the five real workflows above; (6) reassess the
> Research acquisition-to-admission bridge from measured failures; (7) consider
> external pilots only afterward.
>
> Record the recommendation and this reconciliation. Build nothing merely
> because another product has it.

Item (1) of that order is block 123b, shipped with this entry. Items (2) and
(5) are the owner's, not the builder's: they are use, and they produce the
measurements that decide whether (6) is ever built.
