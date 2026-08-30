"""The access gate — a home-LAN pairing lock for the Wordicon server.

What this is, said honestly: a default-deny gate over every corpus, media,
export, mutation, and model-spending route, opened per device by a one-time
pairing code read off the Mac's own terminal. What this is NOT: encrypted
transport. Traffic is plain HTTP on the local network; on shared or hostile
Wi-Fi the gate keeps strangers out of the ROUTES but does not hide the
BYTES. No clinical-grade confidentiality is claimed or should be inferred
until HTTPS or a private overlay exists.

Mechanics, all owned here:
- A master secret (32 bytes via `secrets`) lives at local_state/auth/
  master_secret with 0600 permissions — ignored by git along with all of
  local_state. It is the HMAC key under which session tokens are
  recognized, so ROTATING it invalidates every session at once.
- A pairing code is minted fresh each server boot with `secrets`, held in
  memory only, printed to the terminal (the trusted channel), and accepted
  ONLY via POST body — never a URL, never a query string, never a log.
- A successful pairing mints a session token (`secrets`, 32 bytes); the
  server stores only HMAC(master, token) in an append-only sessions log,
  and the browser holds the token in an HttpOnly, SameSite=Strict cookie.
- Revocation is an append-only row; rotation rewrites the master; both are
  folded the way every other Wordicon log is folded.
- Failed pairing attempts are counted and the code lane locks after a
  bounded number until restart — a phone typo costs a retry, a scan of the
  LAN costs the attacker the whole boot.

Paths derive from cli.LOCAL_STATE at call time, so the test suite's state
redirect and the serve-real harness gate their own scratch worlds and the
owner's real corpus is never touched by a test.
"""

import hashlib
import hmac
import json
import os
import pathlib
import secrets

import wordicon_cli as cli

SESSION_COOKIE = "wordicon_session"
PAIR_MAX_FAILURES = 25
SESSION_DAYS = 180

# in-memory, per-process: the pairing code and the failure counter
_STATE = {"code": None, "failures": 0}


def auth_dir() -> pathlib.Path:
    return pathlib.Path(cli.LOCAL_STATE) / "auth"


def master_path() -> pathlib.Path:
    return auth_dir() / "master_secret"


def sessions_log() -> pathlib.Path:
    return auth_dir() / "sessions.jsonl"


def ensure_master() -> bytes:
    """Load the master secret, minting it on first use — 0600, under the
    ignored state directory, never printed, never in git."""
    p = master_path()
    if not p.exists():
        auth_dir().mkdir(parents=True, exist_ok=True)
        p.write_bytes(secrets.token_bytes(32))
        os.chmod(p, 0o600)
    return p.read_bytes()


def rotate_master() -> None:
    """New master secret. Every session token in the world stops
    verifying at this instant — the sessions log keeps its history, but
    no stored MAC matches under the new key."""
    auth_dir().mkdir(parents=True, exist_ok=True)
    master_path().write_bytes(secrets.token_bytes(32))
    os.chmod(master_path(), 0o600)
    _append({"type": "rotation", "at": cli._now()})


def _append(row: dict) -> None:
    auth_dir().mkdir(parents=True, exist_ok=True)
    with open(sessions_log(), "a") as f:
        f.write(json.dumps(row) + "\n")


def _rows() -> "list[dict]":
    p = sessions_log()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            out.append(row)
    return out


def _mac(token: str) -> str:
    return hmac.new(ensure_master(), token.encode(), hashlib.sha256).hexdigest()


def new_pairing_code() -> str:
    """Fresh code for this server boot. Held in memory, printed to the
    terminal, accepted only via POST."""
    _STATE["code"] = "-".join(
        f"{secrets.randbelow(1000):03d}" for _ in range(3))
    _STATE["failures"] = 0
    return _STATE["code"]


def current_code() -> str:
    return _STATE["code"] or ""


def pair(code: str, device: str = "") -> "dict | None":
    """Verify the pairing code and mint a session. None on failure; the
    failure counter is the brake — after PAIR_MAX_FAILURES the code lane
    locks until the owner restarts the server (and reads a fresh code)."""
    if _STATE["failures"] >= PAIR_MAX_FAILURES:
        return None
    want = _STATE["code"]
    if not want or not hmac.compare_digest(str(code or ""), want):
        _STATE["failures"] += 1
        return None
    return issue_session(device or "unnamed device")


def issue_session(device: str) -> dict:
    """Mint a session. Server-side only — nothing over HTTP reaches this
    except through pair() with a correct code."""
    token = secrets.token_urlsafe(32)
    row = {"type": "session",
           "session_id": "sess_" + secrets.token_hex(6),
           "device": (device or "unnamed device")[:80],
           "mac": _mac(token), "created_at": cli._now()}
    _append(row)
    return {"token": token, "session_id": row["session_id"],
            "device": row["device"]}


def verify(token: str) -> "dict | None":
    """The folded truth: a session is good if its MAC matches under the
    CURRENT master (rotation kills all), and no revocation row names it."""
    if not token:
        return None
    mac = _mac(token)
    active = None
    for r in _rows():
        if r.get("type") == "session" and hmac.compare_digest(
                r.get("mac", ""), mac):
            active = r
        elif r.get("type") == "revoke" and active \
                and r.get("session_id") == active.get("session_id"):
            active = None
    return active


def revoke(session_id: str) -> bool:
    if not any(r.get("session_id") == session_id and r.get("type") == "session"
               for r in _rows()):
        return False
    _append({"type": "revoke", "session_id": session_id, "at": cli._now()})
    return True


def devices() -> "list[dict]":
    """Paired devices, revocations folded — what the manage screen shows."""
    out = {}
    for r in _rows():
        if r.get("type") == "session":
            out[r["session_id"]] = {"session_id": r["session_id"],
                                     "device": r.get("device", ""),
                                     "created_at": r.get("created_at", ""),
                                     "revoked": False}
        elif r.get("type") == "revoke" and r.get("session_id") in out:
            out[r["session_id"]]["revoked"] = True
    return sorted(out.values(), key=lambda d: d["created_at"], reverse=True)


def bind_host() -> str:
    """LAN exposure is opt-in. Without WORDICON_LAN=1 the server binds
    loopback only; with it, 0.0.0.0 — and the gate is enforced either
    way, so an ungated 0.0.0.0 cannot exist."""
    return "0.0.0.0" if os.environ.get("WORDICON_LAN") == "1" else "127.0.0.1"
