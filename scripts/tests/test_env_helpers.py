from __future__ import annotations

import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
HELPER = Path('.agents/skills/owh-env-contracts/scripts/local-env-files.sh')


class EnvHelperTest(unittest.TestCase):
    def setUp(self):
        self.temporary = tempfile.TemporaryDirectory(prefix='owh-env-helper-')
        self.addCleanup(self.temporary.cleanup)
        self.root = Path(self.temporary.name)
        (self.root / HELPER).parent.mkdir(parents=True)
        shutil.copyfile(ROOT / HELPER, self.root / HELPER)
        subprocess.run(['git', 'init', '-q'], cwd=self.root, check=True)
        (self.root / '.env.example').write_text('OPEN_WORK_HUB_NEW=example-value\n')
        (self.root / '.env').write_text('OPEN_WORK_HUB_EXISTING=synthetic-private-value\n')

    def run_helper(self, mode, *extra):
        return subprocess.run(['bash', str(self.root / HELPER), mode, '--source', '.env.example', '--target', '.env', *extra], cwd=self.root, text=True, capture_output=True, timeout=10)

    def test_status_and_dry_run_never_expose_values_or_change_target(self):
        original = (self.root / '.env').read_bytes()
        result = self.run_helper('status')
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('OPEN_WORK_HUB_NEW', result.stdout)
        self.assertIn('target_mode=', result.stdout)
        self.assertNotIn('synthetic-private-value', result.stdout + result.stderr)
        self.assertNotIn('example-value', result.stdout + result.stderr)
        self.assertEqual((self.root / '.env').read_bytes(), original)
        self.assertNotEqual(self.run_helper('install', '--dry-run').returncode, 0)
        self.assertEqual((self.root / '.env').read_bytes(), original)

    def test_install_preserves_existing_values_unless_explicit_force_and_makes_private_backup(self):
        original = (self.root / '.env').read_bytes()
        self.assertNotEqual(self.run_helper('install').returncode, 0)
        result = self.run_helper('install', '--force')
        self.assertEqual(result.returncode, 0, result.stderr)
        backups = list(self.root.glob('.env.backup-*'))
        self.assertEqual(len(backups), 1)
        self.assertEqual(backups[0].read_bytes(), original)
        self.assertEqual(backups[0].stat().st_mode & 0o777, 0o600)
        self.assertEqual((self.root / '.env').stat().st_mode & 0o777, 0o600)

    def test_tracked_targets_and_symlinks_are_refused(self):
        subprocess.run(['git', 'add', '.env'], cwd=self.root, check=True)
        self.assertNotEqual(self.run_helper('install', '--force').returncode, 0)
        (self.root / '.env').unlink()
        (self.root / '.env').symlink_to(self.root / '.env.example')
        self.assertNotEqual(self.run_helper('install', '--force').returncode, 0)

    def test_reproduction_template_requires_task_configuration_and_has_safe_help(self):
        script = ROOT / '.agents/skills/diagnose/scripts/hitl-loop.template.sh'
        plain = subprocess.run(['bash', str(script)], text=True, capture_output=True, timeout=5)
        self.assertEqual(plain.returncode, 2)
        help_result = subprocess.run(['bash', str(script), '--help'], text=True, capture_output=True, timeout=5)
        self.assertEqual(help_result.returncode, 0)


if __name__ == '__main__':
    unittest.main()
