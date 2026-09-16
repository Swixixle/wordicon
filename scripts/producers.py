"""Investigation adapters (workspace-v2 slice F, instructions §10).

One adapter per producer, each declaring the contract it was built
against — route, method, auth reference, payload, side effects, limits,
id correlation, signed-byte format — and where that contract came from.
The contracts here were read from the producers' own source for report 80
(2026-09-15); none has been verified against a deployment from this
workspace, so LIVE STARTS ARE DISABLED by the adapter itself until the
owner records, on the connector, that the deployment was verified. Lookup
and import (a read of the producer's index, a signed export verified
against a pinned key) are the existing federation contract and stay as
they were. In test mode, a declared development connector on loopback
(the journeys' mock producer) may start, so the mechanism is proven
without a deployment.

An investigation is an operation in the store (slice D): reserved under a
request key, claimed, its POST preceded by a dispatch intent and followed
by its outcome with the upstream id, its artifact retrieved through the
import verifier and linked by deposition id, its receipt state recorded
apart from the live output. "Signature valid" means the bytes are the
producer's; it never means the research is true.

Nothing here follows a redirect, accepts a client-supplied URL as a
backend, or writes a credential anywhere: the credential is read from the
environment at the moment of the request through the connector's
reference, as the fetcher already does.
"""
from __future__ import annotations

import json
import time
import urllib.error
import urllib.parse
import urllib.request

import federation
import testmode

ADAPTERS = {
    "ethicalalt": {
        "display": "EthicalAlt",
        "adapter_version": "ethicalalt-adapter/1",
        "connector_kind": "ethicalalt",
        "contract_source": "EthicalAlt server source, read for report 80 on 2026-09-15; not verified against a deployment from this workspace",
        "lookup": {"method": "GET", "path": "/api/profiles/index", "auth": "none", "meaning": "the producer's own profile index — a read"},
        "artifact": {"method": "GET", "path": "/api/profiles/{id}/export/v2", "signed": True, "verifier": "federation.import_package (ethicalalt.export.v2 under a pinned key)"},
        "start": {"method": "POST", "path": "/api/investigate", "payload": ("brand", "session_id"), "auth": "none", "synchronous": True,
                  "upstream_id": "session_id, minted here and echoed by the producer", "status": None, "cancel": None,
                  "side_effects": "the producer researches the brand and creates or updates its profile; its own model lane is called on its side and billed there",
                  "limits": "unknown — the producer's orchestrator is environment-gated on its side", "id_correlation": "the profile slug the producer returns, then the signed export under that slug"},
        "receipt": {"method": "POST", "path": "/api/receipt/generate", "signed": True, "meaning": "a signed receipt over the export's bytes, verified against the pinned key"},
        "subject": "a company or brand name",
    },
    "open_case": {
        "display": "Open Case",
        "adapter_version": "open-case-adapter/1",
        "connector_kind": "open_case",
        "contract_source": "Open Case server source, read for report 80 on 2026-09-15; not verified against a deployment from this workspace",
        "lookup": {"method": "GET", "path": "/api/v1/cases/exportable", "auth": "bearer", "meaning": "the cases the key may export — a read"},
        "artifact": {"method": "GET", "path": "/api/v1/cases/{id}/export", "signed": True, "verifier": "federation.import_package (open_case.seal.v1 under a pinned key)"},
        "start": {"method": "POST", "path": "/api/v1/cases/{id}/investigate", "payload": ("handle",), "auth": "bearer", "synchronous": True,
                  "upstream_id": "the case id the request names", "status": None, "cancel": None,
                  "side_effects": "the producer enriches the case; a provider is called on its side and billed there", "limits": "unknown",
                  "id_correlation": "the case id, then the signed export under that id"},
        "receipt": {"method": "POST", "path": "/cases/{id}/snapshot", "signed": True, "meaning": "a signed snapshot of the case"},
        "subject": "a case id (36 characters) and the handle to investigate",
    },
    "public_eye": {
        "display": "PUBLIC EYE",
        "adapter_version": "public-eye-adapter/0",
        "connector_kind": None,
        "contract_source": "PUBLIC EYE source (formerly FRAME), read for report 80 on 2026-09-15",
        "start": {"method": "POST", "path": "/v1/jobs", "payload": ("url",), "auth": "unknown", "synchronous": False, "status": "GET /v1/jobs/{id} (+SSE)", "cancel": None,
                  "side_effects": "a job on the producer; its job store is in memory on its side", "limits": "unknown", "id_correlation": "the job id"},
        "receipt": {"method": "POST", "path": "/v1/receipts/verify", "signed": True},
        "why_unavailable": "no connector kind exists for this producer yet; the connector contract (origin, credential reference, pinned key) has to be declared before a lookup or a start can be derived",
        "subject": "an article or podcast URL",
    },
    "rabbit_hole": {
        "display": "Rabbit Hole",
        "adapter_version": "none",
        "connector_kind": None,
        "contract_source": "repository not identified",
        "why_unavailable": "your separate application; its repository was not identified, so nothing is represented here — not Explore related ideas, not EthicalAlt's deep mode",
        "subject": "",
    },
}

FETCH_TIMEOUT_S = 60.0
MAX_BYTES = 8_000_000


class AdapterError(Exception):
    """outcome: 'not_sent' (refused before the boundary), 'answered' (the
    producer answered with an error — a known failure) or 'unknown' (the
    request may have arrived and no answer came back)."""
    def __init__(self, message: str, status: int = 400, nothing_sent: bool = True, outcome: str = ""):
        super().__init__(message)
        self.status = status
        self.nothing_sent = nothing_sent
        self.outcome = outcome or ("not_sent" if nothing_sent else "answered")


def adapter(producer: str) -> dict | None:
    return ADAPTERS.get(producer)


def _connector_for(producer: str) -> dict | None:
    kind = (ADAPTERS.get(producer) or {}).get("connector_kind")
    if not kind:
        return None
    conns = [c for c in federation.load_connectors(include_disabled=True) if c.get("producer") == kind]
    if not conns:
        return None
    return sorted(conns, key=lambda x: (not x.get("enabled"), x.get("connector_id")))[0]


def live_start_ruling(connector: dict | None) -> dict:
    """Whether the owner recorded that this connector's deployment was
    verified for starting — a ruling in the connector log, never a
    default. Returns {"enabled": bool, "by": ..., "note": ..., "at": ...}."""
    if not connector:
        return {"enabled": False}
    rows = [r for r in federation._rows(federation.connectors_log())
            if r.get("kind") == "live_start" and r.get("connector_id") == connector.get("connector_id")]
    if not rows:
        return {"enabled": False}
    last = rows[-1]
    return {"enabled": bool(last.get("enabled")), "by": last.get("by", ""), "note": last.get("note", ""), "at": last.get("recorded_at", "")}


def rule_live_start(connector_id: str, enabled: bool, note: str = "", by: str = "owner") -> dict:
    """The owner's ruling that a connector's deployment was verified for
    starting investigations (or that it is not). Recorded, never
    inferred; never made by this code."""
    c = federation.get_connector(connector_id)
    if c is None:
        raise AdapterError("no such connector", 404)
    return federation._append(federation.connectors_log(), {"kind": "live_start", "connector_id": connector_id, "enabled": bool(enabled),
                                                             "note": str(note or "")[:300], "by": by})


def readiness(producer: str, wants: str) -> dict:
    """Derived per capability from the record (§10): configured, contract
    supported, credentials, the last explicit connection check, lookup
    available, start available, deployment verified, reachable at the
    last check. No remote check is made here."""
    ad = ADAPTERS.get(producer)
    out = {"producer": producer, "configured": False, "enabled": False, "contract": "unknown", "credential": "not required",
           "last_check": "never tried", "reachable_last": None, "deployment_verified": False, "lookup_available": False,
           "start_available": False, "available": False, "reason": "", "adapter_version": (ad or {}).get("adapter_version", "none"),
           "contract_source": (ad or {}).get("contract_source", ""), "connector_id": ""}
    if not ad:
        out["reason"] = "no adapter for this producer"
        return out
    if not ad.get("connector_kind"):
        out["reason"] = ad.get("why_unavailable", "no connector kind")
        out["contract"] = "declared, not connectable" if ad.get("start") else "none"
        return out
    c = _connector_for(producer)
    if not c:
        out["reason"] = "no connector registered"
        out["contract"] = "read-only (locate, import, verify)" if wants == "lookup" else "start declared (" + ad["start"]["method"] + " " + ad["start"]["path"] + "), fixture-proven"
        return out
    out.update({"configured": True, "enabled": bool(c.get("enabled")), "connector_id": c.get("connector_id"),
                "last_check": c.get("status") or "never tried", "last_success_at": c.get("last_success_at") or "",
                "reachable_last": (True if str(c.get("status") or "").startswith("reachable") else (False if str(c.get("status") or "").startswith("last attempt failed") else None))})
    needs_cred = (ad.get("start", {}).get("auth") == "bearer") if wants == "start" else (federation.PRODUCERS.get(ad["connector_kind"], {}).get("auth") == "bearer")
    if needs_cred:
        out["credential"] = "present" if c.get("credential_configured") else "missing"
    ruling = live_start_ruling(c)
    out["deployment_verified"] = bool(ruling.get("enabled"))
    out["live_start_ruling"] = ruling
    if wants == "lookup":
        out["contract"] = "read-only (locate, import, verify)"
        if not c.get("enabled"):
            out["reason"] = "the connector is disabled"
        elif needs_cred and not c.get("credential_configured"):
            out["reason"] = "the credential named on the connector is not present"
        else:
            out["lookup_available"] = out["available"] = True
        return out
    out["contract"] = f"start declared: {ad['start']['method']} {ad['start']['path']} — {ad['contract_source']}"
    if not c.get("enabled"):
        out["reason"] = "the connector is disabled"
    elif needs_cred and not c.get("credential_configured"):
        out["reason"] = "the credential named on the connector is not present"
    elif ruling.get("enabled"):
        out["start_available"] = out["available"] = True
        out["reason"] = ""
    elif testmode.active() and c.get("dev_loopback"):
        out["start_available"] = out["available"] = True
        out["reason"] = "test mode: a declared development connector on loopback (the fixture producer)"
        out["fixture_only"] = True
    else:
        out["reason"] = ("starting is disabled until the deployment is verified: the start contract is pinned from source, not proven "
                         "against this connector's deployment — record the verification on the connector to enable it")
    return out


# ---- the bounded POST ------------------------------------------------------------------

def post_json(connector: dict, path: str, body: dict, auth: str = "none") -> dict:
    """POST JSON to a configured connector under the same rules as the
    fetcher: the path is the contract's, the origin is the connector's, no
    redirect is followed, the body is bounded, the credential comes from
    the environment through the connector's reference."""
    if not connector:
        return {"ok": False, "outcome": "not_configured", "detail": "no such connector"}
    if not connector.get("enabled", True):
        return {"ok": False, "outcome": "disabled", "detail": "the connector is disabled"}
    if not path.startswith("/") or ".." in path or "://" in path:
        return {"ok": False, "outcome": "origin_refused", "detail": "a path only"}
    url = connector["base_url"].rstrip("/") + path
    if federation._origin_of(url) != connector.get("origin"):
        return {"ok": False, "outcome": "origin_refused", "detail": "the request would leave the connector's origin"}
    headers = {"Accept": "application/json", "Content-Type": "application/json", "User-Agent": "Nikodemus-connector/1"}
    if auth == "bearer":
        cred = federation._credential_value(connector.get("credential_ref", ""))
        if not cred:
            return {"ok": False, "outcome": "credential_unavailable", "detail": f"set {connector.get('credential_ref') or 'a credential_ref'} in the server's environment"}
        headers["Authorization"] = "Bearer " + cred
    data = json.dumps(body, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(url, data=data, headers=headers, method="POST")
    opener = urllib.request.build_opener(federation._NoRedirect())
    t0 = time.monotonic()
    try:
        with opener.open(req, timeout=FETCH_TIMEOUT_S) as resp:
            status = resp.status
            raw = federation._read_bounded(resp, MAX_BYTES)
    except federation._Oversized:
        return {"ok": False, "outcome": "oversized", "detail": f"the reply exceeded {MAX_BYTES} bytes"}
    except urllib.error.HTTPError as e:
        if e.code in (301, 302, 303, 307, 308):
            return {"ok": False, "outcome": "redirect_refused", "detail": "the producer answered with a redirect; not followed"}
        if e.code in (401, 403):
            return {"ok": False, "outcome": "unauthorized", "detail": f"HTTP {e.code}", "status": e.code}
        if e.code == 404:
            return {"ok": False, "outcome": "not_found", "detail": "HTTP 404", "status": 404}
        return {"ok": False, "outcome": "producer_error", "detail": f"HTTP {e.code}", "status": e.code}
    except urllib.error.URLError as e:
        return {"ok": False, "outcome": "unreachable", "detail": federation._scrub(str(e.reason))[:200]}
    except (TimeoutError, OSError) as e:
        return {"ok": False, "outcome": "unreachable", "detail": federation._scrub(str(e))[:200]}
    elapsed = round(time.monotonic() - t0, 3)
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "outcome": "invalid_json", "detail": "the reply was not JSON", "status": status, "elapsed_s": elapsed}
    return {"ok": True, "status": status, "json": obj, "bytes": len(raw), "elapsed_s": elapsed}


# ---- prepare / start / status / recover / retrieve / verify -----------------------------------

def prepare(producer: str, subject_text: str, inputs: dict | None = None) -> dict:
    """What a start would send and what it would mean — validated locally,
    nothing sent. Returns the spec the proposal freezes."""
    ad = ADAPTERS.get(producer)
    if not ad or not ad.get("connector_kind") or not ad.get("start"):
        raise AdapterError((ad or {}).get("why_unavailable") or "no start contract for this producer", 409)
    text = " ".join(str(subject_text or "").split())
    if not text:
        raise AdapterError(f"an investigation needs {ad['subject']}", 400)
    c = _connector_for(producer)
    rd = readiness(producer, "start")
    spec = {"producer": producer, "adapter_version": ad["adapter_version"], "connector_id": (c or {}).get("connector_id", ""),
            "method": ad["start"]["method"], "path": ad["start"]["path"], "auth": ad["start"]["auth"], "synchronous": ad["start"]["synchronous"],
            "payload_fields": list(ad["start"]["payload"]), "side_effects": ad["start"]["side_effects"], "limits": ad["start"]["limits"],
            "cost": "unknown — the producer's own calls are billed on its side; nothing is priced here", "readiness": rd}
    if producer == "ethicalalt":
        spec["brand"] = text[:200]
    elif producer == "open_case":
        parts = text.split()
        case_id = parts[0] if parts else ""
        import re as _re
        if not _re.match(federation.PRODUCERS["open_case"]["id_pattern"], case_id):
            raise AdapterError("an Open Case investigation names the case id first (36 characters), then the handle", 400)
        spec["case_id"] = case_id
        spec["handle"] = " ".join(parts[1:])[:200]
        if not spec["handle"]:
            raise AdapterError("an Open Case investigation names the handle to investigate after the case id", 400)
    return spec


def start(op_id: str, spec: dict, session_id: str) -> dict:
    """The one outbound POST, at the boundary: a dispatch intent event
    before, the outcome with the upstream id after. Returns what the
    producer said, never more than the record holds."""
    import operations as ops
    producer = spec["producer"]
    ad = ADAPTERS[producer]
    c = federation.get_connector(spec.get("connector_id") or "") or _connector_for(producer)
    rd = readiness(producer, "start")
    if not rd["start_available"]:
        raise AdapterError(f"{ad['display']} cannot be started: {rd['reason']}", 409)
    if producer == "ethicalalt":
        path, body = ad["start"]["path"], {"brand": spec["brand"], "session_id": session_id}
        upstream = session_id
    else:
        path, body = ad["start"]["path"].replace("{id}", spec["case_id"]), {"handle": spec["handle"]}
        upstream = spec["case_id"]
    ops.event(op_id, "stage_intent", stage=f"{ad['start']['method']} {path}", upstream_id=upstream,
              detail={"producer": producer, "adapter_version": ad["adapter_version"], "fields": list(body.keys()), "synchronous": ad["start"]["synchronous"]})
    r = post_json(c, path, body, auth=ad["start"]["auth"])
    ops.event(op_id, "stage_end", stage=f"{ad['start']['method']} {path}", upstream_id=upstream, outcome="ok" if r.get("ok") else "error",
              detail={"outcome": r.get("outcome", "ok"), "status": r.get("status"), "elapsed_s": r.get("elapsed_s"), "detail": r.get("detail", "")})
    federation._record_attempt(c["connector_id"], "ok" if r.get("ok") else r.get("outcome", "error"), r.get("detail", "start"), ok=bool(r.get("ok")), object_id=upstream)
    if not r.get("ok"):
        unknown = r.get("outcome") == "unreachable"      # a connection or read failure: whether the request arrived is not known
        raise AdapterError(f"the producer did not accept the start: {r.get('outcome')} — {r.get('detail')}", 502, nothing_sent=False,
                           outcome=("unknown" if unknown else "answered"))
    reply = r["json"] if isinstance(r["json"], dict) else {}
    out = {"upstream_id": upstream, "producer_state": {k: reply.get(k) for k in ("status", "profile_id", "case_id", "session_id", "job_id", "message") if k in reply},
           "object_id": str(reply.get("profile_id") or reply.get("case_id") or (spec.get("case_id") or "")), "reply_keys": sorted(reply.keys())[:30]}
    return out


def retrieve(op_id: str, spec: dict, object_id: str) -> dict:
    """The artifact: the producer's signed export under the id the start
    returned, through the existing import verifier — kept apart from the
    live reply, verified against the pinned key, linked by deposition id."""
    import operations as ops
    producer = spec["producer"]
    ad = ADAPTERS[producer]
    c = federation.get_connector(spec.get("connector_id") or "") or _connector_for(producer)
    if not object_id:
        return {"ok": False, "outcome": "no_object_id", "detail": "the producer named no object to retrieve"}
    ops.event(op_id, "stage_intent", stage=f"GET {ad['artifact']['path']}", upstream_id=object_id, detail={"artifact": True})
    try:
        res = federation.import_from_connector(c, object_id)
    except Exception as e:  # noqa: BLE001
        ops.event(op_id, "stage_end", stage=f"GET {ad['artifact']['path']}", upstream_id=object_id, outcome="error", detail={"exception": type(e).__name__, "message": str(e)[:200]})
        return {"ok": False, "outcome": "import_failed", "detail": str(e)[:200]}
    ok = bool(res.get("ok"))
    # import_from_connector answers flat: deposition_id, verification, duplicate — the deposition itself is in custody
    dep = federation.get_deposition(res.get("deposition_id", "")) if ok and res.get("deposition_id") else None
    if dep is not None:
        res["deposition"] = dep
    ops.event(op_id, "stage_end", stage=f"GET {ad['artifact']['path']}", upstream_id=object_id, outcome="ok" if ok else "error",
              detail={"outcome": res.get("outcome", "imported" if ok else "failed"), "deposition_id": res.get("deposition_id", ""),
                      "verification": res.get("verification", ""), "duplicate": bool(res.get("duplicate"))})
    if ok:
        ops.event(op_id, "result", upstream_id=object_id, detail={"deposition_id": res.get("deposition_id", ""), "verification": res.get("verification", ""),
                                                                  "sha256": (dep or {}).get("sha256", ""), "duplicate": bool(res.get("duplicate"))})
    return res


def status(op: dict) -> dict:
    """Local: what the record says about the producer side — the upstream
    id, the artifact and receipt states. No producer is refreshed."""
    import operations as ops
    evs = ops.events(op["op_id"])
    ref = op.get("result_ref") or {}
    starts = [e for e in evs if e["kind"] == "stage_end" and e["stage"].startswith("POST")]
    arts = [e for e in evs if e["kind"] == "stage_end" and e["stage"].startswith("GET")]
    dep = federation.get_deposition(ref.get("deposition_id", "")) if ref.get("deposition_id") else None
    ver = (dep or {}).get("verification")
    if isinstance(ver, dict):
        receipt = (f"signature verified ({ver.get('method', '')}) under the pinned key {str(ver.get('key_id', ''))[:28]}…" if ver.get("ok")
                   else "signature NOT verified: " + str(ver.get("why") or "unverified"))
    else:
        receipt = str(ver) if ver else ("none" if not dep else "unverified")
    return {"upstream_id": ref.get("upstream_id") or (starts[-1]["upstream_id"] if starts else ""),
            "start": (starts[-1]["outcome"] if starts else "not sent"),
            "artifact": ("imported" if dep else ("failed: " + arts[-1]["detail"].get("outcome", "") if arts and arts[-1]["outcome"] == "error" else "not retrieved")),
            "receipt": receipt, "verified": bool(isinstance(ver, dict) and ver.get("ok")),
            "deposition_id": (dep or {}).get("deposition_id", ""), "producer_state": op.get("producer_state") or {}}


def recover(op: dict) -> dict:
    """Bounded recovery for an investigation: the record first; then, if
    the start was answered and the artifact was not imported, the artifact
    is retrieved once more by its id (a read of the producer's export,
    verified) — never the start again."""
    st = status(op)
    ref = op.get("result_ref") or {}
    if st["start"] == "ok" and not st["deposition_id"] and ref.get("object_id"):
        spec = (op.get("execution") or {}).get("spec") or {}
        if spec:
            res = retrieve(op["op_id"], spec, ref["object_id"])
            return {"recovered": bool(res.get("ok")), "did": "retrieved the artifact again by its id", **status(op)}
    return {"recovered": False, "did": "read the record", **st}


def verify(deposition_id: str) -> dict:
    dep = federation.get_deposition(deposition_id)
    if dep is None:
        return {"ok": False, "detail": "no such deposition"}
    c = federation.get_connector(dep.get("connector_id", "")) or {}
    keys = c.get("trusted_keys") or []
    try:
        env = json.loads(federation.deposition_bytes(dep).decode("utf-8"))
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "detail": f"the stored bytes are not a package: {e}"}
    return federation.verify_envelope(env, keys)
