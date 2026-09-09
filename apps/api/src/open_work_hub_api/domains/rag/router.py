from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.dependencies import require_admin_context, require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.rag import application as rag_application
from open_work_hub_api.domains.rag.contracts import RagAnswerMode, RagQueryResponse
from open_work_hub_api.domains.rag.filters import RagQueryFilters
from open_work_hub_api.domains.retrieval import application as retrieval_application


class RagQueryRestRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, max_length=2000)
    answer_mode: Literal["search-only", "grounded-answer"] = "grounded-answer"
    source_kinds: list[str] = Field(default_factory=list)
    filters: RagQueryFilters = Field(default_factory=RagQueryFilters)
    top_k: int = Field(default=8, ge=1, le=100)
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
def query_rag(
    payload: RagQueryRestRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RagQueryResponse:
    try:
        return retrieval_application.query_rag_response(
            db,
            user=current_user,
            query=payload.query,
            answer_mode=RagAnswerMode(payload.answer_mode),
            source_kinds=payload.source_kinds,
            filters=payload.filters.to_flat_dict(),
            top_k=payload.top_k,
            include_binary_hits=payload.include_binary_hits,
        )
    except rag_application.RagAccessDeniedError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.access_denied")
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=code,
            **params,
        ) from error
    except rag_application.RagUnavailableError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.unavailable")
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=code,
            **params,
        ) from error


@router.get("/sources", response_model=RagSourceListResponse)
def list_rag_sources(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RagSourceListResponse:
    try:
        return RagSourceListResponse(
            sources=retrieval_application.list_rag_sources_response(
                db,
                user=current_user,
            )
        )
    except rag_application.RagAccessDeniedError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.access_denied")
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=code,
            **params,
        ) from error
    except rag_application.RagUnavailableError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.unavailable")
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=code,
            **params,
        ) from error


@router.post("/reindex", response_model=RagReindexResponse)
def reindex_rag(
    _=Depends(require_admin_context),
    db: Session = Depends(get_db_session),
) -> RagReindexResponse:
    try:
        response = rag_application.enqueue_rag_reindex(
            db,
        )
    except rag_application.RagAccessDeniedError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.access_denied")
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code=code,
            **params,
        ) from error
    except rag_application.RagReindexCooldownError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.reindex_cooldown")
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code=code,
            **params,
        ) from error
    except rag_application.RagUnavailableError as error:
        code, params = rag_application.rag_error_payload(error, default_code="rag.unavailable")
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=code,
            **params,
        ) from error
    db.commit()
    return RagReindexResponse.model_validate(response)
