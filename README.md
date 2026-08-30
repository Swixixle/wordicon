# Wordicon

A private, evidence-bearing workshop. Bring it a feeling with no name and it forges you
candidates worth arguing with. Bring it a book and the book stays a book — byte-intact,
mechanically read, every sentence an anchor you can hold a claim against. Bring it a
recording and the transcript scrolls under the sound, one click from any sentence to its
exact second. Coin a word at the Bench, cross a passage into evidence, walk the Map of
everywhere your thinking has been, enter a work the way you'd enter a room — and every
step leaves a record you can reopen, dispute, and re-rule, because in here **the record
is the product**.

It began as a word-coiner. The words turned out to be the smallest part.

Three laws hold everywhere in it: **the critic advises and never decides**; **anything
the tool isn't sure of says so** instead of quietly rounding up; and **nothing changes
without a visible choice** — no ruling recorded, no meaning rewritten, no check re-run
and no page reset except by a thing you clicked. Your ruling settles things, and only
your ruling, and you are allowed to change it — changes of mind are kept, never
overwritten.

## What it looks like

*All screenshots come from the automated verification batteries, run against a copy of
the real corpus.*

**Reading beside writing** — a document open in the split workspace, with a claim
crossed from an exact span. The claim is born `support: unruled`, because presence is
not support:

![Reading in the split workspace, a claim crossing below the document](docs/screenshots/split-reading.png)

**A Work Room** — one work as a navigable place. Two editions linked as separate
variations (never blended), passages only from imported text, readings kept as accounts
*about* the work, never rendered as its words:

![The Work Room for The Fall with two variations kept separate](docs/screenshots/work-room.png)

**The outside shelf** — Wikipedia as the lobby, not the courtroom. Six templated doors
that open searches and record nothing; a saved reference with an append-only access
history; a Wikidata QID declared by hand with no lookup:

![The outside shelf: doors, a declared QID, an external reference with append-only status history](docs/screenshots/outside-shelf.png)

**The media lane** — a recording you own beside the transcript you supplied. Click a
sentence and the player lands on its second; while it plays, the sentence under the
sound stays lit. The selected span became a time-anchored claim whose play button plays
only its seconds, then stops:

![The media panel: player, synchronized transcript, and a time-anchored claim](docs/screenshots/media-lane.png)

**A recording playing beside the writing room** — switching layouts or entering the
split restyles one element, so playback never stops:

![Media playing in the split workspace beside the writing room](docs/screenshots/media-beside-writing.png)

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
forever, even if Wordicon dies — encrypted to the owner's recipient, verified
by a real decrypt before it counts, and proven by a restore drill that boots
an isolated Wordicon against the restored copy and checks it against the
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

`scripts/wordicon_cli.py` is the oldest organ: the run engines (forge, crack, decompose,
sprout, refract, archetype), the Bone/Flesh/Friction layering, the judgment log, the Map
builder. `server.py` wraps it in Flask routes plus the newer wings. `scripts/library.py`
is the zero-model wing — documents kept byte-intact with deterministic anchors,
span crossings, the two-axis support question's mechanical half, the works registry, and
the media lane (versioned transcripts, time-anchored crossings). `webapp/` is the whole
interface: `index.html` (the page, the writing room, the split workspace, Documents,
Media, Sources, Work Rooms, Library), `overworld.html` (the Map and Wayfinder),
`trails.html` (runs as trails, every item a typed door), `bench.html` (reworking a kept
word). `src/wordicon_corpus/` holds the schema-validated corpus service; `schemas/` and
`config/` carry the data contracts and policy vocabularies it enforces.

## How it is tested, which is most of the point

```bash
python3 tests/test_global_constraints.py   # the whole suite, offline
python3 scripts/scan_secrets.py --tracked  # the owned secret scanner
```

Both also run on every push and pull request via GitHub Actions
(`.github/workflows/suite.yml`), keyless and corpusless, so the repository
proves its own commits.

One file, no framework, currently 88 blocks — and the discipline matters more than the
count. Invariants are enforced in code and then *attacked*: every capability ships with
sabotage mutations (silent truncation, smoothed transcripts, auto-linking, snapshot
testifying instead of retrieval, doors falling back to blank pages…), and a mutation the
suite survives is treated as a hole in the tests, not a pass. Two standing rules came
from wounds: pin exact expressions, because substring needles survive renames; and
**every rendered surface must prove its intended data arrived**, because the day two
routes claimed `/api/library`, the whole Library shelf rendered empty while the corpus
underneath was perfect. The constitution can be flawless while the wiring starves it —
so the wiring is tested too.

## Status

A private tool, built by its owner for its owner, with AI collaborators under standing
rules: every capability summoned, reversible, provenance-bearing, and attached to an
existing human gesture — and anything that learns from use may form *toward* the owner,
but must never form him silently. Publishing any portion of this is a separate, explicit
decision that has not been made.
