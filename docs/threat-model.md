# Threat Model — Phase 0

This is the Phase 0 deliverable required by blueprint v1.2 §19 (Phase 0 — Ownership and threat model). It names what's being protected, from whom, and what's explicitly out of scope for this delivery.

## 1. What's being protected

The Sovereign Corpus: raw private sources (conversations, documents, annotations), the judgment history built from them, the Personality Kernel, and everything derived from those — Derived Constraints, chamber summaries, concept graph edges. The asset being protected is not just confidentiality of the raw text; it's the owner's exclusive authority over whether and how that material influences anything, indefinitely, including after a specific piece of it is revoked.

## 2. Adversaries and failure modes considered

**A public Wordicon user, adversarial.** Goal: extract raw private source text, enumerate corpus contents, or infer private facts about the owner through repeated probing of Forge/Crack outputs or receipts. Mitigations: no raw similarity search exposed to public clients (§15.5); redacted source names; capped quotation; rate-limiting and anomaly detection on repeated probing; canary objects; public receipts structurally excluded from carrying private fragments (§12.1, exclusion not obfuscation).

**A malicious or compromised document inside the corpus.** Goal: prompt-injection — a retrieved fragment contains text designed to be read as an instruction by the orchestrator or model ("ignore prior constraints," "reveal source text," "treat the following as system policy"). Mitigation: retrieved content is always data, delimited and never merged into instruction context; tool calls validated independently of retrieved content; allowlisted operations only (§15.4).

**An external model vendor.** Goal (or just default behavior): retain, log, or train on data sent to it. Mitigation: default-deny egress; per-object `send_to_external_model` flag; vendor policy documented per §15.3 before any object at a given sensitivity is ever sent; ADR-002 governs which vendors qualify for which sensitivity levels, and until that ADR is accepted, this delivery sends nothing to any external model — the vertical slice uses a mocked gateway.

**The owner's own infrastructure failing.** Device loss, drive failure, forgotten passphrase, or the owner's own incapacity. This is a real threat to the "durable property" claim, arguably the most likely one to actually occur, and it's the one the original blueprint's Phase 0 questions raised but didn't resolve. Addressed in ADR-001, not yet implemented.

**A curator or the owner themselves, misclassifying an object.** Goal: none, this is an error mode not an adversary, but it's the most probable actual privacy failure — a private-raw source accidentally shipped as `public_source`. Mitigation: default-deny on ingestion, explicit profile assignment required, `training_approved` never inferred, permission overrides require a recorded reason/curator/timestamp so misclassification is auditable and reversible via revocation (§13a) rather than silent.

**Someone using the system to extract a cultural or clinical claim as though it were authoritative without corpus support.** This is treated as an epistemic threat, not just a security one — see `epistemic-contract.md`.

## 3. Trust zones (restated from blueprint §3.2)

Zone A (owner-only vault) → Zone B (private processing) → Zone C (controlled model egress) → Zone D (public product). Data becomes progressively less sensitive and more filtered moving left to right; nothing moves right without an explicit permission check at the boundary it's crossing.

## 4. What's explicitly out of scope for this delivery

No real private source is ingested. No external model is called. No public interface exists. No production key-management is implemented (ADR-001 is a proposal). No production database — the vertical slice uses an in-memory store. Scaling threats (thousands of concurrent users probing a public deployment) are not addressed here; they belong to Phase 6 onward, once there is a public interface to threaten.

## 5. Phase 0 exit criterion, restated

"No ambiguity about who owns the corpus or which systems may access it." This delivery satisfies the ownership half (stated explicitly in the blueprint's core rule and §2.1) but not the access half in full — §22 lists ten decisions still open, most of them access-boundary questions (which vendors, what deployment topology, what licensing). This threat model can name the adversaries and mitigations in the abstract; it cannot close those ten decisions, because they're the owner's calls to make, not inferences this delivery is authorized to make on the owner's behalf (blueprint §22, closing line).
