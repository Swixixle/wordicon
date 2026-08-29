"""
Forge operation pipeline (blueprint v1.2 §10.2, §10.2a).

This mocked slice implements: retrieve governing constraints (resolved text
only, never their source), build a context package, call the model gateway,
score candidates against the §13 objective, reject weak candidates (staging
them as unreviewed negative examples per §10.2a), validate every Bone claim
against admitted public fragments, and build both receipts.
"""
from __future__ import annotations

import hashlib

from . import receipts as receipts_mod
from . import schema_loader
from . import validators
from .corpus_service import CorpusService
from .model_gateway import ForgeCandidate, MockModelGateway
from .objects import Judgment

REJECTION_THRESHOLDS = {
    "redundancy_risk": 0.6,
    "ornamental_excess_risk": 0.6,
    "distinctiveness_min": 0.3,
}

SCORE_WEIGHTS = dict(alpha=1.0, beta=0.5, gamma=1.0, delta=0.8, lam=1.2, mu=1.0, nu=1.5, xi=0.8)


def _score(candidate: ForgeCandidate) -> float:
    w = SCORE_WEIGHTS
    return (
        w["alpha"] * candidate.semantic_fit
        + w["beta"] * candidate.phonetic_fit
        + w["gamma"] * candidate.distinctiveness
        + w["delta"] * candidate.personal_resonance
        - w["lam"] * candidate.historical_distortion_risk
        - w["mu"] * candidate.redundancy_risk
        - w["nu"] * candidate.unsupported_risk
        - w["xi"] * candidate.ornamental_excess_risk
    )


def _fails_thresholds(candidate: ForgeCandidate) -> str | None:
    if candidate.redundancy_risk >= REJECTION_THRESHOLDS["redundancy_risk"]:
        return "redundancy"
    if candidate.ornamental_excess_risk >= REJECTION_THRESHOLDS["ornamental_excess_risk"]:
        return "style"
    if candidate.distinctiveness < REJECTION_THRESHOLDS["distinctiveness_min"]:
        return "conceptual_weakness"
    return None


def _deterministic_id(prefix: str, *parts: str) -> str:
    digest = hashlib.sha256("|".join(parts).encode()).hexdigest()[:10]
    return f"{prefix}_{digest}"


def run_forge(
    *, corpus: CorpusService, kernel_id: str, input_text: str, trace_id: str,
    public_fragment_pool: list[dict], gateway: MockModelGateway | None = None,
) -> dict:
    gateway = gateway or MockModelGateway()
    kernel = corpus.get(kernel_id)
    if kernel is None or kernel.status != "approved":
        raise RuntimeError(
            f"kernel {kernel_id} is not usable (status={getattr(kernel, 'status', None)}) — an "
            f"invalid or review-required kernel cannot serve new operations (blueprint §13a.4)"
        )

    # ---- retrieve governing constraints: resolved text only, never the
    # derived_from pointer, which stays forensic-only. ----
    governing_constraints = []
    constraint_receipt_entries = []
    for dc_id in kernel.member_constraints:
        dc = corpus.get(dc_id)
        if dc is None or dc.review_status != "approved":
            continue  # an invalidated or degraded constraint does not fire
        governing_constraints.append({"constraint_id": dc.id, "text": dc.text})
        constraint_receipt_entries.append({
            "constraint_id": dc.id, "kernel_version": kernel.kernel_version, "visibility": "private",
        })

    context_package = {
        "operation": "forge",
        "kernel_version": kernel.kernel_version,
        "input": input_text,
        "governing_constraints": governing_constraints,
        "receipt_trace_id": trace_id,
    }

    candidates = gateway.forge(context_package, public_fragment_pool)
    scored = sorted(((c, _score(c)) for c in candidates), key=lambda pair: pair[1], reverse=True)

    accepted, rejected_judgments = [], []
    for candidate, score in scored:
        failure = _fails_thresholds(candidate)
        if failure:
            judgment = Judgment(
                id=_deterministic_id("jdg", candidate.title, trace_id),
                decision="rejected", candidate_text=candidate.title,
                originating_operation=trace_id, decision_source="validator",
                confidence=0.6, review_status="unreviewed",
                reason=f"failed threshold on {failure}", failure_axis=failure,
                scope="local_to_concept",
            )
            corpus.ingest(judgment)
            rejected_judgments.append(judgment)
        else:
            accepted.append((candidate, score))

    if not accepted:
        raise RuntimeError("all candidates rejected; Forge must refuse rather than surface a weak result (§2.7)")

    winner, winner_score = accepted[0]

    admitted_fragment_ids = {f["id"] for f in public_fragment_pool}
    claims = []
    for i, fid in enumerate(winner.bone_claim_ids):
        fragment = next(f for f in public_fragment_pool if f["id"] == fid)
        claim = {
            "id": _deterministic_id("claim", trace_id, str(i)),
            "text": fragment["claim_text"], "claim_type": "historical",
            "supporting_fragments": [fid], "confidence": 0.9,
        }
        validators.validate_bone_claim(claim, admitted_fragment_ids)
        claims.append(claim)

    sources_for_receipt = [
        {
            "source_id": f["source_id"], "fragment_id": f["id"], "use": "supports_claim",
            "visibility": "public", "egress": "excerpt", "public_quote_cleared": True,
        }
        for f in public_fragment_pool
    ]

    private_receipt = receipts_mod.build_private_receipt(
        receipt_id=f"receipt_{trace_id}", trace_id=trace_id, operation="forge", input_text=input_text,
        kernel_version=kernel.kernel_version, engine_version="0.1.0",
        sources=sources_for_receipt, derived_constraints_applied=constraint_receipt_entries,
        claims=[
            {"claim_id": c["id"], "text": c["text"], "type": c["claim_type"],
             "confidence": c["confidence"], "supporting_fragments": c["supporting_fragments"]}
            for c in claims
        ],
        candidates=[{"title": c.title, "score": s} for c, s in scored],
        rejections=[{"judgment_id": j.id, "candidate": j.candidate_text, "reason": j.reason} for j in rejected_judgments],
        warnings=[], model_calls=[{"gateway": gateway.vendor, "is_external": gateway.is_external}],
    )
    validators.validate_receipt_invariants(private_receipt)
    schema_loader.validate("receipt.schema.json", private_receipt)
    corpus.store_receipt(private_receipt)

    public_receipt = receipts_mod.build_public_receipt(private_receipt)
    private_constraint_ids = {e["constraint_id"] for e in constraint_receipt_entries}
    validators.validate_no_private_leak(public_receipt, private_constraint_ids)

    bone_flesh_friction = {
        "title": winner.title,
        "bone": {"summary": "See cited claims.", "claims": [c["id"] for c in claims]},
        "flesh": {
            "definition": winner.definition, "central_contradiction": winner.central_contradiction,
            "archetypal_frame": [], "axiom": winner.axiom,
        },
        "friction": {
            "hostile_read": "Not run against a live adversarial critic in this mocked slice.",
            "cultural_risks": [], "redundancy": f"redundancy_risk={winner.redundancy_risk}",
            "verdict": "provisional",
        },
        "receipt_id": private_receipt["receipt_id"],
    }

    return {
        "trace_id": trace_id,
        "winner": winner,
        "winner_score": winner_score,
        "bone_flesh_friction": bone_flesh_friction,
        "rejected_judgments": rejected_judgments,
        "private_receipt": private_receipt,
        "public_receipt": public_receipt,
        "context_package": context_package,
    }
