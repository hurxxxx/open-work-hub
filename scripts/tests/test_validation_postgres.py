from contextlib import redirect_stderr
import importlib.util
import io
from pathlib import Path
import subprocess
import tempfile
from types import SimpleNamespace
import unittest
from unittest.mock import MagicMock, patch


SCRIPT = Path(__file__).resolve().parents[1] / "ci" / "check-validation-postgres.py"
SPEC = importlib.util.spec_from_file_location("validation_postgres", SCRIPT)
assert SPEC and SPEC.loader
MODULE = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MODULE)


class ValidationPostgresTest(unittest.TestCase):
    def setUp(self):
        self.scratch = tempfile.TemporaryDirectory()
        self.addCleanup(self.scratch.cleanup)
        self.major_file = Path(self.scratch.name) / "postgres-major"
        self.major_file.write_text("18\n")
        self.connection = MagicMock()
        self.connection.info.server_version = 180006
        self.connect = MagicMock()
        self.connect.return_value.__enter__.return_value = self.connection
        self.driver = patch.dict("sys.modules", {"psycopg": SimpleNamespace(connect=self.connect)})
        self.driver.start()
        self.addCleanup(self.driver.stop)

    def tools(self, major=18):
        return patch.object(MODULE.subprocess, "run", side_effect=lambda argv, **_: subprocess.CompletedProcess(
            argv, 0, stdout=f"{argv[0]} (PostgreSQL) {major}.6\n"
        ))

    def test_matching_majors_and_patch_differences(self):
        for major in (17, 18):
            with self.subTest(major=major), self.tools(major):
                self.major_file.write_text(str(major))
                self.connection.info.server_version = major * 10000 + 1
                self.assertEqual(MODULE.check_postgres(self.major_file, "postgresql+psycopg://test"), major)
                self.connect.assert_called_with("postgresql://test", connect_timeout=10)
                self.connection.execute.assert_not_called()

    def test_mismatched_server_is_rejected(self):
        self.connection.info.server_version = 170011
        with self.tools(), self.assertRaisesRegex(MODULE.ValidationError, "server is 17.*clients are 18"):
            MODULE.check_postgres(self.major_file, "postgresql://test")

    def test_mismatched_clients_are_rejected_before_connecting(self):
        for bad_tool in ("pg_dump", "pg_restore", "psql"):
            def version(argv, **_):
                major = 17 if argv[0] == bad_tool else 18
                return subprocess.CompletedProcess(argv, 0, stdout=f"{argv[0]} (PostgreSQL) {major}.6\n")

            with self.subTest(tool=bad_tool), patch.object(MODULE.subprocess, "run", side_effect=version), \
                    self.assertRaisesRegex(MODULE.ValidationError, f"{bad_tool} does not match"):
                MODULE.check_postgres(self.major_file, "postgresql://test")
        self.connect.assert_not_called()

    def test_missing_identity_and_dsn_fail_closed(self):
        for identity, dsn in ((None, "postgresql://test"), ("invalid", "postgresql://test"), ("18", "")):
            if identity is None:
                self.major_file.unlink()
            else:
                self.major_file.write_text(identity)
            with self.assertRaises(MODULE.ValidationError):
                MODULE.check_postgres(self.major_file, dsn)
        self.connect.assert_not_called()

    def test_connection_errors_do_not_expose_dsn_or_password(self):
        secret = "synthetic-secret-must-not-appear"
        self.connect.side_effect = RuntimeError(f"connection failed: postgresql://user:{secret}@private/db")
        stderr = io.StringIO()
        with self.tools(), patch.dict(MODULE.os.environ, {"OPEN_WORK_HUB_CI_POSTGRES_DSN": f"postgresql://{secret}"}), \
                patch.object(MODULE.sys, "argv", [str(SCRIPT), "--major-file", str(self.major_file)]), \
                redirect_stderr(stderr):
            self.assertEqual(MODULE.main(), 2)
        self.assertIn("Connection details are omitted", stderr.getvalue())
        self.assertNotIn(secret, stderr.getvalue())
        self.assertNotIn("private", stderr.getvalue())


if __name__ == "__main__":
    unittest.main()
