# The map of the machine

What is in Nikodemus, and which file is it. Moved here in block 121 from the
README, which became a front door; nothing was rewritten in the move. The
movements below are the constitution's own five, in its order — the front door,
this map and the law are meant to describe the same machine in the same
sequence, and a check fails if they stop agreeing.

For what a person can *reach*, see `nikodemus-surface-map.md`. For what is
actually built at a given commit, see `nikodemus-capability-census.md`. For the
binding text, see `/constitution` in the running app.

## The five movements

Five movements, in the order the About panel now tells them. They are not a pipeline —
you may enter at any of them — but they are the order in which the parts make sense.

**Bringing things in.** Nothing is read, heard, or examined until you hand it over, and
what arrives carries how it arrived. **Documents** reads five formats locally and keeps
the original bytes untouched, with deterministic anchors and no OCR — a photograph with
no text layer says so instead of guessing. **Media** takes a recording you own beside a
transcript you supply. **Speak** is a microphone and a local engine: nothing records
until you press it, the transcript lands editable, the audio never leaves the machine,
and the one network act is fetching the model once. **Depositions** arrive from your
other instruments — Open Case and EthicalAlt — as exact signed bytes, verified under a
key you pinned out of band (docs/adr-federation.md).

**Where the work happens.** A run comes back as **readings** — Claims & sources, Meaning,
and Critique (Bone, Flesh and Friction until 2026-09-13; the record keeps those keys)
layered so the objection is visible beside the claim — each with its own
receipt and its own support question, which asks whether a passage *grounds* a claim
and not merely whether it mentions it. The **writing room** is one live element that is
never rebuilt, so a draft, its caret, its undo stack and its scroll survive every layout
change. A **Work Room** raises the scale to a whole work: editions linked as separate
variations, never blended; passages only from imported text; readings kept as accounts
*about* the work and never rendered as its words. The **Clinic** keeps institutional
authorities separate — sources admitted by declared role, never blended into one voice,
questions about documents and never about a patient. The **Bench** is the smallest
scale: one kept word, split into the pieces any rework must carry, with the concept
first and the coin last, or never.

**What accumulates.** The **Library** holds what you kept — documents byte-intact,
crossings from exact spans, the works registry, the media lane. **The sources** treat
the outside world as a lobby and not a courtroom: templated doors that open searches and
record nothing, saved references with append-only access histories, a Wikidata QID
declared by hand with no lookup. The **Map** is everywhere your thinking has been, and
every relation on it names who put it there — the pipeline, you, or a model's proposal —
and cites the receipt or ruling that produced it; a relation from before origins were
recorded may be labeled *derived*, only from its run's own snapshot reproducing its exact
identity or from the writer invariant of the tracked history, never from its relation's
name, and otherwise *issuer not recorded*. The Map opens on **one place in focus**, chosen
never assumed, with its direct roads and four standings kept apart on each.

**What holds it.** Two organs keep and never produce. The **Vault** seals the corpus
into a standard age file and restores a verified past exactly — it regrows and improves
nothing. The **Keeper** has custody of the narration and no authority over the record:
it may have opinions, it may be wrong, and its wrongness stays inspectable.

**What it will not claim.** It never checks whether it actually *looked*; every check
asks "is this claim supported?" and none asks "did I search before saying nothing
exists?" — which makes an absence claim the least trustworthy thing it produces.
`scripts/blind.py` asks the question the tool cannot ask itself, whether any of this
beats one line of prompt, and under six decided pairs it refuses to conclude anything.

## Which file is which

Grouped the same five ways.

`server.py` is the trunk: Flask routes, the pairing gate (`scripts/gate.py`), the brand
source (`config/brand.json`, served once as `/brand.js` so the visible name has exactly
one origin), and the wiring between everything below.

**Bringing things in** — `scripts/library.py` is the zero-model wing: documents kept
byte-intact with deterministic anchors, span crossings, the two-axis support question's
mechanical half, the works registry, and the media lane (versioned transcripts,
time-anchored crossings). `scripts/speech.py` is the ear: audio in memory to a
transcript, no temporary file, no network, no language model.
`scripts/federation.py` is the controlled tissue facing Open Case and EthicalAlt —
pinned keys, credential *references* only, a fetcher locked to configured origins,
exact-byte custody of every package received.

**Where the work happens** — `scripts/wordicon_cli.py` is the oldest organ: the run
engines (forge, crack, decompose, sprout, refract, archetype), the Claims & sources /
Meaning / Critique layering (`bone`/`flesh`/`friction` in every record), the judgment log, the Map builder. `scripts/clinic.py` is the medical wing:
custody by institutional role, declared and never inferred supersession, one topic room.
`scripts/carry.py` is Carry Back: the append-only store of what the owner carried from
a workup back beside his draft (`local_state/carries.jsonl`), each carry's excerpt and
standing resolved from the run's own record and bound, by the run's recorded lineage,
to the text the run examined — file I/O only, no model, no network.
`scripts/notebook.py` is the writer's notebook: the document store behind the room
(`local_state/notebook.sqlite3` — documents with a stable id, exact body, revision and
fingerprint; every accepted save by its request id, so a lost reply is answered once;
checkpoints), one `BEGIN IMMEDIATE` transaction per save, a stale base refused with the
head returned — SQLite only, no model, no network; the Vault stages the file with the rest.
`local_state/kept_replies/` holds model replies that could not be used as they came —
a reply that parsed only after its unescaped inner quotes were escaped (the one repair
`_extract_json` makes, counted and noted on the run's receipt as a warning), and a reply
that did not parse at all (the failure names the file, and no longer quotes the reply) —
each whole, as it came, 0600, under the Vault like every receipt.
`run_refract` is Find related words / Explore other languages (2026-09-13): one pass,
two model calls, one record of mode `refract` — `english_synonyms`, `english_antonyms`,
`english_set_aside` (a word not in Latin letters, kept with its reason, never shown as
English), `cultural_comparisons` (reviewed on the same two axes as the terms), the
`refractions` with `language_canonical`, `period`, `pronunciation`, `meaning`, `example`,
`sections_asked` (a section asked and empty is not a section never asked; a record from
before this date has none), `source.entry` (concept / description / selection),
`source.passage` for a selection, `source.only_languages` for a follow-up. The selection
goes to BOTH calls exactly as selected (2026-09-14) — the reviewing stage judges fit
against the owner's own words, marked as his — and that stage runs TOOL-FREE
(`gateway.complete`, `review_mode: "tool_free"`, empty `citations`, `acquisition_usage`
None and never inherited): the call that sees his writing has no search tool on it at
all. Live lookup is `run_word_sources` / `POST /api/related/word_sources`, ephemeral like
verify, built from the word, its language and its period alone and refusing a body that
carries anything else; `REFRACT_PASSAGE_MAX` (4,000 code points, the unit the page's
`passageLen` counts too) is a refusal at `run_refract` and at the route, before an id is
minted or a job exists, never a silent cut.
`REFRACT_REQUIRED` is Spanish, Latin and Ancient Greek (`canonical_language` places
Attic/Homeric as Ancient, Koine/Hellenistic as Koine, Demotic as Modern, and a bare
"Greek" nowhere — `unplaced_greek`); the reviewer judges each English item
(`english_reviews`: yes / loanword / no — `_apply_english_reviews` keeps loanwords
marked and sets a "no" aside with the note, `english_set_aside[].by` = script | reviewer);
a pass with no title records no road, because there is no box to tie one to. `GET /api/related/saved` lists an idea's saved comparisons — by id
(`recorded`) or by title (`derived`) — reads only.
`local_state/saved_words.jsonl` is the words he kept from related-words passes
(`save_word` / `unsave_word` / `list_saved_words`): append-only, a removal is a second
row, one bookmark per (run, section, index) while it stands — a repeat hands back the
row it already has (`already`, and `already_saved` on the route) rather than making a
second (2026-09-14) — each row the item as it stood with its run, receipt, language, the meaning the
pass was made for and the reviewer's axes; it reaches no judgment, no accepted concept,
no document, no model; the Vault stages it with the rest.
Run identity (2026-09-13): every lane mints its id through `mint_trace_id` — the input,
the precise clock and sixteen random bytes, checked against the results and receipts
stores and against the ids this process has handed out — and writes its snapshot and
receipt through `write_run_snapshot` / `persist_receipt`, which create exclusively and
raise `RunRecordCollision` (a RuntimeError, so the writers that tolerate a disk error
cannot swallow it) rather than overwrite — a job that hits it is marked failed and that
run's result is lost with it; the record that was there stands. Job ids are minted the
same way against the live job table and RESERVED as they are minted (2026-09-14):
`_new_job_id` claims the row before it releases the lock, so two callers cannot pass the
check on one id and have the second replace the first's job; `_release_job_id` gives a
reservation back and never drops a real job; the job listings skip reservations. The shape of an id is unchanged and nothing in the
store is renamed.
`scripts/map_focus.py` is Map · focus: the served projection behind one place's ring —
exact-identity issuer derivation (`edge_specs_from_snapshot`, `SnapshotIndex`,
`derive_issuer`), provenance resolution, the ring with its burden, facets, groups and
order, the picker, and a read-only census (`--census --state ⟨local_state⟩`, which hashes
the store before and after) — reads only, no model, no network. The served map's
endpoints carry `recorded_key` and `resolved_by` where the concept-first post-pass moved
a legacy title key onto a concept box; sprout, refract, archetype and revise snapshots
store the source's `concept_id` (revise its `steered`/`wordify` flags) under `source`;
composite runs flush their split roads only after their receipt and snapshot exist
(`pending_roads`, `roads_appended`/`roads_failed`/`roads_withheld` on the record result).

**What accumulates** — `src/wordicon_corpus/` holds the schema-validated corpus
service; `scripts/shelf_projection.py` proves the shelf equals what its events rebuild;
`schemas/` and `config/` carry the data contracts and policy vocabularies enforced
everywhere.

**What holds it** — `scripts/vault.py` (seal, restore, drill),
`scripts/keeper.py` (custody of the narration, never authority),
`scripts/recovery.py` (the Recovery Review, where receipt-only acceptances wait for a
definition that comes from the owner or not at all), `scripts/export.py` (the corpus in
a shape something other than this tool can read).

**Asking whether it works** — `scripts/blind.py` (constrained stage versus a bare
prompt, labels hidden), `scripts/digest.py`, `scripts/scan_secrets.py`,
`scripts/hearing_preflight.py`.

**The interface** — `webapp/index.html` is the whole home: the writing room, the split
workspace, Documents, Media, Sources, Work Rooms, Library, and the *What is Nikodemus?*
constitution panel. `webapp/focus.html` is Map · focus — what the header's Map door
opens (`/map`, `/map/focus`; `GET /api/map/focus`, `GET /api/map/places`) — one place in
focus with its direct roads; `webapp/overworld.html` is Map · world, the spatial map and
Wayfinder (`/map/world`); `webapp/trails.html` is Map · trails (`/map/trails`, and the old
`/trails`, `/overworld`), every item a typed door; `webapp/bench.html`
reworks a kept word; `webapp/clinic.html` is the Clinic;
`webapp/recovery.html` the Recovery Review; `webapp/investigation.html` the
investigation lane; and `webapp/anatomy.html` draws the whole organism — every organ,
what constrains it, and what is not built yet — as its own constitutionally isolated
document.

## The anchor-fit census (block 122)

Diagnostic evidence, not a performance threshold, and not a recalibration.

**Population:** every candidate row carrying an anchor-fit verdict in the
owner's `local_state/results/*.json` at the time of the census — 539 rows.
Rows were counted per candidate as stored, so a candidate that appears in both
a component's own run and its parent's projection counts once per stored row,
and a rerun of the same input counts as new rows. Composite parents and their
component runs were both walked. The evaluator, its thresholds, its prompts and
its five-state stored vocabulary were unchanged by this and by block 122.

| anchor fit | rows | share |
| --- | ---: | ---: |
| `partial` | 292 | 54.2% |
| `topical` | 135 | 25.0% |
| `not_run` | 62 | 11.5% |
| `supported` | 34 | 6.3% |
| `contradicted` | 13 | 2.4% |
| `undetermined` | 3 | 0.6% |

Tier 1 anchor integrity over the same rows: `exact` 462 (85.7%), `absent` 56
(10.4%), `normalized` 15 (2.8%), `near` 6 (1.1%).

**What this does and does not establish.** It establishes a five-state
distribution with a large modal class. It does **not** establish that the
evaluator is uninformative, and the first reading of it that said so was wrong
and was corrected. The failure it motivated is a presentation failure: five
materially different results were being drawn as one row.
