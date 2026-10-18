#!/usr/bin/env python3
"""Install a frozen, clean Git checkpoint into an existing managed beta.

Dry run is the default. This tool never imports the app, changes its store or
credentials, installs dependencies, creates connectors, or runs a model. A
complete baseline is required. Generated identities are outside the Git tree.
"""
from __future__ import annotations
import argparse
from contextlib import closing
from datetime import datetime, timezone
import fcntl
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import re
import sqlite3
import socket
import stat
import subprocess
import sys
import tempfile

MARKERS = ('.candidate-commit', '.open-case-integration.json')
DIRECTORIES = {'scripts', 'webapp', 'src', 'tests', 'docs', 'fixtures', 'schemas', 'config', '.github'}
TOP_FILES = {'server.py', 'notify.py', 'conftest.py', 'README.md', 'CURRENT-STATE.txt', '.gitignore'}
TERMINAL = {'complete', 'failed', 'unknown'}


class Refusal(RuntimeError):
    pass


def sha(data):
    return hashlib.sha256(data).hexdigest()


def git(source, *args):
    proc = subprocess.run(['git', '-C', str(source), *args], capture_output=True)
    if proc.returncode:
        raise Refusal('Git verification failed: ' + args[0])
    return proc.stdout


def no_symlinks(path):
    path = Path(os.path.abspath(path))
    for part in [path, *path.parents]:
        if part.is_symlink():
            raise Refusal('Symlink in managed path: ' + str(part))
        if part != path and part.exists() and not part.is_dir():
            raise Refusal('File blocks a managed parent directory: ' + str(part))
    return path


def relative(value):
    p = PurePosixPath(value)
    if not isinstance(value, str) or not value or p.is_absolute() or p.as_posix() != value or any(x in ('.', '..') for x in p.parts):
        raise Refusal('Invalid manifest path')
    if not (p.parts[0] in DIRECTORIES or value in TOP_FILES or re.fullmatch(r'requirements(?:-[a-z-]+)?\.txt', value)):
        raise Refusal('Unreviewed tracked path: ' + value)
    if any(x in {'.env', '.git', 'local_state', 'node_modules', '.venv', '__pycache__'} for x in p.parts):
        raise Refusal('Protected tracked path: ' + value)
    return value


def immutable(path):
    return path.startswith('config/') or (path.startswith('requirements') and path != 'requirements-test.txt')


def tree(source, commit):
    result = {}
    for row in git(source, 'ls-tree', '-rz', '--full-tree', commit).split(b'\0'):
        if not row:
            continue
        metadata, name = row.split(b'\t', 1)
        mode, kind, blob = metadata.decode().split()
        path = relative(name.decode('utf-8'))
        if kind != 'blob' or mode not in ('100644', '100755'):
            raise Refusal('Non-regular tracked object: ' + path)
        content = git(source, 'cat-file', 'blob', blob)
        result[path] = {'sha256': sha(content), 'bytes': content, 'mode': int(mode[-3:], 8), 'git_blob': blob}
    if 'server.py' not in result:
        raise Refusal('Checkpoint has no server.py')
    return result


def clean(source, commit):
    if not re.fullmatch(r'[0-9a-f]{40}', commit):
        raise Refusal('Use the full identified 40-character commit')
    if git(source, 'rev-parse', 'HEAD').decode().strip() != commit:
        raise Refusal('Source HEAD is not the requested checkpoint')
    if git(source, 'status', '--porcelain', '--untracked-files=no').strip():
        raise Refusal('Source has tracked edits; commit or isolate them first')


def idle(state):
    database = no_symlinks(state / 'operations.sqlite3')
    if not database.is_file():
        raise Refusal('Existing operations database is missing')
    try:
        with closing(sqlite3.connect(database.as_uri() + '?mode=ro', uri=True, timeout=3)) as db:
            db.execute('PRAGMA query_only=ON')
            statuses = dict(db.execute('SELECT status, count(*) FROM operations GROUP BY status'))
    except sqlite3.Error:
        raise Refusal('Cannot establish idle state from the existing operations database') from None
    if any(status not in TERMINAL and count for status, count in statuses.items()):
        raise Refusal('Active or unrecognized operation status; leave the managed service unchanged')


def read_regular(path):
    no_symlinks(path)
    if not path.is_file() or not stat.S_ISREG(path.stat().st_mode):
        raise Refusal('Missing or non-regular installed file: ' + str(path))
    return path.read_bytes()


def verify_destination(dest, baseline, desired):
    for name, row in baseline.items():
        if sha(read_regular(dest / name)) != row['sha256']:
            raise Refusal('Installed baseline hash differs: ' + name)
        if bool((dest / name).stat().st_mode & 0o111) != bool(row['mode'] & 0o111):
            raise Refusal('Installed executable mode differs: ' + name)
    for name in desired.keys() - baseline.keys():
        path = no_symlinks(dest / name)
        if path.exists():
            raise Refusal('New tracked path collides with existing content: ' + name)
    # Code beneath an owned directory cannot silently stay under a new release
    # marker. Installed dependencies/cache are outside the tracked release scope.
    for root_name in DIRECTORIES - {'config'}:
        root = dest / root_name
        if not root.exists():
            continue
        no_symlinks(root)
        for directory, dirs, files in os.walk(root, followlinks=False):
            for name in list(dirs):
                path = Path(directory) / name
                if name in {'node_modules', '__pycache__'}:
                    dirs.remove(name)
                    continue
                no_symlinks(path)
            for name in files:
                if name == '.DS_Store' or name.endswith('.pyc'):
                    continue
                path = Path(directory) / name
                no_symlinks(path)
                rel = path.relative_to(dest).as_posix()
                if rel not in baseline:
                    raise Refusal('Unexpected installed file outside baseline: ' + rel)
    for marker in MARKERS:
        path = no_symlinks(dest / marker)
        if path.exists():
            read_regular(path)


def prepare(source, commit, baseline_path, config_path, backup_root):
    source, baseline_path, config_path = map(no_symlinks, (source, baseline_path, config_path))
    clean(source, commit)
    cfg_bytes = read_regular(config_path)
    try:
        cfg = json.loads(cfg_bytes)
        dest, state = no_symlinks(Path(cfg['checkout']).expanduser()), no_symlinks(Path(cfg['state']).expanduser())
        python = Path(cfg['python']).expanduser()
        if not python.is_absolute() or not os.access(python, os.X_OK) or not 1 <= int(cfg['port']) <= 65535 or cfg['mode'] not in ('live', 'fixtures'):
            raise ValueError()
    except (KeyError, TypeError, ValueError):
        raise Refusal('Invalid existing beta configuration') from None
    if config_path.name != 'beta.json':
        raise Refusal('Use the existing managed beta.json')
    launcher = no_symlinks(config_path.parent / 'nikodemus_beta.py')
    launcher_bytes = read_regular(launcher)
    backup_root = no_symlinks(backup_root)
    for a, b in [(source, dest), (state, dest), (source, state), (backup_root, dest), (backup_root, state), (backup_root, source)]:
        if a == b or a.is_relative_to(b) or b.is_relative_to(a):
            raise Refusal('Source, runtime, store and backup paths must be separate')
    if not dest.is_dir() or not state.is_dir():
        raise Refusal('Existing runtime/store is missing; this tool never creates one')
    baseline_bytes = read_regular(baseline_path)
    old_manifest = json.loads(baseline_bytes)
    previous = old_manifest.get('code_commit') or old_manifest.get('source_commit')
    if not isinstance(previous, str) or not re.fullmatch('[0-9a-f]{40}', previous):
        raise Refusal('Baseline lacks a full code commit')
    git(source, 'merge-base', '--is-ancestor', previous, commit)
    baseline, desired = tree(source, previous), tree(source, commit)
    rows = old_manifest.get('files', {})
    supplied = rows if isinstance(rows, dict) else {r['path']: r['sha256'] for r in rows}
    if set(supplied) != set(baseline):
        raise Refusal('Baseline must describe every tracked file, not an overlay or partial runtime')
    for name, row in baseline.items():
        if supplied[name] != row['sha256']:
            raise Refusal('Baseline does not match its Git checkpoint: ' + name)
    if baseline.keys() - desired.keys():
        raise Refusal('Tracked removals require a separately reviewed cleanup; nothing was stopped')
    for name, row in desired.items():
        if immutable(name) and (name not in baseline or row['sha256'] != baseline[name]['sha256']):
            raise Refusal('Dependency/configuration change requires separate review: ' + name)
    verify_destination(dest, baseline, desired)
    idle(state)
    clean(source, commit)
    changed = {p: r for p, r in desired.items() if p not in baseline or r['sha256'] != baseline[p]['sha256'] or r['mode'] != baseline[p]['mode']}
    return dict(source=source, commit=commit, baseline_path=baseline_path, baseline_bytes=baseline_bytes,
                config_path=config_path, cfg_bytes=cfg_bytes, cfg=cfg, dest=dest, state=state,
                launcher=launcher, launcher_bytes=launcher_bytes, python=python, backup_root=backup_root,
                previous=previous, baseline=baseline, desired=desired, changed=changed)


def fsync_dir(path):
    fd = os.open(path, os.O_RDONLY)
    try:
        os.fsync(fd)
    finally:
        os.close(fd)


def atomic(path, data, mode):
    no_symlinks(path)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(prefix='.release-', dir=path.parent)
    try:
        with os.fdopen(fd, 'wb') as handle:
            os.fchmod(handle.fileno(), mode)
            handle.write(data); handle.flush(); os.fsync(handle.fileno())
        os.replace(tmp, path)
        fsync_dir(path.parent)
    finally:
        if os.path.exists(tmp):
            os.unlink(tmp)


def unchanged_controls(plan, check_baseline=True):
    controls = [(plan['config_path'], plan['cfg_bytes']), (plan['launcher'], plan['launcher_bytes'])]
    if check_baseline:
        controls.append((plan['baseline_path'], plan['baseline_bytes']))
    for path, expected in controls:
        if read_regular(path) != expected:
            raise Refusal('Pinned deployment input changed: ' + str(path))
    clean(plan['source'], plan['commit'])


def managed(plan, verb):
    # A later release may use the existing generated marker as its baseline;
    # it has intentionally been replaced by the time the verified code opens.
    unchanged_controls(plan, check_baseline=verb != 'open')
    # Never echo launcher stdout/stderr: its output can contain pairing codes or
    # a startup exception with secret config. No raw output is persisted either.
    try:
        result = subprocess.run([str(plan['python']), str(plan['launcher']), verb],
            env={**os.environ, 'NIKODEMUS_BETA_NO_BROWSER': '1'}, capture_output=True, timeout=60)
    except subprocess.TimeoutExpired:
        raise Refusal('Managed ' + verb + ' timed out; inspect the private managed log') from None
    if result.returncode:
        raise Refusal('Managed ' + verb + ' failed (exit ' + str(result.returncode) + '); inspect the private managed log')


def port_closed(plan):
    with socket.socket() as sock:
        sock.settimeout(2)
        if sock.connect_ex(('127.0.0.1', int(plan['cfg']['port']))) == 0:
            raise Refusal('Pinned port still has a listener after managed stop; no code will be installed')


def unchanged_originals(plan, originals):
    for name, prior in originals.items():
        path = no_symlinks(plan['dest'] / name)
        if prior is None:
            if path.exists():
                raise Refusal('New path appeared after backup: ' + name)
        elif read_regular(path) != prior[0] or stat.S_IMODE(path.stat().st_mode) != prior[1]:
            raise Refusal('Backed-up file changed before installation: ' + name)


def apply(plan):
    root = plan['backup_root']
    no_symlinks(root)
    root.mkdir(parents=True, exist_ok=True, mode=0o700)
    if root.stat().st_mode & 0o077:
        raise Refusal('Backup root must be private (mode0700)')
    # One managed configuration has one release lock even if callers choose
    # different private backup destinations.
    lock = no_symlinks(plan['config_path'].parent / '.release-install.lock')
    fd = os.open(lock, os.O_RDWR | os.O_CREAT, 0o600)
    try:
        try:
            fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError:
            raise Refusal('Another release installation is active') from None
        unchanged_controls(plan)
        verify_destination(plan['dest'], plan['baseline'], plan['desired'])
        idle(plan['state'])
        stamp = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%S.%fZ')
        backup = root / (stamp + '-' + plan['commit'][:12])
        backup.mkdir(mode=0o700)
        originals = {}
        for name in [*plan['changed'], *MARKERS]:
            path = no_symlinks(plan['dest'] / name)
            if path.exists():
                data = read_regular(path)
                originals[name] = (data, stat.S_IMODE(path.stat().st_mode))
                atomic(backup / name, data, 0o600)
            else:
                originals[name] = None
        atomic(backup / 'backup.json', json.dumps({'previous_commit': plan['previous'], 'next_commit': plan['commit'],
            'before': {p: {'sha256': sha(v[0]), 'mode': v[1]} if v else None for p, v in originals.items()}}, indent=2).encode(), 0o600)
        fsync_dir(backup); fsync_dir(root)
        # A second idle check minimizes the normal UI-to-stop interval. The
        # post-stop check refuses installation if work appeared in that interval.
        unchanged_controls(plan); verify_destination(plan['dest'], plan['baseline'], plan['desired']); idle(plan['state'])
        unchanged_originals(plan, originals)
        managed(plan, 'stop')
        written = []
        try:
            idle(plan['state'])
            port_closed(plan)
            verify_destination(plan['dest'], plan['baseline'], plan['desired'])
            unchanged_originals(plan, originals)
            for name, row in plan['changed'].items():
                written.append(name)
                atomic(plan['dest'] / name, row['bytes'], row['mode'])
            for name, row in plan['desired'].items():
                if sha(read_regular(plan['dest'] / name)) != row['sha256']:
                    raise Refusal('Post-install verification failed: ' + name)
            manifest = {'schema': 'nikodemus.managed_release.v1', 'source_commit': plan['commit'],
                'previous_commit': plan['previous'], 'installed_at': stamp, 'state': str(plan['state']),
                'contract': 'exact_tracked_checkpoint', 'scope': 'All tracked regular files; environment, credentials, store, installed dependencies and generated markers excluded from Git identity.',
                'files': {p: r['sha256'] for p, r in plan['desired'].items()},
                'installed': sorted(plan['changed']), 'unchanged_verified': sorted(plan['desired'].keys() - plan['changed'].keys()),
                'backup': str(backup)}
            written.append(MARKERS[0]); atomic(plan['dest'] / MARKERS[0], (plan['commit'] + '\n').encode(), 0o600)
            written.append(MARKERS[1]); atomic(plan['dest'] / MARKERS[1], (json.dumps(manifest, indent=2) + '\n').encode(), 0o600)
            if (plan['dest'] / MARKERS[0]).read_text().strip() != json.loads((plan['dest'] / MARKERS[1]).read_text())['source_commit']:
                raise Refusal('Generated release identities disagree')
        except Exception:
            rollback_errors = []
            for name in reversed(written):
                try:
                    previous = originals[name]
                    if previous is None:
                        (plan['dest'] / name).unlink(missing_ok=True); fsync_dir((plan['dest'] / name).parent)
                    else:
                        atomic(plan['dest'] / name, previous[0], previous[1])
                except Exception:
                    rollback_errors.append(name)
            # Never restart after a failed install: old code has been restored,
            # but the owner should inspect the recorded private backup first.
            if rollback_errors:
                raise Refusal('Installation failed and rollback is incomplete for: ' + ', '.join(rollback_errors) +
                              '. Service remains stopped; inspect the private backup.') from None
            raise
        managed(plan, 'open')
        return {'installed': True, 'source_commit': plan['commit'], 'files_verified': len(plan['desired']),
                'files_changed': len(plan['changed']), 'backup': str(backup), 'managed_start': 'succeeded'}
    finally:
        os.close(fd)


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--source', type=Path, default=Path(__file__).resolve().parents[1])
    parser.add_argument('--commit', required=True)
    parser.add_argument('--baseline', type=Path, required=True)
    parser.add_argument('--beta-config', type=Path, default=Path.home() / 'nikodemus-preview/beta/beta.json')
    parser.add_argument('--backup-root', type=Path)
    parser.add_argument('--apply', action='store_true')
    args = parser.parse_args(argv)
    try:
        plan = prepare(args.source, args.commit, args.baseline, args.beta_config,
                       args.backup_root or args.beta_config.parent / 'release-backups')
        result = apply(plan) if args.apply else {'dry_run': True, 'source_commit': args.commit,
            'destination': str(plan['dest']), 'files_verified': len(plan['desired']),
            'changed_files': sorted(plan['changed']), 'service_stopped': False}
        print(json.dumps(result, indent=2))
        return 0
    except (Refusal, OSError, ValueError, KeyError, TypeError) as error:
        # Errors deliberately contain only paths/statuses, never env or launcher output.
        print('Release refused: ' + str(error), file=sys.stderr)
        return 2


if __name__ == '__main__':
    raise SystemExit(main())
