from __future__ import annotations

import asyncio

from sqlalchemy import select
from sqlalchemy.orm import Session, sessionmaker

from open_alm_api.core.db import get_session_factory
from open_alm_api.domains.ai_artifacts.models import AiArtifact
from open_alm_api.domains.ai_artifacts.repository import AiArtifactRepository
from open_alm_api.domains.ai_graph.checkpoints import async_postgres_checkpointer
from open_alm_api.domains.ai_graph.contracts import AiGraphRunRequest, AiGraphRunResult
from open_alm_api.domains.ai_graph.gateway_adapter import AiGatewayGraphAdapter
from open_alm_api.domains.ai_graph.repository import (
    AiGraphRunInputRepository,
    AiGraphRunRepository,
)
from open_alm_api.domains.ai_graph.runtime import compile_graph, run_graph
from open_alm_api.domains.legacy_issues.analysis_graph.application import (
    LegacyIssueGraphDependencies,
    build_legacy_issue_node_adapters,
)
from open_alm_api.domains.legacy_issues.analysis_graph.data_provider import (
    LangChainLegacyIssueDataProvider,
)
from open_alm_api.domains.legacy_issues.analysis_graph.persistence import (
    AiArtifactAnalysisWriter,
    mark_analysis_placeholder_failed,
)
from open_alm_api.domains.legacy_issues.analysis_graph.topology import (
    legacy_issue_analysis_graph_spec,
)


def execute_legacy_issue_analysis_graph(
    run_id: str,
    *,
    session_factory: sessionmaker[Session] | None = None,
) -> str:
    resolved_factory = session_factory or get_session_factory()
    run_request, assistant_turn_id = _load_request(
        run_id,
        session_factory=resolved_factory,
    )
    if run_request is None:
        return "already_terminal"

    try:
        dependencies = LegacyIssueGraphDependencies(
            gateway=AiGatewayGraphAdapter(resolved_factory),
            data_provider=LangChainLegacyIssueDataProvider(resolved_factory),
            artifact_writer=AiArtifactAnalysisWriter(resolved_factory),
        )
        result = asyncio.run(
            _execute_graph(
                run_id=run_id,
                run_request=run_request,
                dependencies=dependencies,
                session_factory=resolved_factory,
            )
        )
    except Exception as error:
        error_code = f"legacy_analysis.{type(error).__name__}"
        failed_by_this_delivery = _force_failed(
            run_id,
            error_code=error_code,
            session_factory=resolved_factory,
        )
        if not failed_by_this_delivery:
            return "already_running"
        _finalize_failure(
            run_id,
            assistant_turn_id=assistant_turn_id,
            error_code=error_code,
            session_factory=resolved_factory,
        )
        return "failed"

    if result.status == "failed":
        error_code = next(iter(result.errors.values()), "legacy_analysis.failed")
        _finalize_failure(
            run_id,
            assistant_turn_id=assistant_turn_id,
            error_code=error_code,
            session_factory=resolved_factory,
        )
        return "failed"
    if result.status == "skipped":
        return result.reason or "already_running"
    _delete_terminal_input(run_id, session_factory=resolved_factory)
    return "completed"


async def _execute_graph(
    *,
    run_id: str,
    run_request: AiGraphRunRequest,
    dependencies: LegacyIssueGraphDependencies,
    session_factory: sessionmaker[Session],
) -> AiGraphRunResult:
    async with async_postgres_checkpointer() as checkpointer:
        compiled = compile_graph(
            run_request.graph,
            build_legacy_issue_node_adapters(dependencies),
            checkpointer,
        )
        return await run_graph(
            compiled,
            run_request,
            run_id=run_id,
            session_factory=session_factory,
        )


def _load_request(
    run_id: str,
    *,
    session_factory: sessionmaker[Session],
) -> tuple[AiGraphRunRequest | None, str]:
    with session_factory() as db:
        run = AiGraphRunRepository(db).require(run_id)
        if run.status in {"completed", "failed", "cancelled"}:
            return None, ""
        envelope = AiGraphRunInputRepository(db).require(run_id)
        assistant_turn_id = str(envelope.payload_json.get("assistant_turn_id") or "")
        if not assistant_turn_id:
            raise ValueError("analysis assistant_turn_id is missing")
        return (
            AiGraphRunRequest(
                workspace_id=run.workspace_id,
                requested_by_user_id=run.requested_by_user_id,
                app_id=run.app_id,
                graph=legacy_issue_analysis_graph_spec(),
                inputs=dict(envelope.payload_json),
                conversation_id=run.conversation_id,
                visibility=run.visibility,
                checkpoint_ns=run.checkpoint_ns,
            ),
            assistant_turn_id,
        )


def _force_failed(
    run_id: str,
    *,
    error_code: str,
    session_factory: sessionmaker[Session],
) -> bool:
    with session_factory() as db:
        repository = AiGraphRunRepository(db)
        run = repository.require(run_id)
        # Errors outside run_graph happen before this worker owns an execution
        # lease. Never let a duplicate delivery overwrite another worker's
        # fenced running state.
        if run.status == "pending":
            repository.transition(
                run_id,
                "failed",
                stage="graph.failed",
                status_message_key="ai.graphRun.failed",
                error_code=error_code,
            )
            db.commit()
            return True
        return False


def _finalize_failure(
    run_id: str,
    *,
    assistant_turn_id: str,
    error_code: str,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        artifact = db.scalar(
            select(AiArtifact)
            .where(
                AiArtifact.graph_run_id == run_id,
                AiArtifact.status.in_(("pending", "building")),
            )
            .order_by(AiArtifact.created_at, AiArtifact.id)
            .limit(1)
            .with_for_update()
        )
        if artifact is not None:
            AiArtifactRepository(db).fail(artifact, error_code=error_code)
        db.commit()
    mark_analysis_placeholder_failed(
        run_id=run_id,
        assistant_turn_id=assistant_turn_id,
        error_code=error_code,
        session_factory=session_factory,
    )
    _delete_terminal_input(run_id, session_factory=session_factory)


def _delete_terminal_input(
    run_id: str,
    *,
    session_factory: sessionmaker[Session],
) -> None:
    with session_factory() as db:
        AiGraphRunInputRepository(db).delete_after_terminal(run_id)
        db.commit()


__all__ = [
    "execute_legacy_issue_analysis_graph",
]
