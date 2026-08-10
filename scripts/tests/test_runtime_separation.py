from __future__ import annotations

import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path
from typing import Mapping, Sequence


MODULE_PATH = Path(__file__).resolve().parents[1] / "check-runtime-separation.py"
SPEC = importlib.util.spec_from_file_location("check_runtime_separation", MODULE_PATH)
runtime_separation = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = runtime_separation
assert SPEC.loader is not None
SPEC.loader.exec_module(runtime_separation)


DEV_ENV = """\
OPEN_ALM_ENV_PROFILE=dev
OPEN_ALM_API_ENVIRONMENT=development
OPEN_ALM_API_INSTANCE_ID=dev-api
OPEN_ALM_API_SERVE_FRONTEND=false
OPEN_ALM_API_ALLOW_DEV_ADMIN_LOGIN=1
COMPOSE_PROJECT_NAME=open-alm-dev
OPEN_ALM_INFRA_CONTAINER_PREFIX=open-alm-dev
OPEN_ALM_MINIO_BUCKET=open-alm-dev
OPEN_ALM_OPENSEARCH_INDEX_PREFIX=open-alm-dev
OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX=open-alm-dev-rag
OPEN_ALM_DRAWIO_BIND_HOST=0.0.0.0
OPEN_ALM_DRAWIO_SERVER_URL=
"""

PROD_ENV = """\
OPEN_ALM_ENV_PROFILE=prod
OPEN_ALM_API_ENVIRONMENT=production
OPEN_ALM_API_INSTANCE_ID=prod-api
OPEN_ALM_API_SERVE_FRONTEND=true
OPEN_ALM_API_ALLOW_DEV_ADMIN_LOGIN=0
COMPOSE_PROJECT_NAME=open-alm-prod
OPEN_ALM_INFRA_CONTAINER_PREFIX=open-alm-prod
OPEN_ALM_MINIO_BUCKET=open-alm-prod
OPEN_ALM_OPENSEARCH_INDEX_PREFIX=open-alm-prod
OPEN_ALM_RAG_QDRANT_COLLECTION_PREFIX=open-alm-prod-rag
OPEN_ALM_DRAWIO_BIND_HOST=127.0.0.1
OPEN_ALM_DRAWIO_PORT=18083
OPEN_ALM_DRAWIO_SERVER_URL=https://drawio.open-alm.example/
OPEN_ALM_API_DEV_LOGIN_ALLOWED_HOSTS=
OPEN_ALM_PROD_SMOKE_WEB_HOST=prod.example.test
OPEN_ALM_PROD_SMOKE_WORKSPACE_PATH=/w/prod-smoke
"""


class FakeRuntimeAdapter:
    def __init__(
        self,
        *,
        text_by_path: Mapping[Path, str],
        exists_by_path: Mapping[Path, bool] | None = None,
        json_by_url: Mapping[tuple[str, str | None], Mapping[str, object] | None]
        | None = None,
        command_by_args: Mapping[tuple[str, ...], str] | None = None,
    ) -> None:
        self.text_by_path = dict(text_by_path)
        self.exists_by_path = dict(exists_by_path or {})
        self.json_by_url = dict(json_by_url or {})
        self.command_by_args = dict(command_by_args or {})
        self.fetch_calls: list[tuple[str, str | None]] = []
        self.command_calls: list[tuple[str, ...]] = []

    def path_exists(self, path: Path) -> bool:
        return self.exists_by_path.get(path, False)

    def read_text(self, path: Path) -> str | None:
        return self.text_by_path.get(path)

    def fetch_json(
        self,
        url: str,
        *,
        host: str | None = None,
    ) -> Mapping[str, object] | None:
        self.fetch_calls.append((url, host))
        return self.json_by_url.get((url, host))

    def command_text(self, args: Sequence[str]) -> str:
        key = tuple(args)
        self.command_calls.append(key)
        return self.command_by_args.get(key, "")


class RuntimeSeparationScannerTest(unittest.TestCase):
    def passing_texts(self, root: Path) -> dict[Path, str]:
        texts = {
            root
            / "package.json": (
                '{\n'
                '  "scripts": {\n'
                '    "check:env-contract": '
                '"python3 scripts/check-env-contract.py",\n'
                '    "check:runtime-separation:live": '
                '"python3 scripts/check-runtime-separation.py --mode live",\n'
                '    "ci:harness": '
                '"pnpm nx run ci-harness:ci --parallel=4 '
                '--outputStyle=static --skip-nx-cache"\n'
                "  }\n"
                "}\n"
            ),
            root
            / "scripts/ci/project.json": (
                '{"targets":{'
                '"env-contract":{"cache":false,"options":{"command":"pnpm check:env-contract"}},'
                '"runtime-separation":{"cache":false,"options":{"command":"pnpm check:runtime-separation"}},'
                '"skills":{"cache":false,"options":{"command":"pnpm check:skills"}},'
                '"path-hardcoding":{"cache":false,"options":{"command":"pnpm check:path-hardcoding"}},'
                '"ci":{"dependsOn":["env-contract","runtime-separation","skills","path-hardcoding"]}'
                '}}\n'
            ),
            root / "apps/api/project.json": "${OPEN_ALM_API_DEV_PORT:-8001}\n",
            root / "ops/dev/nginx.conf.template": "proxy_pass http://dev-api;\n",
            root
            / "ops/compose/open-alm-dev.infra.yml": (
                "container_name: open-alm-dev-drawio\n"
                '${OPEN_ALM_DRAWIO_BIND_HOST:-0.0.0.0}\n'
                "healthcheck:\n"
                "condition: service_healthy\n"
            ),
            root
            / "ops/compose/open-alm-prod.infra.yml": (
                "container_name: open-alm-prod-drawio\n"
                '${OPEN_ALM_DRAWIO_BIND_HOST:-127.0.0.1}\n'
                '${OPEN_ALM_DRAWIO_PORT:-18083}\n'
                "healthcheck:\n"
            ),
            root
            / "ops/nginx/open-alm.example.proxy-only.conf": (
                "server_name drawio.open-alm.example;\n"
                "proxy_pass http://127.0.0.1:18083;\n"
                "location /drawio/ {\n"
                "  rewrite ^/drawio/(.*)$ https://drawio.open-alm.example/$1 permanent;\n"
                "}\n"
            ),
            root / "scripts/prod-systemd.sh": "require_prod_checkout\n",
            root / "scripts/infra-stack.sh": "require_matching_checkout\n",
            root
            / "scripts/dev-env.sh": 'OPEN_ALM_ENV_PROFILE="${OPEN_ALM_ENV_PROFILE:-dev}"\n',
            root / ".env.example": DEV_ENV,
            root.parent / "dev" / ".env": DEV_ENV,
            root.parent / "prod" / ".env": PROD_ENV,
        }
        for filename, required_settings in (
            runtime_separation.REQUIRED_SYSTEMD_TEMPLATE_SETTINGS.items()
        ):
            texts[root / "ops" / "systemd" / "user" / filename] = "\n".join(
                sorted(required_settings)
            )
        return texts

    def messages(self, report) -> str:
        return "\n".join(failure.message for failure in report.failures)

    def codes(self, report) -> set[str]:
        return {failure.code for failure in report.failures}

    def passing_live_systemd_units(self) -> dict[tuple[str, ...], str]:
        unit_texts = {
            "open-alm-prod-api.service": (
                "WorkingDirectory=/projects/open-alm/prod/apps/api\n"
                "ExecStart=/projects/open-alm/prod/apps/api/.venv/bin/python -m uvicorn open_alm_api.app:app\n"
            ),
            "open-alm-prod-collab.service": (
                "WorkingDirectory=/projects/open-alm/prod/apps/api\n"
                "Environment=OPEN_ALM_API_INSTANCE_ID=prod-collab\n"
                "ExecStart=/projects/open-alm/prod/apps/api/.venv/bin/python -m uvicorn "
                "open_alm_api.app:app --port 8009\n"
            ),
            "open-alm-prod-worker.service": (
                "WorkingDirectory=/projects/open-alm/prod/apps/worker\n"
                "Environment=PYTHONPATH=/projects/open-alm/prod/apps/worker/src\n"
                "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=default\n"
                "ExecStart=/projects/open-alm/prod/apps/worker/.venv/bin/python -m celery "
                "-A open_alm_worker.celery_app:celery_app worker "
                "--hostname=open-alm-prod-worker-default@prod-host -Q celery\n"
            ),
            "open-alm-prod-worker-realtime.service": (
                "WorkingDirectory=/projects/open-alm/prod/apps/worker\n"
                "Environment=PYTHONPATH=/projects/open-alm/prod/apps/worker/src\n"
                "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=realtime\n"
                "ExecStart=/projects/open-alm/prod/apps/worker/.venv/bin/python -m celery "
                "-A open_alm_worker.celery_app:celery_app worker "
                "--hostname=open-alm-prod-worker-realtime@prod-host -Q mail_sync,rag_sync_realtime\n"
            ),
            "open-alm-prod-worker-long.service": (
                "WorkingDirectory=/projects/open-alm/prod/apps/worker\n"
                "Environment=PYTHONPATH=/projects/open-alm/prod/apps/worker/src\n"
                "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=long\n"
                "ExecStart=/projects/open-alm/prod/apps/worker/.venv/bin/python -m celery "
                "-A open_alm_worker.celery_app:celery_app worker "
                "--hostname=open-alm-prod-worker-long@prod-host -Q meeting_transcribe,image_generation\n"
            ),
            "open-alm-prod-worker-ai-graph.service": (
                "WorkingDirectory=/projects/open-alm/prod/apps/worker\n"
                "Environment=PYTHONPATH=/projects/open-alm/prod/apps/worker/src\n"
                "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=ai_graph\n"
                "ExecStart=/projects/open-alm/prod/apps/worker/.venv/bin/python -m celery "
                "-A open_alm_worker.celery_app:celery_app worker "
                "--hostname=open-alm-prod-worker-ai-graph@prod-host -Q ai-graph\n"
            ),
            "open-alm-prod-worker-ppt.service": (
                "WorkingDirectory=/projects/open-alm/prod/apps/worker\n"
                "Environment=PYTHONPATH=/projects/open-alm/prod/apps/worker/src\n"
                "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=ppt\n"
                "ExecStart=/projects/open-alm/prod/apps/worker/.venv/bin/python -m celery "
                "-A open_alm_worker.celery_app:celery_app worker "
                "--hostname=open-alm-prod-worker-ppt@prod-host -Q ppt_generation\n"
            ),
            "open-alm-prod-worker-beat.service": (
                "WorkingDirectory=/projects/open-alm/prod/apps/worker\n"
                "Environment=PYTHONPATH=/projects/open-alm/prod/apps/worker/src\n"
                "Environment=OPEN_ALM_WORKER_QUEUE_GROUP=beat\n"
                "ExecStart=/projects/open-alm/prod/apps/worker/.venv/bin/python -m celery "
                "-A open_alm_worker.celery_app:celery_app beat --loglevel=info "
                "--schedule /projects/open-alm/prod/.runtime/celerybeat-schedule.db\n"
            ),
            "open-alm-dev-app.service": "WorkingDirectory=/projects/open-alm/dev\n",
        }
        return {
            ("systemctl", "--user", "cat", unit_name): unit_text
            for unit_name, unit_text in unit_texts.items()
        } | {
            (
                "docker",
                "inspect",
                "--format",
                "{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}",
                "open-alm-prod-drawio",
            ): "healthy\n",
            ("curl", "-fsSI", "http://127.0.0.1:18083/"): "HTTP/1.1 200 OK\n",
        }

    def test_static_report_uses_fake_adapter_without_live_calls(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dev"
            adapter = FakeRuntimeAdapter(text_by_path=self.passing_texts(root.resolve()))

            report = runtime_separation.build_report(
                root,
                mode="static",
                adapter=adapter,
            )

        self.assertTrue(report.ok)
        self.assertEqual([], adapter.fetch_calls)
        self.assertEqual([], adapter.command_calls)

    def test_env_failures_do_not_print_secret_values(self) -> None:
        secret = "secret-production-profile"
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dev"
            texts = self.passing_texts(root.resolve())
            texts[root.resolve().parent / "prod" / ".env"] = PROD_ENV.replace(
                "OPEN_ALM_API_ENVIRONMENT=production",
                f"OPEN_ALM_API_ENVIRONMENT={secret}",
            )
            adapter = FakeRuntimeAdapter(text_by_path=texts)

            report = runtime_separation.build_report(
                root,
                mode="static",
                adapter=adapter,
            )

        self.assertIn("env_key_unexpected", self.codes(report))
        self.assertIn("prod: OPEN_ALM_API_ENVIRONMENT", self.messages(report))
        self.assertNotIn(secret, self.messages(report))

    def test_static_file_policy_reports_named_failures(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dev"
            texts = self.passing_texts(root.resolve())
            texts[root.resolve() / "package.json"] = '{"scripts":{"vm:app":"node vm.js"}}'
            adapter = FakeRuntimeAdapter(
                text_by_path=texts,
                exists_by_path={
                    root.resolve() / "scripts" / "vm-app-stack.sh": True,
                },
            )

            report = runtime_separation.build_report(
                root,
                mode="static",
                adapter=adapter,
            )

        self.assertIn("preview_vm_script_present", self.codes(report))
        self.assertIn("vm_app_script_present", self.codes(report))
        self.assertIn("scripts/vm-app-stack.sh must be removed", self.messages(report))
        self.assertIn("package.json still exposes vm:app scripts", self.messages(report))

    def test_ci_harness_requires_all_runtime_contract_targets(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dev"
            texts = self.passing_texts(root.resolve())
            ci_project_path = root.resolve() / "scripts/ci/project.json"
            texts[ci_project_path] = texts[ci_project_path].replace(
                '"skills",', ""
            )
            adapter = FakeRuntimeAdapter(text_by_path=texts)

            report = runtime_separation.build_report(
                root,
                mode="static",
                adapter=adapter,
            )

        self.assertIn("ci_harness_runtime_checks_missing", self.codes(report))

    def test_prod_nginx_must_not_proxy_the_inference_gateway_publicly(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dev"
            texts = self.passing_texts(root.resolve())
            texts[root.resolve() / "ops/nginx/open-alm.example.proxy-only.conf"] += (
                "location   ^~   /inference-gateway/ {\n"
                "  proxy_pass   http://127.0.0.1:18080;\n"
                "}\n"
            )
            adapter = FakeRuntimeAdapter(text_by_path=texts)

            report = runtime_separation.build_report(
                root,
                mode="static",
                adapter=adapter,
            )

        self.assertIn("prod_inference_gateway_public_proxy_present", self.codes(report))

    def test_live_report_uses_fake_health_and_systemd_adapter(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dev"
            adapter = FakeRuntimeAdapter(
                text_by_path=self.passing_texts(root.resolve()),
                json_by_url={
                    ("http://127.0.0.1:8000/healthz", None): {
                        "environment": "production",
                        "instance_id": "prod-api",
                    },
                    (
                        "http://127.0.0.1:8000/api/v1/auth/bootstrap-status",
                        "prod.example.test",
                    ): {"dev_admin_login_available": False},
                    ("http://127.0.0.1:8009/healthz", None): {
                        "environment": "production",
                        "instance_id": "prod-collab",
                    },
                    ("http://127.0.0.1:8001/healthz", None): {
                        "environment": "development",
                    },
                },
                command_by_args=self.passing_live_systemd_units(),
            )

            report = runtime_separation.build_report(
                root,
                mode="live",
                adapter=adapter,
            )

        self.assertTrue(report.ok)
        self.assertEqual(4, len(adapter.fetch_calls))
        self.assertEqual(
            len(runtime_separation.LIVE_SYSTEMD_UNIT_EXPECTATIONS) + 2,
            len(adapter.command_calls),
        )

    def test_live_report_checks_prod_worker_unit_contracts(self) -> None:
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory) / "dev"
            command_by_args = self.passing_live_systemd_units()
            command_by_args[
                ("systemctl", "--user", "cat", "open-alm-prod-worker-realtime.service")
            ] = (
                "WorkingDirectory=/projects/open-alm/dev/apps/worker\n"
                "Environment=PYTHONPATH=/projects/open-alm/prod/apps/worker/src\n"
                "ExecStart=/projects/open-alm/prod/apps/worker/.venv/bin/python -m celery\n"
            )
            adapter = FakeRuntimeAdapter(
                text_by_path=self.passing_texts(root.resolve()),
                json_by_url={
                    ("http://127.0.0.1:8000/healthz", None): {
                        "environment": "production",
                        "instance_id": "prod-api",
                    },
                    (
                        "http://127.0.0.1:8000/api/v1/auth/bootstrap-status",
                        "prod.example.test",
                    ): {"dev_admin_login_available": False},
                    ("http://127.0.0.1:8009/healthz", None): {
                        "environment": "production",
                        "instance_id": "prod-collab",
                    },
                    ("http://127.0.0.1:8001/healthz", None): {
                        "environment": "development",
                    },
                },
                command_by_args=command_by_args,
            )

            report = runtime_separation.build_report(
                root,
                mode="live",
                adapter=adapter,
            )

        self.assertIn("prod_worker_realtime_systemd_unit_dev_checkout", self.codes(report))
        self.assertIn("prod_worker_realtime_systemd_unit_missing_contract", self.codes(report))
        self.assertIn("open-alm-prod-worker-realtime.service", self.messages(report))


if __name__ == "__main__":
    unittest.main()
