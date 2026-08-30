#!/usr/bin/env python3
"""Secret scanner — code we own, run before every commit matters and in CI.

Scans the files git tracks (or any paths given) for credential material.
Hard findings exit 1 and print file:line with a LABEL, never the matched
value — a scanner that echoes secrets into CI logs would be the leak it
exists to prevent. Env-var NAME references (os.environ reads and prose
mentions) are the safe pattern and are not findings.

Usage:
  python3 scripts/scan_secrets.py --tracked      # everything git tracks
  python3 scripts/scan_secrets.py PATH [PATH…]   # specific files
"""

import pathlib
import re
import subprocess
import sys

HARD = [
    (re.compile(r"sk-ant-[A-Za-z0-9_\-]{8,}"), "anthropic key literal"),
    (re.compile(r"\bsk-[A-Za-z0-9]{20,}"), "sk- key literal"),
    (re.compile(r"\bAKIA[0-9A-Z]{16}\b"), "AWS access key"),
    (re.compile(r"BEGIN [A-Z ]*PRIVATE KEY"), "private key block"),
    (re.compile(r"\bghp_[A-Za-z0-9]{20,}"), "github token"),
    (re.compile(r"\bgithub_pat_[A-Za-z0-9_]{20,}"), "github fine-grained token"),
    (re.compile(r"\bxox[baprs]-[A-Za-z0-9\-]{10,}"), "slack token"),
    (re.compile(r"\bAIza[0-9A-Za-z_\-]{30,}"), "google api key"),
    (re.compile(r"\beyJ[A-Za-z0-9_\-]{20,}\.eyJ[A-Za-z0-9_\-]{20,}\."),
     "JWT literal"),
    (re.compile(r"(api_key|apikey|password|passwd|client_secret|auth_token)"
                r"\s*[:=]\s*[\"'][A-Za-z0-9+/_\-]{16,}[\"']", re.I),
     "credential field with literal value"),
    (re.compile(r"\bBearer\s+[A-Za-z0-9._\-]{20,}"), "bearer token literal"),
]


def tracked_files(root: pathlib.Path) -> "list[str]":
    out = subprocess.run(["git", "ls-files"], capture_output=True, text=True,
                         cwd=root)
    return [f for f in out.stdout.split("\n") if f.strip()]


def scan(paths: "list[pathlib.Path]") -> "list[str]":
    findings = []
    for path in paths:
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except (OSError, IsADirectoryError):
            continue
        if path.suffix in (".png", ".jpg", ".jpeg", ".gif", ".ico", ".woff",
                            ".woff2"):
            continue
        for rx, label in HARD:
            for m in rx.finditer(text):
                # the scanner itself carries these patterns; skip its own body
                if path.name == "scan_secrets.py":
                    continue
                line = text.count("\n", 0, m.start()) + 1
                findings.append(f"{path}:{line} [{label}]")
    return findings


def main() -> int:
    root = pathlib.Path(__file__).resolve().parent.parent
    if "--tracked" in sys.argv:
        files = tracked_files(root)
        if not files:
            print("REFUSING to call emptiness clean: git tracks no files "
                  "here (not a repository, or nothing staged). A scan of "
                  "zero files proves nothing.")
            return 2
        paths = [root / f for f in files]
    else:
        args = [a for a in sys.argv[1:] if not a.startswith("-")]
        if not args:
            print("usage: scan_secrets.py --tracked | PATH [PATH…]")
            return 2
        paths = [pathlib.Path(a) for a in args]
    findings = scan(paths)
    if findings:
        print(f"SECRETS FOUND — {len(findings)} hard finding(s); "
              "values not echoed:")
        for f in findings:
            print(" ", f)
        return 1
    print(f"clean — {len(paths)} file(s), no credential literal")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
