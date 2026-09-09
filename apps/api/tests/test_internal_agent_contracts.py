from __future__ import annotations

import pytest
from pydantic import ValidationError

from open_work_hub_api.domains.ai.internal_agent_contracts import LocalAgentResult, LocalAgentTask
from open_work_hub_api.domains.ai.local_gateway_request import build_gateway_tool_request


def _task(**overrides) -> LocalAgentTask:
    payload = {
        "agent_id": "domain.docs",
        "objective": "Summarize internal docs safely.",
        "allowed_tool_names": ["docs.search"],
        "context_boundary": "company_current",
        "expected_output": "redacted summary",
    }
    payload.update(overrides)
    return LocalAgentTask(**payload)


def test_local_agent_result_allows_redacted_summary_only() -> None:
    result = LocalAgentResult(
        agent_id="domain.docs",
        status="completed",
        redacted_summary="문서 3건에서 일정 지연 가능성이 확인되었습니다.",
        artifact_refs=["artifact:summary-1"],
        coverage={"covered": ["일정", "리스크"], "missing": []},
        sensitivity_labels=["internal"],
    )

    assert result.redacted_summary.startswith("문서 3건")
    assert result.artifact_refs == ["artifact:summary-1"]


def test_local_agent_result_rejects_raw_internal_data() -> None:
    with pytest.raises(ValidationError, match="payload contains forbidden entity types"):
        LocalAgentResult(
            agent_id="domain.pms",
            status="completed",
            redacted_summary="가상고객A TEST-DX-2400 ORD-TEST-001 계약 리스크가 있습니다.",
            coverage={"covered": ["계약"]},
        )


def test_local_agent_task_recursively_rejects_unsafe_tool_arguments() -> None:
    with pytest.raises(ValidationError, match="payload contains forbidden entity types"):
        LocalAgentTask(
            agent_id="domain.rag",
            objective="Find internal evidence and return only a summary.",
            allowed_tool_names=["retrieval.search"],
            tool_arguments={"filters": {"clauses": [{"raw": "ORD-TEST-001"}]}},
            context_boundary="company_current",
            expected_output="redacted summary with gaps",
        )


def test_domain_specialist_prefers_domain_gateway_tool_before_rag() -> None:
    request = build_gateway_tool_request(
        task=_task(
            agent_id="domain.pms",
            objective="critical launch blocker status",
            allowed_tool_names=[],
        ),
        available_tool_names=frozenset({"retrieval.search", "pms.search_tasks"}),
    )

    assert request is not None
    assert request.tool_name == "pms.search_tasks"
    assert request.arguments == {"q": "critical launch blocker", "limit": 10}


def test_domain_rag_gateway_prefers_retrieval_before_legacy_rag() -> None:
    request = build_gateway_tool_request(
        task=_task(
            agent_id="domain.rag",
            objective="release evidence",
            allowed_tool_names=[],
        ),
        available_tool_names=frozenset({"retrieval.search", "rag.query"}),
    )

    assert request is not None
    assert request.tool_name == "retrieval.search"


def test_domain_rag_gateway_falls_back_when_retrieval_is_hidden() -> None:
    request = build_gateway_tool_request(
        task=_task(
            agent_id="domain.rag",
            objective="release evidence",
            allowed_tool_names=[],
        ),
        available_tool_names=frozenset({"rag.query"}),
    )

    assert request is not None
    assert request.tool_name == "rag.query"


def test_domain_docs_gateway_uses_source_kinds_not_app_id() -> None:
    request = build_gateway_tool_request(
        task=_task(
            objective="manual rollout plan",
            allowed_tool_names=["retrieval.search"],
        ),
        available_tool_names=frozenset({"retrieval.search"}),
    )

    assert request is not None
    assert request.tool_name == "retrieval.search"
    assert request.arguments["sources"] == ["generic_rag"]
    assert "manual" in request.arguments["source_kinds"]
    assert "docs" not in request.arguments["source_kinds"]
