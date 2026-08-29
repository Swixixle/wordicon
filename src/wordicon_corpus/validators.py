"""
Deterministic validators (blueprint v1.2 §2.3, §12.3, epistemic-contract.md).
These are the checks that make the evidentiary standard non-adjustable —
nothing here takes a "how strict" parameter.
"""
from __future__ import annotations


class ValidationFailure(Exception):
    pass


def validate_bone_claim(claim: dict, admitted_fragment_ids: set[str]) -> None:
    """A Bone claim with no supporting fragments admitted to the corpus is
    not Bone (epistemic-contract.md §1). Raises on failure; callers are
    expected to demote the claim to Flesh or drop it, not weaken this check."""
    fragments = claim.get("supporting_fragments") or []
    if not fragments:
        raise ValidationFailure(f"claim {claim.get('id')} has no supporting fragments — cannot be Bone")
    unadmitted = [f for f in fragments if f not in admitted_fragment_ids]
    if unadmitted:
        raise ValidationFailure(
            f"claim {claim.get('id')} cites fragment(s) not admitted to the corpus: {unadmitted}"
        )
    if not (0.0 <= claim.get("confidence", -1) <= 1.0):
        raise ValidationFailure(f"claim {claim.get('id')} has an invalid confidence score")


def validate_no_private_leak(public_receipt: dict, private_object_ids: set[str]) -> None:
    """Walks the public receipt looking for any private source id, fragment
    id, or derived-constraint id. This is the automated half of the
    'public receipt cannot expose a private source' acceptance test —
    it does not trust the redaction code to have gotten it right, it
    re-checks the output."""
    import json
    serialized = json.dumps(public_receipt)
    leaked = [oid for oid in private_object_ids if oid in serialized]
    if leaked:
        raise ValidationFailure(f"public receipt leaks private object id(s): {leaked}")


def validate_receipt_invariants(receipt: dict) -> None:
    """blueprint §12.3: every claim maps to supporting fragments; every
    source has an egress decision; revocation_annotations is append-only
    (checked at the call site by comparing lengths, not here)."""
    for claim in receipt.get("claims", []):
        if not claim.get("supporting_fragments"):
            raise ValidationFailure(f"receipt {receipt.get('receipt_id')} has a claim with no supporting fragments")
    for src in receipt.get("sources", []):
        if "egress" not in src:
            raise ValidationFailure(f"receipt {receipt.get('receipt_id')} has a source with no egress decision")
