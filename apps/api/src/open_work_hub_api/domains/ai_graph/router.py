from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import case, or_, select
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.ai_artifacts.models import AiArtifact
from open_work_hub_api.domains.ai_graph.contracts import (
    AiGraphRunListResponse,
    AiGraphRunResponse,
    GraphRunStatus,
)
from open_work_hub_api.domains.ai_graph.repository import AiGraphRunRepository
from open_work_hub_api.domains.auth.app_gate import (
    allowed_app_ids,
)
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User

router = APIRouter(prefix="/ai", tags=["ai-graph-runs"])


def _artifact_ids_by_run(
    db: Session,
    run_ids: list[str],
    *,
    user_id: str,
    enabled_app_ids: frozenset[str],
) -> dict[str, str]:
    if not run_ids:
        return {}
    rows = db.execute(
        select(AiArtifact.graph_run_id, AiArtifact.id)
        .where(
            AiArtifact.graph_run_id.in_(run_ids),
            AiArtifact.app_id.in_(enabled_app_ids),
            or_(
                AiArtifact.owner_user_id == user_id,
                AiArtifact.visibility == "company",
            ),
        )
        .order_by(
            case((AiArtifact.status == "completed", 0), else_=1),
            AiArtifact.completed_at.desc().nullslast(),
            AiArtifact.created_at.desc(),
            AiArtifact.id.desc(),
        )
    )
    result: dict[str, str] = {}
    for graph_run_id, artifact_id in rows:
        if graph_run_id is not None:
            result.setdefault(graph_run_id, artifact_id)
    return result


def _run_response(run, artifact_id: str | None) -> AiGraphRunResponse:
    return AiGraphRunResponse.model_validate(run).model_copy(update={"artifact_id": artifact_id})


@router.get("/graph-runs", response_model=AiGraphRunListResponse)
def list_graph_runs(
    status: GraphRunStatus | None = None,
    app_id: str | None = Query(default=None, max_length=64),
    conversation_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> AiGraphRunListResponse:
    enabled_app_ids = allowed_app_ids(
        db,
        user_id=current_user.id,
    )
    items, total = AiGraphRunRepository(db).list_visible(
        user_id=current_user.id,
        status=status,
        app_id=app_id,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
        enabled_app_ids=enabled_app_ids,
    )
    artifact_ids = _artifact_ids_by_run(
        db,
        [item.id for item in items],
        user_id=current_user.id,
        enabled_app_ids=enabled_app_ids,
    )
    return AiGraphRunListResponse(
        items=[_run_response(item, artifact_ids.get(item.id)) for item in items],
        total=total,
    )


@router.get("/graph-runs/{run_id}", response_model=AiGraphRunResponse)
def get_graph_run(
    run_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> AiGraphRunResponse:
    enabled_app_ids = allowed_app_ids(
        db,
        user_id=current_user.id,
    )
    run = AiGraphRunRepository(db).get_visible(
        run_id,
        user_id=current_user.id,
        enabled_app_ids=enabled_app_ids,
    )
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "ai.graph_run_not_found"})
    artifact_ids = _artifact_ids_by_run(
        db,
        [run.id],
        user_id=current_user.id,
        enabled_app_ids=enabled_app_ids,
    )
    return _run_response(run, artifact_ids.get(run.id))
