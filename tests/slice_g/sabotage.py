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
     "old": "    elif out[\"deployment_verified\"]:\n        out[\"start_available\"] = out[\"available\"] = True",
     "new": "    elif True:\n        out[\"start_available\"] = out[\"available\"] = True",
     "check": "_check_investigation_adapters", "expect": "without a ruling must not be startable"},
    {"name": "honour a ruling recorded against another revision", "file": "scripts/producers.py",
     "old": "    out[\"deployment_verified\"] = bool(ruling.get(\"enabled\")) and (not ruling.get(\"revision\") or ruling.get(\"revision\") == ct.get(\"revision\"))",
     "new": "    out[\"deployment_verified\"] = bool(ruling.get(\"enabled\"))",
     "check": "_check_investigation_adapters", "expect": "recorded against another revision"},
    {"name": "follow the request off the connector's origin", "file": "scripts/producers.py",
     "old": "    if federation._origin_of(url) != connector.get(\"origin\"):\n        return {\"ok\": False, \"outcome\": \"origin_refused\", \"delivery\": \"not_sent\", \"detail\": \"the request would leave the connector's origin\"}\n    headers = {\"Accept\": \"application/json\", \"User-Agent\": \"Nikodemus-connector/2\"}",
     "new": "    headers = {\"Accept\": \"application/json\", \"User-Agent\": \"Nikodemus-connector/2\"}",
     "check": "_check_investigation_adapters", "expect": "origin comparison"},
    {"name": "call a 5xx after delivery a refusal (the work was never accepted)", "file": "scripts/producers.py",
     "old": "    if o in (\"unauthorized\", \"not_found\", \"refused\"):\n        return \"refused\", \"delivered\", f\"delivered, and the producer refused it ({r.get('detail', '')})\"",
     "new": "    if o in (\"unauthorized\", \"not_found\", \"refused\", \"producer_error\", \"invalid_json\", \"oversized\", \"redirect_refused\"):\n        return \"refused\", \"delivered\", f\"delivered, and the producer refused it ({r.get('detail', '')})\"",
     "check": "_check_investigation_adapters", "expect": "500 after delivery must leave the outcome UNKNOWN"},
    {"name": "trust the public key the receipt reply carries", "file": "scripts/producers.py",
     "old": "    pinned = _pinned_raw_keys(connector)\n    if not pinned:\n        out[\"why\"] = \"unverified: no key is pinned on this connector — pin the producer's receipt public key out of band, never from a reply\"\n        return out",
     "new": "    pinned = _pinned_raw_keys(connector)\n    if reply.get(\"public_key\"):\n        pinned = [{\"key_id\": \"reply\", \"raw\": federation._raw_public_key(str(reply.get(\"public_key\")))}]\n    if not pinned:\n        out[\"why\"] = \"unverified: no key is pinned on this connector — pin the producer's receipt public key out of band, never from a reply\"\n        return out",
     "check": "_check_producer_contracts", "expect": "no pinned key"},
    {"name": "verify the receipt over Python's json.dumps instead of the producer's stableStringify", "file": "scripts/producers.py",
     "old": "        message = stable_stringify(body).encode(\"utf-8\", \"surrogatepass\")",
     "new": "        message = json.dumps(body, sort_keys=True, separators=(\",\", \":\"), ensure_ascii=False).encode(\"utf-8\", \"surrogatepass\")",
     "check": "_check_producer_contracts", "expect": "the canonicalizer is not the producer's"},
    {"name": "skip the content hash of an Open Case snapshot", "file": "scripts/producers.py",
     "old": "    if digest != str(obj.get(\"content_hash\")):\n        out[\"why\"] = \"content_hash does not match the canonical payload (the bytes changed, or the hash was forged)\"\n        return out",
     "new": "    if False:\n        out[\"why\"] = \"content_hash does not match the canonical payload (the bytes changed, or the hash was forged)\"\n        return out",
     "check": "_check_producer_contracts", "expect": "tampered snapshot payload"},
    {"name": "recover an investigation without saying it read the producer", "file": "server.py",
     "old": "                        \"sent\": bool(did.get(\"sent\")), \"what\": did.get(\"what\") or [], \"note\": did.get(\"did\")})",
     "new": "                        \"sent\": False, \"what\": [], \"note\": did.get(\"did\")})",
     "check": "_check_investigation_adapters", "expect": "must say sent: true"},
    {"name": "keep the export but drop the receipt's bytes", "file": "scripts/producers.py",
     "old": "        rk = keep_artifact(op_id, \"receipt.json\", rr[\"raw\"])",
     "new": "        rk = {\"name\": \"receipt.json\", \"bytes\": 0, \"sha256\": \"\"}",
     "check": "_check_investigation_adapters", "expect": "not all kept"},
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
    {"name": "seal a vault from a preview process", "file": "scripts/vault.py",
     "old": "        _LAST_FAILURE[\"msg\"] = \"\"\n        return \"\"",
     "new": "        _LAST_FAILURE[\"msg\"] = \"\"",
     "check": "_check_preview_isolation", "expect": "a preview sealed a vault"},
    {"name": "prune from a preview process", "file": "scripts/vault.py",
     "old": "    if preview_mode():\n        return []           # a preview never touches the destination its copied configuration names",
     "new": "    if False:\n        return []           # a preview never touches the destination its copied configuration names",
     "check": "_check_preview_isolation", "expect": "a preview pruned"},
    {"name": "copy the vault configuration into a preview root", "file": "scripts/preview.py",
     "old": "EXCLUDE_DIRS = {\"vault\", \"auth\"}",
     "new": "EXCLUDE_DIRS = {\"auth\"}",
     "check": "_check_preview_isolation", "expect": "copied vault into the preview root"},
    {"name": "reuse a preview root name", "file": "scripts/preview.py",
     "old": "        d = root_dir / (f\"preview-{stamp}\" if n == 1 else f\"preview-{stamp}-{n}\")\n        try:\n            d.mkdir(exist_ok=False)          # exclusive: two runs cannot take one name\n        except FileExistsError:\n            continue",
     "new": "        d = root_dir / f\"preview-{stamp}\"\n        d.mkdir(exist_ok=True)",
     "check": "_check_preview_isolation", "expect": "same-second allocations are not distinct"},
    {"name": "accept a repeated request id under a different checkpoint reason", "file": "scripts/notebook.py",
     "old": "                if prior[\"request_fp\"] is not None and prior[\"request_fp\"] != rq:",
     "new": "                if False:",
     "check": "_check_notebook_b", "expect": "different checkpoint reason was accepted"},
    {"name": "mint the gate's master secret check-then-write", "file": "scripts/gate.py",
     "old": "    if not p.exists():\n        _write_secret(p, secrets.token_bytes(32), exclusive=True)",
     "new": "    if not p.exists():\n        p.parent.mkdir(parents=True, exist_ok=True); p.write_bytes(secrets.token_bytes(32)); os.chmod(p, 0o600)",
     "check": "_check_gate_mint_race", "expect": "master secrets were minted"},
    {"name": "resume inherited queued work at a preview's startup (the review of 0f2db31, finding 2)", "file": "server.py",
     "old": "    if vault.preview_mode():\n        # the review of 0f2db31, finding 2",
     "new": "    if False:\n        # the review of 0f2db31, finding 2",
     "check": "_check_preview_inheritance", "expect": "a preview dispatched or altered an inherited queued job"},
    {"name": "release the source lease before the copy instead of holding it throughout", "file": "scripts/preview.py",
     "old": "    return fd, \"\"\n\n\nclass PreviewRefused",
     "new": "    fcntl.flock(fd, fcntl.LOCK_UN); os.close(fd)\n    return None, \"\"\n\n\nclass PreviewRefused",
     "check": "_check_preview_inheritance", "expect": "not held for the whole copy"},
    {"name": "call an interrupted request 'not sent' (the review of 0f2db31, 3a)", "file": "scripts/producers.py",
     "old": "    if last_start is None and open_intent is not None:\n        delivery, start_word = \"unknown\", \"no answer recorded (interrupted after the request left)\"\n    else:",
     "new": "    if False:\n        delivery, start_word = \"unknown\", \"no answer recorded (interrupted after the request left)\"\n    else:",
     "check": "_check_investigation_correlation", "expect": "never 'not sent'"},
    {"name": "follow the case id the producer's reply names (the review of 0f2db31, 3b)", "file": "scripts/producers.py",
     "old": "        got = str(reply.get(\"case_id\") or \"\")\n        if got.lower() != str(spec.get(\"case_id\") or \"\").lower():",
     "new": "        got = str(reply.get(\"case_id\") or \"\")\n        if False:",
     "check": "_check_investigation_correlation", "expect": "followed as if it were the requested case"},
    {"name": "accept a correctly signed snapshot of another record as the requested one", "file": "scripts/producers.py",
     "old": "        ver[\"correlation\"] = _oc_snapshot_correlation(packed, spec)",
     "new": "        ver[\"correlation\"] = {\"matches_request\": True, \"why\": \"\"}",
     "check": "_check_investigation_correlation", "expect": "must verify AND be named as not the requested record"},
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
