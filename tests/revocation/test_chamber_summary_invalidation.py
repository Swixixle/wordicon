"""Acceptance test 6: revoking a source invalidates dependent chamber
summaries — and, unlike a kernel, a chamber summary is regenerable, so it's
queued for regeneration rather than only queued for human review."""


def test_revoking_source_invalidates_and_queues_chamber_summary(seeded_corpus):
    corpus = seeded_corpus["corpus"]
    chamber_summary = seeded_corpus["chamber_summary"]
    private_source = seeded_corpus["private_source"]

    assert chamber_summary.review_status == "approved"
    event = corpus.revoke(private_source.id, revoked_by="owner", reason="test")

    assert chamber_summary.id in event.dependents_invalidated
    assert chamber_summary.id in event.chamber_summaries_queued_for_regeneration
    assert corpus.get(chamber_summary.id).review_status == "invalid"
