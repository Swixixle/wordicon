"""The Ledger — the owner's own trail, owned by the owner.

What this is (his ruling, 2026-10-16): "I like the idea of taking all
routes, saved info time stamped and documented in a retrievable way" — the
behavioral layer the big platforms harvest in the dark, captured here in
the light: which doors he opened, which pages he stood in, which documents
and results he looked at, when the desk had his attention and when it went
quiet. The inversion is the point: same instrument, custody flipped — the
ledger is shown to the only person it is for, lives in his store, and the
Vault seals it with his writing.

What this is NOT: a keylogger (ruled out for now — events first), a reader
of content (events carry ids and short titles, never bodies), or a wire to
anywhere (appends come only from his paired page; nothing leaves the
machine). The acts themselves — prepares, Starts, rulings — already live in
their own records; the Ledger holds ATTENTION, which no record held.

Mechanics: append-only JSONL under local_state/ledger/, one file per month
(events-YYYY-MM.jsonl). Each line keeps the client's clock and the
server's receive clock — two clocks, named, never blended. A visible
switch (config.json: {"enabled": bool}) turns capture off; a disabled
ledger refuses appends by name and keeps what was already written.
"""
from __future__ import annotations

import json
import os
import re
import uuid
import fcntl
import pathlib
from datetime import datetime, timezone

import wordicon_cli as cli
import workspace_identity

# every type the ledger will hold; an unknown type is refused by name,
# never silently kept — the disclosure page lists exactly these
EVENT_TYPES = (
    "session_start", "session_end",
    "page_shown",            # a destination of the shell (work, yourwork, investigate, settings, help)
    "place_opened", "place_closed",   # a specialist place inside the shell (bench, clinic, map …)
    "document_opened",
    "result_viewed",
    "visibility_hidden", "visibility_visible",   # the tab lost or regained his attention
    # W2 amendment (his ruling, recorded in docs/adr-extraction.md; "ok go",
    # 2026-10-17): the interaction inventory joins deliberately — the pinned
    # set moves because he ruled it, not because something drifted. Events
    # still carry ids and short titles, never bodies: the query text lives
    # in the capture store, the revision bodies in the notebook, the acts in
    # their own records; these five are the ATTENTION of each.
    "import_attempted",      # he tried to bring something in (outcome lives in the act's own record)
    "question_followed",     # a Go deeper step: a suggested question taken or his own asked
    "material_carried",      # an excerpt carried back to the writing's revision notes
    "edit_applied",          # a save that changed a document (the revision itself is in the notebook)
    "search_performed",      # a search box used (scope and count here; the words in the capture store)
    "capture_gap",           # an explicitly observed delivery/storage gap, never invented activity
    "activity_state",        # visible/focused/idle state; never proof of reading
    "activity_interval",     # bounded coarse estimate, with its observation policy
    "material_selected",     # nonempty selected range boundary, no selected text
    "document_edited",       # observed edit batch, distinct from a committed save
    "document_saved",        # confirmed notebook revision, not a save request
)
MAX_BATCH = 100
MAX_TITLE = 120
MAX_FIELD = 300
SCHEMA = "nikodemus.attention.v2"
_ID = re.compile(r"^[A-Za-z0-9_.:-]{1,120}$")


def scope_id() -> str:
    """Read an initialized workspace routing scope; never create one on read."""
    return workspace_identity.attention_scope()


def _interval(value) -> dict:
    """Closed estimate contract: no event bodies, gestures or arbitrary extras."""
    keys = {"policy", "state", "start_at", "end_at", "duration_ms", "idle_after_ms", "reason"}
    if not isinstance(value, dict) or set(value) != keys:
        raise ValueError("an activity interval has unsupported fields")
    if value["policy"] != "visibility_focus_idle.v1" or value["state"] not in {"foreground_active_estimate", "foreground_idle_estimate"}:
        raise ValueError("an activity interval has an unsupported estimate policy or state")
    if value["reason"] not in {"checkpoint", "idle", "input", "focus", "blur", "hidden", "visible", "pagehide", "recording_off", "context"}:
        raise ValueError("an activity interval has an unsupported boundary")
    if type(value["duration_ms"]) is not int or not 0 < value["duration_ms"] <= 30000 or type(value["idle_after_ms"]) is not int or value["idle_after_ms"] != 60000:
        raise ValueError("an activity interval exceeds its estimate bounds")
    try:
        if any(not isinstance(value[k], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}(?:\.\d{3})?(?:Z|[+-]\d{2}:\d{2})", value[k]) for k in ("start_at", "end_at")):
            raise ValueError("an ISO clock boundary is required")
        dates = [datetime.fromisoformat(value[k].replace("Z", "+00:00")) for k in ("start_at", "end_at")]
        if any(d.tzinfo is None for d in dates):
            raise ValueError("timezone required")
        elapsed = (dates[1] - dates[0]).total_seconds() * 1000
        if elapsed < 0 or abs(elapsed - value["duration_ms"]) > 2000:
            raise ValueError("clock/duration mismatch")
    except (ValueError, TypeError, AttributeError, OverflowError):
        raise ValueError("an activity interval has invalid clock boundaries") from None
    return dict(value)


def _dir() -> pathlib.Path:
    return pathlib.Path(cli.LOCAL_STATE) / "ledger"


def _config_path() -> pathlib.Path:
    return _dir() / "config.json"


def enabled() -> bool:
    """On unless the owner turned it off. The default is his ruling, not a
    silent opt-in: the switch is on the Settings page, named."""
    try:
        value = json.loads(_config_path().read_text(encoding="utf-8"))
        return isinstance(value, dict) and value.get("enabled") is True
    except FileNotFoundError:
        return True
    except (OSError, UnicodeError, json.JSONDecodeError):
        # A damaged or unreadable switch cannot authorize new capture.
        return False


def set_enabled(on: bool) -> dict:
    _dir().mkdir(parents=True, exist_ok=True)
    cfg = {"enabled": bool(on), "changed_at": _now()}
    with open(_dir() / "append.lock", "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        temporary = _dir() / (".config-" + uuid.uuid4().hex)
        try:
            with open(temporary, "x", encoding="utf-8") as f:
                json.dump(cfg, f, indent=1)
                f.flush()
                os.fsync(f.fileno())
            os.replace(temporary, _config_path())
            _sync_directory()
        finally:
            temporary.unlink(missing_ok=True)
    return cfg


def _sync_directory():
    fd = os.open(_dir(), os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _month_path(received_at: str) -> pathlib.Path:
    return _dir() / f"events-{received_at[:7]}.jsonl"


def _lines(paths):
    rows, gaps = [], []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8")
        except (OSError, UnicodeError) as e:
            gaps.append({"kind": "unreadable_file", "file": path.name, "error_class": type(e).__name__})
            continue
        for index, line in enumerate(text.splitlines(), 1):
            try:
                row = json.loads(line)
                if not isinstance(row, dict) or row.get("type") not in EVENT_TYPES:
                    raise ValueError("not an event")
            except (ValueError, TypeError):
                gaps.append({"kind": "malformed_record", "file": path.name, "line": index})
                continue
            rows.append((row, path))
    return rows, gaps


def _identity(row):
    return json.dumps({k: v for k, v in row.items() if k != "received_at"}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def append(events: list) -> dict:
    """Idempotent durable append. Lost acknowledgements never repeat a visit.

    Distinct intentional visits carry distinct event IDs. A process/file lock
    serializes dedup + append; acknowledged rows have been flushed and fsynced.
    Original JSONL stays authoritative and the ID lookup is rebuilt on each
    append, so no derived index can conceal missing or damaged source records.
    """
    def refuse(message, code="invalid_event"):
        return {"error": message, "refused": True, "code": code}
    if not enabled():
        return refuse("the Ledger is off (Settings turns it back on); nothing was recorded", "recording_off")
    if not isinstance(events, list) or not events:
        return refuse("no events were sent")
    if len(events) > MAX_BATCH:
        return refuse(f"a batch is at most {MAX_BATCH} events; this one is {len(events)}")
    received_at = _now()
    prepared = []
    for i, e in enumerate(events):
        if not isinstance(e, dict):
            return refuse(f"event {i} is not an object")
        t = e.get("type")
        if t not in EVENT_TYPES:
            return refuse(f"event {i} has a type the ledger does not hold: {t!r}")
        subject = e.get("subject") or {}
        if not isinstance(subject, dict):
            return refuse(f"event {i} has a subject that is not an object")
        subj = {}
        for k in ("id", "title", "route", "page", "kind", "revision", "scope"):
            v = subject.get(k)
            if v is None:
                continue
            v = str(v)
            if len(v) > (MAX_TITLE if k == "title" else MAX_FIELD):
                return refuse(f"event {i} subject.{k} is longer than the ledger keeps")
            subj[k] = v
        from operation_capture import sanitize_body
        if sanitize_body(subj)["redactions"]:
            return refuse("Credential-like activity metadata was refused; no content was recorded.", "unsafe_metadata")
        event_id = e.get("event_id")
        session_id = e.get("session_id")
        if event_id is not None and (not isinstance(event_id, str) or not _ID.fullmatch(event_id)):
            return refuse(f"event {i} has an invalid event_id")
        if session_id is not None and (not isinstance(session_id, str) or not _ID.fullmatch(session_id)):
            return refuse(f"event {i} has an invalid session_id")
        supplied_scope = e.get("scope_id")
        if supplied_scope is not None and supplied_scope != scope_id():
            return refuse("The queued event belongs to a different local store.", "scope_mismatch")
        row = {"schema": SCHEMA, "event_id": event_id or "legacy_" + uuid.uuid4().hex,
               "session_id": session_id, "scope_id": scope_id(), "type": t,
               "at": str(e.get("at") or "")[:40], "received_at": received_at, "subject": subj}
        if t == "activity_interval":
            try:
                row["interval"] = _interval(e.get("interval"))
            except ValueError as error:
                return refuse(str(error))
        elif "interval" in e:
            return refuse("interval metadata belongs only to an activity_interval event")
        if t == "activity_state" and subj.get("kind") not in {"foreground_active_estimate", "foreground_idle_estimate", "inactive"}:
            return refuse("an activity state has an unsupported estimate state")
        if not event_id:
            row["delivery_idempotency"] = "unavailable_legacy_client"
        prepared.append(row)
    _dir().mkdir(parents=True, exist_ok=True)
    with open(_dir() / "append.lock", "a+b") as lock:
        fcntl.flock(lock.fileno(), fcntl.LOCK_EX)
        # Recheck under the append lock so a disabled store never accepts a
        # queued batch just because the first check ran before the toggle.
        if not enabled():
            return refuse("the Ledger is off; nothing was recorded", "recording_off")
        existing, gaps = _lines(sorted(_dir().glob("events-*.jsonl")))
        if any(g["kind"] == "unreadable_file" for g in gaps):
            return {**refuse("The existing trail cannot be read safely; delivery is pending.", "store_unreadable"), "capture_gaps": gaps}
        seen = {r["event_id"]: (r, p) for r, p in existing if r.get("event_id")}
        new, acknowledgements, sync_paths = [], [], set()
        for row in prepared:
            eid = row["event_id"]
            if eid in seen:
                prior, path = seen[eid]
                if _identity(prior) != _identity(row):
                    return refuse("An event_id was reused for a different activity record.", "event_id_conflict")
                if path is not None:
                    sync_paths.add(path)
            else:
                new.append(row)
                seen[eid] = (row, None)
            acknowledgements.append(eid)
        path = _month_path(received_at)
        if new:
            with open(path, "a+b") as f:
                # Preserve an interrupted tail as its own observable bad line;
                # a retry must not concatenate a good event onto a partial one.
                f.seek(0, os.SEEK_END)
                if f.tell():
                    f.seek(-1, os.SEEK_END)
                    if f.read(1) != b"\n":
                        f.write(b"\n")
                f.write(("\n".join(json.dumps(r, ensure_ascii=False, sort_keys=True) for r in new) + "\n").encode())
                f.flush()
                os.fsync(f.fileno())
            _sync_directory()
        for old_path in sync_paths:
            with open(old_path, "rb") as f:
                os.fsync(f.fileno())
        return {"kept": len(new), "duplicates": len(prepared) - len(new), "acknowledged": acknowledgements,
                "file": path.name, "capture_gaps": gaps, "scope_id": scope_id()}


def read(day: str = "", since: str = "", limit: int = 2000) -> dict:
    """The trail, retrievable: a day (YYYY-MM-DD) or everything since an
    ISO instant, oldest first, capped and saying so."""
    out = []
    # The page's clock is the owner's local time (offset named); the store's
    # is UTC, and the month files are cut on the store's clock. A local day
    # can straddle two month files, so a filtered read looks at every file
    # rather than guessing which month holds an evening — the files are
    # monthly and few, and the trail is a deliberate press, not a hot path.
    paths = sorted(_dir().glob("events-*.jsonl")) if (day or since) \
        else sorted(_dir().glob("events-*.jsonl"))[-1:]
    rows, gaps = _lines(paths)
    for e, _path in rows:
        when = e.get("received_at") or e.get("at") or ""
        if day and not (when.startswith(day) or str(e.get("at", "")).startswith(day)):
            continue
        if since and when < since:
            continue
        out.append(e)
    truncated = len(out) > limit
    return {"events": out[-limit:], "truncated": truncated,
            "enabled": enabled(), "scope_id": scope_id(), "capture_gaps": gaps,
            "population": f"the ledger file(s) read whole from the store; {len(out)} event(s) matched"
                          + (f", the newest {limit} returned" if truncated else "")}
