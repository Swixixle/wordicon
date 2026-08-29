"""
Generalized dependency and invalidation model (blueprint v1.2 §13a).

One typed graph, one revocation procedure — not special-case revocation code
per object type. This is the structural fix for the gap identified in the
v1.1 review: revocation previously reached Concepts but not Personality
Kernel versions or chamber summaries.
"""
from __future__ import annotations

from collections import defaultdict, deque
from dataclasses import dataclass, field
from typing import Literal

Materiality = Literal["essential", "supporting", "historical"]


@dataclass
class Edge:
    from_id: str
    to_id: str  # to_id depends on from_id
    relationship: str
    materiality: Materiality
    created_at: str
    created_by: str = "system"
    visibility: str = "private"


@dataclass
class RevocationResult:
    revoked_object_id: str
    invalidated: list = field(default_factory=list)
    degraded: list = field(default_factory=list)
    review_required: list = field(default_factory=list)
    chamber_summaries_queued_for_regeneration: list = field(default_factory=list)


class DependencyGraph:
    """A dependent (`to_id`) depends on its source (`from_id`). Revoking a
    `from_id` walks every transitive dependent and classifies the impact."""

    def __init__(self) -> None:
        self._edges: list[Edge] = []
        # from_id -> list of edges where this object is the dependency
        self._dependents_index: dict[str, list[Edge]] = defaultdict(list)

    def add_edge(self, edge: Edge) -> None:
        self._edges.append(edge)
        self._dependents_index[edge.from_id].append(edge)

    def direct_dependents(self, object_id: str) -> list[Edge]:
        return list(self._dependents_index.get(object_id, []))

    def transitive_dependents(self, object_id: str) -> list[Edge]:
        """BFS outward from object_id, following the direction 'depends on
        me'. Returns every edge encountered, in discovery order."""
        seen_nodes = {object_id}
        out: list[Edge] = []
        queue = deque([object_id])
        while queue:
            current = queue.popleft()
            for edge in self._dependents_index.get(current, []):
                out.append(edge)
                if edge.to_id not in seen_nodes:
                    seen_nodes.add(edge.to_id)
                    queue.append(edge.to_id)
        return out

    def revoke(self, object_id: str, object_kind_lookup=None) -> RevocationResult:
        """Implements blueprint §13a.3 steps 2-6 (steps 1, 7, 8 — marking the
        object itself unavailable, annotating receipts, and writing the
        RevocationEvent — are the caller's job; see corpus_service.revoke).

        object_kind_lookup: optional callable(object_id) -> "personality_kernel"
        | "chamber_summary" | other, used to decide whether an invalidated
        dependent is regenerable (chamber summaries) or requires human review
        (kernels always do, regardless of materiality, per §13a.4).
        """
        result = RevocationResult(revoked_object_id=object_id)
        for edge in self.transitive_dependents(object_id):
            dependent = edge.to_id
            kind = object_kind_lookup(dependent) if object_kind_lookup else None

            if edge.materiality == "essential":
                result.invalidated.append(dependent)
                if kind == "chamber_summary":
                    result.chamber_summaries_queued_for_regeneration.append(dependent)
                elif kind == "personality_kernel":
                    # Kernels are immutable; invalidation always requires a
                    # human-reviewed new version, never silent regeneration.
                    result.review_required.append(dependent)
            elif edge.materiality == "supporting":
                result.degraded.append(dependent)
                result.review_required.append(dependent)
            else:  # historical
                # Retained for lineage; no action needed, but still surfaced
                # so nothing is silently dropped from the audit trail.
                pass

        # dedupe while preserving order
        result.invalidated = list(dict.fromkeys(result.invalidated))
        result.degraded = list(dict.fromkeys(result.degraded))
        result.review_required = list(dict.fromkeys(result.review_required))
        result.chamber_summaries_queued_for_regeneration = list(
            dict.fromkeys(result.chamber_summaries_queued_for_regeneration)
        )
        return result
