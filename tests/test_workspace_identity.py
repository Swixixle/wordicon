"""Store identity survives relocation and refuses silent replacement."""
from concurrent.futures import ThreadPoolExecutor
import hashlib
from pathlib import Path
import shutil
import sys
import tempfile
import unittest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))
import workspace_identity as identity


class WorkspaceIdentityTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name) / "state"

    def tearDown(self):
        self.temp.cleanup()

    def test_read_missing_creates_nothing(self):
        with self.assertRaises(identity.IdentityError):
            identity.read(self.root)
        self.assertFalse(self.root.exists())

    def test_concurrent_bootstrap_retains_one_identity(self):
        with ThreadPoolExecutor(max_workers=6) as pool:
            rows = list(pool.map(lambda _: identity.ensure(self.root), range(12)))
        self.assertTrue(all(row == rows[0] for row in rows))
        self.assertEqual((self.root / identity.NAME).stat().st_mode & 0o777, 0o600)

    def test_restore_or_move_keeps_identity_and_exact_bytes(self):
        first = identity.ensure(self.root)
        original = (self.root / identity.NAME).read_bytes()
        moved = self.root.parent / "restored"
        shutil.copytree(self.root, moved)
        self.assertEqual(identity.ensure(moved), first)
        self.assertEqual((moved / identity.NAME).read_bytes(), original)

    def test_new_store_at_same_path_gets_distinct_identity_and_scope(self):
        first = identity.ensure(self.root)
        self.root.rename(self.root.parent / "old")
        new = identity.ensure(self.root)
        self.assertNotEqual(first["workspace_id"], new["workspace_id"])
        self.assertNotEqual(first["attention_scope_id"], new["attention_scope_id"])

    def test_corruption_is_preserved_not_replaced(self):
        identity.ensure(self.root)
        path = self.root / identity.NAME
        path.write_bytes(b'{"incomplete')
        with self.assertRaises(identity.IdentityError):
            identity.ensure(self.root)
        self.assertEqual(path.read_bytes(), b'{"incomplete')

    def test_explicit_legacy_scope_migration_keeps_pending_route(self):
        self.root.mkdir()
        old = self.root / "ledger" / "events-2026-10.jsonl"
        old.parent.mkdir(); old.write_bytes(b'{"legacy":"original"}\n')
        row = identity.ensure(self.root, migrate_legacy_scope=True)
        expected = "ledger_" + hashlib.sha256(str(self.root.resolve()).encode()).hexdigest()[:24]
        self.assertEqual(row["attention_scope_id"], expected)
        self.assertTrue(row["legacy_attention_scope_preserved"])
        self.assertEqual(old.read_bytes(), b'{"legacy":"original"}\n')
        self.assertEqual(identity.ensure(self.root), row)


if __name__ == "__main__":
    unittest.main()
