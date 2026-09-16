#!/usr/bin/env python3
"""Start a PREVIEW of this checkout on its own data root, without touching
anything else — the one tested way to try a candidate (workspace-v2; the
review of 6e5b59c, finding 2).

    python3 scripts/preview.py                      # an empty root, fixtures for model answers, port 8421
    python3 scripts/preview.py --from ~/Downloads/wordicon\\ 7\\ 2/local_state
                                                    # a consistent copy of an existing store (its server stopped first)
    python3 scripts/preview.py --from <root> --no-serve   # only make the copy; print the command to serve it

What it does, and only this:
  * allocates a NEW directory under ~/nikodemus-preview/ named by the time
    (preview-YYYYMMDDTHHMMSSZ/state, with a counter if that name is taken),
    made by an exclusive mkdir; it never reuses one and never deletes
    anything — a previous preview's writing stays where it was, and a
    refused run makes nothing;
  * with --from, takes that store's corpus lease and HOLDS it for the whole
    copy (refusing while a server holds it; refusing when it cannot be
    checked; saying so when the source has none), and copies the store
    WITHOUT its vault configuration and history
    (vault/), its pairing secret and sessions (auth/), its locks, its
    derived index and its search database, and copies every SQLite store
    through SQLite's own backup API so the copy is consistent;
  * starts server.py with WORDICON_STATE pointing at the new root,
    WORDICON_PREVIEW=1 (no backup at start, on a timer or at shutdown; no
    pruning; no drill; no notification, whatever the root carries),
    WORDICON_LAN=0 (loopback only), and — unless --live is given — with
    WORDICON_TEST_MODE=1, so every model answer is a fixture and no socket
    leaves the machine. --live uses the real gateway (a key in the
    environment) and is for a preview of your own writing with real runs.

Nothing here reads or writes the store it copies from beyond that one
consistent copy; nothing here touches the live server's port, data or
backups. Promotion to the live data is a different act and is not this
script's.
"""
import argparse
import fcntl
import json
import os
import pathlib
import shutil
import sqlite3
import subprocess
import sys
import time

REPO = pathlib.Path(__file__).resolve().parents[1]
EXCLUDE_DIRS = {"vault", "auth"}                       # the owner's backups and the gate: never copied into a preview
EXCLUDE_NAMES = {"work_index.sqlite3", "operations.lock", ".env"}
EXCLUDE_SUFFIXES = (".lock", "-journal", "-wal", "-shm")
EXCLUDE_REL = {"library/search.db"}                    # rebuilt by the Library; never authority


def _hold_lease(root: pathlib.Path):
    """Take the source store's corpus lease (the same flock a serving process
    holds) and KEEP it for the whole copy — returned as an open descriptor
    the caller closes in a finally, so no writer can start on the source
    while the copy is being made (the review of 0f2db31, finding 2: the
    earlier check took and released the lock before copying, and a second
    writer could slip in between). Returns (fd, note):
      (fd, "")        the lease is held by this process until fd is closed;
      (None, note)    the source has no lease file at all — no serving
                      process of this store has ever held one — and the
                      copy proceeds without it, said so;
    raises PreviewRefused when another process holds the lease, or when the
    lease exists but cannot be checked (fail closed)."""
    p = root / "vault" / "lease"
    if not p.exists():
        return None, "no lease file in the source (no server of this store has held one); nothing could be holding it"
    try:
        fd = os.open(p, os.O_RDWR)
    except OSError as e:
        raise PreviewRefused(3, f"refusing: the lease at {p} exists but cannot be checked ({e.__class__.__name__}: {e}) — not copying a store whose writers cannot be excluded")
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        holder = ""
        try:
            holder = os.read(fd, 400).decode("utf-8", "replace").strip()
        except OSError:
            pass
        os.close(fd)
        raise PreviewRefused(3, f"refusing: the store at {root} is in use by {holder or 'another process'!r} — stop that server first, then run this again")
    return fd, ""


class PreviewRefused(Exception):
    def __init__(self, rc: int, message: str):
        super().__init__(message)
        self.rc = rc


def _allocate(root_dir: pathlib.Path, stamp: str = "") -> pathlib.Path:
    """A NEW preview directory, taken by an exclusive mkdir. The name is the
    time; a name already taken (another run in the same second) gets a
    counter. Nothing is ever reused, nothing is ever removed: a preview that
    exists stays exactly where it is, whatever this run does."""
    root_dir = root_dir.expanduser()
    root_dir.mkdir(parents=True, exist_ok=True)
    stamp = stamp or time.strftime("%Y%m%dT%H%M%SZ", time.gmtime())
    for n in range(1, 1000):
        d = root_dir / (f"preview-{stamp}" if n == 1 else f"preview-{stamp}-{n}")
        try:
            d.mkdir(exist_ok=False)          # exclusive: two runs cannot take one name
        except FileExistsError:
            continue
        return d / "state"
    raise RuntimeError(f"no free preview name under {root_dir} for {stamp} (a thousand exist?)")


def _copy_store(src: pathlib.Path, dst: pathlib.Path) -> dict:
    dst.mkdir(parents=True, exist_ok=False)
    copied, skipped = 0, []
    for p in sorted(src.rglob("*")):
        rel = p.relative_to(src)
        parts = rel.parts
        if parts and parts[0] in EXCLUDE_DIRS:
            skipped.append(str(rel)); continue
        if p.is_dir():
            continue
        if p.name in EXCLUDE_NAMES or p.name.endswith(EXCLUDE_SUFFIXES) or str(rel) in EXCLUDE_REL:
            skipped.append(str(rel)); continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(p, target)
        copied += 1
    # every SQLite store again, through SQLite's own backup API: consistent
    # even if a writer is mid-transaction (a stopped server has none, but the
    # copy does not depend on that)
    api = []
    for p in sorted(src.rglob("*.sqlite3")):
        rel = p.relative_to(src)
        if rel.parts[0] in EXCLUDE_DIRS or p.name in EXCLUDE_NAMES or str(rel) in EXCLUDE_REL:
            continue
        target = dst / rel
        target.parent.mkdir(parents=True, exist_ok=True)
        s = sqlite3.connect(f"file:{p}?mode=ro", uri=True, timeout=30)
        try:
            if target.exists():
                target.unlink()
            d = sqlite3.connect(str(target))
            try:
                s.backup(d)
            finally:
                d.close()
        finally:
            s.close()
        api.append(str(rel))
    return {"copied": copied, "sqlite_backup_api": api, "skipped": sorted(set(x.split("/")[0] if x.split("/")[0] in EXCLUDE_DIRS else x for x in skipped))}


def _counts(root: pathlib.Path) -> dict:
    out = {}
    nb = root / "notebook.sqlite3"
    if nb.exists():
        c = sqlite3.connect(f"file:{nb}?mode=ro", uri=True)
        try:
            out["documents"] = c.execute("SELECT COUNT(*) FROM documents").fetchone()[0]
            out["integrity"] = c.execute("PRAGMA integrity_check").fetchone()[0]
        finally:
            c.close()
    out["results"] = len(list((root / "results").glob("*.json"))) if (root / "results").exists() else 0
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="start a preview of this checkout on its own data root")
    ap.add_argument("--from", dest="src", help="an existing state root to copy (its server must be stopped)")
    ap.add_argument("--port", type=int, default=8421)
    ap.add_argument("--root-dir", default=str(pathlib.Path.home() / "nikodemus-preview"), help="where preview roots are made (default ~/nikodemus-preview)")
    ap.add_argument("--live", action="store_true", help="use the real gateway (a key in the environment) instead of fixtures")
    ap.add_argument("--no-serve", action="store_true", help="prepare the root and print the command instead of starting the server")
    a = ap.parse_args(argv)

    src = None
    lease_fd, lease_note = None, ""
    if a.src:
        # every refusal comes BEFORE a directory is made, so a refused run leaves nothing behind
        src = pathlib.Path(a.src).expanduser().resolve()
        if not (src / "notebook.sqlite3").exists() and not (src / "accepted_concepts.json").exists():
            print(f"refusing: {src} does not look like a state root (no notebook.sqlite3 or accepted_concepts.json)")
            return 2
        try:
            lease_fd, lease_note = _hold_lease(src)     # held from here until the copy is complete
        except PreviewRefused as e:
            print(str(e))
            return e.rc
    try:
        root = _allocate(pathlib.Path(a.root_dir))
        if src is not None:
            rep = _copy_store(src, root)
            print(f"copied {rep['copied']} files from {src}" + (" — the source's lease was held throughout" if lease_fd is not None else f" — {lease_note}"))
            print(f"  SQLite stores copied through the backup API: {', '.join(rep['sqlite_backup_api']) or 'none'}")
            print(f"  left behind on purpose: {', '.join(rep['skipped']) or 'nothing'}")
            (root / "preview-copy.json").write_text(json.dumps({"copied_from": str(src), "copied_at": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
                                                                "source_lease": ("held throughout the copy" if lease_fd is not None else lease_note),
                                                                "sqlite_backup_api": rep["sqlite_backup_api"], "left_behind": rep["skipped"]}, indent=1) + "\n")
    finally:
        if lease_fd is not None:
            try:
                fcntl.flock(lease_fd, fcntl.LOCK_UN)
            finally:
                os.close(lease_fd)
    if src is None:
        root.mkdir(parents=True, exist_ok=False)
        (root / "results").mkdir(); (root / "receipts").mkdir()
    print(f"preview root: {root}")
    print(f"  {_counts(root)}")

    env = dict(os.environ)
    env.update({"WORDICON_STATE": str(root), "WORDICON_PREVIEW": "1", "WORDICON_LAN": "0", "PORT": str(a.port)})
    env.pop("ANTHROPIC_API_KEY", None) if not a.live else None
    if not a.live:
        env["WORDICON_TEST_MODE"] = "1"       # fixtures answer; no socket leaves the machine; the real app's port is refused
    else:
        env.pop("WORDICON_TEST_MODE", None)
    cmd = [sys.executable, str(REPO / "server.py")]
    shown = " ".join(f"{k}={env[k]}" for k in ("WORDICON_STATE", "WORDICON_PREVIEW", "WORDICON_LAN", "PORT") + (("WORDICON_TEST_MODE",) if not a.live else ()))
    print(f"\nserving: {shown} python3 server.py")
    print(f"open http://127.0.0.1:{a.port}/pair with the code the server prints, then http://127.0.0.1:{a.port}/work")
    if not a.live:
        print("model answers in this preview are FIXTURES (test mode); start with --live for real runs on this root")
    if a.no_serve:
        return 0
    os.chdir(REPO)
    os.execvpe(cmd[0], cmd, env)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
