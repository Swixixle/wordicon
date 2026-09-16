"""Investigation adapters (workspace-v2 slice F; corrected after the review
of 6e5b59c, finding 3).

One adapter per producer, built against what that producer's MAIN branch
serves at a pinned revision, read from its source in the owner's checkout
with read-only git plumbing (git show <revision>:<path>) on 2026-09-16 —
never against the routes an earlier report assumed. Every route below
names its file and line at that revision; every reply shape is the one
the source builds. What a producer does NOT serve at that revision is
declared as such (PACKAGE_CONTRACT): the signed package export that the
federation core (block 107) imports exists in both producers only on
unpushed local branches, so the Investigation rooms' import is served,
against a deployment of main, by no route at all — the mock producer
keeps those routes as labelled compatibility fixtures, nothing more.

The contracts are SOURCE-verified. None is verified against a deployment
from this workspace, so LIVE STARTS ARE DISABLED by the adapter itself
until the owner records, on the connector, that the deployment runs the
pinned revision. In test mode a declared development connector on
loopback (the fixture producer) may start, so the mechanism is proven
without a deployment.

An investigation is an operation in the store (slice D): reserved under a
request key, claimed, its POST preceded by a dispatch intent and followed
by its outcome with the upstream id; what the producer answered is kept
byte for byte under the operation (start-reply.json, export.json /
report.json, receipt.json / snapshot.json, each hashed in the record);
the signature state of a receipt or snapshot is recorded apart from the
live reply. "Signature verified" means the bytes are the producer's under
the key the owner pinned; it never means the research is true.

Delivery is kept apart from outcome. A request the producer answered —
with a refusal (4xx), with an error (5xx), with something that is not
JSON, with a redirect, with too many bytes — was DELIVERED, and after a
5xx or an unreadable answer whether the producer accepted or ran the
work is NOT known; only a connection or read failure leaves delivery
itself unknown. Nothing is sent again by itself in either case.

Nothing here follows a redirect, accepts a client-supplied URL as a
backend, or writes a credential anywhere: the credential is read from the
environment at the moment of the request through the connector's
reference, as the fetcher already does.
"""
from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

import federation
import testmode
import wordicon_cli as cli

# ---- the pinned contracts ----------------------------------------------------------------
#
# repo / revision / date: the producer's main as checked out by the owner
# (origin/main at the same commit); read with `git show <rev>:<path>`.
# Each route: method, path (with the mount that gives it that path), the
# file:line of the handler, auth, the request and reply as the source
# builds them, the side effects the source shows. "implemented" says the
# adapter exercises it; a route listed but not implemented is declared so
# the reader knows it exists.

CONTRACTS = {
    "ethicalalt": {
        "repo": "ETHICAL_ALTERNATIVES (github.com/Swixixle)",
        "revision": "1a71460a9bbae62124f9cf774f25f4c05c0b1f61",
        "revision_date": "2026-04-24",
        "branch": "main (= origin/main)",
        "read_on": "2026-09-16, from the owner's checkout, read-only git plumbing",
        "routes": {
            "index": {"method": "GET", "path": "/api/profiles/index", "auth": "none",
                      "source": "server/routes/profiles.index.route.js:16 (router mounted at /api/profiles, server/index.js:132)",
                      "reply": "a JSON array of {brand_slug, display_name, sector, overall_concern_level, generated_headline, has_deep_research}",
                      "side_effects": "none — a read", "implemented": True},
            "start": {"method": "POST", "path": "/api/investigate", "auth": "none",
                      "source": "server/routes/tap.js:506 (router mounted at /api, server/index.js:153)",
                      "request": "{brand: string (required), session_id?: string}",
                      "reply": "synchronous: {identification, identification_tier, investigation (the profile; brand_slug and brand, or null), results: [], "
                               "registry_results, local_results, scene_inventory, searched_sources, empty_sources, version: 'v1', response_ms}; "
                               "400 {error:'brand required'}; 500 {error}",
                      "side_effects": "the producer researches the brand through its own model providers (billed on its side) and creates or updates its profile; "
                                      "it records the request in its tap history under session_id (saveTapHistoryAsync) and in its impact log (recordImpactAfterTypedInvestigate)",
                      "limits": "none declared in the route; the orchestrator is environment-gated on the producer's side",
                      "implemented": True},
            "export": {"method": "GET", "path": "/api/profiles/{slug}/export", "auth": "none",
                       "source": "server/routes/profiles.index.route.js:71 (buildStructuredIncidentExport, server/services/profileIncidentExport.js)",
                       "reply": "{schema_version:'1.0', brand_slug, brand_name, unique_incident_count, category_placement_count, generated_at, incidents[]} — UNSIGNED; "
                                "the route's own comment: 'Structured incidents for researchers (not the signed receipt)'; Cache-Control: public, max-age=300",
                       "side_effects": "none — a read", "implemented": True},
            "receipt": {"method": "POST", "path": "/api/receipt/generate", "auth": "none",
                        "source": "server/routes/receipt.js:178 (router mounted at /api/receipt, server/index.js:142); body and signature: server/services/investigationReceipt.js:21-71,149-241",
                        "request": "{slug: string (required), investigation_id?: string, data_source?: string}",
                        "reply": "{receipt_id, signed_receipt, signature: 'ed25519:<base64url>', public_key: SPKI DER base64url, verify_url, cached: bool}; "
                                 "400 missing_slug / no_deep_research / no_deep_categories; 404 profile_not_found; 503 signing_key_unconfigured; 500 server_error",
                        "signing": "Ed25519 over the UTF-8 bytes of stableStringify(signed_receipt): keys sorted by UTF-16 code units at every level, JSON.stringify "
                                   "formatting, no whitespace. signed_receipt: receipt_id, subject{brand_name, brand_slug, ultimate_parent}, investigated_at, generated_at, "
                                   "incident_count, category_summary[{category, count, overflow}], source_urls, source_count, incidents_hash, data_source, "
                                   "last_deep_researched, disclaimer, methodology_url, issuer, schema_version '1.0', overall_concern_level, investigation_id (when sent)",
                        "incidents_hash": "sha256 of JSON.stringify of the profile's DEEP-RESEARCH incidents sorted by source_url — it covers the incidents the "
                                          "receipt was built from, NOT the export route's payload, so it cannot be recomputed from the export",
                        "side_effects": "a WRITE on the producer: the receipt it issues is stored (INSERT INTO investigation_receipts) unless one exists for the same "
                                        "slug and incidents_hash, in which case that earlier receipt is returned with cached: true — its investigation_id is the earlier request's",
                        "implemented": True},
            "receipt_verify": {"method": "GET", "path": "/api/receipt/verify/{receipt_id}", "auth": "none",
                               "source": "server/routes/receipt.js:296", "reply": "{valid, signature_verified, ...}",
                               "side_effects": "none — a read", "implemented": False,
                               "why_not": "verification is done here, locally, under the pinned key; the producer's own verdict on its own receipt is not evidence"},
        },
        "not_served": {
            "package_export": {"path": "/api/profiles/{slug}/export/v2", "method": "ethicalalt.export.v2",
                               "served_by": "the local branch block107/export-v2 only (443c764 'Add the signed structured profile export v2', 84986ab 2026-09-03) — "
                                            "not on main, not on origin/main at 1a71460",
                               "what": "the signed package (nikodemus.deposition.v1) the federation core imports into custody"},
        },
    },
    "open_case": {
        "repo": "Open-Case (github.com/Swixixle)",
        "revision": "4dc17090feb9915204070e9fdd65fcc0d2813867",
        "revision_date": "2026-07-12",
        "branch": "origin/main",
        "branch_note": "the owner's checkout has aca9920 (fix/fail-closed-key-handling) checked out; 4dc1709 merges it into main with an identical tree for every file named below",
        "read_on": "2026-09-16, from the owner's checkout, read-only git plumbing",
        "routes": {
            "cases": {"method": "GET", "path": "/api/v1/cases", "auth": "none (GET routes are public: auth.py:2-4)",
                      "source": "routes/reporting.py:851 (router prefix /api/v1, reporting.py:51); query: government_level, branch, subject_type, pilot, limit ≤ 500",
                      "reply": "{count, cases: [{id, slug, title, subject_name, subject_type, jurisdiction, status, government_level, branch, pilot_cohort, created_at}]}",
                      "side_effects": "none — a read", "implemented": True},
            "start": {"method": "POST", "path": "/api/v1/cases/{case_id}/investigate", "auth": "bearer — Authorization: Bearer open_case_<64 hex> (auth.py:40-75)",
                      "source": "routes/investigate.py:1976 (router prefix /api/v1, investigate.py:143); body model InvestigateRequest, investigate.py:1087",
                      "request": "{subject_name (required), investigator_handle (required — must equal the key holder's handle, else 403: auth.py:31), "
                                 "address?, bioguide_id?, proximity_days=90, fec_committee_id?}",
                      "reply": "synchronous: {case_id, subject_searched, address_searched, sources_checked, cache_hits, evidence_entries_created, signals_detected, "
                               "signals_unresolved, anticipatory_signals, retrospective_signals, required_sources_ready, required_sources_missing, errors, signals, "
                               "collision_warnings, source_statuses} (investigate.py:1934-1975); 422 with the same shape and evidence_entries_created 0 when required "
                               "sources are missing (investigate.py:1712), or 422 {detail} when a run produced zero signals (investigate.py:1892); 404 case not found",
                      "side_effects": "the producer checks its sources for the subject, creates evidence entries and signals on the case, and runs enrichment as a background "
                                      "task; its own providers are called and billed on its side",
                      "limits": "proximity_days 1–1095; none other declared",
                      "implemented": True},
            "report": {"method": "GET", "path": "/api/v1/cases/{case_id}/report", "auth": "none",
                       "source": "routes/reporting.py:924", "reply": "the case report (_collect_report_payload)",
                       "side_effects": "a read the producer COUNTS: bump_view=True; and when the case needs an FEC refresh the producer schedules its own "
                                       "report_pattern_refresh_task in the background",
                       "implemented": True},
            "case": {"method": "GET", "path": "/cases/{case_id}", "auth": "none", "source": "routes/cases.py:247 (router prefix /cases, cases.py:30)",
                     "reply": "the case detail", "side_effects": "none — a read", "implemented": False, "why_not": "the report route carries what the card shows"},
            "snapshot": {"method": "POST", "path": "/cases/{case_id}/snapshot", "auth": "bearer (as above); taken_by must equal the key holder's handle (403)",
                         "source": "routes/snapshots.py:28 (attached to the cases router, prefix /cases: cases.py:296); signing.py:98-125,189",
                         "request": "{taken_by (required), label: string = ''}",
                         "reply": "{snapshot: {id, case_file_id, snapshot_number, taken_at, taken_by, entry_count, signed_hash, share_url, label}, signature_check, case}",
                         "signing": "signed_hash is a JSON string {content_hash, signature, payload}: content_hash = sha256 hex of the JCS (RFC 8785) canonical payload; "
                                    "signature = Ed25519 over the UTF-8 bytes of that hex digest, base64 (empty when the producer has no signing key: an unsigned snapshot)",
                         "side_effects": "a MUTATION on the producer: a snapshot row is created; an Investigator row is created for taken_by if none exists; the case file "
                                         "is re-signed (apply_case_file_signature); the handle is credited +1 (add_credibility)",
                         "implemented": True, "separate_action": "investigate.opencase.snapshot — never part of a start"},
        },
        "not_served": {
            "package_export": {"path": "/api/v1/cases/{id}/export", "method": "open_case.seal.v1",
                               "served_by": "the local branch block107/export-contract only (17a82f8 'Add the signed case-export contract', on top of 4dc1709) — "
                                            "not on main, not on origin/main",
                               "what": "the signed package (nikodemus.deposition.v1) the federation core imports into custody"},
            "exportable": {"path": "/api/v1/cases/exportable", "served_by": "the same branch only"},
        },
    },
}

PACKAGE_CONTRACT = {
    "what": "nikodemus.deposition.v1 — Nikodemus's own package envelope (block 107), imported into custody by the federation core and verified under a pinned key",
    "served_by_main": False,
    "note": "at the pinned revisions neither producer's main serves it; each has it on an unpushed local branch (see CONTRACTS[*]['not_served']). "
            "The federation journey and the golden fixtures under tests/fixtures/federation exercise that contract against the mock producer's "
            "COMPATIBILITY routes, which are labelled as such; they prove the verifier, not a deployment.",
}

ADAPTERS = {
    "ethicalalt": {
        "display": "EthicalAlt",
        "adapter_version": "ethicalalt-adapter/2",
        "connector_kind": "ethicalalt",
        "contract_source": "EthicalAlt source at 1a71460 (main, 2026-04-24), read 2026-09-16 with git show; not verified against a deployment from this workspace",
        "contract": CONTRACTS["ethicalalt"],
        "lookup": {"method": "GET", "path": "/api/profiles/index", "auth": "none", "meaning": "the producer's own profile index — a read"},
        "start": {"method": "POST", "path": "/api/investigate", "payload": ("brand", "session_id"), "auth": "none", "synchronous": True,
                  "upstream_id": "session_id, minted here and recorded by the producer in its tap history", "status": None, "cancel": None,
                  "side_effects": CONTRACTS["ethicalalt"]["routes"]["start"]["side_effects"],
                  "limits": CONTRACTS["ethicalalt"]["routes"]["start"]["limits"],
                  "id_correlation": "the reply's investigation.brand_slug; then the export under that slug and the receipt whose subject.brand_slug is that slug "
                                    "and whose investigation_id is this operation's id (unless the producer returned a cached receipt)"},
        "artifact": {"method": "GET", "path": "/api/profiles/{id}/export", "signed": False,
                     "meaning": "the producer's UNSIGNED structured export, kept byte for byte with its hash — evidence of what the producer served, not a signed record"},
        "receipt": {"method": "POST", "path": "/api/receipt/generate", "signed": True,
                    "meaning": "the producer's signed receipt, verified here as Ed25519 over stableStringify(signed_receipt) under the pinned key; a write on the producer"},
        "package_contract": {**CONTRACTS["ethicalalt"]["not_served"]["package_export"], "path": "/api/profiles/{id}/export/v2", "served": False},
        "subject": "a company or brand name",
    },
    "open_case": {
        "display": "Open Case",
        "adapter_version": "open-case-adapter/2",
        "connector_kind": "open_case",
        "contract_source": "Open Case source at 4dc1709 (origin/main, 2026-07-12), read 2026-09-16 with git show; not verified against a deployment from this workspace",
        "contract": CONTRACTS["open_case"],
        "lookup": {"method": "GET", "path": "/api/v1/cases", "auth": "none", "meaning": "the producer's own case list — a read"},
        "start": {"method": "POST", "path": "/api/v1/cases/{id}/investigate", "payload": ("subject_name", "investigator_handle"), "auth": "bearer", "synchronous": True,
                  "upstream_id": "the case id the request names", "status": None, "cancel": None,
                  "side_effects": CONTRACTS["open_case"]["routes"]["start"]["side_effects"],
                  "limits": CONTRACTS["open_case"]["routes"]["start"]["limits"],
                  "id_correlation": "the case id: the reply's case_id, then the report under that id"},
        "artifact": {"method": "GET", "path": "/api/v1/cases/{id}/report", "signed": False,
                     "meaning": "the case report, kept byte for byte with its hash — a read the producer counts as a view"},
        "receipt": {"method": "POST", "path": "/cases/{id}/snapshot", "signed": True,
                    "meaning": "a signed snapshot — a SEPARATE mutation on the producer (a snapshot row, a re-signed case file, a credit to the handle), "
                               "its own action and proposal; verified here as JCS → sha256 hex → Ed25519 under the pinned key"},
        "snapshot": {"method": "POST", "path": "/cases/{id}/snapshot", "payload": ("taken_by", "label"), "auth": "bearer", "synchronous": True,
                     "side_effects": CONTRACTS["open_case"]["routes"]["snapshot"]["side_effects"]},
        "package_contract": {**CONTRACTS["open_case"]["not_served"]["package_export"], "path": "/api/v1/cases/{id}/export", "served": False},
        "subject": "a case id (36 characters), your investigator handle, then the subject's name",
    },
    "public_eye": {
        "display": "PUBLIC EYE",
        "adapter_version": "public-eye-adapter/0",
        "connector_kind": None,
        "contract_source": "PUBLIC EYE source (formerly FRAME), read for report 80 on 2026-09-15; its repository was not re-read for this revision",
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
ARTIFACTS_DIR = "operation_artifacts"      # local_state/operation_artifacts/<op_id>/<name> — the producer's bytes, exactly


class AdapterError(Exception):
    """delivery: 'not_sent' (refused before the boundary), 'delivered' (the
    producer answered) or 'unknown' (a connection or read failure: the
    request may have arrived). outcome: 'not_sent', 'refused' (a 4xx —
    delivered, and the producer declined it), 'error_after_delivery' (a
    5xx, a redirect, an unreadable or oversized answer — delivered, and
    whether the producer accepted or ran the work is not known) or
    'unknown'."""
    def __init__(self, message: str, status: int = 400, nothing_sent: bool = True, outcome: str = "", delivery: str = ""):
        super().__init__(message)
        self.status = status
        self.nothing_sent = nothing_sent
        self.outcome = outcome or ("not_sent" if nothing_sent else "refused")
        self.delivery = delivery or ("not_sent" if nothing_sent else "delivered")


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
    """Whether the owner recorded that this connector's deployment runs the
    pinned revision — a ruling in the connector log, never a default.
    Returns {"enabled": bool, "by": ..., "note": ..., "at": ...}."""
    if not connector:
        return {"enabled": False}
    rows = [r for r in federation._rows(federation.connectors_log())
            if r.get("kind") == "live_start" and r.get("connector_id") == connector.get("connector_id")]
    if not rows:
        return {"enabled": False}
    last = rows[-1]
    return {"enabled": bool(last.get("enabled")), "by": last.get("by", ""), "note": last.get("note", ""), "at": last.get("recorded_at", ""),
            "revision": last.get("revision", "")}


def rule_live_start(connector_id: str, enabled: bool, note: str = "", by: str = "owner") -> dict:
    """The owner's ruling that a connector's deployment runs the pinned
    revision, so its contract holds there (or that it does not). Recorded,
    never inferred; never made by this code. The ruling names the revision
    it was made against, so a later re-pin does not inherit it."""
    c = federation.get_connector(connector_id)
    if c is None:
        raise AdapterError("no such connector", 404)
    producer = next((k for k, v in ADAPTERS.items() if v.get("connector_kind") == c.get("producer")), "")
    rev = (CONTRACTS.get(producer) or {}).get("revision", "")
    return federation._append(federation.connectors_log(), {"kind": "live_start", "connector_id": connector_id, "enabled": bool(enabled),
                                                             "note": str(note or "")[:300], "by": by, "revision": rev})


def readiness(producer: str, wants: str) -> dict:
    """Derived per capability from the record (§10): configured, contract
    (source-verified, and which revision), credentials, the last explicit
    connection check, lookup available, start available, deployment
    verified, reachable at the last check. No remote check is made here."""
    ad = ADAPTERS.get(producer)
    ct = CONTRACTS.get(producer) or {}
    out = {"producer": producer, "configured": False, "enabled": False, "contract": "unknown", "credential": "not required",
           "last_check": "never tried", "reachable_last": None, "deployment_verified": False, "lookup_available": False,
           "start_available": False, "available": False, "reason": "", "adapter_version": (ad or {}).get("adapter_version", "none"),
           "contract_source": (ad or {}).get("contract_source", ""), "connector_id": "",
           "contract_verified": ("source" if ct else "none"), "contract_revision": ct.get("revision", ""), "contract_revision_date": ct.get("revision_date", ""),
           "package_contract_served": False if ct else None}
    if not ad:
        out["reason"] = "no adapter for this producer"
        return out
    if not ad.get("connector_kind"):
        out["reason"] = ad.get("why_unavailable", "no connector kind")
        out["contract"] = "declared, not connectable" if ad.get("start") else "none"
        return out
    pin = f"pinned from source: {ad['display']} at {ct.get('revision', '')[:7]} ({ct.get('branch', 'main')}, {ct.get('revision_date', '')})"
    c = _connector_for(producer)
    if not c:
        out["reason"] = "no connector registered"
        out["contract"] = (f"lookup {ad['lookup']['method']} {ad['lookup']['path']} — {pin}" if wants == "lookup"
                           else f"start {ad['start']['method']} {ad['start']['path']} — {pin}; fixture-proven")
        return out
    out.update({"configured": True, "enabled": bool(c.get("enabled")), "connector_id": c.get("connector_id"),
                "last_check": c.get("status") or "never tried", "last_success_at": c.get("last_success_at") or "",
                "reachable_last": (True if str(c.get("status") or "").startswith("reachable") else (False if str(c.get("status") or "").startswith("last attempt failed") else None))})
    needs_cred = (ad.get("start", {}).get("auth") == "bearer") if wants == "start" else (federation.PRODUCERS.get(ad["connector_kind"], {}).get("auth") == "bearer")
    if needs_cred:
        out["credential"] = "present" if c.get("credential_configured") else "missing"
    ruling = live_start_ruling(c)
    out["deployment_verified"] = bool(ruling.get("enabled")) and (not ruling.get("revision") or ruling.get("revision") == ct.get("revision"))
    out["live_start_ruling"] = ruling
    if wants == "lookup":
        out["contract"] = f"lookup {ad['lookup']['method']} {ad['lookup']['path']} — {pin}; the rooms' import (the package contract) is not served by main"
        if not c.get("enabled"):
            out["reason"] = "the connector is disabled"
        elif needs_cred and not c.get("credential_configured"):
            out["reason"] = "the credential named on the connector is not present"
        else:
            out["lookup_available"] = out["available"] = True
        return out
    out["contract"] = f"start {ad['start']['method']} {ad['start']['path']} — {pin}"
    if not c.get("enabled"):
        out["reason"] = "the connector is disabled"
    elif needs_cred and not c.get("credential_configured"):
        out["reason"] = "the credential named on the connector is not present"
    elif out["deployment_verified"]:
        out["start_available"] = out["available"] = True
        out["reason"] = ""
    elif ruling.get("enabled") and ruling.get("revision") and ruling.get("revision") != ct.get("revision"):
        out["reason"] = (f"starting is disabled: your ruling was recorded against revision {str(ruling.get('revision'))[:7]}, and the contract is now pinned at "
                         f"{str(ct.get('revision'))[:7]} — record it again if the deployment runs this revision")
    elif testmode.active() and c.get("dev_loopback"):
        out["start_available"] = out["available"] = True
        out["reason"] = "test mode: a declared development connector on loopback (the fixture producer)"
        out["fixture_only"] = True
    else:
        out["reason"] = (f"starting is disabled until you record that this deployment runs the pinned revision {str(ct.get('revision'))[:7]}: the contract is "
                         "read from the producer's source, not proven against this connector's deployment — record the ruling on the connector to enable it")
    return out


# ---- EthicalAlt's canonicalization, re-implemented byte for byte ---------------------------
#
# server/services/investigationReceipt.js:21-31 @1a71460:
#   stableStringify(val): null/non-object → JSON.stringify(val); array → "[" +
#   elements joined by "," + "]"; object → "{" + Object.keys(o).sort() mapped to
#   JSON.stringify(k) + ":" + stableStringify(o[k]), joined by "," + "}".
# The three places Python's json differs from JSON.stringify are handled by
# hand: number layout (Number::toString), string escapes (JSON.stringify
# escapes only ", \, and controls below 0x20, plus lone surrogates), and key
# order (Array.prototype.sort compares UTF-16 code units). Proven against
# tests/fixtures/producers/ethicalalt.stable-stringify.vectors.json, which
# the producer's own function wrote under Node.

_FLOAT_RX = re.compile(r"^(-?)(\d+)(?:\.(\d+))?(?:e([+-]\d+))?$")
_ESC = {'"': '\\"', "\\": "\\\\", "\b": "\\b", "\f": "\\f", "\n": "\\n", "\r": "\\r", "\t": "\\t"}


def _js_number(x) -> str:
    """ECMAScript Number::toString (ES2023 §6.1.6.1.20) for the value as the
    producer holds it — a double. Python's repr gives the same shortest
    round-trip digits; only the layout differs: integers print in full below
    1e21, the exponent form starts at 1e21 and below 1e-6, and the exponent
    is never zero-padded."""
    if isinstance(x, int):
        if abs(x) < 2 ** 53:
            return str(x)
        x = float(x)                       # a JSON integer beyond 2^53 is a double to the producer
    if not math.isfinite(x):
        return "null"                      # JSON.stringify(NaN/Infinity); a JSON body cannot carry them anyway
    if x == 0:
        return "0"                         # -0 prints as 0
    m = _FLOAT_RX.match(repr(float(x)))
    sign, ip, fp, ex = m.group(1), m.group(2), m.group(3) or "", int(m.group(4) or 0)
    raw = (ip + fp).lstrip("0")
    e10 = ex - len(fp)                     # value = int(ip+fp) × 10^e10
    stripped = raw.rstrip("0")
    e10 += len(raw) - len(stripped)
    d = stripped or "0"
    k = len(d)
    n = k + e10                            # value = 0.d × 10^n
    if k <= n <= 21:
        s = d + "0" * (n - k)
    elif 0 < n <= 21:
        s = d[:n] + "." + d[n:]
    elif -6 < n <= 0:
        s = "0." + "0" * (-n) + d
    else:
        e = n - 1
        s = d[0] + ("." + d[1:] if k > 1 else "") + "e" + ("+" if e >= 0 else "-") + str(abs(e))
    return sign + s


def _js_string(s: str) -> str:
    out = []
    for ch in s:
        o = ord(ch)
        if ch in _ESC:
            out.append(_ESC[ch])
        elif o < 0x20 or 0xD800 <= o <= 0xDFFF:
            out.append("\\u%04x" % o)      # controls, and a lone surrogate (well-formed JSON.stringify)
        else:
            out.append(ch)
    return '"' + "".join(out) + '"'


def stable_stringify(v) -> str:
    """EthicalAlt's stableStringify, byte for byte (see above)."""
    if v is None:
        return "null"
    if v is True:
        return "true"
    if v is False:
        return "false"
    if isinstance(v, (int, float)):
        return _js_number(v)
    if isinstance(v, str):
        return _js_string(v)
    if isinstance(v, list):
        return "[" + ",".join(stable_stringify(x) for x in v) + "]"
    if isinstance(v, dict):
        keys = sorted(v.keys(), key=lambda k: k.encode("utf-16-be", "surrogatepass"))
        return "{" + ",".join(_js_string(k) + ":" + stable_stringify(v[k]) for k in keys) + "}"
    raise TypeError(f"not a JSON value: {type(v).__name__}")


def _pinned_raw_keys(connector: dict | None) -> list[dict]:
    out = []
    for t in (connector or {}).get("trusted_keys") or []:
        try:
            out.append({"key_id": t.get("key_id", ""), "raw": base64.b64decode(t["public_key_b64"]), "label": t.get("label", "")})
        except Exception:  # noqa: BLE001
            continue
    return out


def verify_ethicalalt_receipt(reply: dict, connector: dict | None) -> dict:
    """The receipt route's reply, verified under the connector's pinned keys
    and nothing else: the signature is Ed25519 over stableStringify(
    signed_receipt); the reply's own public_key is compared to the pinned
    key and reported, never trusted. Returns {ok, why, method, key_id,
    key_in_reply_matches_pinned, cached, receipt_id, investigation_id,
    subject_slug, incidents_hash}."""
    out = {"ok": False, "why": "", "method": "ethicalalt.receipt.v1 (stableStringify + Ed25519)", "key_id": "", "key_in_reply_matches_pinned": None,
           "cached": bool(reply.get("cached")) if isinstance(reply, dict) else None, "receipt_id": "", "investigation_id": "", "subject_slug": "", "incidents_hash": ""}
    if not isinstance(reply, dict) or not isinstance(reply.get("signed_receipt"), dict) or not reply.get("signature"):
        out["why"] = "the reply is not a receipt: no signed_receipt object or no signature"
        return out
    body = reply["signed_receipt"]
    out.update({"receipt_id": str(reply.get("receipt_id") or body.get("receipt_id") or ""), "investigation_id": str(body.get("investigation_id") or ""),
                "subject_slug": str((body.get("subject") or {}).get("brand_slug") or "") if isinstance(body.get("subject"), dict) else "",
                "incidents_hash": str(body.get("incidents_hash") or "")})
    sig = str(reply.get("signature") or "")
    if not sig.startswith("ed25519:"):
        out["why"] = "the signature is not 'ed25519:<base64url>'"
        return out
    try:
        sigbytes = federation._b64decode_any(sig[len("ed25519:"):])
    except Exception as e:  # noqa: BLE001
        out["why"] = f"the signature is not base64url: {e}"
        return out
    try:
        message = stable_stringify(body).encode("utf-8", "surrogatepass")
    except Exception as e:  # noqa: BLE001
        out["why"] = f"the receipt body cannot be canonicalized: {e}"
        return out
    pinned = _pinned_raw_keys(connector)
    if not pinned:
        out["why"] = "unverified: no key is pinned on this connector — pin the producer's receipt public key out of band, never from a reply"
        return out
    try:
        reply_raw = federation._raw_public_key(str(reply.get("public_key") or "")) if reply.get("public_key") else b""
    except ValueError:
        reply_raw = b""
    out["key_in_reply_matches_pinned"] = bool(reply_raw) and any(reply_raw == p["raw"] for p in pinned)
    for p in pinned:
        try:
            if federation.verify_ed25519(p["raw"], message, sigbytes):
                out.update({"ok": True, "key_id": p["key_id"], "why": ""})
                return out
        except RuntimeError as e:
            out["why"] = str(e)
            out["library_missing"] = True
            return out
    out["why"] = "the signature does not verify under any pinned key" + ("" if out["key_in_reply_matches_pinned"] else
                                                                        " (and the key the reply carries is not the pinned one — a reply's key is never trusted)")
    return out


def verify_open_case_signed_hash(packed: str, connector: dict | None) -> dict:
    """Open Case's signed_hash (signing.py:189 pack_signed_hash): a JSON
    string {content_hash, signature, payload}. content_hash must be the
    sha256 hex of the JCS-canonical payload; the signature is Ed25519 over
    the UTF-8 bytes of that hex digest (signing.py:98-125), verified under
    the pinned key only. An empty signature is an UNSIGNED snapshot (the
    producer had no signing key), said so."""
    out = {"ok": False, "why": "", "method": "open_case.snapshot (JCS → sha256 hex → Ed25519)", "key_id": "", "content_hash": "", "unsigned": False}
    try:
        obj = json.loads(packed) if isinstance(packed, str) else packed
    except (ValueError, TypeError) as e:
        out["why"] = f"signed_hash is not JSON: {e}"
        return out
    if not isinstance(obj, dict) or not isinstance(obj.get("payload"), dict) or not obj.get("content_hash"):
        out["why"] = "signed_hash carries no payload or no content_hash"
        return out
    try:
        digest = federation.payload_sha256(obj["payload"])
    except Exception as e:  # noqa: BLE001
        out["why"] = f"the payload cannot be canonicalized: {e}"
        return out
    out["content_hash"] = digest
    if digest != str(obj.get("content_hash")):
        out["why"] = "content_hash does not match the canonical payload (the bytes changed, or the hash was forged)"
        return out
    if not obj.get("signature"):
        out.update({"unsigned": True, "why": "the snapshot is UNSIGNED: the producer issued it without a signing key (signature empty) — the hash matches, nothing vouches for it"})
        return out
    try:
        sigbytes = base64.b64decode(str(obj["signature"]))
    except Exception as e:  # noqa: BLE001
        out["why"] = f"the signature is not base64: {e}"
        return out
    pinned = _pinned_raw_keys(connector)
    if not pinned:
        out["why"] = "unverified: no key is pinned on this connector — pin the producer's public key out of band"
        return out
    for p in pinned:
        try:
            if federation.verify_ed25519(p["raw"], digest.encode("utf-8"), sigbytes):
                out.update({"ok": True, "key_id": p["key_id"]})
                return out
        except RuntimeError as e:
            out["why"] = str(e)
            out["library_missing"] = True
            return out
    out["why"] = "the signature does not verify under any pinned key"
    return out


# ---- custody of the producer's bytes, under the operation ------------------------------------

def artifact_dir(op_id: str) -> Path:
    return Path(cli.LOCAL_STATE) / ARTIFACTS_DIR / re.sub(r"[^A-Za-z0-9_\-]", "_", op_id)[:80]


def keep_artifact(op_id: str, name: str, raw: bytes) -> dict:
    """The producer's exact bytes, written once under the operation and
    hashed; the hash goes into the record. Same name again: the earlier
    bytes stay (a second copy is written beside them, numbered)."""
    d = artifact_dir(op_id)
    d.mkdir(parents=True, exist_ok=True)
    p = d / name
    n = 2
    while p.exists():
        if p.read_bytes() == raw:
            break
        p = d / f"{Path(name).stem}.{n}{Path(name).suffix}"
        n += 1
    if not p.exists():
        p.write_bytes(raw)
    return {"name": p.name, "bytes": len(raw), "sha256": hashlib.sha256(raw).hexdigest()}


def artifact_bytes(op_id: str, name: str) -> bytes:
    p = artifact_dir(op_id) / name
    return p.read_bytes() if p.exists() else b""


# ---- the bounded request ------------------------------------------------------------------

def _request(connector: dict, method: str, path: str, body: dict | None, auth: str = "none") -> dict:
    """One request to a configured connector under the fetcher's rules: the
    path is the contract's, the origin is the connector's, no redirect is
    followed, the reply is bounded, the credential comes from the
    environment through the connector's reference. Returns the raw bytes
    with the parsed JSON, or a failure with `delivery` and `outcome` said
    apart."""
    if not connector:
        return {"ok": False, "outcome": "not_configured", "delivery": "not_sent", "detail": "no such connector"}
    if not connector.get("enabled", True):
        return {"ok": False, "outcome": "disabled", "delivery": "not_sent", "detail": "the connector is disabled"}
    if not path.startswith("/") or ".." in path or "://" in path:
        return {"ok": False, "outcome": "origin_refused", "delivery": "not_sent", "detail": "a path only"}
    url = connector["base_url"].rstrip("/") + path
    if federation._origin_of(url) != connector.get("origin"):
        return {"ok": False, "outcome": "origin_refused", "delivery": "not_sent", "detail": "the request would leave the connector's origin"}
    headers = {"Accept": "application/json", "User-Agent": "Nikodemus-connector/2"}
    if body is not None:
        headers["Content-Type"] = "application/json"
    if auth == "bearer":
        cred = federation._credential_value(connector.get("credential_ref", ""))
        if not cred:
            return {"ok": False, "outcome": "credential_unavailable", "delivery": "not_sent", "detail": f"set {connector.get('credential_ref') or 'a credential_ref'} in the server's environment"}
        headers["Authorization"] = "Bearer " + cred
    data = json.dumps(body, ensure_ascii=False).encode("utf-8") if body is not None else None
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    opener = urllib.request.build_opener(federation._NoRedirect())
    t0 = time.monotonic()
    try:
        with opener.open(req, timeout=FETCH_TIMEOUT_S) as resp:
            status = resp.status
            raw = federation._read_bounded(resp, MAX_BYTES)
    except federation._Oversized:
        return {"ok": False, "outcome": "oversized", "delivery": "delivered", "detail": f"the reply exceeded {MAX_BYTES} bytes and was dropped", "status": 200}
    except urllib.error.HTTPError as e:
        raw = b""
        try:
            raw = federation._read_bounded(e, MAX_BYTES)
        except Exception:  # noqa: BLE001
            raw = b""
        if e.code in (301, 302, 303, 307, 308):
            return {"ok": False, "outcome": "redirect_refused", "delivery": "delivered", "detail": "the producer answered with a redirect; not followed", "status": e.code, "raw": raw}
        if e.code in (401, 403):
            return {"ok": False, "outcome": "unauthorized", "delivery": "delivered", "detail": f"HTTP {e.code}", "status": e.code, "raw": raw}
        if e.code == 404:
            return {"ok": False, "outcome": "not_found", "delivery": "delivered", "detail": "HTTP 404", "status": 404, "raw": raw}
        if 400 <= e.code < 500:
            return {"ok": False, "outcome": "refused", "delivery": "delivered", "detail": f"HTTP {e.code}", "status": e.code, "raw": raw}
        return {"ok": False, "outcome": "producer_error", "delivery": "delivered", "detail": f"HTTP {e.code}", "status": e.code, "raw": raw}
    except urllib.error.URLError as e:
        return {"ok": False, "outcome": "unreachable", "delivery": "unknown", "detail": federation._scrub(str(e.reason))[:200]}
    except (TimeoutError, OSError) as e:
        return {"ok": False, "outcome": "unreachable", "delivery": "unknown", "detail": federation._scrub(str(e))[:200]}
    elapsed = round(time.monotonic() - t0, 3)
    try:
        obj = json.loads(raw.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError):
        return {"ok": False, "outcome": "invalid_json", "delivery": "delivered", "detail": "the reply was not JSON", "status": status, "elapsed_s": elapsed, "raw": raw}
    return {"ok": True, "status": status, "json": obj, "raw": raw, "bytes": len(raw), "elapsed_s": elapsed, "delivery": "delivered"}


def post_json(connector: dict, path: str, body: dict, auth: str = "none") -> dict:
    return _request(connector, "POST", path, body, auth=auth)


def get_json(connector: dict, path: str, auth: str = "none") -> dict:
    return _request(connector, "GET", path, None, auth=auth)


def _outcome_of_failure(r: dict) -> tuple[str, str, str]:
    """(outcome, delivery, sentence) for a failed request, with delivery kept
    apart from outcome."""
    o = r.get("outcome", "")
    if r.get("delivery") == "not_sent":
        return "not_sent", "not_sent", f"not sent: {o} — {r.get('detail', '')}"
    if r.get("delivery") == "unknown":
        return "unknown", "unknown", f"no answer came back ({r.get('detail', '')}): whether the request arrived is not known; nothing is sent again by itself"
    if o in ("unauthorized", "not_found", "refused"):
        return "refused", "delivered", f"delivered, and the producer refused it ({r.get('detail', '')})"
    return ("error_after_delivery", "delivered",
            f"delivered, and the producer answered with an error ({o}: {r.get('detail', '')}) — whether it accepted or ran the work is not known; nothing is sent again by itself")


# ---- prepare / start / retrieve / status / recover ---------------------------------------------

_OC_ID_RX = re.compile(r"^[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}$")


def prepare(producer: str, subject_text: str, inputs: dict | None = None, kind: str = "start") -> dict:
    """What a start (or, for Open Case, a snapshot) would send and what it
    would mean — validated locally, nothing sent. Returns the spec the
    proposal freezes."""
    ad = ADAPTERS.get(producer)
    if not ad or not ad.get("connector_kind") or not ad.get("start"):
        raise AdapterError((ad or {}).get("why_unavailable") or "no start contract for this producer", 409)
    text = " ".join(str(subject_text or "").split())
    if not text:
        raise AdapterError(f"an investigation needs {ad['subject']}", 400)
    c = _connector_for(producer)
    rd = readiness(producer, "start")
    ct = CONTRACTS[producer]
    spec = {"producer": producer, "kind": kind, "adapter_version": ad["adapter_version"], "connector_id": (c or {}).get("connector_id", ""),
            "contract_revision": ct["revision"],
            "method": ad["start"]["method"], "path": ad["start"]["path"], "auth": ad["start"]["auth"], "synchronous": ad["start"]["synchronous"],
            "payload_fields": list(ad["start"]["payload"]), "side_effects": ad["start"]["side_effects"], "limits": ad["start"]["limits"],
            "cost": "unknown — the producer's own calls are billed on its side; nothing is priced here", "readiness": rd,
            "then": ("then GET " + ad["artifact"]["path"] + " (unsigned export, kept as bytes) and POST " + ad["receipt"]["path"] + " (a signed receipt the producer stores)")
                    if producer == "ethicalalt" else ("then GET " + ad["artifact"]["path"] + " (the report, a read the producer counts as a view)")}
    if producer == "ethicalalt":
        if kind != "start":
            raise AdapterError("EthicalAlt has no separate mutation to propose", 400)
        spec["brand"] = text[:200]
        return spec
    # Open Case: the case id, the handle bound to the key, then the subject (a start) or a label (a snapshot)
    parts = text.split()
    case_id = parts[0] if parts else ""
    if not _OC_ID_RX.match(case_id):
        raise AdapterError("an Open Case investigation names the case id first (36 characters: 8-4-4-4-12 hex), then your investigator handle, then the subject's name", 400)
    handle = parts[1] if len(parts) > 1 else ""
    rest = " ".join(parts[2:])
    if not handle:
        raise AdapterError("an Open Case investigation names your investigator handle after the case id — it must match the holder of the key on the connector", 400)
    spec["case_id"] = case_id
    spec["handle"] = handle[:80]
    if kind == "snapshot":
        spec.update({"method": ad["snapshot"]["method"], "path": ad["snapshot"]["path"], "payload_fields": list(ad["snapshot"]["payload"]),
                     "side_effects": ad["snapshot"]["side_effects"], "label": rest[:120], "then": "nothing else: the snapshot is the whole act",
                     "mutation": "a snapshot row is created on the producer, the case file is re-signed and the handle credited — this is not a read"})
        return spec
    if not rest:
        raise AdapterError("an Open Case investigation names the subject to investigate after the case id and your handle — the producer requires subject_name; "
                           "without it nothing can be sent", 400)
    spec["subject_name"] = rest[:200]
    return spec


def start(op_id: str, spec: dict, session_id: str) -> dict:
    """The one outbound POST, at the boundary: a dispatch intent event
    before, the outcome with the upstream id after, the producer's exact
    reply kept under the operation. Returns what the producer said, never
    more than the record holds."""
    import operations as ops
    producer = spec["producer"]
    ad = ADAPTERS[producer]
    c = federation.get_connector(spec.get("connector_id") or "") or _connector_for(producer)
    rd = readiness(producer, "start")
    if not rd["start_available"]:
        raise AdapterError(f"{ad['display']} cannot be started: {rd['reason']}", 409)
    kind = spec.get("kind", "start")
    if producer == "ethicalalt":
        method, path, body, auth = "POST", ad["start"]["path"], {"brand": spec["brand"], "session_id": session_id}, "none"
        upstream = session_id
    elif kind == "snapshot":
        method, path, body, auth = "POST", ad["snapshot"]["path"].replace("{id}", spec["case_id"]), {"taken_by": spec["handle"], "label": spec.get("label", "")}, "bearer"
        upstream = spec["case_id"]
    else:
        method, path, body, auth = "POST", ad["start"]["path"].replace("{id}", spec["case_id"]), {"subject_name": spec["subject_name"], "investigator_handle": spec["handle"]}, "bearer"
        upstream = spec["case_id"]
    stage = f"{method} {path}"
    ops.event(op_id, "stage_intent", stage=stage, upstream_id=upstream,
              detail={"producer": producer, "adapter_version": ad["adapter_version"], "contract_revision": spec.get("contract_revision", ""),
                      "fields": list(body.keys()), "synchronous": True, "kind": kind})
    r = _request(c, method, path, body, auth=auth)
    kept = keep_artifact(op_id, "snapshot-reply.json" if kind == "snapshot" else "start-reply.json", r["raw"]) if r.get("raw") else None
    if not r.get("ok"):
        outcome, delivery, sentence = _outcome_of_failure(r)
        ops.event(op_id, "stage_end", stage=stage, upstream_id=upstream, outcome="error",
                  detail={"outcome": r.get("outcome", ""), "delivery": delivery, "status": r.get("status"), "elapsed_s": r.get("elapsed_s"),
                          "detail": r.get("detail", ""), "reply_kept": kept})
        federation._record_attempt(c["connector_id"], r.get("outcome", "error"), r.get("detail", "start"), ok=False, object_id=upstream, http_status=r.get("status"))
        raise AdapterError(f"the start was {sentence}", 502, nothing_sent=(delivery == "not_sent"), outcome=outcome, delivery=delivery)
    ops.event(op_id, "stage_end", stage=stage, upstream_id=upstream, outcome="ok",
              detail={"outcome": "ok", "delivery": "delivered", "status": r.get("status"), "elapsed_s": r.get("elapsed_s"), "reply_kept": kept})
    federation._record_attempt(c["connector_id"], "ok", "start answered", ok=True, object_id=upstream, http_status=r.get("status"))
    reply = r["json"] if isinstance(r["json"], dict) else {}
    if producer == "ethicalalt":
        inv = reply.get("investigation") if isinstance(reply.get("investigation"), dict) else None
        object_id = str((inv or {}).get("brand_slug") or "")
        producer_state = {"identification_tier": reply.get("identification_tier"), "version": reply.get("version"), "response_ms": reply.get("response_ms"),
                          "investigation": ("present: brand_slug " + object_id if object_id else ("present, no brand_slug" if inv else "null — the producer found nothing to profile")),
                          "brand": (inv or {}).get("brand")}
    elif kind == "snapshot":
        snap = reply.get("snapshot") if isinstance(reply.get("snapshot"), dict) else {}
        object_id = str(snap.get("id") or "")
        producer_state = {"snapshot_number": snap.get("snapshot_number"), "entry_count": snap.get("entry_count"), "taken_at": snap.get("taken_at"),
                          "share_url": snap.get("share_url"), "signature_check": reply.get("signature_check")}
    else:
        object_id = str(reply.get("case_id") or spec.get("case_id") or "")
        producer_state = {k: reply.get(k) for k in ("sources_checked", "cache_hits", "evidence_entries_created", "signals_detected", "signals_unresolved",
                                                     "required_sources_ready", "required_sources_missing") if k in reply}
        if reply.get("errors"):
            producer_state["errors"] = len(reply["errors"]) if isinstance(reply["errors"], list) else str(reply["errors"])[:200]
    return {"upstream_id": upstream, "producer_state": producer_state, "object_id": object_id, "reply_keys": sorted(reply.keys())[:30],
            "reply_kept": kept, "kind": kind, "reply": reply}


def retrieve(op_id: str, spec: dict, object_id: str, reply: dict | None = None) -> dict:
    """After a start was answered: the producer's artifact, kept byte for
    byte, and its signed record where the producer issues one — EthicalAlt:
    the unsigned export (a read) then the receipt (a write on the producer,
    verified here); Open Case: the report (a read the producer counts).
    A snapshot needs nothing more: its signed record IS the reply."""
    import operations as ops
    producer = spec["producer"]
    ad = ADAPTERS[producer]
    c = federation.get_connector(spec.get("connector_id") or "") or _connector_for(producer)
    out = {"ok": False, "artifact": None, "receipt": None, "verification": None, "outcome": "", "detail": ""}
    if spec.get("kind") == "snapshot":
        packed = (((reply or {}).get("snapshot") or {}).get("signed_hash")) if isinstance(reply, dict) else None
        ver = verify_open_case_signed_hash(packed, c) if packed else {"ok": False, "why": "the reply carries no signed_hash", "method": "open_case.snapshot"}
        out.update({"ok": True, "receipt": {"name": "snapshot-reply.json", "what": "the snapshot reply (signed_hash inside)"}, "verification": ver, "outcome": "verified" if ver.get("ok") else "kept_unverified"})
        ops.event(op_id, "result", upstream_id=object_id, detail={"verification": ver, "artifact": "snapshot-reply.json"})
        return out
    if not object_id:
        out.update({"outcome": "no_object_id", "detail": "the producer named no object to retrieve"})
        return out
    # the artifact: a read
    a_path = ad["artifact"]["path"].replace("{id}", urllib.parse.quote(object_id, safe=""))
    stage = f"GET {a_path}"
    ops.event(op_id, "stage_intent", stage=stage, upstream_id=object_id, detail={"artifact": True, "signed": False})
    r = get_json(c, a_path, auth=("bearer" if producer == "open_case" and federation.PRODUCERS["open_case"]["auth"] == "bearer" else "none"))
    if not r.get("ok"):
        outcome, delivery, sentence = _outcome_of_failure(r)
        ops.event(op_id, "stage_end", stage=stage, upstream_id=object_id, outcome="error", detail={"outcome": r.get("outcome", ""), "delivery": delivery, "status": r.get("status"), "detail": r.get("detail", "")})
        out.update({"outcome": r.get("outcome", "failed"), "detail": "the artifact was " + sentence})
        return out
    name = "export.json" if producer == "ethicalalt" else "report.json"
    kept = keep_artifact(op_id, name, r["raw"])
    ops.event(op_id, "stage_end", stage=stage, upstream_id=object_id, outcome="ok", detail={"outcome": "ok", "delivery": "delivered", "status": r.get("status"), "kept": kept})
    out["artifact"] = {**kept, "signed": False, "what": ("the producer's unsigned structured export" if producer == "ethicalalt" else "the case report")}
    if producer == "ethicalalt":
        ex = r["json"] if isinstance(r["json"], dict) else {}
        out["artifact"]["summary"] = {k: ex.get(k) for k in ("schema_version", "brand_slug", "unique_incident_count", "category_placement_count", "generated_at") if k in ex}
        out["artifact"]["slug_matches"] = (str(ex.get("brand_slug") or "").lower() == object_id.lower()) if ex else None
        # the receipt: a write on the producer, disclosed in the proposal
        r_path = ad["receipt"]["path"]
        stage = f"POST {r_path}"
        ops.event(op_id, "stage_intent", stage=stage, upstream_id=object_id, detail={"receipt": True, "fields": ["slug", "investigation_id"], "mutation": "the producer stores the receipt it issues"})
        rr = post_json(c, r_path, {"slug": object_id, "investigation_id": op_id}, auth="none")
        if not rr.get("ok"):
            outcome, delivery, sentence = _outcome_of_failure(rr)
            why = rr.get("detail", "")
            try:
                j = json.loads((rr.get("raw") or b"").decode("utf-8"))
                if isinstance(j, dict) and j.get("error"):
                    why = str(j["error"])
            except Exception:  # noqa: BLE001
                pass
            ops.event(op_id, "stage_end", stage=stage, upstream_id=object_id, outcome="error", detail={"outcome": rr.get("outcome", ""), "delivery": delivery, "status": rr.get("status"), "detail": why})
            out.update({"ok": True, "receipt": None, "verification": {"ok": False, "why": "no receipt: the request was " + sentence + (" — " + why if why else ""), "method": ""},
                        "outcome": "export_kept_no_receipt", "detail": why})
            ops.event(op_id, "result", upstream_id=object_id, detail={"artifact": kept, "receipt": None, "verification": out["verification"]})
            return out
        rk = keep_artifact(op_id, "receipt.json", rr["raw"])
        ops.event(op_id, "stage_end", stage=stage, upstream_id=object_id, outcome="ok", detail={"outcome": "ok", "delivery": "delivered", "status": rr.get("status"), "kept": rk})
        ver = verify_ethicalalt_receipt(rr["json"] if isinstance(rr["json"], dict) else {}, c)
        ver["correlation"] = _ea_correlation(ver, op_id, object_id)
        out.update({"ok": True, "receipt": {**rk, "signed": True, "cached": ver.get("cached"), "receipt_id": ver.get("receipt_id")}, "verification": ver,
                    "outcome": "verified" if ver.get("ok") else "kept_unverified"})
        ops.event(op_id, "result", upstream_id=object_id, detail={"artifact": kept, "receipt": rk, "verification": {k: v for k, v in ver.items() if k != "correlation"}, "correlation": ver["correlation"]})
        return out
    # Open Case: the report is the artifact; the signed snapshot is a separate action
    rep = r["json"] if isinstance(r["json"], dict) else {}
    out["artifact"]["summary"] = {k: rep.get(k) for k in ("case_id", "title", "subject_name", "status", "evidence_count", "signal_count") if k in rep}
    out.update({"ok": True, "receipt": None, "verification": {"ok": False, "why": "no signed record: the report is unsigned; a signed snapshot is a separate act (Take a signed snapshot)", "method": ""},
                "outcome": "report_kept"})
    ops.event(op_id, "result", upstream_id=object_id, detail={"artifact": kept, "receipt": None, "verification": out["verification"]})
    return out


def _ea_correlation(ver: dict, op_id: str, slug: str) -> dict:
    """How the receipt ties to this operation: by subject slug (always
    required), by investigation_id (unless the producer returned a cached
    receipt, whose investigation_id is an earlier request's), and what
    incidents_hash does and does not cover."""
    slug_ok = bool(ver.get("subject_slug")) and ver["subject_slug"].lower() == slug.lower()
    inv_ok = ver.get("investigation_id") == op_id
    if ver.get("cached"):
        by_id = ("cached: the producer returned the receipt it issued for an earlier investigation of the same deep-research incidents (same slug and incidents_hash); "
                 "its investigation_id" + (" is this operation's" if inv_ok else (" is " + (repr(ver.get("investigation_id")) if ver.get("investigation_id") else "absent") + ", not this operation's")))
    else:
        by_id = "investigation_id is this operation's" if inv_ok else ("investigation_id is " + (repr(ver.get("investigation_id")) if ver.get("investigation_id") else "absent") + ", not this operation's")
    return {"subject_slug_matches": slug_ok, "investigation_id_matches": inv_ok, "cached": bool(ver.get("cached")), "by_id": by_id,
            "incidents_hash": "covers the profile's deep-research incidents the producer built the receipt from — not the export kept here, which cannot reproduce it"}


def status(op: dict) -> dict:
    """Local: what the record says about the producer side — delivery and
    outcome of the start, the artifact and receipt states, the bytes kept.
    No producer is refreshed."""
    import operations as ops
    evs = ops.events(op["op_id"])
    ref = op.get("result_ref") or {}
    pst = op.get("producer_state") or {}
    starts = [e for e in evs if e["kind"] == "stage_end" and e["stage"].startswith("POST") and "/receipt/" not in e["stage"]]
    gets = [e for e in evs if e["kind"] == "stage_end" and e["stage"].startswith("GET")]
    receipts = [e for e in evs if e["kind"] == "stage_end" and "/receipt/" in e["stage"]]
    last_start = starts[-1] if starts else None
    delivery = (last_start["detail"].get("delivery") if last_start else None) or pst.get("delivery") or ("not_sent" if not starts else "delivered")
    if last_start is None:
        start_word = "not sent"
    elif last_start["outcome"] == "ok":
        start_word = "ok"
    else:
        start_word = {"delivered": "refused" if last_start["detail"].get("outcome") in ("unauthorized", "not_found", "refused") else "error after delivery",
                      "unknown": "no answer", "not_sent": "not sent"}.get(delivery, last_start["detail"].get("outcome", "error"))
    ver = ref.get("verification") if isinstance(ref.get("verification"), dict) else None
    if ver and ver.get("ok"):
        receipt = f"signature verified ({ver.get('method', '')}) under the pinned key {str(ver.get('key_id', ''))[:28]}…"
        corr = ver.get("correlation") or {}
        if corr:
            receipt += "; " + corr.get("by_id", "")
            if not corr.get("subject_slug_matches"):
                receipt += "; the receipt's subject slug is NOT the one investigated"
    elif ver:
        receipt = ("UNSIGNED — " if ver.get("unsigned") else "signature NOT verified: ") + str(ver.get("why") or "unverified")
    else:
        receipt = "none"
    art = ref.get("artifact") if isinstance(ref.get("artifact"), dict) else None
    if art:
        artifact = f"{art.get('what', 'artifact')} kept ({art.get('bytes', 0)} bytes, sha256 {str(art.get('sha256', ''))[:12]}…)" + \
                   ("" if art.get("slug_matches") in (None, True) else " — its brand_slug is NOT the one investigated")
    elif gets and gets[-1]["outcome"] == "error":
        artifact = "not retrieved: " + str(gets[-1]["detail"].get("outcome", ""))
    else:
        artifact = "not retrieved"
    kept = [x for x in (ref.get("kept") or []) if x]
    return {"upstream_id": ref.get("upstream_id") or (last_start["upstream_id"] if last_start else ""),
            "start": start_word, "delivery": delivery, "outcome": (pst.get("outcome") or ("ok" if start_word == "ok" else start_word)),
            "artifact": artifact, "receipt": receipt, "verified": bool(ver and ver.get("ok")),
            "receipt_id": (ref.get("receipt") or {}).get("receipt_id", "") if isinstance(ref.get("receipt"), dict) else "",
            "kept": kept or [x for x in (ref.get("artifact"), ref.get("receipt"), ref.get("reply_kept")) if isinstance(x, dict) and x.get("sha256")],
            "receipt_requests": len(receipts), "deposition_id": "", "producer_state": pst,
            "package_contract": "the rooms' signed package import is not served by the producer's main at the pinned revision; what is kept here is what its main serves"}


def recover(op: dict) -> dict:
    """Bounded recovery for an investigation: the record first; then, if the
    start was delivered and answered and the artifact or receipt is
    missing, the artifact is READ again by its id (EthicalAlt: the receipt
    is asked for again too — a write on the producer, said so) — never the
    start again. Says what it sent."""
    st = status(op)
    ref = op.get("result_ref") or {}
    spec = (op.get("execution") or {}).get("spec") or {}
    if st["start"] == "ok" and spec and ref.get("object_id") and not st["verified"] and spec.get("kind") != "snapshot":
        res = retrieve(op["op_id"], spec, ref["object_id"])
        what = ["GET " + ADAPTERS[spec["producer"]]["artifact"]["path"].replace("{id}", ref["object_id"]) + " — a read" +
                (" the producer counts as a view" if spec["producer"] == "open_case" else "")]
        if spec["producer"] == "ethicalalt" and res.get("artifact"):
            what.append("POST " + ADAPTERS["ethicalalt"]["receipt"]["path"] + " — the receipt asked for again; the producer stores one it issues")
        return {"recovered": bool(res.get("ok")), "did": "retrieved the artifact again by its id" + (" and asked for the receipt again" if len(what) > 1 else ""),
                "sent": True, "what": what, "result": res, **status(op)}
    return {"recovered": False, "did": "read the record", "sent": False, "what": [], **st}


def verify(deposition_id: str) -> dict:
    """The federation core's package verifier, for a deposition in custody."""
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
