#!/usr/bin/env python3
"""Test mode — the environment that fails closed (workspace-v2, slice A).

Why this exists. Report 79 found that the constraint suite, run on the
owner's Mac with ANTHROPIC_API_KEY in the environment, made real Anthropic
calls: `server_gateway()` returned the live gateway whenever the key was
set, and several checks posted jobs through the route without pinning a
mock. `env -u ANTHROPIC_API_KEY` was the workaround. A workaround is not a
guard: a test that spends money when one variable is present is a test
that will spend money again.

What this is. One switch, WORDICON_TEST_MODE=1, read from the environment
(so every child process inherits it) and honoured by THREE independent
layers, any one of which is enough:

  1. the socket guard — every outbound connect() in this process is refused
     unless it targets loopback on a port this module was TOLD about
     (allow_port, WORDICON_TEST_ALLOW_PORTS, JOURNEY_PORT). "Any localhost"
     is deliberately not enough: the real application may be listening on
     this machine, so its port (8420, or PORT) is refused even when listed.
     Name resolution for anything but loopback is refused too, so a
     provider SDK cannot even look a host up. Every refusal is logged
     (host, port, the calling frames — never a payload, never a header).
  2. the gateway refusal — `server.server_gateway()` returns the mock
     regardless of ANTHROPIC_API_KEY, and a provider gateway constructed
     directly (the attempt-loop checks need one) is built on an httpx
     transport that refuses every request. A sentinel key in the
     environment therefore changes nothing, which is what a test proves.
  3. the fixture stand-ins — `harden(server)` swaps the readers, Moira,
     speech and notifications for their deterministic stand-ins, the same
     ones the journeys have used since blocks 106/111/125.

What it is not. It is not a sandbox for the browser: Playwright's own
watch on off-origin requests (tests/journeys/lib.js) covers that side. It
does not scrub the environment — the point is to prove that a key present
in the environment cannot switch a test live, so the key is left alone and
the refusal is asserted.

Import order matters: this module must be imported before any provider
module. wordicon_cli imports it first, so anything that imports
wordicon_cli (the server, the journeys' scratch server, the suite) is
covered from its first line. `.env` is never read in test mode — a real key
in the file must not enter a test process."""
from __future__ import annotations

import json
import os
import socket
import sys
import threading
import time
import traceback
from pathlib import Path

ENV = "WORDICON_TEST_MODE"
ALLOW_ENV = "WORDICON_TEST_ALLOW_PORTS"
LOG_ENV = "WORDICON_TEST_EGRESS_LOG"
REAL_APP_PORTS_ENV = "WORDICON_TEST_DENY_PORTS"
DEFAULT_REAL_APP_PORT = 8420

_TRUTHY = ("1", "true", "yes", "on")


def active() -> bool:
    return os.environ.get(ENV, "").strip().lower() in _TRUTHY


class EgressDenied(OSError):
    """An outbound connection the test environment refused. It is an
    OSError so every HTTP client (urllib, requests, httpx, the provider
    SDK) reports it as the connection failure it is."""


class TestModeViolation(RuntimeError):
    """Something a test process must never do (construct a provider
    gateway, serve the real store) was attempted."""


_lock = threading.Lock()
_allowed_ports: set[int] = set()
_installed = False
_denied: list[dict] = []          # in-process record, capped
_DENIED_CAP = 500
_original = {}


def _real_app_ports() -> set[int]:
    out = {DEFAULT_REAL_APP_PORT}
    p = os.environ.get("PORT")
    if p and p.isdigit():
        out.add(int(p))
    for tok in os.environ.get(REAL_APP_PORTS_ENV, "").split(","):
        tok = tok.strip()
        if tok.isdigit():
            out.add(int(tok))
    return out


def allow_port(port: int) -> None:
    """Tell the guard about a loopback fixture (the scratch server, a mock
    producer, an ad-hoc test server). The real application's port is never
    allowed, whatever is asked."""
    port = int(port)
    if port in _real_app_ports():
        raise TestModeViolation(f"port {port} is the real application's port; a test may not talk to it")
    with _lock:
        _allowed_ports.add(port)


def allowed_ports() -> set[int]:
    with _lock:
        return set(_allowed_ports)


def _loopback(host) -> bool:
    if host is None:
        return True
    h = str(host).strip().lower()
    if h in ("localhost", "::1", "0.0.0.0", "::", ""):
        return True
    return h.startswith("127.")


def _log_path() -> Path:
    p = os.environ.get(LOG_ENV)
    if p:
        return Path(p)
    import tempfile
    return Path(tempfile.gettempdir()) / "wordicon_test_egress_denied.jsonl"


def _frames() -> list[str]:
    out = []
    for fr in reversed(traceback.extract_stack(limit=14)):
        if fr.filename.endswith("testmode.py"):
            continue
        out.append(f"{os.path.basename(fr.filename)}:{fr.lineno} in {fr.name}")
        if len(out) >= 4:
            break
    return out


def _deny(kind: str, host, port) -> EgressDenied:
    rec = {"at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()), "kind": kind,
           "host": str(host)[:120], "port": port, "where": _frames()}
    with _lock:
        if len(_denied) < _DENIED_CAP:
            _denied.append(rec)
    try:
        with _log_path().open("a", encoding="utf-8") as f:
            f.write(json.dumps(rec) + "\n")
    except OSError:
        pass
    return EgressDenied(f"test mode refused {kind} to {host}:{port} — nothing left this process")


def denied() -> list[dict]:
    with _lock:
        return list(_denied)


def _check_address(kind: str, address) -> None:
    # AF_UNIX: a path — local by construction
    if isinstance(address, (str, bytes)):
        return
    if not isinstance(address, tuple) or len(address) < 2:
        return
    host, port = address[0], address[1]
    try:
        port = int(port)
    except (TypeError, ValueError):
        raise _deny(kind, host, port)
    if not _loopback(host):
        raise _deny(kind, host, port)
    if port in _real_app_ports():
        raise _deny(kind + " (real application port)", host, port)
    with _lock:
        ok = port in _allowed_ports
    if not ok:
        raise _deny(kind + " (port not allowed)", host, port)


def install() -> None:
    """Install the socket guard once. Idempotent."""
    global _installed
    with _lock:
        if _installed:
            return
        _installed = True
    for tok in os.environ.get(ALLOW_ENV, "").split(","):
        tok = tok.strip()
        if tok.isdigit():
            _allowed_ports.add(int(tok))
    jp = os.environ.get("JOURNEY_PORT")
    if jp and jp.isdigit():
        _allowed_ports.add(int(jp))
    _allowed_ports.difference_update(_real_app_ports())

    _original["connect"] = socket.socket.connect
    _original["connect_ex"] = socket.socket.connect_ex
    _original["sendto"] = socket.socket.sendto
    _original["getaddrinfo"] = socket.getaddrinfo

    def connect(self, address):
        _check_address("connect", address)
        return _original["connect"](self, address)

    def connect_ex(self, address):
        _check_address("connect", address)
        return _original["connect_ex"](self, address)

    def sendto(self, data, *rest):
        address = rest[-1] if rest else None
        if address is not None:
            _check_address("sendto", address)
        return _original["sendto"](self, data, *rest)

    def getaddrinfo(host, port, *a, **k):
        if not _loopback(host):
            raise _deny("resolve", host, port)
        return _original["getaddrinfo"](host, port, *a, **k)

    socket.socket.connect = connect
    socket.socket.connect_ex = connect_ex
    socket.socket.sendto = sendto
    socket.getaddrinfo = getaddrinfo


def poisoned_http_client():
    """An httpx client whose transport refuses every request. In test mode
    the provider gateway is built on this, so the class can be constructed
    (the attempt-loop checks need a real gateway object to drive with a
    mock transport) but cannot send: a call through it is refused and
    logged exactly like a refused socket."""
    # The SDK names the httpx it was built against (httpx2 in the pinned
    # 1.x line, httpx in older ones); the refusing transport must be that one.
    import anthropic._base_client as _bc
    hx = getattr(_bc, "httpx2", None) or getattr(_bc, "httpx", None)
    if hx is None:
        import httpx as hx

    class _Refusing(hx.BaseTransport):
        def handle_request(self, request):
            raise _deny("http", request.url.host, request.url.port or (443 if request.url.scheme == "https" else 80))

    return hx.Client(transport=_Refusing())


def assert_isolated(state_root, repo_root) -> None:
    """A test process may not serve the repository's own local_state."""
    if not active():
        return
    real = Path(repo_root).resolve() / "local_state"
    got = Path(state_root).resolve()
    if got == real or real in got.parents:
        raise TestModeViolation(f"test mode refuses to run on the real store {real} — "
                                f"set WORDICON_STATE to a scratch directory")


def harden(server_module) -> dict:
    """Swap every model-shaped dependency of the server for its
    deterministic stand-in. Returns what was replaced, for the log."""
    import wordicon_cli as cli
    replaced = {}
    server_module.READER_GATEWAY = cli.MockReader()
    replaced["READER_GATEWAY"] = "MockReader"
    try:
        import moira
        server_module.MOIRA_GATEWAY_FACTORY = moira.mock_gateway_for
        replaced["MOIRA_GATEWAY_FACTORY"] = "moira.mock_gateway_for"
    except ImportError:
        pass
    try:
        import speech
        speech.ENGINE = speech.MockEngine()
        replaced["speech.ENGINE"] = "MockEngine"
    except ImportError:
        pass
    replaced["notify"] = "off (test mode)"
    return replaced


def status() -> dict:
    return {"active": active(), "installed": _installed, "allowed_ports": sorted(allowed_ports()),
            "real_app_ports": sorted(_real_app_ports()), "denied": len(_denied), "log": str(_log_path())}


if active():
    install()
