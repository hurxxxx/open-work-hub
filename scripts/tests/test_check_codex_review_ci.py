from __future__ import annotations

import subprocess
import tempfile
import unittest
from pathlib import Path

import yaml


REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "codex-review-ci.sh"
ROOT_CI = REPO_ROOT / ".gitlab-ci.yml"
EXTERNAL_CI = REPO_ROOT / "ops" / "ci" / "ci-first.gitlab-ci.yml"
CONFIGURE_CI_VALIDATION_ENV = (
    REPO_ROOT / "scripts" / "configure-ci-validation-env.sh"
)
CONTRACT = "feature-codex-release-v1"


def run(*args: str, stdin: str | None = None) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(SCRIPT), *args],
        cwd=REPO_ROOT,
        input=stdin,
        check=False,
        capture_output=True,
        text=True,
    )


def review(decision: str = "MERGE_READY") -> str:
    return f"""## 운영 배포 전 필수 수정

운영 배포 차단 사항 없음.

## 통합 적합성 검토
- 검토 영역: CI 계약
- 프로젝트 계약: feature MR은 Codex만, dev→main은 release validation만 실행
- 결과 및 근거: 파이프라인 경계가 분리됨

## 병합 가능 여부
- 판단: {decision}
- 근거: 통합 차단 사항 없음
- 사용자 행동: GitLab 결과 확인

## 후속 이슈 후보
없음.

## 검증 및 잔여 위험
없음.

## 확인한 명령
git diff --check
"""


class GitlabCiContractTests(unittest.TestCase):
    def validate_ci(self, path: Path) -> subprocess.CompletedProcess[str]:
        return run("--validate-gitlab-ci-contract", str(path))

    def test_root_and_external_ci_share_one_contract(self) -> None:
        self.assertEqual(ROOT_CI.read_bytes(), EXTERNAL_CI.read_bytes())
        for path in (ROOT_CI, EXTERNAL_CI):
            result = self.validate_ci(path)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertEqual(result.stdout.strip(), CONTRACT)

    def test_ci_has_exactly_two_mr_lanes(self) -> None:
        config = yaml.safe_load(EXTERNAL_CI.read_text(encoding="utf-8"))
        feature_rule = (
            '$CI_PIPELINE_SOURCE == "merge_request_event" && '
            '$CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "dev" && '
            '$CI_MERGE_REQUEST_SOURCE_PROJECT_ID == $CI_PROJECT_ID'
        )
        release_rule = (
            '$CI_PIPELINE_SOURCE == "merge_request_event" && '
            '$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME == "dev" && '
            '$CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "main" && '
            '$CI_MERGE_REQUEST_SOURCE_PROJECT_ID == $CI_PROJECT_ID'
        )
        self.assertEqual(
            config["codex_review"]["rules"],
            [{"if": feature_rule, "when": "always"}],
        )
        self.assertEqual(
            config["release_validation"]["rules"],
            [{"if": release_rule}],
        )
        self.assertNotIn("needs", config["codex_review"])
        self.assertFalse(config["codex_review"]["allow_failure"])
        self.assertFalse(config["release_validation"]["allow_failure"])

    def test_contract_rejects_extra_or_weakened_jobs(self) -> None:
        source = EXTERNAL_CI.read_text(encoding="utf-8")
        mutations = (
            source + "\nunexpected_check:\n  script: [true]\n",
            source.replace(
                "  allow_failure: false\n  rules:\n"
                "    - if: '$CI_PIPELINE_SOURCE == \"merge_request_event\" "
                "&& $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == \"dev\"",
                "  allow_failure: true\n  rules:\n"
                "    - if: '$CI_PIPELINE_SOURCE == \"merge_request_event\" "
                "&& $CI_MERGE_REQUEST_TARGET_BRANCH_NAME == \"dev\"",
                1,
            ),
            source.replace(
                '$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME == "dev" && ',
                "",
                1,
            ),
        )
        for mutated in mutations:
            with self.subTest():
                with tempfile.NamedTemporaryFile(
                    "w", encoding="utf-8", suffix=".yml"
                ) as ci_file:
                    ci_file.write(mutated)
                    ci_file.flush()
                    result = self.validate_ci(Path(ci_file.name))
                self.assertNotEqual(result.returncode, 0)

    def test_feature_review_has_no_validation_job_derivation(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertNotIn("derive_required_validation_jobs", source)

    def test_isolated_ci_postgres_uses_test_workload_settings(self) -> None:
        result = subprocess.run(
            ["bash", str(CONFIGURE_CI_VALIDATION_ENV), "--test-postgres-settings"],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "fsync=off",
                "synchronous_commit=off",
                "full_page_writes=off",
                "wal_compression=on",
                "max_wal_size=8GB",
                "checkpoint_timeout=1min",
                "checkpoint_completion_target=0",
            ],
        )

    def test_isolated_ci_postgres_waits_for_validation_bridge(self) -> None:
        result = subprocess.run(
            [
                "bash",
                str(CONFIGURE_CI_VALIDATION_ENV),
                "--test-postgres-systemd-drop-in",
            ],
            cwd=REPO_ROOT,
            check=False,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(
            result.stdout.splitlines(),
            [
                "[Unit]",
                "Wants=network-online.target docker.service",
                "After=network-online.target docker.service",
            ],
        )


class ReviewGateTests(unittest.TestCase):
    def validate_review(self, source: str) -> subprocess.CompletedProcess[str]:
        with tempfile.NamedTemporaryFile("w", encoding="utf-8") as review_file:
            review_file.write(source)
            review_file.flush()
            return run("--validate-review-contract", review_file.name)

    def test_review_contract_accepts_one_decision(self) -> None:
        result = self.validate_review(review())
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertEqual(result.stdout.strip(), "MERGE_READY")

    def test_review_contract_rejects_duplicate_decisions(self) -> None:
        result = self.validate_review(review() + "\nMERGE_BLOCKED\n")
        self.assertNotEqual(result.returncode, 0)

    def test_runner_preconditions_override_llm_ready(self) -> None:
        for index, states in enumerate(
            (
                ("invalid", "ok", "ok"),
                ("ok", "blocked", "ok"),
                ("ok", "ok", "blocked"),
            )
        ):
            with self.subTest(index=index):
                result = run(
                    "--effective-review-decision",
                    "MERGE_READY",
                    states[0],
                    states[1],
                    states[2],
                    "ok",
                )
                self.assertEqual(result.stdout.strip(), "MERGE_BLOCKED")

    def test_runner_keeps_read_only_trust_boundary(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        for token in (
            'features.apps=false',
            'features.remote_plugin=false',
            'features.multi_agent=false',
            'web_search="disabled"',
            "--ignore-user-config",
            "--ignore-rules",
            "--ephemeral",
            "--ask-for-approval never",
        ):
            self.assertIn(token, source)
        self.assertNotIn("required job ${job_name}", source)

    def test_review_prompt_excludes_its_own_running_job_from_blockers(self) -> None:
        source = SCRIPT.read_text(encoding="utf-8")
        self.assertIn(
            "The currently executing canonical codex_review job is necessarily running",
            source,
        )
        self.assertIn(
            "Do not treat that self-state as an unmet prerequisite",
            source,
        )
        self.assertIn(
            "the runner validates the current job identity before review and "
            "revalidates all deterministic gates after review",
            source,
        )

    def test_review_permissions_are_read_only(self) -> None:
        result = run("--print-review-permissions", "/tmp/review")
        self.assertEqual(result.returncode, 0, result.stderr)
        self.assertIn('":workspace_roots"={"."="read"}', result.stdout)
        self.assertNotIn("write", result.stdout)


if __name__ == "__main__":
    unittest.main()
