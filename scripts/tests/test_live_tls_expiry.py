from __future__ import annotations

import io
import subprocess
import unittest
from contextlib import redirect_stderr
from datetime import UTC, datetime
from pathlib import Path

from scripts import check_live_tls_expiry


ROOT = Path(__file__).resolve().parents[2]


class LiveTlsExpiryTest(unittest.TestCase):
    @staticmethod
    def open-alm_certificate(*, expires_at: str = "Sep  6 03:15:57 2026 GMT") -> dict:
        return {
            "notAfter": expires_at,
            "subjectAltName": (
                ("DNS", "*.open-alm.example"),
                ("DNS", "open-alm.example"),
            ),
        }

    def test_valid_certificate_above_threshold_passes(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = check_live_tls_expiry.run(
            [],
            certificate_fetcher=lambda *_args: self.open-alm_certificate(),
            now=lambda: datetime(2026, 7, 23, tzinfo=UTC),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertIn('"status": "ok"', stdout.getvalue())
        self.assertIn('"host": "open-alm.example"', stdout.getvalue())
        self.assertIn('"expires_at": "2026-09-06T03:15:57Z"', stdout.getvalue())
        self.assertEqual(stderr.getvalue(), "")

    def test_certificate_at_thirty_day_boundary_fails_closed(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = check_live_tls_expiry.run(
            [],
            certificate_fetcher=lambda *_args: self.open-alm_certificate(),
            now=lambda: datetime(2026, 8, 7, 3, 15, 57, tzinfo=UTC),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn('"status": "failed"', stderr.getvalue())
        self.assertIn('"reason": "certificate_expiring"', stderr.getvalue())

    def test_zero_day_threshold_accepts_a_certificate_that_is_still_valid(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = check_live_tls_expiry.run(
            ["--threshold-days=0"],
            certificate_fetcher=lambda *_args: self.open-alm_certificate(),
            now=lambda: datetime(2026, 9, 6, 3, 15, 56, tzinfo=UTC),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 0, stderr.getvalue())
        self.assertIn('"threshold_days": 0', stdout.getvalue())
        self.assertIn('"remaining_seconds": 1', stdout.getvalue())

    def test_zero_day_threshold_still_rejects_actual_expiry(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = check_live_tls_expiry.run(
            ["--threshold-days=0"],
            certificate_fetcher=lambda *_args: self.open-alm_certificate(),
            now=lambda: datetime(2026, 9, 6, 3, 15, 57, tzinfo=UTC),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn('"reason": "certificate_expiring"', stderr.getvalue())
        self.assertIn('"threshold_days": 0', stderr.getvalue())

    def test_missing_required_wildcard_san_fails_closed(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()
        certificate = self.open-alm_certificate()
        certificate["subjectAltName"] = (("DNS", "open-alm.example"),)

        exit_code = check_live_tls_expiry.run(
            ["--threshold-days=0"],
            certificate_fetcher=lambda *_args: certificate,
            now=lambda: datetime(2026, 7, 23, tzinfo=UTC),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn('"reason": "required_san_missing"', stderr.getvalue())
        self.assertIn('"missing_sans": ["*.open-alm.example"]', stderr.getvalue())

    def test_tls_connection_failure_is_fail_closed_and_secret_free(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        def unavailable(*_args: object) -> dict:
            raise RuntimeError("upstream rejected token=SENSITIVE")

        exit_code = check_live_tls_expiry.run(
            [],
            certificate_fetcher=unavailable,
            now=lambda: datetime(2026, 7, 23, tzinfo=UTC),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn('"reason": "tls_connection_failed"', stderr.getvalue())
        self.assertNotIn("SENSITIVE", stderr.getvalue())

    def test_unparseable_certificate_is_fail_closed(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = check_live_tls_expiry.run(
            [],
            certificate_fetcher=lambda *_args: {"subjectAltName": ()},
            now=lambda: datetime(2026, 7, 23, tzinfo=UTC),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertEqual(stdout.getvalue(), "")
        self.assertIn('"reason": "certificate_invalid"', stderr.getvalue())

    def test_explicit_clock_makes_boundary_check_deterministic(self) -> None:
        stdout = io.StringIO()
        stderr = io.StringIO()

        exit_code = check_live_tls_expiry.run(
            ["--now", "2026-08-07T03:15:57Z"],
            certificate_fetcher=lambda *_args: self.open-alm_certificate(),
            now=lambda: self.fail("system clock must not be read"),
            stdout=stdout,
            stderr=stderr,
        )

        self.assertEqual(exit_code, 1)
        self.assertIn('"checked_at": "2026-08-07T03:15:57Z"', stderr.getvalue())

    def test_negative_threshold_is_rejected_before_network_access(self) -> None:
        fetched = False

        def must_not_fetch(*_args: object) -> dict:
            nonlocal fetched
            fetched = True
            return self.open-alm_certificate()

        with redirect_stderr(io.StringIO()):
            with self.assertRaises(SystemExit) as raised:
                check_live_tls_expiry.run(
                    ["--threshold-days=-1"],
                    certificate_fetcher=must_not_fetch,
                )

        self.assertEqual(raised.exception.code, 2)
        self.assertFalse(fetched)

    def test_systemd_timer_runs_the_fail_closed_check_daily(self) -> None:
        service = (
            ROOT / "ops/systemd/system/open-alm-tls-expiry-check.service"
        ).read_text(encoding="utf-8")
        timer = (
            ROOT / "ops/systemd/system/open-alm-tls-expiry-check.timer"
        ).read_text(encoding="utf-8")

        self.assertIn(
            "ExecStart=/usr/bin/python3 /usr/local/libexec/open-alm/check_live_tls_expiry.py",
            service,
        )
        self.assertIn("--threshold-days=30", service)
        self.assertIn("--required-san=open-alm.example", service)
        self.assertIn("--required-san=*.open-alm.example", service)
        self.assertIn("TimeoutStartSec=30s", service)
        self.assertIn("UMask=0077", service)
        self.assertIn("OnCalendar=daily", timer)
        self.assertIn("Persistent=true", timer)

    def test_monitor_installer_is_non_mutating_without_apply(self) -> None:
        result = subprocess.run(
            ["bash", str(ROOT / "ops/systemd/install-tls-expiry-monitor.sh")],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("dry-run", result.stdout)
        self.assertIn("--apply", result.stdout)
        self.assertIn("open-alm-tls-expiry-check.timer", result.stdout)

    def test_monitor_installer_rejects_replace_without_apply(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(ROOT / "ops/systemd/install-tls-expiry-monitor.sh"),
                "--replace",
            ],
            cwd=ROOT,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

        self.assertEqual(result.returncode, 2)
        self.assertIn("--replace requires --apply", result.stderr)


if __name__ == "__main__":
    unittest.main()
