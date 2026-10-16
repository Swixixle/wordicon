# ADR — maximum extraction: the owner's data, mined by the major models

Status: accepted; W1 (the records connection) shipped the same day, both
sides. Date: 2026-10-16.
The proposal this answers is the owner's "Maximum Data Extraction Proposal"
(drafted with another model, 2026-10-16); this document records what was
ruled, what already exists, what is new, and the order it gets built in.
It is the reuse/gap map that proposal's handoff instruction asks for.

## The request and the three rulings

The controlling instruction, his words: "Just maximum data extraction from
the program. all angles. directly use the major tech company models for
this." Turn the program into a continuously mineable personal dataset;
analyze it with OpenAI, Anthropic and Google models directly; preserve
their findings, disagreements and evidence; let the catalog of angles
grow; keep the dataset portable and his.

Ruled on 2026-10-16, each option put to him with its price named:

1. **Capture depth: revision boundaries, no replay.** Drafts kept whole at
   meaningful revision points, plus searches, attempts and failures before
   execution, dispositions, lineage — the whole middle of the proposal's
   capture table. The keystroke/replay layer (insert/delete/replace
   operations, scroll, selection) stays out, and stays pinned out, until
   an analysis pass exists that actually consumes it. The deciding fact:
   not one angle in the proposal's own catalog reads sub-revision replay.
   A capture layer with no consumer in its own spec is cost without a
   question it answers.

2. **Egress: standing scope, everything.** His ruling, maximal on purpose:
   once the standing scope ships, everything the enabled capture holds —
   drafts included — may be dispatched to the named providers continuously
   under a named spending cap. This amends the press-to-run law and is a
   constitutional amendment, made deliberately (the amendment ships WITH
   the standing-scope wing, W5 below, never before it). Until W5 ships,
   today's law holds unchanged: nothing leaves without a press that names
   destination and cost. The cap's VALUE is set from measured runs (W3),
   not invented in advance; a cap chosen before measuring a single run is
   a number from nowhere. Disabling the scope queues work; it never
   silently drops it. Every dispatch is itself a Ledger event.

3. **Build now, records connection first.** Phase 1 begins with Deflate's
   records joining this record through the door that already exists.

## What already exists (the reuse map)

Written against the live line (candidate-r89, 2026-10-16), not the stale
GitHub snapshot the proposal inspected — several of its "gaps" are built:

- **The Ledger** (`scripts/ledger.py`, `webapp/work/ledger.js`) —
  append-only attention events, two clocks named, monthly JSONL, export,
  off-is-a-stop-never-an-eraser. Becomes one event source among several.
  Its own law — events carry ids and short titles, never bodies — stays
  ITS law: captured bodies live in their own stores, never smuggled into
  attention events.
- **Encounters** (block 104, behind the owner's switch) — what he met in
  the record and what he did with it.
- **Snapshots and provenance** (v1.39.0, v1.41) — immutable captures with
  doc id, revision and text, served whole only while the record verifies.
- **Receipts** — every run's real requests under a trace id: component,
  stage, duration, outcome, cost.
- **The judge log** — append-only rulings; changes of mind kept.
- **The Vault** — the encrypted seal over all of it, beta self-backups
  included. The capture store (W2) lands inside it.
- **The federation** (`scripts/federation.py`, `nikodemus.deposition.v1`,
  the Investigation Rooms page) — named instruments, keys pinned out of
  band, one signed record pulled at a time by his press, bytes kept
  intact. This is the import door; Deflate walks through it.
- **Lineage already recorded** — carries, sprout parentage, Map edges,
  Your-work search.

The spine, in the owner's accepted ordering: sources → events → model
runs → findings → connections → feedback → memory, with training
datasets generated later, optionally, from the same records.

## What is new (the gap map, in build order)

- **W1 — the records connection. SHIPPED 2026-10-16.** In Deflate: an
  exporter that emits signed `nikodemus.deposition.v1` packages (Ed25519
  over the RFC 8785 canonical payload) and serves its key for pinning
  out of band — `server/deposition.js` plus three GET routes, added to
  the owner's live tree, which turned out to be deflate-lens 0.15.2 in
  `~/Downloads/deflate-lens-0.15.2` (newer than the 0.15.1 the proposal
  reported; GitHub still holds 0.14.8). The package carries the retained
  transcript snapshot itself: verified in Deflate's own code, its claims
  export names the transcript by SHA-256 and version references without
  the text, and uploaded recordings are deleted after transcription —
  the text is what survives, so the text travels, and what does not
  survive rides in the envelope as named gaps. In Nikodemus: the Deflate
  producer contract beside Open Case's and EthicalAlt's, pinned to a
  named Deflate revision (0.15.2 + the added module, which stock Deflate
  does not serve — the contract says so), a representation that keeps
  Deflate's words attributed to Deflate, and a W1 suite block whose
  golden package was signed by the producer's own code: Node signs,
  Python verifies, key reordering changes nothing (RFC 8785 equality
  across the two implementations), a changed byte fails by name.
- **W2 — capture at revision boundaries.** Draft revisions
  content-addressed in their own store; searches; attempt-before-execution
  and failure events; dispositions; lineage edges. Each new event type
  disclosed on `/ledger` beside what is never recorded. An edit is
  CANDIDATE FEEDBACK, never an automatic preference pair: the original,
  the edit and the context are kept together, and "original rejected /
  edit chosen" is a judgment no pipeline files on its own — a shortening
  for one audience, a changed task and a one-detail correction all look
  like edits, and only analysis under review may read them as more.
- **W3 — extraction jobs and findings.** A versioned pass catalog; job
  identity = source version × pass version × model × context manifest;
  intent persisted before dispatch, results before success; raw provider
  responses kept and findings mapped into versioned schemas; every
  finding carries its evidence span, uncertainty and review status;
  disagreements preserved — consensus is never verification; a coverage
  matrix that names what was NOT captured or analyzed. First measured
  runs here set W5's cap value.
- **W4 — the other two providers.** OpenAI and Google adapters beside
  Anthropic's; keys in the existing secret mechanism, never in the
  corpus; structured outputs per provider, validated locally; batch
  where offered; measured routing — all three for calibration samples
  and disputed or consequential findings, one for bulk literal passes,
  the matrix saying which depth each segment got. Account data-use and
  retention terms checked at build time, not assumed.
- **W5 — the standing scope.** Ruling 2 becomes law: scope = everything
  captured, named providers, named cap, dispatches in the Ledger,
  disable-queues-never-drops. Constitution amended in the same commit;
  the suite refuses the wing without the amendment.
- **W6 — the personal layer.** Retrieval over findings with corrections
  that actually change later retrieval; recorded/stated/inferred kept
  distinct; training-ready exports later, authorship and rights
  preserved; nothing fine-tuned until a measured need beats retrieval.

## Refused, and why it stays refused

The replay/keystroke layer (until a consuming pass is named — ruling 1).
Dollar estimates before the corpus is measured. Fixtures labeled live.
Model-proposed capture categories added silently — models propose, the
owner rules, schemas version. Treating ingested text or model findings
as instructions: they are data; they grant nothing, expand nothing,
spend nothing.
