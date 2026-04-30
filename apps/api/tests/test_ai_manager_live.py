from __future__ import annotations

import os
from pathlib import Path
from typing import Any

import pytest

from aidoo_api.domains.ai.events import EnvelopeEncoder
from aidoo_api.domains.ai.manager_runtime import (
    AiManagerConfig,
    AiManagerStreamContext,
    StaticLocalSpecialistRunner,
    build_ai_manager_input,
    build_local_specialist_tool_context,
    run_openai_ai_manager_stream,
)


def _load_openai_key_from_env_file() -> None:
    if os.environ.get("OPENAI_API_KEY"):
        return
    try:
        from dotenv import dotenv_values
    except Exception:
        return
    env_path = Path(__file__).resolve().parents[3] / ".env"
    if not env_path.exists():
        return
    value = dotenv_values(env_path).get("OPENAI_API_KEY")
    if value:
        os.environ["OPENAI_API_KEY"] = value


@pytest.mark.anyio
async def test_live_openai_manager_smoke() -> None:
    if os.environ.get("AIDOO_RUN_LIVE_OPENAI_AI_MANAGER") != "1":
        pytest.skip("set AIDOO_RUN_LIVE_OPENAI_AI_MANAGER=1 to run live OpenAI smoke")
    _load_openai_key_from_env_file()
    if not os.environ.get("OPENAI_API_KEY"):
        pytest.skip("OPENAI_API_KEY is not configured")

    os.environ.setdefault("OPENAI_AGENTS_TRACE_INCLUDE_SENSITIVE_DATA", "0")
    os.environ.setdefault("OPENAI_AGENTS_DONT_LOG_TOOL_DATA", "1")

    model = os.environ.get("AIDOO_AI_MANAGER_MODEL") or "gpt-5.4-mini"
    context = AiManagerStreamContext(
        config=AiManagerConfig(
            adapter_id="openai_agents_ai_manager.v1",
            enabled=True,
            ready=True,
            disabled_reason=None,
            provider="openai",
            model=model,
            max_loops=2,
            trace_sensitive_data=False,
            store_response=False,
            hosted_tools_enabled=False,
        ),
        manager_input=build_ai_manager_input(
            raw_prompt="내부 문서 근거를 확인해서 이번 주 회의 후속조치를 짧게 요약해줘.",
            available_agent_ids=["domain.docs"],
            available_tool_names=["docs.search"],
            workspace_metadata={"scope": "workspace_current"},
        ),
        local_context=build_local_specialist_tool_context(
            enabled_app_ids=["ai", "docs"],
            allowed_app_ids=["ai", "docs"],
            available_tool_names=["docs.search"],
        ),
        local_runner=StaticLocalSpecialistRunner(
            redacted_summary=(
                "로컬 specialist smoke summary: 문서 근거 확인 결과 "
                "후속조치 2건과 미확인 gap 1건이 있습니다."
            )
        ),
        encoder=EnvelopeEncoder(),
        stream_reasoning=True,
        max_tokens=512,
    )

    events: list[dict[str, Any]] = [
        event.model_dump(exclude_none=True)
        async for event in run_openai_ai_manager_stream(context=context)
    ]

    event_types = [event["type"] for event in events]
    assert "tool_call_started" in event_types
    assert "tool_result" in event_types
    assert event_types[-1] == "done"
    assert events[-1]["data"]["finish_reason"] == "stop"
    done_meta = events[-1]["data"]["meta"]
    assert done_meta["provider"] == "openai"
    assert done_meta["model"] == model
    assert done_meta["external_egress_summary"] == {
        "manager": "ai_manager",
        "sdk": "openai_agents",
        "prompt_status": "raw_allowed",
        "removed_entity_types": [],
        "response_storage": False,
        "trace_sensitive_data": False,
        "hosted_tools_enabled": False,
    }
