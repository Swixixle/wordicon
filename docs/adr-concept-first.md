# ADR: Concept-first, coinage-optional

## Status

Accepted by the owner, from observed use, 2026-09-01. The off-device
Vault drill — the standing gate — passed the same day, and the build
proceeded on the owner's execution order.

## The identity law

No persistent identity may be derived solely from a mutable
human-readable title. New identity-bearing events mint
collision-resistant unique ids and cite the concept id separately.
Recovery of a suppressed acceptance is a mechanical replay of an
existing owner decision — never a new inference — preserving original
provenance, adding a recovery event (recovered_at, original ruling
time where the record holds one, recovery_reason:
legacy_title_collision), and modifying no old row. A record without an
owner ruling cannot reconstruct a concept; it waits in a Recovery
Review for the owner.

## Context

Wordicon began as a word-coining tool: bring it an unnamed experience,
receive candidate coinages, judge them. Real use — hundreds of runs,
then one long rabbithole session — showed a consistent pattern: the
owner reaches for the definitions, tensions, contradictions,
mechanisms, axioms, boundaries, lateral parallels, archetypes, and
cross-language material. The invented single word is the field he uses
least, and the interface gave it the largest type. The cards were
upside down: an invented word in the headline, and underneath it the
actual product — a definition worth keeping whether or not any coinage
ever sticks to it.

The system's own constitution already knew this. The panel says the
words became the smallest part; the Bench already practices meaning
first, structure second, language third, coinage last — and sometimes
never. The application is adopting its own lesson.

Reconnaissance then found the title-keyed schema had already cost real
data, which changed this from a preference into an integrity repair. A
second concept arriving under an existing title is silently refused
("already in your Lexicon, nothing added"). A read-only audit of every
acceptance ruling against the lexicon found three distinct accepted
concepts suppressed this way — including two sibling readings of the
corpus's own flagship concept — six further acceptances that never
reached the lexicon at all (receipt-only provenance, held for owner
ruling rather than inferred), and a third title-keyed identity system:
judgment ids derive from titles, so distinct concepts sharing a title
share one id in an append-only log. Recovery reconstructs only what an
owner ruling on the record authorizes, preserves original provenance
and time, and keeps the refusal evidence — the repair must not erase
the fact that the old schema refused them.

## Decision

An idea is allowed to exist without a coined name. A name is a handle
for a concept, not the concept itself.

Concepts become canonical objects with stable identity independent of
any display string. A concept's title may be the owner's original
phrase, a plain multiword description, an established term, a coined
word, or explicitly unsettled — none of that determines whether the
idea can be kept, connected, researched, or developed. Names become
related records attached to concepts, each with its own identity,
origin, ruling, and supersession history. Renaming can never change a
concept's identity, break a road, orphan an expansion, or rewrite a
judgment.

The default flow returns concept readings led by a plain working title
and the idea's anatomy (in one breath, definition, tension, mechanism,
axiom, boundary, grounding and Friction). The primary judgment is
about the idea. Growth lanes — Sprout, Archetype, Refract, Verify,
the Bench — lead; they remain summoned, never auto-run. Coinage moves
to the Bench as a deliberate tool, and "the descriptive phrase is
sufficient; no coined word improves it" is a success verdict. Lexical
novelty (UNCLAIMED, kitchen word, seminar term) belongs to the naming
layer and no longer gates or headlines a concept.

## What does not change

Wordicon keeps its name; word remains one of the main doors. The Play
lane is untouched. Nothing historical is rewritten: existing word
records render exactly as they always did and are read as concepts
with legacy labels through a compatibility layer; roads keep
resolving; no destructive migration runs; same-titled records are
never merged without an owner ruling. Older objects were created under
a word-first system and the record stays honest about that. The Vault
and the Keeper are architecturally untouched.

## Consequences

The repository shows a system that listened to evidence from its own
use and changed direction without erasing its history. The first
vertical slice proves one journey — phrase in, concept card out, kept
without a coinage, grown by ID through the lanes, optionally named at
the Bench, identity intact across Library and Map — before any broader
rearrangement.

## Cause

Observed use, not preference: the owner's session evidence and ruling
of 2026-09-01. Coinage stays because it sometimes produces something
unmistakably his — the error was never having a word forge; it was
making every idea audition for a single-word costume before it was
allowed to exist.
