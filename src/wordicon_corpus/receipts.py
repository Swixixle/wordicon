"""
Receipt construction (blueprint v1.2 §12). The private receipt is built
first, from the full execution trace; the public receipt is derived from it
by redaction — never independently reconstructed (§12.3 invariant).
"""
from __future__ import annotations

import copy
import hashlib
from datetime import datetime, timezone


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def sha256_of(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode()).hexdigest()


def build_private_receipt(
    *, receipt_id: str, trace_id: str, operation: str, input_text: str,
    kernel_version: int, engine_version: str, sources: list[dict],
    derived_constraints_applied: list[dict], claims: list[dict],
    candidates: list[dict], rejections: list[dict], warnings: list[str],
    model_calls: list[dict], prompt_identities: list[dict] | None = None,
    composite: dict | None = None,
) -> dict:
    # block 104: prompt identities (stage, template hash, renderer, model,
    # settings — never the assembled prompt) and, for a deep or decompose
    # run, the composite block naming its component runs. Both are
    # written only when the caller supplies them, so every older receipt
    # shape is unchanged.
    tail = {}
    if prompt_identities is not None:
        tail["prompt_identities"] = list(prompt_identities)
    if composite is not None:
        tail["composite"] = dict(composite)
    return {
        "receipt_id": receipt_id,
        "trace_id": trace_id,
        "created_at": _now(),
        "operation": operation,
        "input_hash": sha256_of(input_text),
        "kernel_version": kernel_version,
        "engine_version": engine_version,
        "sources": sources,
        "derived_constraints_applied": derived_constraints_applied,
        "claims": claims,
        "transformations": [],
        "candidates": candidates,
        "rejections": rejections,
        "warnings": warnings,
        "model_calls": model_calls,
        "revocation_annotations": [],
        "redaction_policy": "public_v1",
        **tail,
    }


def build_public_receipt(private_receipt: dict) -> dict:
    """Applies config/receipt-redaction-policies.yaml's public_v1 policy.
    Exclusion, not obfuscation: a field either survives whole or is dropped.
    """
    public = {
        "receipt_id": private_receipt["receipt_id"],
        "trace_id": private_receipt["trace_id"],
        "created_at": private_receipt["created_at"],
        "operation": private_receipt["operation"],
        "kernel_version": private_receipt["kernel_version"],
        "redaction_policy": private_receipt["redaction_policy"],
        "warnings": list(private_receipt.get("warnings", [])),
    }

    # Sources: included ONLY if public/internal sensitivity AND explicitly
    # cleared to be quoted publicly.
    public_sources = [
        {k: v for k, v in s.items() if k in ("source_id", "use", "visibility", "egress")}
        for s in private_receipt.get("sources", [])
        if s.get("visibility") == "public" and s.get("public_quote_cleared") is True
    ]
    if public_sources:
        public["sources"] = public_sources

    # Claims: factual claims travel with type + confidence, but never with
    # any pointer into a private fragment.
    public_claims = []
    for c in private_receipt.get("claims", []):
        public_claims.append({
            "claim_id": c["claim_id"],
            "text": c["text"],
            "type": c["type"],
            "confidence": c["confidence"],
        })
    public["claims"] = public_claims

    # Derived constraints: never enumerated, never named. A single
    # summarized statement of contribution, or nothing at all.
    if private_receipt.get("derived_constraints_applied"):
        public["interpretive_contribution"] = (
            "Derived using the proprietary Wordicon Sovereign Corpus. "
            "Underlying private materials are not disclosed."
        )

    # Revocation annotations are public-safe by construction (they never
    # contain private ids in this implementation's note text beyond what's
    # already been redacted) but we still strip anything that isn't the
    # bare fact of an annotation having occurred, to avoid depending on
    # annotation authors having been careful.
    if private_receipt.get("revocation_annotations"):
        public["revocation_notice"] = (
            f"{len(private_receipt['revocation_annotations'])} revocation event(s) "
            "have been recorded against material underlying this result. "
            "See the private receipt for details."
        )

    return public


def append_revocation_annotation(receipt: dict, *, revocation_event_id: str, note: str) -> dict:
    """Append-only: never mutates existing fields, only adds to the
    revocation_annotations list. Returns the same dict object for
    convenience; callers should not replace the receipt wholesale."""
    receipt.setdefault("revocation_annotations", []).append({
        "revocation_event_id": revocation_event_id,
        "annotated_at": _now(),
        "note": note,
    })
    return receipt
