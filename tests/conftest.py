"""Shared fixtures: a corpus seeded the same way the vertical-slice script
seeds it (private source -> derived constraint -> kernel -> chamber summary),
so revocation/permission tests don't each re-implement the setup."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from wordicon_corpus.corpus_service import CorpusService
from wordicon_corpus.objects import (
    ChamberSummary, DependencyRef, DerivedConstraint, PersonalityKernel, Source,
)

FIXTURES = Path(__file__).resolve().parents[1] / "fixtures"


def _load(path):
    return json.loads((FIXTURES / path).read_text())


def load_source(d: dict) -> Source:
    return Source(
        id=d["id"], title=d["title"], created_at=d["created_at"],
        origin=d["provenance"]["origin"], author=d["provenance"]["author"],
        external_participants=d["provenance"].get("external_participants", []),
        epistemic_class=d["epistemic_class"], sensitivity=d["sensitivity"],
        permissions_profile=d["permissions_profile"], permissions=d["permissions"],
        permission_overrides=d.get("permission_overrides", []),
        tags=d.get("tags", []), review_status=d.get("review_status", "unreviewed"),
        revoked=d.get("revoked", False), version=d.get("version", 1),
    )


def load_derived_constraint(d: dict) -> DerivedConstraint:
    return DerivedConstraint(
        id=d["id"], text=d["text"],
        derived_from=[DependencyRef(**r) for r in d["derived_from"]],
        derivation_method=d["derivation_method"], review_status=d["review_status"],
        sensitivity=d["sensitivity"], permissions_profile=d["permissions_profile"],
        valid_from=d["valid_from"], valid_until=d.get("valid_until"),
        kernel_membership=d.get("kernel_membership", []), version=d.get("version", 1),
    )


def load_kernel(d: dict) -> PersonalityKernel:
    return PersonalityKernel(
        id=d["id"], kernel_version=d["kernel_version"], status=d["status"],
        principles=d["principles"], member_constraints=d["member_constraints"],
        style=d.get("style", {}), required_checks=d.get("required_checks", []),
    )


def load_chamber_summary(d: dict) -> ChamberSummary:
    return ChamberSummary(
        id=d["id"], chamber=d["chamber"], summary_text=d["summary_text"],
        built_from=[DependencyRef(**r) for r in d["built_from"]],
        review_status=d.get("review_status", "approved"),
    )


@pytest.fixture
def seeded_corpus():
    corpus = CorpusService()

    private_source = load_source(_load("private-sanitized/source.json"))
    corpus.ingest(private_source)

    dc = load_derived_constraint(_load("private-sanitized/derived_constraint.json"))
    corpus.ingest(dc)
    corpus.link(private_source.id, dc.id, relationship="derived_from", materiality="essential")

    kernel = load_kernel(_load("private-sanitized/kernel_v1.json"))
    corpus.ingest(kernel)
    corpus.link(dc.id, kernel.id, relationship="member_of_kernel", materiality="essential")

    chamber_summary = load_chamber_summary(_load("private-sanitized/chamber_summary_v1.json"))
    corpus.ingest(chamber_summary)
    corpus.link(private_source.id, chamber_summary.id, relationship="built_from", materiality="essential")

    for src_dict in _load("public/sources.json"):
        corpus.ingest(load_source(src_dict))

    return {
        "corpus": corpus, "private_source": private_source, "dc": dc,
        "kernel": kernel, "chamber_summary": chamber_summary,
        "public_fragments": _load("public/fragments.json"),
    }
