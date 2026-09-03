# Nikodemus

*Formerly **Wordicon**, renamed 2 September 2026 by the owner's ruling
(`docs/adr-nikodemus.md`). The record keeps the name it was written under: nothing was
rewritten to make the new name look older than it is, and the technical names inside the
machine — `scripts/wordicon_cli.py`, `WORDICON_MODEL`, `src/wordicon_corpus/` — were
deliberately left alone. A name is a handle, never the thing.*

A private, evidence-bearing workshop. Bring it a feeling with no name and it forges you
concept readings worth arguing with — the idea's anatomy under a plain working title.
Bring it a book and the book stays a book — byte-intact, mechanically read, every
sentence an anchor you can hold a claim against. Bring it a recording and the
transcript scrolls under the sound, one click from any sentence to its exact second.
Coin a word at the Bench when you want one, cross a passage into evidence, walk the Map
of everywhere your thinking has been, enter a work the way you'd enter a room — and
every step leaves a record you can reopen, dispute, and re-rule, because in here **the
record is the product**.

It began as a word-coiner. Use revealed that naming was only one small part of the
work: the definitions, tensions, mechanisms, and boundaries were what kept getting
reached for, while the invented word in the headline was the field used least. So it is
now **concept-first and coinage-optional** (docs/adr-concept-first.md): an idea is
allowed to exist without a coined name, a name is a handle for a concept and never the
concept itself, and no identity anywhere derives from a mutable title. Two ideas that
happen to share a title are two entries, two boxes on the Map, two workbenches — and
anywhere a typed title could mean either one, Nikodemus asks instead of choosing.
Coinage stays, at the Bench, summoned — and "the descriptive phrase is sufficient; no
coined word improves it" is a success verdict there, not a failure.

Three laws hold everywhere in it: **the critic advises and never decides**; **anything
the tool isn't sure of says so** instead of quietly rounding up; and **nothing changes
without a visible choice** — no ruling recorded, no meaning rewritten, no check re-run
and no page reset except by a thing you clicked. Your ruling settles things, and only
your ruling, and you are allowed to change it — changes of mind are kept, never
overwritten.

## What is in it

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

## What it looks like

*All screenshots come from the automated verification batteries, run against a copy of
the real corpus.*

**Reading beside writing** — a document open in the split workspace, with a claim
crossed from an exact span. The claim is born `support: unruled`, because presence is
not support:

![Reading in the split workspace, a claim crossing below the document](docs/screenshots/split-reading.png)

**The media lane** — a recording you own beside the transcript you supplied. Click a
sentence and the player lands on its second; while it plays, the sentence under the
sound stays lit. The selected span became a time-anchored claim whose play button plays
only its seconds, then stops:

![The media panel: player, synchronized transcript, and a time-anchored claim](docs/screenshots/media-lane.png)

**A recording playing beside the writing room** — switching layouts or entering the
split restyles one element, so playback never stops:

![Media playing in the split workspace beside the writing room](docs/screenshots/media-beside-writing.png)

**A Work Room** — one work as a navigable place. Two editions linked as separate
variations (never blended), passages only from imported text, readings kept as accounts
*about* the work, never rendered as its words:

![The Work Room for The Fall with two variations kept separate](docs/screenshots/work-room.png)

**The outside shelf** — Wikipedia as the lobby, not the courtroom. Six templated doors
that open searches and record nothing; a saved reference with an append-only access
history; a Wikidata QID declared by hand with no lookup:

![The outside shelf: doors, a declared QID, an external reference with append-only status history](docs/screenshots/outside-shelf.png)

**Honesty when the record is thin** — a run from before result snapshots existed shows
its receipt and names exactly what is unavailable. A door never opens onto an
unexplained blank:

![A receipt-only run: titles and date survive, the reasoning is honestly gone](docs/screenshots/receipt-only.png)

## What is here, and what deliberately is not

This repository is the tool: server, web app, engines, tests, schemas, policies,
sanitized fixtures, and the constitution documents under `docs/`.

It is **not** the corpus. `local_state/` — every concept, judgment, document, recording,
crossing, and journal entry — lives only on the owner's machine and is ignored by git,
along with `.env` (API keys), generated reports, environments, and caches. A fresh clone
runs, but it runs *empty*; that is the boundary working, not a defect. The
same boundary cuts the other way and deserves saying plainly: **GitHub backs
up the code, not the corpus.** The corpus's own protection is the Vault
(`scripts/vault.py`): every server start, and after every quiet quarter-hour
of changes, `local_state/` is sealed crash-consistently into a standard
[age](https://age-encryption.org)-format file — openable by any age tool
forever, even if this tool dies — encrypted to the owner's recipient, verified
by a real decrypt before it counts, and proven by a restore drill that boots
an isolated copy against the restored corpus and checks it against the
vault's own interior manifest. The recovery secret exists in exactly two
places, neither of them a computer: the owner's password manager and a
handwritten paper copy, both proven by full re-entry at setup. Auth material,
`.env`, and the rebuildable search index never ride a vault; a restored
corpus demands fresh pairing, exactly like a new install. The corpus
additionally travels through the tool's own export, which writes a checksum
manifest so a copy can prove it was not edited after the fact.

## Running it

```bash
python3 -m venv .venv && source .venv/bin/activate
pip install -r requirements.txt
cp /path/to/your/.env .        # ANTHROPIC_API_KEY=… and WORDICON_MODEL=…
python server.py               # loopback only — this Mac
WORDICON_LAN=1 python server.py    # reachable on your Wi-Fi, behind the gate
```

The server prints its port (default 8420) and a **pairing code**. Every
corpus, media, export, mutation, and model-spending route is closed until a
device pairs: open `http://<computer-ip>:8420` (phone, same Wi-Fi, LAN mode)
or `http://localhost:8420` (this Mac), land on the pairing screen, type the
code once. The code travels only in a POST body; the session lives in an
HttpOnly, SameSite=Strict cookie; devices are revocable one by one on
`/pair`, and `python3 server.py --rotate-secret` signs out everything at
once. Honest boundary: this is a home-LAN access gate over plain HTTP — fine
on your own Wi-Fi, not confidential on shared or hospital networks. Model
calls happen only through lanes you explicitly invoke, on your own key;
importing, searching, crossing, and ruling are constitutionally zero-model
and work with no key at all.

Back up the corpus before trusting the tool with anything you care about —
from the SAME activated virtual environment as everything above (otherwise
`pyrage` lives in `.venv` while a bare `python3` launches a different
interpreter):

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt   # includes pinned pyrage
python scripts/vault.py init                # one-time custody ritual
python scripts/vault.py drill --blob <downloaded copy> --off-device
```

`init` shows the recovery secret once and proves you stored it twice
(password manager + paper) before the first vault seals; the off-device
drill of a copy downloaded back from your cloud destination is what makes
a backup real. `status`, `backup`, and `restore --blob … --out …` do what
they say — and a standalone `init`/`backup` refuses while the server is
running (the server holds an OS-level corpus lease for its lifetime; two
writers on one corpus is how backups go silently wrong). The page shows a
one-line vault strip that turns red the moment sealing stalls or fails.

## The map of the machine

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

## How it is tested, which is most of the point

```bash
python3 tests/test_global_constraints.py     # the whole suite, offline
python3 scripts/scan_secrets.py --tracked    # the owned secret scanner
(cd tests/journeys && npm ci && npx playwright install chromium)
bash tests/journeys/run.sh                   # eight browser journeys, real headless Chromium
```

All three run on every push and pull request via GitHub Actions
(`.github/workflows/suite.yml`, two jobs), keyless and corpusless, against a scratch
store with the model gateway poisoned and outbound HTTP pointed at a dead proxy — so
the repository proves its own commits and proves them offline.

One file, no framework: about 15,700 lines and roughly 1,500 named failures, with the
constitution's blocks numbered to 107 — and the discipline matters more than any of
those counts. Invariants are enforced in code and then *attacked*: every capability
ships with sabotage mutations (silent truncation, smoothed transcripts, auto-linking,
snapshot testifying instead of retrieval, doors falling back to blank pages, a signed
package trusted with its own key…), and a mutation the suite survives is treated as a
hole in the tests, not a pass. Block 107 alone was closed against 46 mutations, three of
which exposed real holes.

Three standing rules came from wounds: pin exact expressions, because substring needles
survive renames; **every rendered surface must prove its intended data arrived**,
because the day two routes claimed `/api/library`, the whole Library shelf rendered
empty while the corpus underneath was perfect; and **pin what can be reached, not what
exists** — three pins written in the last block passed against code that could never
run. The constitution can be flawless while the wiring starves it, so the wiring is
tested too.

## Status

A private tool, built by its owner for its owner, with AI collaborators under standing
rules: every capability summoned, reversible, provenance-bearing, and attached to an
existing human gesture — and anything that learns from use may form *toward* the owner,
but must never form him silently. Publishing any portion of this is a separate, explicit
decision that has not been made.
