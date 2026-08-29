"""Acceptance test 2: a public receipt cannot expose a private source ID,
title, fragment, or conversation text."""
import json

from wordicon_corpus.operations import run_forge
from wordicon_corpus.validators import ValidationFailure, validate_no_private_leak


def test_public_receipt_excludes_private_source_and_constraint(seeded_corpus):
    corpus = seeded_corpus["corpus"]
    result = run_forge(
        corpus=corpus, kernel_id=seeded_corpus["kernel"].id,
        input_text="guilt produced by escaping a system that still contains people you love",
        trace_id="trace_test_public_receipt", public_fragment_pool=seeded_corpus["public_fragments"],
    )
    public = result["public_receipt"]
    serialized = json.dumps(public)

    assert seeded_corpus["private_source"].id not in serialized
    assert seeded_corpus["private_source"].title not in serialized
    assert seeded_corpus["dc"].id not in serialized
    assert seeded_corpus["dc"].text not in serialized


def test_validator_catches_a_leak_the_redaction_code_missed(seeded_corpus):
    """Defense in depth: even if build_public_receipt had a bug, the
    standalone validator must independently catch a private id appearing in
    the serialized public receipt."""
    leaking_receipt = {"note": f"influenced by {seeded_corpus['private_source'].id}"}
    try:
        validate_no_private_leak(leaking_receipt, {seeded_corpus["private_source"].id})
        assert False, "validator failed to catch a private id embedded in a public receipt"
    except ValidationFailure:
        pass
