from __future__ import annotations

from collections.abc import AsyncIterator

from sqlalchemy.orm import Session, sessionmaker

from ai_do_api.core.db import get_session_factory
from ai_do_api.core.llm_adapters import StreamChunk
from ai_do_api.domains.ai.gateway import LlmWorkloadContext, execute_llm, stream_llm
from ai_do_api.domains.ai.registry import resolve_llm_workload
from ai_do_api.domains.ai_graph.contracts import AiGraphLlmRequest, AiGraphLlmResult


class AiGatewayGraphAdapter:
    """The only LLM seam available to common graph nodes.

    Workloads remain app-owned and registered. Provider/model routing stays
    inside the existing AI Gateway.
    """

    def __init__(
        self,
        session_factory: sessionmaker[Session] | None = None,
    ) -> None:
        self._session_factory = session_factory or get_session_factory()

    @staticmethod
    def _validate_registration(request: AiGraphLlmRequest) -> None:
        workload = resolve_llm_workload(request.workload_id)
        if request.app_id.strip().lower() not in workload.app_ids:
            raise ValueError(
                f"LLM workload {workload.workload_id} is not registered for app "
                f"{request.app_id}"
            )

    @staticmethod
    def _context(request: AiGraphLlmRequest) -> LlmWorkloadContext:
        return LlmWorkloadContext(
            source=request.source,
            workspace_id=request.workspace_id,
            actor_user_id=request.actor_user_id,
            principal_kind=request.principal_kind,
            principal_id=request.principal_id,
            app_id=request.app_id,
        )

    def invoke(self, request: AiGraphLlmRequest) -> AiGraphLlmResult:
        self._validate_registration(request)
        with self._session_factory() as db:
            try:
                result = execute_llm(
                    request.workload_id,
                    self._context(request),
                    db,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    reasoning_effort=request.reasoning_effort,
                    timeout_seconds=request.timeout_seconds,
                    stream_reasoning=request.stream_reasoning,
                    tools=request.tools,
                    tool_choice=request.tool_choice,
                    parallel_tool_calls=request.parallel_tool_calls,
                    agent_run_id=request.graph_run_id,
                    conversation_id=request.conversation_id,
                )
                db.commit()
            except Exception:
                db.rollback()
                raise
        return AiGraphLlmResult(
            text=result.completion.text,
            model=result.completion.model,
            usage=dict(result.completion.usage) if result.completion.usage is not None else None,
            finish_reason=result.completion.finish_reason,
            workload_id=request.workload_id,
            chosen_pool=result.decision.chosen_pool,
        )

    async def stream(self, request: AiGraphLlmRequest) -> AsyncIterator[StreamChunk]:
        self._validate_registration(request)
        with self._session_factory() as db:
            try:
                async for chunk, _decision, _config in stream_llm(
                    request.workload_id,
                    self._context(request),
                    db,
                    messages=request.messages,
                    temperature=request.temperature,
                    max_tokens=request.max_tokens,
                    reasoning_effort=request.reasoning_effort,
                    timeout_seconds=request.timeout_seconds,
                    stream_reasoning=request.stream_reasoning,
                    tools=request.tools,
                    tool_choice=request.tool_choice,
                    parallel_tool_calls=request.parallel_tool_calls,
                    agent_run_id=request.graph_run_id,
                    conversation_id=request.conversation_id,
                ):
                    yield chunk
                db.commit()
            except Exception:
                db.rollback()
                raise
