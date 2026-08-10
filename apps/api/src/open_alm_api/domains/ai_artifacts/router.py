from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.orm import Session

from open_alm_api.core.db import get_db_session
from open_alm_api.domains.ai_artifacts.contracts import (
    AiArtifactDetailResponse,
    AiArtifactIndexGenerationListResponse,
    AiArtifactIndexGenerationResponse,
    AiArtifactListResponse,
    AiArtifactQueryListResponse,
    AiArtifactQueryResponse,
    AiArtifactResponse,
    AiArtifactSourceListResponse,
    AiArtifactSourceResponse,
    ArtifactStatus,
    ArtifactType,
)
from open_alm_api.domains.ai_artifacts.models import (
    AiArtifact,
    AiArtifactIndexGeneration,
    AiArtifactQuery,
    AiArtifactSource,
)
from open_alm_api.domains.ai_artifacts.repository import AiArtifactRepository
from open_alm_api.domains.auth.dependencies import require_current_user, require_current_workspace
from open_alm_api.domains.auth.models import User, Workspace


router = APIRouter(prefix="/ai", tags=["ai-artifacts"])


def _artifact_response(artifact: AiArtifact) -> AiArtifactResponse:
    return AiArtifactResponse.model_validate(artifact)


def _artifact_detail(artifact: AiArtifact) -> AiArtifactDetailResponse:
    return AiArtifactDetailResponse(
        **_artifact_response(artifact).model_dump(),
        payload=artifact.payload_json,
        source_count=len(artifact.sources),
        query_count=len(artifact.queries),
        index_generation_count=len(artifact.index_generations),
    )


def _source_response(source: AiArtifactSource) -> AiArtifactSourceResponse:
    return AiArtifactSourceResponse(
        id=source.id,
        query_id=None,
        ordinal=source.ordinal,
        source_kind=source.source_kind,
        source_ref=source.source_ref,
        source_version=source.source_version,
        title=source.title,
        locator=source.locator_json,
        metadata=source.metadata_json,
        content_sha256=source.content_sha256,
        grid_columns=source.grid_columns_json,
        grid_rows=source.grid_rows_json,
        row_count=source.row_count,
        truncated=source.truncated,
        created_at=source.created_at,
    )


def _query_grid_columns(query: AiArtifactQuery) -> list[dict[str, object]] | None:
    if query.result_schema_json is None:
        return None
    columns: list[dict[str, object]] = []
    for position, source in enumerate(query.result_schema_json):
        key = str(source.get("key") or source.get("name") or f"column_{position + 1}")
        columns.append(
            {
                **source,
                "key": key,
                "label": str(source.get("label") or key),
            }
        )
    return columns


def _query_source_response(
    query: AiArtifactQuery,
    *,
    ordinal: int,
) -> AiArtifactSourceResponse:
    return AiArtifactSourceResponse(
        id=query.id,
        query_id=query.id,
        ordinal=ordinal,
        source_kind="sql_query",
        source_ref=f"query:{query.id}",
        source_version=None,
        title=query.title or query.family_id or "SQL query result",
        locator={
            "queryId": query.id,
            "queryKind": query.query_kind,
            "familyId": query.family_id,
        },
        metadata={
            "executionStatus": query.execution_status,
            "errorCode": query.error_code,
            "exactness": query.exactness,
            "durationMs": query.duration_ms,
            "payloadBytes": query.payload_bytes,
        },
        content_sha256=query.result_sha256,
        grid_columns=_query_grid_columns(query),
        grid_rows=query.result_rows_json,
        row_count=query.row_count,
        truncated=query.truncated,
        created_at=query.created_at,
    )


def _query_response(query: AiArtifactQuery) -> AiArtifactQueryResponse:
    return AiArtifactQueryResponse(
        id=query.id,
        ordinal=query.ordinal,
        query_kind=query.query_kind,
        title=query.title,
        family_id=query.family_id,
        query_spec=query.query_spec_json,
        statement_text=query.statement_text,
        typed_params=query.typed_params_json,
        execution_status=query.execution_status,
        error_code=query.error_code,
        result_schema=query.result_schema_json,
        result_rows=query.result_rows_json,
        query_sha256=query.query_sha256,
        result_sha256=query.result_sha256,
        row_count=query.row_count,
        duration_ms=query.duration_ms,
        truncated=query.truncated,
        payload_bytes=query.payload_bytes,
        exactness=query.exactness,
        created_at=query.created_at,
    )


def _generation_response(
    generation: AiArtifactIndexGeneration,
) -> AiArtifactIndexGenerationResponse:
    return AiArtifactIndexGenerationResponse(
        id=generation.id,
        ordinal=generation.ordinal,
        index_generation_id=generation.index_generation_id,
        metadata=generation.metadata_json,
        created_at=generation.created_at,
    )


def _visible_artifact(
    db: Session,
    *,
    identifier: str,
    workspace: Workspace,
    user: User,
    eager: bool = False,
) -> AiArtifact:
    artifact = AiArtifactRepository(db).get_visible(
        identifier,
        workspace_id=workspace.id,
        user_id=user.id,
        eager=eager,
    )
    if artifact is None:
        raise HTTPException(status_code=404, detail={"code": "ai.artifact_not_found"})
    return artifact


@router.get("/artifacts", response_model=AiArtifactListResponse)
def list_artifacts(
    artifact_type: ArtifactType | None = None,
    status: ArtifactStatus | None = "completed",
    app_id: str | None = Query(default=None, max_length=64),
    graph_run_id: str | None = Query(default=None, max_length=36),
    conversation_id: str | None = Query(default=None, max_length=36),
    limit: int = Query(default=50, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> AiArtifactListResponse:
    items, total = AiArtifactRepository(db).list_visible(
        workspace_id=current_workspace.id,
        user_id=current_user.id,
        artifact_type=artifact_type,
        status=status,
        app_id=app_id,
        graph_run_id=graph_run_id,
        conversation_id=conversation_id,
        limit=limit,
        offset=offset,
    )
    return AiArtifactListResponse(
        items=[_artifact_response(item) for item in items],
        total=total,
    )


@router.get("/artifacts/{artifact_id}", response_model=AiArtifactDetailResponse)
def get_artifact(
    artifact_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> AiArtifactDetailResponse:
    return _artifact_detail(
        _visible_artifact(
            db,
            identifier=artifact_id,
            workspace=current_workspace,
            user=current_user,
            eager=True,
        )
    )


@router.get(
    "/artifacts/{artifact_id}/sources",
    response_model=AiArtifactSourceListResponse,
)
def list_artifact_sources(
    artifact_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> AiArtifactSourceListResponse:
    artifact = _visible_artifact(
        db,
        identifier=artifact_id,
        workspace=current_workspace,
        user=current_user,
        eager=True,
    )
    return AiArtifactSourceListResponse(
        items=[
            *[
                _query_source_response(
                    item,
                    ordinal=position,
                )
                for position, item in enumerate(artifact.queries)
            ],
            *[
                _source_response(item).model_copy(
                    update={"ordinal": len(artifact.queries) + position}
                )
                for position, item in enumerate(artifact.sources)
            ],
        ]
    )


@router.get(
    "/artifacts/{artifact_id}/queries",
    response_model=AiArtifactQueryListResponse,
)
def list_artifact_queries(
    artifact_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> AiArtifactQueryListResponse:
    artifact = _visible_artifact(
        db,
        identifier=artifact_id,
        workspace=current_workspace,
        user=current_user,
        eager=True,
    )
    return AiArtifactQueryListResponse(
        items=[_query_response(item) for item in artifact.queries]
    )


@router.get(
    "/artifacts/{artifact_id}/index-generations",
    response_model=AiArtifactIndexGenerationListResponse,
)
def list_artifact_index_generations(
    artifact_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> AiArtifactIndexGenerationListResponse:
    artifact = _visible_artifact(
        db,
        identifier=artifact_id,
        workspace=current_workspace,
        user=current_user,
        eager=True,
    )
    return AiArtifactIndexGenerationListResponse(
        items=[_generation_response(item) for item in artifact.index_generations]
    )
