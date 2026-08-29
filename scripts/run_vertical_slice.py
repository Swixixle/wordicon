#!/usr/bin/env python3
"""
Vertical-slice proof (blueprint v1.2 §23, GPT-relayed instruction step 8).

Proves, end to end and with mocked model output: a private source can
influence a Wordicon result without being exposed; every Bone claim is
sourced; both receipt tiers are produced; a weak candidate is rejected and
staged as an unreviewed negative example; and revoking the private source
correctly invalidates everything derived from it — including the
Personality Kernel — while leaving prior receipts historically intact.

Run: python3 scripts/run_vertical_slice.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from wordicon_corpus.corpus_service import CorpusService  # noqa: E402
from wordicon_corpus.objects import (  # noqa: E402
    ChamberSummary, DependencyRef, DerivedConstraint, PersonalityKernel, Source,
)
from wordicon_corpus.operations import run_forge  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURES = REPO_ROOT / "fixtures"


def step(n: int, title: str) -> None:
    print(f"\n[{n:02d}] {title}")


def load_json(path: Path):
    return json.loads(path.read_text())


def load_source(d: dict) -> Source:
    return Source(
        id=d["id"], title=d["title"], created_at=d["created_at"],
        origin=d["provenance"]["origin"], author=d["provenance"]["author"],
        external_participants=d["provenance"].get("external_participants", []),
        original_file_hash=d["provenance"].get("original_file_hash"),
        epistemic_class=d["epistemic_class"], sensitivity=d["sensitivity"],
        permissions_profile=d["permissions_profile"], permissions=d["permissions"],
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


def main() -> int:
    corpus = CorpusService()

    step(1, "Ingest one sanitized private source (derived_only)")
    private_source_dict = load_json(FIXTURES / "private-sanitized" / "source.json")
    private_source = load_source(private_source_dict)
    corpus.ingest(private_source)
    print(f"  ingested {private_source.id!r}, sensitivity={private_source.sensitivity!r}")

    step(2, "Confirm it carries the derived_only permission profile")
    assert private_source.permissions_profile == "derived_only"
    assert private_source.permissions["send_to_external_model"] is False
    assert private_source.permissions["retrieve_raw"] is False
    print("  confirmed: retrieve_raw=False, send_to_external_model=False")

    step(3, "Create one reviewed Derived Constraint from it")
    dc = load_derived_constraint(load_json(FIXTURES / "private-sanitized" / "derived_constraint.json"))
    corpus.ingest(dc)
    corpus.link(private_source.id, dc.id, relationship="derived_from", materiality="essential")
    print(f"  ingested {dc.id!r}: {dc.text!r} (review_status={dc.review_status!r})")

    step(4, "Construct Personality Kernel v1 containing that constraint")
    kernel = load_kernel(load_json(FIXTURES / "private-sanitized" / "kernel_v1.json"))
    corpus.ingest(kernel)
    corpus.link(dc.id, kernel.id, relationship="member_of_kernel", materiality="essential")
    print(f"  ingested {kernel.id!r} (status={kernel.status!r}, member_constraints={kernel.member_constraints})")

    chamber_summary = load_chamber_summary(load_json(FIXTURES / "private-sanitized" / "chamber_summary_v1.json"))
    corpus.ingest(chamber_summary)
    corpus.link(private_source.id, chamber_summary.id, relationship="built_from", materiality="essential")
    print(f"  (also ingested {chamber_summary.id!r} to exercise chamber-summary revocation later)")

    step(5, "Load admitted public sources/fragments and run one Forge request")
    for src_dict in load_json(FIXTURES / "public" / "sources.json"):
        corpus.ingest(load_source(src_dict))
    public_fragments = load_json(FIXTURES / "public" / "fragments.json")
    print(f"  admitted {len(public_fragments)} public fragments as the Bone material pool")

    forge_input = "guilt produced by escaping a system that still contains people you love"
    result = run_forge(
        corpus=corpus, kernel_id=kernel.id, input_text=forge_input,
        trace_id="trace_seed_forge_001", public_fragment_pool=public_fragments,
    )
    print(f"  winner: {result['winner'].title!r} (score={result['winner_score']:.3f})")

    step(6, "Confirm the constraint's TEXT reached the model context, never the source")
    ctx = result["context_package"]
    assert ctx["governing_constraints"] == [{"constraint_id": dc.id, "text": dc.text}]
    assert "derived_from" not in json.dumps(ctx)
    assert private_source.id not in json.dumps(ctx)
    print(f"  context_package.governing_constraints = {ctx['governing_constraints']}")
    print(f"  confirmed: {private_source.id!r} does not appear anywhere in the context package")

    step(7, "Bone/Flesh/Friction as strict structured data")
    bff = result["bone_flesh_friction"]
    assert set(bff.keys()) == {"title", "bone", "flesh", "friction", "receipt_id"}
    print(f"  {json.dumps(bff, indent=2)}")

    step(8, "Every Bone claim cites an admitted public fragment")
    admitted_ids = {f["id"] for f in public_fragments}
    for claim in result["private_receipt"]["claims"]:
        assert set(claim["supporting_fragments"]) <= admitted_ids
    print(f"  {len(bff['bone']['claims'])} Bone claim(s), all citing admitted public fragments")

    step(9, "Private forensic receipt created")
    priv = result["private_receipt"]
    assert priv["derived_constraints_applied"][0]["constraint_id"] == dc.id
    print(f"  private receipt {priv['receipt_id']!r} carries the full derived_from-eligible trail (forensic only)")

    step(10, "Redacted public receipt created — cannot reveal the private fragment")
    pub = result["public_receipt"]
    serialized_public = json.dumps(pub)
    assert private_source.id not in serialized_public
    assert dc.id not in serialized_public
    assert dc.text not in serialized_public
    print(f"  public receipt: {json.dumps(pub, indent=2)}")

    step(11, "Reject one alternate candidate; confirm it staged as an unreviewed negative example")
    assert len(result["rejected_judgments"]) >= 1
    rejected = result["rejected_judgments"][0]
    assert rejected.review_status == "unreviewed"
    stored = corpus.get(rejected.id)
    assert stored is rejected
    print(f"  rejected {rejected.candidate_text!r} ({rejected.failure_axis}); staged as {rejected.id!r}, review_status=unreviewed")

    step(12, "Revoke the private source")
    event = corpus.revoke(private_source.id, revoked_by="owner", reason="vertical-slice demonstration")
    print(f"  revocation event {event.id!r}: invalidated={event.dependents_invalidated}, "
          f"queued_for_review={event.dependents_queued_for_review}, "
          f"chamber_summaries_queued_for_regeneration={event.chamber_summaries_queued_for_regeneration}")

    step(13, "Confirm the Derived Constraint and Kernel are now invalid/review-required")
    assert corpus.get(dc.id).review_status == "invalid"
    assert corpus.get(kernel.id).status in ("invalid", "review_required")
    print(f"  {dc.id}.review_status = {corpus.get(dc.id).review_status!r}")
    print(f"  {kernel.id}.status = {corpus.get(kernel.id).status!r}")

    step(14, "Confirm the prior receipt is annotated, not mutated")
    stored_receipt = corpus.receipts[priv["receipt_id"]]
    assert stored_receipt["operation"] == priv["operation"]
    assert stored_receipt["claims"] == priv["claims"]
    assert len(stored_receipt["revocation_annotations"]) >= 1
    print(f"  receipt {priv['receipt_id']!r} original fields unchanged; "
          f"{len(stored_receipt['revocation_annotations'])} revocation annotation(s) appended")

    step(15, "Confirm no subsequent operation can use the invalidated Kernel")
    try:
        run_forge(
            corpus=corpus, kernel_id=kernel.id, input_text="a second, unrelated request",
            trace_id="trace_seed_forge_002", public_fragment_pool=public_fragments,
        )
        print("  FAILED: a second Forge call succeeded against an invalidated kernel")
        return 1
    except RuntimeError as e:
        print(f"  confirmed: second Forge call refused — {e}")

    print("\nAll 15 acceptance steps passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
