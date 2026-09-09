from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.domains.auth.app_gate import require_app_access
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.retrieval import application
from open_work_hub_api.domains.retrieval.app_catalog import RETRIEVAL_SEARCH_APP
from open_work_hub_api.domains.retrieval.contracts import (
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalSourceListResponse,
)

require_retrieval_search_app_enabled = require_app_access(
    RETRIEVAL_SEARCH_APP.app_id,
    error_code="app.access_required",
)

router = APIRouter(
    prefix="/retrieval",
    tags=["retrieval"],
    dependencies=[Depends(require_retrieval_search_app_enabled)],
)


@router.post("/query", response_model=RetrievalQueryResponse)
def query_retrieval(
    payload: RetrievalQueryRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RetrievalQueryResponse:
    return application.query_retrieval(
        db,
        user=current_user,
        request=payload,
    )


@router.get("/sources", response_model=RetrievalSourceListResponse)
def list_retrieval_sources(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RetrievalSourceListResponse:
    return application.list_retrieval_sources(
        db,
        user=current_user,
    )
