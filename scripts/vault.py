"""The Vault — encrypted backup and restore for the corpus.

What this is: every backup seals a crash-consistent snapshot of
local_state/ into a standard age file (pinned pyrage), encrypted to the
owner's recipient. The identity that opens vaults exists in exactly two
places, neither of them a computer this code runs on: the owner's password
manager and a handwritten paper copy — both proven by full re-entry at
setup. Backups therefore run unattended; restores require the owner.

What makes a backup real here is the RESTORE: the drill decrypts the
newest vault into scratch, boots an isolated Wordicon against it with
external egress poisoned, and proves the corpus OPENS — counts checked
against the vault's own interior manifest (never against the live corpus,
which legitimately moves on). A vault that has not been drilled is
optimism; the retention rules treat drilled vaults accordingly.

Hard rules, enforced below and by the suite:
- The identity is NEVER accepted via argv or environment, never written
  to disk, never logged. Prompts only, unechoed.
- .env, the gate's auth material, and the rebuildable search index never
  ride a vault. A restored corpus demands fresh pairing.
- Sealing goes .partial -> decrypt-verify -> atomic rename. The verify is
  a REAL decrypt: each backup is additionally encrypted to a per-backup
  ephemeral recipient whose secret lives only in this process's memory
  and dies after the check — age's multi-recipient support, used so an
  unattended process can prove its own seal without holding the owner's
  key.
- Extraction uses Python's safe tar filter; hostile members (absolute
  paths, .., links, devices) are refused, and a runtime without the
  filter refuses to extract at all.
- Failures are loud: an append-only vault log plus /api/vault/status;
  silence is never success.
"""

import contextlib
import fcntl
import hashlib
import importlib.metadata
import io
import json
import os
import pathlib
import shutil
import subprocess
import sys
import tarfile
import tempfile
import threading
import time

import pyrage

import wordicon_cli as cli

VAULT_SCHEMA = 1
EXCLUDE_DIRS = {"auth"}            # gate master + sessions: never vaulted
EXCLUDE_NAMES = {".env"}           # credentials never ride, wherever found
EXCLUDE_REL = {"library/search.db",  # rebuildable index, never authority
               "vault/vault.jsonl",  # THIS machine's sealing history: it
#   grows during the seal itself (the sealed row lands after the tar), so
#   vaulting it is self-reference; and a restored corpus must start honest
#   new history — inherited drill rows would vouch for vaults that may not
#   exist where it lands. vault/config.json DOES ride: it holds only the
#   public recipient, so a restored corpus can seal again immediately.
               "vault/lease"}        # the corpus lease file (see below)
QUIET_SECONDS = 15 * 60            # debounce: back up after 15 quiet min
CEILING_SECONDS = 60 * 60          # staleness ceiling: 60 dirty minutes max
STAGE_TIMEOUT = 300


def local_state() -> pathlib.Path:
    return pathlib.Path(cli.LOCAL_STATE)


def vault_conf_dir() -> pathlib.Path:
    return local_state() / "vault"


def config_path() -> pathlib.Path:
    return vault_conf_dir() / "config.json"


def vault_log_path() -> pathlib.Path:
    return vault_conf_dir() / "vault.jsonl"


def load_config() -> dict:
    p = config_path()
    if not p.exists():
        return {}
    try:
        return json.loads(p.read_text())
    except (json.JSONDecodeError, OSError):
        return {}


def destination() -> pathlib.Path:
    cfg = load_config()
    return pathlib.Path(cfg.get("destination") or (
        pathlib.Path.home() / "Library" / "Mobile Documents"
        / "com~apple~CloudDocs" / "Wordicon Vault"))


def _log(row: dict) -> None:
    vault_conf_dir().mkdir(parents=True, exist_ok=True)
    row = {**row, "at": cli._now()}
    with open(vault_log_path(), "a") as f:
        f.write(json.dumps(row) + "\n")


def _log_rows() -> "list[dict]":
    p = vault_log_path()
    if not p.exists():
        return []
    out = []
    for line in p.read_text().splitlines():
        try:
            out.append(json.loads(line))
        except json.JSONDecodeError:
            continue
    return out


def fingerprint(recipient: str) -> str:
    return hashlib.sha256(recipient.encode()).hexdigest()[:16]


# ---------------------------------------------------------------------------
# The corpus lock: writers of the corpus (request handlers, background
# jobs) hold the SHARED side around their persistence; the vault's stager
# takes the EXCLUSIVE side for the sub-second staging copy. Writer-
# preferring so a pending stage is never starved by a stream of requests.
# In-process only, single-server assumption — the same assumption the
# suite's leak check already makes.

class _RWLock:
    def __init__(self):
        self._cond = threading.Condition()
        self._readers = 0
        self._writer_waiting = False
        self._writer_active = False

    def acquire_shared(self):
        with self._cond:
            while self._writer_active or self._writer_waiting:
                self._cond.wait()
            self._readers += 1

    def release_shared(self):
        with self._cond:
            self._readers -= 1
            if self._readers == 0:
                self._cond.notify_all()

    def acquire_exclusive(self, timeout: float) -> bool:
        deadline = time.monotonic() + timeout
        with self._cond:
            self._writer_waiting = True
            try:
                while self._readers > 0 or self._writer_active:
                    left = deadline - time.monotonic()
                    if left <= 0:
                        return False
                    self._cond.wait(left)
                self._writer_active = True
                return True
            finally:
                self._writer_waiting = False

    def release_exclusive(self):
        with self._cond:
            self._writer_active = False
            self._cond.notify_all()


_LOCK = _RWLock()
_BACKUP_SERIAL = threading.Lock()   # one backup at a time within a process
_DIRTY = {"since": None, "last_mark": None}
_LAST_FAILURE = {"msg": ""}


def acquire_corpus_write():
    """The shared side, for callers whose hold spans two hooks (the
    server's before_request / teardown_request pair)."""
    _LOCK.acquire_shared()


def release_corpus_write():
    _LOCK.release_shared()


@contextlib.contextmanager
def corpus_write():
    """Held by anything that persists corpus state — request handlers via
    the server chokepoint, background jobs around their whole run."""
    acquire_corpus_write()
    try:
        yield
    finally:
        release_corpus_write()


def mark_dirty():
    now = time.monotonic()
    if _DIRTY["since"] is None:
        _DIRTY["since"] = now
    _DIRTY["last_mark"] = now


# ---------------------------------------------------------------------------
# The corpus lease — the CROSS-PROCESS side of the story (owner's ruling).
# The RWLock above coordinates threads inside one process; this OS-level
# advisory lease (flock) makes one process the corpus's only writer. The
# server holds it for its whole life; a standalone `vault.py init|backup`
# must win the same lease or refuse clearly — so a terminal backup can
# never race a running server, and two terminal backups can never race
# each other. flock dies with the process: no stale-lockfile cleanup, a
# crash releases it by itself.

_LEASE = {"fd": None}


def lease_path() -> pathlib.Path:
    return vault_conf_dir() / "lease"


def hold_lease(owner: str) -> bool:
    """Take the corpus lease for this process's lifetime. False means
    another process holds it (read lease_holder() for who)."""
    if _LEASE["fd"] is not None:
        return True                       # this process already holds it
    p = lease_path()
    p.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(p, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        os.close(fd)
        return False
    os.ftruncate(fd, 0)
    os.write(fd, f"{owner} (pid {os.getpid()}) since {cli._now()}\n"
             .encode())
    _LEASE["fd"] = fd
    return True


def release_lease():
    """Tests only, in practice — a real holder just exits and the OS
    releases the flock with the process."""
    fd = _LEASE["fd"]
    if fd is not None:
        _LEASE["fd"] = None
        try:
            fcntl.flock(fd, fcntl.LOCK_UN)
        finally:
            os.close(fd)


def lease_holder() -> str:
    try:
        return lease_path().read_text().strip()
    except OSError:
        return ""


def _cli_lease_or_refuse(what: str) -> bool:
    """Standalone init/backup must be the corpus's only writer. True when
    the lease is won; False after printing an honest refusal."""
    if hold_lease(f"vault.py {what}"):
        return True
    holder = lease_holder() or "another process"
    print(f"REFUSED: the corpus is in use by {holder}.\n"
          f"A standalone `{what}` while Wordicon is running could tar a "
          "half-written corpus. Stop the server first (Ctrl-C in its "
          "Terminal) and run this again — backups also run by themselves "
          "at every server start, after quiet changes, and at shutdown.")
    return False


# ---------------------------------------------------------------------------
# init — non-interactive core (tests) + the owner's terminal ritual

def init_vault(identity=None, dest: str = "") -> dict:
    """Create the vault config. Returns the identity STRING exactly once —
    the caller is responsible for the custody ritual. Never writes it."""
    ident = identity or pyrage.x25519.Identity.generate()
    recipient = str(ident.to_public())
    cfg = {"schema": VAULT_SCHEMA, "recipient": recipient,
           "recipient_fingerprint": fingerprint(recipient),
           "pyrage_version": importlib.metadata.version("pyrage"),
           "destination": dest or str(destination()),
           "created_at": cli._now()}
    vault_conf_dir().mkdir(parents=True, exist_ok=True)
    config_path().write_text(json.dumps(cfg, indent=1))
    _log({"type": "init", "recipient_fingerprint": cfg["recipient_fingerprint"],
          "pyrage_version": cfg["pyrage_version"]})
    return {"identity": str(ident), "config": cfg}


def interactive_init() -> int:
    """The owner's one-time ritual, at a real terminal. The identity is
    shown once; custody is PROVEN twice by full re-entry — once from the
    password manager, once from the handwritten paper copy — before the
    first backup is permitted. Nothing here echoes to shell history."""
    import getpass
    if load_config():
        print("A vault config already exists. Refusing to overwrite it — "
              "rotation is a separate, deliberate act.")
        return 2
    got = init_vault()
    ident = got["identity"]
    print("\n=== YOUR RECOVERY SECRET — shown exactly once ===\n")
    print("   " + ident + "\n")
    print("Do BOTH, now:")
    print("  1. Store it in your password manager.")
    print("  2. Write it BY HAND on paper. Store the paper somewhere that")
    print("     is not this Mac and not your Apple account.")
    print("Losing both copies makes every vault permanently unreadable.")
    print("There is no reset and no recovery.\n")
    one = getpass.getpass("Re-enter it from your PASSWORD MANAGER: ").strip()
    two = getpass.getpass("Re-enter it from your PAPER copy: ").strip()
    if one != ident or two != ident:
        config_path().unlink()
        print("\nA re-entry did not match. The config was destroyed — run "
              "init again and store the new secret properly. Nothing was "
              "backed up.")
        return 1
    print("\nCustody proven. Sealing the first vault…")
    name = backup(reason="init")
    if not name:
        print("The first backup FAILED — see the message above. "
              "Fix it before trusting anything.")
        return 1
    print(f"Sealed: {name}")
    print("Next: let iCloud sync it, download that file from iCloud web or "
          "another device, and run:\n  python3 scripts/vault.py drill "
          "--blob <downloaded file> --off-device\nThe vault is not a "
          "successful backup until that off-device drill passes.")
    return 0


# ---------------------------------------------------------------------------
# the snapshot walk — exclusions applied, findings recorded

def _walk(root: pathlib.Path):
    files, findings, excluded = [], [], []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        rel = str(p.relative_to(root))
        parts = pathlib.PurePosixPath(rel).parts
        if parts and parts[0] in EXCLUDE_DIRS:
            excluded.append(rel)
            continue
        if p.name in EXCLUDE_NAMES:
            excluded.append(rel)
            findings.append(f"a file named {p.name!r} was found inside the "
                            f"corpus at {rel!r} and EXCLUDED — credentials "
                            "do not ride vaults")
            continue
        if rel in EXCLUDE_REL:
            excluded.append(rel)
            continue
        files.append((p, rel))
    return files, excluded, findings


def _semantic_counts(root: pathlib.Path) -> dict:
    out = {"accepted_concepts": 0, "results": 0, "documents": 0,
           "media_items": 0, "transcripts": 0}
    try:
        acc = json.loads((root / "accepted_concepts.json").read_text())
        out["accepted_concepts"] = len(acc)
    except (OSError, json.JSONDecodeError):
        pass
    if (root / "results").exists():
        out["results"] = sum(1 for _ in (root / "results").glob("*.json"))
    try:
        out["documents"] = len(json.loads(
            (root / "library" / "documents.json").read_text()))
    except (OSError, json.JSONDecodeError):
        pass
    ml = root / "library" / "media.jsonl"
    if ml.exists():
        for line in ml.read_text().splitlines():
            try:
                r = json.loads(line)
            except json.JSONDecodeError:
                continue
            if r.get("type") == "media":
                out["media_items"] += 1
            elif r.get("type") == "transcript":
                out["transcripts"] += 1
    return out


def _app_commit() -> str:
    try:
        got = subprocess.run(["git", "rev-parse", "HEAD"],
                             capture_output=True, text=True, timeout=10,
                             cwd=pathlib.Path(__file__).resolve().parent.parent)
        return got.stdout.strip() or "unknown"
    except Exception:
        return "unknown"


def _sha(b: bytes) -> str:
    return hashlib.sha256(b).hexdigest()


# ---------------------------------------------------------------------------
# backup: stage under the exclusive lock, manifest, seal, VERIFY, rename

def backup(reason: str = "manual", stage_timeout: float = 0) -> str:
    cfg = load_config()
    if not cfg:
        _LAST_FAILURE["msg"] = ("vault not initialized — run "
                                "python3 scripts/vault.py init")
        return ""
    try:
        with _BACKUP_SERIAL:
            return _backup(cfg, reason, stage_timeout or STAGE_TIMEOUT)
    except Exception as e:
        _LAST_FAILURE["msg"] = f"backup failed: {e}"
        _log({"type": "failure", "reason": reason, "error": str(e)[:500]})
        print(f"VAULT BACKUP FAILED ({reason}): {e}")
        return ""


def _backup(cfg: dict, reason: str, stage_timeout: float) -> str:
    root = local_state()
    stage = pathlib.Path(tempfile.mkdtemp(prefix="wordicon_stage_"))
    try:
        # -- crash-consistent staging: writers drained, copy, release --
        if not _LOCK.acquire_exclusive(stage_timeout):
            raise RuntimeError("could not pause writers within "
                               f"{stage_timeout}s — backup aborted, not "
                               "silently inconsistent")
        try:
            snap = stage / "snap"
            shutil.copytree(root, snap)
        finally:
            _LOCK.release_exclusive()
        files, excluded, findings = _walk(snap)
        manifest = {
            "schema": VAULT_SCHEMA, "created_at": cli._now(),
            "reason": reason, "app_commit": _app_commit(),
            "pyrage_version": cfg.get("pyrage_version", ""),
            "recipient_fingerprint": cfg.get("recipient_fingerprint", ""),
            "files": [{"path": rel, "bytes": p.stat().st_size,
                        "sha256": _sha(p.read_bytes())} for p, rel in files],
            "exclusions": sorted(excluded), "findings": findings,
            "semantic": _semantic_counts(snap),
        }
        buf = io.BytesIO()
        with tarfile.open(fileobj=buf, mode="w:gz") as tf:
            mtxt = json.dumps(manifest, indent=1).encode()
            info = tarfile.TarInfo("manifest.json")
            info.size = len(mtxt)
            tf.addfile(info, io.BytesIO(mtxt))
            for p, rel in files:
                tf.add(p, arcname="local_state/" + rel, recursive=False)
        plain = buf.getvalue()

        # -- seal to the owner's recipient AND a per-backup ephemeral
        #    verify recipient (memory-only, dies after the check) --
        eph = pyrage.x25519.Identity.generate()
        recipient = pyrage.x25519.Recipient.from_str(cfg["recipient"])
        ct = pyrage.encrypt(plain, [recipient, eph.to_public()])

        dest = destination()
        dest.mkdir(parents=True, exist_ok=True)
        stamp = cli._now().replace(":", "").replace("-", "")[:15]
        name = f"wordicon-vault-{stamp}.enc"
        if (dest / name).exists():
            # same-second backup: never rename onto an existing vault.
            # 'x' sorts after '.', so the later seal stays the newer name.
            name = (f"wordicon-vault-{stamp}"
                    f"x{time.time_ns() % 10**9:09d}.enc")
        partial = dest / (name + ".partial")
        partial.write_bytes(ct)

        # -- the verify is a REAL decrypt of the written partial --
        try:
            back = pyrage.decrypt(partial.read_bytes(), [eph])
            with tarfile.open(fileobj=io.BytesIO(back), mode="r:gz") as tf:
                got_manifest = json.loads(
                    tf.extractfile("manifest.json").read())
                for entry in got_manifest["files"]:
                    m = tf.extractfile("local_state/" + entry["path"])
                    if m is None or _sha(m.read()) != entry["sha256"]:
                        raise RuntimeError(
                            f"verify failed on {entry['path']!r} — the "
                            "partial was destroyed, nothing was completed")
        except BaseException:
            partial.unlink(missing_ok=True)   # suspect bytes never linger
            raise
        del eph

        partial.rename(dest / name)
        # payload_verified_locally is the HONEST name for what the
        # ephemeral decrypt proved: the sealed bytes decrypt and match the
        # manifest. It does NOT prove the owner's recipient stanza is
        # usable — only a restore with the owner's recovery identity does,
        # and only drill stamps (type "drilled") ever carry that claim.
        sidecar = {"blob_sha256": _sha(ct), "bytes": len(ct),
                   "created_at": manifest["created_at"],
                   "n_files": len(manifest["files"]),
                   "schema": VAULT_SCHEMA,
                   "payload_verified_locally": True,
                   "recipient_fingerprint": cfg.get("recipient_fingerprint"),
                   "pyrage_version": cfg.get("pyrage_version")}
        (dest / (name + ".json")).write_text(json.dumps(sidecar, indent=1))
        _log({"type": "sealed", "name": name, "reason": reason,
              "bytes": len(ct), "n_files": len(manifest["files"]),
              "payload_verified_locally": True,
              "semantic": manifest["semantic"]})
        _DIRTY["since"] = None
        _LAST_FAILURE["msg"] = ""
        prune()
        return name
    finally:
        shutil.rmtree(stage, ignore_errors=True)


# ---------------------------------------------------------------------------
# restore + drill

def _inspect_member(m: tarfile.TarInfo, out: pathlib.Path) -> str:
    """Why this member is hostile, or '' if it is an honest one. A corpus
    holds regular files and directories, nothing else — so anything else
    is refused BY NAME, never quietly neutralized."""
    name = m.name
    if not (m.isfile() or m.isdir()):
        kind = ("symlink" if m.issym() else "hard link" if m.islnk()
                else "device" if m.isdev() else "special file")
        return f"a {kind} has no place in a corpus"
    posix = pathlib.PurePosixPath(name)
    win = pathlib.PureWindowsPath(name)
    if posix.is_absolute() or win.is_absolute() or win.drive \
            or name.startswith("\\"):
        return "absolute or drive path"
    if ".." in posix.parts or ".." in win.parts:
        return "parent escape"
    resolved = (out / name).resolve()
    if not resolved.is_relative_to(out.resolve()):
        return "resolves outside the destination"
    return ""


def _safe_extract(tf: tarfile.TarFile, out: pathlib.Path):
    """Hostile-archive protection, owner's ruling: EVERY member is
    inspected before ANY extraction begins, and one hostile member refuses
    the whole archive out loud — silently rewriting a member's path would
    change the archive, which this tool never does. Only after every
    member passes does extraction run, still under Python's 'data' filter
    as the second layer; a runtime without that filter refuses outright
    rather than trusting the archive. A refusal extracts NOTHING."""
    bad = []
    for m in tf.getmembers():
        why = _inspect_member(m, out)
        if why:
            bad.append(f"{m.name!r}: {why}")
    if bad:
        raise RuntimeError("hostile archive REFUSED, nothing was "
                           "extracted — " + "; ".join(bad[:5]))
    if not hasattr(tarfile, "data_filter"):
        raise RuntimeError("this Python lacks tarfile's safe extraction "
                           "filter; refusing to extract an archive rather "
                           "than trusting it")
    tf.extractall(out, filter="data")


def restore(blob_path: str, out_dir: str, identity_str: str) -> dict:
    """Decrypt, refuse hostile members before extracting anything, verify
    every file against the interior manifest — and on ANY failure leave no
    partially restored tree behind: what this returns from is either the
    complete verified corpus or nothing at all."""
    ident = pyrage.x25519.Identity.from_str(identity_str.strip())
    plain = pyrage.decrypt(pathlib.Path(blob_path).read_bytes(), [ident])
    out = pathlib.Path(out_dir)
    created_out = not out.exists()
    out.mkdir(parents=True, exist_ok=True)
    try:
        with tarfile.open(fileobj=io.BytesIO(plain), mode="r:gz") as tf:
            _safe_extract(tf, out)
        manifest = json.loads((out / "manifest.json").read_text())
        root = out / "local_state"
        bad = []
        for entry in manifest["files"]:
            p = root / entry["path"]
            if not p.exists() or _sha(p.read_bytes()) != entry["sha256"]:
                bad.append(entry["path"])
        if bad:
            raise RuntimeError("restore verification FAILED for "
                               f"{len(bad)} file(s), first: {bad[0]!r}")
        return manifest
    except BaseException:
        if created_out:
            shutil.rmtree(out, ignore_errors=True)
        else:
            (out / "manifest.json").unlink(missing_ok=True)
            shutil.rmtree(out / "local_state", ignore_errors=True)
        raise


def newest_vault() -> "pathlib.Path | None":
    dest = destination()
    if not dest.exists():
        return None
    vaults = sorted(dest.glob("wordicon-vault-*.enc"))
    return vaults[-1] if vaults else None


def drill(identity_str: str, blob: str = "", off_device: bool = False) -> dict:
    """Restore into scratch and PROVE the corpus opens, judged against the
    vault's own manifest — the live corpus may legitimately have moved on
    and is reported only as context. Runs the verification in a child
    process with external egress poisoned and scratch state."""
    target = pathlib.Path(blob) if blob else newest_vault()
    if not target or not target.exists():
        raise RuntimeError("no vault to drill")
    scratch = pathlib.Path(tempfile.mkdtemp(prefix="wordicon_drill_"))
    try:
        manifest = restore(str(target), str(scratch), identity_str)
        proof = subprocess.run(
            [sys.executable, __file__, "_drill_worker",
             str(scratch / "local_state")],
            capture_output=True, text=True, timeout=300)
        got = {}
        for line in proof.stdout.splitlines():
            if line.startswith("PROOF "):
                k, v = line[6:].split("=", 1)
                got[k] = v
        want = manifest["semantic"]
        failures = []
        if proof.returncode != 0:
            failures.append("the drill worker itself failed: "
                            + proof.stdout[-300:] + proof.stderr[-300:])
        for k, v in want.items():
            if str(got.get(k)) != str(v):
                failures.append(f"{k}: manifest says {v}, restored corpus "
                                f"opened {got.get(k)!r}")
        for k in ("anchor_resolves", "transcript_span", "search_rebuilt",
                  "no_auth_dir", "unpaired_refused"):
            if got.get(k) != "yes" and (want.get("documents") or k in
                                         ("no_auth_dir", "unpaired_refused")):
                if k == "transcript_span" and not want.get("transcripts"):
                    continue
                if k in ("anchor_resolves", "search_rebuilt") and \
                        not want.get("documents"):
                    continue
                failures.append(f"{k} was not proven ({got.get(k)!r})")
        if not got:
            failures.append("the drill produced no proof lines at all — "
                            "a silent drill is a failed drill")
        if failures:
            _log({"type": "drill_failed", "name": target.name,
                  "failures": failures[:6]})
            raise RuntimeError("DRILL FAILED: " + " | ".join(failures[:3]))
        _log({"type": "drilled", "name": target.name,
              "off_device": bool(off_device), "proof": got})
        return {"name": target.name, "proof": got, "manifest": want}
    finally:
        shutil.rmtree(scratch, ignore_errors=True)


def _drill_worker(state_dir: str) -> int:
    """Child process: scratch state, poisoned egress, in-process client.
    External sockets explode; the model gateway raises; email is inert;
    local verification runs through Flask's test client — no real server,
    no real network."""
    import socket

    class _NoNet:
        def __init__(self, *a, **k):
            raise AssertionError("drill attempted a network socket")
    socket.socket = _NoNet
    st = pathlib.Path(state_dir)
    cli.LOCAL_STATE = st
    cli.RESULTS_DIR = st / "results"
    cli.RECEIPTS_DIR = st / "receipts"
    cli.ACCEPTED_CONCEPTS_PATH = st / "accepted_concepts.json"
    cli.EDGES_LOG = st / "edges.jsonl"
    cli.JUDGMENTS_LOG = st / "judgments.jsonl"
    for name, fn in (("WARPS_LOG", "warps.jsonl"),
                     ("WARP_NOTES_LOG", "warp_notes.jsonl"),
                     ("BENCH_CORRECTIONS", "bench_corrections.jsonl"),
                     ("INPUTS_LOG", "inputs.jsonl"),
                     ("WAYFINDER_LOG", "wayfinder.jsonl")):
        if hasattr(cli, name):
            setattr(cli, name, st / fn)
    sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent.parent))
    import server
    import library
    import notify

    def _gw():
        raise AssertionError("drill attempted a model call")
    server.server_gateway = _gw
    notify.notify_job_complete = lambda *a, **k: None

    print("PROOF no_auth_dir=" + ("yes" if not (st / "auth").exists()
                                   else "no"))
    c = server.app.test_client()
    if c.get("/api/library").status_code == 401:
        print("PROOF unpaired_refused=yes")
    else:
        print("PROOF unpaired_refused=no")
    import gate
    c.set_cookie(gate.SESSION_COOKIE, gate.issue_session("drill")["token"])
    lib = c.get("/api/library").get_json() or {}
    print(f"PROOF results={sum(1 for _ in (st / 'results').glob('*.json')) if (st / 'results').exists() else 0}")
    try:
        acc = json.loads((st / "accepted_concepts.json").read_text())
        print(f"PROOF accepted_concepts={len(acc)}")
    except (OSError, json.JSONDecodeError):
        print("PROOF accepted_concepts=0")
    docs = lib.get("documents") or []
    print(f"PROOF documents={len(docs)}")
    media = (c.get("/api/media").get_json() or {}).get("media", [])
    n_tsc = sum(len(m.get("transcripts") or []) for m in media)
    print(f"PROOF media_items={len(media)}")
    print(f"PROOF transcripts={n_tsc}")
    c.get("/api/trails")
    if docs:
        rep = docs[0].get("representation_id", "")
        d = c.get(f"/api/library/doc/{rep}?section=0").get_json() or {}
        a = ""
        for par in (d.get("section") or {}).get("paragraphs", []):
            for s2 in par.get("sentences", []):
                a = s2["anchor_id"]
                break
            if a:
                break
        r = c.get(f"/api/library/resolve/{a}").get_json() or {}
        print("PROOF anchor_resolves=" + ("yes" if r.get("ok") else "no"))
        library.index_all_representations() if hasattr(
            library, "index_all_representations") else None
        try:
            for did, dd in library.load_documents().items():
                rep2 = library.load_representation(
                    dd.get("current_representation_id", ""))
                if rep2:
                    library.index_representation(rep2, did)
            print("PROOF search_rebuilt=yes")
        except Exception:
            print("PROOF search_rebuilt=no")
    if n_tsc:
        tsc_id = media[0]["transcripts"][0]["transcript_id"]
        tdoc = library.load_transcript(tsc_id)
        got = library.retrieve_media_span(tdoc, 0, 0)
        print("PROOF transcript_span=" + ("yes" if got.get("ok") else "no"))
    return 0


# ---------------------------------------------------------------------------
# retention — generational; the drilled vault is immortal

def prune() -> "list[str]":
    """Generational retention with three hard boundaries (owner's
    rulings): nothing prunes before this log holds a real drill stamp —
    sealed rows, payload_verified_locally included, never count; the
    newest drilled vault is immortal; and a vault this log has NO sealed
    row for (unknown history — a restored installation looking at its
    pre-disaster vaults, or anything else this machine did not seal) is
    never pruned at all. After a disaster, that means the old vaults are
    untouchable until the owner's verified history exists again."""
    rows = _log_rows()
    if not any(r.get("type") == "drilled" for r in rows):
        return []           # never prune before one vault has passed a drill
    dest = destination()
    vaults = sorted(dest.glob("wordicon-vault-*.enc"),
                    key=lambda p: p.name)
    if len(vaults) <= 2:
        return []
    sealed_here = {r["name"] for r in rows if r.get("type") == "sealed"}
    drilled = {r["name"] for r in rows if r.get("type") == "drilled"}
    newest_drilled = ""
    for v in reversed(vaults):
        if v.name in drilled:
            newest_drilled = v.name
            break
    now = time.time()
    keep = set()
    keep.update(v.name for v in vaults[-2:])          # two newest, always
    if newest_drilled:
        keep.add(newest_drilled)                       # immortal
    keep.update(v.name for v in vaults
                if v.name not in sealed_here)          # unknown history
    daily, weekly, monthly = {}, {}, {}
    for v in vaults:
        age_days = (now - v.stat().st_mtime) / 86400
        if age_days <= 1:
            keep.add(v.name)
        elif age_days <= 7:
            daily.setdefault(int(age_days), v.name)
        elif age_days <= 35:
            weekly.setdefault(int(age_days // 7), v.name)
        else:
            monthly.setdefault(int(age_days // 30), v.name)
    keep.update(daily.values())
    keep.update(weekly.values())
    keep.update(monthly.values())
    pruned = []
    for v in vaults:
        if v.name not in keep:
            v.unlink(missing_ok=True)
            (dest / (v.name + ".json")).unlink(missing_ok=True)
            pruned.append(v.name)
            _log({"type": "pruned", "name": v.name,
                  "rule": "generational retention"})
    return pruned


# ---------------------------------------------------------------------------
# status — three cloud states, ages, and staleness that turns red by itself

def status() -> dict:
    rows = _log_rows()
    sealed = [r for r in rows if r.get("type") == "sealed"]
    drilled = [r for r in rows if r.get("type") == "drilled"]
    off = [r for r in drilled if r.get("off_device")]
    last_seal = sealed[-1] if sealed else None
    dest = destination()
    vaults = sorted(dest.glob("wordicon-vault-*.enc")) if dest.exists() else []
    nv = newest_vault()
    if nv is None:
        cloud = "no vault"
    elif off and off[-1]["name"] == nv.name:
        cloud = "verified off-device"
    else:
        cloud = "sealed locally — cloud synchronization unverified"
    dirty_for = (time.monotonic() - _DIRTY["since"]) if _DIRTY["since"] else 0
    stale = bool(_DIRTY["since"]) and dirty_for > CEILING_SECONDS
    return {"initialized": bool(load_config()),
            "last_seal_at": (last_seal or {}).get("at", ""),
            # a seal's verification is payload-only, and says so; drill
            # rows are the only carriers of owner-recovery verification
            "last_seal_verification": ("payload_verified_locally"
                                       if last_seal else ""),
            "last_drill_at": (drilled[-1]["at"] if drilled else ""),
            "last_drill_vault": (drilled[-1]["name"] if drilled else ""),
            "cloud": cloud,
            "n_vaults": len(vaults),
            "total_bytes": sum(v.stat().st_size for v in vaults),
            "dirty_seconds": int(dirty_for),
            "stale_red": stale or bool(_LAST_FAILURE["msg"]),
            "failure": _LAST_FAILURE["msg"]}


# ---------------------------------------------------------------------------
# the scheduler: quiet-debounce + the staleness ceiling

def start_scheduler():
    def loop():
        while True:
            time.sleep(30)
            if not load_config() or _DIRTY["since"] is None:
                continue
            now = time.monotonic()
            quiet = now - (_DIRTY["last_mark"] or now)
            dirty = now - _DIRTY["since"]
            if quiet >= QUIET_SECONDS:
                backup(reason="debounce")
            elif dirty >= CEILING_SECONDS:
                backup(reason="ceiling")
    t = threading.Thread(target=loop, daemon=True)
    t.start()
    return t


def _read_identity() -> str:
    """Prompts only — never argv, never environment, never echoed."""
    import getpass
    return getpass.getpass("Recovery secret (AGE-SECRET-KEY-1…): ").strip()


def main() -> int:
    args = sys.argv[1:]
    if not args:
        print("usage: vault.py init|backup|drill|restore|status|"
              "_drill_worker")
        return 2
    cmd = args[0]
    if cmd == "init":
        if not _cli_lease_or_refuse("init"):
            return 3
        return interactive_init()
    if cmd == "backup":
        if not _cli_lease_or_refuse("backup"):
            return 3
        name = backup(reason="manual")
        print(f"sealed {name}" if name else "backup failed")
        return 0 if name else 1
    if cmd == "status":
        print(json.dumps(status(), indent=1))
        return 0
    if cmd == "restore":
        blob = args[args.index("--blob") + 1]
        out = args[args.index("--out") + 1]
        restore(blob, out, _read_identity())
        print(f"restored and verified into {out}")
        return 0
    if cmd == "drill":
        blob = args[args.index("--blob") + 1] if "--blob" in args else ""
        got = drill(_read_identity(), blob=blob,
                    off_device="--off-device" in args)
        print("DRILL PASSED — the vault opens:", json.dumps(got["proof"]))
        return 0
    if cmd == "_drill_worker":
        return _drill_worker(args[1])
    print(f"unknown command {cmd!r}")
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
