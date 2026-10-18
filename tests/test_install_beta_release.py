"""Offline release safety tests: disposable Git tree/store and fake launcher only."""
import contextlib
import fcntl
import hashlib
import importlib.util
import io
import json
import os
from pathlib import Path
import shutil
import sqlite3
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

ROOT = Path(__file__).resolve().parents[1]
spec = importlib.util.spec_from_file_location('release_install', ROOT / 'scripts/install_beta_release.py')
release = importlib.util.module_from_spec(spec); spec.loader.exec_module(release)


class ReleaseTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory(prefix='nk-release-', dir='/private/tmp')
        self.root = Path(self.tmp.name)
        self.source, self.dest, self.state, self.beta = [self.root / x for x in ['source','runtime','state','beta']]
        for p in [self.source,self.dest,self.state,self.beta]: p.mkdir()
        self.backups = self.root / 'backups'
        self.run_git('init','-q'); self.run_git('config','user.email','fixture@example.invalid'); self.run_git('config','user.name','Fixture')
        for name, text in {'server.py':'print("old")\n', 'scripts/worker.py':'VALUE=1\n', 'tests/test_old.py':'# retained test\n',
                           'config/brand.json':'{}\n', 'requirements.txt':'# existing environment\n'}.items():
            p=self.source/name;p.parent.mkdir(parents=True,exist_ok=True);p.write_text(text)
        self.run_git('add','.'); self.run_git('commit','-qm','baseline');self.previous=self.run_git('rev-parse','HEAD').strip()
        files={}
        for name in self.run_git('ls-files').splitlines():
            data=(self.source/name).read_bytes();files[name]=hashlib.sha256(data).hexdigest()
            out=self.dest/name;out.parent.mkdir(parents=True,exist_ok=True);out.write_bytes(data);out.chmod(0o644)
        self.baseline=self.root/'baseline.json';self.baseline.write_text(json.dumps({'code_commit':self.previous,'files':files}))
        (self.dest/'.env').write_text('SECRET_FIXTURE=never-print-this\n')
        (self.dest/'.candidate-commit').write_text('stale-marker\n')
        (self.dest/'.open-case-integration.json').write_text('{"source_commit":"previous-history"}\n')
        with contextlib.closing(sqlite3.connect(self.state/'operations.sqlite3')) as db:
            db.execute('CREATE TABLE operations (status TEXT)');db.execute('INSERT INTO operations VALUES ("complete")')
            db.commit()
        (self.state/'connectors.jsonl').write_text('private fixture connector\n')
        (self.source/'server.py').write_text('print("new")\n')
        (self.source/'webapp').mkdir();(self.source/'webapp/new.js').write_text('// new module\n')
        self.commit=self.commit_source('release')
        self.cfg=self.beta/'beta.json';self.cfg.write_text(json.dumps({'checkout':str(self.dest),'state':str(self.state),
            'python':sys.executable,'port':18426,'mode':'fixtures'}))
        (self.beta/'nikodemus_beta.py').write_text('''import sys,json,pathlib
p=pathlib.Path(__file__).parent
verb=sys.argv[1]
with (p/'calls.jsonl').open('a') as out:out.write(json.dumps({'verb':verb,'backup_exists':bool(list((p.parent/'backups').glob('*/backup.json')))})+'\\n')
print('PAIRING CODE secret-pairing-fixture')
print('Authorization: secret-header-fixture',file=sys.stderr)
if (p/('fail-'+verb)).exists():sys.exit(9)
''')
        self.private_before={p:p.read_bytes() for p in [self.dest/'.env',self.state/'operations.sqlite3',self.state/'connectors.jsonl',self.cfg]}

    def tearDown(self): self.tmp.cleanup()
    def run_git(self,*args): return subprocess.run(['git','-C',str(self.source),*args],check=True,capture_output=True,text=True).stdout
    def commit_source(self,label):
        self.run_git('add','.');self.run_git('commit','-qm',label);return self.run_git('rev-parse','HEAD').strip()
    def plan(self): return release.prepare(self.source,self.commit,self.baseline,self.cfg,self.backups)
    def calls(self):
        p=self.beta/'calls.jsonl';return [json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
    def no_calls(self): self.assertEqual(self.calls(),[])
    def install(self,plan=None):
        with patch.object(release,'port_closed'):return release.apply(plan or self.plan())
    def argv(self): return ['--source',str(self.source),'--commit',self.commit,'--baseline',str(self.baseline),'--beta-config',str(self.cfg),'--backup-root',str(self.backups)]

    def test_default_dry_run_does_not_stop_or_write(self):
        before={p.relative_to(self.dest):p.read_bytes() for p in self.dest.rglob('*') if p.is_file()}
        with contextlib.redirect_stdout(io.StringIO()) as out:self.assertEqual(release.main(self.argv()),0)
        self.assertTrue(json.loads(out.getvalue())['dry_run']);self.no_calls();self.assertFalse(self.backups.exists())
        self.assertEqual(before,{p.relative_to(self.dest):p.read_bytes() for p in self.dest.rglob('*') if p.is_file()})

    def test_dirty_source_and_wrong_commit_refuse_before_stop(self):
        (self.source/'server.py').write_text('dirty')
        with self.assertRaisesRegex(release.Refusal,'tracked edits'):self.plan()
        self.run_git('restore','server.py');self.commit=self.previous
        with self.assertRaisesRegex(release.Refusal,'HEAD'):self.plan()
        self.no_calls()

    def test_second_installer_cannot_bypass_lock_with_different_backup_root(self):
        lock=self.beta/'.release-install.lock'
        with lock.open('w') as held:
            fcntl.flock(held,fcntl.LOCK_EX|fcntl.LOCK_NB)
            self.backups=self.root/'other-backup'
            with self.assertRaisesRegex(release.Refusal,'Another release'):self.install()
        self.no_calls()

    def test_missing_changed_partial_or_forged_baseline_refuses(self):
        old=(self.dest/'server.py').read_bytes();(self.dest/'server.py').unlink()
        with self.assertRaisesRegex(release.Refusal,'Missing'):self.plan()
        (self.dest/'server.py').write_bytes(old+b'changed')
        with self.assertRaisesRegex(release.Refusal,'hash differs'):self.plan()
        (self.dest/'server.py').write_bytes(old)
        data=json.loads(self.baseline.read_text());data['files'].pop('tests/test_old.py');self.baseline.write_text(json.dumps(data))
        with self.assertRaisesRegex(release.Refusal,'every tracked file'):self.plan()
        data['files']['tests/test_old.py']='0'*64;self.baseline.write_text(json.dumps(data))
        with self.assertRaisesRegex(release.Refusal,'Git checkpoint'):self.plan()
        self.no_calls()

    def test_collision_unexpected_code_and_symlink_refuse(self):
        (self.dest/'webapp').mkdir();(self.dest/'webapp/new.js').write_text('unrelated owner work')
        with self.assertRaisesRegex(release.Refusal,'collides'):self.plan()
        (self.dest/'webapp/new.js').unlink();(self.dest/'scripts/unknown.py').write_text('unrelated')
        with self.assertRaisesRegex(release.Refusal,'Unexpected'):self.plan()
        (self.dest/'scripts/unknown.py').unlink();(self.dest/'scripts/worker.py').unlink();(self.dest/'scripts/worker.py').symlink_to(self.source/'scripts/worker.py')
        with self.assertRaisesRegex(release.Refusal,'Symlink'):self.plan()
        self.no_calls()

    def test_active_and_unrecognized_operation_status_refuse(self):
        for status in ['queued','claimed','running','dispatching','unexpected']:
            with contextlib.closing(sqlite3.connect(self.state/'operations.sqlite3')) as db:
                db.execute('UPDATE operations SET status=?',(status,));db.commit()
            with self.assertRaisesRegex(release.Refusal,'operation status'):self.plan()
        self.no_calls()

    def test_dependencies_and_tracked_removals_require_separate_review(self):
        (self.source/'config/brand.json').write_text('{"new":true}')
        self.commit=self.commit_source('config changed')
        with self.assertRaisesRegex(release.Refusal,'Dependency/configuration'):self.plan()
        self.run_git('restore','--source',self.previous,'config/brand.json');(self.source/'tests/test_old.py').unlink();self.commit=self.commit_source('removed')
        with self.assertRaisesRegex(release.Refusal,'removals'):self.plan()
        self.no_calls()

    def test_success_verifies_full_tree_backs_up_before_stop_and_filters_secrets(self):
        with patch.object(release,'port_closed'),contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(release.main(self.argv()+['--apply']),0)
        self.assertNotIn('secret',out.getvalue()+err.getvalue())
        manifest=json.loads((self.dest/'.open-case-integration.json').read_text())
        self.assertEqual(manifest['source_commit'],self.commit)
        self.assertEqual((self.dest/'.candidate-commit').read_text(),self.commit+'\n')
        self.assertEqual(set(manifest['files']),set(self.run_git('ls-files').splitlines()))
        self.assertNotIn('.candidate-commit',manifest['files'])
        for name,digest in manifest['files'].items():self.assertEqual(hashlib.sha256((self.dest/name).read_bytes()).hexdigest(),digest)
        for p,data in self.private_before.items():self.assertEqual(p.read_bytes(),data)
        self.assertEqual([c['verb'] for c in self.calls()],['stop','open']);self.assertTrue(all(c['backup_exists'] for c in self.calls()))
        backup=Path(manifest['backup']);self.assertEqual(backup.stat().st_mode&0o777,0o700)
        self.assertEqual((backup/'.candidate-commit').read_text(),'stale-marker\n')
        self.assertEqual((backup/'server.py').stat().st_mode&0o777,0o600)
        self.assertFalse((backup/'.env').exists())
        # The generated manifest is itself a complete next baseline.
        follow=release.prepare(self.source,self.commit,self.dest/'.open-case-integration.json',self.cfg,self.backups)
        self.install(follow)
        self.assertEqual([c['verb'] for c in self.calls()],['stop','open','stop','open'])

    def test_regular_file_parent_collision_refuses_before_stop(self):
        (self.dest/'webapp').write_text('owner data, not a directory')
        with self.assertRaisesRegex(release.Refusal,'parent directory'):self.plan()
        self.no_calls()

    def test_marker_changed_during_stop_is_preserved_and_prevents_install(self):
        original=release.managed
        def stop_then_marker(plan,verb):
            original(plan,verb)
            if verb=='stop':(self.dest/'.candidate-commit').write_text('concurrent update')
        with patch.object(release,'managed',side_effect=stop_then_marker):
            with self.assertRaisesRegex(release.Refusal,'Backed-up file changed'):self.install()
        self.assertEqual((self.dest/'.candidate-commit').read_text(),'concurrent update')
        self.assertEqual((self.dest/'server.py').read_text(),'print("old")\n')
        self.assertEqual([c['verb'] for c in self.calls()],['stop'])

    def test_source_or_baseline_change_after_freeze_refuses_before_stop(self):
        plan=self.plan();(self.source/'server.py').write_text('late source change')
        with self.assertRaisesRegex(release.Refusal,'tracked edits'):self.install(plan)
        self.no_calls()
        self.run_git('restore','server.py');plan=self.plan();self.baseline.write_text('{}')
        with self.assertRaisesRegex(release.Refusal,'deployment input changed'):self.install(plan)
        self.no_calls()

    def test_stop_failure_never_installs_or_prints_launcher_credentials(self):
        (self.beta/'fail-stop').touch()
        with patch.object(release,'port_closed'),contextlib.redirect_stdout(io.StringIO()) as out,contextlib.redirect_stderr(io.StringIO()) as err:
            self.assertEqual(release.main(self.argv()+['--apply']),2)
        self.assertNotIn('secret',out.getvalue()+err.getvalue());self.assertIn('Managed stop failed',err.getvalue())
        self.assertEqual((self.dest/'server.py').read_text(),'print("old")\n')
        self.assertEqual([c['verb'] for c in self.calls()],['stop'])

    def test_failed_install_restores_changed_files_and_markers(self):
        original=release.atomic
        def fail(path,data,mode):
            original(path,data,mode)
            if path==self.dest/'webapp/new.js':raise OSError('fixture disk verification failure after replace')
        with patch.object(release,'atomic',side_effect=fail):
            with self.assertRaisesRegex(OSError,'fixture'):self.install()
        self.assertEqual((self.dest/'server.py').read_text(),'print("old")\n')
        self.assertFalse((self.dest/'webapp/new.js').exists())
        self.assertEqual((self.dest/'.candidate-commit').read_text(),'stale-marker\n')
        self.assertEqual([c['verb'] for c in self.calls()],['stop'])

    def test_port_still_busy_after_stop_refuses_install(self):
        with patch.object(release,'port_closed',side_effect=release.Refusal('still listening')):
            with self.assertRaisesRegex(release.Refusal,'listening'):release.apply(self.plan())
        self.assertEqual((self.dest/'server.py').read_text(),'print("old")\n')
        self.assertEqual([c['verb'] for c in self.calls()],['stop'])

    def test_start_failure_retains_verified_release_and_backup_without_success_claim(self):
        (self.beta/'fail-open').touch()
        with self.assertRaisesRegex(release.Refusal,'Managed open failed'):self.install()
        self.assertEqual((self.dest/'.candidate-commit').read_text().strip(),self.commit)
        self.assertEqual(json.loads((self.dest/'.open-case-integration.json').read_text())['source_commit'],self.commit)
        self.assertEqual([c['verb'] for c in self.calls()],['stop','open'])


if __name__=='__main__':unittest.main()
