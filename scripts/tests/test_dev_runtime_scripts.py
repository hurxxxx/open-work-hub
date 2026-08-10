from __future__ import annotations

import os
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DEV_SMOKE = ROOT / "scripts" / "dev-smoke.sh"
DEV_SYSTEMD = ROOT / "scripts" / "dev-systemd.sh"


class DevRuntimeScriptsTest(unittest.TestCase):
    def run_bash(self, script: str) -> subprocess.CompletedProcess[str]:
        return subprocess.run(
            ["bash", "-c", script],
            cwd=ROOT,
            check=False,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env={**os.environ, "OPEN_ALM_SKIP_DOTENV": "1"},
        )

    def test_unmanaged_local_smoke_skips_managed_checks(self) -> None:
        script = f"""
set -euo pipefail
source {shlex.quote(str(DEV_SMOKE))}
systemctl() {{ return 3; }}
OPEN_ALM_DEV_MANAGED_RUNTIME_CHECK=auto
if dev_managed_runtime_check_enabled; then
  exit 9
else
  status=$?
fi
[[ "$status" == "1" ]]
OPEN_ALM_DEV_MANAGED_RUNTIME_CHECK=0
if dev_managed_runtime_check_enabled; then
  exit 10
else
  status=$?
fi
[[ "$status" == "1" ]]
OPEN_ALM_DEV_MANAGED_RUNTIME_CHECK=1
dev_managed_runtime_check_enabled
"""
        result = self.run_bash(script)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_invalid_managed_smoke_mode_fails_closed(self) -> None:
        script = f"""
set -euo pipefail
source {shlex.quote(str(DEV_SMOKE))}
OPEN_ALM_DEV_MANAGED_RUNTIME_CHECK=invalid
if dev_managed_runtime_check_enabled; then
  exit 9
else
  status=$?
fi
[[ "$status" == "2" ]]
"""
        result = self.run_bash(script)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("must be auto, 1, or 0", result.stderr)

    def test_dev_systemd_renders_revisioned_dedicated_patent_worker(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            systemctl_log = temp / "systemctl.log"
            systemctl = bin_dir / "systemctl"
            systemctl.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'systemctl %s\\n' \"$*\" >> {shlex.quote(str(systemctl_log))}\n"
                'if [[ "$*" == *" is-active "* ]]; then exit 3; fi\n',
                encoding="utf-8",
            )
            systemctl.chmod(0o755)
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'uv %s\\n' \"$*\" >> {shlex.quote(str(systemctl_log))}\n",
                encoding="utf-8",
            )
            uv.chmod(0o755)
            env = {
                **os.environ,
                "HOME": str(temp),
                "XDG_CONFIG_HOME": str(temp / "config"),
                "PATH": f"{bin_dir}:{os.environ['PATH']}",
            }

            for command in ("start", "restart"):
                with self.subTest(command=command):
                    result = subprocess.run(
                        ["bash", str(DEV_SYSTEMD), command],
                        cwd=ROOT,
                        check=False,
                        text=True,
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        env=env,
                    )
                    self.assertEqual(result.returncode, 0, result.stderr)
            revision = subprocess.run(
                ["git", "-C", str(ROOT), "rev-parse", "HEAD"],
                check=True,
                text=True,
                stdout=subprocess.PIPE,
            ).stdout.strip()
            unit_dir = temp / "config" / "systemd" / "user"
            patent = (unit_dir / "open-alm-dev-worker-patent.service").read_text(
                encoding="utf-8"
            )
            self.assertIn("Environment=OPEN_ALM_WORKER_QUEUE_GROUP=patent", patent)
            self.assertIn(f"Environment=OPEN_ALM_RUNTIME_REVISION={revision}", patent)
            self.assertIn("-Q patent_prior_art_server_v1", patent)
            self.assertIn("--concurrency 1", patent)
            self.assertIn("PartOf=open-alm-dev-app.service", patent)
            self.assertIn(
                f"ExecCondition=/usr/bin/test -f {ROOT}/ops/systemd/user/"
                "open-alm-dev-worker-patent.service.template",
                patent,
            )
            self.assertNotIn("__OPEN_ALM_", patent)

            revisioned_units = (
                "open-alm-dev-app.service",
                "open-alm-dev-worker.service",
                "open-alm-dev-worker-realtime.service",
                "open-alm-dev-worker-long.service",
                "open-alm-dev-worker-patent.service",
                "open-alm-dev-worker-ai-graph.service",
                "open-alm-dev-worker-ppt.service",
                "open-alm-dev-worker-beat.service",
            )
            for unit_name in revisioned_units:
                unit_text = (unit_dir / unit_name).read_text(encoding="utf-8")
                self.assertIn(
                    f"Environment=OPEN_ALM_RUNTIME_REVISION={revision}",
                    unit_text,
                    unit_name,
                )

            calls = systemctl_log.read_text(encoding="utf-8")
            self.assertIn("systemctl --user daemon-reload", calls)
            quiesce = calls.index("systemctl --user stop")
            migrate = calls.index("uv run --frozen --python 3.12 alembic upgrade head")
            verify = calls.index("scripts/check-alembic-state.py")
            reconcile = calls.index("scripts/reconcile_patent_prior_art_queue.py")
            start = calls.index("systemctl --user start")
            final_reconcile = calls.rindex(
                "scripts/reconcile_patent_prior_art_queue.py"
            )
            restart = calls.rindex("systemctl --user restart")
            self.assertLess(quiesce, migrate)
            self.assertLess(migrate, verify)
            self.assertLess(verify, reconcile)
            self.assertLess(reconcile, start)
            self.assertLess(final_reconcile, restart)
            for unit_name in revisioned_units:
                self.assertIn(unit_name, calls)

    def test_managed_dev_smoke_checks_revision_queue_owner_and_concurrency(
        self,
    ) -> None:
        script = DEV_SMOKE.read_text(encoding="utf-8")

        self.assertIn("assert_dev_unit_runtime_revisions", script)
        self.assertIn("assert_dev_api_runtime_revisions", script)
        self.assertIn("assert_dev_worker_queues_consumed", script)
        self.assertIn(
            "--celery-queues --celery-queue-group patent",
            script.replace("\\\n", ""),
        )
        self.assertIn("open-alm-dev-worker-patent@", script)
        self.assertIn('pool.get("max-concurrency") != 1', script)
        self.assertIn("protected patent queue has an unauthorized consumer", script)
        self.assertIn(
            "stale worker is still consuming the legacy patent queue",
            script,
        )
        self.assertIn('broker.llen(os.environ["LEGACY_QUEUE"])', script)
        self.assertIn("legacy patent queue still contains", script)
        self.assertNotIn("print(get_settings().broker_url", script)
        self.assertIn("LEGACY_PATENT_PRIOR_ART_QUEUE", script)

    def test_dev_systemd_rolls_queue_back_before_removing_patent_worker(self) -> None:
        script = DEV_SYSTEMD.read_text(encoding="utf-8")

        self.assertIn("rollback-patent-worker)", script)
        self.assertIn("quiesce_search_writers", script)
        self.assertIn("rollback_patent_prior_art_queue.py", script)
        self.assertIn('systemctl --user disable "$unit"', script)
        self.assertIn('rm -f "$UNIT_DIR/$unit"', script)
        self.assertIn(
            "PartOf=open-alm-dev-app.service",
            (
                ROOT / "ops/systemd/user/open-alm-dev-worker-patent.service.template"
            ).read_text(encoding="utf-8"),
        )

    def test_dev_start_and_restart_use_the_queue_cutover_activation_path(self) -> None:
        script = DEV_SYSTEMD.read_text(encoding="utf-8")

        self.assertIn("activate_dev_runtime start", script)
        self.assertIn("activate_dev_runtime restart", script)
        quiesce = script.index(
            "quiesce_search_writers",
            script.index("activate_dev_runtime()"),
        )
        migrate = script.index("run_api_command alembic upgrade head")
        verify = script.index("scripts/check-alembic-state.py")
        reconcile = script.index("scripts/reconcile_patent_prior_art_queue.py")
        activate = script.index('systemctl --user "$systemctl_action"')
        self.assertLess(quiesce, migrate)
        self.assertLess(migrate, verify)
        self.assertLess(verify, reconcile)
        self.assertLess(reconcile, activate)

    def test_dev_restart_fails_before_migration_when_writer_remains_active(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            command_log = temp / "commands.log"
            systemctl = bin_dir / "systemctl"
            systemctl.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'systemctl %s\\n' \"$*\" >> {shlex.quote(str(command_log))}\n",
                encoding="utf-8",
            )
            systemctl.chmod(0o755)
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'uv %s\\n' \"$*\" >> {shlex.quote(str(command_log))}\n",
                encoding="utf-8",
            )
            uv.chmod(0o755)

            result = subprocess.run(
                ["bash", str(DEV_SYSTEMD), "restart"],
                cwd=ROOT,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    **os.environ,
                    "HOME": str(temp),
                    "XDG_CONFIG_HOME": str(temp / "config"),
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                },
            )

            self.assertNotEqual(result.returncode, 0)
            self.assertIn(
                "queue cutover requires inactive search writer", result.stderr
            )
            calls = command_log.read_text(encoding="utf-8")
            self.assertNotIn("uv run", calls)
            self.assertNotIn("systemctl --user restart", calls)

    def test_dev_restart_does_not_activate_when_reconcile_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            bin_dir = temp / "bin"
            bin_dir.mkdir()
            command_log = temp / "commands.log"
            systemctl = bin_dir / "systemctl"
            systemctl.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'systemctl %s\\n' \"$*\" >> {shlex.quote(str(command_log))}\n"
                'if [[ "$*" == *" is-active "* ]]; then exit 3; fi\n',
                encoding="utf-8",
            )
            systemctl.chmod(0o755)
            uv = bin_dir / "uv"
            uv.write_text(
                "#!/usr/bin/env bash\n"
                f"printf 'uv %s\\n' \"$*\" >> {shlex.quote(str(command_log))}\n"
                'if [[ "$*" == *"reconcile_patent_prior_art_queue.py"* ]]; '
                "then exit 1; fi\n",
                encoding="utf-8",
            )
            uv.chmod(0o755)

            result = subprocess.run(
                ["bash", str(DEV_SYSTEMD), "restart"],
                cwd=ROOT,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                env={
                    **os.environ,
                    "HOME": str(temp),
                    "XDG_CONFIG_HOME": str(temp / "config"),
                    "PATH": f"{bin_dir}:{os.environ['PATH']}",
                },
            )

            self.assertNotEqual(result.returncode, 0)
            calls = command_log.read_text(encoding="utf-8")
            self.assertIn("alembic upgrade head", calls)
            self.assertIn("reconcile_patent_prior_art_queue.py", calls)
            self.assertNotIn("systemctl --user restart", calls)


if __name__ == "__main__":
    unittest.main()
