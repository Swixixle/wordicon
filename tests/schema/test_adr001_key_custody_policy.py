"""Acceptance test 12: loss of an ordinary application device does not
prevent recovery under the proposed key-custody plan.

ADR-001 is a proposal, not implemented (see docs/adr/ADR-001... and
blueprint §23) — there is no running key-management code to exercise. This
test instead checks documentation parity: that the ADR actually states the
required property in terms specific enough to hold someone to later, rather
than the property being implied and forgettable. If this test starts
failing, either the ADR was edited to drop the guarantee, or it was never
this specific in the first place — both are worth catching before real
material is ever encrypted under whatever scheme gets built from it.
"""
from pathlib import Path

ADR_PATH = Path(__file__).resolve().parents[2] / "docs" / "adr" / "ADR-001-key-custody-and-recovery.md"


def test_adr001_exists_and_is_not_silent_on_device_loss():
    text = ADR_PATH.read_text()
    assert "Option 2" in text and "recommended" in text.lower()
    assert "does not destroy the corpus" in text
    assert "threshold" in text.lower()


def test_adr001_recommended_option_is_not_the_single_point_of_failure_option():
    text = ADR_PATH.read_text()
    option_2_start = text.index("### Option 2")
    option_3_start = text.index("### Option 3")
    option_2_body = text[option_2_start:option_3_start]
    assert "Loss of any single device, single backup copy, or single recovery share does not destroy the corpus" in option_2_body
