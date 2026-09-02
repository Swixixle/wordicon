"""
Corpus object types (blueprint v1.2 §4.1) as plain dataclasses.

These are deliberately thin: the JSON Schemas under schemas/ are the
normative definition of shape and are validated against at ingestion time
(see corpus_service.CorpusService.ingest). The dataclasses here exist so
application code gets attribute access and type checking rather than raw
dicts everywhere.
"""
from __future__ import annotations

from dataclasses import dataclass, field, asdict
from typing import Any, Optional


def _asdict_clean(obj: Any) -> dict:
    """asdict() but drop None values so serialized objects validate cleanly
    against schemas that don't expect null for optional fields."""
    d = asdict(obj)
    return {k: v for k, v in d.items() if v is not None}


@dataclass
class DependencyRef:
    object_id: str
    materiality: str  # essential | supporting | historical
    relationship: str = "derived_from"

    def to_dict(self) -> dict:
        return {"object_id": self.object_id, "relationship": self.relationship, "materiality": self.materiality}


@dataclass
class PermissionOverride:
    flag: str
    prior_value: Any
    new_value: Any
    reason: str
    curator: str
    timestamp: str

    def to_dict(self) -> dict:
        return asdict(self)


@dataclass
class Source:
    id: str
    title: str
    created_at: str
    origin: str
    author: str
    epistemic_class: str
    sensitivity: str
    permissions_profile: str
    permissions: dict
    object_type: str = "source"
    external_participants: list = field(default_factory=list)
    original_file_hash: Optional[str] = None
    permission_overrides: list = field(default_factory=list)
    rights_record: Optional[str] = None
    tags: list = field(default_factory=list)
    review_status: str = "unreviewed"
    revoked: bool = False
    version: int = 1

    def to_schema_dict(self) -> dict:
        return {
            "id": self.id,
            "object_type": self.object_type,
            "title": self.title,
            "created_at": self.created_at,
            "provenance": {
                "origin": self.origin,
                "author": self.author,
                "external_participants": self.external_participants,
                **({"original_file_hash": self.original_file_hash} if self.original_file_hash else {}),
            },
            "epistemic_class": self.epistemic_class,
            "sensitivity": self.sensitivity,
            "permissions_profile": self.permissions_profile,
            "permissions": self.permissions,
            "permission_overrides": [o.to_dict() if isinstance(o, PermissionOverride) else o for o in self.permission_overrides],
            **({"rights_record": self.rights_record} if self.rights_record else {}),
            "tags": self.tags,
            "review_status": self.review_status,
            "revoked": self.revoked,
            "version": self.version,
        }


@dataclass
class Fragment:
    id: str
    source_id: str
    locator: str
    sensitivity: str
    object_type: str = "fragment"
    text_hash: Optional[str] = None
    text: Optional[str] = None
    themes: list = field(default_factory=list)
    version: int = 1

    def to_schema_dict(self) -> dict:
        d = {
            "id": self.id, "object_type": self.object_type, "source_id": self.source_id,
            "locator": self.locator, "sensitivity": self.sensitivity, "themes": self.themes,
            "version": self.version,
        }
        if self.text_hash:
            d["text_hash"] = self.text_hash
        if self.text is not None:
            d["text"] = self.text
        return d


@dataclass
class Claim:
    id: str
    text: str
    claim_type: str
    supporting_fragments: list
    confidence: float
    object_type: str = "claim"
    confidence_components: list = field(default_factory=list)
    material_disagreement: Optional[str] = None

    def to_schema_dict(self) -> dict:
        d = {
            "id": self.id, "object_type": self.object_type, "text": self.text,
            "claim_type": self.claim_type, "supporting_fragments": self.supporting_fragments,
            "confidence": self.confidence,
        }
        if self.confidence_components:
            d["confidence_components"] = self.confidence_components
        if self.material_disagreement:
            d["material_disagreement"] = self.material_disagreement
        return d


@dataclass
class DerivedConstraint:
    id: str
    text: str
    derived_from: list  # list[DependencyRef]
    derivation_method: str
    review_status: str
    sensitivity: str
    permissions_profile: str
    valid_from: str
    object_type: str = "derived_constraint"
    valid_until: Optional[str] = None
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None
    kernel_membership: list = field(default_factory=list)
    chamber_summary_membership: list = field(default_factory=list)
    reused_in_operations: list = field(default_factory=list)
    version: int = 1

    def to_schema_dict(self) -> dict:
        return {
            "id": self.id,
            "object_type": self.object_type,
            "text": self.text,
            "derived_from": [r.to_dict() if isinstance(r, DependencyRef) else r for r in self.derived_from],
            "derivation_method": self.derivation_method,
            "review_status": self.review_status,
            "sensitivity": self.sensitivity,
            "permissions_profile": self.permissions_profile,
            "valid_from": self.valid_from,
            "valid_until": self.valid_until,
            "supersedes": self.supersedes,
            "superseded_by": self.superseded_by,
            "kernel_membership": self.kernel_membership,
            "chamber_summary_membership": self.chamber_summary_membership,
            "reused_in_operations": self.reused_in_operations,
            "version": self.version,
        }


@dataclass
class PersonalityKernel:
    id: str
    kernel_version: int
    status: str
    principles: list
    member_constraints: list
    object_type: str = "personality_kernel"
    style: dict = field(default_factory=dict)
    required_checks: list = field(default_factory=list)
    supersedes: Optional[str] = None
    superseded_by: Optional[str] = None

    def to_schema_dict(self) -> dict:
        return {
            "id": self.id, "object_type": self.object_type, "kernel_version": self.kernel_version,
            "status": self.status, "principles": self.principles, "style": self.style,
            "required_checks": self.required_checks, "member_constraints": self.member_constraints,
            "immutable": True, "supersedes": self.supersedes, "superseded_by": self.superseded_by,
        }


@dataclass
class Judgment:
    id: str
    decision: str
    candidate_text: str
    originating_operation: str
    decision_source: str
    confidence: float
    review_status: str = "unreviewed"
    object_type: str = "judgment"
    concept_id: Optional[str] = None
    reason: Optional[str] = None
    failure_axis: Optional[str] = None
    scope: str = "local_to_concept"
    # Block 103 (backlog item 47): the clock a ruling was made at, the
    # owner-declared epoch it fell in, where it was made (a run's cards,
    # the Recovery Review), and what it cites (an older judgment, a
    # receipt). Rows written before this carry none of these and are
    # never rewritten to invent them — their missing clocks are a finding.
    ruled_at: Optional[str] = None
    epoch: Optional[str] = None
    origin: Optional[str] = None
    cites: Optional[dict] = None

    def to_schema_dict(self) -> dict:
        d = {
            "id": self.id, "object_type": self.object_type, "decision": self.decision,
            "candidate_text": self.candidate_text, "originating_operation": self.originating_operation,
            "decision_source": self.decision_source, "confidence": self.confidence,
            "review_status": self.review_status, "scope": self.scope,
        }
        if self.concept_id:
            d["concept_id"] = self.concept_id
        if self.reason:
            d["reason"] = self.reason
        if self.failure_axis:
            d["failure_axis"] = self.failure_axis
        if self.ruled_at:
            d["ruled_at"] = self.ruled_at
        if self.epoch:
            d["epoch"] = self.epoch
        if self.origin:
            d["origin"] = self.origin
        if self.cites:
            d["cites"] = dict(self.cites)
        return d


@dataclass
class ChamberSummary:
    id: str
    chamber: str
    summary_text: str
    built_from: list  # list[DependencyRef]
    review_status: str = "approved"
    object_type: str = "chamber_summary"
    regenerable: bool = True
    version: int = 1

    def to_schema_dict(self) -> dict:
        return {
            "id": self.id, "object_type": self.object_type, "chamber": self.chamber,
            "summary_text": self.summary_text,
            "built_from": [r.to_dict() if isinstance(r, DependencyRef) else r for r in self.built_from],
            "review_status": self.review_status, "regenerable": self.regenerable, "version": self.version,
        }
