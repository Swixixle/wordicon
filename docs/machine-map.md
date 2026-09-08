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

**Where the work happens.** A run comes back as **readings** — Bone, Flesh, and
Friction layered so the objection is visible beside the claim — each with its own
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
and cites the receipt or ruling that produced it.

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
engines (forge, crack, decompose, sprout, refract, archetype), the Bone/Flesh/Friction
layering, the judgment log, the Map builder. `scripts/clinic.py` is the medical wing:
custody by institutional role, declared and never inferred supersession, one topic room.

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
constitution panel. `webapp/overworld.html` is the Map and Wayfinder;
`webapp/trails.html` runs as trails, every item a typed door; `webapp/bench.html`
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
