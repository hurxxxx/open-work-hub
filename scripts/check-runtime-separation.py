#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from collections.abc import Iterable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, TypeVar
from urllib.error import URLError
from urllib.request import Request, urlopen


ROOT = Path(__file__).resolve().parents[1]
T = TypeVar("T")

STATIC_TEXT_FILE_PATHS: Mapping[str, Path] = {
    "package_json": Path("package.json"),
    "api_project": Path("apps/api/project.json"),
    "ci_harness_project": Path("scripts/ci/project.json"),
    "dev_nginx_template": Path("ops/dev/nginx.conf.template"),
    "dev_infra_compose": Path("ops/compose/ai-do-dev.infra.yml"),
    "prod_infra_compose": Path("ops/compose/ai-do-prod.infra.yml"),
    "prod_nginx_proxy": Path("ops/nginx/dwdcc.kr.proxy-only.conf"),
    "prod_systemd_script": Path("scripts/prod-systemd.sh"),
    "infra_stack_script": Path("scripts/infra-stack.sh"),
    "dev_env_script": Path("scripts/dev-env.sh"),
}

STATIC_PRESENCE_PATHS: Mapping[str, Path] = {
    "vm_app_stack": Path("scripts/vm-app-stack.sh"),
    "preview_deploy_skill": Path(".agents/skills/ai-do-preview-deploy"),
}

REQUIRED_SYSTEMD_TEMPLATE_SETTINGS: Mapping[str, frozenset[str]] = {
    "ai-do-dev-app.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=control-group",
        }
    ),
    "ai-do-prod-api.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=control-group",
        }
    ),
    "ai-do-prod-collab.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=control-group",
        }
    ),
    "ai-do-prod-worker.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=mixed",
        }
    ),
    "ai-do-prod-worker-long.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=mixed",
        }
    ),
    "ai-do-prod-worker-realtime.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=mixed",
        }
    ),
    "ai-do-prod-worker-ai-graph.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=mixed",
        }
    ),
    "ai-do-prod-worker-ppt.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=mixed",
        }
    ),
    "ai-do-dev-worker-long.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=mixed",
        }
    ),
    "ai-do-dev-worker-ai-graph.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=mixed",
        }
    ),
    "ai-do-dev-worker-ppt.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=mixed",
        }
    ),
    "ai-do-prod-worker-beat.service.template": frozenset(
        {
            "NoNewPrivileges=true",
            "PrivateTmp=true",
            "UMask=0077",
            "KillMode=control-group",
        }
    ),
}
LIVE_SYSTEMD_UNIT_EXPECTATIONS: Mapping[str, tuple[str, tuple[str, ...]]] = {
    "prod_api": (
        "ai-do-prod-api.service",
        (
            "WorkingDirectory=/projects/ai-do/prod/apps/api",
            "/projects/ai-do/prod/apps/api/.venv/bin/python -m uvicorn",
        ),
    ),
    "prod_collab": (
        "ai-do-prod-collab.service",
        (
            "WorkingDirectory=/projects/ai-do/prod/apps/api",
            "Environment=AI_DO_API_INSTANCE_ID=prod-collab",
            "/projects/ai-do/prod/apps/api/.venv/bin/python -m uvicorn",
            "--port 8009",
        ),
    ),
    "prod_worker_default": (
        "ai-do-prod-worker.service",
        (
            "WorkingDirectory=/projects/ai-do/prod/apps/worker",
            "Environment=PYTHONPATH=/projects/ai-do/prod/apps/worker/src",
            "Environment=AI_DO_WORKER_QUEUE_GROUP=default",
            "/projects/ai-do/prod/apps/worker/.venv/bin/python -m celery",
            "--hostname=ai-do-prod-worker-default@",
            "-Q celery",
        ),
    ),
    "prod_worker_realtime": (
        "ai-do-prod-worker-realtime.service",
        (
            "WorkingDirectory=/projects/ai-do/prod/apps/worker",
            "Environment=PYTHONPATH=/projects/ai-do/prod/apps/worker/src",
            "Environment=AI_DO_WORKER_QUEUE_GROUP=realtime",
            "/projects/ai-do/prod/apps/worker/.venv/bin/python -m celery",
            "--hostname=ai-do-prod-worker-realtime@",
        ),
    ),
    "prod_worker_long": (
        "ai-do-prod-worker-long.service",
        (
            "WorkingDirectory=/projects/ai-do/prod/apps/worker",
            "Environment=PYTHONPATH=/projects/ai-do/prod/apps/worker/src",
            "Environment=AI_DO_WORKER_QUEUE_GROUP=long",
            "/projects/ai-do/prod/apps/worker/.venv/bin/python -m celery",
            "--hostname=ai-do-prod-worker-long@",
        ),
    ),
    "prod_worker_ai_graph": (
        "ai-do-prod-worker-ai-graph.service",
        (
            "WorkingDirectory=/projects/ai-do/prod/apps/worker",
            "Environment=PYTHONPATH=/projects/ai-do/prod/apps/worker/src",
            "Environment=AI_DO_WORKER_QUEUE_GROUP=ai_graph",
            "/projects/ai-do/prod/apps/worker/.venv/bin/python -m celery",
            "--hostname=ai-do-prod-worker-ai-graph@",
        ),
    ),
    "prod_worker_ppt": (
        "ai-do-prod-worker-ppt.service",
        (
            "WorkingDirectory=/projects/ai-do/prod/apps/worker",
            "Environment=PYTHONPATH=/projects/ai-do/prod/apps/worker/src",
            "Environment=AI_DO_WORKER_QUEUE_GROUP=ppt",
            "/projects/ai-do/prod/apps/worker/.venv/bin/python -m celery",
            "--hostname=ai-do-prod-worker-ppt@",
        ),
    ),
    "prod_worker_beat": (
        "ai-do-prod-worker-beat.service",
        (
            "WorkingDirectory=/projects/ai-do/prod/apps/worker",
            "Environment=PYTHONPATH=/projects/ai-do/prod/apps/worker/src",
            "Environment=AI_DO_WORKER_QUEUE_GROUP=beat",
            "/projects/ai-do/prod/apps/worker/.venv/bin/python -m celery",
            "--schedule /projects/ai-do/prod/.runtime/celerybeat-schedule.db",
        ),
    ),
    "dev_app": (
        "ai-do-dev-app.service",
        ("WorkingDirectory=/projects/ai-do/dev",),
    ),
}


@dataclass(frozen=True)
class RuntimeSeparationFailure:
    code: str
    message: str


@dataclass(frozen=True)
class PathState:
    name: str
    path: Path
    exists: bool


@dataclass(frozen=True)
class TextFileContent:
    name: str
    path: Path
    text: str | None
    label: str | None = None

    @property
    def display_name(self) -> str:
        return self.label or str(self.path)


@dataclass(frozen=True)
class EnvFileContent:
    name: str
    path: Path
    text: str | None
    required: bool = False


@dataclass(frozen=True)
class ParsedEnvFile:
    name: str
    path: Path
    values: Mapping[str, str]
    missing: bool = False
    required: bool = False

    @property
    def empty(self) -> bool:
        return not self.values


@dataclass(frozen=True)
class JsonEndpointSnapshot:
    name: str
    url: str
    host: str | None
    payload: Mapping[str, object] | None


@dataclass(frozen=True)
class CommandSnapshot:
    name: str
    args: tuple[str, ...]
    text: str


@dataclass(frozen=True)
class RuntimeSeparationSnapshot:
    mode: str
    root: Path
    path_states: tuple[PathState, ...]
    static_files: tuple[TextFileContent, ...]
    env_files: tuple[EnvFileContent, ...]
    systemd_templates: tuple[TextFileContent, ...]
    http_endpoints: tuple[JsonEndpointSnapshot, ...] = ()
    systemd_units: tuple[CommandSnapshot, ...] = ()


@dataclass(frozen=True)
class RuntimeSeparationReport:
    mode: str
    env_files: tuple[ParsedEnvFile, ...]
    failures: tuple[RuntimeSeparationFailure, ...]

    @property
    def ok(self) -> bool:
        return not self.failures

    def success_message(self) -> str:
        return f"{self.mode} ok"


class RuntimeAdapter(Protocol):
    def path_exists(self, path: Path) -> bool:
        ...

    def read_text(self, path: Path) -> str | None:
        ...

    def fetch_json(
        self,
        url: str,
        *,
        host: str | None = None,
    ) -> Mapping[str, object] | None:
        ...

    def command_text(self, args: Sequence[str]) -> str:
        ...


class RuntimeSystemAdapter:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path_exists(self, path: Path) -> bool:
        return path.exists()

    def read_text(self, path: Path) -> str | None:
        if not path.exists():
            return None
        return path.read_text(encoding="utf-8", errors="replace")

    def fetch_json(
        self,
        url: str,
        *,
        host: str | None = None,
    ) -> Mapping[str, object] | None:
        headers = {"Host": host} if host else {}
        request = Request(url, headers=headers)
        try:
            with urlopen(request, timeout=2) as response:
                payload = json.loads(response.read().decode("utf-8"))
        except (OSError, URLError, TimeoutError, json.JSONDecodeError):
            return None
        if not isinstance(payload, dict):
            return None
        return payload

    def command_text(self, args: Sequence[str]) -> str:
        try:
            return subprocess.run(
                list(args),
                cwd=self.root,
                check=False,
                text=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.DEVNULL,
                timeout=5,
            ).stdout
        except (OSError, subprocess.SubprocessError):
            return ""


def read_text(path: Path) -> str:
    return RuntimeSystemAdapter(ROOT).read_text(path) or ""


def parse_env_text(text: str) -> dict[str, str]:
    values: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[7:].strip()
        if "=" not in line:
            continue
        key, value = line.split("=", 1)
        key = key.strip()
        if not key:
            continue
        values[key] = value.strip().strip("\"'")
    return values


def parse_env(path: Path) -> dict[str, str]:
    text = RuntimeSystemAdapter(ROOT).read_text(path)
    if text is None:
        return {}
    return parse_env_text(text)


def fetch_json(url: str, *, host: str | None = None) -> Mapping[str, object] | None:
    return RuntimeSystemAdapter(ROOT).fetch_json(url, host=host)


def command_text(args: Sequence[str]) -> str:
    return RuntimeSystemAdapter(ROOT).command_text(args)


def failure(code: str, message: str) -> RuntimeSeparationFailure:
    return RuntimeSeparationFailure(code=code, message=message)


def by_name(items: Iterable[T]) -> dict[str, T]:
    return {getattr(item, "name"): item for item in items}


def expected_env_values(label: str) -> tuple[dict[str, set[str]], set[str]]:
    if label in {"dev", "example"}:
        return (
            {
                "AI_DO_API_ENVIRONMENT": {"development"},
                "AI_DO_API_INSTANCE_ID": {"dev-api"},
                "AI_DO_API_SERVE_FRONTEND": {"false", "0"},
                "AI_DO_API_ALLOW_DEV_ADMIN_LOGIN": {"1", "true"},
                "COMPOSE_PROJECT_NAME": {"ai-do-dev"},
                "AI_DO_INFRA_CONTAINER_PREFIX": {"ai-do-dev"},
                "AI_DO_MINIO_BUCKET": {"ai-do-dev"},
                "AI_DO_OPENSEARCH_INDEX_PREFIX": {"ai-do-dev"},
                "AI_DO_RAG_QDRANT_COLLECTION_PREFIX": {"ai-do-dev-rag"},
                "AI_DO_DRAWIO_BIND_HOST": {"0.0.0.0"},
                "AI_DO_DRAWIO_SERVER_URL": {""},
            },
            {"dev"},
        )
    return (
        {
            "AI_DO_API_ENVIRONMENT": {"production"},
            "AI_DO_API_INSTANCE_ID": {"prod-api"},
            "AI_DO_API_SERVE_FRONTEND": {"true", "1"},
            "AI_DO_API_ALLOW_DEV_ADMIN_LOGIN": {"0", "false"},
            "COMPOSE_PROJECT_NAME": {"ai-do-prod"},
            "AI_DO_INFRA_CONTAINER_PREFIX": {"ai-do-prod"},
            "AI_DO_MINIO_BUCKET": {"ai-do-prod"},
            "AI_DO_OPENSEARCH_INDEX_PREFIX": {"ai-do-prod"},
            "AI_DO_RAG_QDRANT_COLLECTION_PREFIX": {"ai-do-prod-rag"},
            "AI_DO_DRAWIO_BIND_HOST": {"127.0.0.1"},
            "AI_DO_DRAWIO_PORT": {"18083"},
            "AI_DO_DRAWIO_SERVER_URL": {"https://drawio.dwdcc.kr/"},
        },
        {"prod", "production"},
    )


def parse_env_file(env_file: EnvFileContent) -> ParsedEnvFile:
    if env_file.text is None:
        return ParsedEnvFile(
            name=env_file.name,
            path=env_file.path,
            values={},
            missing=True,
            required=env_file.required,
        )
    return ParsedEnvFile(
        name=env_file.name,
        path=env_file.path,
        values=parse_env_text(env_file.text),
        required=env_file.required,
    )


def check_env_value(
    failures: list[RuntimeSeparationFailure],
    label: str,
    env: Mapping[str, str],
    key: str,
    allowed: set[str],
) -> None:
    expected = sorted(allowed)
    if key not in env:
        failures.append(
            failure(
                "env_key_missing",
                f"{label}: {key} is missing; expected one of {expected}",
            )
        )
    elif env[key] not in allowed:
        failures.append(
            failure(
                "env_key_unexpected",
                f"{label}: {key} has unexpected value; expected one of {expected}",
            )
        )


def evaluate_env_files(
    env_files: Iterable[EnvFileContent],
) -> tuple[tuple[ParsedEnvFile, ...], tuple[RuntimeSeparationFailure, ...]]:
    parsed = tuple(parse_env_file(env_file) for env_file in env_files)
    failures: list[RuntimeSeparationFailure] = []

    for env_file in parsed:
        if env_file.missing:
            if env_file.required:
                failures.append(
                    failure(
                        "env_file_missing",
                        f"{env_file.name}: missing env file at {env_file.path}",
                    )
                )
            continue
        if env_file.empty:
            if env_file.required:
                failures.append(
                    failure(
                        "env_file_empty",
                        f"{env_file.name}: env file is empty at {env_file.path}",
                    )
                )
            continue

        expected, profile_allowed = expected_env_values(env_file.name)
        if env_file.name == "prod" and env_file.values.get(
            "AI_DO_API_DEV_LOGIN_ALLOWED_HOSTS",
            "",
        ):
            failures.append(
                failure(
                    "prod_dev_login_hosts_set",
                    "prod: AI_DO_API_DEV_LOGIN_ALLOWED_HOSTS must be empty",
                )
            )

        check_env_value(
            failures,
            env_file.name,
            env_file.values,
            "AI_DO_ENV_PROFILE",
            profile_allowed,
        )
        for key, allowed in expected.items():
            check_env_value(failures, env_file.name, env_file.values, key, allowed)

    return parsed, tuple(failures)


def evaluate_static_files(
    snapshot: RuntimeSeparationSnapshot,
) -> tuple[RuntimeSeparationFailure, ...]:
    failures: list[RuntimeSeparationFailure] = []
    states = by_name(snapshot.path_states)
    files = by_name(snapshot.static_files)

    if states["vm_app_stack"].exists:
        failures.append(
            failure("preview_vm_script_present", "scripts/vm-app-stack.sh must be removed")
        )
    if states["preview_deploy_skill"].exists:
        failures.append(
            failure(
                "preview_deploy_skill_present",
                "ai-do-preview-deploy skill must be removed",
            )
        )

    package_json = files["package_json"].text or ""
    if "vm:app" in package_json:
        failures.append(
            failure("vm_app_script_present", "package.json still exposes vm:app scripts")
        )
    if '"check:env-contract": "python3 scripts/check-env-contract.py"' not in package_json:
        failures.append(
            failure(
                "env_contract_script_missing",
                "package.json must expose check:env-contract",
            )
        )
    if (
        '"check:runtime-separation:live": '
        '"python3 scripts/check-runtime-separation.py --mode live"'
        not in package_json
    ):
        failures.append(
            failure(
                "runtime_live_script_missing",
                "package.json must expose check:runtime-separation:live",
            )
        )
    ci_harness_project = files["ci_harness_project"].text or ""
    try:
        ci_harness_config = json.loads(ci_harness_project)
    except (json.JSONDecodeError, TypeError):
        ci_harness_config = {}
    ci_harness_targets = ci_harness_config.get("targets", {})
    ci_harness_dependencies = {
        dependency
        for dependency in ci_harness_targets.get("ci", {}).get("dependsOn", [])
        if isinstance(dependency, str)
    }
    required_runtime_targets = {
        "env-contract": "pnpm check:env-contract",
        "runtime-separation": "pnpm check:runtime-separation",
        "skills": "pnpm check:skills",
        "path-hardcoding": "pnpm check:path-hardcoding",
    }
    ci_harness_interface_ok = (
        "pnpm nx run ci-harness:ci" in package_json
        and "--parallel=4" in package_json
        and "--skip-nx-cache" in package_json
    )
    ci_harness_runtime_targets_ok = all(
        target_name in ci_harness_dependencies
        and ci_harness_targets.get(target_name, {}).get("cache") is False
        and ci_harness_targets.get(target_name, {}).get("options", {}).get("command")
        == command
        for target_name, command in required_runtime_targets.items()
    )
    if not ci_harness_interface_ok or not ci_harness_runtime_targets_ok:
        failures.append(
            failure(
                "ci_harness_runtime_checks_missing",
                "ci:harness must depend on uncached env, runtime, skill, and path checks",
            )
        )

    api_project = files["api_project"].text or ""
    if "${AI_DO_API_DEV_PORT:-8000}" in api_project:
        failures.append(
            failure(
                "api_dev_port_uses_prod_default",
                "api project dev/serve targets must not default to prod port 8000",
            )
        )
    if "${AI_DO_API_DEV_PORT:-8001}" not in api_project:
        failures.append(
            failure(
                "api_dev_port_missing_dev_default",
                "api project dev/serve targets must default to dev port 8001",
            )
        )

    nginx_template = files["dev_nginx_template"].text or ""
    if "__AI_DO_DEV_API_UPSTREAM_HOST__:8000" in nginx_template:
        failures.append(
            failure(
                "dev_nginx_uses_prod_api_port",
                "dev nginx upstream must not include prod API port 8000",
            )
        )

    dev_compose = files["dev_infra_compose"].text or ""
    if "ai-do-dev-drawio" not in dev_compose or "service_healthy" not in dev_compose:
        failures.append(
            failure(
                "dev_drawio_healthcheck_missing",
                "dev infra compose must include a healthy draw.io service dependency",
            )
        )
    if "${AI_DO_DRAWIO_BIND_HOST:-0.0.0.0}" not in dev_compose:
        failures.append(
            failure(
                "dev_drawio_bind_default_unexpected",
                "dev draw.io bind host must default to 0.0.0.0 for remote dev access",
            )
        )

    prod_compose = files["prod_infra_compose"].text or ""
    if "ai-do-prod-drawio" not in prod_compose or "healthcheck:" not in prod_compose:
        failures.append(
            failure(
                "prod_drawio_healthcheck_missing",
                "prod infra compose must health-check ai-do-prod-drawio",
            )
        )
    if "${AI_DO_DRAWIO_BIND_HOST:-127.0.0.1}" not in prod_compose:
        failures.append(
            failure(
                "prod_drawio_bind_default_unexpected",
                "prod draw.io bind host must default to 127.0.0.1",
            )
        )
    if "${AI_DO_DRAWIO_PORT:-18083}" not in prod_compose:
        failures.append(
            failure(
                "prod_drawio_port_default_unexpected",
                "prod draw.io must default to 18083 so it cannot collide with dev draw.io",
            )
        )

    prod_nginx_proxy = files["prod_nginx_proxy"].text or ""
    if "server_name drawio.dwdcc.kr" not in prod_nginx_proxy:
        failures.append(
            failure(
                "prod_drawio_origin_missing",
                "prod nginx must expose draw.io on drawio.dwdcc.kr",
            )
        )
    if "proxy_pass http://127.0.0.1:18083" not in prod_nginx_proxy:
        failures.append(
            failure(
                "prod_drawio_proxy_missing",
                "prod nginx must proxy drawio.dwdcc.kr to 127.0.0.1:18083",
            )
        )
    if "location /drawio/" in prod_nginx_proxy and "proxy_pass http://127.0.0.1:18083/" in prod_nginx_proxy:
        failures.append(
            failure(
                "prod_same_origin_drawio_proxy_present",
                "prod nginx must not keep same-origin /drawio/ proxying enabled",
            )
        )
    if re.search(
        r"location\s+(?:\^~\s+)?/inference-gateway/\s*\{"
        r"[^}]*\bproxy_pass\s+http://127\.0\.0\.1:18080\b",
        prod_nginx_proxy,
        flags=re.DOTALL,
    ):
        failures.append(
            failure(
                "prod_inference_gateway_public_proxy_present",
                "prod nginx must not expose the unauthenticated inference gateway publicly",
            )
        )

    if "require_prod_checkout" not in (files["prod_systemd_script"].text or ""):
        failures.append(
            failure(
                "prod_systemd_checkout_guard_missing",
                "prod-systemd.sh is missing prod checkout guard",
            )
        )
    if "require_matching_checkout" not in (files["infra_stack_script"].text or ""):
        failures.append(
            failure(
                "infra_stack_checkout_guard_missing",
                "infra-stack.sh is missing checkout guard",
            )
        )
    if 'AI_DO_ENV_PROFILE="${AI_DO_ENV_PROFILE:-dev}"' not in (
        files["dev_env_script"].text or ""
    ):
        failures.append(
            failure(
                "dev_env_profile_default_missing",
                "dev-env.sh must default AI_DO_ENV_PROFILE to dev",
            )
        )

    return tuple(failures)


def evaluate_systemd_templates(
    templates: Iterable[TextFileContent],
) -> tuple[RuntimeSeparationFailure, ...]:
    failures: list[RuntimeSeparationFailure] = []
    templates_by_name = by_name(templates)
    for filename, required_settings in REQUIRED_SYSTEMD_TEMPLATE_SETTINGS.items():
        template = templates_by_name[filename]
        text = template.text or ""
        if not text:
            failures.append(
                failure("systemd_template_missing", f"{filename}: missing systemd template")
            )
            continue
        for setting in sorted(required_settings):
            if setting not in text:
                failures.append(
                    failure(
                        "systemd_template_setting_missing",
                        f"{filename}: missing {setting}",
                    )
                )
    return tuple(failures)


def evaluate_runtime_http(
    endpoints: Iterable[JsonEndpointSnapshot],
) -> tuple[RuntimeSeparationFailure, ...]:
    failures: list[RuntimeSeparationFailure] = []
    endpoint_by_name = by_name(endpoints)

    prod_health = endpoint_by_name["prod_health"].payload
    if prod_health is None:
        failures.append(
            failure(
                "prod_health_unavailable",
                "prod runtime on :8000 did not respond to /healthz",
            )
        )
    else:
        if prod_health.get("environment") != "production":
            failures.append(
                failure(
                    "prod_health_environment_unexpected",
                    "prod runtime on :8000 must report environment=production",
                )
            )
        if prod_health.get("instance_id") != "prod-api":
            failures.append(
                failure(
                    "prod_health_instance_unexpected",
                    "prod runtime on :8000 must report instance_id=prod-api",
                )
            )

        prod_bootstrap = endpoint_by_name["prod_bootstrap"].payload
        if prod_bootstrap is None:
            failures.append(
                failure(
                    "prod_bootstrap_unavailable",
                    "prod bootstrap-status on :8000 did not respond",
                )
            )
        elif prod_bootstrap.get("dev_admin_login_available") is not False:
            failures.append(
                failure(
                    "prod_bootstrap_dev_login_available",
                    "prod bootstrap-status must disable dev admin login",
                )
            )

    prod_collab_health = endpoint_by_name["prod_collab_health"].payload
    if prod_collab_health is None:
        failures.append(
            failure(
                "prod_collab_health_unavailable",
                "prod collab runtime on :8009 did not respond to /healthz",
            )
        )
    else:
        if prod_collab_health.get("environment") != "production":
            failures.append(
                failure(
                    "prod_collab_health_environment_unexpected",
                    "prod collab runtime on :8009 must report environment=production",
                )
            )
        if prod_collab_health.get("instance_id") != "prod-collab":
            failures.append(
                failure(
                    "prod_collab_health_instance_unexpected",
                    "prod collab runtime on :8009 must report instance_id=prod-collab",
                )
            )

    dev_health = endpoint_by_name["dev_health"].payload
    if dev_health is None:
        failures.append(
            failure(
                "dev_health_unavailable",
                "dev runtime on :8001 did not respond to /healthz",
            )
        )
    elif dev_health.get("environment") != "development":
        failures.append(
            failure(
                "dev_health_environment_unexpected",
                "dev runtime on :8001 must report environment=development",
            )
        )

    return tuple(failures)


def evaluate_systemd_units(
    systemd_units: Iterable[CommandSnapshot],
) -> tuple[RuntimeSeparationFailure, ...]:
    failures: list[RuntimeSeparationFailure] = []
    units_by_name = by_name(systemd_units)

    for name, (unit_name, required_snippets) in LIVE_SYSTEMD_UNIT_EXPECTATIONS.items():
        unit_text = units_by_name[name].text
        if not unit_text:
            failures.append(
                failure(
                    f"{name}_systemd_unit_unreadable",
                    f"{unit_name} is not installed or not readable",
                )
            )
            continue
        if name.startswith("prod_") and "/projects/ai-do/dev" in unit_text:
            failures.append(
                failure(
                    f"{name}_systemd_unit_dev_checkout",
                    f"{unit_name} must not point at /projects/ai-do/dev",
                )
            )
        if name.startswith("prod_") and "__AI_DO_" in unit_text:
            failures.append(
                failure(
                    f"{name}_systemd_unit_unrendered_placeholder",
                    f"{unit_name} must not contain unrendered AI-DO placeholders",
                )
            )
        for snippet in required_snippets:
            if snippet not in unit_text:
                failures.append(
                    failure(
                        f"{name}_systemd_unit_missing_contract",
                        f"{unit_name} must contain {snippet}",
                    )
                )

    return tuple(failures)


def evaluate_drawio_live_commands(
    commands: Iterable[CommandSnapshot],
) -> tuple[RuntimeSeparationFailure, ...]:
    failures: list[RuntimeSeparationFailure] = []
    commands_by_name = by_name(commands)

    health = commands_by_name.get("prod_drawio_container_health")
    if health is None or health.text.strip() != "healthy":
        failures.append(
            failure(
                "prod_drawio_container_unhealthy",
                "ai-do-prod-drawio container health must be healthy",
            )
        )

    http = commands_by_name.get("prod_drawio_http")
    if http is None or "HTTP/" not in http.text:
        failures.append(
            failure(
                "prod_drawio_http_unavailable",
                "prod draw.io runtime on configured port did not respond",
            )
        )

    return tuple(failures)


def evaluate_runtime_separation(
    snapshot: RuntimeSeparationSnapshot,
) -> RuntimeSeparationReport:
    parsed_env_files, env_failures = evaluate_env_files(snapshot.env_files)
    failures: list[RuntimeSeparationFailure] = []
    failures.extend(evaluate_static_files(snapshot))
    failures.extend(evaluate_systemd_templates(snapshot.systemd_templates))
    failures.extend(env_failures)

    if snapshot.mode == "live":
        failures.extend(evaluate_runtime_http(snapshot.http_endpoints))
        failures.extend(evaluate_systemd_units(snapshot.systemd_units))
        failures.extend(evaluate_drawio_live_commands(snapshot.systemd_units))

    return RuntimeSeparationReport(
        mode=snapshot.mode,
        env_files=parsed_env_files,
        failures=tuple(failures),
    )


def checkout_root(root: Path) -> Path:
    return root.parent


def env_file_specs(root: Path) -> tuple[EnvFileContent, ...]:
    root = root.resolve()
    checkout = checkout_root(root)
    return (
        EnvFileContent(
            name="example",
            path=root / ".env.example",
            text=None,
            required=True,
        ),
        EnvFileContent(
            name="dev",
            path=checkout / "dev" / ".env",
            text=None,
        ),
        EnvFileContent(
            name="prod",
            path=checkout / "prod" / ".env",
            text=None,
        ),
    )


def load_text_file(
    name: str,
    path: Path,
    adapter: RuntimeAdapter,
    *,
    label: str | None = None,
) -> TextFileContent:
    return TextFileContent(
        name=name,
        path=path,
        text=adapter.read_text(path),
        label=label,
    )


def build_snapshot(
    root: Path = ROOT,
    *,
    mode: str = "static",
    adapter: RuntimeAdapter | None = None,
) -> RuntimeSeparationSnapshot:
    root = root.resolve()
    adapter = adapter or RuntimeSystemAdapter(root)

    path_states = tuple(
        PathState(name=name, path=root / relative_path, exists=adapter.path_exists(root / relative_path))
        for name, relative_path in STATIC_PRESENCE_PATHS.items()
    )
    static_files = tuple(
        load_text_file(name, root / relative_path, adapter, label=str(relative_path))
        for name, relative_path in STATIC_TEXT_FILE_PATHS.items()
    )
    env_files = tuple(
        EnvFileContent(
            name=env_file.name,
            path=env_file.path,
            text=adapter.read_text(env_file.path),
            required=env_file.required,
        )
        for env_file in env_file_specs(root)
    )
    systemd_templates = tuple(
        load_text_file(
            filename,
            root / "ops" / "systemd" / "user" / filename,
            adapter,
            label=filename,
        )
        for filename in REQUIRED_SYSTEMD_TEMPLATE_SETTINGS
    )
    prod_env_values = parse_env_text(
        next((env_file.text for env_file in env_files if env_file.name == "prod"), "")
        or ""
    )
    prod_smoke_host = prod_env_values.get("AI_DO_PROD_SMOKE_WEB_HOST", "").strip() or None
    prod_drawio_port = prod_env_values.get("AI_DO_DRAWIO_PORT", "18083").strip() or "18083"

    http_endpoints: tuple[JsonEndpointSnapshot, ...] = ()
    systemd_units: tuple[CommandSnapshot, ...] = ()
    if mode == "live":
        prod_health_payload = adapter.fetch_json("http://127.0.0.1:8000/healthz")
        prod_bootstrap_payload = None
        if prod_health_payload is not None:
            prod_bootstrap_payload = adapter.fetch_json(
                "http://127.0.0.1:8000/api/v1/auth/bootstrap-status",
                host=prod_smoke_host,
            )
        http_endpoints = (
            JsonEndpointSnapshot(
                name="prod_health",
                url="http://127.0.0.1:8000/healthz",
                host=None,
                payload=prod_health_payload,
            ),
            JsonEndpointSnapshot(
                name="prod_bootstrap",
                url="http://127.0.0.1:8000/api/v1/auth/bootstrap-status",
                host=prod_smoke_host,
                payload=prod_bootstrap_payload,
            ),
            JsonEndpointSnapshot(
                name="prod_collab_health",
                url="http://127.0.0.1:8009/healthz",
                host=None,
                payload=adapter.fetch_json("http://127.0.0.1:8009/healthz"),
            ),
            JsonEndpointSnapshot(
                name="dev_health",
                url="http://127.0.0.1:8001/healthz",
                host=None,
                payload=adapter.fetch_json("http://127.0.0.1:8001/healthz"),
            ),
        )
        systemd_units = tuple(
            CommandSnapshot(
                name=name,
                args=("systemctl", "--user", "cat", unit_name),
                text=adapter.command_text(
                    ("systemctl", "--user", "cat", unit_name)
                ),
            )
            for name, (unit_name, _required_snippets) in LIVE_SYSTEMD_UNIT_EXPECTATIONS.items()
        ) + (
            CommandSnapshot(
                name="prod_drawio_container_health",
                args=(
                    "docker",
                    "inspect",
                    "--format",
                    "{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}",
                    "ai-do-prod-drawio",
                ),
                text=adapter.command_text(
                    (
                        "docker",
                        "inspect",
                        "--format",
                        "{{if .State.Health}}{{.State.Health.Status}}{{else}}missing-healthcheck{{end}}",
                        "ai-do-prod-drawio",
                    )
                ),
            ),
            CommandSnapshot(
                name="prod_drawio_http",
                args=("curl", "-fsSI", f"http://127.0.0.1:{prod_drawio_port}/"),
                text=adapter.command_text(
                    ("curl", "-fsSI", f"http://127.0.0.1:{prod_drawio_port}/")
                ),
            ),
        )

    return RuntimeSeparationSnapshot(
        mode=mode,
        root=root,
        path_states=path_states,
        static_files=static_files,
        env_files=env_files,
        systemd_templates=systemd_templates,
        http_endpoints=http_endpoints,
        systemd_units=systemd_units,
    )


def build_report(
    root: Path = ROOT,
    *,
    mode: str = "static",
    adapter: RuntimeAdapter | None = None,
) -> RuntimeSeparationReport:
    return evaluate_runtime_separation(build_snapshot(root, mode=mode, adapter=adapter))


def format_report_lines(report: RuntimeSeparationReport) -> tuple[str, ...]:
    if report.failures:
        return tuple(
            f"[runtime-separation] {failure.message}" for failure in report.failures
        )
    return (f"[runtime-separation] {report.success_message()}",)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit AI-DO runtime separation.")
    parser.add_argument(
        "--mode",
        choices=("static", "live"),
        default="static",
        help="static is CI-safe; live requires running prod/dev services.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    report = build_report(ROOT, mode=args.mode)

    if not report.ok:
        for line in format_report_lines(report):
            print(line, file=sys.stderr)
        return 1

    for line in format_report_lines(report):
        print(line)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
