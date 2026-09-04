# Changelog — Wordicon Sovereign Corpus Blueprint

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
