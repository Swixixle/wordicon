# ADR: The visible name is Nikodemus; the entrance is continuation-first

## Status

Ruled by the owner 2026-09-02 (the execution ruling on backlog item 39,
"Let's go"), effective **2026-09-02T08:20:00Z** (September 2, 2026,
4:20 a.m. EDT). Presentation-level only. Formerly Wordicon.

## The naming law (adopted verbatim)

A new name begins when it is ruled. Historical records retain the
identity under which they were created. Nothing is rewritten to make a
new name appear older than it is.

## What changed

The environment's visible name is **Nikodemus**. It is a label, not an
identifier, and it lives in one presentation-level source —
`config/brand.json` — consumed by the server (the pair page, the PWA
manifest, the anatomy stamp, the terminal banner) and by every page
through `/brand.js`, which fills `[data-brand]` elements and the page
titles at load. "Formerly Wordicon" appears in About, here, and in the
change record — never beside the wordmark.

Nikodemus names the environment. The Owner remains the only final
authority. The Keeper remains a separate speaking organ, named on its
own through the Play lane before it is activated. The External Witness
remains a role outside the membrane. The name grants no permission, no
authority, and no claim about consciousness.

## What did not change, deliberately

The repository name and remote; every route (`/bench`, `/clinic`,
`/map`, `/trails`, `/anatomy`, `/api/*`); environment variables
(`WORDICON_LAN`, `WORDICON_MODEL`, `WORDICON_NOTIFY_*`); local-storage
keys (`wordicon.session.v1`, `wordicon.workspace.v1`, …); the vault file
prefix and drill log; the state directory and every JSONL name; the
`wordicon_corpus` package; the `X-Wordicon-Manifest-Sha256` header; the
Bench method value `let Wordicon choose` (a contract, not a label);
test fixtures and the sanitization baseline; the CI workflow; and every
historical text — ADRs, blueprints, changelog entries, receipts,
judgments, Keeper entries — which keep the name they were written
under. Deep prose inside instruments (the Work Room's copy, the Play
lane's "not Wordicon judging") is left for the workspace pass the owner
has not yet ruled; it is prose, not a brand surface.

## The entrance (Home), in the same ruling

Home is continuation-first, in this order: **Continue** (real stored
objects reached through stable ids — concepts by `concept_id`, Rooms by
`room_id`, documents and recordings by their ids, the draft this
browser holds; a run alone never earns a card; a legacy ruling whose
title names two concepts, or none, is excluded and counted, never
guessed), **Needs your ruling** (bounded to five structured sources:
unruled document claims, unruled recording claims, Clinic disagreement
proposals, Keeper entries without a ruling, the recovery-review queue —
never failure-styled, never a backlog), **Bring something in** (the
original phrase box, same element and wiring, one band down, beside the
document, recording, and Room doors), then the **places**: Concepts (the
shelf), Rooms (Work Rooms and the Clinic), Library (documents,
recordings, sources), Map, Write.

Home paints with zero model calls and no provider-client construction;
`/api/home` reads local records only, and the suite poisons the gateway
to prove the page still paints. Healthy infrastructure is a quiet dot;
a vault failure stays red and specific. The provider's name is
provenance, shown in About & proof on demand, never as identity.

The writing room is protected machinery: its element is never rebuilt,
reparented, or recreated by Home; the draft, caret, undo history,
scroll, split side, and return navigation survive as before.

## Proofs

Block 99 of the suite (twenty required proofs, the static half) and the
browser journey (first paint at laptop size, the room's object identity
across Write / split / swap / full page / Bench and back, Back, widths,
reduced motion). Sabotage: provider construction returning to Home,
title-keyed continuation, writing-room reconstruction, historical-name
rewriting, ambiguous-legacy admission, the phrase box as hero again.

## Amendment 2026-09-02: saved, not due (the reviewer's correction, owner-ruled)

Block 99 as first rendered listed the recovery review queue under
**Needs your ruling** with the action "review not built yet — the queue
is the record": a ruling due with nowhere to make it. That is the
guilt-inbox failure the entrance was built to avoid. The correction,
ruled in the same session and carried by block 100 (`v1.3.1`):

**Needs your ruling** admits an item only if Home has a door for it — a
document, a recording, a room, the Keeper. The set of doors is
declared in the server (`HOME_RULING_DOORS`) and enforced structurally:
an item without one is an error, not a row. The band's sources are the
four actionable ones (unruled document claims, unruled recording
claims, Clinic disagreement proposals, Keeper entries without a
ruling); the paragraph above that counts five stands as the record of
what block 99 decided before the correction.

The recovery review queue — accepted-but-absent, receipt-only concepts
whose review is a ruled step with no surface yet — is reported apart,
beneath the band and outside it, as a quiet **Saved for later** line:
counted, named on hover, never a link, never in the ruling count,
hidden when empty. The queue file is read where the audit writes it
and is never rewritten by painting Home; the record is unchanged, only
its classification on Home is. No review surface was built; the suite
pins that absence so the day it is ruled is a ledger entry, not a
drift.

Proofs: block 100 of the suite (the doors, the split, the byte identity
of the queue across a paint, the line's placement and its every line
pinned); the browser journey (one ruling due, the saved line visible
and quiet at laptop, phone and split widths, gone when empty).
Sabotage: the queue back under the band; the doors grown to admit it;
the saved entries painted as rows inside the band; the line dropped;
the hide rule lost; the queue rewritten on paint; the saved entry
grown a door and a link.

## Amendment 2026-09-02: the legacy shelf bridge (read-only), owner-ruled

The first look at Home against the real store found a false statement
block 99 could not have seen from its fixtures: 35 of the 39 accepted
concepts have a judgment that cites a concept_id and a shelf entry
written before the persist wiring carried ids — title-keyed, `acc_`.
Home decided shelf membership by concept_id alone and called them
absent. The ruling (backlog item 41, option C): compatibility now,
reconciliation later, with a strict boundary.

**The bridge.** For a ruling with a concept_id that no shelf entry
carries, Home may locate a shelf entry only when the ruling carries the
exact stored title of the legacy acceptance, exactly one legacy entry
has that exact title, no concept-aware entry resolves the concept, and
no second entry of any kind exists. No lowercasing, trimming, fuzzy,
semantic or title-based merging. The result is used only to describe
and open that persisted entry by its own `acc_` id, and the card says
so — "On the shelf through an older title-keyed record." It writes
nothing, stamps nothing, adds no concept_id, is not a general identity
resolver, and may not be reused by the Map, the Bench, exports, or the
concept door merely because Home uses it; it disappears by itself the
day a ruled reconciliation gives the entry an explicit identity. Zero
or many matches: Home does not say the concept is on the shelf; the
ambiguity is kept and the owner is pointed at review.

**A shape found while proving it.** The shelf loader also shows back,
as a row of its own, the title of any accepted ruling that never got an
entry written. Such a row is not a persisted record; the card says "On
the shelf as a title only — its ruling is the only record," opens the
ruling, and offers the shelf by title. And block 99 had tied a
title-only ruling (no concept_id) to a concept when exactly one
concept-aware entry carried its title — identity from a title. It no
longer does; those rulings are counted, never carded.

**The excluded line** now distinguishes the older rulings honestly:
how many correspond to shelf entries, how many are revisions or
rejections, which titles name more than one entry; none were guessed
into Continue.

**Reconciliation (option B) is recorded, not built.** It needs an
evidence ladder — an explicit identity; matching acceptance judgment
and originating trace; matching stored candidate/run identity;
matching immutable definition or payload; an explicit owner ruling — a
snapshot and hash before mutation, classification of every candidate,
mutation only of proven or owner-ruled cases, siblings untouched, a
recovery event per stamped entry, every legacy row byte-identical
except the ruled addition, separate reporting of proven / ambiguous /
absent / owner-required, and a restore drill before closure. A unique
title supports the bridge's sentence; it does not rewrite identity.

Proofs: block 101 (the eight shapes the ruling names plus the two found:
one exact legacy entry; no entry; two concepts with one title; two
entries sharing a title; a rejected and a revised title-keyed ruling; a
title-only ruling with and without a modern entry; a modern entry that
must bypass the bridge; a title-only row; a near-miss title) — the
record's bytes across a paint, the bridge as Home's single helper with
no lowercasing or trimming in it, the card's sentences and doors, the
library carrying entry ids, `scripts/home_smoke.py` read-only by
construction. The browser journey renders all four shelf states and
opens the bridged entry by its id. `scripts/home_smoke.py` run against
the real store is the acceptance: the three accepted concepts stop
saying they are absent; the sibling stays unresolved.

## Amendment (block 105), 2026-09-02: the destination chooser — the intent layer, fixed once

Ruled by the reviewer's execution order (backlog items 42, 50, 53) and
pinned by the two failures that forced it. Home's intake band read
"press Run it" and ran whatever was typed through a deterministic
router into a concept-building lane: the owner's question about the
historical superstitions involving cats was forged into concept
readings of the wish to know, and his own name with his birth data
would have been forged the same way. Both were routing failures of one
kind — the record had no layer for *what he wanted done* — so one
layer fixes both, generally, and the router is not patched for names.

**What changed.** Once words are in the box (typed, or an attached
file's text), a row of destinations appears under it. The server reads
the words' shape mechanically — a question, a name beside a date and a
place, a single word, a short phrase, a passage, a statement — with no
model and no write, and returns the destinations that shape offers with
exactly one highlighted: Research outside Nikodemus, Search my record,
Develop the idea, Start a Room, Write from this, Save as an open
question; for a name with a date, Study the name, Create a private
portrait, Save owner-declared facts, and the rest. The highlight is a
reading, said as such with its signals; the law of the band is that
nothing runs until the owner chooses — the original Run it / Go deep controls and the gesture
chooser are unchanged but appear only after *Develop the idea* is
chosen, and Develop is offered for every shape so concept analysis
stays a deliberate choice, highlighted only where it is the plain
reading. A destination that does not exist yet — Research, Study the
name, the Portrait, the Owner Card — is shown as **unbuilt**, disabled,
with the reason, never as a button that quietly does something else.
The built destinations open their own lanes with the words: exact-text
search of the shelf and the library, a Clinic room with the words as
its subject (confirmed first), the writing room with the words as
words, and a new small object — an **open question**, kept verbatim
with how it arrived, in the Library under its own card, counted on
Home in a quiet line that is not a ruling due; withdrawing one appends
a status and rewrites nothing.

**Two boundaries the reviewer asked to see pinned (block 105b).**
Typing words and displaying destinations makes no model call and
writes nothing to the record — proven for the cats sentence and for an
identity-shaped input alike, with the gateway poisoned and the store
hashed before and after, in the suite and in the quiet browser journey
(the draft persists only in the browser's own storage). And the local
search is labeled as what it is — *Search my record*, exact text, never
the web — while the outward door is labeled *Research outside
Nikodemus* and marked not built, so the cats question can never mistake
a corpus search for internet research.

**Provenance.** `spoken` joins the input vocabulary before any
microphone exists, so the chooser is held from the first day to the
reviewer's law: the same sentence typed or spoken receives the same
destinations — provenance travels beside the words and never branches.
The job route records the door chosen and what the chooser had
highlighted on the input row, so the record can later count how often
its reading matched the owner's choice; it never infers either.

**Proofs (block 105).** The cats sentence reads as a question with
Research highlighted and unbuilt and Develop offered but not
highlighted; an invented name with a date and a place reads as identity
with the three studies unbuilt; typed and spoken give identical rows;
the reading route writes nothing and refuses the unpaired; the chooser's
page code calls nothing that runs; an open question is kept verbatim,
listed, counted, withdrawn by an appended status, and never due; the
intake's order is box → destinations → Develop's controls → doors; the
browser journey types the cats sentence, sees the row, saves it as an
open question without anything running, and reaches Run it only
through Develop.
