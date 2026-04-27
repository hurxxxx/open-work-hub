from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field


FIXTURE_DIR = Path(__file__).parent / "fixtures" / "ai_runtime"

REQUIRED_FIXTURES = {
    "routing": "routing_cases.json",
    "grounded_answer": "grounded_answer_cases.json",
    "sanitizer_leakage": "sanitizer_leakage_cases.json",
    "approval_safe_drafting": "approval_safe_drafting_cases.json",
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
