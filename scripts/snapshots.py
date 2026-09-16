#!/usr/bin/env python3
"""Immutable input snapshots (workspace-v2, slice B; the storage contract's
"analysis snapshot" of §7).

What a snapshot is. The exact material an action was proposed on, frozen
at the press: the document's id, committed revision and local edit
generation, the range and its units, the exact text (and, from slice C,
the structured content and its versions), and hashes of the whole text and
of the selected slice. It is written once and never rewritten; an
operation and its result link to it by id, so "what did the model see" is
always answerable from the record and never re-read from a newer head.

Identity is content-addressed: the id is a hash of the canonical record
(everything but `created_at`), so the same capture twice is the same
snapshot, and a snapshot can be checked against its own id. Files live
under <state>/snapshots/<id>.json, written by temp-file-and-rename so a
crash leaves either a whole file or none."""
from __future__ import annotations

import hashlib
import json
import os
import tempfile
from datetime import datetime, timezone
from pathlib import Path

import wordicon_cli as cli

UNITS = ("codepoint", "utf16")


def _dir() -> Path:
    return Path(cli.LOCAL_STATE) / "snapshots"


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="microseconds").replace("+00:00", "Z")


def sha256_text(text: str) -> str:
    return hashlib.sha256((text or "").encode("utf-8")).hexdigest()


def canonical(rec: dict) -> str:
    body = {k: v for k, v in rec.items() if k not in ("created_at", "snapshot_id")}
    return json.dumps(body, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def make(*, kind: str, text: str, doc_id: str = "", revision: int | None = None, seq: int | None = None,
         range_: dict | None = None, units: str = "codepoint", structure: dict | None = None,
         doc_schema: int | None = None, projection_version: int | None = None, input_kind: str = "text",
         title: str = "", editor_session: str = "") -> dict:
    """Build the record without writing it. `text` is the exact text the
    action will receive; for a selection it is the slice, and `range_` says
    where in the document (start/end in `units`) it was taken from."""
    if kind not in ("document", "selection", "description", "concept", "word"):
        raise ValueError(f"unknown snapshot kind {kind!r}")
    if units not in UNITS:
        raise ValueError(f"unknown range units {units!r}")
    text = text if isinstance(text, str) else ""
    rec = {
        "kind": kind,
        "doc_id": str(doc_id or ""),
        "revision": int(revision) if isinstance(revision, int) and not isinstance(revision, bool) else None,
        "seq": int(seq) if isinstance(seq, int) and not isinstance(seq, bool) else None,
        "editor_session": str(editor_session or "")[:64],
        "range": ({"start": int(range_["start"]), "end": int(range_["end"]), "units": units}
                  if isinstance(range_, dict) and "start" in range_ and "end" in range_ else None),
        "title": str(title or "")[:200],
        "text": text,
        "text_sha256": sha256_text(text),
        "chars": len(text),
        "words": len(text.split()),
        "input_kind": input_kind,
        "structure": structure,
        "doc_schema": doc_schema,
        "projection_version": projection_version,
    }
    rec["snapshot_id"] = "snap_" + hashlib.sha256(canonical(rec).encode("utf-8")).hexdigest()[:24]
    rec["created_at"] = _now()
    return rec


def write(rec: dict) -> dict:
    """Persist the record once. An existing file with the same id is the
    same content by construction and is left alone."""
    d = _dir()
    d.mkdir(parents=True, exist_ok=True)
    path = d / f"{rec['snapshot_id']}.json"
    if path.exists():
        return rec
    fd, tmp = tempfile.mkstemp(prefix=".snap_", dir=str(d))
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(rec, f, ensure_ascii=False, sort_keys=True)
            f.flush()
            os.fsync(f.fileno())
        os.replace(tmp, path)
    finally:
        try:
            os.unlink(tmp)
        except OSError:
            pass
    return rec


def load(snapshot_id: str) -> dict | None:
    if not snapshot_id or "/" in snapshot_id or not snapshot_id.startswith("snap_"):
        return None
    path = _dir() / f"{snapshot_id}.json"
    try:
        rec = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    return rec


def verify(rec: dict) -> bool:
    """The record hashes to its own id and its text to its own digest."""
    try:
        want = "snap_" + hashlib.sha256(canonical(rec).encode("utf-8")).hexdigest()[:24]
        return rec.get("snapshot_id") == want and rec.get("text_sha256") == sha256_text(rec.get("text", ""))
    except Exception:  # noqa: BLE001
        return False


def summary(rec: dict) -> dict:
    """What a card may say about a snapshot: never the whole text."""
    t = rec.get("text") or ""
    head = t.strip().replace("\n", " ")
    return {"snapshot_id": rec.get("snapshot_id"), "kind": rec.get("kind"), "doc_id": rec.get("doc_id"),
            "revision": rec.get("revision"), "seq": rec.get("seq"), "editor_session": rec.get("editor_session") or "",
            "range": rec.get("range"),
            "chars": rec.get("chars"), "words": rec.get("words"), "text_sha256": rec.get("text_sha256"),
            "head": head[:80] + ("…" if len(head) > 80 else ""), "input_kind": rec.get("input_kind"),
            "created_at": rec.get("created_at")}
