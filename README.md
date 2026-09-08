# Nikodemus

A private, local workshop for developing ideas beside your sources and your
writing — and a record of how you got there that you can reopen and argue with.

Bring it a feeling you have no word for and it forges concept readings worth
disputing: the idea's anatomy, under a plain working title. Bring it a book and
the book stays a book, byte-intact, every sentence an anchor a claim can be
held against. Bring it a recording and the transcript scrolls under the sound,
one click from any sentence to its second. Nothing is kept until you rule on
it, and **your ruling is the only thing that decides**.

Three laws hold everywhere in it:

- **The critic advises and never decides.** It objects; you rule; the objection
  and your ruling are both kept, even when they disagree.
- **Anything it isn't sure of says so** — a claim with no source says so rather
  than being rounded up to searched-and-found.
- **Nothing changes without a visible choice.** No ruling recorded, no meaning
  rewritten, no check re-run, except by something you clicked.

The binding text is the constitution, served at `/constitution` when the app is
running. It is versioned, and the test suite refuses to pass if a wing ships
without amending it.

## What is built today

From [`docs/nikodemus-capability-census.md`](docs/nikodemus-capability-census.md)
— a read-only snapshot, not a promise:

A writing room; a forge that decomposes a passage into components and judges
each one; a Library that keeps documents byte-intact and reads five formats
without OCR; a Clinic where authorities stay separate; an Investigation Room
that pulls from Open Case and EthicalAlt without merging them; Inquiry; a
Bench for coinage when you want one; a Keeper with custody but no authority; an
encrypted Vault that restores a verified past and regrows nothing; a Map of
where the thinking has been; and Speak, which hears what you deliberately say
to it and transcribes nothing on its own.

Boundaries worth knowing before you judge it:

- It does not claim to beat a plain prompt. There is a bench for that question
  and the bench has not answered it.
- Search results from a provider are **leads**, not verification. A claim
  becomes verified only when a source is admitted through Nikodemus and tied to
  an exact anchor.
- Six judgments in the record were made by a model rather than by the owner,
  and are marked as such rather than quietly counted.
- It is single-owner and local. There is no multi-user model, and the LAN gate
  is an access lock, not encrypted transport.

## Run it locally

Python 3.13+. The app makes real model calls and they cost money.

```
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
python server.py
```

There is no `.env.example` to copy. Create `.env` yourself with the two lines
the server reports on startup:

```
ANTHROPIC_API_KEY=your-own-key
WORDICON_MODEL=your-model-slug
```

It serves on `http://127.0.0.1:8420`, loopback only. `WORDICON_LAN=1 python
server.py` opens it to your own network and prints a pairing code for a phone.
Jobs run in the background: the terminal and the machine have to stay awake for
a submitted run to finish, though the phone can be closed.

Without an API key it still runs — the offline gateway is deterministic and
proves the pipeline rather than the prose.

## First use

Type into the box on the home page: a feeling you have no word for, a passage
you are arguing with, a paragraph of your own. Press Go Deep for a passage with
several ideas in it, or Forge for a single one.

What comes back is a set of readings, each with its anchor in your text, a
craft objection from the critic, and a check on whether the anchor actually
licenses the claim. Nothing is saved until you rule. Reopen anything under
Recent; "another round" retries briefed on what failed.

## How its claims work

Four things are kept apart on purpose, and the interface never merges them:

- **The source** — what you admitted, byte-intact, with an exact anchor.
- **The proposal** — what the model wrote. Never treated as your conclusion.
- **The critic** — an objection on craft, plus a separate mechanical check on
  whether the quoted span supports the claim. Advisory. Never a gate.
- **Your ruling** — the only thing that settles anything. Append-only, so
  changes of mind are kept rather than overwritten.

Every run leaves a receipt under its own trace id, and every real request the
run made is recorded — which component, which stage, how long, what came back,
and whether it failed. A partial run says so before anything else on the page,
and no count on that page speaks for the components that never ran.

## Documentation

[`docs/README.md`](docs/README.md) is the complete index, grouped by purpose.
The three worth opening first:

- [`docs/CHANGELOG.md`](docs/CHANGELOG.md) — every block, what it repaired, and
  what it refused to do. The most honest account of how this got here.
- [`docs/epistemic-contract.md`](docs/epistemic-contract.md) — what it may
  assert and on what basis.
- [`docs/nikodemus-capability-census.md`](docs/nikodemus-capability-census.md)
  — what exists, read-only, at one commit.

## How it is tested

`python3 tests/test_global_constraints.py` — one suite of behavioural pins,
each named for the defect it prevents rather than the function it calls. It
reports three outcomes: pass, fail, and **skipped**, because a check that did
not run is not a check that passed.

`bash tests/journeys/run.sh` — fifteen browser journeys in real Chromium and
WebKit, for the things source review cannot see: rendered order, whether text
is really text, what survives with a stylesheet removed.

Pins are sabotaged deliberately: break the behaviour, confirm the pin fails
**by name** rather than by crashing. A check that cannot fail is not a check,
and this suite has caught nine of its own that could not.

## History and legacy names

Nikodemus was **Wordicon** until 2 September 2026
([`docs/adr-nikodemus.md`](docs/adr-nikodemus.md)). The record keeps the name
it was written under — nothing was rewritten to make the new name look older
than it is.

The legacy name is still the real name of real things, and deliberately so:
the repository is `wordicon`, the CLI is `scripts/wordicon_cli.py`, the model
environment variable is `WORDICON_MODEL`, the LAN flag is `WORDICON_LAN`, and
the package is `src/wordicon_corpus/`. Those are not branding oversights. A
name is a handle, never the thing, and renaming a working command to tidy a
logo is how a setup guide starts lying.
