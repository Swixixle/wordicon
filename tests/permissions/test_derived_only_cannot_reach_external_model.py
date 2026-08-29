"""Acceptance test 1: a derived_only source cannot appear in an
external-model context."""
from wordicon_corpus.model_gateway import EgressViolation, MockModelGateway
from wordicon_corpus.permissions import can_send_to_external_model, resolve_permissions


def test_derived_only_profile_forbids_external_send():
    permissions = resolve_permissions("derived_only")
    assert can_send_to_external_model(permissions) is False


def test_context_package_carrying_raw_text_is_refused_by_gateway():
    gateway = MockModelGateway()
    dirty_context = {
        "operation": "forge", "kernel_version": 1, "input": "x",
        "governing_constraints": [], "receipt_trace_id": "trace_x",
        "raw_text": "this should never be here",
    }
    try:
        gateway.forge(dirty_context, [])
        assert False, "gateway accepted a context package containing raw_text"
    except EgressViolation:
        pass


def test_context_package_carrying_derived_from_pointer_is_refused_by_gateway():
    gateway = MockModelGateway()
    dirty_context = {
        "operation": "forge", "kernel_version": 1, "input": "x",
        "governing_constraints": [{"constraint_id": "dc_1", "text": "t", "derived_from": ["src_private_1"]}],
        "receipt_trace_id": "trace_x",
    }
    try:
        gateway.forge(dirty_context, [])
        assert False, "gateway accepted a context package leaking a derived_from chain"
    except EgressViolation:
        pass


def test_forge_context_package_from_real_pipeline_never_carries_source_id(seeded_corpus):
    from wordicon_corpus.operations import run_forge

    corpus = seeded_corpus["corpus"]
    result = run_forge(
        corpus=corpus, kernel_id=seeded_corpus["kernel"].id,
        input_text="test input", trace_id="trace_test_1",
        public_fragment_pool=seeded_corpus["public_fragments"],
    )
    import json
    serialized = json.dumps(result["context_package"])
    assert seeded_corpus["private_source"].id not in serialized
