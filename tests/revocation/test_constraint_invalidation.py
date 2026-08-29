"""Acceptance test 4: revoking an essential source invalidates its Derived
Constraint."""


def test_revoking_essential_source_invalidates_constraint(seeded_corpus):
    corpus = seeded_corpus["corpus"]
    dc = seeded_corpus["dc"]
    private_source = seeded_corpus["private_source"]

    assert dc.review_status == "approved"
    event = corpus.revoke(private_source.id, revoked_by="owner", reason="test")

    assert dc.id in event.dependents_invalidated
    assert corpus.get(dc.id).review_status == "invalid"
