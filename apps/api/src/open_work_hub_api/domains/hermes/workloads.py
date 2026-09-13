"""Durable Hermes execution behind the registered LLM gateway.

The caller has already resolved the administrator route and applied the data
boundary. Dedicated DB sessions keep run staging/leases independent of an
application transaction. The normal dispatch outbox recovers a lost caller.
"""

from __future__ import annotations

import asyncio
import json
from typing import Any
from uuid import uuid4

from jsonschema import Draft202012Validator

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.core.llm import LlmTaskContext, ResolvedLlmExecution
from open_work_hub_api.core.llm_adapters import StreamChunk
from open_work_hub_api.core.llm_errors import LlmProviderError
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import get_ai_capability_registry
from open_work_hub_api.domains.auth.app_gate import can_use_app
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.hermes.execution import execute_hermes_run
from open_work_hub_api.domains.hermes.model_policy import HermesModelPolicy
from open_work_hub_api.domains.hermes.repository import HermesRunRepository, TERMINAL_RUN_STATUSES
from open_work_hub_api.domains.hermes.service import ensure_profile_binding, runtime_client


def _messages(payload: dict[str, Any]) -> tuple[str, str, list[dict[str, str]]]:
    messages = payload.get("messages", [])
    instructions = []
    history = []
    for message in messages:
        content = message.get("content")
        if not isinstance(content, str):
            raise LlmProviderError("This Hermes workload requires text messages.")
        if message["role"] in {"system", "developer"}:
            instructions.append(content)
        elif message["role"] in {"user", "assistant"}:
            history.append({"role": message["role"], "content": content})
        else:
            raise LlmProviderError("Raw application tool loops must use Hermes tools.")
    if not history or history[-1]["role"] != "user":
        raise LlmProviderError("A Hermes workload requires a final user message.")
    current = history.pop()["content"]
    return current, "\n\n".join(instructions), history


async def run_workload(
    context: LlmTaskContext,
    execution: ResolvedLlmExecution,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    settings = get_settings()
    if not settings.hermes_enabled:
        raise LlmProviderError("Hermes is disabled; registered generation is unavailable.")
    owner_id = context.execution_user_id or context.actor_user_id
    if not context.workload_id or not owner_id:
        raise LlmProviderError("A registered workload and execution owner are required.")
    workload = get_ai_capability_registry().resolve_llm_workload(context.workload_id)
    if type(context.native_tool_limit) is not int or not 1 <= context.native_tool_limit <= 20:
        raise LlmProviderError("Invalid native tool limit")
    if payload.get("tools"):
        raise LlmProviderError("Application tool-call results must use a structured output schema.")
    if output_schema is not None:
        Draft202012Validator.check_schema(output_schema)
    policy = HermesModelPolicy.from_pool(
        execution.config,
        model=execution.chosen_model,
        max_tokens=execution.resolved_max_tokens,
    )
    input_text, instructions, history = _messages(payload)
    if output_schema is not None:
        instructions += (
            "\n\nSubmit your result with owh_submit_result. The result must satisfy this JSON Schema: "
            + json.dumps(output_schema, ensure_ascii=False)
            + "\nIf validation fails, correct the result and submit it again before finishing."
        )
    factory = get_session_factory()
    with factory() as db:
        user = db.get(User, owner_id)
        if (
            user is None
            or user.status != "active"
            or user.login_blocked
            or not can_use_app(
                db,
                app_id=context.app_id,
                user_id=user.id,
            )
        ):
            raise LlmProviderError("Workload owner no longer has access to this app.")
        binding = await ensure_profile_binding(db, user=user, model_policy=policy)
        run = HermesRunRepository(db).stage(
            binding=binding,
            session=None,
            input_text=input_text,
            instructions=instructions,
            conversation_history=history,
            allowed_app_ids=[],
            kind="workload",
            workload_id=context.workload_id,
            owner_app_id=context.app_id,
            runtime_options={
                **policy.run_options(reasoning_effort=execution.resolved_reasoning_effort),
                "native_tools": list(workload.native_tools),
                "native_tool_limit": context.native_tool_limit,
            },
            output_schema=output_schema,
            client_request_id=str(uuid4()),
        )
        run_id, profile_name = run.id, binding.profile_name
        db.commit()
    deadline = asyncio.get_running_loop().time() + min(timeout_seconds, 3600)
    try:
        while True:
            remaining = deadline - asyncio.get_running_loop().time()
            if remaining <= 0:
                raise TimeoutError
            with factory() as db:
                await asyncio.wait_for(
                    execute_hermes_run(
                        db,
                        run_id=run_id,
                        runtime_base_url=settings.hermes_runtime_base_url,
                        api_key=settings.hermes_api_key.get_secret_value(),
                        request_timeout_seconds=settings.hermes_request_timeout_seconds,
                        lease_seconds=3900,
                        max_concurrent_runs=settings.hermes_max_concurrent_runs,
                    ),
                    timeout=remaining,
                )
                db.expire_all()
                run = HermesRunRepository(db).get(run_id)
                if run is None:
                    raise LlmProviderError("Hermes workload projection is missing.")
                if run.status in TERMINAL_RUN_STATUSES:
                    if run.status != "completed":
                        raise LlmProviderError(f"Hermes workload ended with {run.status}.")
                    usage = run.usage
                    input_tokens = usage.get("input_tokens", usage.get("prompt_tokens", 0))
                    output_tokens = usage.get("output_tokens", usage.get("completion_tokens", 0))
                    input_tokens = (
                        input_tokens if type(input_tokens) is int and input_tokens >= 0 else 0
                    )
                    output_tokens = (
                        output_tokens if type(output_tokens) is int and output_tokens >= 0 else 0
                    )
                    return {
                        "id": run.id,
                        "model": execution.chosen_model,
                        "choices": [
                            {"message": {"content": run.output_text or ""}, "finish_reason": "stop"}
                        ],
                        "usage": {
                            "prompt_tokens": input_tokens,
                            "completion_tokens": output_tokens,
                            "total_tokens": input_tokens + output_tokens,
                        },
                        "structured_output": run.output_payload,
                    }
            await asyncio.sleep(0.5)
    except TimeoutError as error:
        with factory() as db:
            run = HermesRunRepository(db).request_stop(run_id, user_id=owner_id)
            native_id = run.hermes_run_id
            db.commit()
        if native_id:
            await runtime_client().stop_run(profile_name, native_id)
        raise LlmProviderError("Hermes workload timed out.") from error


def complete_workload(
    context: LlmTaskContext,
    execution: ResolvedLlmExecution,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
    output_schema: dict[str, Any] | None = None,
) -> dict[str, Any]:
    def execute():
        return asyncio.run(
            run_workload(
                context,
                execution,
                payload,
                timeout_seconds=timeout_seconds,
                output_schema=output_schema,
            )
        )

    # Blocking an ASGI loop would prevent this same API from handling the
    # native Hermes result/tool callback. Async callers must use stream_llm
    # or offload their synchronous domain operation to the ASGI thread pool.
    try:
        asyncio.get_running_loop()
    except RuntimeError:
        return execute()
    raise LlmProviderError("Synchronous Hermes execution requires a worker thread.")


async def stream_workload(
    context: LlmTaskContext,
    execution: ResolvedLlmExecution,
    payload: dict[str, Any],
    *,
    timeout_seconds: float,
    output_schema: dict[str, Any] | None = None,
):
    result = await run_workload(
        context,
        execution,
        payload,
        timeout_seconds=timeout_seconds,
        output_schema=output_schema,
    )
    # Application graphs consume completed stage output. Interactive chatbot
    # progress/approval/deltas use the durable /agent event projection directly.
    yield StreamChunk(kind="content", text=result["choices"][0]["message"]["content"])
    yield StreamChunk(kind="usage", usage=result["usage"])
    yield StreamChunk(
        kind="done", finish_reason="stop", structured_output=result["structured_output"]
    )
