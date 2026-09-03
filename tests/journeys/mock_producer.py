"""A mock Open Case and a mock EthicalAlt on one loopback port, for the
browser journeys (block 107). It serves the golden fixtures under their
contract paths and the failure shapes a real host produces — a redirect,
an oversized body, an HTML sign-in page, an HTML 502, invalid JSON, a
500, a slow answer, a 404 — so the journey can show each class landing
as a named failure and never as "nothing found". The Open Case routes
require the bearer credential the scratch environment carries; nothing
here is a real producer, a real record, or a real key."""
import http.server
import json
import os
import pathlib
import threading
import time

FIXTURES = pathlib.Path(__file__).resolve().parent.parent / "fixtures" / "federation"
OC_KEY_ENV = "JOURNEY_OPEN_CASE_KEY"
MAX_BYTES = 8_000_000


def _load():
    oc = (FIXTURES / "open_case.exemplar.deposition.json").read_bytes()
    ea = (FIXTURES / "ethicalalt.exemplar.deposition.json").read_bytes()
    lg = (FIXTURES / "ethicalalt.legacy.deposition.json").read_bytes()
    return {"oc": oc, "oc_id": json.loads(oc)["object"]["id"], "ea": ea, "ea_id": json.loads(ea)["object"]["id"], "lg": lg,
            "exportable": (FIXTURES / "open_case.exportable.json").read_bytes()}


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

    def do_GET(self):  # noqa: N802
        fx = self.fx
        Handler.seen.append({"path": self.path, "headers": {k.lower(): v for k, v in self.headers.items()}, "at": time.time()})
        p = self.path.split("?")[0]
        if p.startswith("/api/v1/cases"):
            if self.headers.get("Authorization") != "Bearer " + os.environ.get(OC_KEY_ENV, "~"):
                return self._send(401, b'{"detail":"an investigator API key is required"}')
            if p == f"/api/v1/cases/{fx['oc_id']}/export":
                return self._send(200, fx["oc"])
            if p == "/api/v1/cases/exportable":
                return self._send(200, fx["exportable"])
            return self._send(404, b'{"detail":"case not found"}')
        if p == f"/api/profiles/{fx['ea_id']}/export/v2":
            return self._send(200, fx["ea"])
        if p == "/api/profiles/exemplar-legacy-co/export/v2":
            return self._send(200, fx["lg"])
        if p == "/api/profiles/index":
            return self._send(200, b'{"items":[{"slug":"exemplar-holdings","brand_name":"Exemplar Holdings"},{"slug":"exemplar-legacy-co","brand_name":"Exemplar Legacy Co"}]}')
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
