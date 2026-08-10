from __future__ import annotations

import re
from pathlib import Path


SRC_ROOT = Path(__file__).parents[1] / "src" / "open_alm_api"
WORKER_SRC_ROOT = Path(__file__).parents[2] / "worker" / "src" / "open_alm_worker"
ALLOWED_DIRECT_LLM_CALL_FILES = {
    Path("core/llm.py"),
    Path("core/llm_execution_adapters.py"),
    Path("domains/ai/gateway.py"),
}
DIRECT_LLM_CALL_PATTERN = re.compile(
    r"\b(?:complete_chat|complete_chat_text|complete_chat_stream|resolve_chat_execution)\s*\("
)
LEGACY_GATEWAY_CALL_PATTERN = re.compile(
    r"\b(?:complete_gateway_chat|complete_gateway_chat_text|complete_gateway_chat_stream|"
    r"ai_gateway_request_from_task_context)\s*\("
)
PLATFORM_GATEWAY_RUNTIME_FILES = {
    Path("domains/ai/agent.py"),
    Path("domains/ai/gateway.py"),
    Path("domains/ai/router.py"),
}
PROVIDER_CALL_PATTERN = re.compile(
    r"^\s*from\s+(?:anthropic|openai|agents(?:\.[\w.]+)?)\s+import\s+|"
    r"/(?:chat/completions|v1/messages)[\"']"
)
ALLOWED_PROVIDER_ADAPTER_FILES = {
    Path("core/llm.py"),
    Path("core/llm_execution_adapters.py"),
    Path("core/llm_official_providers.py"),
    Path("domains/ai/model_discovery.py"),
    Path("domains/ppt_generator/anthropic_search_adapter.py"),
    Path("domains/images/agent_runtime.py"),
    Path("domains/rag/providers/local.py"),
    Path("domains/rag/providers/openai_compatible.py"),
    Path("domains/web_search/service.py"),
}


def test_domain_code_routes_llm_chat_calls_through_ai_gateway() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative_path = path.relative_to(SRC_ROOT)
        if relative_path in ALLOWED_DIRECT_LLM_CALL_FILES:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if DIRECT_LLM_CALL_PATTERN.search(line):
                violations.append(f"{relative_path}:{line_number}:{line.strip()}")

    assert violations == []


def test_domain_workloads_use_registered_llm_facade() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative_path = path.relative_to(SRC_ROOT)
        if relative_path in PLATFORM_GATEWAY_RUNTIME_FILES:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if LEGACY_GATEWAY_CALL_PATTERN.search(line):
                violations.append(f"api/{relative_path}:{line_number}:{line.strip()}")
    for path in sorted(WORKER_SRC_ROOT.rglob("*.py")):
        relative_path = path.relative_to(WORKER_SRC_ROOT)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if LEGACY_GATEWAY_CALL_PATTERN.search(line):
                violations.append(f"worker/{relative_path}:{line_number}:{line.strip()}")

    assert violations == []


def test_provider_sdk_calls_stay_in_registered_adapters() -> None:
    violations: list[str] = []
    for path in sorted(SRC_ROOT.rglob("*.py")):
        relative_path = path.relative_to(SRC_ROOT)
        if relative_path in ALLOWED_PROVIDER_ADAPTER_FILES:
            continue
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PROVIDER_CALL_PATTERN.search(line):
                violations.append(f"api/{relative_path}:{line_number}:{line.strip()}")

    for path in sorted(WORKER_SRC_ROOT.rglob("*.py")):
        relative_path = path.relative_to(WORKER_SRC_ROOT)
        for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
            if PROVIDER_CALL_PATTERN.search(line):
                violations.append(f"worker/{relative_path}:{line_number}:{line.strip()}")

    assert violations == []
