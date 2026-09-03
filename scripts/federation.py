"""Connected instruments — the federation core (block 107; docs/adr-federation.md).

Open Case and EthicalAlt are sovereign applications outside Nikodemus's
private membrane. This module is the controlled tissue between them and
the record: a registry of named connectors with pinned trusted keys and
credential *references*; a strict fetcher that reaches only configured
origins; verification of a producer's signed package against the pinned
key by the producer's own declared method — never a key the package
carries; exact-byte custody of every package received (verified or
not), with a rebuildable derived representation beside it; namespaced
identities, relationship proposals that only the owner's ruling can turn
into a declared link; an Investigation Room whose seats keep each
instrument's material apart; and, after a declaration only, a mechanical
convergence that names the exact source records.

Laws enforced here in code (the ADR has the rulings):
- Federation, not merger: no producer logic lives here; a payload is
  parsed by the producer's schema and shown with the producer's own
  vocabulary, never re-scored.
- Names are not identities: a proposal is a proposal until the owner
  declares, rejects, or leaves it unresolved; nothing merges by name.
- Absence, failure, and unknown never collapse: a fetch that fails is a
  failure record, never an empty result; a source searched and empty is
  said to be empty; a gap documented by the producer survives.
- The original deposition is preserved byte for byte; representations
  are derivatives and say so; a re-import of the same bytes appends an
  import event and nothing else; changed bytes are a new version linked
  to the prior, with supersession unknown until declared.
- No hidden outbound context: a request carries the configured origin,
  the explicit object id, and the credential resolved at request time —
  nothing from the corpus.
- Secrets stay outside the corpus: the registry holds a credential
  reference (env:NAME); the value is read from the environment when the
  request is made and never written anywhere.
- Reading is side-effect-free and nothing runs on its own: every fetch
  is an owner's act; there is no polling and no refresh.
- No model anywhere in this module.
"""
from __future__ import annotations

import base64
import hashlib
import json
import os
import pathlib
import re
import socket
import time
import urllib.error
import urllib.parse
import urllib.request

import wordicon_cli as cli

ENVELOPE_SCHEMA = "nikodemus.deposition.v1"
REP_REV = 1                                   # representation revision (derived files are rebuildable)
FETCH_TIMEOUT_S = 15
FETCH_MAX_BYTES = 8_000_000                   # a sealed case or a deep profile is well under a megabyte
KEY_ID_PREFIX = "ed25519:sha256:"

# The producers this block knows, as their own contracts declare them.
# Object types, signing methods and the export paths are the producer's;
# Nikodemus only dispatches on them.
PRODUCERS = {
    "open_case": {
        "display": "Open Case",
        "object_types": ("case_seal",),
        "methods": ("open_case.seal.v1",),
        "schemas": ("open-case-full-1", "open-case-full-2", "open-case-full-3", "open-case-full-4"),
        "export_path": "/api/v1/cases/{id}/export",
        "locate_path": "/api/v1/cases/exportable",
        "url_patterns": (r"/cases/([0-9a-fA-F-]{36})", r"/api/v1/cases/([0-9a-fA-F-]{36})"),
        "id_pattern": r"^[0-9a-fA-F-]{36}$",
        "auth": "bearer",
        "vocabulary": {
            "epistemic_levels": "Open Case's classifier: VERIFIED, REPORTED, ALLEGED, DISPUTED, CONTEXTUAL — attributed to Open Case, never re-scored here",
            "signals": "an Open Case signal is Open Case's pattern-engine output, not a Nikodemus finding",
        },
    },
    "ethicalalt": {
        "display": "EthicalAlt",
        "object_types": ("profile_export",),
        "methods": ("ethicalalt.export.v2",),
        "schemas": ("ethicalalt.profile_export.v2",),
        "export_path": "/api/profiles/{id}/export/v2",
        "locate_path": "/api/profiles/index",
        "url_patterns": (r"/profile/([a-z0-9][a-z0-9-]{0,120})", r"/api/profiles/([a-z0-9][a-z0-9-]{0,120})"),
        "id_pattern": r"^[a-z0-9][a-z0-9-]{0,120}$",
        "auth": "none",
        "vocabulary": {
            "concern_level": "EthicalAlt's assessment (significant / moderate / critical / minor / clean, as recorded) — attributed to EthicalAlt, never a Nikodemus fact",
            "confidence": "EthicalAlt's per-incident confidence (high / medium / low), attributed to EthicalAlt",
            "allegation_response": "EthicalAlt's allegation response types 1–3, paired with the allegation they answer",
        },
    },
}
RELATION_STATES = ("proposed_same_entity", "declared_same_entity", "affiliate_of", "parent_of",
                   "political_committee_of", "recipient_of", "rejected_match", "unresolved")
RULING_STATES = ("declared_same_entity", "affiliate_of", "parent_of", "political_committee_of", "recipient_of",
                 "rejected_match", "unresolved")
FETCH_FAILURES = ("not_configured", "disabled", "origin_refused", "redirect_refused", "dns_or_connection", "timeout",
                  "http_401", "http_403", "http_404", "http_409", "http_429", "http_5xx", "http_other",
                  "not_json", "html_error_page", "oversized", "unknown_schema", "credential_unavailable")
ROOM_SEATS = (
    {"seat": "Open Case evidence", "producer": "open_case", "kind": "evidence"},
    {"seat": "Open Case signals", "producer": "open_case", "kind": "signal"},
    {"seat": "EthicalAlt incidents and profile", "producer": "ethicalalt", "kind": "incident"},
    {"seat": "primary-source documents admitted here", "producer": "nikodemus", "kind": "document"},
    {"seat": "organizational statements and responses", "producer": "ethicalalt", "kind": "allegation_response"},
    {"seat": "counterevidence and disputes", "producer": "open_case", "kind": "dispute"},
    {"seat": "documented gaps and unavailable sources", "producer": "*", "kind": "gap"},
    {"seat": "owner rulings", "producer": "nikodemus", "kind": "ruling"},
)
CONVERGENCE_WINDOW_DAYS = 90


# ---- paths ------------------------------------------------------------------------

def fed_dir() -> pathlib.Path:
    return cli.LOCAL_STATE / "federation"


def connectors_log() -> pathlib.Path:
    return fed_dir() / "connectors.jsonl"


def attempts_log() -> pathlib.Path:
    return fed_dir() / "connector_attempts.jsonl"


def depositions_log() -> pathlib.Path:
    return fed_dir() / "depositions.jsonl"


def blobs_dir() -> pathlib.Path:
    """The Library's own blob store — one custody, content-addressed."""
    import library
    return library.blobs_dir()


def reps_dir() -> pathlib.Path:
    return fed_dir() / "reps"


def proposals_log() -> pathlib.Path:
    return fed_dir() / "identity_proposals.jsonl"


def rulings_log() -> pathlib.Path:
    return fed_dir() / "identity_rulings.jsonl"


def rooms_log() -> pathlib.Path:
    return fed_dir() / "investigation_rooms.jsonl"


def _rows(p: pathlib.Path) -> "list[dict]":
    if not p.exists():
        return []
    out = []
    try:
        for line in p.read_text(encoding="utf-8").splitlines():
            line = line.strip()
            if not line:
                continue
            try:
                out.append(json.loads(line))
            except json.JSONDecodeError:
                continue
    except OSError:
        return []
    return out


def _append(p: pathlib.Path, row: dict) -> dict:
    """Append-only, with the ruled clock discipline (item 58): every row
    gets recorded_at from this machine's clock; a row whose clock precedes
    the log's last row is labeled clock_regression, never silently taken."""
    fed_dir().mkdir(parents=True, exist_ok=True)
    row = dict(row)
    row.setdefault("recorded_at", cli._now())
    last = _rows(p)[-1:] if p.exists() else []
    if last and str(last[0].get("recorded_at", "")) > str(row["recorded_at"]):
        row["clock_regression"] = {"previous_recorded_at": last[0].get("recorded_at")}
    with p.open("a", encoding="utf-8") as fh:
        fh.write(json.dumps(row, ensure_ascii=False) + "\n")
    return row


def _hid(prefix: str, *parts) -> str:
    return prefix + hashlib.sha256("|".join(str(x) for x in parts).encode("utf-8")).hexdigest()[:12]


# ---- canonicalization and keys ------------------------------------------------------

def canonical_json(obj) -> bytes:
    """RFC 8785 (JCS), through the jcs package — the same canonicalization
    Open Case signs with; EthicalAlt's export v2 declares it too."""
    import jcs
    return jcs.canonicalize(obj)


def payload_sha256(payload) -> str:
    return hashlib.sha256(canonical_json(payload)).hexdigest()


def key_id_from_spki_b64(spki_b64: str) -> str:
    """The fingerprint pinned outside every package: sha256 over the raw
    32-byte Ed25519 public key (the tail of its SPKI DER), so that all
    three systems compute the same id from the same key."""
    raw = _raw_public_key(spki_b64)
    return KEY_ID_PREFIX + hashlib.sha256(raw).hexdigest()


def _b64decode_any(s: str) -> bytes:
    s = (s or "").strip()
    s = s.replace("-", "+").replace("_", "/")
    s += "=" * (-len(s) % 4)
    return base64.b64decode(s)


def _raw_public_key(spki_or_raw_b64: str) -> bytes:
    der = _b64decode_any(spki_or_raw_b64)
    if len(der) == 44:
        return der[-32:]
    if len(der) == 32:
        return der
    raise ValueError("a public key is a 44-byte Ed25519 SPKI DER or a raw 32-byte key, base64")


def verify_ed25519(raw_public_key: bytes, message: bytes, signature: bytes) -> bool:
    try:
        from cryptography.hazmat.primitives.asymmetric.ed25519 import Ed25519PublicKey
        from cryptography.exceptions import InvalidSignature
    except Exception as e:  # noqa: BLE001
        raise RuntimeError("the verification library (cryptography) is not installed — pip install -r requirements.txt") from e
    try:
        Ed25519PublicKey.from_public_bytes(raw_public_key).verify(signature, message)
        return True
    except InvalidSignature:
        return False
    except Exception:  # noqa: BLE001 — a malformed key or signature is a failed verification, said plainly
        return False


def verification_available() -> dict:
    out = {"jcs": False, "cryptography": False}
    try:
        import jcs  # noqa: F401
        out["jcs"] = True
    except Exception:  # noqa: BLE001
        pass
    try:
        import cryptography  # noqa: F401
        out["cryptography"] = True
    except Exception:  # noqa: BLE001
        pass
    return out


# ---- the registry: connectors as named instruments ------------------------------------

CONNECTOR_KINDS = ("register", "update", "enable", "disable", "pin_key", "unpin_key", "attempt", "imported")


def _origin_of(url: str) -> str:
    u = urllib.parse.urlsplit(url)
    if not u.scheme or not u.netloc:
        raise ValueError("base_url must be an absolute http(s) URL")
    return f"{u.scheme}://{u.netloc}".lower()


def _is_loopback(netloc: str) -> bool:
    host = netloc.split("@")[-1].split(":")[0].strip("[]").lower()
    return host in ("127.0.0.1", "localhost", "::1")


def register_connector(connector_id: str, producer: str, base_url: str, display: str = "", credential_ref: str = "",
                       dev_loopback: bool = False, by: str = "owner") -> dict:
    """Register (or re-declare) a connector. The base URL is the whole
    network permission: the fetcher never leaves its origin. Deployed
    origins must be HTTPS; plain HTTP is allowed only on loopback and only
    when the connector says it is a development endpoint."""
    cid = (connector_id or "").strip()
    if not re.match(r"^[a-z][a-z0-9_-]{1,40}$", cid):
        raise ValueError("a connector id is lowercase letters, digits, _ or - (2–41 characters)")
    if producer not in PRODUCERS:
        raise ValueError(f"producer must be one of {tuple(PRODUCERS)}")
    origin = _origin_of(base_url)
    u = urllib.parse.urlsplit(origin)
    if u.scheme != "https":
        if not (u.scheme == "http" and _is_loopback(u.netloc) and dev_loopback):
            raise ValueError("a deployed connector must be https; plain http is allowed only on loopback for a declared development endpoint")
    cref = (credential_ref or "").strip()
    if cref and not re.match(r"^env:[A-Z][A-Z0-9_]{1,60}$", cref):
        raise ValueError("credential_ref is a reference (env:NAME) — never a value")
    if cref and (len(cref) > 70 or " " in cref):
        raise ValueError("credential_ref is a reference, not a value")
    row = {"kind": "register", "connector_id": cid, "producer": producer, "display": (display or PRODUCERS[producer]["display"]).strip()[:80],
           "base_url": base_url.rstrip("/"), "origin": origin, "credential_ref": cref, "dev_loopback": bool(dev_loopback), "by": by}
    return _append(connectors_log(), row)


def set_enabled(connector_id: str, enabled: bool, by: str = "owner") -> dict:
    if connector_id not in {c["connector_id"] for c in load_connectors(include_disabled=True)}:
        raise ValueError("no such connector")
    return _append(connectors_log(), {"kind": "enable" if enabled else "disable", "connector_id": connector_id, "by": by})


def pin_key(connector_id: str, public_key_b64: str, label: str = "", by: str = "owner") -> dict:
    """Pin a trusted public key on a connector — by the owner, out of band.
    The key id is computed here from the key, never taken from a package."""
    if connector_id not in {c["connector_id"] for c in load_connectors(include_disabled=True)}:
        raise ValueError("no such connector")
    raw = _raw_public_key(public_key_b64)
    kid = KEY_ID_PREFIX + hashlib.sha256(raw).hexdigest()
    return _append(connectors_log(), {"kind": "pin_key", "connector_id": connector_id, "key_id": kid,
                                      "public_key_b64": base64.b64encode(raw).decode("ascii"), "label": (label or "")[:80], "by": by})


def unpin_key(connector_id: str, key_id: str, by: str = "owner") -> dict:
    return _append(connectors_log(), {"kind": "unpin_key", "connector_id": connector_id, "key_id": key_id, "by": by})


def _record_attempt(connector_id: str, outcome: str, detail: str = "", ok: bool = False, object_id: str = "",
                    http_status: "int | None" = None, deposition_id: str = "", network: bool = True) -> dict:
    """A failure record or a success record — never a body, never a header, never a credential.
    network=False marks a custody event (an import of bytes already in hand) that says nothing about reachability."""
    row = {"kind": "attempt", "connector_id": connector_id, "ok": bool(ok), "outcome": outcome, "detail": _scrub(detail)[:200],
           "object_id": str(object_id or "")[:160], "network": bool(network)}
    if http_status is not None:
        row["http_status"] = int(http_status)
    if deposition_id:
        row["deposition_id"] = deposition_id
    return _append(attempts_log(), row)


_SECRET_RX = re.compile(r"(bearer\s+\S+|open_case_[0-9a-f]{8,}|[A-Za-z0-9_\-]{32,})", re.I)


def _scrub(s: str) -> str:
    """Nothing that could be a credential survives into a stored error."""
    return _SECRET_RX.sub("[redacted]", str(s or ""))


def load_connectors(include_disabled: bool = False) -> "list[dict]":
    """The registry projection, folded from events."""
    conns: "dict[str, dict]" = {}
    for r in _rows(connectors_log()):
        cid = r.get("connector_id")
        k = r.get("kind")
        if k == "register" and cid:
            prev = conns.get(cid, {})
            conns[cid] = {**{"enabled": True, "trusted_keys": [], "registered_at": r.get("recorded_at")}, **prev,
                          **{kk: r[kk] for kk in ("producer", "display", "base_url", "origin", "credential_ref", "dev_loopback") if kk in r},
                          "connector_id": cid, "updated_at": r.get("recorded_at")}
        elif cid in conns:
            c = conns[cid]
            if k == "enable":
                c["enabled"] = True
            elif k == "disable":
                c["enabled"] = False
            elif k == "pin_key":
                if not any(t["key_id"] == r.get("key_id") for t in c["trusted_keys"]):
                    c["trusted_keys"].append({"key_id": r.get("key_id"), "public_key_b64": r.get("public_key_b64"),
                                              "label": r.get("label", ""), "pinned_at": r.get("recorded_at")})
            elif k == "unpin_key":
                c["trusted_keys"] = [t for t in c["trusted_keys"] if t["key_id"] != r.get("key_id")]
    attempts = _rows(attempts_log())
    deps = load_depositions()
    out = []
    for cid, c in conns.items():
        if not include_disabled and not c.get("enabled", True):
            continue
        mine = [a for a in attempts if a.get("connector_id") == cid and a.get("network", True)]
        okays = [a for a in mine if a.get("ok")]
        my_deps = [d for d in deps if d.get("connector_id") == cid]
        p = PRODUCERS.get(c.get("producer"), {})
        c = {**c,
             "capabilities": {"read_only": ["locate", "import", "verify"], "mutating": []},
             "commands_mutating": False,
             "supported_schemas": list(p.get("schemas", ())),
             "supported_object_types": list(p.get("object_types", ())),
             "signing_methods": list(p.get("methods", ())),
             "credential_configured": bool(c.get("credential_ref")) and _credential_present(c.get("credential_ref", "")),
             "last_attempt": mine[-1] if mine else None,
             "last_success_at": okays[-1].get("recorded_at") if okays else "",
             "status": ("never tried" if not mine else ("reachable at last attempt" if mine[-1].get("ok") else f"last attempt failed: {mine[-1].get('outcome')}")),
             "latest_deposition": my_deps[-1]["deposition_id"] if my_deps else "",
             "depositions": len(my_deps)}
        out.append(c)
    return out


def get_connector(connector_id: str) -> "dict | None":
    for c in load_connectors(include_disabled=True):
        if c["connector_id"] == connector_id:
            return c
    return None


def _credential_present(ref: str) -> bool:
    return bool(ref.startswith("env:") and os.environ.get(ref[4:], ""))


def _credential_value(ref: str) -> "str | None":
    """Resolved at request time from the environment. Never stored, never logged."""
    if not ref:
        return None
    if not ref.startswith("env:"):
        return None
    return os.environ.get(ref[4:]) or None


def recognize_url(url: str) -> "dict | None":
    """Does a pasted URL belong to a configured connector? Matched by origin
    and the producer's own path shape; anything else is not fetched."""
    try:
        origin = _origin_of(url.strip())
    except ValueError:
        return None
    path = urllib.parse.urlsplit(url.strip()).path
    for c in load_connectors():
        if c.get("origin") != origin:
            continue
        p = PRODUCERS[c["producer"]]
        for pat in p["url_patterns"]:
            m = re.search(pat, path)
            if m:
                return {"connector_id": c["connector_id"], "producer": c["producer"], "object_id": m.group(1), "display": c.get("display")}
    return None


# ---- the strict fetcher: configured origins only, bounded, no redirects, no secrets in records ----

class _NoRedirect(urllib.request.HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):  # noqa: D401
        raise urllib.error.HTTPError(req.full_url, code, "redirect refused", headers, fp)


def fetch_json(connector: dict, path: str, object_id: str = "") -> dict:
    """GET a JSON document from a configured connector. Returns
    {"ok": True, "status": 200, "body": bytes, "json": obj} or
    {"ok": False, "outcome": <FETCH_FAILURES>, "detail": ...}. The URL is
    the connector's base plus a path the producer's contract names —
    never a user-supplied URL; the credential is read from the
    environment now and appears nowhere else."""
    if not connector:
        return {"ok": False, "outcome": "not_configured", "detail": "no such connector"}
    if not connector.get("enabled", True):
        return {"ok": False, "outcome": "disabled", "detail": "the connector is disabled"}
    if not path.startswith("/") or ".." in path or "://" in path:
        return {"ok": False, "outcome": "origin_refused", "detail": "a path only"}
    url = connector["base_url"].rstrip("/") + path
    if _origin_of(url) != connector.get("origin"):
        return {"ok": False, "outcome": "origin_refused", "detail": "the request would leave the connector's origin"}
    headers = {"Accept": "application/json", "User-Agent": "Nikodemus-connector/1"}
    p = PRODUCERS[connector["producer"]]
    if p.get("auth") == "bearer":
        cred = _credential_value(connector.get("credential_ref", ""))
        if not cred:
            _record_attempt(connector["connector_id"], "credential_unavailable", "credential reference not set in the environment", object_id=object_id)
            return {"ok": False, "outcome": "credential_unavailable", "detail": f"set {connector.get('credential_ref') or 'a credential_ref'} in the server's environment"}
        headers["Authorization"] = "Bearer " + cred
    req = urllib.request.Request(url, headers=headers, method="GET")
    opener = urllib.request.build_opener(_NoRedirect())
    t0 = time.monotonic()
    try:
        with opener.open(req, timeout=FETCH_TIMEOUT_S) as resp:
            status = resp.status
            ctype = (resp.headers.get("Content-Type") or "").lower()
            body = _read_bounded(resp, FETCH_MAX_BYTES)
    except urllib.error.HTTPError as e:
        code = e.code
        ctype = ""
        try:
            ctype = (e.headers.get("Content-Type") or "").lower()
        except Exception:  # noqa: BLE001
            ctype = ""
        if code in (301, 302, 303, 307, 308):
            outcome = "redirect_refused"
        elif "text/html" in ctype:
            outcome = "html_error_page"          # a proxy's or a host's page, not the producer's answer — never parsed, never "nothing found"
        elif code in (401, 403, 404, 409, 429):
            outcome = f"http_{code}"
        elif 500 <= code < 600:
            outcome = "http_5xx"
        else:
            outcome = "http_other"
        _record_attempt(connector["connector_id"], outcome, f"HTTP {code}", object_id=object_id, http_status=code)
        return {"ok": False, "outcome": outcome, "status": code, "detail": f"HTTP {code} from the producer" + (" (an HTML page, not JSON)" if outcome == "html_error_page" else "")}
    except (socket.timeout, TimeoutError):
        _record_attempt(connector["connector_id"], "timeout", f"no answer within {FETCH_TIMEOUT_S} s", object_id=object_id)
        return {"ok": False, "outcome": "timeout", "detail": f"no answer within {FETCH_TIMEOUT_S} s — the producer may be down; nothing was imported"}
    except _Oversized:
        _record_attempt(connector["connector_id"], "oversized", f"body over {FETCH_MAX_BYTES} bytes", object_id=object_id)
        return {"ok": False, "outcome": "oversized", "detail": f"the response exceeded {FETCH_MAX_BYTES} bytes and was dropped"}
    except (urllib.error.URLError, OSError) as e:
        _record_attempt(connector["connector_id"], "dns_or_connection", _scrub(str(getattr(e, "reason", e)))[:120], object_id=object_id)
        return {"ok": False, "outcome": "dns_or_connection", "detail": "the producer could not be reached (DNS or connection) — nothing was imported"}
    elapsed = round(time.monotonic() - t0, 3)
    if "application/json" not in ctype:
        outcome = "html_error_page" if ("text/html" in ctype or body.lstrip()[:1] == b"<") else "not_json"
        _record_attempt(connector["connector_id"], outcome, f"content-type {ctype[:40]}", object_id=object_id, http_status=status)
        return {"ok": False, "outcome": outcome, "status": status, "detail": f"the producer answered with {ctype or 'no content type'}, not JSON"}
    try:
        obj = json.loads(body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        _record_attempt(connector["connector_id"], "not_json", "body did not parse as JSON", object_id=object_id, http_status=status)
        return {"ok": False, "outcome": "not_json", "status": status, "detail": "the body did not parse as JSON (a parse failure, not a transport failure)"}
    return {"ok": True, "status": status, "body": body, "json": obj, "elapsed_s": elapsed}


class _Oversized(Exception):
    pass


def _read_bounded(resp, cap: int) -> bytes:
    buf = bytearray()
    while True:
        chunk = resp.read(min(65536, cap + 1 - len(buf)))
        if not chunk:
            break
        buf += chunk
        if len(buf) > cap:
            raise _Oversized()
    return bytes(buf)


# ---- the envelope: validation and verification ----------------------------------------

def validate_envelope(env) -> "list[str]":
    """Shape problems, named — an empty list means the envelope is well formed."""
    p = []
    if not isinstance(env, dict):
        return ["the package is not a JSON object"]
    if env.get("schema") != ENVELOPE_SCHEMA:
        p.append(f"unsupported envelope schema {env.get('schema')!r} (this Nikodemus reads {ENVELOPE_SCHEMA})")
    prod = env.get("producer") or {}
    if not isinstance(prod, dict) or prod.get("id") not in PRODUCERS:
        p.append(f"unknown producer {prod.get('id') if isinstance(prod, dict) else prod!r}")
        return p
    spec = PRODUCERS[prod["id"]]
    obj = env.get("object") or {}
    if not isinstance(obj, dict) or obj.get("type") not in spec["object_types"] or not str(obj.get("id") or "").strip():
        p.append(f"the object type or id is not one {spec['display']} exports ({obj})")
    if env.get("payload_media_type") != "application/json":
        p.append("payload_media_type must be application/json")
    if not re.match(r"^[0-9a-f]{64}$", str(env.get("payload_sha256") or "")):
        p.append("payload_sha256 must be a hex sha256")
    sig = env.get("signature") or {}
    if not isinstance(sig, dict) or sig.get("algorithm") != "Ed25519" or sig.get("method") not in spec["methods"] \
            or not str(sig.get("trusted_key_id") or "").startswith(KEY_ID_PREFIX) or not sig.get("value"):
        p.append(f"the signature block must name Ed25519, one of {spec['methods']}, a trusted_key_id and a value")
    if "payload" not in env:
        p.append("no payload")
    for k in ("gaps", "source_times", "subject_refs"):
        if k in env and not isinstance(env[k], list):
            p.append(f"{k} must be a list")
    return p


def _payload_native_id(producer: str, payload) -> str:
    if not isinstance(payload, dict):
        return ""
    if producer == "open_case":
        return str(((payload.get("case") or {}).get("id")) or "")
    if producer == "ethicalalt":
        return str(((payload.get("profile") or {}).get("brand_slug")) or "")
    return ""


def verify_envelope(env: dict, trusted_keys: "list[dict]") -> dict:
    """Verify a package against the connector's pinned keys and nothing
    else: the hash of the canonical payload must equal payload_sha256,
    the package's trusted_key_id must be one the owner pinned, and the
    signature must verify under that key by the producer's method. A
    public key inside the package — anywhere — is ignored. Returns
    {ok, why, method, key_id, payload_sha256_recomputed, legacy}."""
    problems = validate_envelope(env)
    if problems:
        return {"ok": False, "why": "; ".join(problems), "method": "", "key_id": ""}
    producer = env["producer"]["id"]
    sig = env["signature"]
    method = sig["method"]
    kid = sig["trusted_key_id"]
    payload = env.get("payload")
    if payload is None:
        legacy = env.get("legacy") or {}
        return {"ok": False, "why": "the package carries no payload — " + str(legacy.get("note") or "a legacy seal that cannot be re-verified from the export"),
                "method": method, "key_id": kid, "legacy": True}
    try:
        digest = payload_sha256(payload)
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "why": f"the payload cannot be canonicalized: {e}", "method": method, "key_id": kid}
    if digest != env["payload_sha256"]:
        return {"ok": False, "why": "payload_sha256 does not match the canonical payload (the bytes changed, or the hash was forged)",
                "method": method, "key_id": kid, "payload_sha256_recomputed": digest}
    pinned = next((t for t in (trusted_keys or []) if t.get("key_id") == kid), None)
    if not pinned:
        return {"ok": False, "why": f"the package names key {kid[:32]}…, which is not pinned on this connector — pin the producer's key out of band, never from a package",
                "method": method, "key_id": kid, "payload_sha256_recomputed": digest}
    try:
        raw_key = base64.b64decode(pinned["public_key_b64"])
        sigbytes = _signature_bytes(method, sig["value"])
        message = _signed_message(method, digest, payload)
        ok = verify_ed25519(raw_key, message, sigbytes)
    except RuntimeError as e:
        return {"ok": False, "why": str(e), "method": method, "key_id": kid, "payload_sha256_recomputed": digest, "library_missing": True}
    except Exception as e:  # noqa: BLE001
        return {"ok": False, "why": f"the signature is malformed: {e}", "method": method, "key_id": kid, "payload_sha256_recomputed": digest}
    if not ok:
        return {"ok": False, "why": "the signature does not verify under the pinned key", "method": method, "key_id": kid, "payload_sha256_recomputed": digest}
    native = _payload_native_id(producer, payload)
    if native and native != str(env["object"]["id"]):
        return {"ok": False, "why": f"the envelope names object {env['object']['id']!r} but the signed payload is {native!r}",
                "method": method, "key_id": kid, "payload_sha256_recomputed": digest}
    return {"ok": True, "why": "", "method": method, "key_id": kid, "payload_sha256_recomputed": digest}


def _signature_bytes(method: str, value: str) -> bytes:
    v = str(value or "")
    if method == "ethicalalt.export.v2":
        if not v.startswith("ed25519:"):
            raise ValueError("an EthicalAlt signature is 'ed25519:<base64url>'")
        v = v[len("ed25519:"):]
    return _b64decode_any(v)


def _signed_message(method: str, digest_hex: str, payload) -> bytes:
    if method == "open_case.seal.v1":
        return digest_hex.encode("utf-8")           # Open Case signs the hex digest string
    if method == "ethicalalt.export.v2":
        return canonical_json(payload)              # EthicalAlt v2 signs the canonical bytes
    raise ValueError(f"unknown signing method {method}")


# ---- custody: exact bytes, then a derived representation ---------------------------------

def load_depositions(connector_id: str = "", include_events: bool = False) -> "list[dict]":
    rows = _rows(depositions_log())
    if include_events:
        return [r for r in rows if not connector_id or r.get("connector_id") == connector_id]
    out = []
    for r in rows:
        if r.get("kind") != "deposition":
            continue
        if connector_id and r.get("connector_id") != connector_id:
            continue
        out.append(r)
    return out


def get_deposition(deposition_id: str) -> "dict | None":
    for d in load_depositions():
        if d.get("deposition_id") == deposition_id:
            return d
    return None


def deposition_bytes(dep: dict) -> bytes:
    p = blobs_dir() / dep["sha256"]
    return p.read_bytes() if p.exists() else b""


def deposition_representation(dep: dict) -> "dict | None":
    p = reps_dir() / f"{dep['sha256']}.r{dep.get('rep_rev', REP_REV)}.json"
    if not p.exists():
        return None
    try:
        return json.loads(p.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return None


def import_package(connector: dict, body: bytes, how: str = "fetched", object_id_hint: str = "") -> dict:
    """The one admission chokepoint. Exact bytes into custody first, then
    verification against the pinned keys, then — only when verified — a
    derived representation. Same bytes again: an import event citing the
    existing deposition, nothing else. Different bytes for the same
    producer object: a new deposition linked to the prior, supersession
    unknown."""
    if not isinstance(body, (bytes, bytearray)) or not body:
        raise ValueError("no package bytes")
    if len(body) > FETCH_MAX_BYTES:
        raise ValueError("the package is over the size cap")
    sha = hashlib.sha256(body).hexdigest()
    try:
        env = json.loads(bytes(body).decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        env = None
    existing = next((d for d in load_depositions() if d.get("sha256") == sha), None)
    if existing:
        _append(depositions_log(), {"kind": "import_event", "connector_id": connector["connector_id"], "deposition_id": existing["deposition_id"],
                                    "sha256": sha, "duplicate_of": existing["deposition_id"], "how": how, "by": "owner"})
        _record_attempt(connector["connector_id"], "duplicate", "same bytes already in custody", ok=True, object_id=existing.get("object_id", ""),
                        deposition_id=existing["deposition_id"], network=False)
        return {"deposition_id": existing["deposition_id"], "duplicate": True, "duplicate_of": existing["deposition_id"], "verification": existing.get("verification"),
                "note": "the same bytes were already in custody — an import event was recorded and nothing else"}
    blobs_dir().mkdir(parents=True, exist_ok=True)
    (blobs_dir() / sha).write_bytes(bytes(body))
    producer = connector["producer"]
    verification = verify_envelope(env, connector.get("trusted_keys", [])) if isinstance(env, dict) else \
        {"ok": False, "why": "the package is not a JSON object", "method": "", "key_id": ""}
    obj = (env.get("object") if isinstance(env, dict) else None) or {}
    object_id = str(obj.get("id") or object_id_hint or "")
    if isinstance(env, dict) and (env.get("producer") or {}).get("id") not in (None, producer):
        verification = {**verification, "ok": False, "why": f"the package says producer {(env.get('producer') or {}).get('id')!r} but this connector is {producer!r}"}
    # the version chain links VERIFIED depositions of the same producer object only: an unverified package makes no
    # claim, not even to be a version, so it can never cast "superseded?" over a verified one
    prior = [d for d in load_depositions() if d.get("producer") == producer and d.get("object_id") == object_id and d.get("sha256") != sha
             and (d.get("verification") or {}).get("ok")] if verification.get("ok") else []
    dep_id = _hid("dep_", sha, connector["connector_id"])
    row = {"kind": "deposition", "deposition_id": dep_id, "connector_id": connector["connector_id"], "producer": producer,
           "object_type": str(obj.get("type") or ""), "object_id": object_id, "sha256": sha, "bytes": len(body),
           "envelope_schema": (env.get("schema") if isinstance(env, dict) else None),
           "payload_schema": _payload_schema(producer, env.get("payload") if isinstance(env, dict) else None),
           "producer_version": ((env.get("producer") or {}).get("version") if isinstance(env, dict) else None),
           "constitution_version": ((env.get("producer") or {}).get("constitution_version") if isinstance(env, dict) else None),
           "source_recorded_at": (env.get("recorded_at") if isinstance(env, dict) else None),
           "source_times": (env.get("source_times") if isinstance(env, dict) and isinstance(env.get("source_times"), list) else []),
           "received_at": cli._now(), "how": how, "verification": verification, "trusted_key_id": verification.get("key_id", ""),
           "rep_rev": REP_REV, "prior_version_of": prior[-1]["deposition_id"] if prior else "",
           "supersession": ("unknown" if prior else "n/a"), "legacy": bool(verification.get("legacy")), "by": "owner"}
    _append(depositions_log(), row)
    rep = None
    if verification.get("ok"):
        rep = build_representation(producer, env)
        reps_dir().mkdir(parents=True, exist_ok=True)
        (reps_dir() / f"{sha}.r{REP_REV}.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    _record_attempt(connector["connector_id"], "imported" if verification.get("ok") else "imported_unverified",
                    "" if verification.get("ok") else verification.get("why", ""), ok=True, object_id=object_id, deposition_id=dep_id, network=False)
    return {"deposition_id": dep_id, "duplicate": False, "verification": verification, "prior_version_of": row["prior_version_of"],
            "supersession": row["supersession"], "representation": bool(rep),
            "note": ("verified against the pinned key; the exact bytes are in custody and a representation was derived" if verification.get("ok")
                     else "kept in custody as received, UNVERIFIED — no representation was derived and nothing from it is shown as evidence")}


def _payload_schema(producer: str, payload) -> "str | None":
    if not isinstance(payload, dict):
        return None
    return str(payload.get("schema_version") or payload.get("schema") or "") or None


def import_from_connector(connector: dict, object_id: str) -> dict:
    """Locate the producer's export by the object id the owner named — the
    connector's configured origin, the producer's contract path — fetch,
    then the chokepoint."""
    spec = PRODUCERS[connector["producer"]]
    oid = str(object_id or "").strip()
    if not re.match(spec["id_pattern"], oid):
        return {"ok": False, "outcome": "bad_id", "detail": f"that is not a {spec['display']} object id"}
    res = fetch_json(connector, spec["export_path"].format(id=urllib.parse.quote(oid, safe="")), object_id=oid)
    if not res.get("ok"):
        return {"ok": False, **{k: v for k, v in res.items() if k != "ok"}}
    out = import_package(connector, res["body"], how="fetched", object_id_hint=oid)
    return {"ok": True, **out}


def locate(connector: dict, query: str = "") -> dict:
    """The producer's own list of exportable objects, read-only, on the
    owner's explicit press — never on paint."""
    spec = PRODUCERS[connector["producer"]]
    res = fetch_json(connector, spec["locate_path"], object_id="")
    if not res.get("ok"):
        return {"ok": False, **{k: v for k, v in res.items() if k != "ok"}}
    _record_attempt(connector["connector_id"], "located", "", ok=True)
    obj = res["json"]
    items = obj.get("items") if isinstance(obj, dict) else obj
    if not isinstance(items, list):
        items = []
    q = (query or "").strip().lower()
    if q:
        items = [it for it in items if q in json.dumps(it, ensure_ascii=False).lower()]
    return {"ok": True, "items": items[:200], "count": len(items), "note": "the producer's own list, unchanged; nothing was imported"}


# ---- representations: the producer's records, in the producer's words, indexed for the room ----

def build_representation(producer: str, env: dict) -> dict:
    payload = env.get("payload") or {}
    if producer == "open_case":
        return _rep_open_case(env, payload)
    if producer == "ethicalalt":
        return _rep_ethicalalt(env, payload)
    return {"producer": producer, "rep_rev": REP_REV, "items": []}


def _rep_open_case(env: dict, payload: dict) -> dict:
    case = payload.get("case") or {}
    att = env.get("attachments") or {}
    case_id = str(case.get("id") or env["object"]["id"])
    items = []
    for e in payload.get("evidence") or []:
        eid = str(e.get("id") or "")
        items.append({"kind": "evidence", "ref": f"open_case:evidence:{eid}", "stable_ref": f"open_case:evidence_hash:{e.get('evidence_hash', '')}",
                      "title": e.get("title") or "", "body": e.get("body") or "", "date": e.get("date_of_event") or e.get("source_date") or "",
                      "source_url": e.get("source_url") or "", "source_name": e.get("source_name") or "", "entry_type": e.get("entry_type") or "",
                      "epistemic_level": e.get("epistemic_level") or "", "epistemic_attributed_to": "Open Case's classifier",
                      "classification_basis": e.get("classification_basis") or "", "source_type": e.get("source_type") or "",
                      "is_absence": bool(e.get("is_absence")), "claim_status": e.get("claim_status") or "", "matched_name": e.get("matched_name") or "",
                      "amount": e.get("amount"), "signed": True})
    for s in (att.get("signals") or {}).get("rows", []) if isinstance(att.get("signals"), dict) else []:
        items.append({"kind": "signal", "ref": f"open_case:signal:{s.get('id', '')}", "stable_ref": f"open_case:signal_identity:{s.get('signal_identity_hash', '')}",
                      "signal_type": s.get("signal_type") or "", "description": s.get("description") or "", "weight": s.get("weight"),
                      "evidence_ids": [f"open_case:evidence:{x}" for x in (s.get("evidence_ids") or [])], "pattern_engine_version": (att.get("pattern_engine") or {}).get("version", ""),
                      "epistemic_level": s.get("epistemic_level") or "", "epistemic_attributed_to": "Open Case's classifier",
                      "confirmed": s.get("confirmed"), "dismissed": s.get("dismissed"), "exposure_state": s.get("exposure_state") or "",
                      "date_a": s.get("event_date_a") or "", "date_b": s.get("event_date_b") or "", "signed": False,
                      "attributed_to": "Open Case's pattern engine — a signal, not a Nikodemus finding"})
    for sc in (att.get("source_checks") or {}).get("rows", []) if isinstance(att.get("source_checks"), dict) else []:
        items.append({"kind": "source_check", "ref": f"open_case:source_check:{sc.get('id', '')}", "source_name": sc.get("source_name") or "",
                      "status": sc.get("status") or "unknown", "result_count": sc.get("result_count"), "checked_at": sc.get("checked_at") or "", "signed": False})
    gaps = list(env.get("gaps") or [])
    for it in items:
        if it["kind"] == "evidence" and it.get("is_absence"):
            gaps.append({"kind": "gap_documented", "ref": it["ref"], "detail": it.get("title", "")})
        if it["kind"] == "source_check" and it.get("status") == "search_failed":
            gaps.append({"kind": "source_unavailable", "ref": it["ref"], "detail": f"{it.get('source_name')}: the search could not be completed"})
    subject = {"ref": f"open_case:case:{case_id}", "name": case.get("subject_name") or case.get("title") or "", "subject_type": case.get("subject_type") or "",
               "external_ids": {k: v for k, v in (("bioguide_id", (att.get("subject") or {}).get("bioguide_id")), ("fec_committee_id", case.get("fec_committee_id"))) if v}}
    names = {subject["name"]} | {it.get("matched_name") for it in items if it.get("matched_name")}
    return {"producer": "open_case", "rep_rev": REP_REV, "object_id": case_id, "subject": subject,
            "schema_version": payload.get("schema_version"), "sealed_at": (env.get("seal") or {}).get("last_signed_at") or env.get("recorded_at") or case.get("last_signed_at") or "",
            "items": items, "gaps": gaps, "names": sorted(n for n in names if n), "vocabulary": PRODUCERS["open_case"]["vocabulary"],
            "legacy": bool((env.get("legacy") or {}).get("self_contained") is False), "counts": {k: sum(1 for i in items if i["kind"] == k) for k in ("evidence", "signal", "source_check")}}


def _ea_partial_reasons(prof: dict, completeness: dict) -> "list[str]":
    """Why this profile is partial, as reasons — an empty list means EthicalAlt's
    own counts show nothing missing. A signature proves origin, never completeness."""
    out = []
    depth = prof.get("research_depth") or "unknown"
    if depth != "deep_research":
        out.append(f"research_depth is {depth} — no deep research recorded by EthicalAlt")
    if completeness:
        total = int(completeness.get("incidents_total") or 0)
        direct = int(completeness.get("incidents_with_direct_url") or 0)
        if total and direct < total:
            out.append(f"{total - direct} of {total} incidents without a direct source URL")
        if int(completeness.get("categories_capped") or 0):
            out.append(f"{completeness.get('categories_capped')} category(ies) capped — EthicalAlt found more than it exported")
        if total and int(completeness.get("incidents_with_full_date") or 0) < total:
            out.append(f"{total - int(completeness.get('incidents_with_full_date') or 0)} of {total} incidents without a full date")
    return out


def _rep_ethicalalt(env: dict, payload: dict) -> dict:
    prof = payload.get("profile") or {}
    slug = str(prof.get("brand_slug") or env["object"]["id"])
    items = []
    for inc in payload.get("incidents") or []:
        iid = str(inc.get("incident_id") or "")
        alle = inc.get("allegation") or {}
        items.append({"kind": "incident", "ref": f"ethicalalt:incident:{iid}", "date": inc.get("date") or "", "date_precision": inc.get("date_precision") or "none",
                      "description": inc.get("description") or "", "categories": inc.get("categories") or [], "action_type": inc.get("action_type") or "",
                      "action_type_origin": inc.get("action_type_origin") or "", "outcome": inc.get("outcome") or "", "amount_usd": inc.get("amount_usd"),
                      "currency": inc.get("currency") or "USD", "jurisdiction": inc.get("jurisdiction") or "", "agency_or_court": inc.get("agency_or_court") or "",
                      "source_type": inc.get("source_type") or "", "confidence": inc.get("confidence") or "", "confidence_attributed_to": "EthicalAlt",
                      "sources": inc.get("sources") or [], "entity": inc.get("entity") or "",
                      "allegation_status": alle.get("status") or "", "response_type": alle.get("response_type"), "response_note": alle.get("response_note") or "",
                      "canonical": bool(inc.get("canonical", True)), "signed": True})
    for a in payload.get("allegations") or []:
        items.append({"kind": "allegation_response", "ref": f"ethicalalt:allegation:{a.get('allegation_id', '')}", "summary": a.get("summary") or "",
                      "response_type": a.get("response_type"), "response_label": a.get("response_label") or "", "signed": True})
    gaps, seen_gaps = [], set()
    for g in list(env.get("gaps") or []) + list(payload.get("gaps") or []):
        key = json.dumps(g, sort_keys=True, ensure_ascii=False)
        if key not in seen_gaps:
            seen_gaps.add(key); gaps.append(g)
    completeness = payload.get("provenance_completeness") or {}
    parents = [prof.get("parent_company"), prof.get("ultimate_parent")]
    names = {prof.get("brand_name")} | {p for p in parents if p}
    return {"producer": "ethicalalt", "rep_rev": REP_REV, "object_id": slug,
            "subject": {"ref": f"ethicalalt:profile:{slug}", "name": prof.get("brand_name") or slug, "parent_company": prof.get("parent_company") or "",
                        "ultimate_parent": prof.get("ultimate_parent") or "", "profile_type": prof.get("profile_type") or "",
                        "research_depth": prof.get("research_depth") or "unknown", "concern_level": prof.get("overall_concern_level"),
                        "concern_attributed_to": "EthicalAlt", "researched_at": prof.get("researched_at") or "", "updated_at": prof.get("updated_at") or ""},
            "schema_version": payload.get("schema_version"), "items": items, "gaps": gaps, "provenance_completeness": completeness,
            "names": sorted(n for n in names if n), "vocabulary": PRODUCERS["ethicalalt"]["vocabulary"],
            "partial": _ea_partial_reasons(prof, completeness),
            "counts": {"incident": sum(1 for i in items if i["kind"] == "incident"), "allegation_response": sum(1 for i in items if i["kind"] == "allegation_response")}}


# ---- identity: proposals and the owner's rulings ------------------------------------------

def load_proposals() -> "list[dict]":
    return [r for r in _rows(proposals_log()) if r.get("kind") == "proposal"]


def load_rulings() -> "list[dict]":
    return [r for r in _rows(rulings_log()) if r.get("kind") == "ruling"]


def relationship_state(proposal_id: str) -> str:
    """The latest ruling wins; no ruling means the proposal is only proposed."""
    st = "proposed_same_entity"
    for r in load_rulings():
        if r.get("proposal_id") == proposal_id and r.get("state") in RULING_STATES:
            st = r["state"]
    return st


def propose_relationship(a_ref: str, b_ref: str, relation: str, origin: str, basis: str, room_id: str = "", by: str = "") -> dict:
    """A proposal — by mechanical name comparison, by the model (later, a
    summoned doorway), or by the owner — is a row that grants nothing."""
    if relation not in ("proposed_same_entity", "affiliate_of", "parent_of", "political_committee_of", "recipient_of"):
        raise ValueError("a proposal names one of the relationship kinds")
    if origin not in ("mechanical", "model", "owner"):
        raise ValueError("origin must be mechanical, model, or owner")
    a, b = sorted([str(a_ref), str(b_ref)])
    pid = _hid("rel_", a, b, relation)
    if any(p.get("proposal_id") == pid for p in load_proposals()):
        return next(p for p in load_proposals() if p.get("proposal_id") == pid)
    return _append(proposals_log(), {"kind": "proposal", "proposal_id": pid, "a": a, "b": b, "relation": relation, "origin": origin,
                                     "basis": str(basis)[:400], "room_id": room_id, "by": by or origin,
                                     "note": "a proposal grants nothing — names are not identities; the owner declares, rejects, or leaves it unresolved"})


def rule_relationship(proposal_id: str, state: str, note: str = "", by: str = "owner") -> dict:
    if state not in RULING_STATES:
        raise ValueError(f"a ruling is one of {RULING_STATES}")
    if by != "owner":
        raise ValueError("only the owner rules on identity")
    if not any(p.get("proposal_id") == proposal_id for p in load_proposals()):
        raise ValueError("no such proposal")
    return _append(rulings_log(), {"kind": "ruling", "ruling_id": _hid("rul_", proposal_id, state, cli._now(), os.urandom(3).hex()),
                                   "proposal_id": proposal_id, "state": state, "note": (note or "")[:400], "by": "owner"})


def declared_links(room_id: str = "") -> "list[dict]":
    out = []
    for p in load_proposals():
        st = relationship_state(p["proposal_id"])
        if st in ("declared_same_entity", "affiliate_of", "parent_of", "political_committee_of", "recipient_of"):
            if not room_id or p.get("room_id") in ("", room_id):
                out.append({**p, "state": st})
    return out


def propose_mechanically(room_id: str) -> "list[dict]":
    """The one mechanical proposer of this block: an exact, case-insensitive
    NAME match between an EthicalAlt profile (brand, parent, ultimate
    parent) and an Open Case subject or matched name in the same room.
    It proposes; it never links — names are not identities."""
    room = get_room(room_id)
    if not room:
        raise ValueError("no such room")
    reps = [(d, deposition_representation(d)) for d in _room_depositions(room)]
    ea = [(d, r) for d, r in reps if r and r.get("producer") == "ethicalalt"]
    oc = [(d, r) for d, r in reps if r and r.get("producer") == "open_case"]
    made = []
    for _, er in ea:
        e_names = {n.strip().lower(): n for n in er.get("names", []) if n and n.strip()}
        for _, orr in oc:
            subj = orr.get("subject") or {}
            candidates = [(subj.get("ref"), subj.get("name"))] + [(it["ref"], it.get("matched_name")) for it in orr.get("items", []) if it.get("kind") == "evidence" and it.get("matched_name")]
            for ref, name in candidates:
                key = (name or "").strip().lower()
                if key and key in e_names:
                    made.append(propose_relationship(er["subject"]["ref"], ref, "proposed_same_entity", "mechanical",
                                                     f"exact name match: EthicalAlt records {e_names[key]!r}; Open Case records {name!r} — names are not identities", room_id=room_id))
    return made


# ---- the Investigation Room ------------------------------------------------------------

def create_room(title: str, by: str = "owner") -> dict:
    t = (title or "").strip()[:160]
    if not t:
        raise ValueError("a room needs a title")
    rid = _hid("inv_", t, cli._now(), os.urandom(3).hex())
    return _append(rooms_log(), {"kind": "room", "room_id": rid, "title": t, "by": by})


def add_to_room(room_id: str, deposition_id: str = "", document_id: str = "", by: str = "owner") -> dict:
    if not get_room(room_id):
        raise ValueError("no such room")
    if deposition_id and not get_deposition(deposition_id):
        raise ValueError("no such deposition")
    if not deposition_id and not document_id:
        raise ValueError("name a deposition or a document")
    return _append(rooms_log(), {"kind": "member", "room_id": room_id, "deposition_id": deposition_id, "document_id": document_id, "by": by})


def load_rooms() -> "list[dict]":
    rooms: "dict[str, dict]" = {}
    for r in _rows(rooms_log()):
        if r.get("kind") == "room":
            rooms[r["room_id"]] = {"room_id": r["room_id"], "title": r.get("title", ""), "created_at": r.get("recorded_at"), "members": []}
        elif r.get("kind") == "member" and r.get("room_id") in rooms:
            rooms[r["room_id"]]["members"].append({k: r.get(k, "") for k in ("deposition_id", "document_id", "recorded_at")})
    return list(rooms.values())


def get_room(room_id: str) -> "dict | None":
    return next((r for r in load_rooms() if r["room_id"] == room_id), None)


def _room_depositions(room: dict) -> "list[dict]":
    seen, out = set(), []
    for m in room.get("members", []):
        d = get_deposition(m.get("deposition_id", "")) if m.get("deposition_id") else None
        if d and d["deposition_id"] not in seen:
            seen.add(d["deposition_id"]); out.append(d)
    return out


def room_state(room_id: str) -> dict:
    """Seats filled mechanically from the representations of verified
    depositions in the room; unverified packages are listed apart, with
    nothing from them in a seat. No sentence here blends what one
    instrument said with what another said."""
    room = get_room(room_id)
    if not room:
        raise ValueError("no such room")
    deps = _room_depositions(room)
    seats = [{**s, "items": []} for s in ROOM_SEATS]
    by_seat = {s["kind"]: s for s in seats}
    unverified = []
    for d in deps:
        v = d.get("verification") or {}
        stamp = {"deposition_id": d["deposition_id"], "producer": d["producer"], "object_id": d["object_id"], "signature_ok": bool(v.get("ok")),
                 "trusted_key_id": d.get("trusted_key_id", ""), "imported_at": d.get("received_at", ""), "source_recorded_at": d.get("source_recorded_at", ""),
                 "status": _deposition_status(d)}
        rep = deposition_representation(d) if v.get("ok") else None
        if not rep:
            unverified.append({**stamp, "why": v.get("why", "")})
            continue
        for it in rep.get("items", []):
            kind = it["kind"]
            if kind == "evidence":
                by_seat["evidence"]["items"].append({**it, **stamp})
                if (it.get("claim_status") or "").lower() in ("disputed", "contradicted") or (it.get("epistemic_level") or "") == "DISPUTED":
                    by_seat["dispute"]["items"].append({**it, **stamp})
            elif kind == "signal":
                by_seat["signal"]["items"].append({**it, **stamp})
            elif kind == "incident":
                by_seat["incident"]["items"].append({**it, **stamp})
                if it.get("response_type") is not None or it.get("allegation_status"):
                    by_seat["allegation_response"]["items"].append({**it, **stamp})
            elif kind == "allegation_response":
                by_seat["allegation_response"]["items"].append({**it, **stamp})
        for g in rep.get("gaps", []):
            by_seat["gap"]["items"].append({**g, **stamp})
    for m in room.get("members", []):
        if m.get("document_id"):
            by_seat["document"]["items"].append({"document_id": m["document_id"], "producer": "nikodemus", "status": "admitted"})
    props = [p for p in load_proposals() if p.get("room_id") in ("", room_id)]
    rels = []
    for p in props:
        st = relationship_state(p["proposal_id"])
        rels.append({**p, "state": st})
        if st != "proposed_same_entity":
            by_seat["ruling"]["items"].append({**p, "state": st, "producer": "nikodemus"})
    return {"room_id": room_id, "title": room["title"], "created_at": room.get("created_at"), "depositions": [_deposition_summary(d) for d in deps],
            "unverified": unverified, "seats": seats, "relationships": rels, "declared": [r for r in rels if r["state"] != "proposed_same_entity" and r["state"] not in ("rejected_match", "unresolved")],
            "note": "seats are kept apart on purpose: each item says which instrument said it and under which of that instrument's own labels; nothing here is a Nikodemus finding"}


def _deposition_status(d: dict) -> str:
    v = d.get("verification") or {}
    if d.get("legacy"):
        return "legacy"
    if not v.get("ok"):
        return "unverified"
    newer = [x for x in load_depositions() if x.get("prior_version_of") == d["deposition_id"]]
    if newer:
        return "superseded?" if newer[-1].get("supersession") == "unknown" else "stale"
    return "current"


def _deposition_summary(d: dict) -> dict:
    v = d.get("verification") or {}
    return {k: d.get(k) for k in ("deposition_id", "connector_id", "producer", "object_type", "object_id", "sha256", "bytes", "received_at",
                                  "source_recorded_at", "trusted_key_id", "payload_schema", "producer_version", "prior_version_of", "supersession", "legacy")} | \
        {"signature_ok": bool(v.get("ok")), "why": v.get("why", ""), "status": _deposition_status(d)}


# ---- convergence: mechanical, after a declaration, naming its records ----------------------------

def _date_key(s: str) -> "tuple[str, str]":
    s = str(s or "").strip()
    m = re.match(r"^(\d{4})(?:-(\d{2}))?(?:-(\d{2}))?", s)
    if not m:
        return ("", "none")
    y, mo, d = m.group(1), m.group(2), m.group(3)
    if d:
        return (f"{y}-{mo}-{d}", "day")
    if mo:
        return (f"{y}-{mo}", "month")
    return (y, "year")


def _days_between(a: str, b: str) -> "int | None":
    import datetime as _dt
    ka, pa = _date_key(a)
    kb, pb = _date_key(b)
    if pa != "day" or pb != "day":
        return None
    try:
        da = _dt.date.fromisoformat(ka); db = _dt.date.fromisoformat(kb)
    except ValueError:
        return None
    return abs((db - da).days)


def convergence(room_id: str) -> dict:
    """After the owner has declared a link between an EthicalAlt subject
    and an Open Case subject or record: one timeline of both instruments'
    dated records for that pair, each row citing its source record, and
    the pairs that fall within a declared window. Mechanical sentences
    only; the interpretive proposal is a doorway that is not built."""
    room = get_room(room_id)
    if not room:
        raise ValueError("no such room")
    links = declared_links(room_id)
    if not links:
        return {"room_id": room_id, "links": [], "timeline": [], "overlaps": [],
                "note": "no declared relationship in this room — nothing converges until the owner declares one (a proposal, an unresolved match or a rejection produces nothing here)"}
    reps = {d["deposition_id"]: deposition_representation(d) for d in _room_depositions(room) if (d.get("verification") or {}).get("ok")}
    timeline, overlaps, cited = [], [], set()
    for link in links:
        refs = {link["a"], link["b"]}
        for dep_id, rep in reps.items():
            if not rep:
                continue
            subject_ref = (rep.get("subject") or {}).get("ref")
            for it in rep.get("items", []):
                if it["kind"] not in ("evidence", "incident"):
                    continue
                belongs = subject_ref in refs or it.get("ref") in refs
                if not belongs:
                    continue
                key, prec = _date_key(it.get("date", ""))
                timeline.append({"date": key, "date_precision": prec, "producer": rep["producer"], "record": it["ref"], "deposition_id": dep_id,
                                 "what": (it.get("title") or it.get("description") or "")[:200], "label": it.get("epistemic_level") or it.get("confidence") or "",
                                 "label_attributed_to": it.get("epistemic_attributed_to") or it.get("confidence_attributed_to") or "",
                                 "source_url": it.get("source_url") or ((it.get("sources") or [{}])[0].get("url") if it.get("sources") else "") or "",
                                 "link": link["proposal_id"]})
                cited.add(it["ref"])
    timeline.sort(key=lambda r: (r["date"] == "", r["date"]))
    oc = [t for t in timeline if t["producer"] == "open_case"]
    ea = [t for t in timeline if t["producer"] == "ethicalalt"]
    for a in oc:
        for b in ea:
            d = _days_between(a["date"], b["date"])
            if d is not None and d <= CONVERGENCE_WINDOW_DAYS:
                overlaps.append({"open_case_record": a["record"], "ethicalalt_record": b["record"], "days_apart": d, "window_days": CONVERGENCE_WINDOW_DAYS,
                                 "sentence": f"Open Case records {a['record']} on {a['date']}; EthicalAlt records {b['record']} on {b['date']}; {d} day(s) apart, within the {CONVERGENCE_WINDOW_DAYS}-day window the owner declared. This is a mechanical intersection, not a claim of relation."})
    return {"room_id": room_id, "links": [{"proposal_id": l["proposal_id"], "a": l["a"], "b": l["b"], "state": l["state"], "basis": l.get("basis", "")} for l in links],
            "timeline": timeline, "overlaps": overlaps, "records_cited": sorted(cited), "window_days": CONVERGENCE_WINDOW_DAYS,
            "interpretation": {"built": False, "note": "why these records might matter together is a proposal a model could make when summoned — not built in this block"},
            "note": "mechanical: the owner's declared link, the dated records of both instruments for that pair, and pairs inside the window — each citing its source record; nothing here says one thing caused another"}


# ---- self-description ------------------------------------------------------------------------

def status() -> dict:
    return {"envelope_schema": ENVELOPE_SCHEMA, "producers": {k: {"display": v["display"], "object_types": list(v["object_types"]), "methods": list(v["methods"]),
                                                             "schemas": list(v["schemas"]), "auth": v["auth"]} for k, v in PRODUCERS.items()},
            "libraries": verification_available(), "connectors": load_connectors(include_disabled=True),
            "depositions": len(load_depositions()), "rooms": len(load_rooms()), "proposals": len(load_proposals()), "rulings": len(load_rulings()),
            "fetch": {"timeout_s": FETCH_TIMEOUT_S, "max_bytes": FETCH_MAX_BYTES, "redirects": "refused", "origins": "configured only"},
            "automation": "none — manual pull only; no polling, no refresh, no background comparison"}
