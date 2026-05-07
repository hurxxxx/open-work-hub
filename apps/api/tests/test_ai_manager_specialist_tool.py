from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from pydantic import ValidationError
import pytest

from ai_do_api.core.llm import LlmTaskContext
from ai_do_api.domains.ai import internal_agents
from ai_do_api.domains.ai.manager_runtime import (
    LocalLlmSpecialistRunner,
    LocalToolGatewaySpecialistRunner,
    RUN_LOCAL_SPECIALIST_TOOL_NAME,
    LocalAgentResult,
    LocalAgentTask,
    StaticLocalSpecialistRunner,
    build_local_specialist_tool_context,
    run_local_specialist,
    validate_local_specialist_task,
)
from ai_do_api.domains.ai.tool_runtime import ToolCallExecution


class CapturingRunner:
    def __init__(self, result: LocalAgentResult) -> None:
        self.result = result
        self.tasks: list[LocalAgentTask] = []

    def run(self, task: LocalAgentTask) -> LocalAgentResult:
        self.tasks.append(task)
        return self.result


class UnsafeRunner:
    def run(self, task: LocalAgentTask) -> LocalAgentResult:
        raise ValidationError.from_exception_data(
            title="LocalAgentResult",
            line_errors=[
                {
                    "type": "value_error",
                    "loc": ("redacted_summary",),
                    "msg": "Value error, unsafe",
                    "input": "가상고객A",
                    "ctx": {"error": ValueError("unsafe")},
                }
            ],
        )


class CrashingRunner:
    def run(self, task: LocalAgentTask) -> LocalAgentResult:
        raise RuntimeError("boom")


def _task(**overrides) -> LocalAgentTask:
    payload = {
        "agent_id": "domain.docs",
        "objective": "Summarize internal docs safely.",
        "allowed_tool_names": ["docs.search"],
        "context_boundary": "workspace_current",
        "expected_output": "redacted summary",
    }
    payload.update(overrides)
    return LocalAgentTask(**payload)


def _context(**overrides):
    payload = {
        "enabled_app_ids": ["ai", "docs"],
        "allowed_app_ids": ["ai", "docs"],
        "available_tool_names": ["docs.search"],
    }
    payload.update(overrides)
    return build_local_specialist_tool_context(**payload)


def test_run_local_specialist_tool_name_is_stable() -> None:
    assert RUN_LOCAL_SPECIALIST_TOOL_NAME == "run_local_specialist"


def test_internal_agents_do_not_import_manager_provider_sdks() -> None:
    source = Path(internal_agents.__file__).read_text(encoding="utf-8")

    assert "from agents " not in source
    assert "import agents" not in source
    assert "openai_adapter" not in source
    assert "claude" not in source.lower()


def test_run_local_specialist_invokes_runner_after_validation() -> None:
    expected = LocalAgentResult(
        agent_id="domain.docs",
        status="completed",
        redacted_summary="문서 요약 결과입니다.",
        coverage={"covered": ["docs"], "missing": []},
        sensitivity_labels=["internal"],
    )
    runner = CapturingRunner(expected)
    task = _task()

    result = run_local_specialist(
        task=task,
        context=_context(),
        runner=runner,
    )

    assert result == expected
    assert runner.tasks == [task]


def test_run_local_specialist_blocks_unknown_or_hidden_agent() -> None:
    result = run_local_specialist(
        task=_task(agent_id="domain.pms"),
        context=_context(enabled_app_ids=["ai", "docs"], allowed_app_ids=["ai", "docs"]),
        runner=StaticLocalSpecialistRunner(),
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "agent_not_available"


def test_run_local_specialist_blocks_scope_without_ai_app() -> None:
    result = run_local_specialist(
        task=_task(),
        context=_context(enabled_app_ids=["docs"], allowed_app_ids=["docs"]),
        runner=StaticLocalSpecialistRunner(),
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "agent_not_available"


def test_run_local_specialist_blocks_unavailable_tool() -> None:
    result = run_local_specialist(
        task=_task(allowed_tool_names=["docs.search", "pms.search"]),
        context=_context(available_tool_names=["docs.search"]),
        runner=StaticLocalSpecialistRunner(),
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "tool_not_available"


def test_run_local_specialist_blocks_approval_required_tool() -> None:
    result = run_local_specialist(
        task=_task(allowed_tool_names=["docs.write"]),
        context=_context(
            available_tool_names=["docs.write"],
            approval_required_tool_names=["docs.write"],
        ),
        runner=StaticLocalSpecialistRunner(),
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "approval_required"


def test_run_local_specialist_allows_approved_write_tool() -> None:
    result = run_local_specialist(
        task=_task(
            agent_id="domain.pms",
            allowed_tool_names=["pms.delete_issue"],
            tool_arguments={"issue_id": "issue-1"},
            approved_call_id="approval-1",
        ),
        context=_context(
            enabled_app_ids=["ai", "pms"],
            allowed_app_ids=["ai", "pms"],
            available_tool_names=["pms.delete_issue"],
            approval_required_tool_names=["pms.delete_issue"],
        ),
        runner=StaticLocalSpecialistRunner(),
    )

    assert result.status == "completed"


def test_validate_local_specialist_task_allows_no_tool_task_for_visible_agent() -> None:
    blocked_reason = validate_local_specialist_task(
        task=_task(allowed_tool_names=[]),
        context=_context(available_tool_names=[]),
    )

    assert blocked_reason is None


def test_run_local_specialist_converts_unsafe_runner_result_to_failure() -> None:
    result = run_local_specialist(
        task=_task(),
        context=_context(),
        runner=UnsafeRunner(),
    )

    assert result.status == "failed"
    assert result.blocked_reason == "unsafe_local_result"
    assert "가상고객A" not in result.redacted_summary


def test_run_local_specialist_converts_runner_exception_to_failure() -> None:
    result = run_local_specialist(
        task=_task(),
        context=_context(),
        runner=CrashingRunner(),
    )

    assert result.status == "failed"
    assert result.blocked_reason == "local_agent_failed"


def _llm_context() -> LlmTaskContext:
    return LlmTaskContext(
        source="api.stream",
        actor_user_id="user-1",
        workspace_id="workspace-1",
        task_kind="chatbot",
    )


def _response(content: str):
    return SimpleNamespace(
        choices=[SimpleNamespace(message=SimpleNamespace(content=content))],
    )


def test_local_llm_specialist_runner_forces_local_pool(monkeypatch: pytest.MonkeyPatch) -> None:
    calls = []

    def fake_complete_chat(context, db, **kwargs):
        calls.append({"context": context, "db": db, "kwargs": kwargs})
        return (_response("로컬 근거 요약입니다."), None, None)

    monkeypatch.setattr(
        "ai_do_api.domains.ai.internal_agents.complete_chat",
        fake_complete_chat,
    )
    runner = LocalLlmSpecialistRunner(
        db=object(),
        llm_context=_llm_context(),
        max_tokens=777,
        conversation_id="conversation-1",
    )

    result = runner.run(_task())

    assert result.status == "completed"
    assert result.redacted_summary == "로컬 근거 요약입니다."
    assert calls[0]["context"].source == "api.stream.local_agent"
    assert calls[0]["kwargs"]["pool_hint"] == "local"
    assert calls[0]["kwargs"]["reasoning_effort"] == "none"
    assert calls[0]["kwargs"]["max_tokens"] == 777
    assert calls[0]["kwargs"]["conversation_id"] == "conversation-1"
    assert calls[0]["kwargs"]["messages"][0]["role"] == "system"
    assert calls[0]["kwargs"]["messages"][1]["role"] == "user"


def test_run_local_specialist_converts_unsafe_local_llm_output(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_complete_chat(context, db, **kwargs):
        del context, db, kwargs
        return (_response("가상고객A ORD-TEST-001 계약 리스크입니다."), None, None)

    monkeypatch.setattr(
        "ai_do_api.domains.ai.internal_agents.complete_chat",
        fake_complete_chat,
    )

    result = run_local_specialist(
        task=_task(),
        context=_context(),
        runner=LocalLlmSpecialistRunner(db=object(), llm_context=_llm_context()),
    )

    assert result.status == "failed"
    assert result.blocked_reason == "unsafe_local_result"
    assert "가상고객A" not in result.redacted_summary


def test_local_tool_gateway_specialist_runner_calls_read_tool_then_local_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_calls = []
    llm_calls = []

    def fake_execute_tool_call(db, **kwargs):
        tool_calls.append({"db": db, "kwargs": kwargs})
        return ToolCallExecution(
            call_id="call-1",
            tool_name=kwargs["tool_name"],
            arguments_json="{}",
            status="ok",
            response={
                "tool": kwargs["tool_name"],
                "result": {
                    "answer": "raw internal result stays local",
                    "sources": [{"id": "artifact-doc-1"}],
                },
            },
        )

    def fake_complete_chat(context, db, **kwargs):
        llm_calls.append({"context": context, "db": db, "kwargs": kwargs})
        return (_response("도구 근거 기반 redacted summary입니다."), None, None)

    monkeypatch.setattr(
        "ai_do_api.domains.ai.internal_agents.execute_tool_call",
        fake_execute_tool_call,
    )
    monkeypatch.setattr(
        "ai_do_api.domains.ai.internal_agents.complete_chat",
        fake_complete_chat,
    )
    runner = LocalToolGatewaySpecialistRunner(
        db=object(),
        workspace=object(),
        principal=object(),
        user=object(),
        llm_context=_llm_context(),
        available_tool_names=frozenset({"rag.query"}),
        conversation_id="conversation-1",
    )

    result = run_local_specialist(
        task=_task(agent_id="domain.docs", allowed_tool_names=[]),
        context=_context(available_tool_names=["rag.query"]),
        runner=runner,
    )

    assert result.status == "completed"
    assert result.redacted_summary == "도구 근거 기반 redacted summary입니다."
    assert result.artifact_refs == ["artifact-doc-1"]
    assert tool_calls[0]["kwargs"]["tool_name"] == "rag.query"
    assert tool_calls[0]["kwargs"]["arguments"]["source_kinds"] == ["docs"]
    assert tool_calls[0]["kwargs"]["source"] == "internal.local_agent"
    assert llm_calls[0]["context"].source == "api.stream.local_agent.tool_summary"
    assert "raw internal result stays local" in llm_calls[0]["kwargs"]["messages"][1]["content"]


def test_local_tool_gateway_specialist_runner_extracts_search_query(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_calls = []

    def fake_execute_tool_call(db, **kwargs):
        tool_calls.append({"db": db, "kwargs": kwargs})
        return ToolCallExecution(
            call_id="call-1",
            tool_name=kwargs["tool_name"],
            arguments_json="{}",
            status="ok",
            response={"tool": kwargs["tool_name"], "result": {"items": []}},
        )

    def fake_complete_chat(context, db, **kwargs):
        del context, db, kwargs
        return (_response("검색 결과 요약입니다."), None, None)

    monkeypatch.setattr(
        "ai_do_api.domains.ai.internal_agents.execute_tool_call",
        fake_execute_tool_call,
    )
    monkeypatch.setattr(
        "ai_do_api.domains.ai.internal_agents.complete_chat",
        fake_complete_chat,
    )
    runner = LocalToolGatewaySpecialistRunner(
        db=object(),
        workspace=object(),
        principal=object(),
        user=object(),
        llm_context=_llm_context(),
        available_tool_names=frozenset({"pms.search_issues"}),
    )

    result = run_local_specialist(
        task=_task(
            agent_id="domain.pms",
            objective="납기 지연 실행 과제의 현재 상태와 우선순위 패턴을 요약해줘.",
            allowed_tool_names=["pms.search_issues"],
        ),
        context=_context(
            enabled_app_ids=["ai", "pms"],
            allowed_app_ids=["ai", "pms"],
            available_tool_names=["pms.search_issues"],
        ),
        runner=runner,
    )

    assert result.status == "completed"
    assert tool_calls[0]["kwargs"]["arguments"]["q"] == "납기 지연"


def test_local_tool_gateway_specialist_runner_returns_blocked_on_approval(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def fake_execute_tool_call(db, **kwargs):
        del db, kwargs
        return ToolCallExecution(
            call_id="call-1",
            tool_name="rag.query",
            arguments_json="{}",
            status="blocked",
            error_message="approval required",
        )

    monkeypatch.setattr(
        "ai_do_api.domains.ai.internal_agents.execute_tool_call",
        fake_execute_tool_call,
    )
    runner = LocalToolGatewaySpecialistRunner(
        db=object(),
        workspace=object(),
        principal=object(),
        user=object(),
        llm_context=_llm_context(),
        available_tool_names=frozenset({"rag.query"}),
    )

    result = run_local_specialist(
        task=_task(agent_id="domain.rag", allowed_tool_names=[]),
        context=_context(available_tool_names=["rag.query"]),
        runner=runner,
    )

    assert result.status == "blocked"
    assert result.blocked_reason == "approval_required"


def test_local_tool_gateway_specialist_runner_executes_approved_write_with_exact_args(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    tool_calls = []

    def fake_execute_tool_call(db, **kwargs):
        tool_calls.append({"db": db, "kwargs": kwargs})
        return ToolCallExecution(
            call_id="call-1",
            tool_name=kwargs["tool_name"],
            arguments_json='{"issue_id":"issue-1"}',
            status="ok",
            response={
                "tool": kwargs["tool_name"],
                "result": {"id": "issue-1", "deleted": True},
            },
        )

    def fake_complete_chat(context, db, **kwargs):
        del context, db, kwargs
        return (_response("승인된 PMS 삭제 결과 요약입니다."), None, None)

    monkeypatch.setattr(
        "ai_do_api.domains.ai.internal_agents.execute_tool_call",
        fake_execute_tool_call,
    )
    monkeypatch.setattr(
        "ai_do_api.domains.ai.internal_agents.complete_chat",
        fake_complete_chat,
    )
    runner = LocalToolGatewaySpecialistRunner(
        db=object(),
        workspace=object(),
        principal=object(),
        user=object(),
        llm_context=_llm_context(),
        available_tool_names=frozenset({"pms.delete_issue"}),
    )

    result = run_local_specialist(
        task=_task(
            agent_id="domain.pms",
            allowed_tool_names=["pms.delete_issue"],
            tool_arguments={"issue_id": "issue-1"},
            approved_call_id="approval-1",
        ),
        context=_context(
            enabled_app_ids=["ai", "pms"],
            allowed_app_ids=["ai", "pms"],
            available_tool_names=["pms.delete_issue"],
            approval_required_tool_names=["pms.delete_issue"],
        ),
        runner=runner,
    )

    assert result.status == "completed"
    assert tool_calls[0]["kwargs"]["tool_name"] == "pms.delete_issue"
    assert tool_calls[0]["kwargs"]["arguments"] == {"issue_id": "issue-1"}
    assert tool_calls[0]["kwargs"]["approved_call_id"] == "approval-1"
