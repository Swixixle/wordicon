"""
Loads schemas/*.schema.json into a jsonschema Draft 2020-12 registry so that
cross-file $refs (e.g. source.schema.json referencing enums.schema.json)
resolve without a network fetch or manual pointer surgery.
"""
from __future__ import annotations

import json
from functools import lru_cache
from pathlib import Path

from jsonschema import Draft202012Validator
from referencing import Registry, Resource

SCHEMAS_DIR = Path(__file__).resolve().parents[2] / "schemas"


@lru_cache(maxsize=1)
def _registry() -> Registry:
    resources = []
    for path in SCHEMAS_DIR.glob("*.schema.json"):
        schema = json.loads(path.read_text())
        resources.append((schema["$id"], Resource.from_contents(schema)))
    return Registry().with_resources(resources)


@lru_cache(maxsize=None)
def validator_for(schema_filename: str) -> Draft202012Validator:
    schema = json.loads((SCHEMAS_DIR / schema_filename).read_text())
    return Draft202012Validator(schema, registry=_registry())


def validate(schema_filename: str, instance: dict) -> None:
    """Raises jsonschema.exceptions.ValidationError on failure."""
    validator_for(schema_filename).validate(instance)
