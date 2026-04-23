from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
    require_workspace_membership,
)
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.rag import application as rag_application
from aidoo_api.domains.rag.contracts import RagAnswerMode, RagQueryResponse
from aidoo_api.domains.rag.filters import RagQueryFilters


class RagQueryRestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    answer_mode: Literal["search-only", "grounded-answer"] = "search-only"
    source_kinds: list[str] = Field(default_factory=list)
    filters: RagQueryFilters = Field(default_factory=RagQueryFilters)
    top_k: int = Field(default=10, ge=1, le=100)
    include_binary_hits: bool = False


class RagSourceDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid")

    source_kind: str
    resource_type: str
    label: str
    app_id: str


class RagSourceListResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    sources: list[RagSourceDescriptor] = Field(default_factory=list)


class RagReindexResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    lane: str
    queued_count: int
    resource_counts: dict[str, int] = Field(default_factory=dict)


router = APIRouter(prefix="/rag", tags=["rag"])


@router.post("/query", response_model=RagQueryResponse)
def query_workspace_rag(
    payload: RagQueryRestRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> RagQueryResponse:
    try:
        return rag_application.query_workspace_rag(
            db,
            workspace=current_workspace,
            user=current_user,
            query=payload.query,
            answer_mode=RagAnswerMode(payload.answer_mode),
            source_kinds=payload.source_kinds,
            filters=payload.filters.to_flat_dict(),
            top_k=payload.top_k,
            include_binary_hits=payload.include_binary_hits,
        )
    except rag_application.RagUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.get("/sources", response_model=RagSourceListResponse)
def list_workspace_rag_sources(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> RagSourceListResponse:
    try:
        return RagSourceListResponse(
            sources=rag_application.list_workspace_rag_sources(
                db,
                workspace=current_workspace,
                user=current_user,
            )
        )
    except rag_application.RagUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error


@router.post("/reindex", response_model=RagReindexResponse)
def reindex_workspace_rag(
    _=Depends(require_workspace_membership("admin")),
    db: Session = Depends(get_db_session),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> RagReindexResponse:
    try:
        response = rag_application.enqueue_workspace_rag_reindex(
            db,
            workspace=current_workspace,
        )
    except rag_application.RagReindexCooldownError as error:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=str(error),
        ) from error
    except rag_application.RagUnavailableError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=str(error),
        ) from error
    db.commit()
    return RagReindexResponse.model_validate(response)
