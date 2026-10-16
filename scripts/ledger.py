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
import pathlib
from datetime import datetime, timezone

import wordicon_cli as cli

# every type the ledger will hold; an unknown type is refused by name,
# never silently kept — the disclosure page lists exactly these
EVENT_TYPES = (
    "session_start", "session_end",
    "page_shown",            # a destination of the shell (work, yourwork, investigate, settings, help)
    "place_opened", "place_closed",   # a specialist place inside the shell (bench, clinic, map …)
    "document_opened",
    "result_viewed",
    "visibility_hidden", "visibility_visible",   # the tab lost or regained his attention
)
MAX_BATCH = 100
MAX_TITLE = 120
MAX_FIELD = 300


def _dir() -> pathlib.Path:
    return pathlib.Path(cli.LOCAL_STATE) / "ledger"


def _config_path() -> pathlib.Path:
    return _dir() / "config.json"


def enabled() -> bool:
    """On unless the owner turned it off. The default is his ruling, not a
    silent opt-in: the switch is on the Settings page, named."""
    try:
        return json.loads(_config_path().read_text(encoding="utf-8")).get("enabled", True) is not False
    except (OSError, json.JSONDecodeError):
        return True


def set_enabled(on: bool) -> dict:
    _dir().mkdir(parents=True, exist_ok=True)
    cfg = {"enabled": bool(on), "changed_at": _now()}
    _config_path().write_text(json.dumps(cfg, indent=1), encoding="utf-8")
    return cfg


def _now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _month_path(received_at: str) -> pathlib.Path:
    return _dir() / f"events-{received_at[:7]}.jsonl"


def append(events: list) -> dict:
    """Keep a batch of events the owner's page reported. Shape is enforced,
    never repaired: an unknown type or an oversized field refuses the whole
    batch by name, so the ledger never holds a line it cannot vouch for."""
    if not enabled():
        return {"error": "the Ledger is off (Settings turns it back on); nothing was recorded", "refused": True}
    if not isinstance(events, list) or not events:
        return {"error": "no events were sent", "refused": True}
    if len(events) > MAX_BATCH:
        return {"error": f"a batch is at most {MAX_BATCH} events; this one is {len(events)}", "refused": True}
    received_at = _now()
    lines = []
    for i, e in enumerate(events):
        if not isinstance(e, dict):
            return {"error": f"event {i} is not an object", "refused": True}
        t = e.get("type")
        if t not in EVENT_TYPES:
            return {"error": f"event {i} has a type the ledger does not hold: {t!r}", "refused": True}
        at = str(e.get("at") or "")[:40]
        subject = e.get("subject") or {}
        if not isinstance(subject, dict):
            return {"error": f"event {i} has a subject that is not an object", "refused": True}
        subj = {}
        for k in ("id", "title", "route", "page", "kind"):
            v = subject.get(k)
            if v is None:
                continue
            v = str(v)
            if len(v) > (MAX_TITLE if k == "title" else MAX_FIELD):
                return {"error": f"event {i} subject.{k} is longer than the ledger keeps", "refused": True}
            subj[k] = v
        lines.append(json.dumps({"type": t, "at": at, "received_at": received_at, "subject": subj},
                                ensure_ascii=False, sort_keys=True))
    _dir().mkdir(parents=True, exist_ok=True)
    path = _month_path(received_at)
    with open(path, "a", encoding="utf-8") as f:
        f.write("\n".join(lines) + "\n")
    return {"kept": len(lines), "file": path.name}


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
    for p in paths:
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            continue
        for line in text.splitlines():
            try:
                e = json.loads(line)
            except json.JSONDecodeError:
                continue
            when = e.get("received_at") or e.get("at") or ""
            if day and not (when.startswith(day) or str(e.get("at", "")).startswith(day)):
                continue
            if since and when < since:
                continue
            out.append(e)
    truncated = len(out) > limit
    return {"events": out[-limit:], "truncated": truncated,
            "enabled": enabled(),
            "population": f"the ledger file(s) read whole from the store; {len(out)} event(s) matched"
                          + (f", the newest {limit} returned" if truncated else "")}
