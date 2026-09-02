# Changelog — Wordicon Sovereign Corpus Blueprint

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
