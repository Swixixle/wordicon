#!/usr/bin/env python3
"""Migration / backup / restore / rollback rehearsal on DISPOSABLE data
(instructions §3.5 and §12.5). Nothing here touches the owner's store: the
"live" corpus is a copy of SEED_STATE (a scratch server's fixture state, or
a copy the owner makes of his own store for his own rehearsal).
Usage: SEED_STATE=<state root> python3 tests/slice_g/rehearse.py

  1. live:      a v2 store (notebook schema 2 with structured documents,
                operations.sqlite3, results, the derived index)
  2. backup:    vault init + backup — the SQLite stores through SQLite's own
                backup API inside the drained window; counts, no text
  3. restore:   into a fresh root; per-file digests verified by the vault
                itself; integrity_check; the new code's startup reconciliation;
                the derived index rebuilt from the record and compared
  4. rollback:  the OLD code (17894e3, a git worktree) run against a copy of
                the v2 store — reads every document; edits a plain one; is
                refused, by the store's own triggers, when it would flatten a
                structured head or checkpoint it without its structure
  5. forward:   the new code opens the rolled-back store again: everything
                intact, the plain edit kept, the structured heads whole

Every step runs in its own process so each one resolves its own state root.
"""
import json
import os
import pathlib
import shutil
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[2]
SEED = pathlib.Path(os.environ["SEED_STATE"])          # a DISPOSABLE v2 state root to rehearse on (never the owner's store)
OUT = pathlib.Path(os.environ.get("REHEARSAL_OUT", "/tmp/nikodemus-rehearsal"))
R = OUT / ("rehearsal-" + time.strftime("%Y%m%dT%H%M%S"))
R.mkdir(parents=True)
LOG = []


def say(*a):
    line = " ".join(str(x) for x in a)
    LOG.append(line)
    print(line, flush=True)


def run_py(code, cwd, env_extra=None, timeout=600):
    env = {k: v for k, v in os.environ.items() if k != "ANTHROPIC_API_KEY"}
    env["WORDICON_TEST_MODE"] = "1"
    env.update(env_extra or {})
    p = subprocess.run([sys.executable, "-c", code], cwd=str(cwd), capture_output=True, text=True, timeout=timeout, env=env)
    out = next((l for l in p.stdout.splitlines() if l.startswith("RESULT ")), "")
    if not out:
        return {"error": "no RESULT line", "stdout": p.stdout[-800:], "stderr": p.stderr[-1500:]}
    return json.loads(out[len("RESULT "):])


COUNTS = r'''
import json, sqlite3, os, hashlib
from pathlib import Path
root = Path(os.environ["WORDICON_STATE"])
def q(db, sql):
    c = sqlite3.connect(f"file:{db}?mode=ro", uri=True)
    try: return c.execute(sql).fetchall()
    finally: c.close()
nb = root / "notebook.sqlite3"; ops = root / "operations.sqlite3"
out = {"root": str(root)}
out["integrity_notebook"] = q(nb, "PRAGMA integrity_check")[0][0]
out["integrity_operations"] = q(ops, "PRAGMA integrity_check")[0][0]
out["notebook_schema"] = q(nb, "SELECT value FROM meta WHERE key='schema'")[0][0]
out["documents"] = q(nb, "SELECT COUNT(*) FROM documents")[0][0]
out["documents_structured"] = q(nb, "SELECT COUNT(*) FROM documents WHERE doc_json IS NOT NULL")[0][0]
out["checkpoints"] = q(nb, "SELECT COUNT(*) FROM checkpoints")[0][0]
out["document_events"] = q(nb, "SELECT COUNT(*) FROM document_events")[0][0]
out["operations"] = q(ops, "SELECT COUNT(*) FROM operations")[0][0]
out["operation_events"] = q(ops, "SELECT COUNT(*) FROM operation_events")[0][0]
out["results_files"] = len(list((root / "results").glob("*.json"))) if (root / "results").exists() else 0
# a digest over the documents' identities, revisions and fingerprints — never the text
rows = q(nb, "SELECT doc_id, revision, fingerprint, doc_json IS NOT NULL FROM documents ORDER BY doc_id")
out["documents_digest"] = hashlib.sha256(json.dumps([list(r) for r in rows]).encode()).hexdigest()[:16]
orows = q(ops, "SELECT op_id, status, request_key FROM operations ORDER BY op_id")
out["operations_digest"] = hashlib.sha256(json.dumps([list(r) for r in orows]).encode()).hexdigest()[:16]
print("RESULT " + json.dumps(out))
'''


def counts(root):
    return run_py(COUNTS, REPO, {"WORDICON_STATE": str(root)})


def main():
    # ---- 1. the live corpus (a copy of the dev scratch state) ----
    src = SEED
    live = R / "live"
    shutil.copytree(src, live, ignore=shutil.ignore_patterns("operations.lock", "*.lock"))
    for stale in ("vault",):
        shutil.rmtree(live / stale, ignore_errors=True)
    # a plain document beside the structured ones (the seed's documents were all
    # written by the structured editor): the old code must still be able to edit one
    seed_plain = run_py(r'''
import json, os
from pathlib import Path
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import testmode, state_root
root = Path(os.environ["WORDICON_STATE"]); state_root.apply(root)
import notebook as nb
a = nb.save("doc_rehearsal_plain", title="", title_is_manual=False, body="A plain document, kept plain.\n\nTwo paragraphs.", base_revision=0, base_fingerprint="", request_id="req_rehearsal_plain_0")
print("RESULT " + json.dumps({"doc": a["doc_id"], "revision": a["revision"], "rich": a["rich"]}))
''', REPO, {"WORDICON_STATE": str(live)})
    say("   a plain document added to the seed:", json.dumps(seed_plain))
    before = counts(live)
    say("1. live store:", json.dumps(before))
    if before.get("documents_structured", 0) < 1:
        say("   (no structured document in the seed — the rollback refusal would prove nothing; aborting)")
        return

    # ---- 2. backup ----
    backup_code = r'''
import json, os
from pathlib import Path
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import testmode, state_root
root = Path(os.environ["WORDICON_STATE"]); state_root.apply(root)
import vault
got = vault.init_vault(dest=os.environ["VAULT_DEST"])
Path(os.environ["IDENTITY_FILE"]).write_text(got["identity"])      # disposable rehearsal identity, kept only under the rehearsal directory
name = vault.backup(reason="rehearsal")
if not name:
    print("RESULT " + json.dumps({"error": vault._LAST_FAILURE["msg"]})); raise SystemExit
side = json.loads((Path(os.environ["VAULT_DEST"]) / (name + ".json")).read_text())
rows = [r for r in vault._log_rows() if r.get("type") == "sealed"]
print("RESULT " + json.dumps({"name": name, "bytes": side["bytes"], "n_files": side["n_files"], "payload_verified_locally": side["payload_verified_locally"], "semantic": rows[-1]["semantic"] if rows else None}))
'''
    dest = R / "vaults"
    b = run_py(backup_code, REPO, {"WORDICON_STATE": str(live), "VAULT_DEST": str(dest), "IDENTITY_FILE": str(R / "identity.txt")})
    say("2. backup:", json.dumps(b))
    if "error" in b:
        return
    # the manifest, read back from the sealed blob through restore below

    # ---- 3. restore into a fresh root; verify; reconcile; rebuild the index ----
    restore_code = r'''
import json, os
from pathlib import Path
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import testmode, state_root
root = Path(os.environ["WORDICON_STATE"]); state_root.apply(root)
import vault
man = vault.restore(os.environ["BLOB"], os.environ["OUT"], Path(os.environ["IDENTITY_FILE"]).read_text())
print("RESULT " + json.dumps({"files": len(man["files"]), "sqlite_backup_api": man.get("sqlite_backup_api"), "semantic": man.get("semantic"), "exclusions": man.get("exclusions"), "app_commit": man.get("app_commit")}))
'''
    restored = R / "restored"
    rs = run_py(restore_code, REPO, {"WORDICON_STATE": str(live), "BLOB": str(dest / b["name"]), "OUT": str(restored), "IDENTITY_FILE": str(R / "identity.txt")})
    say("3. restore:", json.dumps(rs))
    rroot = restored / "local_state"
    after = counts(rroot)
    say("   restored store:", json.dumps(after))
    same = all(before.get(k) == after.get(k) for k in ("documents", "documents_structured", "checkpoints", "document_events", "operations", "operation_events", "results_files", "documents_digest", "operations_digest", "notebook_schema"))
    say("   counts and digests equal to the live store:", same, "· integrity:", after.get("integrity_notebook"), after.get("integrity_operations"))
    startup_code = r'''
import json, os
from pathlib import Path
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import testmode, state_root
root = Path(os.environ["WORDICON_STATE"]); state_root.apply(root)
import server, workindex, operations as ops
rep = server.ops_startup_report()
live_items = int(os.environ["LIVE_ITEMS"])
rb = workindex.rebuild()
h = workindex.health()
print("RESULT " + json.dumps({"startup": rep, "index_rebuilt_items": rb.get("items"), "index_failed": rb.get("failed"), "index_health_population": h.get("population"), "counts": ops.counts()}))
'''
    live_index = run_py(r'''
import json, os
from pathlib import Path
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import testmode, state_root
root = Path(os.environ["WORDICON_STATE"]); state_root.apply(root)
import workindex
rb = workindex.rebuild()
print("RESULT " + json.dumps({"items": rb.get("items"), "failed": rb.get("failed")}))
''', REPO, {"WORDICON_STATE": str(live)})
    say("   live index (rebuilt for comparison):", json.dumps(live_index))
    st = run_py(startup_code, REPO, {"WORDICON_STATE": str(rroot), "LIVE_ITEMS": str(live_index.get("items", -1))})
    say("   new code on the restored store — startup reconciliation and index rebuild:", json.dumps(st))
    say("   the restored index holds the same number of items as the live one:", st.get("index_rebuilt_items") == live_index.get("items"))

    # ---- 4. rollback: the OLD code against a copy of the v2 store ----
    old = R / "old"
    subprocess.run(["git", "worktree", "add", "--detach", str(old), "17894e3"], cwd=str(REPO), check=True, capture_output=True)
    shutil.copytree(live, old / "local_state", ignore=shutil.ignore_patterns("*.lock", "vault"))
    rollback_code = r'''
import json, sqlite3
from pathlib import Path
import sys; sys.path.insert(0, "scripts"); sys.path.insert(0, ".")
import wordicon_cli as cli
import notebook as nb
out = {"code": "17894e3", "store": str(nb.db_path())}
docs = nb.list_documents(limit=200)["documents"]
out["documents_listed"] = len(docs)
out["all_readable"] = all(nb.get(d["doc_id"]) is not None for d in docs)
conn = sqlite3.connect(str(nb.db_path())); conn.row_factory = sqlite3.Row
rich = conn.execute("SELECT doc_id, revision, fingerprint, body FROM documents WHERE doc_json IS NOT NULL ORDER BY doc_id LIMIT 1").fetchone()
plain = conn.execute("SELECT doc_id, revision, fingerprint, body FROM documents WHERE doc_json IS NULL ORDER BY doc_id LIMIT 1").fetchone()
out["schema_after_old_open"] = conn.execute("SELECT value FROM meta WHERE key='schema'").fetchone()[0]
conn.close()
# a plain document is still editable by the old code
ack = nb.save(plain["doc_id"], title="", title_is_manual=False, body=plain["body"] + " — edited by the old code", base_revision=plain["revision"], base_fingerprint=plain["fingerprint"], request_id="req_rollback_plain_1")
out["plain_edit"] = {"doc": plain["doc_id"], "revision": ack["revision"], "was": plain["revision"]}
# the old code cannot flatten a structured head: the store's own trigger refuses
try:
    nb.save(rich["doc_id"], title="", title_is_manual=False, body=rich["body"] + " flattened", base_revision=rich["revision"], base_fingerprint=rich["fingerprint"], request_id="req_rollback_rich_1")
    out["rich_flatten"] = "ACCEPTED (wrong)"
except Exception as e:
    out["rich_flatten"] = "refused: " + type(e).__name__ + ": " + str(e)[:120]
# nor checkpoint it without its structure (the old checkpoint is idempotent per
# document, revision and reason, so a reason with no checkpoint yet is used, and
# the row count is compared: an existing row returned is not a write)
conn = sqlite3.connect(str(nb.db_path()))
used = {r[0] for r in conn.execute("SELECT reason FROM checkpoints WHERE doc_id = ? AND revision = ?", (rich["doc_id"], rich["revision"])).fetchall()}
n_before = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0]
conn.close()
reason = next(r for r in nb.REASONS if r not in used)
try:
    nb.checkpoint(rich["doc_id"], revision=rich["revision"], fingerprint_=rich["fingerprint"], reason=reason)
    out["rich_checkpoint"] = "ACCEPTED (wrong)"
except Exception as e:
    out["rich_checkpoint"] = "refused: " + type(e).__name__ + ": " + str(e)[:120]
conn = sqlite3.connect(str(nb.db_path()))
out["checkpoints_written_by_old_code_on_rich_head"] = conn.execute("SELECT COUNT(*) FROM checkpoints").fetchone()[0] - n_before
conn.close()
# through the old server's route, the refusal is an error status, and the head is untouched
import server, gate
c = server.app.test_client(); c.set_cookie(gate.SESSION_COOKIE, gate.issue_session("rehearsal")["token"])
r = c.put("/api/notebook/documents/" + rich["doc_id"], json={"title": "", "title_is_manual": False, "body": rich["body"] + " via route", "base_revision": rich["revision"], "base_fingerprint": rich["fingerprint"], "request_id": "req_rollback_rich_2"})
out["rich_flatten_via_old_route"] = {"status": r.status_code, "error": (r.get_json() or {}).get("error", "")[:100] if r.is_json else r.get_data(as_text=True)[:100]}
head = nb.get(rich["doc_id"])
out["rich_head_after"] = {"revision": head["revision"], "fingerprint_same": head["fingerprint"] == rich["fingerprint"], "body_same": head["body"] == rich["body"]}
g = c.get("/api/notebook/documents/" + rich["doc_id"])
out["rich_read_via_old_route"] = {"status": g.status_code, "body_same": (g.get_json() or {}).get("body") == rich["body"]}
print("RESULT " + json.dumps(out))
'''
    rb = run_py(rollback_code, old, {})
    say("4. rollback — the old code (17894e3) on a copy of the v2 store:", json.dumps(rb))
    rolled = counts(old / "local_state")
    say("   the store after the old code ran:", json.dumps(rolled))

    # ---- 5. forward again: the new code on the rolled-back store ----
    fwd = run_py(startup_code, REPO, {"WORDICON_STATE": str(old / "local_state"), "LIVE_ITEMS": "-1"})
    say("5. the new code on the rolled-back store — startup and index:", json.dumps(fwd))
    fwd_counts = counts(old / "local_state")
    ok_forward = (fwd_counts.get("documents_structured") == before.get("documents_structured")
                  and fwd_counts.get("integrity_notebook") == "ok" and fwd_counts.get("notebook_schema") == "2"
                  and fwd_counts.get("checkpoints") == before.get("checkpoints"))
    say("   structured heads intact, schema 2, checkpoints untouched, integrity ok:", ok_forward, json.dumps(fwd_counts))
    subprocess.run(["git", "worktree", "remove", "--force", str(old)], cwd=str(REPO), capture_output=True)
    summary = {"rehearsal_dir": str(R), "live": before, "backup": b, "restore": rs, "restored_counts": after, "restore_equal": same,
               "startup_on_restored": st, "live_index": live_index, "rollback": rb, "rolled_counts": rolled, "forward": fwd, "forward_counts": fwd_counts, "forward_ok": ok_forward}
    (R / "rehearsal.json").write_text(json.dumps(summary, indent=1))
    (R / "rehearsal.log").write_text("\n".join(LOG) + "\n")
    say("written", R / "rehearsal.json")


if __name__ == "__main__":
    main()
