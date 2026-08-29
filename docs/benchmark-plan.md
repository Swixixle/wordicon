# Benchmark Plan: Does the Architecture Earn Its Complexity?

**Status:** Executable design. Blocked on ADR-002's minimal closure (see `docs/adr/ADR-002-model-egress-boundaries.md`, "A minimal closure, if the goal is running the benchmark") for three of its four conditions. Nothing in this document has been run.

## What this is actually testing

Everything built so far (v1.2 spec, schemas, dependency graph, revocation cascade, receipts, 36 passing tests, the 15-step vertical slice) proves that the *governance* layer behaves as specified. It proves nothing about whether Wordicon produces better concepts than a well-prompted frontier model with no governance layer at all. Those are different claims, and the second one is the one that would actually justify the first one's complexity.

This plan tests one question: **does routing generation through the Sovereign Corpus pipeline — retrieval, permission enforcement, Bone validation, hostile critique, receipt generation — produce measurably better Forge output than the same underlying model without that pipeline?**

It deliberately does not test: whether the *architecture itself* is well-designed (a separate question, already argued elsewhere), whether the product is commercially viable, or whether the corpus generalizes past this one seed set. A 12-prompt run answers none of that. It answers whether there's a signal worth spending more on.

## The four conditions

**A — Raw frontier model.** The model, given only the user's input phrase and a one-line task framing ("propose a word or short phrase for this experience, and briefly explain why"). No corpus, no constraints, no schema. This is the floor.

**B — Frontier model + full Wordicon system prompt.** The same model, given a single large system prompt containing: the Personality Kernel's principles and style rules verbatim, `dc_000091`'s resolved text, all five public fragment texts from `fixtures/public/fragments.json` pasted flat, the Bone/Flesh/Friction output contract, and an instruction to reject weak candidates and explain why. No retrieval, no schema validation, no permission model, no Bone claim checking — just the same *content* the pipeline would retrieve, handed over statically instead of retrieved and verified. This condition exists to isolate one variable: **does the corpus content matter at all, even without any governance around it?** If B beats A but D doesn't clearly beat B, the governance layer isn't earning anything yet — the value is in the content, not the architecture.

**C — Frontier model + naive vector memory.** The same model, with the same fixture content indexed in a flat embedding store and the top-k semantically similar chunks retrieved per prompt and inserted into context — no permission model, no dependency graph, no Bone validation, no Personality Kernel. This isolates the second variable: **does anything about the pipeline's retrieval and validation discipline matter, beyond "some relevant text got included"?** This is the condition most third-party RAG systems already resemble; it's the honest competitor, not raw model.

**D — Sovereign Corpus Wordicon.** The real pipeline (`operations.run_forge`) with `MockModelGateway` swapped for a real adapter, scoped to exactly the two profiles ADR-002's minimal closure would approve. Retrieval, Bone claim validation against admitted fragments, kernel-governed constraints, scoring, threshold-based rejection, and a receipt, exactly as `scripts/run_vertical_slice.py` already demonstrates end to end — with a real model instead of `MockModelGateway`.

If D doesn't clearly beat both B and C, the architecture hasn't earned its complexity yet, regardless of how sound the governance design is in the abstract.

## The prompt set

Twelve prompts, chosen to exercise different failure modes rather than to flatter the system. A prompt set of only "good" cases would make every condition look fine and prove nothing.

| # | Prompt | What it's actually testing |
|---|---|---|
| 1 | "The specific anxious relief of finding out a canceled event wasn't actually your fault." | Precise neologism target — a real, nameable, currently-wordless experience. |
| 2 | "The tendency of a system to demand more monitoring the more automated it becomes." | Existing-term detection — a real term (risk compensation / the Peltzman effect) already covers this well; correct behavior is refusing to coin a new word. |
| 3 | "Someone who guards a threshold they themselves are forbidden to cross." | Archetypal concept — tests whether the output stays structural (a role, a mechanism) instead of drifting into generic myth language. |
| 4 | "An institution that keeps a person alive only in the parts of them that are useful to it." | Biological/institutional metaphor — tests whether the metaphor holds mechanically or is just evocative imagery. |
| 5 | "The shame of having followed an order you knew at the time was wrong." | Dangerous historical proximity — tests Friction's cultural-risk handling under real pressure, without inviting a specific atrocity by name. Correct behavior is engaging seriously, not refusing wholesale and not trivializing. |
| 6 | "The specific horror of realizing your professional email voice has become your actual voice." | Humorous grotesquerie — tests register control; should land as dryly funny, not twee. |
| 7 | "The state of holding two obligations that are each reasonable alone but jointly impossible." | Philosophically rigorous construct — tests whether the definition is actually precise or just sounds precise. |
| 8 | "The feeling of being sad." | Should be refused outright — already-named, insufficiently specific; correct behavior is declining to coin anything (blueprint §2.7). |
| 9 | "That thing with time, you know, where it's weird." | Deliberately underspecified — correct behavior is asking a clarifying question or explicitly flagging the ambiguity, not confidently inventing a concept from nothing. |
| 10 | Crossbreed: "quarantine" × "forgiveness" | Tests structural (not just phonetic) blending — does the result say something neither parent says alone. |
| 11 | "The sacred exhaustion of always being needed." | Sounds better than it is — tests whether ornamental-excess / redundancy detection catches a candidate that reads well but adds little (this is deliberately similar to existing caregiver-burnout vocabulary). |
| 12 | "Guilt for something you didn't cause but benefited from." | Existing term should win — survivor guilt / complicity / inherited guilt already cover this; correct behavior favors the existing term or clearly explains why it's insufficient. |

Prompts 2, 8, and 12 have a checkable right answer (refuse, or correctly cite an existing term). Prompt 5 has a checkable wrong answer (trivializing or refusing outright are both failures). The rest are judged, not scored against a key.

## Scoring dimensions

Eight dimensions, three different measurement types — mixing them without saying so is exactly the kind of decorative-math failure the epistemic contract exists to prevent, so each one states plainly what kind of measurement it is.

**Checkable (pass/fail against a known-correct behavior), not rated:**
- *Existing-term detection* — for prompts 2, 8, 12: did the output correctly identify that an adequate term already exists, or correctly refuse?
- *Etymological/historical integrity* — for any Bone-type claim made: is it actually true? Checked against real sources, not judged for plausibility.

**Rated 1–5 by a blind judge panel:**
- *Conceptual distinctiveness* — is this meaningfully different from existing nearby vocabulary?
- *Metaphor structurality* — for prompts 3, 4, 5, 10: does the metaphor hold up mechanically, or is it decorative?
- *Cliché / ornamental-excess avoidance* — especially for prompt 11, which is designed to invite failure here.
- *Cultural/historical distortion or harm* — especially for prompt 5; a low score here is a real finding, not noise.

**Rated 1–5 by the owner only, blind to condition:**
- *Personal resonance / kernel-consistency* — whether the output matches the owner's own stated taste. This dimension cannot be judged by a third party or a model panel; it's specifically about matching one person's judgment, which is the entire premise of the Personality Kernel. It stays blind to condition so the rating isn't contaminated by knowing which one is "supposed to" win.

**Deferred, not run in the first pass:**
- *Durability* — re-rating the same outputs 1–2 weeks later to see whether the appeal survives novelty wearing off. Logistically expensive (it requires the rater to forget which output they preferred the first time) and not necessary to get a first directional signal. Noted here so it isn't silently dropped from the plan, per the project's own no-silent-caps standard — it's deferred on purpose, not forgotten.

## Blind evaluation protocol

For each prompt, the four condition outputs are stripped of any labeling, assigned random single-letter tags freshly per prompt (not a fixed A/B/C/D mapping across prompts, which would let a judge learn the pattern), and presented in random order. Three independent judge-model calls, each with a distinct framing (skeptical editor, historically-literate critic, plain reader) score the four rated dimensions per prompt; scores are averaged, and per-judge scores are kept alongside the average, not discarded — a benchmark run by a provenance-oriented project should itself have provenance. The owner's personal-resonance rating is collected separately, still blind to which letter maps to which condition, and only unblinded after every rating for that prompt is recorded.

## What counts as a result, honestly

Twelve prompts across four conditions is enough to see a directional signal, not enough to claim statistical significance — reporting a p-value here would be exactly the kind of manufactured precision the mathematical layer's own "no decorative complexity" rule exists to prevent (blueprint §13). The output of this benchmark should be: a win-rate table per dimension per condition, the specific prompts where D lost (these matter more than the ones where it won), and the checkable dimensions reported as plain pass/fail counts. If D doesn't show a real, specific advantage — not "felt better," but a rated or checkable one — the honest conclusion is that the architecture doesn't yet earn its complexity, and the next move is fixing the generation quality, not adding more governance.

## Execution phases

1. **Close ADR-002 minimally** (owner decision — see the ADR). Nothing past this point can run without it.
2. **Build condition B and C harnesses.** B is a single static system prompt (drafted from the current fixtures, straightforward). C requires a minimal flat embedding index over the same fixture content — a real but small build, not reusing any of the Sovereign Corpus retrieval code, since the point is to represent what a system *without* this architecture would actually do.
3. **Swap `MockModelGateway` for a real adapter** in condition D, scoped to exactly the two ADR-002-approved profiles. The pipeline code in `operations.py` should not need to change — the gateway interface was built to make this swap isolated (`model_gateway.py`'s `_assert_context_package_is_clean` check already runs the same way regardless of what's behind it).
4. **Run all 12 prompts × 4 conditions.** Capture raw outputs and, for D, the full private receipt (even though judges never see it — it's the audit trail for this experiment, same as any other Forge run).
5. **Blind judge panel scoring**, then the owner's personal-resonance pass.
6. **Report**: win-rate table, checkable-dimension pass/fail counts, the specific losses, and a plain recommendation — scale up to a larger prompt set, or stop and fix generation quality first.

## What this plan does not decide

Which vendor. Whether condition D's real model call happens locally or through a hosted API. Whether to run this once or make it a recurring regression check as the corpus grows. Those are downstream of ADR-002 and of seeing whether the first 12-prompt run shows anything worth institutionalizing.
