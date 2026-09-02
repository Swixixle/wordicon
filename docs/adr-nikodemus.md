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
