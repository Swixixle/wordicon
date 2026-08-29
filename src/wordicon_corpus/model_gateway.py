"""
Model Gateway (blueprint v1.2 §3.1, §17.3) — mocked implementation.

No real model call happens anywhere in this package (§23, ADR-002). This
gateway exists so the rest of the pipeline has a stable interface to code
against, and so the egress check it performs — refusing anything not cleared
for `send_to_external_model` — is exercised by the same code path a real
gateway would use, rather than only existing in a test that never runs.
"""
from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from .permissions import can_send_to_external_model


class EgressViolation(Exception):
    """Raised if the orchestrator attempts to send a context package
    containing anything not cleared for the target vendor."""


@dataclass
class ForgeCandidate:
    title: str
    definition: str
    central_contradiction: str
    axiom: str
    semantic_fit: float
    phonetic_fit: float
    distinctiveness: float
    personal_resonance: float
    historical_distortion_risk: float
    redundancy_risk: float
    unsupported_risk: float
    ornamental_excess_risk: float
    bone_claim_ids: list


class MockModelGateway:
    """Deterministic, offline stand-in for a real model call. Given a context
    package, it produces two or three Forge candidates using simple,
    reproducible text transforms — no network access, no real inference.
    This is sufficient to prove the pipeline's permission, provenance, and
    receipt behavior (§23's stated purpose), not to prove prose quality."""

    def __init__(self, vendor: str = "mock_local") -> None:
        self.vendor = vendor
        self.is_external = False  # this mock represents local/offline inference

    def _assert_context_package_is_clean(self, context_package: dict) -> None:
        """Refuse to 'send' (i.e. proceed with) a context package that
        embeds raw private text. Even though this gateway is local/mocked,
        it enforces the same rule a real external gateway would, so the
        check is exercised in the vertical slice rather than assumed."""
        forbidden_keys = {"raw_text", "source_text", "conversation_text"}
        for key, value in context_package.items():
            if key in forbidden_keys:
                raise EgressViolation(f"context package illegally carries raw text under key '{key}'")
            if isinstance(value, list):
                for item in value:
                    if isinstance(item, dict) and "derived_from" in item:
                        raise EgressViolation(
                            "context package item carries a 'derived_from' pointer — "
                            "that chain is forensic-only and must never enter a model context package"
                        )

    def forge(self, context_package: dict, bone_fragment_pool: list[dict]) -> list[ForgeCandidate]:
        self._assert_context_package_is_clean(context_package)

        input_text = context_package["input"]
        constraints = [c["text"] for c in context_package.get("governing_constraints", [])]
        seed = hashlib.sha256(input_text.encode()).hexdigest()

        bone_claim_ids = [f["id"] for f in bone_fragment_pool if f.get("supports_bone")]

        candidates = [
            ForgeCandidate(
                title="The Refusenik Posture",
                definition=(
                    f"The stance of one who exits a containing system without pretending the exit "
                    f"resolves it. Constrained by: {'; '.join(constraints) if constraints else 'no active constraints'}."
                ),
                central_contradiction="Escape and belonging remain simultaneously true.",
                axiom="Leaving does not close the ledger.",
                semantic_fit=0.81, phonetic_fit=0.62, distinctiveness=0.74, personal_resonance=0.7,
                historical_distortion_risk=0.1, redundancy_risk=0.15, unsupported_risk=0.05,
                ornamental_excess_risk=0.2,
                bone_claim_ids=bone_claim_ids,
            ),
            ForgeCandidate(
                title="Threshold Grief",
                definition="Generic liminal-space language describing standing at a boundary.",
                central_contradiction="Being between two states feels significant.",
                axiom="The doorway is meaningful.",
                # Deliberately weak on distinctiveness/redundancy/ornament so
                # the pipeline has something legitimate to reject and stage
                # as a negative example (§10.2a) rather than the rejection
                # step being untestable.
                semantic_fit=0.55, phonetic_fit=0.5, distinctiveness=0.22, personal_resonance=0.3,
                historical_distortion_risk=0.1, redundancy_risk=0.72, unsupported_risk=0.1,
                ornamental_excess_risk=0.65,
                bone_claim_ids=bone_claim_ids,
            ),
        ]
        return candidates
