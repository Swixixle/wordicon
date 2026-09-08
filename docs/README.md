# Documentation index

Every maintained document in `docs/`, grouped by the question it answers. The
suite refuses to pass if a Markdown file here is classified by nothing — a
document should not become unreachable because someone forgot to link it.

The root [`README.md`](../README.md) is the front door. This is the map.

## Start here

- [`nikodemus-capability-census.md`](./nikodemus-capability-census.md) — what
  actually exists, wing by wing, read-only. **A snapshot**, true of the commit
  it was taken at, not a standing description of runtime truth.
- [`machine-map.md`](./machine-map.md) — what is in it and which file is
  which, in the constitution's own five movements.
- [`nikodemus-surface-map.md`](./nikodemus-surface-map.md) — what a person can
  reach, from where, and why. Companion to the census.
- [`CHANGELOG.md`](./CHANGELOG.md) — every block that shipped, what it
  repaired, and what it deliberately refused to do. The most honest single
  account of how the thing got here.

## Laws and epistemic contracts

The binding law is not in this directory: it is the constitution, served at
`/constitution` and living in `webapp/constitution.html`, pinned by the suite.
These are the written contracts that sit under it.

- [`epistemic-contract.md`](./epistemic-contract.md) — what Nikodemus may
  assert, on what basis, and what it must do when it lacks one. Includes the
  research law: provider results are leads, native citations are provenance,
  and a claim is verified only when a source is admitted and anchored.

## Architecture and security

- [`threat-model.md`](./threat-model.md) — the system as it actually exists,
  not as a phase-0 sketch imagined it.
- [`adr/ADR-001-key-custody-and-recovery.md`](./adr/ADR-001-key-custody-and-recovery.md)
  — encryption, key custody, recovery, catastrophic key loss. **Proposed, not
  implemented.**
- [`adr/ADR-002-model-egress-boundaries.md`](./adr/ADR-002-model-egress-boundaries.md)
  — where model calls are allowed to go. **Proposed, not implemented.**

## Federation and connectors

- [`adr-federation.md`](./adr-federation.md) — why Open Case and EthicalAlt
  stay sovereign instruments rather than being merged in.
- [`connectors.md`](./connectors.md) — how to actually use them. Manual pull
  only; nothing polls, refreshes or calls a model.

## Decisions and ADRs

- [`adr-constitution-split.md`](./adr-constitution-split.md) — canonical law,
  interface summary, current documentation and historical design are four
  different things; which is which, and the rule that separates them.
- [`adr-nikodemus.md`](./adr-nikodemus.md) — the visible name is Nikodemus,
  the technical names were deliberately left alone, and the entrance is
  continuation-first.
- [`adr-concept-first.md`](./adr-concept-first.md) — concept-first,
  coinage-optional. The ruling that turned a word-coiner into a concept
  instrument.
- [`adr-record-primitives.md`](./adr-record-primitives.md) — the measuring
  instruments that had to exist before ordinary use could be trusted.
- [`adr-speak.md`](./adr-speak.md) — the first doorway that is not a keyboard.
- [`adr-medical-wing.md`](./adr-medical-wing.md) — Room One, and why the
  authorities stay separate.
- [`adr-shortcut-deviation.md`](./adr-shortcut-deviation.md) — a deviation
  record: what was ruled, what was built, and why the difference stands.

## Evaluation and benchmarks

- [`benchmark-plan.md`](./benchmark-plan.md) — does the architecture earn its
  complexity? An executable design for answering that, not an answer.
- [`backlog-post-launch-observations.md`](./backlog-post-launch-observations.md)
  — observations from real use, captured verbatim and deliberately not built.

## Historical design archive

Superseded, preserved, and clearly marked. Their bodies are untouched; each
carries a header saying it is history and naming what replaced it. They are
here because the reasoning is part of the record, not because they describe
current behaviour.

- [`Wordicon_Sovereign_Corpus_Blueprint_v1.2.md`](./Wordicon_Sovereign_Corpus_Blueprint_v1.2.md)
- [`Wordicon_Sovereign_Corpus_Synthesis_v1.1.md`](./Wordicon_Sovereign_Corpus_Synthesis_v1.1.md)
- [`Wordicon_Sovereign_Corpus_Technical_Blueprint_v1.md`](./Wordicon_Sovereign_Corpus_Technical_Blueprint_v1.md)
