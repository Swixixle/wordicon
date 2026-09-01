#!/usr/bin/env python3
"""
Wordicon web server — the same forge/crack loop as scripts/wordicon_cli.py,
reachable from a phone browser instead of a terminal.

This is deliberately thin: it imports and reuses everything from
scripts/wordicon_cli.py (seed corpus loading, prompt construction, Bone
validation, judgment/receipt persistence) rather than reimplementing any of
it. The only new code here is the HTTP layer.

Run it:
  python3 server.py
Then on your phone, on the same Wi-Fi as this computer, open:
  http://<this-computer's-local-IP>:8420
and use Safari's Share -> Add to Home Screen to make it a full-screen icon.

Gateway is chosen server-side, never from the phone: if ANTHROPIC_API_KEY is
set in this process's environment, real model calls are used (model name
from WORDICON_MODEL, required in that case); otherwise it falls back to the
mock gateway automatically. The API key never travels to the browser.
"""
from __future__ import annotations

import hashlib
import json
import os
import pathlib
import re
import sys
import threading
import time
import traceback
import uuid
from datetime import datetime, timezone
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent
sys.path.insert(0, str(REPO_ROOT / "scripts"))
sys.path.insert(0, str(REPO_ROOT / "src"))


def _load_dotenv() -> None:
    """Read .env into the environment before anything else reads it.

    Flask can do this via python-dotenv, but only inside app.run() — which
    is the LAST line of this file, so everything checked at import or in
    the startup banner (notify config, the gateway report) would still see
    an empty environment and print something false. Doing it here, first,
    means one answer for the whole process. Also means the API key never
    has to be typed into a shell, where it lands in history in plaintext.

    Deliberately dependency-free: KEY=value, # comments, optional quotes,
    and a real environment variable always wins over the file."""
    path = REPO_ROOT / ".env"
    if not path.exists():
        return
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, _, value = line.partition("=")
        key, value = key.strip(), value.strip().strip('"').strip("'")
        if key and key not in os.environ:   # never override a real export
            os.environ[key] = value


_load_dotenv()

from flask import Flask, Response, g, jsonify, redirect, request, send_from_directory  # noqa: E402

import wordicon_cli as cli  # noqa: E402
import library as library  # noqa: E402  (the Library wing — zero model calls)
import gate  # noqa: E402
import vault  # noqa: E402  (encrypted backup — the corpus-writers lock lives there)
import notify  # noqa: E402
import keeper  # noqa: E402  (the Book's narrator — summoned only, never scheduled)
from wordicon_corpus.objects import Judgment  # noqa: E402

WEBAPP_DIR = REPO_ROOT / "webapp"

app = Flask(__name__, static_folder=str(WEBAPP_DIR), static_url_path="")

# ---------------------------------------------------------------------------
# The access gate (hardening pass, owner's go 2026-08-29). DEFAULT-DENY:
# every route — corpus reads, media streaming (Range included), exports,
# mutations, model-spending lanes, and the static file server itself — is
# closed to an unpaired client. The allowlist below is the ENTIRE public
# surface: the pairing page, the pairing POST, and the PWA's manifest and
# icons (no corpus in any of them). Unpaired API calls get an explicit 401
# JSON; unpaired browsers get the pairing screen, never an empty Wordicon.
# This is a home-LAN access gate, NOT encrypted transport: traffic is plain
# HTTP, so on shared or hostile Wi-Fi the gate keeps strangers off the
# routes but does not hide the bytes.

_GATE_PUBLIC = {"/pair", "/api/pair", "/manifest.json"}


def _gate_session():
    return gate.verify(request.cookies.get(gate.SESSION_COOKIE, ""))


@app.before_request
def _gate_check():
    path = request.path
    if path in _GATE_PUBLIC or path.startswith("/icons/"):
        return None
    sess = _gate_session()
    if sess is not None:
        # paired — but still refuse cross-site state changes outright
        if request.method not in ("GET", "HEAD", "OPTIONS"):
            origin = request.headers.get("Origin", "")
            if origin:
                host = origin.split("://", 1)[-1].split("/", 1)[0]
                if host != request.host:
                    return jsonify({"error": "cross-site request refused"}), 403
            # every mutating request holds the corpus-writers lock for its
            # whole life (released in _vault_release), so a vault staging
            # copy never catches a half-written file. Dirty is marked on
            # the way IN — conservative: a failed mutation may cost one
            # extra backup, a missed mark could cost real work.
            vault.acquire_corpus_write()
            g._corpus_shared = True
            vault.mark_dirty()
        return None
    if path.startswith("/api/"):
        return jsonify({"error": "not paired — this Wordicon only answers "
                                  "devices its owner has paired. POST the "
                                  "pairing code from the server terminal to "
                                  "/api/pair."}), 401
    return redirect("/pair")


@app.teardown_request
def _vault_release(exc):
    if g.pop("_corpus_shared", False):
        vault.release_corpus_write()


@app.route("/pair")
def pair_page():
    """Self-contained: the pairing form for a stranger, the device manager
    for a paired owner. No corpus content either way."""
    paired = _gate_session() is not None
    manage = ""
    if paired:
        rows = "".join(
            f"<div class='dev'>{d['device']} · {d['created_at'][:10]}"
            + (" · <b>revoked</b>" if d["revoked"] else
               f" <button onclick=\"revoke('{d['session_id']}')\">revoke</button>")
            + "</div>" for d in gate.devices())
        manage = ("<h2>Paired devices</h2>" + (rows or "<div class='dev'>none</div>")
                  + "<p class='note'>Revoking a device signs it out everywhere, "
                  "immediately and append-only. Rotating the master secret "
                  "(<code>python3 server.py --rotate-secret</code>, then restart) "
                  "signs out every device at once.</p>"
                  "<p><a href='/' style='color:#8cc8ff'>back to Wordicon</a></p>")
    return f"""<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Wordicon — pair this device</title><style>
body {{ background:#11161d; color:#e7ecf3; font-family:-apple-system,system-ui,sans-serif;
  display:flex; justify-content:center; padding:12vh 20px 40px; }}
.card {{ max-width:430px; }}
h1 {{ font-size:20px; }} h2 {{ font-size:15px; margin-top:28px; }}
input {{ background:#1f2833; color:#e7ecf3; border:1px solid #2a3441; border-radius:10px;
  padding:12px 14px; font-size:18px; width:100%; box-sizing:border-box; letter-spacing:2px; }}
button {{ background:#1f2833; color:#8cc8ff; border:1px solid #8cc8ff; border-radius:10px;
  padding:10px 18px; font-size:15px; margin-top:10px; cursor:pointer; }}
.note {{ color:#8a94a3; font-size:13px; line-height:1.5; }}
.dev {{ border-top:1px solid #2a3441; padding:8px 0; font-size:14px; }}
.dev button {{ font-size:12px; padding:3px 10px; margin:0 0 0 8px; }}
#err {{ color:#e08a8a; font-size:14px; min-height:20px; }}</style></head><body>
<div class="card"><h1>Pair this device with Wordicon</h1>
<p class="note">This Wordicon answers only devices its owner has paired.
The pairing code is printed in the terminal window where the server is
running — it never travels in a link. Type it here once; this device stays
paired until revoked.</p>
<input id="code" placeholder="000-000-000" autocomplete="one-time-code" inputmode="numeric">
<div id="err"></div>
<button onclick="pair()">Pair — the code stays out of the URL</button>
<p class="note">Honest boundary: this is a home-LAN access gate, not
encrypted transport. Traffic is plain HTTP — fine on your own Wi-Fi,
not confidential on shared or hospital networks.</p>
{manage}</div>
<script>
async function pair() {{
  const r = await fetch('/api/pair', {{ method:'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{ code: document.getElementById('code').value.trim(),
                            device: navigator.platform || 'device' }}) }});
  if (r.ok) {{ location.href = '/'; return; }}
  const d = await r.json().catch(() => ({{}}));
  document.getElementById('err').textContent = d.error || 'that code was not accepted';
}}
async function revoke(id) {{
  await fetch('/api/auth/revoke', {{ method:'POST',
    headers: {{'Content-Type':'application/json'}},
    body: JSON.stringify({{ session_id: id }}) }});
  location.reload();
}}
</script></body></html>"""


@app.route("/api/pair", methods=["POST"])
def api_pair():
    data = request.get_json(force=True, silent=True) or {}
    got = gate.pair(str(data.get("code") or ""),
                    device=str(data.get("device") or ""))
    if got is None:
        return jsonify({"error": "wrong or expired code — read the current "
                                  "one off the server terminal (a fresh code "
                                  "is printed at every start)"}), 401
    resp = jsonify({"paired": True, "device": got["device"],
                     "session_id": got["session_id"]})
    resp.set_cookie(gate.SESSION_COOKIE, got["token"],
                    max_age=gate.SESSION_DAYS * 86400, httponly=True,
                    samesite="Strict", path="/")
    return resp


@app.route("/api/auth/devices")
def api_auth_devices():
    return jsonify({"devices": gate.devices()})


@app.route("/api/auth/revoke", methods=["POST"])
def api_auth_revoke():
    data = request.get_json(force=True) or {}
    if not gate.revoke(str(data.get("session_id") or "")):
        return jsonify({"error": "no such session"}), 400
    return jsonify({"revoked": True})


@app.route("/api/vault/status")
def api_vault_status():
    """Gated like everything else. A failing or stale vault is data the
    owner must see — the page's strip renders this, red when it matters."""
    return jsonify(vault.status())


# ---- the Keeper -------------------------------------------------------
#
# Summoned only. No scheduler, hook, or boot path references a close;
# with the Keeper inactive, an ordinary run performs zero keeper reads,
# writes, or model calls, and this server never creates local_state/keeper
# on its own — activation does. All routes sit behind the gate like
# everything else. A close narrates in a background thread (a model call
# should never ride a phone's HTTP request), holding the corpus-writers
# lock exactly as jobs do so a vault staging copy never catches a
# half-written keeper file.

_KEEPER_BUSY = threading.Lock()
_KEEPER_LAST_ERROR = {"error": ""}


def _keeper_narrate(fn, *args):
    def body():
        try:
            with vault.corpus_write():
                try:
                    _KEEPER_LAST_ERROR["error"] = ""
                    fn(*args)
                finally:
                    vault.mark_dirty()
        except Exception as e:
            traceback.print_exc()
            _KEEPER_LAST_ERROR["error"] = str(e)
        finally:
            _KEEPER_BUSY.release()
    threading.Thread(target=body, daemon=True).start()


@app.route("/api/keeper/status")
def api_keeper_status():
    st = keeper.status()
    st["narrating"] = _KEEPER_BUSY.locked()
    st["last_error"] = _KEEPER_LAST_ERROR["error"]
    return jsonify(st)


@app.route("/api/keeper/activate", methods=["POST"])
def api_keeper_activate():
    data = request.get_json(force=True) or {}
    try:
        return jsonify(keeper.activate(str(data.get("name") or ""),
                                       str(data.get("title") or ""),
                                       str(data.get("naming_receipt") or "")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/keeper/deactivate", methods=["POST"])
def api_keeper_deactivate():
    try:
        return jsonify(keeper.deactivate())
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/keeper/close", methods=["POST"])
def api_keeper_close():
    if not keeper.active():
        return jsonify({"error": "the Keeper is not active — the Book has "
                                  "no one to close it"}), 400
    if not _KEEPER_BUSY.acquire(blocking=False):
        return jsonify({"error": "the Book is already being closed"}), 409
    _keeper_narrate(keeper.close, server_gateway())
    return jsonify({"narrating": True})


@app.route("/api/keeper/retry", methods=["POST"])
def api_keeper_retry():
    data = request.get_json(force=True) or {}
    close_id = str(data.get("close_id") or "")
    if not _KEEPER_BUSY.acquire(blocking=False):
        return jsonify({"error": "the Book is already being closed"}), 409
    _keeper_narrate(keeper.retry, close_id, server_gateway())
    return jsonify({"narrating": True})


@app.route("/api/keeper/renarrate", methods=["POST"])
def api_keeper_renarrate():
    data = request.get_json(force=True) or {}
    close_id = str(data.get("close_id") or "")
    if not _KEEPER_BUSY.acquire(blocking=False):
        return jsonify({"error": "the Book is already being closed"}), 409
    _keeper_narrate(keeper.renarrate, close_id, server_gateway())
    return jsonify({"narrating": True})


@app.route("/api/keeper/entries")
def api_keeper_entries():
    entries = keeper._rows(keeper.entries_path())
    rulings = keeper._active_rulings()
    for e in entries:
        j = rulings.get(e["entry_id"])
        e["ruling"] = ({"ruling": j.get("ruling"), "why": j.get("why"),
                        "revision_text": j.get("revision_text"),
                        "at": j.get("at")} if j else None)
    closes = keeper._rows(keeper.closes_path())
    attempts = keeper._rows(keeper.attempts_path())
    entry_closes = {e["close_id"] for e in entries}
    failed = [c["close_id"] for c in closes
              if c["close_id"] not in entry_closes]
    return jsonify({"entries": list(reversed(entries))[:8],
                    "failed_closes": failed[-3:],
                    "attempts": len(attempts)})


@app.route("/api/keeper/rule", methods=["POST"])
def api_keeper_rule():
    data = request.get_json(force=True) or {}
    try:
        return jsonify(keeper.rule(str(data.get("entry_id") or ""),
                                   str(data.get("ruling") or ""),
                                   str(data.get("why") or ""),
                                   str(data.get("revision_text") or "")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400


@app.route("/api/keeper/review", methods=["POST"])
def api_keeper_review():
    """Records the cold review that lifts an adaptation freeze. The
    review's substance is the owner's own re-reading and re-ruling of the
    recent entries; this endpoint records that it happened, over the last
    DRILL_LOOKBACK entries, and ratifies the watermark. A freeze with no
    unfreeze would be a trap, not a discipline."""
    data = request.get_json(force=True) or {}
    recent = [e["entry_id"] for e in
              keeper._rows(keeper.entries_path())[-keeper.DRILL_LOOKBACK:]]
    return jsonify(keeper.record_review(recent,
                                        str(data.get("notes") or "")))

# ---- jobs -------------------------------------------------------------
#
# Every Forge/Crack/Decompose run is a job from the moment it's submitted,
# not something bolted onto a synchronous request later. The HTTP request
# that submits a job returns almost immediately with a job id; the actual
# pipeline runs in a background thread, independent of whether the phone
# that submitted it is still connected. This matters for two separate
# reasons, not one: it's what lets you close the app and get notified when
# it's done, and independently, it's what keeps a slow Decompose from dying
# when iOS suspends a backgrounded tab's pending fetch — a synchronous
# multi-minute request was never going to survive that regardless of
# notifications.
#
# In-memory, not a real queue — this is a single-user local server, one
# process, and jobs don't need to survive a server restart. If you restart
# the server mid-job, that job is gone; its receipt only exists if the
# pipeline got far enough to persist one before the process died.

JOBS: dict[str, dict] = {}
JOBS_LOCK = threading.Lock()


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _new_job_id() -> str:
    return "job_" + hashlib.sha256(f"{time.time()}{threading.get_ident()}".encode()).hexdigest()[:12]


def _update_job(job_id: str, **fields) -> None:
    with JOBS_LOCK:
        if job_id in JOBS:
            JOBS[job_id].update(fields)
            JOBS[job_id]["updated_at"] = _now_iso()


def _shape_candidates(result: dict) -> list[dict]:
    return [
        {
            "title": r["bff"]["title"],
            "bone_flesh_friction": r["bff"],
            "claims_detail": r["claims_detail"],
        }
        for r in result["candidates"]
    ]


def _shape_operation_result(mode: str, gateway_name: str, cli_result) -> dict:
    """Same response shape the old synchronous /api/run returned — kept
    identical so the frontend's rendering code didn't need to change,
    only how it gets the result."""
    if mode == "decompose":
        groups = []
        for g in cli_result["groups"]:
            base = {
                "label": g["label"],
                "gist": g["gist"],
                "grounding": g.get("grounding", ""),
                "anchor": g.get("anchor", ""),
                "anchor_verified": g.get("anchor_verified", False),
                "anchor_near_miss": g.get("anchor_near_miss", False),
                "recurrence_unsupported": g.get("recurrence_unsupported", False),
                "constraint_beyond_anchor": g.get("constraint_beyond_anchor") or [],
                "source_check": g.get("source_check") or {},
                "constraints": g.get("constraints", ""),
                "background": g.get("background", ""),
                "stance": g.get("stance", ""),
            }
            if g.get("failed"):
                # Soft-failed concept: no result to shape — carry the exact
                # forge packet so the UI can retry just this one.
                base.update({"failed": True, "error": g.get("error", ""),
                             "failure_explanation": g.get("failure_explanation", ""),
                             "forge_input": g.get("forge_input", "")})
                groups.append(base)
                continue
            result = g["result"]
            receipt = result["private_receipt"]
            base.update({
                "trace_id": result["trace_id"],
                "candidates": _shape_candidates(result),
                "receipt_id": receipt["receipt_id"],
                "summary": cli.summary_line(receipt, result["candidates"]),
                "metrics": result.get("metrics", {}),
            })
            groups.append(base)
        return {"mode": "decompose", "source_text": cli_result["source_text"],
                "global_constraints": cli_result.get("global_constraints", ""),
                "uncovered": cli_result.get("uncovered", []),
                "partial": cli_result.get("partial", False),
                "n_failed": cli_result.get("n_failed", 0),
                "groups": groups, "gateway": gateway_name}

    receipt = cli_result["private_receipt"]
    return {
        "mode": mode,
        "trace_id": cli_result["trace_id"],
        "candidates": _shape_candidates(cli_result),
        "receipt_id": receipt["receipt_id"],
        "summary": cli.summary_line(receipt, cli_result["candidates"]),
        "metrics": cli_result.get("metrics", {}),
        "gateway": gateway_name,
    }


def _run_job(job_id: str, mode: str, input_text: str) -> None:
    """Background jobs persist receipts and results mid-run, interleaved
    with model calls inside cli — so the WHOLE body holds the shared side
    of the corpus-writers lock, and a vault staging copy waits for the job
    rather than tar a half-written receipt. Dirty is marked when the job
    ends, so the quiet-debounce clock starts after the work, not during."""
    with vault.corpus_write():
        try:
            _run_job_body(job_id, mode, input_text)
        finally:
            vault.mark_dirty()


def _run_job_body(job_id: str, mode: str, input_text: str) -> None:
    def on_progress(stage: str, detail: str) -> None:
        # stage_changed_at lets the UI show how long the CURRENT step has
        # been running — a stalled API call then looks like a stall
        # ("92s on this step") instead of looking identical to work.
        _update_job(job_id, status=stage, progress=detail,
                    stage_changed_at=time.time())

    try:
        gateway = server_gateway()
    except Exception as e:
        # The full traceback goes to the terminal — a bare str(e) here once
        # cost an hour of blind theorizing (the brew-python truststore
        # incident, 2026-09-01). The job still carries the plain sentence.
        traceback.print_exc()
        _update_job(job_id, status="failed", error=str(e))
        with JOBS_LOCK:
            notify.notify_job_complete(dict(JOBS[job_id]))
        return

    with JOBS_LOCK:
        avoid_titles = JOBS[job_id].get("avoid_titles") or []
        prior_attempts = JOBS[job_id].get("prior_attempts") or []

    try:
        if mode == "deep":
            with JOBS_LOCK:
                _gesture = JOBS[job_id].get("gesture") or "trial"
            cli_result = cli.run_deep(input_text, gateway, interactive=False, on_progress=on_progress,
                                        avoid_titles=avoid_titles, prior_attempts=prior_attempts,
                                        gesture=_gesture)
            groups = []
            for g in cli_result["groups"]:
                deep_common = {
                    "grounding": g.get("grounding", ""),
                    "anchor": g.get("anchor", ""),
                    "anchor_verified": g.get("anchor_verified", False),
                    "anchor_near_miss": g.get("anchor_near_miss", False),
                    "recurrence_unsupported": g.get("recurrence_unsupported", False),
                "constraint_beyond_anchor": g.get("constraint_beyond_anchor") or [],
                "source_check": g.get("source_check") or {},
                    "background": g.get("background", ""),
                }
                if g.get("failed"):
                    groups.append({
                        "label": g["label"], "gist": g["gist"],
                        "neighbors": g.get("neighbors", ""), "constraints": g.get("constraints", ""),
                        **deep_common,
                        "failed": True, "error": g.get("error", ""),
                        "failure_explanation": g.get("failure_explanation", ""),
                        "forge_input": g.get("forge_input", ""),
                    })
                    continue
                result = g["result"]
                receipt = result["private_receipt"]
                groups.append({
                    "label": g["label"], "gist": g["gist"],
                    "neighbors": g.get("neighbors", ""), "constraints": g.get("constraints", ""),
                    **deep_common,
                    "trace_id": result["trace_id"],
                    "candidates": _shape_candidates(result),
                    "receipt_id": receipt["receipt_id"],
                    "summary": cli.summary_line(receipt, result["candidates"]),
                    "metrics": result.get("metrics", {}),
                })
            result = {"mode": "deep", "source_text": cli_result["source_text"],
                       "attack": cli_result["attack"],
                       "gesture": cli_result.get("gesture", "trial"),
                       "partial": cli_result.get("partial", False),
                       "n_failed": cli_result.get("n_failed", 0),
                       "groups": groups, "gateway": gateway.name}
        elif mode == "decompose":
            cli_result = cli.run_decompose(input_text, gateway, interactive=False, on_progress=on_progress,
                                             avoid_titles=avoid_titles, prior_attempts=prior_attempts)
            result = _shape_operation_result(mode, gateway.name, cli_result)
        elif mode == "sprout":
            with JOBS_LOCK:
                original = JOBS[job_id].get("original") or {}
                parent_trace = JOBS[job_id].get("parent_trace_id")
                via = JOBS[job_id].get("via")
                parent_door_id = JOBS[job_id].get("parent_door_id")
            result = cli.run_sprout(original, gateway, on_progress=on_progress,
                                     parent_trace_id=parent_trace, via=via,
                                     parent_door_id=parent_door_id)
            result["gateway"] = gateway.name
        elif mode == "refract":
            with JOBS_LOCK:
                original = JOBS[job_id].get("original") or {}
                known_neighbors = JOBS[job_id].get("known_neighbors")
            result = cli.run_refract(original, gateway, on_progress=on_progress,
                                      known_neighbors=known_neighbors)
            result["gateway"] = gateway.name
        elif mode == "archetype":
            with JOBS_LOCK:
                original = JOBS[job_id].get("original") or {}
            result = cli.run_archetype(original, gateway, on_progress=on_progress)
            result["gateway"] = gateway.name
        elif mode == "etymon":
            with JOBS_LOCK:
                word = JOBS[job_id].get("input_text") or ""
            result = cli.run_etymon(word, gateway, on_progress=on_progress)
            result["gateway"] = gateway.name
        elif mode == "recheck":
            with JOBS_LOCK:
                original = JOBS[job_id].get("original") or {}
            result = cli.run_recheck(original, gateway, on_progress=on_progress)
            result["gateway"] = gateway.name
        elif mode == "verify":
            with JOBS_LOCK:
                verify_candidate = JOBS[job_id].get("verify_candidate") or {}
            result = cli.run_verify(verify_candidate, gateway, on_progress=on_progress)
            result["gateway"] = gateway.name
        elif mode == "revise":
            with JOBS_LOCK:
                original = JOBS[job_id].get("original") or {}
                claims_detail = JOBS[job_id].get("claims_detail") or []
                owner_note = JOBS[job_id].get("owner_note")
                prior_friction = JOBS[job_id].get("prior_friction")
                wordify = bool(JOBS[job_id].get("wordify"))
            cli_result = cli.run_revise(original, gateway, claims_detail=claims_detail,
                                          on_progress=on_progress, owner_note=owner_note,
                                          friction=prior_friction, wordify=wordify)
            receipt = cli_result["private_receipt"]
            result = {
                "mode": "revise",
                "revised_from": cli_result["revised_from"],
                "trace_id": cli_result["trace_id"],
                "candidates": _shape_candidates(cli_result),
                "receipt_id": receipt["receipt_id"],
                "summary": cli.summary_line(receipt, cli_result["candidates"]),
                "gateway": gateway.name,
            }
        else:
            with JOBS_LOCK:
                r_anchor = JOBS[job_id].get("retry_anchor")
                r_stance = JOBS[job_id].get("retry_stance")
                r_match = JOBS[job_id].get("retry_match_text")
            cli_result = cli.run(mode, input_text, gateway, interactive=False, on_progress=on_progress,
                                  avoid_titles=avoid_titles, prior_attempts=prior_attempts,
                                  anchor=r_anchor, stance=r_stance, match_text=r_match)
            result = _shape_operation_result(mode, gateway.name, cli_result)
        _update_job(job_id, status="complete", result=result)
    except Exception as e:
        traceback.print_exc()
        _update_job(job_id, status="failed", error=str(e))

    with JOBS_LOCK:
        notify.notify_job_complete(dict(JOBS[job_id]))


def server_gateway() -> cli.Gateway:
    """Decided once per request from server-side environment only — the
    phone never sends or sees a key."""
    if os.environ.get("ANTHROPIC_API_KEY"):
        model = os.environ.get("WORDICON_MODEL")
        if not model:
            raise RuntimeError(
                "ANTHROPIC_API_KEY is set but WORDICON_MODEL is not — set both, "
                "e.g. export WORDICON_MODEL=claude-sonnet-4-5-20250929, or unset "
                "ANTHROPIC_API_KEY to use the mock gateway."
            )
        return cli.make_gateway("anthropic", model)
    return cli.make_gateway("mock", None)


@app.route("/")
def index():
    return send_from_directory(WEBAPP_DIR, "index.html")


@app.route("/manifest.json")
def manifest():
    return send_from_directory(WEBAPP_DIR, "manifest.json")


@app.route("/overworld/map")
def overworld_map_page():
    """The original spatial map, kept unchanged. It draws everything at
    once, which is why it needs a camera; /overworld now defaults to the
    list that doesn't."""
    return send_from_directory(WEBAPP_DIR, "overworld.html")


@app.route("/api/trails")
def api_trails():
    return jsonify(cli.build_trails())


@app.route("/api/warp", methods=["POST"])
def api_warp():
    """Record one jump the OWNER made. The client supplies what was on
    screen and for how long; the CLI decides whether that counts, and says
    why when it doesn't. Refusals come back 200 with recorded:false — a
    jump that didn't qualify is not an error, and turning it into one would
    put an alarm on the page every time the owner scrolled the archive."""
    b = request.get_json(silent=True) or {}
    out = cli.record_warp(
        from_trace=b.get("from_trace", ""), from_label=b.get("from_label", ""),
        to_trace=b.get("to_trace", ""), to_label=b.get("to_label", ""),
        shelf=b.get("shelf", ""), dwell_s=b.get("dwell_s", 0))
    return jsonify(out)


@app.route("/api/warp/note", methods=["POST"])
def api_warp_note():
    """The owner's own sentence about a jump. There is no model in this
    path, and no other path writes to this file."""
    b = request.get_json(silent=True) or {}
    out = cli.record_warp_note(b.get("warp_id", ""), b.get("note", ""))
    return (jsonify(out), 200 if out.get("ok") else 400)


@app.route("/api/warps")
def api_warps():
    warps = cli.load_warps()
    return jsonify({"warps": warps, "count": len(warps),
                    "min_dwell_s": cli.WARP_MIN_DWELL_S})


@app.route("/overworld")
@app.route("/trails")
def overworld_page():
    return send_from_directory(WEBAPP_DIR, "trails.html")


@app.route("/api/overworld")
def api_overworld():
    """The map's data: chronological runs, recorded + snapshot-synthesized
    edges, and the two computed overlays (recurrence, disputes). Assembled
    fresh from disk on every request — the map is a view of the corpus,
    never a second copy of it that could drift."""
    return jsonify(cli.build_overworld())


# "Map" is the label now; Overworld the label is dead, the old URLs live on
# for bookmarks. /map = the trails list (same default as /overworld),
# /map/world = the spatial map, where the Wayfinder lives.
@app.route("/map")
def map_page():
    return send_from_directory(WEBAPP_DIR, "trails.html")


@app.route("/map/world")
def map_world_page():
    return send_from_directory(WEBAPP_DIR, "overworld.html")


def _map_nodes():
    """label→node and the key set, for validating roads against what the
    map actually contains."""
    ow = cli.build_overworld()
    label_to_key, keys = {}, set()
    for r in ow["runs"]:
        for it in r["items"]:
            keys.add(it["key"])
            norm = cli._norm_title(it["label"])
            hit = label_to_key.get(norm)
            if hit is None:
                label_to_key[norm] = {"key": it["key"], "label": it["label"],
                                       "kind": it["kind"]}
            elif hit.get("key") != it["key"]:
                # Two different nodes share this title. The old setdefault
                # silently kept the first — the exact coin-flip the
                # identity law forbids. The ambiguity is recorded as a
                # fact; consumers must ask, never choose.
                hit["ambiguous"] = True
                hit.setdefault("candidates", [
                    {"key": hit["key"], "label": hit["label"],
                     "kind": hit["kind"]}])
                hit["candidates"].append(
                    {"key": it["key"], "label": it["label"],
                     "kind": it["kind"]})
    return label_to_key, keys


@app.route("/api/map/roads/suggest", methods=["POST"])
def api_map_suggest_roads():
    """Resonance/Friction route strategies: a model PROPOSES roads; every
    proposal is checked in code against the actual map (an endpoint that
    isn't on the map is dropped with a finding); nothing is persisted here.
    The proposals are session material until the owner ratifies one via
    /api/map/road."""
    data = request.get_json(force=True) or {}
    from_l = str(data.get("from") or "").strip()[:160]
    to_l = str(data.get("to") or "").strip()[:160]
    kind = str(data.get("kind") or "").strip().lower()
    if kind not in cli.ROAD_KINDS:
        return jsonify({"error": "kind must be resonance or friction"}), 400
    if not from_l or not to_l:
        return jsonify({"error": "both ends of the journey are required"}), 400
    label_to_key, _ = _map_nodes()
    _amb = []
    for _l in (from_l, to_l):
        _hit = label_to_key.get(cli._norm_title(_l))
        if isinstance(_hit, dict) and _hit.get("ambiguous"):
            _amb.append({"label": _l,
                         "candidates": _hit.get("candidates") or []})
    if _amb:
        # The identity law: a typed title resolving to multiple concepts
        # is a QUESTION, never a coin flip. The UI shows the candidates
        # and the owner says which one he means.
        return jsonify({"ambiguous": _amb, "roads": [],
                        "findings": ["That title names more than one "
                                      "concept on this map — say which "
                                      "one you mean."]})
    defs = {}
    for c in cli.load_accepted_concepts():
        defs[cli._norm_title(c.get("name") or c.get("title") or "")] = \
            (c.get("definition") or "")[:400]
    try:
        result = cli.run_suggest_roads(
            from_l, to_l, defs.get(cli._norm_title(from_l), ""),
            defs.get(cli._norm_title(to_l), ""), kind, label_to_key,
            server_gateway())
    except Exception as e:
        return jsonify({"error": cli.explain_component_failure(str(e))}), 500
    return jsonify(result)


@app.route("/api/map/road", methods=["POST"])
def api_map_declare_road():
    """The owner declares a road — append-only into the same edge log every
    recorded road uses, marked owner_declared. This is the ratification
    step for inferred roads and the direct path for roads the owner simply
    knows exist. Origin is retained: a ratified proposal keeps proposed_by
    = model with its proposal run's trace_id; declaration never erases
    where a road came from."""
    data = request.get_json(force=True) or {}
    a, b = data.get("a") or {}, data.get("b") or {}
    if not isinstance(a, dict) or not isinstance(b, dict):
        return jsonify({"error": "a and b must be map nodes"}), 400
    origin = data.get("origin") if isinstance(data.get("origin"), dict) else None
    _, keys = _map_nodes()
    try:
        row = cli.declare_road(a, b, str(data.get("verb") or ""),
                                str(data.get("note") or ""), keys, origin=origin)
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/map/route/analyze", methods=["POST"])
def api_map_route_analyze():
    """A plotted route becomes the input to a run. The server assembles the
    materials mechanically from the record — stop definitions from the
    accepted shelf, the roads exactly as routed — and the analysis stage's
    claims are checked in code: 'from the record' must cite roads that are
    on this route, or it is demoted to interpretation."""
    data = request.get_json(force=True) or {}
    stops_in = data.get("stops") if isinstance(data.get("stops"), list) else []
    roads_in = data.get("roads") if isinstance(data.get("roads"), list) else []
    strategy = str(data.get("strategy") or "route")[:40]
    if not stops_in or not roads_in:
        return jsonify({"error": "a route needs stops and roads — plot one first"}), 400
    if len(stops_in) > 30 or len(roads_in) > 30:
        return jsonify({"error": "that route is too long to analyze in one run"}), 400
    defs = {}
    for c in cli.load_accepted_concepts():
        defs[cli._norm_title(c.get("name") or c.get("title") or "")] = \
            (c.get("definition") or "")[:400]
    stops = []
    for s in stops_in:
        if not isinstance(s, dict):
            continue
        label = str(s.get("label") or "")[:160]
        stops.append({"key": str(s.get("key") or "")[:200], "label": label,
                      "definition": defs.get(cli._norm_title(label), "")})
    roads = []
    for i, r in enumerate(roads_in):
        if not isinstance(r, dict):
            continue
        roads.append({"id": f"d{i + 1}",
                      "edge_id": str(r.get("edge_id") or "")[:60],
                      "from": str(r.get("from") or "")[:160],
                      "to": str(r.get("to") or "")[:160],
                      "rel": str(r.get("rel") or "")[:60],
                      "verb": str(r.get("verb") or "")[:120],
                      "road_type": str(r.get("road_type") or "recorded")[:30],
                      "detail": str(r.get("detail") or "")[:300],
                      "when": str(r.get("when") or "")[:40]})
    try:
        result = cli.run_route_analysis(stops, roads, strategy, server_gateway())
    except Exception as e:
        return jsonify({"error": cli.explain_component_failure(str(e))}), 500
    return jsonify(result)


@app.route("/api/map/log", methods=["POST"])
def api_map_log():
    """Client-side Wayfinder acts (find, select, discard) appended to the
    behavioral log. Whitelisting happens in cli.log_wayfinder; this
    endpoint only refuses events with no type."""
    data = request.get_json(force=True) or {}
    if not str(data.get("type") or "").strip():
        return jsonify({"error": "an event needs a type"}), 400
    cli.log_wayfinder(data)
    return jsonify({"ok": True})


@app.route("/api/map/stats")
def api_map_stats():
    """Counts of what the owner actually did with the map — plots, roads
    declared, proposals ratified — plus the structure of the record itself
    (islands, most-traveled roads). Raw counts and dates, computed fresh;
    no conclusions, because the dataset is the point: evidence of how he
    travels, not a summary of who he is."""
    log = cli.load_wayfinder_log()
    finds = [e for e in log if e.get("type") == "find"]
    by_type = {}
    for e in log:
        by_type[e["type"]] = by_type.get(e["type"], 0) + 1
    pair_counts = {}
    for e in finds:
        k = f"{e.get('from', '?')} → {e.get('to', '?')}"
        pair_counts[k] = pair_counts.get(k, 0) + 1
    top_pairs = sorted(pair_counts.items(), key=lambda kv: -kv[1])[:8]
    no_road = sum(1 for e in finds if e.get("none"))
    edges = cli.load_edges()
    declared = [e for e in edges if e.get("rel") == "declared_road"]
    ratified = [e for e in declared if e.get("proposed_by") == "model"]
    suggested = sum(int(e.get("n_candidates") or 0) for e in log
                    if e.get("type") == "suggest")
    # most-traveled: same pair of places, counted across every run that
    # recorded the road (recorded multiplicity — the log's own plot counts
    # grow beside it, and each is reported as what it is)
    ow = cli.build_overworld()
    trav = {}
    for e in ow["edges"]:
        if e["source"]["key"] == e["target"]["key"]:
            continue
        k = tuple(sorted((e["source"]["key"], e["target"]["key"])))
        trav.setdefault(k, {"a": e["source"]["label"], "b": e["target"]["label"],
                             "n": 0})
        trav[k]["n"] += 1
    most_traveled = sorted(trav.values(), key=lambda v: -v["n"])[:8]
    # islands: components of the full road graph, member keys kept so the
    # client can brighten one from the stats panel
    adj = {}
    for e in ow["edges"]:
        adj.setdefault(e["source"]["key"], set()).add(e["target"]["key"])
        adj.setdefault(e["target"]["key"], set()).add(e["source"]["key"])
    labels = {}
    for r in ow["runs"]:
        for it in r["items"]:
            labels.setdefault(it["key"], it["label"])
    seen, islands = set(), []
    for n in adj:
        if n in seen:
            continue
        comp, stack = set(), [n]
        while stack:
            x = stack.pop()
            if x in seen:
                continue
            seen.add(x)
            comp.add(x)
            stack.extend(adj.get(x, ()) - seen)
        islands.append(comp)
    islands.sort(key=len, reverse=True)
    island_rows = [{"size": len(c),
                    "labels": [labels.get(k, k) for k in sorted(c)[:3]],
                    "keys": sorted(c)[:60]} for c in islands[:10]]
    return jsonify({
        "acts": by_type, "plots": len(finds), "no_road": no_road,
        "top_pairs": [{"pair": p, "n": n} for p, n in top_pairs],
        "declared_roads": len(declared), "ratified_from_model": len(ratified),
        "proposals_shown": suggested,
        "most_traveled": most_traveled,
        "islands": {"n": len(islands), "top": island_rows},
        "note": "Counts of what you did and what the record holds — kept raw "
                "so anything trained on it later starts from evidence, not "
                "from a summary of you."})


# ---------------------------------------------------------------------------
# The Library wing — Phase 0. Ingestion is mechanical: hash, segment,
# index, render. server_gateway is never consulted on any route below, and
# the suite proves it by poisoning the gateway and ingesting anyway.

@app.route("/api/library/ingest", methods=["POST"])
def api_library_ingest():
    f = request.files.get("file")
    if f is None:
        return jsonify({"error": "no file was sent"}), 400
    data = f.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return jsonify({"error": f"that file is over the "
                                 f"{MAX_UPLOAD_BYTES // (1024*1024)}MB limit."}), 400
    if not data:
        return jsonify({"error": "that file is empty"}), 400
    try:
        result = library.ingest(
            data, filename=f.filename or "",
            source=str(request.form.get("source") or "")[:500],
            title=str(request.form.get("title") or "")[:200])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(result)


def _library_documents_payload():
    """The Documents listing — shared by the one true /api/library route.
    Two routes once claimed that rule and the first silently shadowed the
    second, which emptied the page's whole Library shelf; this helper plus
    the single merged route below is the repair, and the suite now pins
    the union payload so a shadowing route can never hide again."""
    docs = library.load_documents()
    ingests = library.load_ingests()
    by_doc = {}
    for row in ingests:
        by_doc.setdefault(row["document_id"], []).append(row)
    out = []
    for did, d in docs.items():
        rep = library.load_representation(d.get("current_representation_id", ""))
        out.append({"document_id": did, "title": d.get("title", ""),
                     "kind": d.get("kind", ""),
                     "representation_id": d.get("current_representation_id", ""),
                     "n_sections": rep.get("n_sections", 0),
                     "n_sentences": rep.get("n_sentences", 0),
                     "n_findings": len(rep.get("findings") or []),
                     "acquisitions": [{"source": r.get("source", ""),
                                        "retrieved_at": r.get("retrieved_at", "")}
                                       for r in by_doc.get(did, [])],
                     "created_at": d.get("created_at", "")})
    out.sort(key=lambda x: x["created_at"], reverse=True)
    return out


@app.route("/api/library/doc/<rep_id>")
def api_library_doc(rep_id):
    rep = library.load_representation(rep_id)
    if not rep:
        return jsonify({"error": "no such representation"}), 404
    try:
        sec_i = max(0, min(int(request.args.get("section", 0)),
                            rep["n_sections"] - 1))
    except ValueError:
        sec_i = 0
    sec = rep["sections"][sec_i] if rep["sections"] else {}
    return jsonify({"representation_id": rep["representation_id"],
                     "title": rep["title"], "kind": rep["kind"],
                     "extractor": rep["extractor"],
                     "segmenter_rev": rep["segmenter_rev"],
                     "n_sections": rep["n_sections"],
                     "n_sentences": rep["n_sentences"],
                     "findings": rep["findings"],
                     "section_index": sec_i,
                     "headings": [x["heading"] for x in rep["sections"]],
                     "section": {"heading": sec.get("heading", ""),
                                  "paragraphs": [
                                      {"tag": p2["tag"],
                                       "sentences": [
                                           {"anchor_id": f"{rep['representation_id']}:{s2['path']}",
                                            "text": s2["text"]}
                                           for s2 in p2["sentences"]]}
                                      for p2 in sec.get("paragraphs", [])]}})


@app.route("/api/library/search")
def api_library_search():
    return jsonify({"lane": "library-exact",
                     "note": "Exact text in your library only — not semantic, "
                             "not the web.",
                     "results": library.search(request.args.get("q", ""))})


@app.route("/api/library/resolve/<path:anchor_id>")
def api_library_resolve(anchor_id):
    return jsonify(library.resolve_anchor(anchor_id))


@app.route("/api/library/crossing", methods=["POST"])
def api_library_crossing():
    """Phase 1A: a selection becomes a note, claim, citation, or Bench
    ingredient. Mechanical — no gateway on this path, and creating a claim
    records only that it was created while viewing the span: support is
    born unruled. Idempotent against double-clicks by content-hashed id."""
    data = request.get_json(force=True) or {}
    try:
        row = library.make_crossing(
            str(data.get("kind") or ""),
            str(data.get("representation_id") or ""),
            str(data.get("start_path") or ""), int(data.get("start_offset") or 0),
            str(data.get("end_path") or ""), int(data.get("end_offset") or 0),
            owner_text=str(data.get("owner_text") or ""))
    except (ValueError, TypeError) as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/library/crossings")
def api_library_crossings():
    return jsonify({"crossings": library.load_crossings(
        str(request.args.get("representation_id") or ""))})


@app.route("/api/library/crossing/retract", methods=["POST"])
def api_library_retract():
    data = request.get_json(force=True) or {}
    try:
        row = library.retract_crossing(str(data.get("crossing_id") or ""),
                                        undo=bool(data.get("undo")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/library/support", methods=["POST"])
def api_library_support():
    """Phase 1B rev 2: the explicit support question, summoned by the
    owner. Context is supplied as LABELED sentences (the span's paragraphs
    plus one neighbor each side) so the stage can read the span — and so
    code can catch it the moment its judgment actually rests outside the
    selection. The proposal changes nothing until the owner rules."""
    data = request.get_json(force=True) or {}
    cid = str(data.get("crossing_id") or "")
    target = next((c for c in library.load_crossings()
                   if c["crossing_id"] == cid), None)
    if not target:
        return jsonify({"error": "no such crossing"}), 400
    if target.get("kind") != "claim":
        return jsonify({"error": "support is a question about claims"}), 400
    if target.get("mismatch"):
        return jsonify({"error": "the span no longer retrieves cleanly — "
                                 "resolve the mismatch before asking anything "
                                 "of it"}), 400
    sr = target["span_ref"]
    rep = library.load_representation(sr["representation_id"])
    si = int(sr["start_anchor"].split(".")[0])
    sec = rep["sections"][si]
    p0 = int(sr["start_anchor"].split(".")[1])
    p1 = int(sr["end_anchor"].split(".")[1])
    lo, hi = max(0, min(p0, p1) - 1), min(len(sec["paragraphs"]) - 1,
                                           max(p0, p1) + 1)
    context_sentences = [
        {"path": s2["path"], "text": s2["text"]}
        for i in range(lo, hi + 1)
        for s2 in sec["paragraphs"][i]["sentences"]]
    k0 = tuple(int(x) for x in sr["start_anchor"].split("."))
    k1 = tuple(int(x) for x in sr["end_anchor"].split("."))
    if k1 < k0:
        k0, k1 = k1, k0
    span_paths = [c2["path"] for c2 in context_sentences
                  if k0 <= tuple(int(x) for x in c2["path"].split(".")) <= k1]
    try:
        result = cli.run_support_question(
            target.get("owner_text", ""), target["retrieved_text"], sr,
            span_paths, context_sentences, target.get("heading", ""),
            server_gateway())
    except Exception as e:
        return jsonify({"error": cli.explain_component_failure(str(e))}), 500
    library.record_support_proposal(cid, result)
    return jsonify(result)


def _source_anchor_list():
    snaps = []
    if cli.RESULTS_DIR.exists():
        for path in cli.RESULTS_DIR.glob("*.json"):
            try:
                snap = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(snap, dict) and snap.get("threads"):
                snaps.append(snap)
    canon, _notes = cli.concept_canon(with_notes=True)
    return cli.anchor_index(snaps, canon)


# ---------------------------------------------------------------------------
# The Work Room (backlog 21/21b — owner's explicit go). Zero model calls,
# zero network on every route below: creation, linking, statuses and the
# room's assembly are all mechanical reads of records that already exist.

@app.route("/api/works")
def api_works_list():
    return jsonify({"works": sorted(library.load_works().values(),
                                     key=lambda w: w["created_at"],
                                     reverse=True)})


@app.route("/api/works", methods=["POST"])
def api_works_create():
    data = request.get_json(force=True) or {}
    try:
        row = library.create_work(
            str(data.get("canonical_title") or ""),
            str(data.get("creator_display") or ""),
            str(data.get("work_kind") or "other"),
            str(data.get("original_date") or ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/works/link", methods=["POST"])
def api_works_link():
    data = request.get_json(force=True) or {}
    try:
        row = library.link_work(
            str(data.get("work_id") or ""),
            str(data.get("subject_kind") or ""),
            str(data.get("subject_id") or ""),
            role=str(data.get("role") or ""),
            origin=str(data.get("origin") or "owner"),
            proposal_trace_id=str(data.get("proposal_trace_id") or ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/works/link/retract", methods=["POST"])
def api_works_link_retract():
    data = request.get_json(force=True) or {}
    try:
        row = library.retract_work_link(str(data.get("link_id") or ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/works/external", methods=["POST"])
def api_works_external():
    data = request.get_json(force=True) or {}
    try:
        row = library.save_external_ref(
            str(data.get("work_id") or ""), str(data.get("url") or ""),
            str(data.get("title") or ""),
            str(data.get("source_function") or ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/works/external/status", methods=["POST"])
def api_works_external_status():
    data = request.get_json(force=True) or {}
    try:
        row = library.set_access_status(str(data.get("ref_id") or ""),
                                         str(data.get("status") or ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/works/room/<work_id>")
def api_works_room(work_id):
    """The room, assembled from records that already exist. Passages come
    only from crossings over linked imported documents (mechanical
    retrieval, the existing machinery); readings are the existing
    source-index accounts for linked entries — never rendered as the
    work's words; variations are linked documents kept separate; paths are
    the Map's existing recorded/reconstructed/declared roads touching
    linked keys. Nothing here is generated."""
    works = library.load_works()
    w = works.get(work_id)
    if not w:
        return jsonify({"error": "no such work"}), 404
    links = w["links"]
    doc_ids = [l["subject_id"] for l in links if l["subject_kind"] == "document"]
    src_ids = {l["subject_id"] for l in links if l["subject_kind"] == "source_entry"}
    map_keys = {l["subject_id"] for l in links if l["subject_kind"] == "map_key"}
    docs = library.load_documents()
    variations = []
    for l in links:
        if l["subject_kind"] != "document":
            continue
        d = docs.get(l["subject_id"]) or {}
        rep = library.load_representation(d.get("current_representation_id", ""))
        variations.append({"document_id": l["subject_id"], "role": l["role"],
                            "title": d.get("title", ""),
                            "kind": d.get("kind", ""),
                            "representation_id": d.get("current_representation_id", ""),
                            "n_sections": rep.get("n_sections", 0),
                            "n_sentences": rep.get("n_sentences", 0),
                            "findings": rep.get("findings") or []})
    passages = [c for c in library.load_crossings()
                if c.get("document_id") in doc_ids and not c.get("retracted")]
    readings = []
    if src_ids:
        for a in _source_anchor_list():
            if a["key"] in src_ids:
                readings.append({"key": a["key"], "name": a["name"],
                                  "works": a.get("works") or [],
                                  "accounts": a.get("accounts") or [],
                                  "account_missing": a.get("account_missing", "")})
    concepts = sorted({ac.get("from_concept", "")
                       for r in readings for ac in r["accounts"]
                       if ac.get("from_concept")})
    roads = []
    if map_keys:
        for e in cli.build_overworld()["edges"]:
            if e["source"]["key"] in map_keys or e["target"]["key"] in map_keys:
                roads.append({"rel": e["rel"],
                               "source": e["source"]["label"],
                               "target": e["target"]["label"],
                               "road_type": ("declared" if e["rel"] == "declared_road"
                                              else "reconstructed" if e.get("synthesized")
                                              else "recorded"),
                               "run_trace_id": e.get("run_trace_id", "")})
    return jsonify({"work": {k: w[k] for k in ("work_id", "canonical_title",
                     "creator_display", "work_kind", "original_date",
                     "created_at")},
                     "links": links, "external_refs": w["external_refs"],
                     "variations": variations, "passages": passages,
                     "readings": readings, "concepts": concepts,
                     "roads": roads[:80]})




# ---------------------------------------------------------------------------
# The media lane (slices 1+2 — owner's go 2026-08-29). Every route below is
# zero-model and zero-network: recordings you own, transcripts you supply,
# crossings and rulings appended mechanically. The blob route streams with
# Range support because seeking IS the feature; streaming a byte range is
# still only reading a file you already own.

@app.route("/api/media")
def api_media_list():
    items = sorted(library.load_media().values(),
                   key=lambda m: m["created_at"], reverse=True)
    return jsonify({"media": items})


MEDIA_UPLOAD_CAP = 30 * 1024 * 1024      # temporary, until streamed ingestion
TRANSCRIPT_UPLOAD_CAP = 2 * 1024 * 1024


def _capped_upload(f, cap, what):
    """Bounded read — the whole recording must not land in memory. Reads
    cap+1 bytes so an oversize file is DETECTED, never swallowed."""
    if request.content_length and request.content_length > cap + 4096:
        return None
    data = f.read(cap + 1)
    if len(data) > cap:
        return None
    return data


@app.route("/api/media/ingest", methods=["POST"])
def api_media_ingest():
    f = request.files.get("file")
    if f is None:
        return jsonify({"error": "no file arrived"}), 400
    data = _capped_upload(f, MEDIA_UPLOAD_CAP, "recording")
    if data is None:
        return jsonify({"error": "streamed ingestion is not built yet — "
                        "recordings over 30 MB are refused plainly rather "
                        "than loaded whole into memory. A full-length "
                        "episode waits for the streaming pass; a short "
                        "recording or an excerpt works today."}), 413
    try:
        got = library.ingest_media(data, filename=f.filename or "",
                                    source=request.form.get("source", ""),
                                    title=request.form.get("title", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(got)


@app.route("/api/media/transcript", methods=["POST"])
def api_media_transcript():
    f = request.files.get("file")
    if f is None:
        return jsonify({"error": "no transcript file arrived"}), 400
    data = _capped_upload(f, TRANSCRIPT_UPLOAD_CAP, "transcript")
    if data is None:
        return jsonify({"error": "that transcript is over 2 MB — refused "
                        "plainly; a transcript that size is almost "
                        "certainly not a transcript."}), 413
    try:
        got = library.add_transcript(
            request.form.get("media_id", ""), data,
            filename=f.filename or "",
            origin=request.form.get("origin", ""),
            source=request.form.get("source", ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(got)


@app.route("/api/media/blob/<media_id>")
def api_media_blob(media_id):
    m = library.load_media().get(media_id)
    if not m:
        return jsonify({"error": "no such media item"}), 404
    path = library.blobs_dir() / m["blob_id"]
    if not path.exists():
        return jsonify({"error": "the stored bytes are missing — the "
                        "record exists but the blob does not"}), 410
    from flask import send_file
    return send_file(path, mimetype=m.get("mime") or
                     "application/octet-stream", conditional=True)


@app.route("/api/media/transcript/<transcript_id>")
def api_media_transcript_get(transcript_id):
    tdoc = library.load_transcript(transcript_id)
    if not tdoc:
        return jsonify({"error": "no such transcript"}), 404
    return jsonify(tdoc)


@app.route("/api/media/crossing", methods=["POST"])
def api_media_crossing():
    data = request.get_json(force=True) or {}
    try:
        row = library.make_media_crossing(
            str(data.get("kind") or ""),
            str(data.get("transcript_id") or ""),
            data.get("start_i"), data.get("end_i"),
            owner_text=str(data.get("owner_text") or ""))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/media/crossing/retract", methods=["POST"])
def api_media_crossing_retract():
    data = request.get_json(force=True) or {}
    try:
        row = library.retract_media_crossing(
            str(data.get("crossing_id") or ""),
            undo=bool(data.get("undo")))
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/media/crossings")
def api_media_crossings():
    return jsonify({"crossings": library.load_media_crossings(
        request.args.get("transcript_id", ""))})


@app.route("/api/media/rule", methods=["POST"])
def api_media_rule():
    data = request.get_json(force=True) or {}
    try:
        row = library.rule_media_claim(
            str(data.get("crossing_id") or ""),
            str(data.get("bearing") or ""),
            (str(data.get("mode")) if data.get("mode") else None),
            origin=str(data.get("origin") or "owner"),
            reason=str(data.get("reason") or "")[:500])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/library/support/rule", methods=["POST"])
def api_library_support_rule():
    """The owner's ruling — mechanical append, no model, and sovereign:
    adopt a proposal (origin adopted_model, carrying the proposal trace),
    rule it yourself (origin owner, optional basis and reason, the
    evidence boundary applied), or reject. A ruling over an existing one
    auto-links as superseding; history only grows."""
    data = request.get_json(force=True) or {}
    basis = data.get("basis") if isinstance(data.get("basis"), list) else None
    try:
        row = library.record_support_ruling(
            str(data.get("crossing_id") or ""),
            str(data.get("bearing") or ""),
            (str(data.get("mode")) if data.get("mode") else None),
            origin=str(data.get("origin") or "owner"),
            basis=[str(b)[:20] for b in (basis or [])][:8] or None,
            reason=str(data.get("reason") or "")[:500],
            proposal_trace_id=str(data.get("proposal_trace_id") or "")[:60])
    except ValueError as e:
        return jsonify({"error": str(e)}), 400
    return jsonify(row)


@app.route("/api/config")
def api_config():
    try:
        gw = server_gateway()
        return jsonify({"gateway": gw.name, "ok": True})
    except Exception as e:
        return jsonify({"gateway": None, "ok": False, "error": str(e)})


@app.route("/api/jobs", methods=["POST"])
def api_create_job():
    data = request.get_json(force=True) or {}
    mode = data.get("mode")
    if mode not in ("auto", "deep", "forge", "crack", "decompose", "riff", "play", "revise",
                    "sprout", "refract", "verify", "archetype", "recheck", "etymon"):
        return jsonify({"error": "mode must be 'auto', 'deep', 'forge', 'crack', 'decompose', "
                                 "'riff', 'play', 'revise', 'sprout', 'refract', 'archetype', "
                                 "'recheck', 'etymon', or 'verify'"}), 400
    # The gesture rides only the deep workup (the chooser's Interpret /
    # Put-it-on-trial choices); Play is its own mode, and anything else
    # carrying a gesture is a caller bug worth refusing out loud.
    gesture = str(data.get("gesture") or "trial")
    if gesture not in ("trial", "interpret"):
        return jsonify({"error": "gesture must be 'trial' or 'interpret'"}), 400
    if gesture != "trial" and mode != "deep":
        return jsonify({"error": "a gesture applies only to mode 'deep'"}), 400

    original, claims_detail = None, None
    owner_note, prior_friction = None, None
    wordify = False
    parent_trace_id, via, parent_door_id = None, None, None
    known_neighbors = None
    retry_anchor, retry_stance, retry_match_text = None, None, None
    verify_candidate = None
    if mode == "sprout":
        original = data.get("original") or {}
        if not original.get("title") or not original.get("definition"):
            return jsonify({"error": "sprout requires original.title and original.definition"}), 400
        parent_trace_id = str(data.get("parent_trace_id") or "")[:64] or None
        via = str(data.get("via") or "")[:200] or None
        # The door that led here, by id. This edge — not a text comparison
        # against the door's wording — is what proves a door was opened.
        parent_door_id = str(data.get("parent_door_id") or "")[:64] or None
        # Carried forward from the thread's OWN review, when sprouting
        # from a thread rather than a fresh candidate or a door — never
        # trusted blindly, just sanitized and handed to run_sprout so the
        # inherited-caveat rule can act on it. The phone never sends
        # anything the pipeline itself didn't generate one hop earlier.
        inherited_verdict = str(original.get("inherited_verdict") or "")[:20]
        inherited_note = str(original.get("inherited_note") or "")[:1000]
        original = {**original, "inherited_verdict": inherited_verdict,
                    "inherited_note": inherited_note}
        input_text = f"sprout: {original['title']}"
    elif mode == "refract":
        original = data.get("original") or {}
        if not original.get("title") or not original.get("definition"):
            return jsonify({"error": "refract requires original.title and original.definition"}), 400
        known_neighbors = str(data.get("known_neighbors") or "")[:800] or None
        input_text = f"refract: {original['title']}"
    elif mode == "recheck":
        original = data.get("original") or {}
        if not original.get("title") or not original.get("definition"):
            return jsonify({"error": "recheck requires original.title and original.definition"}), 400
        original = {k: str(original.get(k, ""))[:1500] for k in
                    ("title", "definition", "central_contradiction", "axiom",
                     "plain_gloss", "concept_id")}
        input_text = f"recheck: {original['title']}"
    elif mode == "archetype":
        original = data.get("original") or {}
        if not original.get("title") or not original.get("definition"):
            return jsonify({"error": "archetype requires original.title and original.definition"}), 400
        original = {k: str(original.get(k, ""))[:1500] for k in
                    ("title", "definition", "central_contradiction", "axiom", "plain_gloss")}
        input_text = f"archetype: {original['title']}"
    elif mode == "verify":
        c = data.get("candidate") or {}
        if not c.get("title") or not c.get("definition"):
            return jsonify({"error": "verify requires candidate.title and candidate.definition"}), 400
        verify_candidate = {
            "title": str(c.get("title", ""))[:200],
            "definition": str(c.get("definition", ""))[:1200],
            "central_contradiction": str(c.get("central_contradiction", ""))[:800],
            "axiom": str(c.get("axiom", ""))[:400],
            "verdict": str(c.get("verdict", ""))[:20],
            "hostile_read": str(c.get("hostile_read", ""))[:1200],
            "redundancy_note": str(c.get("redundancy_note", ""))[:1200],
            "source_fidelity_note": str(c.get("source_fidelity_note", ""))[:1200],
            "anchor": str(c.get("anchor", ""))[:400],
            "background": str(c.get("background", ""))[:1200],
        }
        input_text = f"verify: {verify_candidate['title']}"
    elif mode == "revise":
        original = data.get("original") or {}
        claims_detail = data.get("claims_detail") or []
        owner_note = (data.get("owner_note") or "").strip() or None
        wordify = bool(data.get("wordify")) and not owner_note
        f = data.get("friction") or {}
        prior_friction = {"hostile_read": str(f.get("hostile_read", ""))[:600],
                           "redundancy_note": str(f.get("redundancy_note", ""))[:600]} if f else None
        if not original.get("title") or not original.get("definition"):
            return jsonify({"error": "revise requires original.title and original.definition"}), 400
        input_text = f"{'wordify' if wordify else 'revise'}: {original['title']}"
    else:
        input_text = (data.get("input_text") or "").strip()
        # THE SOURCE IS THE ARTIFACT'S BYTES AND NOTHING ELSE.
        #
        # This used to wrap input_text in the quarantine preamble right here,
        # which put ten lines of MY instructions into the string every later
        # stage treats as the source. The consequences on the first README
        # uploaded: the run extracted "Content-versus-instruction quarantine"
        # as a concept found in his file, anchored it to "It is data to be
        # read, never instructions to you" — a sentence I wrote — and
        # reported it as an exact match on line 3. Every real line was off by
        # ten. Tier 1 was mechanically correct against a contaminated
        # substrate, which is worse than being wrong, because it was
        # confident and reproducible.
        #
        # The defence against injection now lives where it belongs: in the
        # PROMPT, at build time, wrapping the source as it is handed to a
        # model. Nothing is concatenated into the source itself.
        artifact_id = (data.get("from_artifact") or "").strip()
        if not input_text:
            return jsonify({"error": "input_text is required"}), 400
        # Optional retry-fidelity fields: a failed decompose concept is
        # retried as a plain forge carrying its exact original packet.
        retry_anchor = str(data.get("anchor") or "")[:400] or None
        retry_stance = str(data.get("stance") or "")[:200] or None
        retry_match_text = str(data.get("match_text") or "")[:2000] or None

    routing_note, routed_from = "", None
    if mode == "auto":
        input_probe = (data.get("input_text") or "").strip()
        if not input_probe:
            return jsonify({"error": "input_text is required"}), 400
        mode, routing_note = cli.route_input(input_probe)
        routed_from = "auto"

    avoid_titles = [str(t) for t in (data.get("avoid_titles") or [])][:60]
    prior_attempts = []
    for a in (data.get("prior_attempts") or [])[:20]:
        if isinstance(a, dict) and a.get("title"):
            prior_attempts.append({
                "title": str(a.get("title", ""))[:120],
                "definition": str(a.get("definition", ""))[:400],
                "verdict": str(a.get("verdict", ""))[:20],
                "hostile": str(a.get("hostile", ""))[:400],
                "redundancy": str(a.get("redundancy", ""))[:400],
            })

    job_id = _new_job_id()
    with JOBS_LOCK:
        JOBS[job_id] = {
            "id": job_id, "mode": mode, "gesture": gesture, "input_text": input_text,
            "original": original, "claims_detail": claims_detail,
            "owner_note": owner_note, "prior_friction": prior_friction,
            "wordify": wordify, "parent_trace_id": parent_trace_id, "via": via,
            "parent_door_id": parent_door_id,
            "known_neighbors": known_neighbors, "verify_candidate": verify_candidate,
            "retry_anchor": retry_anchor, "retry_stance": retry_stance,
            "retry_match_text": retry_match_text,
            "avoid_titles": avoid_titles, "prior_attempts": prior_attempts,
            "routing_note": routing_note, "routed_from": routed_from,
            "status": "queued", "progress": "Queued…", "result": None, "error": None,
            "stage_changed_at": time.time(),
            "created_at": _now_iso(), "updated_at": _now_iso(),
        }
    # On disk BEFORE the thread starts. If the gateway refuses, if the
    # process dies, if he closes the tab — the words he typed survive all
    # three, which was not true of any of them a moment ago.
    cli.record_input(job_id, mode, input_text, parent_trace_id or "")
    thread = threading.Thread(target=_run_job, args=(job_id, mode, input_text), daemon=True)
    thread.start()
    return jsonify({"job_id": job_id, "status": "queued"})


@app.route("/api/jobs/<job_id>")
def api_get_job(job_id):
    with JOBS_LOCK:
        job = JOBS.get(job_id)
        if job is None:
            return jsonify({"error": "no job with that id — the server may have restarted since it was submitted"}), 404
        shaped = dict(job)
        # Server-clock-only elapsed time for the current step — computed at
        # read time so the phone never has to compare its clock to ours.
        if shaped.get("status") not in ("done", "failed") and shaped.get("stage_changed_at"):
            shaped["stage_elapsed_s"] = int(time.time() - shaped["stage_changed_at"])
        return jsonify(shaped)


@app.route("/api/jobs")
def api_list_jobs():
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda j: j["created_at"], reverse=True)[:20]
        return jsonify({"jobs": [
            {k: v for k, v in j.items() if k != "result"} for j in jobs
        ]})


@app.route("/api/inflight")
def api_inflight():
    """What you were doing — so that walking to the Bench is no longer the
    same act as throwing it away.

    Two sources, and they answer different questions. JOBS is what is
    RUNNING (in memory, lost on restart); inputs.jsonl is what was TYPED
    (on disk, survives everything). A run that failed appears in the second
    and not the first, which is exactly the case the owner lost work to.

    GET /api/jobs has existed since the job model was written and no client
    has ever called it — the list of everything in flight was sitting here
    unread the whole time the interface was telling him his work was gone.
    """
    with JOBS_LOCK:
        jobs = sorted(JOBS.values(), key=lambda j: j.get("created_at") or "",
                      reverse=True)[:20]
        live = [{
            "job_id": j.get("id", ""), "mode": j.get("mode", ""),
            "status": j.get("status", ""), "progress": j.get("progress", ""),
            "error": j.get("error") or "",
            "input_text": (j.get("input_text") or "")[:600],
            "created_at": j.get("created_at", ""),
            "trace_id": ((j.get("result") or {}) or {}).get("trace_id", ""),
        } for j in jobs]
    # Which typed inputs already reached a finished run, so the strip can
    # show an abandoned one differently from one that simply completed.
    done = {j["job_id"] for j in live if j["status"] in ("complete", "failed")}
    running = [j for j in live if j["status"] not in ("complete", "failed")]
    return jsonify({"running": running, "recent": live,
                    "inputs": cli.load_inputs(60), "finished_job_ids": sorted(done)})


# ---- getting it out ------------------------------------------------------
#
# scripts/export.py is standalone on purpose — "an exporter that can crash
# the tool it exports is worse than no exporter" — so it is imported HERE,
# inside the request, rather than at module load. A broken exporter then
# returns a 500 on one route instead of stopping the server from starting.

def _exporter():
    import importlib.util
    spec = importlib.util.spec_from_file_location(
        "wordicon_export", str(pathlib.Path(__file__).resolve().parent / "scripts" / "export.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    # The server is the authority on where state lives; the exporter's own
    # default is for running it from a shell.
    mod.LOCAL_STATE = cli.LOCAL_STATE
    return mod


def _writing_md():
    """Everything you have typed, newest first, as one document.

    This is the journal. It is deliberately NOT filtered to runs that
    succeeded or words that were kept — the whole reason inputs are written
    at submission is that what you wrote is worth more than what the tool
    made of it."""
    rows = cli.load_inputs(100000)
    out = ["# Everything you have typed", "",
           f"{len(rows)} entr{'y' if len(rows) == 1 else 'ies'} · exported "
           + _now_iso(), "",
           "Newest first. Every one of these was written to disk the moment it "
           "was submitted, before any model was contacted, so entries here may "
           "belong to runs that failed or were never opened again.", "", "---", ""]
    for r in rows:
        when = (r.get("created_at") or "")[:19].replace("T", " ")
        out.append(f"## {when or 'undated'} · {r.get('mode') or 'input'}")
        out.append("")
        out.append((r.get("text") or "").rstrip())
        out.append("")
        out.append("---")
        out.append("")
    return "\n".join(out)


def _download(body: bytes, filename: str, mime: str):
    return Response(body, mimetype=mime, headers={
        "Content-Disposition": f'attachment; filename="{filename}"',
        "Content-Length": str(len(body)),
        # A stale export is a wrong export: these are generated per request.
        "Cache-Control": "no-store",
    })


@app.route("/api/export/<kind>")
def api_export(kind):
    try:
        # `datetime` here is the CLASS — server.py binds it that way at the
        # top and my module-level import was silently shadowed by it. Every
        # route 500'd on the first line before the try block caught anything,
        # which is also why the stamp is computed inside it now.
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        if kind == "writing":
            return _download(_writing_md().encode("utf-8"),
                             f"wordicon-writing-{stamp}.md", "text/markdown; charset=utf-8")
        ex = _exporter()
        if kind == "lexicon":
            entries = ex.build_entries()
            return _download(ex.lexicon_md(entries, "").encode("utf-8"),
                             f"wordicon-lexicon-{stamp}.md", "text/markdown; charset=utf-8")
        if kind == "table":
            return _download(ex.table_jsonl(ex.build_entries()).encode("utf-8"),
                             f"wordicon-lexicon-{stamp}.jsonl", "application/x-ndjson")
        if kind == "corpus":
            # The bundle and its manifest are written to disk by the
            # exporter, then handed over. The manifest digest travels in a
            # HEADER rather than inside the archive: a receipt that ships in
            # the box it certifies certifies nothing.
            import tempfile
            tar, man, digest, n = ex.bundle(pathlib.Path(tempfile.mkdtemp()))
            r = _download(tar.read_bytes(), tar.name, "application/gzip")
            r.headers["X-Wordicon-Manifest-Sha256"] = digest
            r.headers["X-Wordicon-File-Count"] = str(n)
            return r
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"the export failed: {e}"}), 500
    return jsonify({"error": f"nothing exports as {kind!r}"}), 404


@app.route("/api/export/corpus/manifest")
def api_export_manifest():
    """The manifest on its own, so the digest can be kept somewhere other
    than beside the archive it vouches for."""
    try:
        import tempfile
        ex = _exporter()
        tar, man, digest, n = ex.bundle(pathlib.Path(tempfile.mkdtemp()))
        return _download(man.read_bytes(), man.name, "application/json")
    except Exception as e:
        traceback.print_exc()
        return jsonify({"error": f"the manifest failed: {e}"}), 500


@app.route("/api/definition", methods=["POST"])
def api_definition():
    """Replace a kept word's meaning with the owner's own.

    The one thing this endpoint must never do is let the new sentence keep
    the old sentence's evidence. That is enforced in the store rather than
    here, and reported back so the page can say it out loud rather than
    leaving the owner to assume the checks still apply."""
    d = request.get_json(force=True) or {}
    title = str(d.get("title") or "").strip()[:200]
    definition = str(d.get("definition") or "").strip()[:1500]
    reason = str(d.get("reason") or "").strip()[:400]
    if not title or not definition:
        return jsonify({"error": "a word and a definition are required"}), 400
    out = cli.persist_definition_edit(title, definition, reason)
    if not out.get("changed"):
        return jsonify({"error": out.get("why") or "nothing changed"}), 400
    return jsonify({**out, "grounding_reset": True,
                    "note": "Everything previously checked about this word was checked "
                            "against the sentence you just replaced. None of it carries "
                            "over. The old wording is kept on the entry."})


@app.route("/api/similar")
def api_similar():
    """Preflight for an acceptance: what would this duplicate?

    Deliberately a SEPARATE call made before the judgment, not a check
    inside it. The point is forced comparison at the moment of admission
    — the owner sees the collision while deciding, rather than being told
    afterward. Nothing here blocks anything; it returns findings and the
    owner rules, same as everywhere else in this tool."""
    title = (request.args.get("title") or "").strip()
    definition = (request.args.get("definition") or "").strip()
    if not title:
        return jsonify({"matches": []})
    return jsonify({"matches": cli.similar_accepted(title, definition)})


@app.route("/bench")
def bench_page():
    return send_from_directory(WEBAPP_DIR, "bench.html")


@app.route("/api/bench/open", methods=["POST"])
def api_bench_open():
    """Open an accepted word on the Bench.

    Synchronous on purpose: one model call, and the owner is sitting in
    front of it choosing what to do next. A job queue here would put a
    spinner between every step of what is supposed to feel like moving
    pieces around on a table."""
    data = request.get_json(force=True) or {}
    title = str(data.get("title") or "").strip()[:200]
    definition = str(data.get("definition") or "").strip()[:1500]
    if not title:
        return jsonify({"error": "title is required"}), 400
    if not definition:
        # The six oldest Library entries are titles with nothing attached.
        # Say that, rather than letting the Bench invent a meaning to
        # break into parts.
        return jsonify({"error": "This entry has no definition stored, so there is no "
                                 "meaning to take apart. It predates definitions being "
                                 "saved with acceptances."}), 400
    fresh = str(data.get("fresh_contract") or "") == "1"
    try:
        result = cli.run_bench(title, definition, server_gateway())
    except Exception as e:
        return jsonify({"error": cli.explain_component_failure(str(e))}), 500

    # Store the opening BEFORE anything is substituted, so `opens` always
    # holds what the model actually proposed this time.
    stored = cli.save_bench_open(title, definition, result,
                                  concept_id=str(data.get("concept_id") or "").strip()[:64])

    # HIS CONTRACT WINS, AND THE MODEL'S IS STILL SHOWN. Reopening a word
    # he has already corrected must not make him correct it again — that is
    # the whole ask. But quietly swapping in the stored version would hide
    # that the model proposed something different this time, and a silent
    # disagreement between the two is exactly the kind of thing this tool
    # exists to surface rather than smooth over.
    result["contract_proposed_now"] = result.get("contract") or []
    result["contract_source"] = cli.CONTRACT_MODEL
    result["contract_confirmed_at"] = ""
    result["reused_contract"] = False
    if not fresh and stored.get("contract") \
            and stored.get("contract_source") == cli.CONTRACT_OWNER:
        result["contract"] = stored["contract"]
        result["contract_source"] = cli.CONTRACT_OWNER
        result["contract_confirmed_at"] = stored.get("contract_confirmed_at", "")
        result["reused_contract"] = True
        a, b = result["contract"], result["contract_proposed_now"]
        result["contract_differs_from_now"] = (
            [p.get("name") for p in a] != [p.get("name") for p in b]
            or [p.get("gist") for p in a] != [p.get("gist") for p in b])
    # Past rounds travel WITH the open, so the Bench page can show its own
    # history instead of making him leave for the Library to find out what
    # he already did here.
    corrections_by_word = {}
    for c in (cli.load_bench_library().get("words") or []):
        if cli._norm_title(c.get("title", "")) == cli._norm_title(title):
            for row in (c.get("corrections") or []):
                corrections_by_word.setdefault(row.get("word", ""), []).append(row)

    now_contract = [(p2.get("name"), p2.get("gist")) for p2 in (result.get("contract") or [])]
    rounds = []
    for r in (stored.get("builds") or []):
        then = [(p2.get("name"), p2.get("gist")) for p2 in (r.get("contract_at_build") or [])]
        rounds.append({
            "at": r.get("at", ""), "method": r.get("method", ""),
            "materials": r.get("materials") or [],
            # A verdict reached against a contract he has since rewritten is
            # not a verdict on the contract he is looking at now. Saying so
            # is the difference between history and a stale claim.
            "contract_changed_since": bool(then) and then != now_contract,
            "contract_then": [p2.get("name") for p2 in (r.get("contract_at_build") or [])],
            "words": [{"word": b.get("word", ""), "contract": b.get("contract") or {},
                       "standing": b.get("standing", ""),
                       "corrections": corrections_by_word.get(b.get("word", ""), [])}
                      for b in (r.get("builds") or [])],
        })
    rounds.reverse()          # newest first

    result["history"] = {
        "opens": len(stored.get("opens") or []),
        "build_rounds": len(stored.get("builds") or []),
        "words_built": sorted({b.get("word", "") for r in (stored.get("builds") or [])
                               for b in (r.get("builds") or []) if b.get("word")}),
        "first_opened": stored.get("created_at", ""),
        "rounds": rounds,
    }
    return jsonify(result)


@app.route("/api/bench/contract", methods=["POST"])
def api_bench_contract():
    """Store the contract the owner is working with, and whether he has
    confirmed it. `confirmed` is his act and arrives from the confirm
    button; the CLI derives the label from it so no caller can mint an
    owner confirmation the owner never gave."""
    d = request.get_json(force=True) or {}
    title = str(d.get("title") or "").strip()[:200]
    if not title:
        return jsonify({"error": "title is required"}), 400
    contract = []
    for pt in (d.get("contract") or [])[:5]:
        if not isinstance(pt, dict) or not (pt.get("key") or "").strip():
            continue
        contract.append({"key": str(pt["key"])[:40], "name": str(pt.get("name") or "")[:60],
                         "gist": str(pt.get("gist") or "")[:240],
                         "locked": bool(pt.get("locked", True))})
    out = cli.save_bench_contract(title, contract, bool(d.get("confirmed")),
                                   concept_id=str(d.get("concept_id") or "").strip()[:64])
    return jsonify({"ok": True, "contract_source": out.get("contract_source"),
                    "contract_confirmed_at": out.get("contract_confirmed_at", "")})


@app.route("/api/bench/keep", methods=["POST"])
def api_bench_keep():
    """Keep a coin the Bench built — into the Lexicon, with its construction.

    Until this existed the Bench built words and dropped them on the floor:
    nothing it made could enter the library, so nothing it made could ever
    be opened on the Bench, so the verified-slice construction record added
    for exactly that case had no reachable path to it.

    TWO REFUSALS, both about not letting the tool assert what it has just
    finished denying:

    - The definition must be the OWNER'S. Copying the parent word's
      definition onto a coin the contract report just said drops two of
      four parts would be the tool asserting a meaning it disproved one
      line earlier. It is not offered as a default and not accepted from
      the client if it matches the parent.
    - A coin with no definition is refused outright. The six oldest
      entries in this lexicon are titles with nothing attached, and the
      Bench cannot open them at all; minting more of those would be a
      regression with a nice button on it.

    The construction is NOT written here. recorded_construction reads it
    back out of the Bench store at open time, where the seam-verified
    condition is enforced — so a coin whose seam description failed is
    still keepable as a word and still, correctly, has no recorded
    construction."""
    d = request.get_json(force=True) or {}
    parent = str(d.get("parent_title") or "").strip()[:200]
    word = str(d.get("word") or "").strip()[:80]
    definition = str(d.get("definition") or "").strip()[:1500]
    if not word:
        return jsonify({"error": "which coin?"}), 400
    if not definition:
        return jsonify({"error": "This coin needs a definition in your words before it can be kept. "
                                 "The parent's definition is not offered, because the contract "
                                 "report above says which parts this build dropped — writing that "
                                 "meaning onto it would assert something the Bench just denied."}), 400

    stored = cli.load_bench_session(
        parent, str(d.get("concept_id") or "").strip()[:64]
    ) if parent else {}
    if definition.strip().lower() == (stored.get("definition") or "").strip().lower():
        return jsonify({"error": "That is the parent word's definition verbatim. This build did not "
                                 "carry all of it — say what THIS coin means."}), 400

    # is this coin actually one the Bench built? no minting from thin air
    coined = {b.get("word") for r in (stored.get("builds") or []) for b in (r.get("builds") or [])}
    if word not in coined:
        return jsonify({"error": "That coin was not built on this word's Bench."}), 400

    _kcid = (stored.get("concept_id") or "").strip()
    if _kcid:
        # Concept-first: the coin is a NAME attached to the concept — a
        # handle, not a second concept entry (docs/adr-concept-first.md).
        row = cli.record_concept_name(_kcid, word, "coinage",
                                       origin="owner", ruling="kept")
        return jsonify({"kept": True, "word": word,
                        "attached_to_concept": _kcid,
                        "name_uid": row["name_uid"],
                        "construction_recorded": False, "construction": ""})
    before = {c.get("name", "").strip().lower() for c in cli.load_accepted_concepts()}
    if word.strip().lower() in before:
        return jsonify({"error": f"“{word}” is already in your Lexicon."}), 400
    cli.persist_accepted_concept(word, definition, "", status="accepted")
    rec = cli.recorded_construction(word)
    return jsonify({"kept": True, "word": word,
                    "construction_recorded": bool(rec.get("note")),
                    "construction": rec.get("note", "")})


# ---- intake -------------------------------------------------------------

MAX_UPLOAD_BYTES = 12 * 1024 * 1024


@app.route("/api/upload", methods=["POST"])
def api_upload():
    """Take a file in, store it unchanged, derive ONE representation, and
    report both separately. The artifact is the source; the text is a
    derivative and says which it is."""
    f = request.files.get("file")
    if f is None:
        return jsonify({"error": "no file was sent"}), 400
    data = f.read(MAX_UPLOAD_BYTES + 1)
    if len(data) > MAX_UPLOAD_BYTES:
        return jsonify({"error": f"that file is over the {MAX_UPLOAD_BYTES // (1024*1024)}MB limit "
                                 f"for this version."}), 400
    if not data:
        return jsonify({"error": "that file is empty"}), 400

    art = cli.store_artifact(data, f.filename or "")
    if art["kind"] == "unsupported":
        # Plainly refused, not silently mangled into text.
        return jsonify({"error": f"Wordicon can't read this kind of file yet "
                                 f"({art['mime']}). This version takes plain text, "
                                 f"Markdown, PDF, and JPEG/PNG/GIF/WebP images. "
                                 f"A .docx needs saving as PDF or text first.",
                        "artifact": art}), 400
    try:
        rep = cli.represent_artifact(art["artifact_id"], server_gateway())
    except Exception as e:
        return jsonify({"error": cli.explain_component_failure(str(e)), "artifact": art}), 500
    return jsonify({"artifact": art, "representation": _rep_out(rep, art)})


def _rep_out(rep, art):
    """What the client is told about a representation — including, always,
    which representation any later quote check would run against."""
    if not rep:
        return {}
    probe = cli.tier1_verdict("", dict(rep, artifact_kind=art.get("kind")))
    return {
        "rep_id": rep.get("rep_id", ""), "version": rep.get("version", 1),
        "method": rep.get("method", ""), "model": rep.get("model", ""),
        "confirmed": bool(rep.get("confirmed")),
        "text": rep.get("text", ""), "chars": rep.get("chars", 0),
        "note": rep.get("note", {}),
        "needs_check": rep.get("method") == "model_transcription",
        "tier1_if_found": cli.tier1_words(
            "not_applicable_image" if not rep.get("text") and art.get("kind") == "image"
            else ("confirmed_transcription" if rep.get("confirmed")
                  else {"original_text": "original_text",
                        "pdf_text_layer": "pdf_text_layer"}.get(rep.get("method"),
                                                                "unconfirmed_transcription")))[0],
    }


@app.route("/api/representation/confirm", methods=["POST"])
def api_representation_confirm():
    """The owner's act, and the only way a representation becomes confirmed.
    Stored as a NEW version — the model's original reading is never
    overwritten, because an analysis that ran against version 1 has to stay
    readable as having run against version 1."""
    d = request.get_json(force=True) or {}
    art_id = str(d.get("artifact_id") or "").strip()
    text = str(d.get("text") or "")
    art = cli.load_artifact(art_id)
    if not art:
        return jsonify({"error": "no such artifact"}), 400
    prior = cli.current_representation(art_id)
    rep = cli.add_representation(art_id, text, "owner_correction", confirmed=True,
                                 supersedes=prior.get("rep_id", ""))
    return jsonify({"representation": _rep_out(rep, art), "versions": len(cli.load_representations(art_id))})


@app.route("/api/artifact/<artifact_id>")
def api_artifact(artifact_id):
    art = cli.load_artifact(artifact_id)
    if not art:
        return jsonify({"error": "no such artifact"}), 404
    return jsonify({"artifact": art,
                    "representations": [
                        {k: v for k, v in r.items() if k != "text"} | {"chars": r.get("chars", 0)}
                        for r in cli.load_representations(artifact_id)]})


@app.route("/api/bench/library")
def api_bench_library():
    return jsonify(cli.load_bench_library())


@app.route("/api/bench/build", methods=["POST"])
def api_bench_build():
    data = request.get_json(force=True) or {}
    title = str(data.get("title") or "").strip()[:200]
    definition = str(data.get("definition") or "").strip()[:1500]
    method = str(data.get("method") or "").strip()[:60] or "let Wordicon choose"
    materials = [str(m).strip()[:40] for m in (data.get("materials") or [])
                 if str(m).strip()][:cli.MAX_MATERIALS]
    # The contract comes back from the client because the owner may have
    # UNLOCKED a part since it was built — that choice is theirs and the
    # server has no business overriding it. Everything else about each
    # part is re-derived, so a client cannot invent a part or rename one.
    contract = []
    for p in (data.get("contract") or [])[:5]:
        if not isinstance(p, dict) or not (p.get("key") or "").strip():
            continue
        contract.append({"key": str(p["key"])[:40], "name": str(p.get("name") or "")[:60],
                         "gist": str(p.get("gist") or "")[:240],
                         "locked": bool(p.get("locked", True))})
    # THE CONTRACT IS THE OWNER'S, NOT THE MODEL'S. The first live run
    # misread "forgiving those who caused it" as self-pardon — forgiving
    # yourself rather than whoever brought you into existence — and every
    # build below was then faithfully measured against the wrong idea. The
    # code protected a contract that did not represent the concept. Nothing
    # builds until the owner has said this contract is right.
    if not data.get("contract_confirmed"):
        return jsonify({"error": "The meaning contract has to be confirmed before anything is "
                                 "built. The parts were written by a model reading your "
                                 "definition, and a wrong part silently sends every build "
                                 "after it to the wrong target."}), 400
    if not title or not contract:
        return jsonify({"error": "title and a confirmed contract are required"}), 400
    # There is no upper limit. Pick every material on the screen if you want
    # to; a coin made of eleven stems is a bad coin, not an invalid request,
    # and which of those it is was never the tool's call. The floor is
    # arithmetic rather than taste: compounding, blending and root-fusing all
    # need two things to join, an ending or a beginning needs one.
    floor = cli.METHOD_FLOOR.get(method, 2)
    if len(materials) < floor:
        return jsonify({"error": f"“{method}” needs at least {floor} material"
                                 f"{'' if floor == 1 else 's'} — {len(materials)} "
                                 f"{'was' if len(materials) == 1 else 'were'} sent. "
                                 + ("An ending is applied to a stem; there has to be a stem."
                                    if floor == 1 else
                                    "There has to be more than one thing to join.")}), 400
    material_parts = {str(k)[:40]: str(v)[:40]
                      for k, v in (data.get("material_parts") or {}).items()}
    try:
        result = cli.run_bench_build(title, definition, contract,
                                      materials, method, server_gateway(),
                                      material_parts=material_parts)
    except Exception as e:
        return jsonify({"error": cli.explain_component_failure(str(e))}), 500
    # The contract reaching here has been confirmed (checked above), so the
    # store learns that too — otherwise a build could be recorded against a
    # contract the file still calls the model's.
    _bcid = str(data.get("concept_id") or "").strip()[:64]
    cli.save_bench_contract(title, contract, True, concept_id=_bcid)
    cli.save_bench_build(title, result, concept_id=_bcid)
    return jsonify(result)


@app.route("/api/bench/concept", methods=["POST"])
def api_bench_concept():
    """Build the concept — the lane where the Bench's payoff now lives.
    Meaning first, structure second, language third, coinage last and
    sometimes never."""
    data = request.get_json(force=True) or {}
    title = str(data.get("title") or "").strip()[:200]
    definition = str(data.get("definition") or "").strip()[:1500]
    ingredients = []
    for pn in (data.get("ingredients") or [])[:8]:
        if not isinstance(pn, dict) or not (pn.get("key") or "").strip():
            continue
        role = str(pn.get("role") or "supporting").strip().lower()
        ingredients.append({
            "key": str(pn["key"])[:40], "name": str(pn.get("name") or "")[:60],
            "gist": str(pn.get("gist") or "")[:240],
            "role": role if role in cli.CONCEPT_ROLES else "supporting"})
    relations = []
    for i, r in enumerate((data.get("relations") or [])[:8]):
        if not isinstance(r, dict):
            continue
        verb = str(r.get("verb") or "").strip()[:80]
        a, b = str(r.get("a_name") or "").strip()[:60], str(r.get("b_name") or "").strip()[:60]
        if verb and a and b:
            relations.append({"id": f"r{i+1}", "a_name": a, "verb": verb, "b_name": b})
    if not data.get("contract_confirmed"):
        return jsonify({"error": "Confirm the ingredients first — they were written by a "
                                 "model reading your definition, and a wrong one sends the "
                                 "whole structure at the wrong target."}), 400
    if not title or not ingredients:
        return jsonify({"error": "a title and confirmed ingredients are required"}), 400
    try:
        result = cli.run_concept_build(title, definition, ingredients, relations,
                                        server_gateway())
    except Exception as e:
        return jsonify({"error": cli.explain_component_failure(str(e))}), 500
    cli.save_bench_concept(title, result)
    return jsonify(result)


@app.route("/api/bench/concept/names", methods=["POST"])
def api_bench_concept_names():
    """The optional naming stage. Keep-the-existing-name is inserted by
    code as the first option and stands unless the reviewer STAKES an
    improvement — the old design was structurally incapable of that answer
    because it had been ordered to manufacture something."""
    data = request.get_json(force=True) or {}
    title = str(data.get("title") or "").strip()[:200]
    statement = str(data.get("statement") or "").strip()[:1200]
    anatomy = data.get("anatomy") if isinstance(data.get("anatomy"), dict) else {}
    if not title or not statement:
        return jsonify({"error": "a title and a built concept statement are required"}), 400
    try:
        result = cli.run_concept_names(title, statement, anatomy, server_gateway())
    except Exception as e:
        return jsonify({"error": cli.explain_component_failure(str(e))}), 500
    return jsonify(result)


@app.route("/api/bench/correct", methods=["POST"])
def api_bench_correct():
    """The owner overruling one contract verdict on one build.

    This is the pilot's actual instrument. A build reporting "culpability:
    kept" when the material used was *shame* is a semantic slip nothing in
    the code can see, and handing that judgment to a second model would be
    the same kind of thing making the same kind of call. Collect the
    owner's corrections; decide later whether anything can be trained on
    them."""
    d = request.get_json(force=True) or {}
    owner = str(d.get("owner_says") or "").strip()
    if owner not in ("kept", "weakened", "lost", "unstated"):
        return jsonify({"error": "owner_says must be kept, weakened, lost or unstated"}), 400
    return jsonify(cli.record_bench_correction(
        str(d.get("title") or "")[:200], str(d.get("word") or "")[:80],
        str(d.get("part_key") or "")[:40], str(d.get("part_name") or "")[:80],
        str(d.get("model_said") or "")[:20], owner, str(d.get("note") or "")[:600]))


@app.route("/api/bench/corrections")
def api_bench_corrections():
    rows = cli.load_bench_corrections()
    return jsonify({"corrections": rows, "count": len(rows)})


@app.route("/api/judge", methods=["POST"])
def api_judge():
    data = request.get_json(force=True) or {}
    trace_id = data.get("trace_id")
    candidate_title = data.get("candidate_title")
    decision_key = data.get("decision")
    note = (data.get("note") or "").strip()
    concept_id = str(data.get("concept_id") or "").strip()[:64] or None
    # Which PARTS of the candidate failed, as distinct from whether the
    # candidate failed. Lands in the Judgment schema's `failure_axis`, a
    # field that has existed since the corpus objects were written and has
    # never once been populated — same situation concept_id was in. A bare
    # "rejected" threw away the most common real reaction ("the word is
    # wrong, the definition and the research are good") and left nothing in
    # the corpus to learn from.
    VALID_PARTS = ("title", "definition", "contradiction", "axiom", "friction")
    parts_flagged = [str(p) for p in (data.get("parts_flagged") or [])
                     if str(p) in VALID_PARTS][:5]
    if not trace_id or not candidate_title or decision_key not in ("a", "r", "v"):
        return jsonify({"error": "trace_id, candidate_title, and decision (a/r/v) are required"}), 400

    decision = {"a": "accepted", "r": "rejected", "v": "revised"}[decision_key]
    # Event id, minted unique — never derived from the title. The old
    # sha(title+trace) recipe gave two distinct same-titled concepts the
    # SAME id in an append-only log (docs/adr-concept-first.md).
    judgment = Judgment(
        id="jdg_evt_" + uuid.uuid4().hex[:16],
        decision=decision, candidate_text=candidate_title, originating_operation=trace_id,
        decision_source="owner", confidence=1.0, review_status="unreviewed",
        reason=note or None, scope="local_to_concept", concept_id=concept_id,
        failure_axis=",".join(parts_flagged) or None,
    )
    cli.persist_judgment(judgment)
    added = removed = False
    if decision != "accepted":
        # Taking a word back OFF the shelf. This is the half that did not
        # exist: /api/judge could only ever add, so changing your mind about
        # an accepted word wrote the new ruling and left the old word in the
        # lexicon. Coming back with fresh eyes has to be able to undo, or
        # the first ruling is permanent and the log is decoration.
        removed = cli.retract_accepted_concept(candidate_title,
                                                concept_id=concept_id or "")
    if decision == "accepted":
        # Accepted concepts join the already-named check on every later
        # run — this is the corpus actually growing from your judgments.
        # adopted=True marks an established term knowingly taken in (the
        # candidate carried Friction's "existing term wins" verdict).
        _dec = data.get("declined_alias")
        added = cli.persist_accepted_concept(
            candidate_title, (data.get("definition") or "").strip(), trace_id,
            status="adopted" if data.get("adopted") else "accepted",
            alias_of=str(data.get("alias_of") or "").strip()[:200],
            declined_alias=_dec if isinstance(_dec, dict) else None,
            decline_reason=note,
            concept_id=concept_id or "")
    # What the judgment DID to the corpus, not merely that it was filed.
    # These two facts came apart six times already — six accepted words
    # sitting in judgments.jsonl with no lexicon entry behind them — and
    # nothing in the interface could have shown the owner the difference.
    # Counted from the corpus after the write, never predicted before it.
    lex = cli.load_accepted_concepts()
    return jsonify({"recorded": decision, "lexicon_added": bool(added),
                    "lexicon_removed": bool(removed), "lexicon_size": len(lex)})


@app.route("/api/result/<trace_id>")
def api_result(trace_id):
    """Reopen a past run in full — Bone/Flesh/Friction and your recorded
    judgments. Only runs made after result snapshots existed can be
    reopened; older receipts never stored the Flesh/Friction text."""
    path = cli.RESULTS_DIR / f"{trace_id}.json"
    if not path.exists():
        # A door must never open onto an unexplained blank. If the receipt
        # survives, show the receipt and say exactly what is unavailable;
        # only when NOTHING survives is this a resolution failure.
        rpath = cli.RECEIPTS_DIR / f"receipt_{trace_id}.json"
        if rpath.exists():
            try:
                receipt = json.loads(rpath.read_text())
            except (json.JSONDecodeError, OSError):
                receipt = {}
            return jsonify({
                "receipt_only": True, "trace_id": trace_id,
                "operation": receipt.get("operation", ""),
                "created_at": receipt.get("created_at", ""),
                "titles": [c.get("title", "") for c in
                           (receipt.get("candidates") or []) if c.get("title")],
                "n_sources": len(receipt.get("sources") or []),
                "unavailable": "Only the receipt survives: the titles, the "
                               "operation, and the date. The reasoning was "
                               "never stored — this run predates result "
                               "snapshots, and nothing can recover it."})
        return jsonify({"error": "destination could not be resolved — no "
                                  "snapshot and no receipt exist for this "
                                  "run."}), 404
    snapshot = json.loads(path.read_text())

    decisions = {}
    if cli.JUDGMENTS_LOG.exists():
        for line in cli.JUDGMENTS_LOG.read_text().splitlines():
            if not line.strip():
                continue
            j = json.loads(line)
            if j["originating_operation"] == trace_id:
                decisions[j["candidate_text"]] = {"decision": j["decision"], "reason": j.get("reason")}
    snapshot["judgments"] = decisions
    return jsonify(snapshot)


@app.route("/api/concept/<concept_id>")
def api_concept(concept_id):
    """Every judgment recorded against one concept_id — the visibility half
    of the alias-tracking fix, not a reconciliation feature. Revise and
    Wordify carry the original candidate's concept_id forward unchanged
    (see run_revise in wordicon_cli.py), so this is what lets the owner
    actually see "these titles are the same idea" instead of that link
    sitting unused in the judgments log. It does NOT compare verdicts
    across runs, dedupe re-generation, or know about Sprout/Refract/Verify
    results for this concept — those don't carry a concept_id yet. That's
    a real feature, left for later, not silently claimed here."""
    return jsonify({"concept_id": concept_id, "judgments": cli.judgments_for_concept(concept_id)})


@app.route("/api/history")
def api_history():
    receipts_dir = cli.RECEIPTS_DIR
    if not receipts_dir.exists():
        return jsonify({"items": []})

    judgments_by_trace = {}
    if cli.JUDGMENTS_LOG.exists():
        for line in cli.JUDGMENTS_LOG.read_text().splitlines():
            if not line.strip():
                continue
            j = json.loads(line)
            judgments_by_trace.setdefault(j["originating_operation"], []).append(j)

    items = []
    for path in sorted(receipts_dir.glob("*.json"), key=lambda p: p.stat().st_mtime, reverse=True)[:30]:
        receipt = json.loads(path.read_text())
        trace_id = receipt["trace_id"]
        judgments = judgments_by_trace.get(trace_id, [])
        decision_by_title = {j["candidate_text"]: j["decision"] for j in judgments}
        for c in receipt.get("candidates", []):
            items.append({
                "trace_id": trace_id,
                "operation": receipt["operation"],
                "created_at": receipt["created_at"],
                "title": c["title"],
                "decision": decision_by_title.get(c["title"]),
                "receipt_id": receipt["receipt_id"],
            })
    return jsonify({"items": items[:50]})


# How a derived run says which word it came off. The server writes
# `f"sprout: {title}"` at submission and the pipeline rewrites it into this
# fuller form before the snapshot is saved, so this is the shape that is
# actually on disk for all 106 derived runs in the corpus.
_PARENT_RX = re.compile(
    r"^\s*(sprout|refract|revise|wordify|reconsider)\s+of\s+[\u2018'\"](.+?)[\u2019'\"]"
    r"\s*(?:per owner reasoning)?\s*:", re.I)


def _titles_produced(snap):
    """Every name a run put into the world, whatever mode made it."""
    out = []
    for c in (snap.get("candidates") or []):
        t = ((c.get("bff") or {}).get("title") or "").strip()
        if t:
            out.append(t)
    for r in (snap.get("refractions") or []):
        t = (r.get("title") or r.get("coin") or "").strip()
        if t:
            out.append(t)
    for th in (snap.get("threads") or []):
        t = (th.get("title") or "").strip()
        if t:
            out.append(t)
    return out


def _lineage(snaps_full):
    """Which run each derived run came off, and — always — HOW that was
    established.

    Sprouts carry parent_trace_id in the snapshot; refractions and
    revisions never have. Their only tie to the parent is the sentence the
    pipeline wrote into input_text, so the link is READ BACK OUT of that
    and matched against the most recent earlier run that produced a word by
    that name. That works on 91 of the 106 derived runs here, which is
    worth having, but it is a reconstruction and not a record — the same
    difference the Bench draws between a construction you recorded and one
    guessed from spelling. So every link ships with `via`: "recorded" or
    "derived". Nothing in the interface may present the two as equal.
    """
    order = sorted(snaps_full.values(), key=lambda d: d.get("created_at") or "")
    seen = []          # (created_at, lowercase title, trace) in time order
    link = {}
    for d in order:
        trace = d.get("trace_id") or ""
        rec = (d.get("parent_trace_id") or "").strip()
        if rec:
            link[trace] = {"parent": rec, "parent_title": (d.get("via") or "").strip(),
                           "via": "recorded"}
        else:
            m = _PARENT_RX.match(d.get("input_text") or "")
            if m:
                want = m.group(2).strip().lower()
                mine = d.get("created_at") or ""
                # LAST match wins: the same title gets coined more than
                # once here, and a revision belongs to the run he was
                # looking at, not the first one that ever used the word.
                # The `at <= mine` guard is defensive rather than load-
                # bearing — `seen` is filled in creation order, so nothing
                # later is in it yet — and it stays so that reordering this
                # loop later cannot silently invent backwards lineage.
                hit = ""
                for at, name, tr in seen:
                    if name == want and at <= mine:
                        hit = tr
                if hit:
                    link[trace] = {"parent": hit, "parent_title": m.group(2).strip(),
                                   "via": "derived"}
                else:
                    # Named a parent that no surviving run produced — the
                    # twenty runs from before snapshots existed are exactly
                    # this. Say so rather than dropping the relationship.
                    link[trace] = {"parent": "", "parent_title": m.group(2).strip(),
                                   "via": "parent lost"}
        for t in _titles_produced(d):
            seen.append((d.get("created_at") or "", t.lower(), trace))
    return link


@app.route("/api/anchors")
def api_anchors():
    """The sources, read as themselves.

    Sprout has always written what the source shows separately from the
    reading laid over it, and the split was enforced so the two could be
    told apart on a card. The side effect is that the corpus contains a
    few hundred short accounts of real works, each written under an
    explicit instruction not to mention the concept that went looking —
    and there has never been anywhere to read them except inside the trail
    that produced them.

    This endpoint is keyed by the SOURCE. Which of his words reached it is
    demoted to a fold at the bottom of each entry, because the point is to
    be able to read about Beowulf without reading about Held Ledger.
    """
    snaps = []
    if cli.RESULTS_DIR.exists():
        for path in cli.RESULTS_DIR.glob("*.json"):
            try:
                snap = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            if isinstance(snap, dict) and snap.get("threads"):
                snaps.append(snap)
    canon, canon_notes = cli.concept_canon(with_notes=True)
    anchors = cli.anchor_index(snaps, canon)
    return jsonify({
        "anchors": anchors,
        "n_anchors": len(anchors),
        "n_with_account": sum(1 for a in anchors if a["accounts"]),
        "n_withheld": sum(1 for a in anchors if a["account_missing"]),
        "n_multi": sum(1 for a in anchors if a["multi_account"]),
        # Canonical, not raw: a rename on record is one concept twice.
        "n_crossed": sum(1 for a in anchors if a["n_canonical"] > 1),
        # Identities INFERRED rather than stated — two lexicon entries
        # collapsed because their definitions are byte-identical. A rename
        # family is stated by the record and needs no note; an inference
        # that changes a count is never silent.
        "canon_notes": canon_notes,
    })


@app.route("/api/library")
def api_library():
    """The full archive — every run ever made, uncapped, plus the Lexicon
    (accepted concepts). RECENT stays a short window; this is the shelf
    nothing falls off of. Search happens client-side; this just returns
    everything, which stays small because each run is one compact row."""
    judgments_by_trace = {}
    if cli.JUDGMENTS_LOG.exists():
        for line in cli.JUDGMENTS_LOG.read_text().splitlines():
            if not line.strip():
                continue
            j = json.loads(line)
            judgments_by_trace.setdefault(j["originating_operation"], {})[j["candidate_text"]] = j["decision"]

    snaps, snaps_full = {}, {}
    if cli.RESULTS_DIR.exists():
        for path in cli.RESULTS_DIR.glob("*.json"):
            try:
                snap = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            snaps_full[snap.get("trace_id")] = snap
            snaps[snap.get("trace_id")] = {
                "mode": snap.get("mode", ""),
                # The FULL input, not a 160-character stub. This is his
                # writing; truncating it in the one view meant to hand it
                # back is the same loss in a smaller font.
                "input_text": snap.get("input_text") or "",
                "produced": _titles_produced(snap),
                "trail": [t.get("title", "") for t in (snap.get("trail") or [])][:12],
            }
    lineage = _lineage(snaps_full)

    runs = []
    if cli.RECEIPTS_DIR.exists():
        for path in sorted(cli.RECEIPTS_DIR.glob("*.json"),
                            key=lambda p: p.stat().st_mtime, reverse=True):
            try:
                receipt = json.loads(path.read_text())
            except (json.JSONDecodeError, OSError):
                continue
            trace_id = receipt["trace_id"]
            snap = snaps.get(trace_id)
            runs.append({
                "trace_id": trace_id,
                "operation": (snap or {}).get("mode") or receipt.get("operation", ""),
                "created_at": receipt.get("created_at", ""),
                "titles": [c.get("title", "") for c in receipt.get("candidates", [])],
                "decisions": judgments_by_trace.get(trace_id, {}),
                "input_preview": (snap or {}).get("input_text", ""),
                "produced": (snap or {}).get("produced") or
                            [c.get("title", "") for c in receipt.get("candidates", [])],
                "trail": (snap or {}).get("trail") or [],
                "has_snapshot": trace_id in snaps,
                # Empty for a root run; for a derived one it names the run
                # it came off AND how that was established.
                "parent": (lineage.get(trace_id) or {}).get("parent", ""),
                "parent_title": (lineage.get(trace_id) or {}).get("parent_title", ""),
                "parent_via": (lineage.get(trace_id) or {}).get("via", ""),
            })

    # EVERY word this tool has ever put in front of him, not only the ones
    # he kept. 674 titles exist in the corpus and 83 carry a ruling; the
    # other 591 were rendered once and then unreachable forever. A library
    # that shows only the accepted words is a trophy case, and a trophy
    # case cannot be revised.
    decisions_now = cli.latest_decisions()
    acc_by_name = {(c.get("name") or "").strip().lower(): c
                   for c in cli.load_accepted_concepts()}
    # The bff of the run that produced each title, kept so standing can be
    # computed from what was actually recorded rather than re-derived.
    bff_by_key = {}
    words_by_key = {}
    for snap in snaps_full.values():
        at = snap.get("created_at") or ""
        mode = snap.get("mode", "")
        trace = snap.get("trace_id", "")
        found = []
        for c in (snap.get("candidates") or []):
            b = c.get("bff") or {}
            _t = (b.get("title") or "").strip().lower()
            if _t and (_t not in bff_by_key or at >= bff_by_key[_t][0]):
                bff_by_key[_t] = (at, b)
            found.append((b.get("title") or "",
                          ((b.get("flesh") or {}).get("definition") or "")))
        for r in (snap.get("refractions") or []):
            found.append((r.get("title") or r.get("coin") or "", r.get("gloss") or ""))
        for th in (snap.get("threads") or []):
            found.append((th.get("title") or "", th.get("definition") or ""))
        for title, definition in found:
            title = (title or "").strip()
            if not title:
                continue
            key = title.lower()
            prev = words_by_key.get(key)
            # Latest run wins the row, but never let a later run with no
            # definition blank out a definition an earlier one recorded.
            if prev and prev["created_at"] > at:
                if not prev["definition"] and definition:
                    prev["definition"] = definition.strip()
                continue
            words_by_key[key] = {
                "name": title, "definition": (definition or "").strip()
                or (prev or {}).get("definition", ""),
                "mode": mode, "trace_id": trace, "created_at": at,
            }
    # Judged titles whose run no longer survives still belong on the shelf.
    for key, d in decisions_now.items():
        if key not in words_by_key:
            words_by_key[key] = {"name": d["title"], "definition": "", "mode": "",
                                 "trace_id": d.get("trace", ""), "created_at": ""}
    words = []
    for key, w in words_by_key.items():
        d = decisions_now.get(key) or {}
        acc = acc_by_name.get(key) or {}
        words.append({**w,
                      "definition": w["definition"] or (acc.get("definition") or ""),
                      "decision": d.get("decision", "") or "undecided",
                      "rulings": d.get("times", 0),
                      "changed_mind": bool(d.get("changed")),
                      "in_lexicon": key in acc_by_name,
                      "accepted_at": acc.get("accepted_at", ""),
                      # Aliases nest under their family head on the shelf.
                      # Six names for one four-rung ladder is six names, not
                      # six ideas, and the count has to know the difference.
                      "alias_of": acc.get("alias_of", "") or "",
                      # And a word kept as its own concept over a warning
                      # says so on the shelf, with what it was warned about.
                      "declined_identical": acc.get("declined_identical") or [],
                      "decline_reason": acc.get("decline_reason", "") or "",
                      # What the RECORD says, beside what he ruled. Two bands,
                      # two questions: his ruling is his and final; standing
                      # is what happened on the way in. Measured by running
                      # this function over his corpus: of 65 accepted words 63
                      # join a run, and of those 13 were kept over Friction's
                      # recorded objection, 6 rest on an anchor mechanically
                      # absent from its source, 6 carry an anchor nobody
                      # support-checked, 2 Friction called already named, 2
                      # were never checked at all — and every one of the 65
                      # rendered with the same green "kept" chip.
                      "standing": cli.concept_standing((bff_by_key.get(key) or (None, {}))[1]),
                      "definition_source": acc.get("definition_source", "") or "",
                      "definition_history": acc.get("definition_history") or [],
                      "grounding_reset_at": acc.get("grounding_reset_at", "") or "",
                      # Re-judging needs the run the ruling was filed
                      # against, or the new row lands under a different key
                      # and the old one keeps standing.
                      "judge_trace": d.get("trace", "") or w["trace_id"]})
    words.sort(key=lambda w: w["name"].lower())

    lexicon = [{
        "name": c.get("name", ""),
        "definition": c.get("definition", ""),
        "accepted_from": c.get("accepted_from", ""),
        "accepted_at": c.get("accepted_at", ""),
        "alias_of": c.get("alias_of", ""),
        "declined_identical": c.get("declined_identical") or [],
        "decline_reason": c.get("decline_reason", ""),
    } for c in cli.load_accepted_concepts()]

    # The Bench's own shelf. Compacted here rather than sent whole: a
    # benched word's file carries every opening's full diagnosis, and the
    # Library only needs enough to find it and see what happened.
    bench = cli.load_bench_library()
    benched = [{
        "title": d.get("title", ""),
        "definition": (d.get("definition") or "")[:200],
        "opens": len(d.get("opens") or []),
        "build_rounds": len(d.get("builds") or []),
        "words": sorted({b.get("word", "") for r in (d.get("builds") or [])
                         for b in (r.get("builds") or []) if b.get("word")}),
        "contract": [{"name": p2.get("name", ""), "gist": p2.get("gist", ""),
                      "locked": bool(p2.get("locked", True))}
                     for p2 in (d.get("contract") or [])],
        "contract_source": d.get("contract_source", ""),
        "contract_confirmed_at": d.get("contract_confirmed_at", ""),
        "corrections": d.get("corrections") or [],
        "created_at": d.get("created_at", ""),
        "updated_at": d.get("updated_at", ""),
    } for d in bench.get("words") or []]

    return jsonify({"documents": _library_documents_payload(),
                     "lexicon": lexicon, "words": words, "runs": runs, "bench": benched,
                    "standing_keys": cli.standing_keys(),
                    "inputs": cli.load_inputs(500),
                    "orphan_corrections": bench.get("orphan_corrections") or []})


if __name__ == "__main__":
    import sys as _sys
    if "--rotate-secret" in _sys.argv:
        gate.rotate_master()
        print("Master secret rotated. Every paired device is signed out; "
              "each pairs again with the code printed at the next start.")
        raise SystemExit(0)
    port = int(os.environ.get("PORT", 8420))
    # The corpus lease: this process becomes the corpus's only writer for
    # its whole life (flock — released by the OS even on a crash). A
    # standalone `vault.py init|backup`, or a second server on the same
    # corpus, refuses instead of racing.
    if not vault.hold_lease("wordicon server"):
        print("REFUSED to start: the corpus is already in use by "
              f"{vault.lease_holder() or 'another process'}.\n"
              "Two writers on one corpus is how backups go silently "
              "wrong. Stop that process first.")
        raise SystemExit(3)
    host = gate.bind_host()
    gate.ensure_master()
    code = gate.new_pairing_code()
    print(f"\nWordicon server starting on port {port}.")
    if host == "0.0.0.0":
        print("LAN: ON — reachable by devices on this Wi-Fi, behind the gate.")
        print("On your PHONE (same Wi-Fi as this computer), open:")
        print(f"  http://<this-computer's-local-IP>:{port}")
        print("Find your local IP with: ipconfig getifaddr en0   (or en1 on some Macs)")
    else:
        print("LAN: OFF — loopback only. For the phone, start with: "
              "WORDICON_LAN=1 python3 server.py")
    print(f"\nPAIRING CODE for new devices (typed once, on /pair): {code}")
    print("The gate is a home-LAN access lock, not encrypted transport — "
          "plain HTTP is fine on your own Wi-Fi, not confidential on shared "
          "or hospital networks.\n")
    # Which gateway is actually about to run, said out loud. Without this
    # a missing key degrades to the mock gateway in silence, and a mock run
    # is indistinguishable from a real one at a glance — same layout, same
    # verdicts, canned content. That is the same failure as a green
    # "verified" badge over an unchecked claim, one layer down.
    try:
        gw = server_gateway()
        if gw.is_external:
            print(f"Gateway: {gw.name.upper()} — live model calls, "
                  f"model {os.environ.get('WORDICON_MODEL', '?')}. Runs cost money.")
        else:
            print("Gateway: MOCK — NO LIVE MODEL CALLS. Every result will be a canned "
                  "fixture that looks exactly like a real run. Set ANTHROPIC_API_KEY "
                  "and WORDICON_MODEL (in .env or the environment) for real output.")
    except Exception as e:
        # Full traceback, deliberately: on the night brew swapped the
        # interpreter, this line's bare str(e) said only "invalid literal
        # for int() with base 10: ''" and the real culprit (truststore's
        # macOS version parse, three imports deep) stayed invisible.
        traceback.print_exc()
        print(f"Gateway: MISCONFIGURED — {e}\n  Nothing will run until this is fixed.")
    print(f"Config source: .env {'found' if (REPO_ROOT / '.env').exists() else 'not present'}"
          f" · ANTHROPIC_API_KEY {'set' if os.environ.get('ANTHROPIC_API_KEY') else 'NOT set'}"
          f" · WORDICON_MODEL {os.environ.get('WORDICON_MODEL') or 'NOT set'}\n")
    if notify._configured():
        print("Email notifications: ON — you'll get an email when a job finishes.")
    else:
        print("Email notifications: OFF — set WORDICON_NOTIFY_EMAIL_FROM and "
              "WORDICON_NOTIFY_EMAIL_APP_PASSWORD to turn them on (see notify.py).")
    print("Jobs run in the background: this Terminal window and your Mac need to "
          "stay open and awake for a submitted job to finish, even though the "
          "phone app itself can be closed.\n")
    _vst = vault.status()
    if _vst["initialized"]:
        print(f"Vault: {_vst['n_vaults']} vault(s), "
              f"{_vst['total_bytes'] // 1024} KB at {vault.destination()}")
        threading.Thread(target=lambda: vault.backup(reason="start"),
                         daemon=True).start()
    else:
        print("Vault: NOT INITIALIZED — the corpus exists on this disk only. "
              "Set up encrypted backups with: python3 scripts/vault.py init")
    vault.start_scheduler()
    import atexit
    atexit.register(lambda: bool(vault.load_config())
                    and vault.backup(reason="shutdown", stage_timeout=10))
    # threaded=True so a poll request (GET /api/jobs/<id>) isn't blocked behind
    # a job submission — the job itself already runs on its own thread, this
    # is just about the dev server being able to serve more than one request
    # at a time.
    app.run(host=host, port=port, debug=False, threaded=True)
