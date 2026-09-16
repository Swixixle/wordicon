"""A mock Open Case and a mock EthicalAlt on one loopback port, for the
browser journeys and the suite (block 107; slice F; the review of 6e5b59c,
finding 3).

Two kinds of route live here, and they are labelled apart:

1. FIXTURES OF THE PRODUCERS' CONTRACTS AT THE PINNED REVISIONS — what
   each producer's main actually serves, in the shapes its source builds
   (scripts/producers.py CONTRACTS names the file:line of each):
     EthicalAlt @1a71460:  GET /api/profiles/index · POST /api/investigate ·
                           GET /api/profiles/{slug}/export (unsigned) ·
                           POST /api/receipt/generate (signed: stableStringify +
                           Ed25519, under the test-only key beside the fixtures)
     Open Case @4dc1709:   GET /api/v1/cases · POST /api/v1/cases/{id}/investigate
                           (bearer; handle must match) · GET /api/v1/cases/{id}/report ·
                           POST /cases/{id}/snapshot (bearer; a mutation; signed_hash:
                           JCS → sha256 hex → Ed25519 under the test-only key)
   The EthicalAlt receipt is signed here with the SAME canonicalizer the
   adapter verifies with (scripts/producers.stable_stringify); that the
   canonicalizer is the producer's is proven separately, against bytes the
   producer's own function wrote under Node
   (tests/fixtures/producers/ethicalalt.stable-stringify.vectors.json and
   ethicalalt.receipt.node-signed.json).

2. COMPATIBILITY FIXTURES OF NIKODEMUS'S PACKAGE CONTRACT
   (nikodemus.deposition.v1: the golden depositions under
   tests/fixtures/federation) — GET /api/profiles/{id}/export/v2,
   GET /api/v1/cases/{id}/export, GET /api/v1/cases/exportable. At the pinned
   revisions NEITHER producer's main serves these; they exist on unpushed
   local branches (block107/export-v2, block107/export-contract). They stay
   here so the federation core's verifier and the rooms' import are
   exercised; they say nothing about a deployment.

Plus the failure shapes a real host produces — a redirect, an oversized
body, an HTML sign-in page, an HTML 502, invalid JSON, a 500, a slow answer,
a 404 — so a journey can show each class landing as a named failure and
never as "nothing found". Nothing here is a real producer, a real record,
or a real key.
"""
import base64
import hashlib
import http.server
import json
import os
import pathlib
import sys
import threading
import time
import uuid

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "federation"
PFIX = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "producers"
OC_KEY_ENV = "JOURNEY_OPEN_CASE_KEY"
OC_HANDLE = "exemplar"            # the investigator handle bound to the mock's key (auth.py:31 require_matching_handle)
MAX_BYTES = 8_000_000
sys.path.insert(0, str(pathlib.Path(__file__).resolve().parents[2] / "scripts"))

EA_INDEX = [
    {"brand_slug": "exemplar-holdings", "display_name": "Exemplar Holdings", "sector": "retail", "overall_concern_level": "significant",
     "generated_headline": "An invented company for fixtures", "has_deep_research": True},
    {"brand_slug": "exemplar-legacy-co", "display_name": "Exemplar Legacy Co", "sector": "retail", "overall_concern_level": "moderate",
     "generated_headline": None, "has_deep_research": False},
]
EA_EXPORT = {
    "schema_version": "1.0", "brand_slug": "exemplar-holdings", "brand_name": "Exemplar Holdings",
    "unique_incident_count": 2, "category_placement_count": 3, "generated_at": "2026-09-16T09:00:00.000Z",
    "incidents": [
        {"incident_key": "exemplar-holdings|labor-2025", "categories": ["labor"], "date": "2025-03-01", "source_url": "https://example.org/exemplar/labor-2025",
         "description": "An invented labor incident.", "confidence": "high"},
        {"incident_key": "exemplar-holdings|spill-2024", "categories": ["environment", "governance"], "date": "2024-11-12", "source_url": "https://example.org/exemplar/spill-2024",
         "description": "An invented spill.", "confidence": "medium"},
    ],
}
OC_REPORT_BASE = {"title": "Exemplar Case", "subject_name": "Exemplar Person", "status": "open", "evidence_count": 3, "signal_count": 1,
                  "sections": {"evidence": [{"title": "An invented filing", "source": "example.gov", "epistemic": "REPORTED"}], "signals": [{"pattern": "invented", "level": "low"}]}}


def _load():
    oc = (FIXTURES / "open_case.exemplar.deposition.json").read_bytes()
    ea = (FIXTURES / "ethicalalt.exemplar.deposition.json").read_bytes()
    lg = (FIXTURES / "ethicalalt.legacy.deposition.json").read_bytes()
    from cryptography.hazmat.primitives.serialization import load_der_private_key
    ea_key = load_der_private_key(base64.b64decode((PFIX / "ethicalalt.receipt.key.pkcs8.b64").read_text().strip()), password=None)
    oc_key = load_der_private_key(base64.b64decode((PFIX / "open_case.snapshot.key.pkcs8.b64").read_text().strip()), password=None)
    return {"oc": oc, "oc_id": json.loads(oc)["object"]["id"], "ea": ea, "ea_id": json.loads(ea)["object"]["id"], "lg": lg,
            "exportable": (FIXTURES / "open_case.exportable.json").read_bytes(),
            "ea_key": ea_key, "ea_pub_b64url": base64.urlsafe_b64encode(base64.b64decode((PFIX / "ethicalalt.receipt.pub.spki.b64").read_text().strip())).decode().rstrip("="),
            "oc_key": oc_key, "receipts": {}, "snapshots": 0}


def _ea_receipt(fx, slug, investigation_id):
    """routes/receipt.js:178-297 @1a71460: the body as buildReceiptPayloadFromProfileRow
    makes it; cached by slug + incidents_hash (the second request for the same
    slug returns the FIRST receipt, with its investigation_id, cached: true)."""
    import producers as _p
    incidents_hash = hashlib.sha256(json.dumps(sorted(EA_EXPORT["incidents"], key=lambda i: i["source_url"]), separators=(",", ":")).encode()).hexdigest()
    key = (slug, incidents_hash)
    if key in fx["receipts"]:
        prior = fx["receipts"][key]
        return {**prior, "cached": True}
    body = {
        "receipt_id": str(uuid.uuid4()),
        "subject": {"brand_name": "Exemplar Holdings", "brand_slug": slug, "ultimate_parent": "Exemplar Holdings"},
        "investigated_at": "2026-09-01T10:00:00.000Z", "generated_at": time.strftime("%Y-%m-%dT%H:%M:%S.000Z", time.gmtime()),
        "incident_count": 2, "category_summary": [{"category": "labor", "count": 1, "overflow": 0}, {"category": "environment", "count": 1, "overflow": 0}],
        "source_urls": sorted(i["source_url"] for i in EA_EXPORT["incidents"]), "source_count": 2, "incidents_hash": incidents_hash,
        "data_source": "deep_research+database", "last_deep_researched": "2026-09-01T10:00:00.000Z",
        "disclaimer": "This receipt documents public records and credible reporting. It is not a legal finding. Sources are linked directly and independently verifiable.",
        "methodology_url": "https://ethicalalt-client.onrender.com/methodology", "issuer": "EthicalAlt / Nikodemus Systems", "schema_version": "1.0",
        "overall_concern_level": "significant",
    }
    if investigation_id:
        body["investigation_id"] = investigation_id
    sig = fx["ea_key"].sign(_p.stable_stringify(body).encode("utf-8"))
    reply = {"receipt_id": body["receipt_id"], "signed_receipt": body, "signature": "ed25519:" + base64.urlsafe_b64encode(sig).decode().rstrip("="),
             "public_key": fx["ea_pub_b64url"], "verify_url": "https://ethicalalt-client.onrender.com/verify/" + body["receipt_id"], "cached": False}
    fx["receipts"][key] = reply
    return reply


def _oc_signed_hash(fx, payload):
    """signing.py:98-125,189 @4dc1709: JCS canonical → sha256 hex → Ed25519 over the hex's UTF-8 bytes, base64; packed with the payload."""
    import jcs
    digest = hashlib.sha256(jcs.canonicalize(payload)).hexdigest()
    sig = base64.b64encode(fx["oc_key"].sign(digest.encode("utf-8"))).decode()
    return json.dumps({"content_hash": digest, "signature": sig, "payload": payload}, separators=(",", ":"), sort_keys=True)


class Handler(http.server.BaseHTTPRequestHandler):
    fx = None
    seen = []

    def log_message(self, *a):  # noqa: D401
        pass

    def _send(self, code, body, ctype="application/json", extra=None):
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(body)))
        for k, v in (extra or {}).items():
            self.send_header(k, v)
        self.end_headers()
        self.wfile.write(body)

    def _j(self, code, obj):
        return self._send(code, json.dumps(obj).encode("utf-8"))

    def _bearer_ok(self):
        return self.headers.get("Authorization") == "Bearer " + os.environ.get(OC_KEY_ENV, "~")

    def do_GET(self):  # noqa: N802
        fx = self.fx
        Handler.seen.append({"path": self.path, "method": "GET", "headers": {k.lower(): v for k, v in self.headers.items()}, "at": time.time()})
        p = self.path.split("?")[0]
        # ---- Open Case @4dc1709: what main serves (GET routes are public) ----
        if p == "/api/v1/cases":
            return self._j(200, {"count": 1, "cases": [{"id": fx["oc_id"], "slug": "exemplar-case", "title": "Exemplar Case", "subject_name": "Exemplar Person",
                                                        "subject_type": "official", "jurisdiction": "example", "status": "open", "government_level": "federal",
                                                        "branch": "legislative", "pilot_cohort": None, "created_at": "2026-07-01T00:00:00"}]})
        if p == f"/api/v1/cases/{fx['oc_id']}/report":
            return self._j(200, {"case_id": fx["oc_id"], **OC_REPORT_BASE})
        if p.startswith("/api/v1/cases/") and p.endswith("/report"):
            return self._j(404, {"detail": "Case not found"})
        # ---- Open Case: COMPATIBILITY fixtures of the package contract (branch block107/export-contract only) ----
        if p.startswith("/api/v1/cases"):
            if not self._bearer_ok():
                return self._send(401, b'{"detail":"an investigator API key is required"}')
            if p == f"/api/v1/cases/{fx['oc_id']}/export":
                return self._send(200, fx["oc"], extra={"X-Nikodemus-Fixture": "compatibility: package contract, not served by main"})
            if p == "/api/v1/cases/exportable":
                return self._send(200, fx["exportable"], extra={"X-Nikodemus-Fixture": "compatibility: package contract, not served by main"})
            return self._send(404, b'{"detail":"case not found"}')
        # ---- EthicalAlt @1a71460: what main serves ----
        if p == "/api/profiles/index":
            return self._send(200, json.dumps(EA_INDEX).encode("utf-8"))
        if p == "/api/profiles/exemplar-holdings/export":
            return self._send(200, json.dumps(EA_EXPORT).encode("utf-8"), extra={"Cache-Control": "public, max-age=300"})
        if p == "/api/profiles/exemplar-legacy-co/export":
            return self._send(200, json.dumps({**EA_EXPORT, "brand_slug": "exemplar-legacy-co", "brand_name": "Exemplar Legacy Co", "unique_incident_count": 0,
                                               "category_placement_count": 0, "incidents": []}).encode("utf-8"))
        if p.endswith("/export") and p.startswith("/api/profiles/") and "/export/v2" not in p:
            return self._send(404, b'{"error":"Profile not found"}')
        # ---- EthicalAlt: COMPATIBILITY fixtures of the package contract (branch block107/export-v2 only) ----
        if p == f"/api/profiles/{fx['ea_id']}/export/v2":
            return self._send(200, fx["ea"], extra={"X-Nikodemus-Fixture": "compatibility: package contract, not served by main"})
        if p == "/api/profiles/exemplar-legacy-co/export/v2":
            return self._send(200, fx["lg"], extra={"X-Nikodemus-Fixture": "compatibility: package contract, not served by main"})
        # ---- the failure shapes a real host produces ----
        if p == "/api/profiles/redirect-me/export/v2":
            return self._send(302, b"", extra={"Location": "http://127.0.0.1:1/elsewhere"})
        if p == "/api/profiles/big-body/export/v2":
            return self._send(200, b'{"pad":"' + b"x" * (MAX_BYTES + 10) + b'"}')
        if p == "/api/profiles/html-page/export/v2":
            return self._send(200, b"<html><body>Sign in to continue</body></html>", ctype="text/html")
        if p == "/api/profiles/not-json/export/v2":
            return self._send(200, b"{not json", ctype="application/json")
        if p == "/api/profiles/gateway-502/export/v2":
            return self._send(502, b"<html><body>502 Bad Gateway</body></html>", ctype="text/html")
        if p == "/api/profiles/server-boom/export/v2":
            return self._send(500, b'{"error":"internal"}')
        if p == "/api/profiles/slow-slow/export/v2":
            time.sleep(20)
            return self._send(200, fx["ea"])
        return self._send(404, b'{"error":"profile not found"}')

    def do_POST(self):  # noqa: N802
        fx = self.fx
        n = int(self.headers.get("Content-Length") or 0)
        raw = self.rfile.read(n) if n else b""
        Handler.seen.append({"path": self.path, "method": "POST", "headers": {k.lower(): v for k, v in self.headers.items()}, "at": time.time(), "bytes": len(raw)})
        p = self.path.split("?")[0]
        try:
            body = json.loads(raw.decode("utf-8")) if raw else {}
        except (UnicodeDecodeError, json.JSONDecodeError):
            return self._send(400, b'{"error":"body must be JSON"}')
        # ---- EthicalAlt @1a71460: POST /api/investigate (tap.js:506) — synchronous; the reply's investigation carries brand_slug ----
        if p == "/api/investigate":
            brand = str(body.get("brand") or "").strip()
            if not brand:
                return self._j(400, {"error": "brand required"})
            low = brand.lower()
            if low == "boom industries":
                return self._j(500, {"error": "the orchestrator failed"})
            if low == "refused industries":
                return self._j(422, {"error": "brand not eligible"})
            if low == "html industries":
                return self._send(502, b"<html><body>502 Bad Gateway</body></html>", ctype="text/html")
            if low == "slow industries":
                time.sleep(20)
            if low == "nameless industries":
                inv = None
            else:
                slug = "exemplar-holdings" if "exemplar" in low else "not-a-profile"
                inv = {"brand": brand, "brand_slug": slug, "parent": None, "overall_concern_level": "significant", "investigation_provider": "fixture",
                       "profile_type": "database", "research_depth": "deep" if slug == "exemplar-holdings" else "legacy"}
            return self._j(200, {"identification": {"object": brand, "brand": brand, "corporate_parent": None, "category": "search", "confidence": 1,
                                                    "identification_method": "text_search", "search_keywords": brand},
                                 "identification_tier": "typed", "investigation": inv, "results": [], "registry_results": [], "local_results": [],
                                 "scene_inventory": None, "searched_sources": ["investigation"] if inv else [], "empty_sources": [], "version": "v1", "response_ms": 12})
        # ---- EthicalAlt: POST /api/receipt/generate (receipt.js:178) ----
        if p == "/api/receipt/generate":
            slug = str(body.get("slug") or "").strip().lower()
            if not slug:
                return self._j(400, {"ok": False, "error": "missing_slug"})
            if slug == "not-a-profile":
                return self._j(404, {"ok": False, "error": "profile_not_found"})
            if slug == "exemplar-legacy-co":
                return self._j(400, {"ok": False, "error": "no_deep_research"})
            if os.environ.get("MOCK_EA_NO_SIGNING_KEY"):
                return self._j(503, {"ok": False, "error": "signing_key_unconfigured"})
            inv_id = body.get("investigation_id") if isinstance(body.get("investigation_id"), str) else None
            return self._j(200, _ea_receipt(fx, slug, inv_id.strip() if inv_id else None))
        # ---- Open Case @4dc1709: POST /api/v1/cases/{id}/investigate (investigate.py:1976) — bearer; handle must match ----
        if p.startswith("/api/v1/cases/") and p.endswith("/investigate"):
            if not self._bearer_ok():
                return self._j(401, {"detail": "Invalid or revoked API key"})
            cid = p[len("/api/v1/cases/"):-len("/investigate")]
            if cid != fx["oc_id"]:
                return self._j(404, {"detail": "Case not found"})
            subject, handle = str(body.get("subject_name") or "").strip(), str(body.get("investigator_handle") or "").strip()
            if not subject or not handle:
                return self._j(422, {"detail": [{"loc": ["body", "subject_name" if not subject else "investigator_handle"], "msg": "field required", "type": "value_error.missing"}]})
            if handle != OC_HANDLE:
                return self._j(403, {"detail": "investigator_handle must match the authenticated API key holder"})
            if subject.lower() == "sources missing":
                return self._j(422, {"case_id": cid, "subject_searched": subject, "address_searched": None, "sources_checked": 2, "cache_hits": 0, "evidence_entries_created": 0,
                                     "signals_detected": 0, "signals_unresolved": 0, "errors": ["fec: unavailable"], "signals": [], "collision_warnings": [], "source_statuses": {},
                                     "required_sources_ready": [], "required_sources_missing": ["fec"]})
            return self._j(200, {"case_id": cid, "subject_searched": subject, "address_searched": None, "sources_checked": 4, "cache_hits": 1, "evidence_entries_created": 3,
                                 "signals_detected": 1, "signals_unresolved": 0, "anticipatory_signals": 0, "retrospective_signals": 1, "required_sources_ready": ["fec", "votes"],
                                 "required_sources_missing": [], "errors": [], "signals": [{"pattern": "invented", "level": "low"}], "collision_warnings": [],
                                 "source_statuses": {"fec": "ok", "votes": "ok", "lobbying": "empty", "contracts": "ok"}})
        # ---- Open Case: POST /cases/{id}/snapshot (snapshots.py:28) — bearer; a MUTATION; signed_hash ----
        if p.startswith("/cases/") and p.endswith("/snapshot"):
            if not self._bearer_ok():
                return self._j(401, {"detail": "Invalid or revoked API key"})
            cid = p[len("/cases/"):-len("/snapshot")]
            if cid != fx["oc_id"]:
                return self._j(404, {"detail": "case not found"})
            taken_by = str(body.get("taken_by") or "").strip()
            if taken_by != OC_HANDLE:
                return self._j(403, {"detail": "investigator_handle must match the authenticated API key holder"})
            fx["snapshots"] += 1
            payload = {"case": {"id": cid, "title": "Exemplar Case", "subject_name": "Exemplar Person"}, "entries": [{"title": "An invented filing"}], "pattern_alerts": [], "case_signals": [],
                       "snapshot": {"snapshot_number": fx["snapshots"], "taken_at": time.strftime("%Y-%m-%dT%H:%M:%S+00:00", time.gmtime()), "taken_by": taken_by,
                                    "entry_count": 1, "label": str(body.get("label") or "")}}
            packed = "" if os.environ.get("MOCK_OC_NO_SIGNING_KEY") else _oc_signed_hash(fx, payload)
            if os.environ.get("MOCK_OC_NO_SIGNING_KEY"):
                import jcs
                packed = json.dumps({"content_hash": hashlib.sha256(jcs.canonicalize(payload)).hexdigest(), "signature": "", "payload": payload}, separators=(",", ":"), sort_keys=True)
            sid = str(uuid.uuid4())
            return self._j(200, {"snapshot": {"id": sid, "case_file_id": cid, "snapshot_number": fx["snapshots"], "taken_at": payload["snapshot"]["taken_at"], "taken_by": taken_by,
                                              "entry_count": 1, "signed_hash": packed, "share_url": f"/cases/{cid}/snapshots/{sid}", "label": payload["snapshot"]["label"]},
                                 "signature_check": {"valid": True}, "case": {"id": cid, "title": "Exemplar Case"}})
        return self._send(404, b'{"error":"no such route"}')


def start(port=0):
    """Start the mock on 127.0.0.1:<port> (0 = any free port) in a daemon
    thread; returns (server, port)."""
    Handler.fx = _load()
    srv = http.server.ThreadingHTTPServer(("127.0.0.1", port), Handler)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.server_address[1]


if __name__ == "__main__":
    s, p = start(int(os.environ.get("PRODUCER_PORT", "0")))
    print(f"mock producers on http://127.0.0.1:{p}", flush=True)
    try:
        while True:
            time.sleep(3600)
    except KeyboardInterrupt:
        pass
