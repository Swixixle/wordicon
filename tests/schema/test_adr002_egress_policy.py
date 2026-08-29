"""
ADR-002 structural parity tests (mirrors test_adr001_key_custody_policy.py).

ADR-002 is a proposal, not a closed decision (docs/adr/ADR-002...). Until
the owner names a vendor and a vendor policy record is completed per
blueprint §15.3, no object anywhere should be able to reach an external
model. These tests check that this is true by construction — not by
convention — and that the one place a real egress path is designed to
eventually open (a Derived Constraint's resolved text) can never be
accidentally granted to a raw Source instead.
"""
import yaml
import pytest

from wordicon_corpus.corpus_service import CorpusError, CorpusService
from wordicon_corpus.objects import Source
from wordicon_corpus.permissions import CONFIG_DIR, can_send_to_external_model, resolve_permissions


def test_no_profile_currently_approves_any_vendor():
    """Every profile's send_to_external_model must be false or an empty
    list — proving ADR-002 is still open, not just documented as open."""
    with open(CONFIG_DIR / "permission-profiles.yaml") as f:
        profiles = yaml.safe_load(f)["profiles"]

    for name, profile in profiles.items():
        val = profile.get("send_to_external_model")
        assert val is False or val == [], (
            f"profile {name!r} has an approved vendor ({val!r}) but ADR-002 has not been closed — "
            f"this would mean real egress is possible without the owner ever having signed off"
        )


@pytest.mark.parametrize("profile_name", [
    "private_raw", "private_retrieval", "derived_only", "private_citation",
    "public_source", "training_approved", "sealed",
])
def test_can_send_to_external_model_is_false_for_every_current_profile(profile_name):
    permissions = resolve_permissions(profile_name)
    assert can_send_to_external_model(permissions) is False


def test_constraint_text_profile_cannot_be_assigned_to_a_source():
    """The one profile designed to eventually carry real egress
    (constraint_text_external_approved) is scoped to Derived Constraint
    objects only. A Source assigned this profile must be refused at
    ingestion, not silently accepted."""
    corpus = CorpusService()
    bad_source = Source(
        id="src_should_be_refused", title="t", created_at="2026-01-01T00:00:00Z",
        origin="manual_entry", author="owner", epistemic_class="personal_authority",
        sensitivity="derived_only", permissions_profile="constraint_text_external_approved",
        permissions={"retrieve_raw": False, "send_to_external_model": [], "derive_constraints": True,
                     "quote_in_private_receipt": False, "quote_in_public_receipt": False, "use_for_training": False},
    )
    with pytest.raises(CorpusError):
        corpus.ingest(bad_source)


def test_constraint_text_profile_still_has_no_approved_vendor_by_default():
    permissions = resolve_permissions("constraint_text_external_approved")
    assert can_send_to_external_model(permissions) is False
