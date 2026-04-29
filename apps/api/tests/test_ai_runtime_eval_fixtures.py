from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field

from aidoo_api.core.settings import Settings
from aidoo_api.domains.ai.runtime.external_egress import evaluate_external_egress
from aidoo_api.domains.ai.runtime.external_planner import (
    build_external_planner_request,
    execute_mock_external_planner,
    summarize_external_planner_execution,
)
from aidoo_api.domains.ai.runtime.external_search import (
    build_external_search_request,
    execute_mock_external_search,
    summarize_external_search_execution,
)


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ai_runtime"

REQUIRED_FIXTURES = {
    "routing": "routing_cases.json",
    "grounded_answer": "grounded_answer_cases.json",
    "sanitizer_leakage": "sanitizer_leakage_cases.json",
    "approval_safe_drafting": "approval_safe_drafting_cases.json",
    "external_execution_summary": "external_execution_summary_cases.json",
}


class AiRuntimeEvalCase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    id: str
    locale: str
    synthetic: bool = True
    tags: list[str] = Field(default_factory=list)
    input: dict[str, Any]
    expected: dict[str, Any]


class AiRuntimeFixture(BaseModel):
    model_config = ConfigDict(extra="forbid")

    schema_version: Literal[1]
    suite: Literal[
        "routing",
        "grounded_answer",
        "sanitizer_leakage",
        "approval_safe_drafting",
        "external_execution_summary",
    ]
    description: str
    cases: list[AiRuntimeEvalCase]


def _load_fixture(path: Path) -> AiRuntimeFixture:
    return AiRuntimeFixture.model_validate(json.loads(path.read_text(encoding="utf-8")))


def test_required_ai_runtime_eval_fixtures_exist_and_validate() -> None:
    assert FIXTURE_DIR.exists()

    for suite, filename in REQUIRED_FIXTURES.items():
        fixture = _load_fixture(FIXTURE_DIR / filename)
        assert fixture.suite == suite
        assert fixture.cases, f"{filename} must include at least one seed case"
        for case in fixture.cases:
            assert case.synthetic is True
            assert case.locale == "ko-KR"
            assert case.id.startswith(f"{suite.split('_')[0]}-")


def test_routing_fixture_locks_phase0_expected_shape() -> None:
    fixture = _load_fixture(FIXTURE_DIR / REQUIRED_FIXTURES["routing"])

    for case in fixture.cases:
        assert {"route", "runtime_profile", "domains", "requires_external"} <= set(
            case.expected
        )
        assert case.expected["route"] in {"fast_path", "graph_path"}
        assert isinstance(case.expected["domains"], list)


def test_grounded_answer_fixture_locks_evidence_expectations() -> None:
    fixture = _load_fixture(FIXTURE_DIR / REQUIRED_FIXTURES["grounded_answer"])

    for case in fixture.cases:
        assert {"required_refs", "unsupported_claims", "citation_required"} <= set(
            case.expected
        )
        assert isinstance(case.expected["required_refs"], list)
        assert case.expected["citation_required"] is True


def test_sanitizer_fixture_locks_leakage_gate_shape() -> None:
    fixture = _load_fixture(FIXTURE_DIR / REQUIRED_FIXTURES["sanitizer_leakage"])

    for case in fixture.cases:
        assert {"allow_external", "removed_entity_types", "sanitized_query"} <= set(
            case.expected
        )
        assert isinstance(case.expected["allow_external"], bool)
        assert isinstance(case.expected["removed_entity_types"], list)
        if case.expected["allow_external"]:
            sanitized_query = case.expected["sanitized_query"]
            assert "가상고객A" not in sanitized_query
            assert "TEST-DX-2400" not in sanitized_query
            assert "ORD-TEST-001" not in sanitized_query


def test_approval_fixture_locks_safe_drafting_boundary() -> None:
    fixture = _load_fixture(FIXTURE_DIR / REQUIRED_FIXTURES["approval_safe_drafting"])

    for case in fixture.cases:
        assert {"approval_required", "allowed_actions", "forbidden_actions"} <= set(
            case.expected
        )
        assert isinstance(case.expected["approval_required"], bool)
        assert isinstance(case.expected["allowed_actions"], list)
        assert isinstance(case.expected["forbidden_actions"], list)


def test_external_execution_fixture_locks_mock_summary_contract() -> None:
    fixture = _load_fixture(FIXTURE_DIR / REQUIRED_FIXTURES["external_execution_summary"])

    for case in fixture.cases:
        assert {"summary"} <= set(case.expected)
        summary = _external_execution_summary_from_case(case)
        assert summary == case.expected["summary"]
        serialized_summary = json.dumps(summary, ensure_ascii=False)
        raw_text = case.input.get("text")
        if isinstance(raw_text, str):
            assert raw_text not in serialized_summary
        assert summary["execution_provider"] == "mock"
        assert summary["raw_output_persisted"] is False
        assert {"latency_ms", "retry_count", "error_class", "estimated_cost_microunits"} <= set(
            summary
        )


def _external_execution_summary_from_case(case: AiRuntimeEvalCase) -> dict[str, Any]:
    adapter = case.input.get("adapter")
    settings = _settings_from_fixture(case.input.get("settings"))
    egress = evaluate_external_egress(
        capability=str(case.input["capability"]),
        provider=str(case.input["provider"]),
        text=str(case.input["text"]),
        settings=settings,
    )
    execution_enabled = bool(case.input.get("execution_enabled"))
    force_error_class = case.input.get("force_error_class")
    error_class = force_error_class if isinstance(force_error_class, str) else None
    if adapter == "planner":
        request = build_external_planner_request(
            egress_decision=egress,
            runtime_profile=str(case.input["runtime_profile"]),
            agent_ids=[
                agent_id
                for agent_id in case.input.get("agent_ids", [])
                if isinstance(agent_id, str)
            ],
        )
        return summarize_external_planner_execution(
            execute_mock_external_planner(
                request,
                execution_enabled=execution_enabled,
                force_error_class=error_class,
            )
        )
    if adapter == "search":
        request = build_external_search_request(egress_decision=egress)
        return summarize_external_search_execution(
            execute_mock_external_search(
                request,
                execution_enabled=execution_enabled,
                force_error_class=error_class,
            )
        )
    raise AssertionError(f"unsupported external execution adapter: {adapter}")


def _settings_from_fixture(raw_settings: Any) -> Settings:
    aliases = {
        "ai_external_llm_enabled": "AIDOO_AI_EXTERNAL_LLM_ENABLED",
        "ai_external_planning_enabled": "AIDOO_AI_EXTERNAL_PLANNING_ENABLED",
        "ai_external_search_enabled": "AIDOO_AI_EXTERNAL_SEARCH_ENABLED",
    }
    settings = raw_settings if isinstance(raw_settings, dict) else {}
    return Settings(
        postgres_dsn="postgresql+psycopg://aidoo_test:aidoo_test@127.0.0.1:5432/aidoo_test",
        **{
            aliases.get(key, key): value
            for key, value in settings.items()
            if isinstance(key, str)
        },
    )


def test_phase0_gate_readme_documents_slo_and_structured_output_targets() -> None:
    readme = (FIXTURE_DIR / "README.md").read_text(encoding="utf-8")

    for term in (
        "concurrent active users",
        "p95 TTFT",
        "p95 report latency",
        "approval wait time",
        "ExecutionGraph",
        "schema success rate",
        "tool-call stability",
        "malformed output rate",
    ):
        assert term in readme
