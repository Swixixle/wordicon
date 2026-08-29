# Backlog — post-launch observations (not implemented)

Captured verbatim from your first real usage session (the "species chrysalis" /
"Jesus" Crack run), 2026-08-22, per your own instruction: don't build any of
this yet, use the tool aggressively first and see what actually breaks. This
file exists so none of it gets lost between now and whenever that's done.

## UI/labeling fixes (small, whenever you're ready)

- `3 candidate(s) · 0 rejected` is misleading — "rejected" currently means
  *your* recorded judgment, not Friction's disposition. Two of three
  candidates got a Friction "reject" in the run that produced this count.
  Reword to something like `3 candidates · 2 Friction rejects · 0 curator
  judgments`, or `1 survived Friction · awaiting your judgment`.
- `critique: reject` next to a title reads like a debug console. Separate
  it visually and semantically from "YOUR JUDGMENT" — two different
  authorities: Wordicon's assessment (advisory) vs. your judgment
  (authoritative). E.g. "Friction finding: structurally weak" /
  "System disposition: reject", kept visually distinct from the
  accept/reject/revise controls.
- Rename "keep" → "survives" (or similar). "Keep" reads as arbitrary
  preference; the actual claim is that the candidate survived an attack.

## Bone presentation

Right now Bone shows `2 claim(s) grounded in admitted public sources` and
then a raw claim + fragment ID — provenance for the machine, not for the
person. Idea: render the claim as fact + confidence + why-it-matters, with
the fragment ID behind a disclosure panel rather than inline.

Also: some claim text currently blends the grounded historical fact with
Wordicon's own interpretive move in one sentence (e.g. "Exile removed a
person... — Jesus establishes a counter-community that functions as...").
Those are two epistemic layers and should probably be split: the Bone
claim stays purely the sourced fact; the interpretive application moves to
Flesh. The contract (nothing becomes Bone without a citable source) is
already stricter than the current display — this is a presentation gap,
not a contract violation.

## Friction attack taxonomy (candidate list, unvalidated)

Structural metaphor vs. illustrative metaphor was the key distinction that
came out of this session: a successful coinage's metaphor should reveal a
mechanism, not just supply a mood — "mapping A onto B reveals a mechanism
in A that was harder to perceive before the mapping." (Worth noting this
maps onto Lakoff & Johnson's structural-vs-conventional metaphor
distinction in cognitive linguistics — not inventing the concept from
scratch, just operationalizing it as a Friction check, which is a point in
its favor.)

Candidate recurring failure modes to eventually formalize and let the
anti-corpus learn from:
- metaphorical smuggling (rhetoric introduces ontology the argument hasn't earned)
- contradiction by definitional fiat
- false universality
- aesthetic redundancy
- conceptual redundancy
- historical overreach
- mechanism mismatch
- category error
- unsupported necessity
- axiom inflation
- ornamental profundity

## "Why this fooled me" feature

A button on a rejected candidate that generates a short diagnostic: what
gave it surface plausibility (elegant phrase, mirrored syntax, recognizable
motif) vs. what actually failed (no new mechanism, redundant, axiom adds
drama not explanatory power). Framed as a teaching tool for conceptual
discrimination, not just curation.

**Caution to carry into that feature, not just note here:** this is exactly
the kind of output that needs the same skepticism Friction itself exists to
apply. An LLM explaining "why it fooled itself" doesn't have privileged
introspective access to its own generation process — it would be producing
another plausible narrative, not a verified account. If this ships, it
should probably be labeled with the same epistemic caution as Flesh (an
interpretation, not a Bone claim), not treated as ground truth about the
model's own reasoning.

## Concept lifecycle / ancestry view

Draft → Provisional → Canonical → Contested → Deprecated, with Revoked
possibly separate (a provenance state, not an intellectual one). Opening a
concept would show its full ancestry: N candidates generated, N redundancy
failures, N historical distortions, N metaphor failures, N curator
rejections, N accepted. This has a real seed already in the original
blueprint's revocation/versioning design (kernel versioning, chamber
summary regeneration, `revocation_event` objects) — not starting from zero
when this gets built.

## RECENT section

Currently just prompt + operation type. Idea: show intellectual events
instead — "3 candidates · 1 survived · judgment pending", "accepted · 2
sources · kernel influenced", "rejected · redundancy" — so the home screen
shows the corpus evolving, not just a log of inputs.

## Forge/Crack semantic differentiation

Forge: "I have an experience that isn't named yet — help me form it."
Crack: "I already have a concept/word/argument — attack it, see if it
survives." Current UI doesn't make this distinction obvious at a glance.
Eventual product loop: Forge → Crack → Canonize.

## The thing to actually watch for, per your own framing

Not "does Flesh sound good" — LLMs are very good defense attorneys for
their own candidates. The real metric: how often does Friction destroy
something that initially sounded excellent? If that number stays high,
that's the system working, not failing.

## Open questions from your message, worth tracking answers to as you use it

Does Friction get repetitive or develop pet criticisms? Does it reject too
much? Does Already-Named actually work? Do sourced claims hold up under
inspection? Does the private constraint meaningfully change output? Are
three candidates enough? Do you ever strongly disagree with the system's
implicit read? Does recording judgments measurably change later output?
Does the corpus produce things a fresh Claude conversation wouldn't?
