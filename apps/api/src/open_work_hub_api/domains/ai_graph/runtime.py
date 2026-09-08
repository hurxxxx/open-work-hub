from __future__ import annotations

import asyncio
import logging
import re
from collections.abc import Awaitable, Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Annotated, Any, Protocol, TypedDict
from uuid import uuid4

from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.graph import END, START, StateGraph
from langgraph.graph.state import CompiledStateGraph
from langgraph.runtime import Runtime
from sqlalchemy.orm import Session, sessionmaker

from open_work_hub_api.core.db import get_session_factory
from open_work_hub_api.domains.ai_graph.contracts import (
    AiGraphNodeResult,
    AiGraphNodeSpec,
    AiGraphRunRequest,
    AiGraphRunResult,
    AiGraphSpec,
    merge_graph_values,
)
from open_work_hub_api.domains.ai_graph.execution_policy import enforce_graph_run_app_policy
from open_work_hub_api.domains.ai_graph.repository import (
    AiGraphExecutionLeaseLostError,
    AiGraphRunInputRepository,
    AiGraphRunRepository,
)

logger = logging.getLogger(__name__)

_SAFE_ERROR_DETAIL = re.compile(r"^[a-z][a-z0-9_.-]{0,119}$")

_EXECUTION_LEASE_DURATION = timedelta(minutes=15)
_EXECUTION_LEASE_HEARTBEAT_INTERVAL_SECONDS = 60.0


class _RuntimeState(TypedDict):
    inputs: dict[str, Any]
    outputs: Annotated[dict[str, Any], merge_graph_values]
    errors: Annotated[dict[str, Any], merge_graph_values]
    routes: Annotated[dict[str, Any], merge_graph_values]


@dataclass(frozen=True)
class AiGraphRuntimeContext:
    run_id: str
    requested_by_user_id: str
    app_id: str
    conversation_id: str | None
    progress_callback: Callable[[str], Awaitable[None]]
    policy_callback: Callable[[], Awaitable[None]]


class AiGraphExecutionDisabledError(RuntimeError):
    pass


class AiGraphNodeAdapter(Protocol):
    def __call__(
        self,
        state: Mapping[str, Any],
        context: AiGraphRuntimeContext,
    ) -> Awaitable[AiGraphNodeResult]: ...


@dataclass(frozen=True)
class CompiledAiGraph:
    spec: AiGraphSpec
    graph: CompiledStateGraph


def _safe_error_detail(error: BaseException) -> str | None:
    detail = str(error).strip()
    return detail if _SAFE_ERROR_DETAIL.fullmatch(detail) else None


def _node_runner(
    node: AiGraphNodeSpec,
    adapter: AiGraphNodeAdapter,
) -> Callable[[_RuntimeState, Runtime[AiGraphRuntimeContext]], Awaitable[dict[str, Any]]]:
    async def execute(
        state: _RuntimeState,
        runtime: Runtime[AiGraphRuntimeContext],
    ) -> dict[str, Any]:
        try:
            await runtime.context.policy_callback()
            result = await adapter(state, runtime.context)
            if not isinstance(result, AiGraphNodeResult):
                result = AiGraphNodeResult.model_validate(result)
            if node.routes and result.route not in node.routes:
                raise ValueError(f"node {node.node_id} returned unknown route {result.route!r}")
            if not node.routes and result.route is not None:
                raise ValueError(f"node {node.node_id} returned an undeclared route")
            values: dict[str, Any] = {"outputs": {node.node_id: result.output}}
            if node.routes:
                values["routes"] = {node.node_id: result.route}
            await runtime.context.progress_callback(node.node_id)
            return values
        except AiGraphExecutionDisabledError:
            raise
        except Exception as error:
            if node.required or node.routes:
                logger.error(
                    "AI graph node execution failed",
                    extra={
                        "graph_run_id": runtime.context.run_id,
                        "node_id": node.node_id,
                        "error_type": type(error).__name__,
                        "error_detail": _safe_error_detail(error),
                    },
                )
                raise
            await runtime.context.progress_callback(node.node_id)
            return {"errors": {node.node_id: type(error).__name__}}

    return execute


def _route_selector(node_id: str) -> Callable[[_RuntimeState], str]:
    def select_route(state: _RuntimeState) -> str:
        route = state.get("routes", {}).get(node_id)
        if not isinstance(route, str) or not route:
            raise ValueError(f"node {node_id} did not select a route")
        return route

    return select_route


def compile_graph(
    spec: AiGraphSpec,
    node_adapters: Mapping[str, AiGraphNodeAdapter],
    checkpointer: BaseCheckpointSaver,
) -> CompiledAiGraph:
    """Compile a versioned DAG, including conditional edges, into LangGraph."""

    if checkpointer is None:
        raise ValueError("a LangGraph checkpointer is required")
    missing = {node.node_id for node in spec.nodes} - set(node_adapters)
    extra = set(node_adapters) - {node.node_id for node in spec.nodes}
    if missing or extra:
        raise ValueError(f"node adapter mismatch; missing={sorted(missing)}, extra={sorted(extra)}")

    builder = StateGraph(_RuntimeState, context_schema=AiGraphRuntimeContext)
    for node in spec.nodes:
        builder.add_node(node.node_id, _node_runner(node, node_adapters[node.node_id]))

    routed_targets = {
        target for node in spec.nodes for target in node.routes.values() if target is not None
    }
    static_dependents = {
        node.node_id: {
            candidate.node_id for candidate in spec.nodes if node.node_id in candidate.depends_on
        }
        for node in spec.nodes
    }

    for node in spec.nodes:
        if node.depends_on:
            starts: str | list[str]
            starts = node.depends_on[0] if len(node.depends_on) == 1 else list(node.depends_on)
            builder.add_edge(starts, node.node_id)
        elif node.node_id not in routed_targets:
            builder.add_edge(START, node.node_id)

        if node.routes:
            path_map = {
                route: target if target is not None else END
                for route, target in node.routes.items()
            }
            builder.add_conditional_edges(
                node.node_id,
                _route_selector(node.node_id),
                path_map,
            )
        elif not static_dependents[node.node_id]:
            builder.add_edge(node.node_id, END)

    return CompiledAiGraph(spec=spec, graph=builder.compile(checkpointer=checkpointer))


def _progress_callback(
    session_factory: sessionmaker[Session],
    run_id: str,
    claim_token: str,
) -> Callable[[str], Awaitable[None]]:
    async def advance(node_id: str) -> None:
        def persist() -> None:
            with session_factory() as db:
                AiGraphRunRepository(db).advance(
                    run_id,
                    node_id=node_id,
                    claim_token=claim_token,
                )
                db.commit()

        try:
            await asyncio.to_thread(persist)
        except AiGraphExecutionLeaseLostError:
            raise
        except Exception:
            logger.exception(
                "Failed to update graph run progress projection",
                extra={"graph_run_id": run_id, "node_id": node_id},
            )

    return advance


def _policy_callback(
    session_factory: sessionmaker[Session],
    run_id: str,
    claim_token: str,
) -> Callable[[], Awaitable[None]]:
    async def enforce() -> None:
        def persist() -> bool:
            with session_factory() as db:
                enabled = enforce_graph_run_app_policy(
                    db,
                    run_id=run_id,
                    claim_token=claim_token,
                    stage="graph.node_policy_gate",
                )
                if not enabled:
                    AiGraphRunInputRepository(db).delete_after_terminal(run_id)
                db.commit()
                return enabled

        if not await asyncio.to_thread(persist):
            raise AiGraphExecutionDisabledError("app_execution_disabled")

    return enforce


async def _renew_execution_lease(
    session_factory: sessionmaker[Session],
    *,
    run_id: str,
    claim_token: str,
) -> None:
    def persist() -> None:
        with session_factory() as db:
            AiGraphRunRepository(db).renew_execution_lease(
                run_id,
                claim_token=claim_token,
                lease_duration=_EXECUTION_LEASE_DURATION,
            )
            db.commit()

    await asyncio.to_thread(persist)


async def _execution_lease_heartbeat(
    session_factory: sessionmaker[Session],
    *,
    run_id: str,
    claim_token: str,
    stop: asyncio.Event,
) -> None:
    while True:
        try:
            await asyncio.wait_for(
                stop.wait(),
                timeout=_EXECUTION_LEASE_HEARTBEAT_INTERVAL_SECONDS,
            )
            return
        except TimeoutError:
            await _renew_execution_lease(
                session_factory,
                run_id=run_id,
                claim_token=claim_token,
            )


async def _invoke_with_execution_lease(
    compiled: CompiledAiGraph,
    graph_input: _RuntimeState | None,
    *,
    config: dict[str, Any],
    context: AiGraphRuntimeContext,
    session_factory: sessionmaker[Session],
    run_id: str,
    claim_token: str,
) -> _RuntimeState:
    stop = asyncio.Event()
    graph_task = asyncio.create_task(
        compiled.graph.ainvoke(
            graph_input,
            config=config,
            context=context,
        )
    )
    heartbeat_task = asyncio.create_task(
        _execution_lease_heartbeat(
            session_factory,
            run_id=run_id,
            claim_token=claim_token,
            stop=stop,
        )
    )
    try:
        done, _pending = await asyncio.wait(
            {graph_task, heartbeat_task},
            return_when=asyncio.FIRST_COMPLETED,
        )
        if heartbeat_task in done:
            await heartbeat_task
            raise RuntimeError("execution lease heartbeat stopped unexpectedly")
        return await graph_task
    finally:
        stop.set()
        if not graph_task.done():
            graph_task.cancel()
        await asyncio.gather(graph_task, heartbeat_task, return_exceptions=True)


async def run_graph(
    compiled: CompiledAiGraph,
    request: AiGraphRunRequest,
    *,
    run_id: str | None = None,
    claim_token: str | None = None,
    session_factory: sessionmaker[Session] | None = None,
) -> AiGraphRunResult:
    """Run or resume a graph while keeping only UI status in ``ai_graph_runs``."""

    if (
        request.graph.graph_id != compiled.spec.graph_id
        or request.graph.graph_version != compiled.spec.graph_version
    ):
        raise ValueError("compiled graph does not match run request")
    resolved_factory = session_factory or get_session_factory()
    resolved_claim_token = claim_token or uuid4().hex
    with resolved_factory() as db:
        repository = AiGraphRunRepository(db)
        if run_id is None:
            run = repository.create(request)
            run_id = run.id
        else:
            run = repository.require(run_id)
            if (
                run.app_id != request.app_id
                or run.graph_id != request.graph.graph_id
                or run.graph_version != request.graph.graph_version
            ):
                raise ValueError("persisted graph run does not match request")
        claim = repository.claim_execution(
            run_id,
            claim_token=resolved_claim_token,
            lease_duration=_EXECUTION_LEASE_DURATION,
        )
        if claim.acquired and not enforce_graph_run_app_policy(
            db,
            run_id=run_id,
            claim_token=resolved_claim_token,
            stage="graph.claim_policy_gate",
        ):
            AiGraphRunInputRepository(db).delete_after_terminal(run_id)
            db.commit()
            return AiGraphRunResult(
                run_id=run_id,
                status="skipped",
                reason="app_disabled",
            )
        db.commit()
        if not claim.acquired:
            return AiGraphRunResult(
                run_id=run_id,
                status="skipped",
                reason=claim.reason,
            )

    context = AiGraphRuntimeContext(
        run_id=run_id,
        requested_by_user_id=request.requested_by_user_id,
        app_id=request.app_id,
        conversation_id=request.conversation_id,
        progress_callback=_progress_callback(
            resolved_factory,
            run_id,
            resolved_claim_token,
        ),
        policy_callback=_policy_callback(
            resolved_factory,
            run_id,
            resolved_claim_token,
        ),
    )
    config = {
        "configurable": {
            "thread_id": run_id,
            "checkpoint_ns": request.checkpoint_ns,
        },
        "max_concurrency": 8,
    }
    try:
        graph_input: _RuntimeState | None = {
            "inputs": request.inputs,
            "outputs": {},
            "errors": {},
            "routes": {},
        }
        if claim.resume_from_checkpoint:
            checkpoint = await compiled.graph.checkpointer.aget_tuple(config)
            if checkpoint is not None:
                graph_input = None
        state = await _invoke_with_execution_lease(
            compiled,
            graph_input,
            config=config,
            context=context,
            session_factory=resolved_factory,
            run_id=run_id,
            claim_token=resolved_claim_token,
        )
    except AiGraphExecutionDisabledError:
        return AiGraphRunResult(
            run_id=run_id,
            status="skipped",
            reason="app_disabled",
        )
    except asyncio.CancelledError:
        with resolved_factory() as db:
            try:
                AiGraphRunRepository(db).transition(
                    run_id,
                    "cancelled",
                    stage="graph.cancelled",
                    status_message_key="ai.graphRun.cancelled",
                    claim_token=resolved_claim_token,
                )
                db.commit()
            except AiGraphExecutionLeaseLostError:
                db.rollback()
        raise
    except AiGraphExecutionLeaseLostError:
        return AiGraphRunResult(
            run_id=run_id,
            status="skipped",
            reason="lease_lost",
        )
    except Exception as error:
        error_code = f"graph_execution.{type(error).__name__}"
        logger.error(
            "AI graph execution failed",
            extra={
                "graph_run_id": run_id,
                "graph_id": request.graph.graph_id,
                "graph_version": request.graph.graph_version,
                "error_code": error_code,
                "error_detail": _safe_error_detail(error),
            },
        )
        with resolved_factory() as db:
            try:
                AiGraphRunRepository(db).transition(
                    run_id,
                    "failed",
                    stage="graph.failed",
                    status_message_key="ai.graphRun.failed",
                    error_code=error_code,
                    claim_token=resolved_claim_token,
                )
                db.commit()
            except AiGraphExecutionLeaseLostError:
                db.rollback()
                return AiGraphRunResult(
                    run_id=run_id,
                    status="skipped",
                    reason="lease_lost",
                )
        return AiGraphRunResult(
            run_id=run_id,
            status="failed",
            errors={"graph": error_code},
        )

    with resolved_factory() as db:
        try:
            if not enforce_graph_run_app_policy(
                db,
                run_id=run_id,
                claim_token=resolved_claim_token,
                stage="graph.completion_policy_gate",
            ):
                AiGraphRunInputRepository(db).delete_after_terminal(run_id)
                db.commit()
                return AiGraphRunResult(
                    run_id=run_id,
                    status="skipped",
                    reason="app_disabled",
                )
            AiGraphRunRepository(db).transition(
                run_id,
                "completed",
                stage="graph.completed",
                status_message_key="ai.graphRun.completed",
                claim_token=resolved_claim_token,
            )
            db.commit()
        except AiGraphExecutionLeaseLostError:
            db.rollback()
            return AiGraphRunResult(
                run_id=run_id,
                status="skipped",
                reason="lease_lost",
            )
    return AiGraphRunResult(
        run_id=run_id,
        status="completed",
        outputs=dict(state.get("outputs", {})),
        errors=dict(state.get("errors", {})),
    )
