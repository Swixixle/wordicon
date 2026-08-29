"""Acceptance test 8: a permission-profile override is impossible without an
audit record."""
import pytest

from wordicon_corpus.permissions import PermissionError_, resolve_permissions


def test_override_missing_reason_is_rejected():
    with pytest.raises(PermissionError_):
        resolve_permissions("private_raw", overrides=[{
            "flag": "quote_in_public_receipt", "new_value": True,
            "curator": "owner", "timestamp": "2026-08-19T00:00:00Z",
            # "reason" deliberately omitted
        }])


def test_override_missing_curator_is_rejected():
    with pytest.raises(PermissionError_):
        resolve_permissions("private_raw", overrides=[{
            "flag": "quote_in_public_receipt", "new_value": True,
            "reason": "owner wants this quoted", "timestamp": "2026-08-19T00:00:00Z",
        }])


def test_fully_audited_override_is_applied():
    resolved = resolve_permissions("private_raw", overrides=[{
        "flag": "quote_in_public_receipt", "prior_value": False, "new_value": True,
        "reason": "owner explicitly approved this one quote for publication",
        "curator": "owner", "timestamp": "2026-08-19T00:00:00Z",
    }])
    assert resolved["quote_in_public_receipt"] is True
    # everything else from the profile is untouched
    assert resolved["send_to_external_model"] is False
