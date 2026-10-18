#!/usr/bin/env python3
"""Deterministic code-only manifests from Git objects; no store or network access.

Generate writes JSON to stdout. Verify reads the supplied manifest and named Git
objects, and optionally compares the exact checkout. Untracked files are never
opened and symlinks are hashed as link-target bytes, never traversed.
"""
from __future__ import annotations
import argparse
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import stat
import subprocess
import sys

SCHEMA = "nikodemus.code-manifest.v1"
MODES = {"100644", "100755", "120000"}


class ManifestError(ValueError):
    pass


def _git(repo, *args):
    env = {**os.environ, "GIT_OPTIONAL_LOCKS": "0"}
    result = subprocess.run(["git", "--no-replace-objects", "-C", str(repo), *args],
                            capture_output=True, env=env)
    if result.returncode:
        raise ManifestError("Git could not read the requested repository or commit: " + result.stderr.decode(errors="replace").strip())
    return result.stdout


def _hex(value):
    return bool(isinstance(value, str) and re.fullmatch(r"(?:[a-f0-9]{40}|[a-f0-9]{64})", value))


def _path(value):
    path = PurePosixPath(value)
    if not value or "\\" in value or path.is_absolute() or (os.name == "nt" and ":" in value) or any(part in ("", ".", "..", ".git") for part in value.split("/")):
        raise ManifestError("Unsafe tracked path in Git tree.")
    return path


def generate(repo, revision="HEAD"):
    repo = Path(repo).resolve()
    commit = _git(repo, "rev-parse", "--verify", "--end-of-options", revision + "^{commit}").decode().strip()
    if not _hex(commit):
        raise ManifestError("Git did not resolve a full commit identity.")
    tree = _git(repo, "rev-parse", commit + "^{tree}").decode().strip()
    objects = _git(repo, "ls-tree", "-rz", "--full-tree", commit).split(b"\0")
    files = []
    for row in objects:
        if not row:
            continue
        metadata, raw_path = row.split(b"\t", 1)
        mode, kind, oid = metadata.decode("ascii").split(" ")
        path = os.fsdecode(raw_path)
        _path(path)
        if kind != "blob" or mode not in MODES:
            raise ManifestError("Submodules and unsupported Git entries need a separate manifest: " + path)
        files.append({"path": path, "mode": mode, "git_blob": oid})
    cache = {}
    process = subprocess.Popen(["git", "--no-replace-objects", "-C", str(repo), "cat-file", "--batch"],
                               stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
                               env={**os.environ, "GIT_OPTIONAL_LOCKS": "0"})
    try:
        for entry in files:
            oid = entry["git_blob"]
            if oid not in cache:
                process.stdin.write((oid + "\n").encode("ascii")); process.stdin.flush()
                header = process.stdout.readline().decode("ascii").strip().split(" ")
                if len(header) != 3 or header[0] != oid or header[1] != "blob":
                    raise ManifestError("Git blob is unavailable: " + oid)
                size = int(header[2]); remaining = size; digest = hashlib.sha256()
                while remaining:
                    chunk = process.stdout.read(min(1024 * 1024, remaining))
                    if not chunk:
                        raise ManifestError("Git returned an incomplete blob: " + oid)
                    digest.update(chunk); remaining -= len(chunk)
                if process.stdout.read(1) != b"\n":
                    raise ManifestError("Git blob framing failed.")
                cache[oid] = {"bytes": size, "sha256": digest.hexdigest()}
            entry.update(cache[oid])
        process.stdin.close()
        if process.wait(timeout=30):
            raise ManifestError("Git could not finish reading committed blobs.")
    finally:
        if process.poll() is None:
            process.terminate(); process.wait(timeout=10)
        for stream in (process.stdin, process.stdout, process.stderr):
            if not stream.closed: stream.close()
    return {"schema": SCHEMA, "commit": commit, "tree": tree,
            "object_format": _git(repo, "rev-parse", "--show-object-format").decode().strip(),
            "scope": "All tracked blobs at the named commit; no untracked files, live stores or submodules.",
            "file_count": len(files), "files": files}


def _checkout_entry(root, entry):
    parts = _path(entry["path"]).parts
    parent = root
    for part in parts[:-1]:
        parent = parent / part
        info = parent.lstat()
        if not stat.S_ISDIR(info.st_mode):
            raise ManifestError("Checkout parent is not a real directory: " + entry["path"])
    target = parent / parts[-1]
    info = target.lstat()
    if entry["mode"] == "120000":
        if not stat.S_ISLNK(info.st_mode):
            raise ManifestError("Expected a symlink: " + entry["path"])
        raw = os.fsencode(os.readlink(target))
        return len(raw), hashlib.sha256(raw).hexdigest()
    if not stat.S_ISREG(info.st_mode):
        raise ManifestError("Expected a regular file: " + entry["path"])
    if os.name != "nt" and bool(info.st_mode & 0o111) != (entry["mode"] == "100755"):
        raise ManifestError("Executable mode differs: " + entry["path"])
    fd = os.open(target, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0))
    with os.fdopen(fd, "rb") as stream:
        opened = os.fstat(stream.fileno())
        if (opened.st_dev, opened.st_ino) != (info.st_dev, info.st_ino):
            raise ManifestError("Checkout file changed during verification: " + entry["path"])
        digest = hashlib.sha256(); size = 0
        for chunk in iter(lambda: stream.read(1024 * 1024), b""):
            digest.update(chunk); size += len(chunk)
    return size, digest.hexdigest()


def verify(repo, manifest, *, working_tree=False):
    if not isinstance(manifest, dict) or manifest.get("schema") != SCHEMA or not _hex(manifest.get("commit")):
        raise ManifestError("A supported manifest with its full commit identity is required.")
    if not isinstance(manifest.get("files"),list) or any(not isinstance(entry,dict) or not isinstance(entry.get("path"),str) for entry in manifest["files"]):
        raise ManifestError("Manifest files must be records with relative paths.")
    expected = generate(repo, manifest["commit"])
    if json.dumps(manifest,sort_keys=True,ensure_ascii=True) != json.dumps(expected,sort_keys=True,ensure_ascii=True):
        provided = {f.get("path"): f for f in manifest.get("files", []) if isinstance(f, dict)}
        actual = {f["path"]: f for f in expected["files"]}
        mismatch = sorted(set(provided) ^ set(actual) | {p for p in provided.keys() & actual.keys() if provided[p] != actual[p]}, key=str)
        raise ManifestError("Manifest differs from committed Git objects" + (": " + ", ".join(str(p) for p in mismatch[:10]) if mismatch else " (metadata or ordering)") + ".")
    if working_tree:
        root = Path(os.fsdecode(_git(repo, "rev-parse", "--show-toplevel")).strip()).resolve()
        head = _git(repo, "rev-parse", "HEAD").decode().strip()
        if head != manifest["commit"]:
            raise ManifestError("Checkout HEAD differs from the manifest commit; check out the full named commit first.")
        for entry in expected["files"]:
            try: size, digest = _checkout_entry(root, entry)
            except OSError as exc:
                raise ManifestError("Tracked checkout file is unavailable: " + entry["path"]) from exc
            if size != entry["bytes"] or digest != entry["sha256"]:
                raise ManifestError("Checkout bytes differ: " + entry["path"])
    return {"ok": True, "commit": expected["commit"], "tree": expected["tree"],
            "file_count": expected["file_count"], "working_tree_verified": working_tree,
            "scope": expected["scope"]}


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    gen = commands.add_parser("generate", help="Print a deterministic manifest from committed Git objects")
    gen.add_argument("--repo", default="."); gen.add_argument("--commit", default="HEAD")
    check = commands.add_parser("verify", help="Verify a supplied manifest against the same Git commit")
    check.add_argument("--repo", default="."); check.add_argument("--manifest", required=True)
    check.add_argument("--working-tree", action="store_true", help="Also require exact HEAD, tracked bytes and executable modes")
    args = parser.parse_args(argv)
    try:
        if args.command == "generate":
            result = generate(args.repo, args.commit)
        else:
            result = verify(args.repo, json.loads(Path(args.manifest).read_text()), working_tree=args.working_tree)
        print(json.dumps(result, indent=2, ensure_ascii=True))
        return 0
    except (ManifestError, OSError, ValueError, subprocess.SubprocessError) as exc:
        print("Code manifest verification failed: " + str(exc), file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
