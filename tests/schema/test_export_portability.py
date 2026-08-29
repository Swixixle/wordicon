"""Acceptance test 11: corpus export does not depend on a model vendor's
proprietary format (blueprint §2.2, §18)."""
import json
from pathlib import Path

from wordicon_corpus.objects import DerivedConstraint, DependencyRef, PersonalityKernel, Source

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"


def test_every_schema_file_is_plain_json_no_custom_loader_needed():
    schema_files = list(SCHEMAS_DIR.glob("*.schema.json"))
    assert len(schema_files) >= 12, "expected the full set of corpus object schemas to be present"
    for path in schema_files:
        with open(path) as f:
            doc = json.load(f)  # stdlib json only — no vendor SDK required
        assert doc["$schema"].startswith("https://json-schema.org/"), (
            f"{path.name} does not declare a standard JSON Schema dialect"
        )


def test_object_serialization_round_trips_through_stdlib_json():
    source = Source(
        id="src_export_test", title="t", created_at="2026-01-01T00:00:00Z",
        origin="manual_entry", author="owner", epistemic_class="personal_authority",
        sensitivity="sealed", permissions_profile="sealed",
        permissions={"retrieve_raw": False, "send_to_external_model": False, "derive_constraints": False,
                     "quote_in_private_receipt": False, "quote_in_public_receipt": False, "use_for_training": False},
    )
    dc = DerivedConstraint(
        id="dc_export_test", text="constraint text",
        derived_from=[DependencyRef(object_id="src_export_test", materiality="essential")],
        derivation_method="curator_authored", review_status="approved",
        sensitivity="derived_only", permissions_profile="derived_only", valid_from="2026-01-01T00:00:00Z",
    )
    kernel = PersonalityKernel(
        id="kernel_v1_test", kernel_version=1, status="approved",
        principles=["p1"], member_constraints=["dc_export_test"],
    )

    for obj in (source, dc, kernel):
        raw = obj.to_schema_dict()
        text = json.dumps(raw)  # no custom encoder
        back = json.loads(text)  # no custom decoder
        assert back == raw, f"{obj.id} did not round-trip through plain json.dumps/json.loads"
