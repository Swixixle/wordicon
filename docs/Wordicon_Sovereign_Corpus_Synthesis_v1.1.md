# Wordicon Sovereign Corpus — Synthesis Addendum v1.1

**Reconciles:** the v1.0 blueprint (GPT) against the Gemini exchange on the same architecture. Written as amendments, not a rewrite — the v1.0 document stays the base.

---

## 1. What Gemini's pass actually adds

Most of the Gemini conversation is the same architecture in looser prose — useful for explaining the idea to a person, not for building it. Three things in it are genuinely worth pulling into the blueprint.

**A worked API example that's more concrete than the blueprint's own.** Section 14.3 of v1.0 shows an internal corpus request but never shows the response. Gemini's exchange shows both sides — a request with `requested_materials` and a response with `governing_constraints`, `relevant_concepts`, and `source_mechanisms` as separate typed lists. That's a better shape for the actual wire format than anything in v1.0, and it exposes a gap described below (missing object type).

**An ordinal permission ladder for humans, distinct from the machine-enforced flags.** Gemini's seven-row table (Private raw → Retrieval permitted → Derived only → Citation permitted → Public attribution → Training permitted → Prohibited) reads as a single scale a curator picks per source. The blueprint's section 4.5 is a bag of ~12 independent booleans with no default bundling. Both are correct at different layers, and the blueprint is currently missing the human-facing one — see the amendment below.

**The naming exercise itself is informative, not decorative.** Gemini's brainstorm (Black Library, Vault, Temperament Engine, Nikodemus Corpus, Sovereign Corpus) shows "Sovereign Corpus" was chosen from a set that included options implying different postures — "Vault" reads as pure containment, "Temperament Engine" reads as the kernel only, "Nikodemus Corpus" reads as personal/eponymous. "Sovereign Corpus" was the right pick: it names the ownership claim (sovereign) without collapsing the corpus into the kernel or into a single mood. Worth keeping the rejected names in a footnote so a future editor doesn't re-litigate it.

Everything else in Gemini's version — the fine-tune/retrieve/hybrid comparison, the "model replaceable, corpus not" framing, the two-tier receipt sketch — is v1.0 restated with less rigor. Where the two disagree in emphasis, v1.0 should win: its trust-zone framing (section 3.2, zones A–D) has no equivalent in Gemini's flat four-box diagram, and Gemini's two-receipt sketch is a simplification of v1.0's three-tier receipt with explicit invariants (section 12). Don't let the looser version leak back into the spec.

---

## 2. A real gap: derived constraints have no object type

Section 2.4 and section 8's context package both depend on "derived constraints" — natural-language rules like *"do not romanticize survivor guilt"* that leave the vault while the source stays inside it. Gemini's `governing_constraints` field shows this is already being treated, informally, as a return type. But section 4.1's object type list (Source, Fragment, Claim, Concept, Mechanism, Judgment, Style example, Person/tradition card, Permission policy, Graph edge) never defines it as a first-class corpus object.

That matters because everything else in this system gets provenance, versioning, and a receipt trail *because* it's a typed object with an ID. A derived constraint that only exists as a transient string in a context package can't be cited, can't be revoked when its source is revoked, and can't be reused across operations without silently re-deriving it (and possibly drifting) each time.

**Amendment:** add `Derived Constraint` as an object type.

```json
{
  "id": "dc_000091",
  "object_type": "derived_constraint",
  "text": "Do not romanticize survivor guilt.",
  "derived_from": ["src_personal_000142"],
  "derivation_method": "kernel_v1_manual | model_proposed | curator_authored",
  "confidence": "reviewed | unreviewed",
  "kernel_version_applicable": 1,
  "sensitivity": "derived_only",
  "reused_in_operations": ["trace_..."]
}
```

`derived_from` points at the private source, but that pointer is itself a private-only field — it appears in the forensic receipt, never the public one. This closes the gap and gives derived constraints the same lifecycle as everything else, including revocation (see next point).

---

## 3. A real gap: revocation doesn't reach the kernel or the summaries

Section 15.6 (deletion and revocation) says deleting a source must "queue re-evaluation of canonical concepts materially dependent on it." It does not mention two other things that quietly depend on private sources:

The Personality Kernel is hand-authored today (6.3) but the blueprint already anticipates it being updated "from repeated judgments." Once that happens, the kernel is materially dependent on specific conversations the way a concept is. If a source is later revoked, nothing in 15.6 flags the kernel version for review — it just keeps operating on a judgment whose source no longer exists in the vault.

The chamber-level summaries described in 8.4 ("hierarchical summaries of corpus chambers") have no versioning story at all, unlike ordinary objects (7.1 step 10). If they're built from a set of sources and one gets revoked, the summary is stale until someone remembers to regenerate it, and nothing in the system says who or when.

**Amendment:** extend the revocation propagation list in 15.6 to include: (a) flag any Personality Kernel version whose derivation history cites the revoked source, for owner re-approval before the kernel is used again; (b) invalidate and queue regeneration of any chamber summary built with the revoked source as an input. This is a small addition but it's the difference between "revocation" meaning what it claims to mean and meaning "revocation of direct citations only."

---

## 4. A real gap: permission administration at scale

The blueprint's 4.5 permission model is deliberately granular and default-deny, which is correct for enforcement. It says nothing about how a curator classifies hundreds of ingested objects without hand-setting twelve booleans each time. Gemini's ladder is the missing administrative layer, not a competing model.

**Amendment:** define named permission *profiles* that set all twelve flags at once, applied at ingestion and overridable per-object:

| Profile | retrieve_raw | send_external | derive_constraints | quote_private | quote_public | train |
|---|---|---|---|---|---|---|
| Private raw | owner-local only | false | true | true | false | false |
| Retrieval permitted | owner-local + private cloud | false | true | true | false | false |
| Derived only | false | false | true | false | false | false |
| Citation permitted | true | false | true | true | true (attributed) | false |
| Public attribution | true | true | true | true | true | false |
| Training permitted | true | true | true | true | true | true |
| Sealed | false | false | false | false | false | false |

This is the actual missing piece for Phase 2 (seed corpus, 3–6 weeks): without it, hand-setting permissions on ~150 seed objects is the kind of friction that quietly causes a builder to start taking shortcuts on the default-deny rule. A profile-first workflow keeps default-deny cheap to apply correctly.

---

## 5. A smaller gap worth naming: automatic rejection capture

Section 12.3 requires every final candidate to record rejected alternatives, and section 7.2 says AI-conversation acceptance should never be inferred just because the conversation continued. But nothing states whether a rejected Forge candidate automatically becomes an anti-corpus / Style-example object, or whether that requires separate curator action. Given the ingestion pipeline already has a pattern for this — auto-capture with low confidence, promote on review (7.1 step 8) — the same pattern should apply here explicitly: every rejected candidate is auto-written as an unreviewed negative Style example, and only counts toward retrieval-time anti-corpus matching once reviewed. Otherwise the rejection corpus, which section 20.5 correctly calls "one of the most valuable assets in the system," depends on someone remembering to curate it by hand.

---

## 6. One open decision neither document resolves

Section 22, question 10 asks what backup and key-custody model the owner wants, but section 15.1 never states what happens on key loss. For a system whose entire pitch is "the corpus outlives any model vendor," the actual single point of failure is the owner's own key management, not vendor lock-in. This isn't a flaw in either document — it's flagged as an open decision in v1.0 — but it deserves an explicit answer before Phase 0 closes, because "no ambiguity about who owns the corpus" (the Phase 0 exit criterion) is hollow if there's ambiguity about what recovers the corpus after a lost drive or a lost passphrase.

---

## 7. Net effect on the document

v1.0 stays the spec. This adds: one object type (`Derived Constraint`), two lines in the revocation cascade (kernel, chamber summaries), one administrative layer (permission profiles) sitting above the existing granular flags, and one clarification (auto-capture rejections at low confidence). None of this changes scope or timeline meaningfully — it fits inside Phase 1 (epistemic contract and schemas) and Phase 2 (seed corpus), before any code gets written.
