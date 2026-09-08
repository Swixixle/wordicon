# ADR: The constitution is canonical, the panel is an orientation

## Status

Ruled by the owner 2026-09-08, on the reviewer's information-architecture
ruling. Built in block 121.

## Context

The constitution — what Nikodemus promises, refuses, and will not claim — lived
inside the home page's "What is Nikodemus?" panel. It had reached about nine
thousand words on one scroll, inside the controls, because a standing law says
a wing that ships amends the constitution in the same block. It accumulates by
design, and the interface had no shape that survived the accumulation.

That is the same defect the interface blocks kept repairing one level down: a
true statement placed where its length or position makes it unreadable. Block
114 came from a demo where the first thing shown was the wrong thing. Block 116
put explanations behind a mark. Block 119 moved a partiality warning to the
front of a page because being third made it read as an afterthought. The
constitution was the largest instance and the last one anybody looked at.

Two repairs were rejected. Cutting it would delete substance the standing law
requires. Reordering the whole canon so the refusals came first would move nine
thousand words to solve a problem that is not about order.

## Decision

Four kinds of text, and they do not get mixed:

**Canonical law** — `/constitution`, from `webapp/constitution.html`. The whole
of it, in the five movements it has always had, in their canonical order. A
table of contents, stable anchors, a plain statement opening each movement, the
detailed explanation behind a native `<details>`, and one button that opens
everything for reading straight through or printing. Inert: no model call, no
network request, no runtime state.

**Interface summary** — the What-is panel on the home page. What Nikodemus is,
the refusals that define it, and the machine's live state. It is not a second
constitution and may not become one: it carries no movement heading and no
restatement of law. Each of its promises is a link carrying `data-canon`, and
the suite fails if any of those does not resolve to a real clause. The binding
words exist in one place.

**Current documentation** — `docs/`, indexed by `docs/README.md`, grouped by
the question each file answers. Every maintained Markdown file must be
classified there, explicitly excluded, or identified as generated; a check
enforces it, so a new document cannot become unreachable because someone forgot
to link it. Snapshot reports say they are snapshots.

**Historical design** — the three pre-rename Sovereign Corpus documents. Bodies
untouched, each carrying a header saying it is history and naming what replaced
it. Preserved because the reasoning is part of the record, not because it
describes current behaviour.

## The rule that governs the split

**Hide explanation when necessary; never hide state.**

A long explanation may sit behind a disclosure. A fact that changes how a result
should be read — a partial run, a failed warrant, an unverified source, a
provider boundary, an unsearched claim — stays visible where it matters. This
is why the provider status, the epoch control, the encounter switch, the speech
instrument and the connected-instruments readout did NOT follow the prose onto
the canonical page. They report what this machine is doing right now, and an
inert document is the wrong place for them. The first cut of this block moved
them anyway; the suite caught it.

## Consequences

The law does not bind less for being one click away. It binds because it is
canonical, versioned, and pinned by the suite — not because it occupied the
workspace. Amending it in the same block as any wing that ships is unchanged.

Every pin that held a constitutional sentence moved to the canonical file
deliberately rather than being softened. Three of them were fixed-byte windows
after a heading (`[:3000]`, `[:4000]`, `[:6000]`) that had been silently
shrinking their guarded region every time the prose above them grew; they are
now bounded by the section's own structure. That class of pin is not to be used
again.

## Amendment, same day: pointing is not enough

The first build pinned only that each panel line's `data-canon` destination
existed. The reviewer's objection: **a destination proves correspondence of
location, not correspondence of meaning.** He was right, and the demonstration
was worse than the objection. All five refusal lines were written in the
panel's own words rather than the law's, and one of them pointed at a section
that did not contain the claim at all — the check passed anyway, because the
anchor existed.

So a panel line must now be a **verbatim excerpt** of the region it names.
Every one is checked word for word against that region, and the suite fails on
either drift mode: an excerpt reworded, or a correct excerpt pointed at the
wrong clause. Both were sabotaged; both fail by name.

Regions are addressable at movement level as well as section level, because the
last movement carries a thousand words of its own body before its only section
label, and a clause living there had nothing to point at.

The panel may therefore contain navigation labels and verbatim excerpts of the
law. It may not contain a summary of the law in its own words. That is not a
style preference: a summary's accuracy depends on editorial judgment, no test
can check editorial judgment, and an unfalsifiable summary of binding text is a
second constitution wearing a link.

## A finding left visible rather than resolved

Blocks 119 and 120 amended the constitution by appending near a convenient
paragraph rather than a semantically right one, so the partial-workup law, the
attempt-ledger law and the retry-authority law all sit inside **The Library —
where kept things live**. They are correctly stated and correctly pinned, and
they are filed under the wrong heading. Moving them is restructuring, which
this block was told not to do. Reported here rather than quietly fixed.
