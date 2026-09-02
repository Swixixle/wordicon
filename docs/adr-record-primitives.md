# ADR: The record primitives — measuring instruments before ordinary use

## Status

Built and proven in block 104, 2026-09-02, on the owner's execution
order relayed from the reviewer, and held for inspection: the owner's
"Begin ordinary use" has not been pressed, and this block does not
press it. Nothing here proposes, trends, converges, or chooses; every
primitive records or reports.

## Why

The corpus is in its declared `development_and_calibration` epoch. The
reviewer's ruling was that before ordinary use begins, the record must
be able to say four things about itself that it could not say in
v1.3.3: which prompt produced a run; who put a relation on the Map;
what every definition on the shelf was, when, and by whose ruling; and
what the owner actually met in the record, if and only if he asked for
that to be kept. Without these, later analysis of the corpus would be
analysis of a store that cannot distinguish its own hands. The sixth
primitive is a repair: an unresolved Recovery Review case must remain
findable and reopenable, because "not enough survives" is a ruling
about today, not forever.

## The primitives

The laws, in the reviewer's words: prompt identity is stage, template
version or hash, renderer version, model and settings — the record
holds never the assembled prompt, and never a hash of private text;
every new edge
carries an origin class and cites the event or receipt that produced
it, and nothing is inferred while backfilling; definition events append
the exact definition, the concept id, the time, the origin and what
they supersede, and the shelf becomes a projection; deep runs settle
into the canonical receipt vocabulary; the encounter switch is visibly
off by default, nothing is written while it is off, only stable ids and
explicit event types are written when it is on, and turning it on or
off is itself recorded; unresolved cases remain findable and
reopenable.

**Prompt identity.** A receipt names the prompt templates behind it as
`prompt_identities`: one entry per stage the run used — `stage`,
`template_sha`, `renderer_rev`, `calls`, `gateway`, `model`,
`settings`. The template hash is computed from the builder's own source
code, its helpers and the constants it names (`template_sha_of`), never
from the assembled prompt and never from private text: two runs over
different passages carry identical identities, and editing a template
changes its identity. Every `build_*_prompt` in the CLI is registered
by stage (`PROMPT_STAGE_BUILDERS`; the suite fails on an unregistered
builder); each is wrapped at import so a call notes its stage on a
per-thread ledger that the run drains into its receipt. Model and
settings are the gateway's as the code holds them; sampling is recorded
as the API default because the code sets none. The Keeper's, the
Clinic's and the Library's own prompts are not yet registered — a
documented absence, not a claim.

**Edge origin and producer.** `record_edge` now requires an `origin` —
`mechanical`, `owner_declared`, `model_proposed`, `imported` — and a
`producer` citing the receipt, judgment, owner declaration or result
snapshot that produced the edge, checked before the best-effort write
so a missing origin surfaces as a programming error. The classes were
assigned per call site by what actually happened: `produced`,
`forged_as`, `reworked_into`, `renamed_as`, `compressed_as` and
`continued_from` are the pipeline's own links (mechanical, citing the
receipt); `decomposed_into`, `parallels`, `archetype_of`,
`translated_as` and `english_fossil` are a model stage's proposals
(model_proposed, citing the receipt and naming the stage — the
archetype run has no receipt and cites its result snapshot);
`declared_road` is the owner's (owner_declared, citing a minted
declaration id the Wayfinder row also carries). Rows written before
this block carry no origin; the reader labels them `legacy_unknown` in
memory and never infers one from the relation. The file is not
rewritten. The real corpus held 1,606 such rows at the start of this
block — every edge it had — and they stay as they are.

**Definition events.** Every write to the shelf is first an appended
event in `definition_events.jsonl`: `defined` or `retracted`, the entry
id, the concept id, the title, the exact definition at top level, the
time, the origin (`run`, `bench`, `recovery_review`, `retraction`,
`baseline_snapshot`, `reconstructed_recovery`), the judgment cited, and
`supersedes` — the latest earlier event for the same entry, found
mechanically. The shelf file stays what readers consult; it is now a
projection that `rebuild_shelf_from_events` rebuilds and
`shelf_projection_check` compares, reporting and never repairing.
Older entries get exactly one clearly labeled baseline through
`scripts/shelf_projection.py --baseline`: an entry whose concept id a
Recovery Review ruling minted is reconstructed mechanically from that
ruling (its clock, its judgment id, the definition the owner supplied —
read from files, nothing inferred) and marked `reconstructed`; every
other entry is a `baseline_snapshot` — the entry as found, dated now,
carrying its own `accepted_at` as an observed fact and no history the
record does not hold. Running the baseline twice appends nothing.

**Composite runs in the receipt vocabulary.** A deep run and a
decompose run each mint their own trace id before their first model
call and write a schema-validated receipt under it — operation `deep`
or `decompose`, a `composite` block naming the component runs by trace
and receipt id with the completion state, and for deep the gesture and
the trial's verdict — plus the result snapshot the page reopens. The
parent receipt lists no candidates of its own, so nothing is counted
twice; the component forges keep their receipts. A deep run reopens
from its receipt alone when the snapshot is gone, and the page is told
exactly what the snapshot held that the receipt does not. The block-103
deep record is superseded by this, as the reviewer required.

**The encounter switch.** `encounter_switch.jsonl` holds the owner's
flips; the switch is off by default and reads as "off (default — never
turned on)" in About & proof until the first flip. While off, nothing
is written — not a row, not a file: the page never posts, and the
server refuses a posted encounter with a 409 and the reason. When on,
`encounters.jsonl` takes ids and explicit event types only
(`system_surfaced`, `owner_opened`, `owner_selected`, `owner_reused`,
`owner_cited`, `sprouted_from`, `refracted_from`, `revised`,
`linked_by_owner`, `linked_by_proposal`, `exported`); anything shaped
like text is refused. Turning it on or off is itself recorded, with the
epoch. In this block exactly one door emits an encounter — opening a
shelf entry from Home (`owner_opened`); the other types are vocabulary,
wired to nothing yet. `/api/encounters` shows the raw log and counts
nothing.

**Unresolved, reopenable.** A Recovery Review case ruled `unresolved`
is not due — the owner ruled — but it stays listed on `/recovery` under
"unresolved — reopenable", counted on Home in a quiet line that is not
a ruling, and a later Accept, Revise or Reject appends a ruling that
carries `reopens` and whose judgment events cite `prior_ruling_id`. A
second `unresolved` on an unresolved case is refused; any other ruling
in force still closes the case. The queue is never written.

## What this block did not do

No Observatory, no trend analysis, no convergence, no series, no
destination chooser, no Portrait, no Name Study, no aside lane. The
shelf's readers still read the file, not the projection — flipping
them is a later decision with its own evidence. The trace id recipe of
ordinary runs (`sha256(input_text + now)[:10]`) predates this block and
was left as it is; it is noted here because it hashes the input with a
clock, which the prompt-identity law forbids for identities but which
was never an identity.

## The real corpus, 2026-09-02 (read-only counts, then the one baseline)

Before the baseline: 1,606 edges, all `legacy_unknown`, none with a
producer; 106 shelf entries and no definition events; 432 receipts
(crack 7, crossbreed 115, forge 310), none with prompt identities and
none composite — no deep run has a receipt in the store, because none
was run since the deep record existed; the encounter switch off with
no flips; the Recovery Review 6 ruled, 0 open, 0 unresolved. The
baseline's dry run would reconstruct 6 and baseline 100; applied once,
it wrote 106 events — 6 `reconstructed_recovery` at the rulings' own
clocks (10:38–10:44 UTC that day), each citing its accepted judgment,
and 100 `baseline_snapshot`, each keeping the entry's own `accepted_at`
(earliest 2026-08-23) as an observed fact — and the shelf equals its
projection. A second run appended nothing. Every receipt written from
now on carries its prompt identities; every edge its origin and
producer; every shelf write its event.

## Acceptance, as proven by the suite (block 104)

Identical templates hash identically and an edited one differs; two
runs over different passages carry identical identities and no
identity carries the input or the assembled prompt; every
`record_edge` call site passes an origin and a producer minted by
`edge_producer`, a produced edge carries its receipt, a legacy row
reads as `legacy_unknown` without the log changing; the shelf equals
its projection after the baseline, after an acceptance and after a
retraction, and the events log only grows; a deep run's receipt
validates and reopens the run with the snapshot deleted; browsing with
recording off leaves the store byte-identical while both flips and one
recorded encounter appear once turned on; the unresolved case is found,
reopened with a definition, its judgment cites the unresolved ruling,
and a third ruling is refused.
