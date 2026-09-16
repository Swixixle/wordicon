#!/usr/bin/env python3
"""The browser side of the sabotage pass: each mutation of the workspace's
browser modules must make the editor journey fail its NAMED check, then be
restored. Runs against a dev scratch server started like the journeys' work
server (JOURNEY_DIR with token/cookie/state, JOURNEY_PORT), which serves
webapp/work from disk, so a mutation is live on the next page load.
Usage: JOURNEY_DIR=<dir> JOURNEY_PORT=<port> python3 tests/slice_g/sabotage_browser.py <report.json>"""
import json
import os
import pathlib
import subprocess
import sys

REPO = pathlib.Path(__file__).resolve().parents[2]
DEV = pathlib.Path(os.environ.get("JOURNEY_DIR", "/tmp/nikodemus-dev"))   # the dev scratch server's directory (token, cookie, state, out)
SC = pathlib.Path(os.environ.get("SABOTAGE_OUT", str(DEV / "sabotage")))
SC.mkdir(parents=True, exist_ok=True)
ENGINE = os.environ.get("JOURNEY_ENGINE", "chromium")
PORT = os.environ.get("JOURNEY_PORT", "8499")

MUTATIONS = [
    {"name": "omit the structure from the recovery envelope", "file": "webapp/work/session.js",
     "old": "      structure: this.adapter.getStructure ? this.adapter.getStructure() : null,\n      doc_schema:",
     "new": "      structure: null,\n      doc_schema:",
     "expect": "an unsent formatting-only edit (no character changed) is recovered from the envelope"},
    {"name": "drop the editor-session/sequence guard on an application", "file": "webapp/work/apply.js",
     "old": "    if (s.editorSession !== scope.editor_session || s.seq !== scope.seq) return { ok: false, why: 'the draft changed since this result was made', retarget: true };\n",
     "new": "",
     "expect": "after the draft changed, the old target is refused"},
    {"name": "drop the editor's own last check on the words at the target", "file": "webapp/work/editor_pm.js",
     "old": "    if (current.slice(start, end) !== expect) return { ok: false, why: 'the words at that place are not the words this suggestion was made for' };\n",
     "new": "",
     "expect": "the editor’s own last check refuses a target"},
    {"name": "ignore a reply that arrives after the switch", "file": "webapp/work/session.js",
     "old": "      if (r.ok && d && !d.error && r.status === 200) this.lateAck(inf, d);\n",
     "new": "",
     "expect": "the late reply repaired its envelope"},
    {"name": "switch documents without waiting for the save in flight", "file": "webapp/work/session.js",
     "old": "    if (this.id) await this.settle(undefined, SWITCH_WAIT_MS);",
     "new": "    await this.flush();",
     "expect": "every word typed before the switch is on the server"},
]


def run_journey(tag):
    env = {**os.environ, "JOURNEY_DIR": str(DEV), "JOURNEY_STATE": str(DEV / "state"), "JOURNEY_OUT": str(DEV / "out"),
           "JOURNEY_PORT": PORT, "JOURNEY_ENGINE": ENGINE}
    log = SC / f"sabotage-browser-{tag}.log"
    with open(log, "w") as fh:
        subprocess.run(["node", "editor.js"], cwd=str(REPO / "tests" / "journeys"), stdout=fh, stderr=subprocess.STDOUT, env=env, timeout=900)
    return log.read_text(encoding="utf-8")


def main():
    only = [a[len("--only="):] for a in sys.argv[2:] if a.startswith("--only=")]
    report = []
    for i, m in enumerate(MUTATIONS):
        if only and not any(o.lower() in m["name"].lower() for o in only):
            continue
        path = REPO / m["file"]
        src = path.read_text(encoding="utf-8")
        if src.count(m["old"]) != 1:
            report.append({"mutation": m["name"], "applied": False, "why": f"the anchor text occurs {src.count(m['old'])} times — not applied"})
            print("NOT APPLIED " + m["name"], flush=True)
            continue
        path.write_text(src.replace(m["old"], m["new"], 1), encoding="utf-8")
        try:
            out = run_journey(f"m{i}")
        finally:
            path.write_text(src, encoding="utf-8")   # the file as it was before the mutation, uncommitted work included
        fails = [l[5:] for l in out.splitlines() if l.startswith("FAIL ")]
        hit = [f for f in fails if m["expect"] in f]
        n = next((l for l in out.splitlines() if l.startswith("CHECKS ")), "CHECKS ?")
        report.append({"mutation": m["name"], "file": m["file"], "engine": ENGINE, "applied": True, "caught": bool(hit),
                       "named_check": m["expect"], "failed_checks": [f[:160] for f in fails][:8], "checks": n})
        print(("caught  " if hit else "MISSED  ") + m["name"] + " → " + (hit[0][:120] if hit else ("other failures: " + str(len(fails)))), flush=True)
    clean = subprocess.run(["git", "status", "--short", "--", "webapp/work"], cwd=str(REPO), capture_output=True, text=True).stdout
    report.append({"restored_webapp_work": clean.strip() == "", "git_status_webapp_work": clean.strip()})
    pathlib.Path(sys.argv[1] if len(sys.argv) > 1 else "sabotage-browser-report.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report[-1]))


if __name__ == "__main__":
    main()
