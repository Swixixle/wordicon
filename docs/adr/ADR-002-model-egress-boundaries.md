# ADR-002: Model Egress Boundaries

**Status:** Proposed. Not implemented. This delivery calls no external model — the vertical slice's model gateway is fully mocked (`src/wordicon_corpus/model_gateway.py`). This ADR exists to define the policy that will govern real egress once the owner approves specific vendors.

## Context

Blueprint v1.2 §15.3 requires, for every external model provider under consideration, documentation of retention behavior, training-use policy, regional processing, logging controls, deletion options, contractual protections, and the maximum sensitivity level that provider's policy can support. §22 Q2 ("which external model providers, if any, may receive confidential excerpts") is listed as open. This ADR proposes the decision structure, not a specific vendor list — the owner has not named providers, and this document should not infer permissive defaults where the blueprint explicitly says not to (§22, closing line).

## Decision structure

Every object's `permissions.send_to_external_model` flag (blueprint §4.2, §4.5) is the enforcement point. That flag is `false` or an empty list by default for every profile.

An earlier draft of this ADR proposed carving out an exception within `derived_only` for the resolved constraint text. That was wrong in a way worth recording: `derived_only` governs the *Source*, and a single profile can't simultaneously mean "this object's raw text can never leave" and "the abstraction built from it can, once reviewed" without a code path that has to remember which meaning applies to which field — exactly the kind of ambiguity a permission system should never depend on a human remembering correctly. v1.2.1 fixed this with a dedicated profile, `constraint_text_external_approved` (`config/permission-profiles.yaml`), assignable only to Derived Constraint objects — a Source carrying it is refused at ingestion (`CorpusService.ingest`, enforced by `tests/schema/test_adr002_egress_policy.py`). The two egress-eligible candidates are therefore: `public_source` for Source objects, and `constraint_text_external_approved` for Derived Constraint objects — never the same profile serving both roles.

For any object where `send_to_external_model` could plausibly be `true`, the destination vendor must have a completed vendor policy record (per §15.3's seven fields) before the flag can be set, and the flag records *which* vendor(s) it's scoped to — it is not a global "may leave the vault" switch.

## Default posture (this delivery)

No vendor has a completed policy record. No profile's `send_to_external_model` is non-empty. The model gateway used in the vertical slice is mocked specifically so that this posture can be demonstrated as true by construction, not by policy alone — see `tests/permissions/test_derived_only_cannot_reach_external_model.py` and `tests/schema/test_adr002_egress_policy.py`.

## What must be true before this ADR can be closed

1. The owner names candidate vendors (§22 Q2).
2. For each, a vendor policy record is completed per §15.3.
3. The owner decides, per sensitivity class, which vendors (if any) qualify — this is expected to be "none" for `private_raw` and `sealed` under any circumstance, and possibly a short allowlist for `derived_only` constraint text and `public_source` material.
4. `config/permission-profiles.yaml`'s `send_to_external_model` entries are updated from blanket booleans to vendor-scoped allowlists, and the model gateway is extended from its current mock to enforce that allowlist per call, logging every egress event per §15.5.

## A minimal closure, if the goal is running the benchmark — not general production egress

The full closure above (§ "What must be true before this ADR can be closed") is the real requirement for production use. But the immediate reason to close any part of it right now is narrower: running the four-way benchmark comparison (`docs/benchmark-plan.md`) needs at least one real model call for three of its four conditions. A minimal closure sized to exactly that need, and no further, would be:

1. **One vendor**, named by the owner — not a shortlist, one, for this first experiment.
2. **Two sensitivity tiers only**: `public_source` (the five etymology/history sources already in `fixtures/public/`) and `constraint_text_external_approved` (the resolved text of `dc_000091`, never `src_personal_sanitized_001` itself). Nothing at `private_raw`, `private_retrieval`, `private_citation`, or plain `derived_only` changes — those stay exactly as closed as they are today.
3. **A vendor policy record** for that one vendor, even if abbreviated, covering the seven §15.3 fields — this is the one step that can't be skipped for speed, because it's the entire point of the ADR.
4. **Explicit owner sign-off on this document, in writing, before any config value changes.** This delivery does not treat "the owner asked for a benchmark" as implicit permission to also flip an egress flag — those are two different requests, and the second one is the one this ADR exists to gate. If and when that sign-off happens, the change itself is small: name the vendor in `send_to_external_model` for the two profiles above, complete the vendor policy record, and swap `MockModelGateway` for a real adapter scoped to exactly those two profiles.

Nothing in this delivery performs step 4. `docs/benchmark-plan.md` is written to be executable the moment it does, and to say plainly, at the point it needs a real model, that it's blocked on this.

## Consequence of leaving this open

Every operation in this delivery, and every operation until this ADR is closed, must run against local/mocked model inference only. This is consistent with the blueprint's own safest-default instruction (§22): "no raw private text sent externally" by default, and that default holds until explicitly overridden per vendor.
