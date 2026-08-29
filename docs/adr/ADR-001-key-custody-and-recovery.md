# ADR-001: Encryption, Key Custody, Recovery, and Catastrophic Key Loss

**Status:** Proposed. Not implemented. No key infrastructure described here is built by this delivery — this ADR exists so the owner can decide before any real private material is encrypted under a scheme that might later prove unrecoverable.

## Context

Blueprint v1.2 §15.1 requires originals, parsed text, indexes, backups, and receipts to be encrypted at rest, with encryption keys kept separate from application data and owner-controlled key rotation. It does not specify what happens when the owner loses access to the key material itself. This is not a hypothetical — it's the single most likely actual failure mode for a system whose entire premise is that the corpus outlives any model vendor, application, or company. A corpus that survives every vendor but not a lost laptop or a forgotten passphrase hasn't achieved sovereignty; it's achieved a more elaborate way to lose the same data.

## The tradeoff

Absolute single-owner control, with no redundant recovery path, means no AI vendor, application host, or model provider can ever reconstruct the key — which is the strongest possible confidentiality guarantee. It also means device loss, drive failure, fire, theft, a forgotten passphrase, or the owner's own incapacity permanently destroys the corpus, with no remediation. Strengthening confidentiality here directly weakens durability, and durability is the other half of what this system claims to provide (blueprint §2.2, §24 — "the durable property is... model-independent").

## Options considered

### Option 1 — Strict single-owner recovery

One key (or one key held only by the owner, with no split), no third party, no threshold scheme. Simplest to implement and reason about. Maximum confidentiality. Zero resilience to owner-side loss: one bad drive failure, one forgotten passphrase, or one incapacitating event and the corpus is unrecoverable. Rejected as the default because it fails the durability half of the system's own stated purpose, but may be the right choice for a subset of the most sensitive `sealed` or `private raw` objects even under Option 2 below.

### Option 2 — Owner-controlled threshold recovery across locations (recommended, provisionally)

- Corpus data encrypted with randomly generated data-encryption keys (DEKs), one or more per object or object class.
- DEKs wrapped by a separate key-encryption key (KEK).
- Normal day-to-day operation unlocks the KEK through an owner-controlled hardware-backed credential (e.g. a hardware security key or platform secure enclave) or a secure local key store — no threshold scheme needed for routine use.
- A separate offline recovery key is split using a threshold scheme (e.g. Shamir's Secret Sharing), such as 2-of-3 or 3-of-5 shares.
- All shares remain under the owner's control, but stored in physically separate secure locations (e.g. a home safe, a bank deposit box, a trusted-but-uninvolved location) — no single location's loss or compromise is fatal.
- No AI vendor, application host, or model provider ever possesses enough material, alone, to reconstruct the key.
- Encrypted backups follow a 3-2-1 strategy (3 copies, 2 media types, 1 offsite).
- Recovery is tested on a schedule (e.g. annually) against a nonproduction copy of the corpus, so "recovery works" is a verified fact, not an assumption.
- Loss of any single device, single backup copy, or single recovery share does not destroy the corpus — only loss of a quorum of shares plus all working credentials does.
- A documented succession or incapacity option exists (e.g. a sealed instruction for a designated person to combine recovery shares under specific conditions) but stays **disabled** — no share pre-distributed to that person — unless the owner explicitly activates it.

This is the option that treats "sole authority" and "not a single point of failure" as compatible rather than in tension, at the cost of real operational overhead (physically distributing and periodically testing shares).

### Option 3 — Optional trusted-person or legal-estate recovery

Extends Option 2 by pre-authorizing a specific trusted person or legal mechanism (power of attorney, estate executor) to hold or trigger recovery under defined conditions, without the owner manually activating it at the time of loss. Strongest resilience to owner incapacity specifically. Weakest confidentiality of the three options, since it means a real recovery path exists that doesn't require the owner's contemporaneous action — which is exactly the property Option 1 was designed to avoid. Appropriate only if incapacity (not just device loss) is a scenario the owner specifically wants covered, and only for whichever sensitivity tiers the owner is willing to extend that exposure to.

## Recommendation

Option 2, provisionally, as the default for `private_raw` and `derived_only` material generally, with the explicit note that this is a recommendation pending the owner's own risk tolerance, not a decision this document is authorized to make. Option 3's succession mechanism can be layered on top of Option 2 later, selectively, without re-architecting anything — it only requires deciding whether and when to pre-distribute an additional share.

## What this ADR does not decide

Which specific hardware/software implements the KEK unlock step; which threshold scheme library; how many total shares vs. threshold; where physically the shares are stored; whether Option 3's succession mechanism is activated at all. These are downstream of the owner picking an option here.

## Consequences if left unresolved

Per blueprint §15.1, no real private material should be encrypted under a scheme without this decision made first — encrypting now under an ad hoc scheme and deciding key custody later risks having to re-encrypt everything (or worse, having already created the single point of failure this ADR exists to avoid) once the real decision is made.
