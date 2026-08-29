"""Acceptance test 10: a sealed source cannot be retrieved, summarized,
quoted, transformed, or trained on."""
from wordicon_corpus.permissions import (
    can_derive_constraints, can_quote_in_public_receipt, can_retrieve_raw,
    can_send_to_external_model, resolve_permissions,
)


def test_sealed_profile_forbids_everything():
    permissions = resolve_permissions("sealed")
    assert can_retrieve_raw(permissions) is False
    assert can_retrieve_raw(permissions, context="private_cloud_processing") is False
    assert can_send_to_external_model(permissions) is False
    assert can_derive_constraints(permissions) is False
    assert can_quote_in_public_receipt(permissions) is False
    assert permissions["use_for_training"] is False
    assert permissions["transform_creatively"] is False
