from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ai_do_api.domains.ai_artifacts.contracts import AiArtifactCreate
from ai_do_api.domains.ai_artifacts.models import AiArtifact
from ai_do_api.domains.ai_artifacts.repository import AiArtifactRepository
from ai_do_api.domains.ai_graph.contracts import AiGraphDispatchCreate, AiGraphRunRequest
from ai_do_api.domains.ai_graph.models import (
    AiGraphDispatchOutbox,
    AiGraphRun,
    AiGraphRunInput,
)
from ai_do_api.domains.ai_graph.repository import (
    AiGraphDispatchRepository,
    AiGraphRunInputRepository,
    AiGraphRunRepository,
)


@dataclass(frozen=True)
class PreparedGraphDispatch:
    graph_run: AiGraphRun
    pending_artifact: AiArtifact
    run_input: AiGraphRunInput
    outbox: AiGraphDispatchOutbox


def stage_graph_dispatch(
    db: Session,
    *,
    run_request: AiGraphRunRequest,
    pending_artifact: AiArtifactCreate,
    payload_ref: str | None = None,
) -> PreparedGraphDispatch:
    """Stage run, bootstrap input, placeholder and outbox in the caller transaction.

    By default ``payload_ref`` addresses the immutable bootstrap-input row.
    Mutable execution state belongs exclusively to LangGraph checkpoints.
    """

    _validate_dispatch_coherence(run_request, pending_artifact)
    run = AiGraphRunRepository(db).create(run_request)
    run_input = AiGraphRunInputRepository(db).create(
        graph_run_id=run.id,
        payload=run_request.inputs,
        schema_version=run_request.graph.state_schema_version,
    )
    artifact_request = pending_artifact.model_copy(update={"graph_run_id": run.id})
    artifact = AiArtifactRepository(db).create_pending(artifact_request)
    outbox = AiGraphDispatchRepository(db).enqueue(
        AiGraphDispatchCreate(
            graph_run_id=run.id,
            payload_ref=payload_ref or f"ai-graph-input:{run.id}",
        )
    )
    return PreparedGraphDispatch(
        graph_run=run,
        pending_artifact=artifact,
        run_input=run_input,
        outbox=outbox,
    )


def _validate_dispatch_coherence(
    run_request: AiGraphRunRequest,
    artifact: AiArtifactCreate,
) -> None:
    mismatches: list[str] = []
    if artifact.workspace_id != run_request.workspace_id:
        mismatches.append("workspace_id")
    if artifact.app_id != run_request.app_id:
        mismatches.append("app_id")
    if artifact.owner_user_id != run_request.requested_by_user_id:
        mismatches.append("owner_user_id")
    if artifact.conversation_id != run_request.conversation_id:
        mismatches.append("conversation_id")
    if artifact.visibility != run_request.visibility:
        mismatches.append("visibility")
    if artifact.graph_run_id is not None:
        mismatches.append("graph_run_id")
    if mismatches:
        raise ValueError(
            "pending artifact does not match graph run: " + ", ".join(mismatches)
        )


def prepare_graph_dispatch(
    db: Session,
    *,
    run_request: AiGraphRunRequest,
    pending_artifact: AiArtifactCreate,
    payload_ref: str | None = None,
) -> PreparedGraphDispatch:
    """Stage and commit the dispatch aggregate before any broker publish."""

    prepared = stage_graph_dispatch(
        db,
        run_request=run_request,
        pending_artifact=pending_artifact,
        payload_ref=payload_ref,
    )
    db.commit()
    db.refresh(prepared.graph_run)
    db.refresh(prepared.pending_artifact)
    db.refresh(prepared.run_input)
    db.refresh(prepared.outbox)
    return prepared
