"""Acceptance test 9: an unreviewed rejection cannot influence the canonical
anti-corpus (blueprint §10.2a). A rejection is captured automatically, but
promotion to a canonical, generally-applicable style prohibition requires
review — it stays 'local_to_concept' and 'unreviewed' until then."""
from wordicon_corpus.operations import run_forge


def canonical_anti_corpus_prohibitions(corpus):
    """Stand-in for a real anti-corpus retrieval query: only reviewed,
    generally-scoped rejections count as canonical prohibitions."""
    return [
        obj for obj in corpus.objects.values()
        if getattr(obj, "object_type", None) == "judgment"
        and obj.decision == "rejected"
        and obj.review_status != "unreviewed"
        and obj.scope == "general_style_prohibition"
    ]


def test_freshly_rejected_candidate_is_staged_unreviewed_and_local(seeded_corpus):
    corpus = seeded_corpus["corpus"]
    result = run_forge(
        corpus=corpus, kernel_id=seeded_corpus["kernel"].id,
        input_text="test input", trace_id="trace_test_rejection",
        public_fragment_pool=seeded_corpus["public_fragments"],
    )
    assert len(result["rejected_judgments"]) >= 1
    rejected = result["rejected_judgments"][0]
    assert rejected.review_status == "unreviewed"
    assert rejected.scope == "local_to_concept"

    # And it must not appear in the canonical anti-corpus query yet.
    assert rejected.id not in [j.id for j in canonical_anti_corpus_prohibitions(corpus)]


def test_reviewed_general_rejection_does_appear_in_canonical_anti_corpus(seeded_corpus):
    from wordicon_corpus.objects import Judgment

    corpus = seeded_corpus["corpus"]
    reviewed = Judgment(
        id="jdg_reviewed_001", decision="rejected", candidate_text="Gentle Unburdening",
        originating_operation="trace_seed_004", decision_source="owner",
        confidence=0.9, review_status="approved", scope="general_style_prohibition",
        reason="therapeutic reassurance language",
    )
    corpus.ingest(reviewed)
    assert reviewed.id in [j.id for j in canonical_anti_corpus_prohibitions(corpus)]
