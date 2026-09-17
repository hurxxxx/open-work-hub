import importlib.util
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SPEC = importlib.util.spec_from_file_location(
    "runtime_config_migrate", ROOT / "scripts/runtime-config-migrate.py"
)
migration = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(migration)
KEY = "OPEN_WORK_HUB_WORKER_DB_POOL_SIZE"


class MigrationTest(unittest.TestCase):
    def test_duplicate_keys_and_multiline_changes_are_rejected(self):
        with self.assertRaises(ValueError):
            migration.prune_defaults(f"{KEY}=2\n{KEY}=1\n", {KEY: 1})
        with self.assertRaises(ValueError):
            migration.prune_defaults(f'PRIVATE="first\n{KEY}=1\nlast"\n', {KEY: 1})

    def test_interpolation_dependencies_are_preserved(self):
        text = f"{KEY}=1\nOTHER=${{{KEY}}}\n"
        self.assertEqual(migration.prune_defaults(text, {KEY: 1}), (text, ()))

    def test_only_equal_defaults_are_removed(self):
        text = f"# preserve\n{KEY}=1\nOPEN_WORK_HUB_SECRET='private'\nOTHER=2\n"
        migrated, keys = migration.prune_defaults(text, {KEY: 1})
        self.assertEqual(
            migrated, "# preserve\nOPEN_WORK_HUB_SECRET='private'\nOTHER=2\n"
        )
        self.assertEqual(keys, (KEY,))
        self.assertEqual(
            migration.prune_defaults(f"{KEY}=2\n", {KEY: 1}), (f"{KEY}=2\n", ())
        )

    def test_private_backup_dry_run_and_unchanged_overrides(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            (root / ".gitignore").write_text(".env*\n")
            shutil.copytree(ROOT / "config", root / "config")
            env = root / ".env"
            original = f"{KEY}=1\nOPEN_WORK_HUB_SECRET=private\n"
            env.write_text(original)
            env.chmod(0o600)
            self.assertEqual(migration.migrate(root, ".env", apply=False), (KEY,))
            self.assertEqual(env.read_text(), original)
            self.assertEqual(migration.migrate(root, ".env", apply=True), (KEY,))
            self.assertEqual(env.read_text(), "OPEN_WORK_HUB_SECRET=private\n")
            self.assertEqual(env.stat().st_mode & 0o777, 0o600)
            backups = list(root.glob(".env.backup-config-*"))
            self.assertEqual(len(backups), 1)
            self.assertEqual(backups[0].read_text(), original)
            self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
            self.assertEqual(migration.migrate(root, ".env", apply=True), ())

    def test_tracked_symlink_and_missing_config_are_rejected(self):
        with tempfile.TemporaryDirectory() as folder:
            root = Path(folder)
            subprocess.run(["git", "init", "-q", str(root)], check=True)
            env = root / ".env"
            env.write_text(f"{KEY}=1\n")
            env.chmod(0o600)
            with self.assertRaises(ValueError):
                migration.migrate(root, ".env", apply=True)
            (root / ".gitignore").write_text(".env*\n")
            with self.assertRaises(ValueError):
                migration.migrate(root, ".env", apply=True)
            env.unlink()
            env.symlink_to(root / ".gitignore")
            with self.assertRaises(ValueError):
                migration.migrate(root, ".env", apply=True)
