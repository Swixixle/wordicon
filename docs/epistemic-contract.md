# Epistemic Contract

Governs what Wordicon is allowed to assert, on what basis, and what it must do when it doesn't have enough basis to assert something. This is extracted and made binding from blueprint v1.2 §2 and §4.3, so it can be checked independently of the rest of the architecture.

## 1. What counts as Bone

A Bone claim is a factual proposition — linguistic, historical, scientific, or cultural — that the system asserts as documented rather than interpreted. A claim qualifies as Bone only if:

1. it cites one or more admitted corpus sources (not pretrained model knowledge);
2. it declares a claim type (historical, etymological, scientific, cultural, biographical, ...);
3. it carries a confidence score computed from the claim-support function (blueprint §13, \(Q(c)\)), not an unexplained number;
4. material disagreement between sources is disclosed rather than silently resolved in favor of one side;
5. every cited source's permission policy allows the use being made of it (quoting, summarizing, or citing without quoting).

If a claim fails any of these five, it is not Bone. It becomes Flesh (explicitly speculative), is quarantined for research, or is omitted. There is no fourth option where an unsupported claim is presented as documented because it is "probably true" or because a general-purpose model is confident about it.

## 2. What a language model is and isn't for

The model may synthesize, compress, compare, and propose candidates. It is never the source of truth for a Bone claim, regardless of how confident its output looks. Concretely: if the model gateway returns a claim with no `supporting_fragments` pointing at admitted sources, the Bone validator rejects it before it reaches a receipt. See `src/wordicon_corpus/validators.py::validate_bone_claim`.

## 3. Private influence without private disclosure

A Derived Constraint may govern an output without exposing the source it was derived from. This is not a loophole in the epistemic contract — the constraint itself is still fully accountable: it has an ID, a review status, a materiality-tagged dependency chain, and a revocation lifecycle (blueprint §13a). What's withheld from the public is the *source text*, not the *fact that private material contributed and how strongly*. The forensic receipt always has the full chain; the public receipt always discloses that a proprietary derived constraint contributed, without naming or quoting it.

## 4. Refusal is a valid output

The engine must be able to conclude, and say plainly:

- an existing word already suffices (Already Named);
- the proposed concept is not distinct from one already in the corpus;
- the evidence is inadequate to support a Bone claim;
- the requested metaphor trivializes a historical trauma;
- the output would be decorative rather than structurally meaningful;
- the requested material is not licensed for the requested use.

A refusal is not a failure state to be minimized — it's evidence the evidentiary standard is actually being enforced rather than rubber-stamped.

## 5. Verification is not a dial

Creative intensity, adversarial pressure, and register are user-adjustable. The evidentiary bar for Bone is not. There is no request parameter that lowers `Q(c)`'s threshold, and no "trust me" override — including from the owner — that admits an unsupported claim as Bone. If the owner wants to assert something as fact without a supporting fragment, that assertion belongs in Flesh, labeled as interpretation, same as anyone else's unsupported claim.

## 6. Failure modes this contract exists to prevent

- A model hallucinating an etymology and it reaching Bone because it sounded plausible.
- A private conversation's judgment leaking into a public result as if it were external scholarship.
- A rejected candidate's reasoning quietly disappearing instead of being captured as a negative example.
- A claim's confidence score being a number nobody can trace back to actual source authority, relevance, and entailment.
- The owner's own private conviction being asserted as documented fact rather than personal authority (which is a real epistemic class, §4.3, but a different one from external factual authority).
