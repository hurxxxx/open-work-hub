from __future__ import annotations

import json

import pytest

from aidoo_api.domains.ai.events import EnvelopeEncoder
from aidoo_api.domains.ai.manager_runtime import (
    AiManagerConfig,
    AiManagerInput,
    AiManagerStreamContext,
    LocalAgentResult,
    LocalAgentTask,
    ManagerPlan,
    ManagerReview,
    StaticLocalSpecialistRunner,
    build_ai_manager_input,
    build_local_specialist_tool_context,
    run_ai_manager_stream,
)


class ScriptedManagerClient:
    def __init__(self, *, plan: ManagerPlan, reviews: list[ManagerReview]) -> None:
        self.plan = plan
        self.reviews = list(reviews)
        self.review_calls: list[list[LocalAgentResult]] = []

    def create_plan(self, manager_input: AiManagerInput) -> ManagerPlan:
        self.manager_input = manager_input
        return self.plan

    def review_results(
        self,
        *,
        manager_input: AiManagerInput,
        plan: ManagerPlan,
        local_results: list[LocalAgentResult],
        loop_index: int,
    ) -> ManagerReview:
        del manager_input, plan, loop_index
        self.review_calls.append(list(local_results))
        return self.reviews.pop(0)


def _config(*, max_loops: int = 3) -> AiManagerConfig:
    return AiManagerConfig(
        adapter_id="openai_agents_ai_manager.v1",
        enabled=True,
        ready=True,
        disabled_reason=None,
        provider="openai",
        model="gpt-test",
        max_loops=max_loops,
        trace_sensitive_data=False,
        store_response=False,
        hosted_tools_enabled=False,
    )


def _manager_input(raw_prompt: str = "문서를 근거로 요약해줘") -> AiManagerInput:
    return build_ai_manager_input(
        raw_prompt=raw_prompt,
        available_agent_ids=["domain.docs", "writer.template"],
        available_tool_names=["docs.search", "docs.write"],
        workspace_metadata={"scope": "workspace_current"},
    )


def _context(
    *,
    max_loops: int = 3,
    manager_input: AiManagerInput | None = None,
    stream_reasoning: bool = True,
    approval_required_tool_names: list[str] | None = None,
) -> AiManagerStreamContext:
    return AiManagerStreamContext(
        config=_config(max_loops=max_loops),
        manager_input=manager_input or _manager_input(),
        local_context=build_local_specialist_tool_context(
            enabled_app_ids=["ai", "docs"],
            allowed_app_ids=["ai", "docs"],
            available_tool_names=["docs.search", "docs.write"],
            approval_required_tool_names=approval_required_tool_names or [],
        ),
        local_runner=StaticLocalSpecialistRunner(redacted_summary="safe local summary"),
        encoder=EnvelopeEncoder(),
        stream_reasoning=stream_reasoning,
    )


async def _collect(
    context: AiManagerStreamContext,
    *,
    manager_client: ScriptedManagerClient | None = None,
) -> list[dict]:
    return [
        event.model_dump(exclude_none=True)
        async for event in run_ai_manager_stream(
            context=context,
            manager_client=manager_client,
        )
    ]


def _task(**overrides) -> LocalAgentTask:
    payload = {
        "agent_id": "domain.docs",
        "objective": "Collect a redacted summary.",
        "allowed_tool_names": [],
        "context_boundary": "workspace_current",
        "expected_output": "redacted summary",
    }
    payload.update(overrides)
    return LocalAgentTask(**payload)


@pytest.mark.anyio
async def test_ai_manager_stream_static_success() -> None:
    events = await _collect(_context())

    assert [event["type"] for event in events] == [
        "reasoning_delta",
        "tool_call_started",
        "tool_call_args_delta",
        "tool_result",
        "reasoning_delta",
        "content_delta",
        "done",
    ]
    assert [event["seq"] for event in events] == list(range(len(events)))
    assert events[1]["data"]["name"] == "run_local_specialist"
    assert events[3]["data"]["status"] == "ok"
    assert "safe local summary" in events[5]["data"]["text"]
    done_meta = events[-1]["data"]["meta"]
    assert done_meta["policy"] == "ai_manager"
    assert done_meta["provider"] == "openai"
    assert done_meta["runtime_profile"] == "ai_manager"
    assert done_meta["external_egress_summary"] == {
        "manager": "ai_manager",
        "prompt_status": "raw_allowed",
        "removed_entity_types": [],
        "response_storage": False,
        "trace_sensitive_data": False,
        "hosted_tools_enabled": False,
    }


@pytest.mark.anyio
async def test_ai_manager_stream_redacts_sensitive_prompt_before_events() -> None:
    events = await _collect(
        _context(manager_input=_manager_input("ORD-ABC-1 가격을 확인해줘"))
    )

    wire = json.dumps(events, ensure_ascii=False)
    assert "ORD-ABC-1" not in wire
    assert "가격" not in wire
    assert events[-1]["data"]["meta"]["external_egress_summary"]["prompt_status"] == "redacted"
    assert set(
        events[-1]["data"]["meta"]["external_egress_summary"][
            "removed_entity_types"
        ]
    ) >= {"order_id", "price"}


@pytest.mark.anyio
async def test_ai_manager_stream_user_question_stops_without_tool_call() -> None:
    client = ScriptedManagerClient(
        plan=ManagerPlan(
            objective="clarify",
            needs_user_decision=True,
            clarification_question="어떤 문서를 기준으로 할까요?",
        ),
        reviews=[],
    )

    events = await _collect(_context(), manager_client=client)

    assert [event["type"] for event in events] == [
        "reasoning_delta",
        "content_delta",
        "done",
    ]
    assert events[1]["data"]["text"] == "어떤 문서를 기준으로 할까요?"
    assert events[-1]["data"]["meta"]["decision_reason"] == "ask_user"


@pytest.mark.anyio
async def test_ai_manager_stream_one_retry_then_final() -> None:
    client = ScriptedManagerClient(
        plan=ManagerPlan(objective="first", tasks=[_task()]),
        reviews=[
            ManagerReview(
                decision="retry",
                gap_summary="Need writer pass.",
                next_tasks=[_task(agent_id="writer.template")],
            ),
            ManagerReview(decision="final", result_summary="final after retry"),
        ],
    )

    events = await _collect(_context(), manager_client=client)

    assert [event["type"] for event in events].count("tool_call_started") == 2
    assert events[-2]["data"]["text"] == "final after retry"
    assert events[-1]["data"]["meta"]["decision_reason"] == "final"
    assert "loops_used:2" in events[-1]["data"]["meta"]["runtime_routing_reason_codes"]


@pytest.mark.anyio
async def test_ai_manager_stream_loop_limit_returns_partial_answer() -> None:
    client = ScriptedManagerClient(
        plan=ManagerPlan(objective="first", tasks=[_task()]),
        reviews=[
            ManagerReview(
                decision="retry",
                gap_summary="Need one more pass.",
                next_tasks=[_task(agent_id="writer.template")],
            )
        ],
    )

    events = await _collect(_context(max_loops=1), manager_client=client)

    assert events[-2]["type"] == "content_delta"
    assert "loop limit" in events[-2]["data"]["text"]
    assert events[-1]["data"]["meta"]["decision_reason"] == "partial"
    assert "loops_used:1" in events[-1]["data"]["meta"]["runtime_routing_reason_codes"]


@pytest.mark.anyio
async def test_ai_manager_stream_approval_required_stops_for_user() -> None:
    client = ScriptedManagerClient(
        plan=ManagerPlan(
            objective="write",
            tasks=[_task(allowed_tool_names=["docs.write"])],
        ),
        reviews=[
            ManagerReview(
                decision="ask_user",
                user_question="쓰기 승인이 필요합니다.",
            )
        ],
    )

    events = await _collect(
        _context(approval_required_tool_names=["docs.write"]),
        manager_client=client,
    )

    tool_result = next(event for event in events if event["type"] == "tool_result")
    assert tool_result["data"]["status"] == "rejected"
    assert tool_result["data"]["error"] == "approval_required"
    assert events[-2]["data"]["text"] == "쓰기 승인이 필요합니다."
    assert events[-1]["data"]["meta"]["decision_reason"] == "ask_user"


@pytest.mark.anyio
async def test_ai_manager_stream_failed_review_emits_error_done() -> None:
    client = ScriptedManagerClient(
        plan=ManagerPlan(objective="first", tasks=[_task()]),
        reviews=[
            ManagerReview(
                decision="failed",
                gap_summary="manager review failed",
            )
        ],
    )

    events = await _collect(_context(), manager_client=client)

    assert [event["type"] for event in events][-2:] == ["error", "done"]
    assert events[-2]["data"]["code"] == "ai_manager_failed"
    assert events[-1]["data"]["finish_reason"] == "error"
