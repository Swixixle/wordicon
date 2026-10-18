"""Code manifest behavior against disposable Git repos/bundles; no owner data."""
import copy
import hashlib
import importlib.util
import json
import os
from pathlib import Path
import subprocess
import sys
import tempfile
import unittest
from unittest.mock import patch

SCRIPT=Path(__file__).resolve().parents[1]/'scripts/code_manifest.py'
spec=importlib.util.spec_from_file_location('code_manifest',SCRIPT)
manifest=importlib.util.module_from_spec(spec);spec.loader.exec_module(manifest)


class ManifestTests(unittest.TestCase):
    def setUp(self):
        self.temp=tempfile.TemporaryDirectory(prefix='nk-code-manifest-')
        self.root=Path(self.temp.name);self.repo=self.root/'source';self.repo.mkdir()
        self.git('init','-q')
        (self.repo/'.gitignore').write_text('local_state/\n')
        (self.repo/'program.txt').write_text('Committed source\n')
        (self.repo/'sub').mkdir();(self.repo/'sub'/'spaced ü file.txt').write_bytes(b'\x00binary\xff')
        self.outside=self.root/'excluded.txt';self.outside.write_text('UNTRACKED PRIVATE MATERIAL')
        (self.repo/'pointer').symlink_to(self.outside)
        (self.repo/'local_state').mkdir();(self.repo/'local_state'/'private.txt').write_text('OWNER MATERIAL MUST STAY OUT')
        self.git('add','.gitignore','program.txt','sub','pointer');self.commit=self.commit_all()

    def tearDown(self):self.temp.cleanup()

    def git(self,*args,cwd=None):
        r=subprocess.run(['git','-C',str(cwd or self.repo),*args],capture_output=True,text=True,check=True)
        return r.stdout.strip()

    def commit_all(self):
        self.git('-c','user.name=Fixture','-c','user.email=fixture@example.invalid','commit','-qm','Scrubbed fixture')
        return self.git('rev-parse','HEAD')

    def test_deterministic_commit_manifest_excludes_untracked_and_hashes_link_not_target(self):
        first=manifest.generate(self.repo);second=manifest.generate(self.repo,self.commit)
        self.assertEqual(first,second);self.assertEqual(first['commit'],self.commit)
        self.assertEqual(first['file_count'],4)
        paths={f['path']:f for f in first['files']}
        self.assertNotIn('local_state/private.txt',paths)
        self.assertEqual(paths['pointer']['sha256'],hashlib.sha256(os.fsencode(str(self.outside))).hexdigest())
        self.outside.write_text('UNTRACKED CHANGED')
        self.assertEqual(manifest.generate(self.repo),first)
        self.assertTrue(manifest.verify(self.repo,first,working_tree=True)['ok'])

    def test_dirty_file_does_not_change_committed_manifest_but_checkout_verification_fails(self):
        original=manifest.generate(self.repo)
        (self.repo/'program.txt').write_text('Uncommitted difference')
        self.assertEqual(original,manifest.generate(self.repo))
        self.assertTrue(manifest.verify(self.repo,original)['ok'])
        with self.assertRaisesRegex(manifest.ManifestError,'Checkout bytes differ: program.txt'):
            manifest.verify(self.repo,original,working_tree=True)

    def test_missing_extra_forged_and_traversal_entries_are_refused(self):
        original=manifest.generate(self.repo)
        changed=[]
        x=copy.deepcopy(original);x['files'].pop();changed.append(x)
        x=copy.deepcopy(original);x['files'][0]['sha256']='0'*64;changed.append(x)
        x=copy.deepcopy(original);x['files'].append({**x['files'][0],'path':'../excluded.txt'});changed.append(x)
        x=copy.deepcopy(original);x['file_count']+=1;changed.append(x)
        for candidate in changed:
            with self.subTest(candidate=candidate['file_count']),self.assertRaises(manifest.ManifestError):manifest.verify(self.repo,candidate,working_tree=True)

    def test_symlink_parent_escape_is_refused_before_opening_target(self):
        original=manifest.generate(self.repo)
        (self.repo/'sub').rename(self.root/'moved');(self.repo/'sub').symlink_to(self.root/'moved',target_is_directory=True)
        with self.assertRaisesRegex(manifest.ManifestError,'parent is not a real directory'):
            manifest.verify(self.repo,original,working_tree=True)

    def test_regular_file_replaced_by_symlink_is_not_followed(self):
        original=manifest.generate(self.repo)
        (self.repo/'program.txt').unlink();(self.repo/'program.txt').symlink_to(self.outside)
        with self.assertRaisesRegex(manifest.ManifestError,'Expected a regular file'):
            manifest.verify(self.repo,original,working_tree=True)

    @unittest.skipIf(os.name=='nt','POSIX executable mode check')
    def test_executable_mode_is_checked_separately_from_bytes(self):
        original=manifest.generate(self.repo);(self.repo/'program.txt').chmod(0o755)
        with self.assertRaisesRegex(manifest.ManifestError,'Executable mode differs'):
            manifest.verify(self.repo,original,working_tree=True)

    def test_bundle_clone_reproduces_exact_commit_and_manifest_through_cli(self):
        ancestor=self.commit
        (self.repo/'later.txt').write_text('Later committed source');self.git('add','later.txt');self.commit=self.commit_all()
        original=manifest.generate(self.repo);bundle=self.root/'source.bundle';clone=self.root/'replica'
        self.git('bundle','create',str(bundle),'--all')
        subprocess.run(['git','clone','-q',str(bundle),str(clone)],check=True,capture_output=True)
        self.git('checkout','--detach',self.commit,cwd=clone)
        self.git('merge-base','--is-ancestor',ancestor,self.commit,cwd=clone)
        self.assertEqual(manifest.generate(clone),original)
        checkpoint=self.root/'code.json';checkpoint.write_text(json.dumps(original))
        result=subprocess.run([sys.executable,str(SCRIPT),'verify','--repo',str(clone),'--manifest',str(checkpoint),'--working-tree'],capture_output=True,text=True)
        self.assertEqual(result.returncode,0,result.stderr)
        self.assertEqual(json.loads(result.stdout)['commit'],self.commit)
        self.assertFalse((clone/'local_state').exists())

    def test_checkout_of_another_commit_is_not_same_checkpoint(self):
        original=manifest.generate(self.repo)
        (self.repo/'new.txt').write_text('new source');self.git('add','new.txt');self.commit_all()
        self.assertTrue(manifest.verify(self.repo,original)['ok'])
        with self.assertRaisesRegex(manifest.ManifestError,'HEAD differs'):
            manifest.verify(self.repo,original,working_tree=True)

    def test_submodules_are_explicitly_outside_full_blob_coverage(self):
        self.git('update-index','--add','--cacheinfo','160000,'+self.commit+',embedded')
        self.commit_all()
        with self.assertRaisesRegex(manifest.ManifestError,'Submodules.*separate manifest'):
            manifest.generate(self.repo)

if __name__=='__main__':unittest.main()
