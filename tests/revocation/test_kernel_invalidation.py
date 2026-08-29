"""Acceptance test 5: invalidating a Derived Constraint marks dependent
Kernel versions unusable — and, per blueprint §13a.4, kernels are never
silently patched, only marked invalid/review-required."""
import pytest

from wordicon_corpus.operations import run_forge


def test_revoking_source_marks_dependent_kernel_invalid(seeded_corpus):
    corpus = seeded_corpus["corpus"]
    kernel = seeded_corpus["kernel"]
    private_source = seeded_corpus["private_source"]

    assert kernel.status == "approved"
    corpus.revoke(private_source.id, revoked_by="owner", reason="test")

    assert corpus.get(kernel.id).status in ("invalid", "review_required")


def test_invalidated_kernel_refuses_new_forge_operations(seeded_corpus):
    corpus = seeded_corpus["corpus"]
    kernel = seeded_corpus["kernel"]
    private_source = seeded_corpus["private_source"]

    corpus.revoke(private_source.id, revoked_by="owner", reason="test")

    with pytest.raises(RuntimeError):
        run_forge(
            corpus=corpus, kernel_id=kernel.id, input_text="anything",
            trace_id="trace_should_not_run", public_fragment_pool=seeded_corpus["public_fragments"],
        )


def test_kernel_is_never_silently_patched_in_place(seeded_corpus):
    """The object identified by kernel_v1's id must reflect the invalid
    status — not a new, differently-shaped object created in its place. A
    new usable version would have to be a distinct id (kernel_v2)."""
    corpus = seeded_corpus["corpus"]
    kernel = seeded_corpus["kernel"]
    private_source = seeded_corpus["private_source"]
    original_principles = list(kernel.principles)

    corpus.revoke(private_source.id, revoked_by="owner", reason="test")

    post = corpus.get(kernel.id)
    assert post.id == kernel.id
    assert post.principles == original_principles  # content untouched, only status changed
    assert post.status != "approved"
