"""
Permission profile resolution (blueprint v1.2 §4.5, §4.5a).

Granular boolean/list flags remain the actual enforcement surface. Profiles
are named presets that populate those flags in bulk. An object may deviate
from its profile only through a recorded PermissionOverride with a reason,
prior value, new value, curator, and timestamp — never silently.
"""
from __future__ import annotations

import copy
from pathlib import Path
from typing import Any

import yaml

CONFIG_DIR = Path(__file__).resolve().parents[2] / "config"


class PermissionError_(Exception):
    """Raised when an operation would violate an object's resolved permissions."""


def load_profiles() -> dict:
    with open(CONFIG_DIR / "permission-profiles.yaml") as f:
        data = yaml.safe_load(f)
    return data["profiles"]


def resolve_permissions(profile_name: str, overrides: list[dict] | None = None) -> dict:
    """Return the effective flag set for an object: profile defaults with any
    recorded, audited overrides applied on top. Every override must carry a
    reason, curator, and timestamp — an override missing any of those is
    rejected rather than silently applied."""
    profiles = load_profiles()
    if profile_name not in profiles:
        raise PermissionError_(f"unknown permission profile: {profile_name}")

    resolved = copy.deepcopy(profiles[profile_name])
    resolved.pop("description", None)

    for ov in overrides or []:
        for required in ("flag", "new_value", "reason", "curator", "timestamp"):
            if required not in ov or ov[required] in (None, ""):
                raise PermissionError_(
                    f"permission override on flag {ov.get('flag')!r} is missing required field {required!r}; "
                    "unaudited overrides are rejected, not silently applied"
                )
        resolved[ov["flag"]] = ov["new_value"]

    return resolved


def can_send_to_external_model(permissions: dict, vendor: str | None = None) -> bool:
    val = permissions.get("send_to_external_model", False)
    if val is False:
        return False
    if not val:  # empty list = no vendor approved yet
        return False
    if vendor is None:
        return True
    return vendor in val


def can_quote_in_public_receipt(permissions: dict) -> bool:
    return bool(permissions.get("quote_in_public_receipt", False))


def can_derive_constraints(permissions: dict) -> bool:
    return bool(permissions.get("derive_constraints", False))


def can_retrieve_raw(permissions: dict, context: str = "owner_local_processing") -> bool:
    val = permissions.get("retrieve_raw", False)
    if val is False:
        return False
    return context in val


def default_profile_for_origin(origin: str) -> str:
    profiles_yaml_path = CONFIG_DIR / "permission-profiles.yaml"
    with open(profiles_yaml_path) as f:
        data = yaml.safe_load(f)
    mapping = data.get("default_profile_by_ingestion_route", {})
    return mapping.get(origin, "sealed")
