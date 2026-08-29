"""Acceptance test 7: historical receipts are annotated, not silently
mutated (blueprint §12.3 invariant, added in v1.2)."""
import copy

from wordicon_corpus.operations import run_forge


def test_receipt_content_unchanged_after_revocation_only_annotation_appended(seeded_corpus):
    corpus = seeded_corpus["corpus"]
    result = run_forge(
        corpus=corpus, kernel_id=seeded_corpus["kernel"].id,
        input_text="guilt produced by escaping a system that still contains people you love",
        trace_id="trace_test_annotation", public_fragment_pool=seeded_corpus["public_fragments"],
    )
    receipt_id = result["private_receipt"]["receipt_id"]
    before = copy.deepcopy(corpus.receipts[receipt_id])
    assert before["revocation_annotations"] == []

    corpus.revoke(seeded_corpus["private_source"].id, revoked_by="owner", reason="test")

    after = corpus.receipts[receipt_id]
    # Every field except revocation_annotations must be byte-for-byte identical.
    for key in before:
        if key == "revocation_annotations":
            continue
        assert after[key] == before[key], f"receipt field {key!r} was mutated by revocation"

    assert len(after["revocation_annotations"]) == 1
    assert after["revocation_annotations"][0]["revocation_event_id"].startswith("rev_")
