from __future__ import annotations

import os
import re
import runpy
import shlex
import subprocess
import tempfile
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SCRIPT = ROOT / "scripts" / "prod-deploy.sh"
SYSTEMD_SCRIPT = ROOT / "scripts" / "prod-systemd.sh"
ENV_CONTRACT_SCRIPT = ROOT / "scripts" / "check-env-contract.py"


def load_tests(
    loader: unittest.TestLoader,
    standard_tests: unittest.TestSuite,
    pattern: str | None,
) -> unittest.TestSuite:
    if pattern is None:
        standard_tests.addTests(
            loader.loadTestsFromName("scripts.tests.test_dev_runtime_scripts")
        )
    return standard_tests


class ProdDeployScriptTest(unittest.TestCase):
    def run_bash(
        self,
        script: str,
        *,
        allow_non_prod_checkout: bool = True,
    ) -> subprocess.CompletedProcess[str]:
        env = os.environ.copy()
        env["OPEN_ALM_IMAGE_ENABLED"] = "false"
        if allow_non_prod_checkout:
            env["OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS"] = "1"
        else:
            env.pop("OPEN_ALM_ALLOW_NON_PROD_CHECKOUT_PROD_COMMANDS", None)
        return subprocess.run(
            ["bash", "-lc", script],
            cwd=ROOT,
            env=env,
            text=True,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            check=False,
        )

    def test_source_does_not_run_deployment_main(self) -> None:
        result = self.run_bash(f"source {shlex.quote(str(SCRIPT))}; echo sourced")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "sourced")

    def test_env_loader_supports_export_quotes_and_inline_comments(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "\n".join(
                    [
                        'export OPEN_ALM_PROD_SKIP_RELEASE_GATES="1" # deliberate',
                        "OPEN_ALM_PROD_RELEASE_GATE_ADAPTERS=' keyword_dataset_scope '",
                        "OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS= ws-a, ws-b # scoped",
                        "OPEN_ALM_PROD_KEYWORD_REINDEX_ALL_ACTIVE=0",
                        "OPEN_ALM_PROD_REMOTE_REF= origin/main # default",
                    ]
                )
                + "\n",
                encoding="utf-8",
            )
            bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
unset OPEN_ALM_PROD_SKIP_RELEASE_GATES
unset OPEN_ALM_PROD_RELEASE_GATE_ADAPTERS
unset OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS
unset OPEN_ALM_PROD_KEYWORD_REINDEX_ALL_ACTIVE
unset OPEN_ALM_PROD_REMOTE_REF
ROOT_DIR={shlex.quote(str(root))}
load_prod_deploy_env_file
[[ "$OPEN_ALM_PROD_SKIP_RELEASE_GATES" == "1" ]]
[[ "$OPEN_ALM_PROD_RELEASE_GATE_ADAPTERS" == " keyword_dataset_scope " ]]
[[ "$OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS" == "ws-a, ws-b" ]]
[[ "$OPEN_ALM_PROD_KEYWORD_REINDEX_ALL_ACTIVE" == "0" ]]
[[ "$OPEN_ALM_PROD_REMOTE_REF" == "origin/main" ]]
SKIP_RELEASE_GATES="${{OPEN_ALM_PROD_SKIP_RELEASE_GATES:-0}}"
RELEASE_GATE_ADAPTERS="${{OPEN_ALM_PROD_RELEASE_GATE_ADAPTERS:-}}"
KEYWORD_REINDEX_WORKSPACE_KEYS="${{OPEN_ALM_PROD_KEYWORD_REINDEX_WORKSPACE_KEYS:-}}"
KEYWORD_REINDEX_ALL_ACTIVE="${{OPEN_ALM_PROD_KEYWORD_REINDEX_ALL_ACTIVE:-0}}"
validate_release_gate_configuration
"""

            result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_keyword_release_gate_supports_explicit_all_active_mode(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
RELEASE_GATE_ADAPTERS=keyword_dataset_scope
KEYWORD_REINDEX_WORKSPACE_KEYS=
KEYWORD_REINDEX_ALL_ACTIVE=1
SKIP_RELEASE_GATES=0
validate_release_gate_configuration
[[ "$(keyword_reindex_args)" == " --all-active" ]]
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_keyword_all_active_cli_option_enables_release_gate_mode(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
usage() {{ [[ "$KEYWORD_REINDEX_ALL_ACTIVE" == "1" ]]; }}
main --keyword-reindex-all-active --help
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_keyword_release_gate_rejects_mixed_workspace_and_all_active_modes(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
RELEASE_GATE_ADAPTERS=keyword_dataset_scope
KEYWORD_REINDEX_WORKSPACE_KEYS=ws-a
KEYWORD_REINDEX_ALL_ACTIVE=1
SKIP_RELEASE_GATES=0
if validate_release_gate_configuration; then
  exit 9
fi
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("mutually exclusive", result.stderr)

    def test_keyword_dataset_scope_gate_is_pre_activation_only(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
calls=""
run_keyword_dataset_scope_gate() {{ calls="$calls|keyword"; }}
dispatch_release_gate_adapter pre_activate keyword_dataset_scope 1
dispatch_release_gate_adapter post_activate keyword_dataset_scope 1
[[ "$calls" == "|keyword" ]]
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_image_enabled_requires_non_bypassable_cutover_gate(self) -> None:
        missing_adapter = self.run_bash(
            f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
IMAGE_ENABLED=true
RELEASE_GATE_ADAPTERS=keyword_dataset_scope
SKIP_RELEASE_GATES=0
if validate_release_gate_configuration; then
  exit 9
fi
"""
        )
        skipped = self.run_bash(
            f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
IMAGE_ENABLED=true
RELEASE_GATE_ADAPTERS=image_model_settings_cutover
SKIP_RELEASE_GATES=1
if validate_release_gate_configuration; then
  exit 9
fi
"""
        )

        self.assertEqual(missing_adapter.returncode, 0, missing_adapter.stderr)
        self.assertIn("requires the image_model_settings_cutover", missing_adapter.stderr)
        self.assertEqual(skipped.returncode, 0, skipped.stderr)
        self.assertIn("cannot bypass", skipped.stderr)

    def test_image_model_settings_cutover_gate_is_pre_activation_only(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
calls=""
validate_model_settings_cutover_env_file() {{ calls="$calls|validate"; }}
run_image_model_settings_cutover_gate() {{ calls="$calls|image"; }}
dispatch_release_gate_adapter validate image_model_settings_cutover 1
dispatch_release_gate_adapter pre_activate image_model_settings_cutover 1
dispatch_release_gate_adapter post_activate image_model_settings_cutover 1
[[ "$calls" == "|validate|image" ]]
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_knowledge_retirement_preflight_is_owned_by_the_migration(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("run_knowledge_retirement_cutover_gate", script)
        self.assertNotIn("audit_knowledge_retirement.py", script)
        self.assertNotIn("Require a safe Knowledge retirement inventory", script)
        self.assertNotIn("temporary non-bypassable Knowledge retirement cutover gate", script)
        self.assertNotIn("mandatory in Release N/N+1", script)

        result = self.run_bash(f"source {shlex.quote(str(SCRIPT))}; usage")

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn(
            "6. quiesce all production writer units while keeping production infra "
            "available",
            result.stderr,
        )
        self.assertIn(
            "7. create and verify the native Postgres rollback backup from the "
            "quiesced state",
            result.stderr,
        )
        self.assertIn(
            "8. run Alembic migrations explicitly; destructive migrations fail closed "
            "in-migration",
            result.stderr,
        )
        self.assertIn(
            "The N+2 Knowledge physical-retirement migration performs its fail-closed",
            result.stderr,
        )
        self.assertIn(
            "preflight in the same transaction before dropping the retired tables.",
            result.stderr,
        )
        self.assertIn(
            "No separate Knowledge audit-script release gate runs after migration.",
            result.stderr,
        )

    def test_files_full_consistency_checker_is_not_an_every_deploy_gate(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertNotIn("files_retrieval_cutover", script)
        self.assertNotIn("check_files_retrieval_cutover.py", script)

    def test_image_model_settings_cutover_runs_idle_import_and_readiness_in_order(
        self,
    ) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
calls=""
MODEL_SETTINGS_CUTOVER_ENV_FILE="$ROOT_DIR/.env"
run_shell_step() {{ calls="$calls|$1"; }}
run_image_model_settings_cutover_gate
expected="|Require an idle image generation queue before settings cutover|Preview legacy image model settings cutover|Apply legacy image model settings cutover|Verify image model settings cutover idempotency|Validate image model settings readiness after cutover"
[[ "$calls" == "$expected" ]]
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_env_loader_preserves_preexisting_environment_values(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            (root / ".env").write_text(
                "OPEN_ALM_PROD_SKIP_RELEASE_GATES=0\n",
                encoding="utf-8",
            )
            bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
OPEN_ALM_PROD_SKIP_RELEASE_GATES=1
ROOT_DIR={shlex.quote(str(root))}
load_prod_deploy_env_file
[[ "$OPEN_ALM_PROD_SKIP_RELEASE_GATES" == "1" ]]
"""

            result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_deploy_requires_remote_ref_sync(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            remote = root / "origin.git"
            deploy = root / "deploy"
            writer = root / "writer"
            bash = f"""
set -euo pipefail
git init --bare {shlex.quote(str(remote))}
git clone {shlex.quote(str(remote))} {shlex.quote(str(deploy))}
git -C {shlex.quote(str(deploy))} config user.email deploy@example.invalid
git -C {shlex.quote(str(deploy))} config user.name Deploy
git -C {shlex.quote(str(deploy))} checkout -b main
printf old > {shlex.quote(str(deploy / "README.md"))}
git -C {shlex.quote(str(deploy))} add README.md
git -C {shlex.quote(str(deploy))} commit -m initial
git -C {shlex.quote(str(deploy))} push -u origin main
git clone {shlex.quote(str(remote))} {shlex.quote(str(writer))}
git -C {shlex.quote(str(writer))} config user.email writer@example.invalid
git -C {shlex.quote(str(writer))} config user.name Writer
git -C {shlex.quote(str(writer))} checkout main
printf new >> {shlex.quote(str(writer / "README.md"))}
git -C {shlex.quote(str(writer))} commit -am second
git -C {shlex.quote(str(writer))} push origin main
source {shlex.quote(str(SCRIPT))}
ROOT_DIR={shlex.quote(str(deploy))}
EXPECTED_ROOT={shlex.quote(str(deploy))}
EXPECTED_BRANCH=main
EXPECTED_REMOTE_REF=origin/main
require_prod_checkout
"""

            result = self.run_bash(bash, allow_non_prod_checkout=False)

        self.assertEqual(result.returncode, 1, result.stderr)
        self.assertIn("HEAD is not synced with origin/main", result.stderr)

    def test_prod_script_env_keys_are_declared_in_env_contract(self) -> None:
        script_text = "\n".join(
            [
                SCRIPT.read_text(encoding="utf-8"),
                SYSTEMD_SCRIPT.read_text(encoding="utf-8"),
            ]
        )
        referenced_keys = set(re.findall(r"\bOPEN_ALM_PROD_[A-Z0-9_]+\b", script_text))
        contract = runpy.run_path(str(ENV_CONTRACT_SCRIPT))
        declared_keys = set(contract["DEPLOY_ENV_KEYS"])

        self.assertFalse(
            referenced_keys - declared_keys,
            "OPEN_ALM_PROD_* keys used by production scripts must be in DEPLOY_ENV_KEYS",
        )

    def test_production_systemd_smoke_checks_readiness(self) -> None:
        script = SYSTEMD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("open-alm-prod-worker.service", script)
        self.assertIn("open-alm-prod-worker-realtime.service", script)
        self.assertIn("open-alm-prod-worker-long.service", script)
        self.assertIn("open-alm-prod-worker-patent.service", script)
        self.assertIn("open-alm-prod-worker-ai-graph.service", script)
        self.assertIn("open-alm-prod-worker-ppt.service", script)
        self.assertIn("systemctl --user is-active --quiet \"$worker_unit\"", script)
        self.assertIn("systemctl --user is-active --quiet open-alm-prod-worker-beat.service", script)
        self.assertIn("http://127.0.0.1:8000/healthz", script)
        self.assertIn("http://127.0.0.1:8000/readyz", script)
        self.assertIn("assert_prod_health_payload", script)
        self.assertIn('payload.get("environment") != "production"', script)
        self.assertIn('payload.get("instance_id") != "prod-api"', script)
        self.assertIn("assert_prod_bootstrap_payload", script)
        self.assertIn('payload.get("dev_admin_login_available") is not False', script)
        self.assertIn("assert_worker_queues_consumed", script)
        self.assertIn("open_alm_worker.queue_contract --celery-queues", script)
        self.assertIn(
            "--celery-queues --celery-queue-group patent",
            script.replace("\\\n", ""),
        )
        self.assertIn("inspect active_queues", script)
        self.assertIn("inspect stats", script)
        self.assertIn("--celery-queue-group patent", script)
        self.assertIn("protected patent queue must have exactly one consumer", script)
        self.assertIn("protected patent queue has an unauthorized consumer", script)
        self.assertIn(
            "stale worker is still consuming the legacy patent queue",
            script,
        )
        self.assertIn("LEGACY_PATENT_PRIOR_ART_QUEUE", script)
        self.assertIn('pool.get("max-concurrency") != 1', script)
        self.assertIn("assert_unit_runtime_revisions", script)
        self.assertIn('payload.get("runtime_revision")', script)
        self.assertIn("curl_optional_prod_smoke_path", script)
        self.assertIn("fetch_prod_bootstrap_payload", script)
        self.assertNotIn("http://127.0.0.1:8000/w/hq/meeting/example", script)
        self.assertLess(
            script.index("http://127.0.0.1:8000/healthz"),
            script.index("http://127.0.0.1:8000/readyz"),
        )

    def test_production_health_contract_accepts_only_current_revision(self) -> None:
        current_payload = (
            '{"environment":"production","instance_id":"prod-api",'
            '"runtime_revision":"current"}'
        )
        stale_payload = (
            '{"environment":"production","instance_id":"prod-api",'
            '"runtime_revision":"stale"}'
        )
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SYSTEMD_SCRIPT))}
assert_prod_health_payload {shlex.quote(current_payload)} current
if assert_prod_health_payload {shlex.quote(stale_payload)} current; then
  exit 9
fi
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("runtime revision is stale", result.stderr)

    def test_production_systemd_smoke_fails_closed_when_tls_check_fails(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SYSTEMD_SCRIPT))}
python3() {{ return 17; }}
if assert_prod_tls_ready; then
  exit 9
fi
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)
        script = SYSTEMD_SCRIPT.read_text(encoding="utf-8")
        self.assertIn("assert_prod_tls_ready || return $?", script)

    def test_production_systemd_tls_break_glass_only_changes_expiry_threshold(
        self,
    ) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SYSTEMD_SCRIPT))}
calls=""
python3() {{ calls="$calls|$*"; }}
TLS_EXPIRY_BREAK_GLASS=0
assert_prod_tls_ready
[[ "$calls" == *"scripts/check_live_tls_expiry.py" ]]
[[ "$calls" != *"--threshold-days=0"* ]]
calls=""
TLS_EXPIRY_BREAK_GLASS=1
assert_prod_tls_ready
[[ "$calls" == *"scripts/check_live_tls_expiry.py --threshold-days=0"* ]]
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("one-shot TLS expiry break-glass", result.stderr)

    def test_production_systemd_accepts_tls_break_glass_only_for_smoke(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SYSTEMD_SCRIPT))}
parse_command_args smoke --tls-expiry-break-glass
[[ "$COMMAND" == "smoke" ]]
[[ "$TLS_EXPIRY_BREAK_GLASS" == "1" ]]
if parse_command_args status --tls-expiry-break-glass; then
  exit 9
fi
if parse_command_args smoke --unexpected-option; then
  exit 10
fi
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("supported only with the smoke command", result.stderr)
        self.assertIn("Usage:", result.stderr)

    def test_production_deploy_checks_tls_before_mutating_steps(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        tls_check = script.index("Validate public TLS certificate readiness")
        dependency_install = script.index("Install locked production dependencies")
        self.assertLess(tls_check, dependency_install)
        self.assertIn('python3 \"$ROOT_DIR/scripts/check_live_tls_expiry.py\"', script)

    def test_production_deploy_tls_break_glass_reaches_preflight_and_both_smokes(
        self,
    ) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
acquire_prod_deploy_lock() {{ :; }}
require_prod_checkout() {{ :; }}
validate_release_gate_configuration() {{ :; }}
print_git_state() {{ :; }}
run_step() {{ printf 'step'; printf '|%s' "$@"; printf '\n'; }}
run_shell_step() {{ :; }}
run_postgres_backup_step() {{ :; }}
run_frontend_build_step() {{ :; }}
promote_frontend_build_step() {{ :; }}
run_release_gates() {{ :; }}
main --dry-run --tls-expiry-break-glass
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)
        self.assertIn("one-shot TLS expiry break-glass", result.stderr)
        self.assertEqual(result.stdout.count("--threshold-days=0"), 1)
        self.assertEqual(result.stdout.count("--tls-expiry-break-glass"), 2)

    def test_production_deploy_default_tls_path_has_no_break_glass_arguments(
        self,
    ) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
run_step() {{ printf 'step'; printf '|%s' "$@"; printf '\n'; }}
run_prod_tls_preflight
run_prod_smoke_step smoke-one
run_prod_smoke_step smoke-two
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertNotIn("--threshold-days=0", result.stdout)
        self.assertNotIn("--tls-expiry-break-glass", result.stdout)

    def test_production_backup_is_private_verified_and_captured_after_quiesce(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        pg_dump = script.index('subprocess.run(["pg_dump", "-Fc", "-f", backup_file]')
        private_mode = script.index("os.chmod(backup_file, 0o600)")
        archive_check = script.index('["pg_restore", "-l", backup_file]')
        quiesce = script.index(
            "Quiesce all production writer units before rollback backup and database "
            "migration"
        )
        backup = script.rindex('run_postgres_backup_step "$backup_file"')
        migration = script.index("Run Alembic migrations")
        self.assertLess(pg_dump, private_mode)
        self.assertLess(private_mode, archive_check)
        self.assertLess(quiesce, backup)
        self.assertLess(backup, migration)
        self.assertEqual(script.count('run_postgres_backup_step "$backup_file"'), 1)
        self.assertIn(
            'install -d -m 700 "$BACKUP_ROOT" "$backup_dir"',
            script,
        )
        self.assertIn(
            "${OPEN_ALM_PROD_BACKUP_ROOT:-/projects/open-alm/backups/prod}",
            script,
        )
        self.assertIn("sha256={digest.hexdigest()}", script)

    def test_production_systemd_smoke_settings_are_loaded_from_env_file(self) -> None:
        script = SYSTEMD_SCRIPT.read_text(encoding="utf-8")

        self.assertLess(
            script.index("load_prod_systemd_env_file\n"),
            script.index('SMOKE_ATTEMPTS="$(normalize_prod_systemd_env_value'),
        )
        self.assertLess(
            script.index("load_prod_systemd_env_file\n"),
            script.index('SMOKE_DELAY_SECONDS="$(normalize_prod_systemd_env_value'),
        )
        self.assertLess(
            script.index("load_prod_systemd_env_file\n"),
            script.index('SMOKE_CELERY_TIMEOUT_SECONDS="$(normalize_prod_systemd_env_value'),
        )
        self.assertLess(
            script.index("load_prod_systemd_env_file\n"),
            script.index('SMOKE_WEB_HOST="$(normalize_prod_systemd_env_value'),
        )
        self.assertLess(
            script.index("load_prod_systemd_env_file\n"),
            script.index('SMOKE_WORKSPACE_PATH="$(normalize_prod_systemd_env_value'),
        )

    def test_production_systemd_uses_deploy_checkout_guard(self) -> None:
        script = SYSTEMD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("OPEN_ALM_PROD_ROOT", script)
        self.assertIn("OPEN_ALM_PROD_BRANCH", script)
        self.assertIn('git -C "$ROOT_DIR" rev-parse --abbrev-ref HEAD', script)
        self.assertIn('git -C "$ROOT_DIR" status --porcelain', script)
        self.assertIn("require_clean_prod_checkout", script)
        self.assertLess(
            script.index("require_clean_prod_checkout"),
            script.index("render_units"),
        )

    def test_production_systemd_quiesces_only_search_writing_app_units(self) -> None:
        bash = f"""
set -euo pipefail
systemctl() {{ printf 'systemctl'; printf ' %s' "$@"; printf '\n'; }}
export -f systemctl
bash {shlex.quote(str(SYSTEMD_SCRIPT))} quiesce-search-writers
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--user stop open-alm-prod-api.service", result.stdout)
        self.assertIn("open-alm-prod-collab.service", result.stdout)
        self.assertIn("open-alm-prod-worker.service", result.stdout)
        self.assertIn("open-alm-prod-worker-realtime.service", result.stdout)
        self.assertIn("open-alm-prod-worker-long.service", result.stdout)
        self.assertIn("open-alm-prod-worker-patent.service", result.stdout)
        self.assertIn("open-alm-prod-worker-ai-graph.service", result.stdout)
        self.assertIn("open-alm-prod-worker-ppt.service", result.stdout)
        self.assertIn("open-alm-prod-worker-beat.service", result.stdout)
        self.assertNotIn("open-alm-prod-infra.service", result.stdout)
        self.assertNotIn("open-alm-privacy-filter.service", result.stdout)

    def test_production_systemd_can_resume_search_writing_app_units(self) -> None:
        bash = f"""
set -euo pipefail
systemctl() {{ printf 'systemctl'; printf ' %s' "$@"; printf '\n'; }}
export -f systemctl
bash {shlex.quote(str(SYSTEMD_SCRIPT))} resume-search-writers
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn("--user start open-alm-prod-api.service", result.stdout)
        self.assertIn("open-alm-prod-collab.service", result.stdout)
        self.assertIn("open-alm-prod-worker-patent.service", result.stdout)
        self.assertIn("open-alm-prod-worker-beat.service", result.stdout)
        self.assertNotIn("open-alm-prod-infra.service", result.stdout)

    def test_production_systemd_renders_only_prod_units(self) -> None:
        script = SYSTEMD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn('template_dir.glob("open-alm-prod-*.service.template")', script)
        self.assertIn("__OPEN_ALM_WORKER_DEFAULT_QUEUE_NAMES__", script)
        self.assertIn("__OPEN_ALM_WORKER_REALTIME_QUEUE_NAMES__", script)
        self.assertIn("__OPEN_ALM_WORKER_LONG_QUEUE_NAMES__", script)
        self.assertIn("__OPEN_ALM_WORKER_PATENT_QUEUE_NAMES__", script)
        self.assertIn("__OPEN_ALM_WORKER_PATENT_CONCURRENCY__", script)
        self.assertIn("__OPEN_ALM_WORKER_PPT_QUEUE_NAMES__", script)
        self.assertIn("__OPEN_ALM_WORKER_AI_GRAPH_QUEUE_NAMES__", script)
        self.assertIn("__OPEN_ALM_RUNTIME_REVISION__", script)
        template_text = "\n".join(
            [
                (
                    ROOT / "ops/systemd/user/open-alm-prod-worker.service.template"
                ).read_text(encoding="utf-8"),
                (
                    ROOT / "ops/systemd/user/open-alm-prod-worker-realtime.service.template"
                ).read_text(encoding="utf-8"),
                (
                    ROOT / "ops/systemd/user/open-alm-prod-worker-long.service.template"
                ).read_text(encoding="utf-8"),
                (
                    ROOT / "ops/systemd/user/open-alm-prod-worker-patent.service.template"
                ).read_text(encoding="utf-8"),
                (
                    ROOT / "ops/systemd/user/open-alm-prod-worker-ai-graph.service.template"
                ).read_text(encoding="utf-8"),
                (
                    ROOT / "ops/systemd/user/open-alm-prod-worker-ppt.service.template"
                ).read_text(encoding="utf-8"),
                (
                    ROOT / "ops/systemd/user/open-alm-prod-worker-beat.service.template"
                ).read_text(encoding="utf-8"),
            ]
        )
        self.assertIn("Environment=OPEN_ALM_WORKER_QUEUE_GROUP=default", template_text)
        self.assertIn("Environment=OPEN_ALM_WORKER_QUEUE_GROUP=realtime", template_text)
        self.assertIn("Environment=OPEN_ALM_WORKER_QUEUE_GROUP=long", template_text)
        self.assertIn("Environment=OPEN_ALM_WORKER_QUEUE_GROUP=patent", template_text)
        self.assertIn("Environment=OPEN_ALM_WORKER_QUEUE_GROUP=ai_graph", template_text)
        self.assertIn("Environment=OPEN_ALM_WORKER_QUEUE_GROUP=ppt", template_text)
        self.assertIn("Environment=OPEN_ALM_WORKER_QUEUE_GROUP=beat", template_text)
        self.assertIn("--hostname=open-alm-prod-worker-default@%H", template_text)
        self.assertIn("--hostname=open-alm-prod-worker-realtime@%H", template_text)
        self.assertIn("--hostname=open-alm-prod-worker-long@%H", template_text)
        self.assertIn("--hostname=open-alm-prod-worker-patent@%H", template_text)
        self.assertIn("--hostname=open-alm-prod-worker-ai-graph@%H", template_text)
        self.assertIn("--hostname=open-alm-prod-worker-ppt@%H", template_text)
        self.assertIn("-Q __OPEN_ALM_WORKER_PATENT_QUEUE_NAMES__", template_text)
        self.assertIn("--concurrency __OPEN_ALM_WORKER_PATENT_CONCURRENCY__", template_text)
        self.assertIn("PartOf=open-alm-prod-api.service", template_text)
        self.assertIn(
            "ExecCondition=/usr/bin/test -f __OPEN_ALM_ROOT__/ops/systemd/user/"
            "open-alm-prod-worker-patent.service.template",
            template_text,
        )
        self.assertIn(
            "Environment=OPEN_ALM_RUNTIME_REVISION=__OPEN_ALM_RUNTIME_REVISION__",
            template_text,
        )
        self.assertNotIn("open-alm-inference-gateway.service.template", script)

    def test_production_deploy_syncs_api_and_worker_python_environments(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("Sync production API Python dependencies", script)
        self.assertIn("Sync production worker Python dependencies", script)
        self.assertIn(
            "cd '$ROOT_DIR/apps/api' && uv sync --python 3.12 --frozen --no-dev",
            script,
        )
        self.assertIn(
            "cd '$ROOT_DIR/apps/worker' && uv sync --python 3.12 --frozen --no-dev",
            script,
        )
        self.assertLess(
            script.index("Sync production worker Python dependencies"),
            script.index("Restart production systemd units"),
        )

    def test_production_deploy_restarts_all_revisioned_units_before_smoke(self) -> None:
        deploy_script = SCRIPT.read_text(encoding="utf-8")
        systemd_script = SYSTEMD_SCRIPT.read_text(encoding="utf-8")

        self.assertLess(
            deploy_script.index("Restart production systemd units"),
            deploy_script.index("Wait for production smoke checks after activation"),
        )
        self.assertIn('systemctl --user restart "${UNITS[@]}"', systemd_script)
        self.assertIn("open-alm-prod-api.service", systemd_script)
        self.assertIn("open-alm-prod-worker-patent.service", systemd_script)
        self.assertIn("open-alm-prod-worker-beat.service", systemd_script)
        self.assertLess(
            systemd_script.index('assert_unit_runtime_revisions "$expected_revision"'),
            systemd_script.index("assert_worker_queues_consumed || return $?"),
        )

    def test_production_deploy_reconciles_patent_queue_while_writers_are_quiesced(
        self,
    ) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        quiesce = script.index(
            "Quiesce all production writer units before rollback backup and database migration"
        )
        migrate = script.index("Run Alembic migrations")
        reconcile = script.index(
            "Fence and republish patent prior-art jobs onto the protected queue"
        )
        restart = script.index("Restart production systemd units")
        self.assertLess(quiesce, migrate)
        self.assertLess(migrate, reconcile)
        self.assertLess(reconcile, restart)
        self.assertIn("reconcile_patent_prior_art_queue.py", script)

    def test_production_systemd_rolls_queue_back_before_removing_patent_worker(
        self,
    ) -> None:
        script = SYSTEMD_SCRIPT.read_text(encoding="utf-8")

        self.assertIn("rollback-patent-worker)", script)
        self.assertIn('systemctl --user stop "${SEARCH_WRITER_UNITS[@]}"', script)
        self.assertIn("rollback_patent_queue", script)
        self.assertIn("rollback_patent_prior_art_queue.py", script)
        self.assertIn('systemctl --user disable "$unit"', script)
        self.assertIn('rm -f "$UNIT_DIR/$unit"', script)
        self.assertIn('systemctl --user daemon-reload', script)

    def test_production_patent_rollback_is_fail_closed_when_writer_stop_fails(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            unit_dir = temp / "systemd"
            unit_dir.mkdir()
            unit_file = unit_dir / "open-alm-prod-worker-patent.service"
            unit_file.write_text("rendered", encoding="utf-8")
            rollback_marker = temp / "rollback-called"
            bash = f"""
set -euo pipefail
source {shlex.quote(str(SYSTEMD_SCRIPT))}
UNIT_DIR={shlex.quote(str(unit_dir))}
systemctl() {{
  if [[ "$1 $2" == "--user stop" ]]; then
    return 9
  fi
  return 0
}}
rollback_patent_queue() {{ touch {shlex.quote(str(rollback_marker))}; }}
rollback_patent_worker
"""

            result = self.run_bash(bash)

            self.assertEqual(result.returncode, 9, result.stderr)
            self.assertTrue(unit_file.exists())
            self.assertFalse(rollback_marker.exists())

    def test_production_patent_rollback_quiesces_republishes_then_removes_unit(
        self,
    ) -> None:
        with tempfile.TemporaryDirectory() as directory:
            temp = Path(directory)
            unit_dir = temp / "systemd"
            unit_dir.mkdir()
            unit_file = unit_dir / "open-alm-prod-worker-patent.service"
            unit_file.write_text("rendered", encoding="utf-8")
            calls = temp / "calls"
            bash = f"""
set -euo pipefail
source {shlex.quote(str(SYSTEMD_SCRIPT))}
UNIT_DIR={shlex.quote(str(unit_dir))}
systemctl() {{
  printf 'systemctl:%s\\n' "$*" >> {shlex.quote(str(calls))}
  if [[ "$1 $2" == "--user is-active" ]]; then
    return 3
  fi
  return 0
}}
rollback_patent_queue() {{
  printf 'queue-rollback\\n' >> {shlex.quote(str(calls))}
}}
rollback_patent_worker
"""

            result = self.run_bash(bash)

            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertFalse(unit_file.exists())
            recorded = calls.read_text(encoding="utf-8")
            self.assertLess(recorded.index("systemctl:--user stop"), recorded.index("queue-rollback"))
            self.assertLess(
                recorded.index("queue-rollback"),
                recorded.index(
                    "systemctl:--user disable open-alm-prod-worker-patent.service"
                ),
            )

    def test_production_deploy_promotes_complete_frontend_without_mixing_assets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apps = root / "dist" / "apps"
            live = apps / "web"
            staged = apps / ".web-staging"
            previous = apps / ".web-previous"
            (live / "assets").mkdir(parents=True)
            (staged / "assets").mkdir(parents=True)
            (live / "index.html").write_text("old-index", encoding="utf-8")
            (live / "assets" / "old.js").write_text("old", encoding="utf-8")
            (staged / "index.html").write_text("new-index", encoding="utf-8")
            (staged / "assets" / "new.js").write_text("new", encoding="utf-8")
            bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
ROOT_DIR={shlex.quote(str(root))}
promote_frontend_build \
  {shlex.quote(str(staged))} \
  {shlex.quote(str(live))} \
  {shlex.quote(str(previous))}
[[ "$(cat {shlex.quote(str(live / "index.html"))})" == "new-index" ]]
[[ -e {shlex.quote(str(live / "assets" / "new.js"))} ]]
[[ ! -e {shlex.quote(str(live / "assets" / "old.js"))} ]]
[[ "$(cat {shlex.quote(str(previous / "index.html"))})" == "old-index" ]]
[[ -e {shlex.quote(str(previous / "assets" / "old.js"))} ]]
"""

            result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_frontend_promotion_propagates_missing_stage_failure(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apps = root / "dist" / "apps"
            live = apps / "web"
            live.mkdir(parents=True)
            (live / "index.html").write_text("old-index", encoding="utf-8")
            bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
ROOT_DIR={shlex.quote(str(root))}
STAGED_FRONTEND_DIR={shlex.quote(str(apps / '.web-missing'))}
if promote_frontend_build_step; then
  exit 91
fi
[[ "$STAGED_FRONTEND_DIR" == {shlex.quote(str(apps / '.web-missing'))} ]]
[[ "$(cat {shlex.quote(str(live / 'index.html'))})" == "old-index" ]]
"""

            result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_frontend_promotion_restores_live_build_when_second_move_fails(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            apps = root / "dist" / "apps"
            live = apps / "web"
            staged = apps / ".web-staging"
            previous = apps / ".web-previous"
            live.mkdir(parents=True)
            staged.mkdir(parents=True)
            (live / "index.html").write_text("old-index", encoding="utf-8")
            (staged / "index.html").write_text("new-index", encoding="utf-8")
            bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
ROOT_DIR={shlex.quote(str(root))}
move_count=0
mv() {{
  move_count=$((move_count + 1))
  if (( move_count == 2 )); then
    return 42
  fi
  command mv "$@"
}}
if promote_frontend_build \
  {shlex.quote(str(staged))} \
  {shlex.quote(str(live))} \
  {shlex.quote(str(previous))}; then
  exit 91
fi
[[ "$(cat {shlex.quote(str(live / 'index.html'))})" == "old-index" ]]
[[ "$(cat {shlex.quote(str(staged / 'index.html'))})" == "new-index" ]]
[[ ! -e {shlex.quote(str(previous))} ]]
"""

            result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_frontend_release_paths_reject_symlinked_release_root(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "root"
            outside = Path(directory) / "outside"
            (root / "dist").mkdir(parents=True)
            outside.mkdir()
            (root / "dist" / "apps").symlink_to(outside, target_is_directory=True)
            bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
ROOT_DIR={shlex.quote(str(root))}
if require_frontend_release_path {shlex.quote(str(root / 'dist' / 'apps' / 'web'))}; then
  exit 91
fi
"""

            result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_activation_cleanup_restarts_stopped_api(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
calls=""
systemctl() {{ calls="$calls|$*"; }}
ACTIVATION_STARTED=1
FRONTEND_PROMOTED=1
API_STOPPED=1
cleanup_prod_deploy 0
[[ "$API_STOPPED" == "0" ]]
[[ "$calls" == *"--user start open-alm-prod-api.service"* ]]
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_interrupted_post_promotion_activation_resumes_all_search_writers(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
calls=""
bash() {{ calls="$calls|$*"; }}
SEARCH_WRITERS_QUIESCED=1
ACTIVATION_STARTED=1
FRONTEND_PROMOTED=1
API_STOPPED=1
cleanup_prod_deploy 0
[[ "$SEARCH_WRITERS_QUIESCED" == "0" ]]
[[ "$API_STOPPED" == "0" ]]
[[ "$calls" == *"scripts/prod-systemd.sh resume-search-writers"* ]]
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_failed_prepromotion_activation_keeps_api_fail_closed(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
calls=""
systemctl() {{ calls="$calls|$*"; }}
ACTIVATION_STARTED=1
FRONTEND_PROMOTED=0
API_STOPPED=1
if cleanup_prod_deploy 0; then
  exit 91
fi
[[ "$API_STOPPED" == "1" ]]
[[ "$calls" == *"--user stop open-alm-prod-api.service"* ]]
[[ "$calls" != *"--user start open-alm-prod-api.service"* ]]
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr)

    def test_production_deploy_uses_nonblocking_single_deploy_lock(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn("acquire_prod_deploy_lock", script)
        self.assertIn("flock -n", script)
        self.assertLess(
            script.rindex("acquire_prod_deploy_lock"),
            script.rindex("require_prod_checkout"),
        )

    def test_frontend_stage_build_passes_validated_out_dir_on_cli(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertIn('--outDir=$STAGED_FRONTEND_DIR', script)
        self.assertNotIn('OPEN_ALM_WEB_BUILD_OUT_DIR=', script)

    def test_production_deploy_rejects_incomplete_frontend_manifest(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            staged = root / "dist" / "apps" / ".web-staging"
            (staged / ".vite").mkdir(parents=True)
            (staged / "index.html").write_text(
                '<script type="module" src="/assets/missing.js"></script>',
                encoding="utf-8",
            )
            (staged / ".open-alm-build-id").write_text("build-current\n", encoding="utf-8")
            (staged / ".vite" / "manifest.json").write_text(
                '{"index.html":{"file":"assets/missing.js","isEntry":true}}',
                encoding="utf-8",
            )
            bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
ROOT_DIR={shlex.quote(str(root))}
validate_frontend_build {shlex.quote(str(staged))} build-current
"""

            result = self.run_bash(bash)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("missing frontend build artifact", result.stderr)

    def test_production_deploy_stages_before_quiesce_and_migrates_without_active_writers(
        self,
    ) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertLess(
            script.index("run_frontend_build_step"),
            script.index("Quiesce all production writer units"),
        )
        self.assertLess(
            script.index("Quiesce all production writer units"),
            script.rindex('run_postgres_backup_step "$backup_file"'),
        )
        self.assertLess(
            script.rindex('run_postgres_backup_step "$backup_file"'),
            script.index("Run Alembic migrations"),
        )
        self.assertLess(
            script.index("Run Alembic migrations"),
            script.index("Verify Alembic database revision"),
        )
        self.assertLess(
            script.index("Verify Alembic database revision"),
            script.rindex("promote_frontend_build_step"),
        )
        self.assertLess(
            script.rindex("promote_frontend_build_step"),
            script.index("Restart production systemd units"),
        )

    def test_production_deploy_installs_new_units_before_migration_quiesce(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")

        self.assertLess(
            script.index("Install production systemd units before migration quiesce"),
            script.index("Quiesce all production writer units"),
        )

    def test_production_deploy_runs_release_gates_before_activation(self) -> None:
        script = SCRIPT.read_text(encoding="utf-8")
        pre_activate_gate_index = script.index("run_release_gates pre_activate")
        post_activate_gate_index = script.index("run_release_gates post_activate")

        self.assertIn("Validate Alembic revision graph", script)
        self.assertIn("Verify Alembic database revision", script)
        self.assertIn("scripts/check-alembic-state.py' --graph-only", script)
        self.assertIn("scripts/check-alembic-state.py'", script)
        self.assertLess(
            script.index("Validate Alembic revision graph"),
            script.index("Create backup directory"),
        )
        self.assertLess(
            script.index("Run Alembic migrations"),
            script.index("Verify Alembic database revision"),
        )
        self.assertLess(
            script.index("Verify Alembic database revision"), pre_activate_gate_index
        )
        self.assertLess(
            script.index("Quiesce all production writer units"), pre_activate_gate_index
        )
        self.assertLess(
            pre_activate_gate_index, script.index("Restart production systemd units")
        )
        self.assertLess(
            script.index("Restart production systemd units"),
            script.index("Wait for production smoke checks after activation"),
        )
        self.assertLess(
            script.index("Wait for production smoke checks after activation"),
            post_activate_gate_index,
        )
        self.assertLess(
            post_activate_gate_index,
            script.index("Wait for final production smoke checks"),
        )

    def test_production_deploy_executes_quiesce_and_gate_phases_in_order(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
events=""
acquire_prod_deploy_lock() {{ :; }}
require_prod_checkout() {{ :; }}
validate_release_gate_configuration() {{ :; }}
print_git_state() {{ :; }}
run_step() {{ events="$events|step:$1"; }}
run_shell_step() {{ events="$events|shell:$1"; }}
run_postgres_backup_step() {{ events="$events|backup"; }}
run_frontend_build_step() {{ events="$events|build"; }}
promote_frontend_build_step() {{ events="$events|promote"; }}
run_release_gates() {{ events="$events|gate:${{1:?phase is required}}"; }}
main --dry-run
expected="|step:Quiesce all production writer units before rollback backup and database migration|backup|shell:Run Alembic migrations|shell:Verify Alembic database revision|shell:Fence and republish patent prior-art jobs onto the protected queue|gate:pre_activate|promote|step:Restart production systemd units|step:Wait for production smoke checks after activation|gate:post_activate|step:Wait for final production smoke checks"
[[ "$events" == *"$expected"* ]]
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 0, result.stderr + result.stdout)

    def test_failed_pre_activation_gate_keeps_new_frontend_inactive_and_writers_quiesced(
        self,
    ) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
acquire_prod_deploy_lock() {{ :; }}
require_prod_checkout() {{ :; }}
validate_release_gate_configuration() {{ :; }}
print_git_state() {{ :; }}
run_step() {{ printf 'step:%s\n' "$1"; }}
run_shell_step() {{ :; }}
run_postgres_backup_step() {{ :; }}
run_frontend_build_step() {{ :; }}
promote_frontend_build_step() {{ printf 'PROMOTED\n'; }}
bash() {{ printf 'cleanup:%s\n' "$*"; }}
run_release_gates() {{
  printf 'gate:%s\n' "$1"
  if [[ "$1" == pre_activate ]]; then
    return 42
  fi
}}
main
"""

        result = self.run_bash(bash)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn("gate:pre_activate", result.stdout)
        self.assertNotIn("PROMOTED", result.stdout)
        self.assertNotIn("Restart production systemd units", result.stdout)
        self.assertIn("keeping search-writing app units quiesced", result.stderr)
        self.assertIn("staged frontend inactive", result.stderr)
        self.assertIn("prod-systemd.sh quiesce-search-writers", result.stdout)

    def test_failed_post_activation_gate_keeps_restarted_services_running(
        self,
    ) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
acquire_prod_deploy_lock() {{ :; }}
require_prod_checkout() {{ :; }}
validate_release_gate_configuration() {{ :; }}
print_git_state() {{ :; }}
run_step() {{ printf 'step:%s\n' "$1"; }}
run_shell_step() {{ :; }}
run_postgres_backup_step() {{ :; }}
run_frontend_build_step() {{ :; }}
promote_frontend_build_step() {{ FRONTEND_PROMOTED=1; printf 'PROMOTED\n'; }}
bash() {{ printf 'cleanup:%s\n' "$*"; }}
run_release_gates() {{
  printf 'gate:%s\n' "$1"
  if [[ "$1" == post_activate ]]; then
    return 42
  fi
}}
main
"""

        result = self.run_bash(bash)

        self.assertEqual(result.returncode, 42)
        self.assertIn("PROMOTED", result.stdout)
        self.assertIn("step:Restart production systemd units", result.stdout)
        self.assertIn(
            "step:Wait for production smoke checks after activation", result.stdout
        )
        self.assertIn("gate:post_activate", result.stdout)
        self.assertNotIn("step:Wait for final production smoke checks", result.stdout)
        self.assertNotIn("deployment flow complete", result.stdout)
        self.assertNotIn("cleanup:", result.stdout)
        self.assertIn("Production services remain active", result.stderr)
        self.assertIn("deployment is not complete", result.stderr)

    def test_failed_migration_keeps_new_frontend_inactive_and_writers_quiesced(
        self,
    ) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
acquire_prod_deploy_lock() {{ :; }}
require_prod_checkout() {{ :; }}
validate_release_gate_configuration() {{ :; }}
print_git_state() {{ :; }}
run_step() {{ printf 'step:%s\n' "$1"; }}
run_shell_step() {{
  printf 'shell:%s\n' "$1"
  if [[ "$1" == "Run Alembic migrations" ]]; then
    return 42
  fi
}}
run_postgres_backup_step() {{ printf 'backup:verified\n'; }}
run_frontend_build_step() {{ :; }}
promote_frontend_build_step() {{ printf 'PROMOTED\n'; }}
run_release_gates() {{ printf 'gate:%s\n' "$1"; }}
bash() {{ printf 'cleanup:%s\n' "$*"; }}
main
"""

        result = self.run_bash(bash)

        self.assertNotEqual(result.returncode, 0)
        self.assertLess(
            result.stdout.index("backup:verified"),
            result.stdout.index("shell:Run Alembic migrations"),
        )
        self.assertIn("shell:Run Alembic migrations", result.stdout)
        self.assertNotIn("PROMOTED", result.stdout)
        self.assertNotIn("gate:pre_activate", result.stdout)
        self.assertNotIn("Restart production systemd units", result.stdout)
        self.assertIn("keeping search-writing app units quiesced", result.stderr)
        self.assertIn("prod-systemd.sh quiesce-search-writers", result.stdout)

    def test_failed_backup_stops_before_migration_and_keeps_writers_quiesced(
        self,
    ) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
acquire_prod_deploy_lock() {{ :; }}
require_prod_checkout() {{ :; }}
validate_release_gate_configuration() {{ :; }}
print_git_state() {{ :; }}
run_step() {{ printf 'step:%s\n' "$1"; }}
run_shell_step() {{ printf 'shell:%s\n' "$1"; }}
run_postgres_backup_step() {{ printf 'backup:failed\n'; return 42; }}
run_frontend_build_step() {{ :; }}
promote_frontend_build_step() {{ printf 'PROMOTED\n'; }}
run_release_gates() {{ printf 'gate:%s\n' "$1"; }}
bash() {{ printf 'cleanup:%s\n' "$*"; }}
main
"""

        result = self.run_bash(bash)

        self.assertNotEqual(result.returncode, 0)
        self.assertIn(
            "step:Quiesce all production writer units before rollback backup and "
            "database migration",
            result.stdout,
        )
        self.assertIn("backup:failed", result.stdout)
        self.assertNotIn("shell:Run Alembic migrations", result.stdout)
        self.assertNotIn("PROMOTED", result.stdout)
        self.assertNotIn("gate:pre_activate", result.stdout)
        self.assertIn("keeping search-writing app units quiesced", result.stderr)
        self.assertIn("prod-systemd.sh quiesce-search-writers", result.stdout)

    def test_failed_writer_quiesce_retries_fail_closed_before_activation(self) -> None:
        bash = f"""
set -euo pipefail
source {shlex.quote(str(SCRIPT))}
acquire_prod_deploy_lock() {{ :; }}
require_prod_checkout() {{ :; }}
validate_release_gate_configuration() {{ :; }}
print_git_state() {{ :; }}
run_shell_step() {{ :; }}
run_postgres_backup_step() {{ :; }}
run_frontend_build_step() {{ :; }}
promote_frontend_build_step() {{ printf 'PROMOTED\n'; }}
run_release_gates() {{ :; }}
run_step() {{
  printf 'step:%s\n' "$1"
  if [[ "$1" == "Quiesce all production writer units before rollback backup and database migration" ]]; then
    return 41
  fi
}}
bash() {{ printf 'cleanup:%s\n' "$*"; }}
main
"""

        result = self.run_bash(bash)

        self.assertNotEqual(result.returncode, 0)
        self.assertNotIn("PROMOTED", result.stdout)
        self.assertIn("prod-systemd.sh quiesce-search-writers", result.stdout)
        self.assertIn("keeping search-writing app units quiesced", result.stderr)


if __name__ == "__main__":
    unittest.main()
