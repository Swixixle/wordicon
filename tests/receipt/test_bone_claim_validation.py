"""Acceptance test 3: a Bone claim without an admitted supporting fragment
fails validation (epistemic-contract.md §1)."""
import pytest

from wordicon_corpus.validators import ValidationFailure, validate_bone_claim


def test_claim_with_no_supporting_fragments_fails():
    claim = {"id": "claim_x", "text": "unsupported assertion", "supporting_fragments": [], "confidence": 0.9}
    with pytest.raises(ValidationFailure):
        validate_bone_claim(claim, admitted_fragment_ids={"frag_1"})


def test_claim_citing_an_unadmitted_fragment_fails():
    claim = {"id": "claim_x", "text": "assertion", "supporting_fragments": ["frag_not_admitted"], "confidence": 0.9}
    with pytest.raises(ValidationFailure):
        validate_bone_claim(claim, admitted_fragment_ids={"frag_1"})


def test_claim_with_admitted_fragment_and_valid_confidence_passes():
    claim = {"id": "claim_x", "text": "assertion", "supporting_fragments": ["frag_1"], "confidence": 0.9}
    validate_bone_claim(claim, admitted_fragment_ids={"frag_1"})  # should not raise


def test_claim_with_out_of_range_confidence_fails():
    claim = {"id": "claim_x", "text": "assertion", "supporting_fragments": ["frag_1"], "confidence": 1.4}
    with pytest.raises(ValidationFailure):
        validate_bone_claim(claim, admitted_fragment_ids={"frag_1"})
