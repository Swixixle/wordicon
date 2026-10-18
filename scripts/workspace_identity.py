"""Durable local workspace identity; copying/restoring a store retains identity.

Only ensure() writes. Readers fail closed on missing/corrupt identity. The
one-time, explicit legacy migration preserves the former attention routing
scope so pending browser records remain attached to their original store.
New stores never derive identity from their filesystem path.
"""
from __future__ import annotations

from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path
import re
import uuid

SCHEMA = "nikodemus.workspace_identity.v1"
NAME = "workspace-identity.json"


class IdentityError(ValueError):
    pass


def _root(root=None):
    if root is None:
        import wordicon_cli as cli
        root = cli.LOCAL_STATE
    return Path(root).resolve()


def read(root=None):
    """Read without creating files, locks or replacement identities."""
    try:
        value = json.loads((_root(root) / NAME).read_text(encoding="utf-8"))
    except FileNotFoundError as e:
        raise IdentityError("Workspace identity is not initialized; restart the local server.") from e
    except (OSError, ValueError, UnicodeError) as e:
        raise IdentityError("Workspace identity cannot be read; its original file was preserved.") from e
    if (not isinstance(value, dict) or value.get("schema") != SCHEMA
            or not re.fullmatch(r"workspace_[a-f0-9]{32}", str(value.get("workspace_id", "")))
            or not re.fullmatch(r"ledger_[a-f0-9]{24}", str(value.get("attention_scope_id", "")))
            or type(value.get("legacy_attention_scope_preserved")) is not bool
            or not isinstance(value.get("created_at"), str)):
        raise IdentityError("Workspace identity has an unsupported shape; no replacement was made.")
    return value


def ensure(root=None, *, migrate_legacy_scope=False):
    """Initialize once at a serving/migration boundary under the corpus guard.

    migrate_legacy_scope is only for a checked existing store at its original
    path. Restores of pre-identity backups need an explicit migration decision;
    they must not silently claim an old browser queue from the same path.
    """
    root = _root(root)
    root.mkdir(parents=True, exist_ok=True)
    with open(root / "workspace-identity.lock", "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        path = root / NAME
        if path.exists():
            return read(root)
        workspace_id = "workspace_" + uuid.uuid4().hex
        scope_basis = str(root) if migrate_legacy_scope else workspace_id
        value = {"schema": SCHEMA, "workspace_id": workspace_id,
                 "attention_scope_id": "ledger_" + hashlib.sha256(scope_basis.encode()).hexdigest()[:24],
                 "legacy_attention_scope_preserved": bool(migrate_legacy_scope),
                 "created_at": datetime.now(timezone.utc).isoformat()}
        temporary = root / (".workspace-identity-" + uuid.uuid4().hex)
        try:
            fd = os.open(temporary, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as f:
                json.dump(value, f, sort_keys=True, indent=2)
                f.write("\n"); f.flush(); os.fsync(f.fileno())
            os.replace(temporary, path)
            fd = os.open(root, os.O_RDONLY)
            try:
                os.fsync(fd)
            finally:
                os.close(fd)
        finally:
            temporary.unlink(missing_ok=True)
        return value


def attention_scope():
    return read()["attention_scope_id"]
