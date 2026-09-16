#!/usr/bin/env python3
"""The bounded sabotage pass (instructions §11): each mutation must fail its
named assertion for the intended reason, then be restored. Runs one suite
check function per mutation in a fresh subprocess on a scratch root; the
mutated file is written back exactly as it was, whether or not the check
ran. Usage: python3 tests/slice_g/sabotage.py <report.json> [--only=<substring>...]
Run it on a clean tree, from the repository root."""
import json
import os
import pathlib
import subprocess
import sys
import textwrap

REPO = pathlib.Path(__file__).resolve().parents[2]

RUNNER = textwrap.dedent('''
    import os, sys, json
    os.environ["WORDICON_TEST_MODE"] = "1"
    # the suite module sets its own scratch root and test mode before its first
    # application import, and imports the server itself; use it as it is
    sys.path.insert(0, "tests"); sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
    import test_global_constraints as T
    import server, gate as _gate
    def _paired(c):
        c.set_cookie(_gate.SESSION_COOKIE, _gate.issue_session("suite")["token"]); return c
    fn = getattr(T, sys.argv[1])
    try:
        out = fn(server, _paired) if fn.__code__.co_argcount == 2 else (fn(server) if fn.__code__.co_argcount == 1 else fn())
    except Exception as e:
        # the assertions the check had already recorded before it crashed are
        # in its frame's local list; a crash after a recorded failure is that
        # failure plus the crash, not the crash alone
        partial, tb = None, e.__traceback__
        while tb is not None:
            if tb.tb_frame.f_code.co_name == sys.argv[1] and isinstance(tb.tb_frame.f_locals.get("out"), list):
                partial = list(tb.tb_frame.f_locals["out"])
            tb = tb.tb_next
        out = (partial or []) + ["CRASH " + type(e).__name__ + ": " + str(e)[:300]]
    print("SABOTAGE_RESULT " + json.dumps([str(o) for o in out]))
''')

MUTATIONS = [
    {"name": "omit the structure from the fingerprint", "file": "scripts/notebook.py",
     "old": "    fp = ds.fingerprint_v2(title, title_is_manual, body, json.loads(doc_text), sch, proj) if doc_text is not None \\\n        else fingerprint(title, title_is_manual, body)",
     "new": "    fp = fingerprint(title, title_is_manual, body)",
     "check": "_check_document_contract", "expect": "formatting only"},
    {"name": "flatten a structured head on a body-only save (the old escape hatch)", "file": "scripts/notebook.py",
     "old": "                if doc_text is None and head[\"doc_json\"]:\n                    raise NotebookError(",
     "new": "                if False and doc_text is None and head[\"doc_json\"]:\n                    raise NotebookError(",
     "check": "_check_document_contract", "expect": "body-only"},
    {"name": "let a request key answer for a different request", "file": "scripts/operations.py",
     "old": "                if prior[\"fingerprint\"] != fp:\n                    raise OperationsError(",
     "new": "                if False and prior[\"fingerprint\"] != fp:\n                    raise OperationsError(",
     "check": "_check_durable_operations", "expect": "changed request under the same key"},
    {"name": "dispatch without the store's claim", "file": "server.py",
     "old": "    if not ops.claim(job_id, OPS_DISPATCHER.token):\n        row = ops.get(job_id) or {}",
     "new": "    if False and not ops.claim(job_id, OPS_DISPATCHER.token):\n        row = ops.get(job_id) or {}",
     "check": "_check_durable_operations", "expect": "reserved, claimed"},
    {"name": "replay a dispatch whose outcome is unknown", "file": "scripts/operations.py",
     "old": "            if a[\"case\"] == \"never_dispatched\":",
     "new": "            if a[\"case\"] in (\"never_dispatched\", \"delivery_unknown\"):",
     "check": "_check_durable_operations", "expect": "delivery_unknown"},
    {"name": "send an attempt before its intent is persisted", "file": "scripts/wordicon_cli.py",
     "old": "                hook(\"attempt_intent\", stage=stage, attempt=attempt, started_at=started_at)\n            try:\n                response = make_call()",
     "new": "                pass\n            try:\n                response = make_call()",
     "check": "_check_durable_operations", "expect": "intent"},
    {"name": "stop draining the notebook's outbox", "file": "scripts/workindex.py",
     "old": "            pending = src.execute(\"SELECT seq, doc_id FROM index_outbox WHERE done = 0 ORDER BY seq ASC LIMIT 500\").fetchall()",
     "new": "            pending = []",
     "check": "_check_work_index", "expect": "outbox"},
    {"name": "link a run to a document by its text", "file": "scripts/workindex.py",
     "old": "                               open_={\"place\": \"/?trace=\" + trace}))\n    for name in set(known) - set(seen):\n        deletes.append(item_id(\"results\", \"run\", name[:-5]))",
     "new": "                               open_={\"place\": \"/?trace=\" + trace}, related=[item_id(\"notebook\", \"writing\", \"doc_twin_a\")]))\n    for name in set(known) - set(seen):\n        deletes.append(item_id(\"results\", \"run\", name[:-5]))",
     "check": "_check_work_index", "expect": "similarity"},
    {"name": "enable a live start without the owner's ruling", "file": "scripts/producers.py",
     "old": "    elif ruling.get(\"enabled\"):\n        out[\"start_available\"] = out[\"available\"] = True",
     "new": "    elif True:\n        out[\"start_available\"] = out[\"available\"] = True",
     "check": "_check_investigation_adapters", "expect": "verification ruling"},
    {"name": "follow the request off the connector's origin", "file": "scripts/producers.py",
     "old": "    if federation._origin_of(url) != connector.get(\"origin\"):\n        return {\"ok\": False, \"outcome\": \"origin_refused\", \"detail\": \"the request would leave the connector's origin\"}\n    headers = {\"Accept\": \"application/json\", \"Content-Type\"",
     "new": "    headers = {\"Accept\": \"application/json\", \"Content-Type\"",
     "check": "_check_investigation_adapters", "expect": "origin comparison"},
    {"name": "let a test process answer the real provider", "file": "server.py",
     "old": "    if testmode.active():\n        return cli.make_gateway(\"mock\", None)\n    if os.environ.get(\"ANTHROPIC_API_KEY\"):",
     "new": "    if os.environ.get(\"ANTHROPIC_API_KEY\"):",
     "check": "_check_test_mode_fails_closed", "expect": "answered 'anthropic'"},
    {"name": "leak the definition and passage into Check sources", "file": "server.py",
     "old": "    for bad in (\"trace_id\", \"passage\", \"definition\", \"meaning\", \"item\", \"section\", \"index\"):\n        if bad in data:\n",
     "new": "    for bad in (\"trace_id\", \"passage\", \"definition\", \"meaning\", \"item\", \"section\", \"index\"):\n        if False and bad in data:\n",
     "check": "_check_word_sources_evidence", "expect": "the route accepted"},
    {"name": "reserve a request key without the store's immediate lock (two callers can both find no prior row)", "file": "scripts/operations.py",
     "old": "        conn.execute(\"BEGIN IMMEDIATE\")\n        try:\n            prior = conn.execute(\"SELECT * FROM operations WHERE request_key = ?\", (request_key,)).fetchone()",
     "new": "        conn.execute(\"BEGIN\")\n        try:\n            prior = conn.execute(\"SELECT * FROM operations WHERE request_key = ?\", (request_key,)).fetchone()",
     "check": "_check_dispatch_concurrency", "expect": "G-dispatch"},
    {"name": "hand the vault a plain copy of an active database", "file": "scripts/vault.py",
     "old": "            api_copied = _sqlite_consistent_copies(root, snap)",
     "new": "            api_copied = []",
     "check": "_check_vault_sqlite", "expect": "journal sibling rode the vault"},
]

# the browser-side mutations (recovery, the application guard) are proven by the editor journey; they run separately (sabotage_browser.sh)


def run_check(name):
    p = subprocess.run([sys.executable, "-c", RUNNER, name], cwd=str(REPO), capture_output=True, text=True, timeout=600,
                       env={**os.environ, "WORDICON_TEST_MODE": "1"})
    for line in p.stdout.splitlines():
        if line.startswith("SABOTAGE_RESULT "):
            return json.loads(line[len("SABOTAGE_RESULT "):])
    return ["RUNNER DID NOT REPORT: " + p.stderr[-500:]]


def main():
    report = []
    only = [a[len("--only="):] for a in sys.argv[2:] if a.startswith("--only=")]
    for m in MUTATIONS:
        if only and not any(o.lower() in m["name"].lower() for o in only):
            continue
        path = REPO / m["file"]
        src = path.read_text(encoding="utf-8")
        if m["old"] not in src:
            report.append({"mutation": m["name"], "applied": False, "why": "the anchor text was not found — the mutation could not be applied"})
            continue
        path.write_text(src.replace(m["old"], m["new"], 1), encoding="utf-8")
        try:
            out = run_check(m["check"])
        finally:
            path.write_text(src, encoding="utf-8")   # the file as it was before the mutation, uncommitted work included
        hit = [o for o in out if m["expect"].lower() in o.lower()]
        report.append({"mutation": m["name"], "file": m["file"], "check": m["check"], "applied": True, "caught": bool(hit),
                       "assertion": (hit[0] if hit else (out[0] if out else "(the check passed — NOT caught)"))[:300], "failures": len(out)})
        print(("caught  " if hit else "MISSED  ") + m["name"] + " → " + (hit[0][:140] if hit else (out[0][:140] if out else "no failure")), flush=True)
    clean = subprocess.run(["git", "status", "--short"], cwd=str(REPO), capture_output=True, text=True).stdout
    report.append({"restored": clean.strip() == "" or all(l.startswith("??") for l in clean.splitlines()), "git_status": clean.strip()})
    pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "sabotage-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report[-1]))


if __name__ == "__main__":
    main()
