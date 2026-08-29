"""
Sovereign Corpus Service (blueprint v1.2 §3.1) — in-memory reference
implementation. Stands in for the PostgreSQL-backed service described in
§17.2; the interface (ingest / admit / revoke / get / search) is the part
meant to survive a swap to a real database.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Optional

from . import schema_loader
from .dependency_graph import DependencyGraph, Edge
from .objects import (
    ChamberSummary, Claim, DerivedConstraint, DependencyRef, Fragment,
    Judgment, PersonalityKernel, Source,
)

SOURCE_FORBIDDEN_PROFILES = {"constraint_text_external_approved"}
"""Profiles that exist only to govern a Derived Constraint's resolved text
and must never be assignable to a Source. If a Source ever carried this
profile, its raw text would inherit an egress allowance meant only for a
reviewed abstraction — collapsing the exact boundary derived_only exists to
enforce. Checked at ingestion, not just documented (config/
permission-profiles.yaml)."""

SCHEMA_FILE_BY_TYPE = {
    "source": "source.schema.json",
    "fragment": "fragment.schema.json",
    "claim": "claim.schema.json",
    "concept": "concept.schema.json",
    "mechanism": "mechanism.schema.json",
    "judgment": "judgment.schema.json",
    "derived_constraint": "derived-constraint.schema.json",
    "personality_kernel": "personality-kernel.schema.json",
    "chamber_summary": "chamber-summary.schema.json",
    "revocation_event": "revocation-event.schema.json",
}


class CorpusError(Exception):
    pass


@dataclass
class RevocationEventRecord:
    id: str
    revoked_object_id: str
    revoked_at: str
    revoked_by: str
    reason: str
    dependents_invalidated: list = field(default_factory=list)
    dependents_degraded: list = field(default_factory=list)
    dependents_queued_for_review: list = field(default_factory=list)
    chamber_summaries_queued_for_regeneration: list = field(default_factory=list)
    receipts_annotated: list = field(default_factory=list)
    object_type: str = "revocation_event"

    def to_schema_dict(self) -> dict:
        return {
            "id": self.id, "object_type": self.object_type,
            "revoked_object_id": self.revoked_object_id, "revoked_at": self.revoked_at,
            "revoked_by": self.revoked_by, "reason": self.reason,
            "dependents_invalidated": self.dependents_invalidated,
            "dependents_degraded": self.dependents_degraded,
            "dependents_queued_for_review": self.dependents_queued_for_review,
            "chamber_summaries_queued_for_regeneration": self.chamber_summaries_queued_for_regeneration,
            "receipts_annotated": self.receipts_annotated,
        }


def _now() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


class CorpusService:
    def __init__(self) -> None:
        self.objects: dict[str, Any] = {}
        self.graph = DependencyGraph()
        self.receipts: dict[str, dict] = {}
        self._revocation_counter = 0

    # ---- ingestion -----------------------------------------------------

    def ingest(self, obj) -> Any:
        """Validate against the object's JSON Schema, then admit to the
        in-memory store. Raises CorpusError on schema violation — nothing
        enters the store without passing its schema, matching §7.1 step 9
        ('index') being downstream of a valid object existing."""
        schema_dict = obj.to_schema_dict()
        object_type = schema_dict["object_type"]

        if object_type == "source" and schema_dict.get("permissions_profile") in SOURCE_FORBIDDEN_PROFILES:
            raise CorpusError(
                f"source {schema_dict.get('id')} was assigned {schema_dict['permissions_profile']!r}, "
                f"a profile reserved for Derived Constraint objects — a Source may never carry it, "
                f"since doing so would let raw text inherit an egress allowance meant only for a "
                f"reviewed abstraction"
            )

        schema_file = SCHEMA_FILE_BY_TYPE.get(object_type)
        if schema_file:
            try:
                schema_loader.validate(schema_file, schema_dict)
            except Exception as e:  # jsonschema.ValidationError
                raise CorpusError(f"{object_type} {schema_dict.get('id')} failed schema validation: {e}") from e
        self.objects[obj.id] = obj
        return obj

    def get(self, object_id: str):
        return self.objects.get(object_id)

    # ---- dependency graph ------------------------------------------------

    def link(self, from_id: str, to_id: str, relationship: str, materiality: str, visibility: str = "private") -> None:
        self.graph.add_edge(Edge(
            from_id=from_id, to_id=to_id, relationship=relationship,
            materiality=materiality, created_at=_now(), visibility=visibility,
        ))

    def _object_kind(self, object_id: str) -> Optional[str]:
        obj = self.objects.get(object_id)
        return getattr(obj, "object_type", None)

    # ---- revocation -----------------------------------------------------

    def revoke(self, object_id: str, revoked_by: str, reason: str) -> RevocationEventRecord:
        """Implements the full §13a.3 procedure."""
        obj = self.objects.get(object_id)
        if obj is None:
            raise CorpusError(f"cannot revoke unknown object {object_id}")

        # Step 1: mark unavailable for future retrieval.
        if hasattr(obj, "revoked"):
            obj.revoked = True

        # Steps 2-6: walk the dependency graph and classify impact.
        result = self.graph.revoke(object_id, object_kind_lookup=self._object_kind)

        for dep_id in result.invalidated:
            dep = self.objects.get(dep_id)
            if dep is None:
                continue
            if getattr(dep, "object_type", None) == "personality_kernel":
                dep.status = "invalid"
            elif getattr(dep, "object_type", None) == "derived_constraint":
                dep.review_status = "invalid"
            elif hasattr(dep, "review_status"):
                dep.review_status = "invalid"

        for dep_id in result.degraded:
            dep = self.objects.get(dep_id)
            if dep is not None and hasattr(dep, "review_status"):
                dep.review_status = "degraded"

        for dep_id in result.review_required:
            dep = self.objects.get(dep_id)
            if dep is not None and getattr(dep, "object_type", None) == "personality_kernel":
                if dep.status != "invalid":
                    dep.status = "review_required"

        # Step 7: annotate (never mutate) receipts that used the revoked
        # object or any of its now-invalidated dependents.
        self._revocation_counter += 1
        event_id = f"rev_{self._revocation_counter:06d}"
        touched = {object_id, *result.invalidated, *result.degraded}
        annotated_receipts = []
        for receipt_id, receipt in self.receipts.items():
            cited = {s["source_id"] for s in receipt.get("sources", [])}
            cited |= {c["constraint_id"] for c in receipt.get("derived_constraints_applied", [])}
            if cited & touched:
                receipt.setdefault("revocation_annotations", []).append({
                    "revocation_event_id": event_id,
                    "annotated_at": _now(),
                    "note": (
                        f"Object {object_id} was revoked on {_now()} ({reason}). "
                        f"This receipt cited it or a dependent invalidated by that revocation. "
                        f"The receipt's original content is unchanged; this is an appended annotation."
                    ),
                })
                annotated_receipts.append(receipt_id)

        # Step 8: create the RevocationEvent.
        event = RevocationEventRecord(
            id=event_id, revoked_object_id=object_id, revoked_at=_now(),
            revoked_by=revoked_by, reason=reason,
            dependents_invalidated=result.invalidated, dependents_degraded=result.degraded,
            dependents_queued_for_review=result.review_required,
            chamber_summaries_queued_for_regeneration=result.chamber_summaries_queued_for_regeneration,
            receipts_annotated=annotated_receipts,
        )
        schema_loader.validate("revocation-event.schema.json", event.to_schema_dict())
        self.objects[event.id] = event
        return event

    # ---- receipts ---------------------------------------------------------

    def store_receipt(self, receipt: dict) -> None:
        self.receipts[receipt["receipt_id"]] = receipt
