from __future__ import annotations

import importlib.util
import os
import subprocess
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

SCRIPT = Path(__file__).resolve().parents[2] / '.agents/skills/owh-docs-reader/scripts/read_open_work_hub_doc.py'
SPEC = importlib.util.spec_from_file_location('docs_reader', SCRIPT)
reader = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(reader)
MEDIA_ID = '12345678-1234-1234-1234-123456789012'


class DocsReaderTest(unittest.TestCase):
    def setUp(self):
        self.environment = patch.dict(os.environ, {}, clear=True)
        self.environment.start()
        self.files = patch.object(reader, 'file_env', return_value={})
        self.files.start()
        self.addCleanup(self.environment.stop)
        self.addCleanup(self.files.stop)

    def test_dev_defaults_and_non_dev_preflight(self):
        self.assertEqual(reader.local_config()['pg_db'], 'open_work_hub_dev')
        for values in [
            {'OPEN_WORK_HUB_ENV_PROFILE': 'prod'},
            {'OPEN_WORK_HUB_INFRA_CONTAINER_PREFIX': 'open-work-hub-prod'},
            {'OPEN_WORK_HUB_INFRA_POSTGRES_DB': 'open_work_hub'},
            {'OPEN_WORK_HUB_POSTGRES_DSN': 'postgresql://u:p@db.invalid:55433/open_work_hub_dev'},
            {'OPEN_WORK_HUB_POSTGRES_DSN': 'postgresql://u:p@127.0.0.1:55432/open_work_hub_dev'},
            {'OPEN_WORK_HUB_POSTGRES_DSN': 'postgresql://u:p@127.0.0.1:55433/open_work_hub_dev?host=remote'},
            {'OPEN_WORK_HUB_MINIO_BUCKET': 'open-work-hub-prod'},
        ]:
            with self.subTest(values=list(values)), patch.dict(os.environ, values), patch.object(reader, 'run') as run:
                with self.assertRaises(RuntimeError):
                    reader.psql_command()
                run.assert_not_called()

    def test_readonly_psql_and_container_identity(self):
        with patch.object(reader, 'container_running', return_value=True):
            command, _, _ = reader.psql_command()
            self.assertIn('PGOPTIONS=-c default_transaction_read_only=on -c statement_timeout=20000', command)
        with patch.object(reader.shutil, 'which', return_value='/usr/bin/docker'), patch.object(reader, 'run', return_value=subprocess.CompletedProcess([], 0, 'true|open-work-hub-prod\n', '')):
            with self.assertRaisesRegex(RuntimeError, 'dev Compose identity'):
                reader.container_running('open-work-hub-dev-postgres')

    def test_host_psql_is_readonly_and_uses_connect_timeout(self):
        with patch.object(reader, 'container_running', return_value=False), patch.object(reader.shutil, 'which', return_value='/usr/bin/psql'):
            command, env, _ = reader.psql_command()
        self.assertEqual(command[0], 'psql')
        self.assertIn('default_transaction_read_only=on', env['PGOPTIONS'])
        self.assertEqual(env['PGCONNECT_TIMEOUT'], '5')

    def test_process_timeouts_and_error_redaction(self):
        with patch.object(reader.subprocess, 'run', return_value=subprocess.CompletedProcess([], 1, '', 'synthetic-password')) as run:
            with self.assertRaises(RuntimeError) as failure:
                reader.run(['psql', 'synthetic-password'])
            self.assertNotIn('synthetic-password', str(failure.exception))
            self.assertEqual(run.call_args.kwargs['timeout'], 30)
        with patch.object(reader.subprocess, 'run', side_effect=subprocess.TimeoutExpired('secret', 30)):
            with self.assertRaisesRegex(RuntimeError, 'timed out'):
                reader.run(['psql'])

    def test_media_limits_and_no_clobber(self):
        media = {'id': MEDIA_ID, 'filename': 'image.bin', 'storage_key': 'workspace/object', 'size_bytes': 1}
        with tempfile.TemporaryDirectory() as output, patch.object(reader, 'container_running', return_value=True), patch.object(reader, 'run') as run:
            with self.assertRaisesRegex(ValueError, '50 MiB'):
                reader.copy_media([{**media, 'size_bytes': reader.MAX_MEDIA_BYTES + 1}], Path(output))
            target = Path(output) / f'local-{MEDIA_ID}-image.bin'
            target.write_bytes(b'original')
            with self.assertRaisesRegex(ValueError, 'already exists'):
                reader.copy_media([media], Path(output))
            self.assertEqual(target.read_bytes(), b'original')
            run.assert_not_called()

    def test_media_failure_cleans_validated_container_temp(self):
        commands = []
        def mock_run(command, **kwargs):
            commands.append(command)
            if 'mktemp' in command:
                return subprocess.CompletedProcess(command, 0, '/tmp/owh-doc-media.ABC12345\n', '')
            if '/bin/sh' in command:
                raise RuntimeError('copy failed')
            return subprocess.CompletedProcess(command, 0, '', '')
        with tempfile.TemporaryDirectory() as output, patch.object(reader, 'container_running', return_value=True), patch.object(reader, 'run', side_effect=mock_run):
            with self.assertRaisesRegex(RuntimeError, 'copy failed'):
                reader.copy_media([{'id': MEDIA_ID, 'filename': 'x', 'storage_key': 'object', 'size_bytes': 1}], Path(output))
            self.assertEqual(list(Path(output).iterdir()), [])
        self.assertEqual(commands[-1][-4:], ['rm', '-rf', '--', '/tmp/owh-doc-media.ABC12345'])
        self.assertIn('--config-dir', commands[1][-1])

    def test_help_is_service_and_env_free(self):
        with patch.object(reader, 'env_file_values', side_effect=AssertionError('must not read env')), patch.object(reader, 'run', side_effect=AssertionError('must not query')):
            parser = reader.build_parser()
            self.assertIn('--copy-media', parser.format_help())


if __name__ == '__main__':
    unittest.main()
