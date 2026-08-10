from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.domains.auth.dependencies import require_current_user, require_current_workspace
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from ai_do_api.domains.retrieval import application
from ai_do_api.domains.retrieval.app_catalog import RETRIEVAL_SEARCH_WORKSPACE_APP
from ai_do_api.domains.retrieval.contracts import (
    RetrievalQueryRequest,
    RetrievalQueryResponse,
    RetrievalSourceListResponse,
)


require_retrieval_search_app_enabled = require_workspace_app_enabled(
    RETRIEVAL_SEARCH_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/retrieval",
    tags=["retrieval"],
    dependencies=[Depends(require_retrieval_search_app_enabled)],
)


@router.post("/query", response_model=RetrievalQueryResponse)
def query_workspace_retrieval(
    payload: RetrievalQueryRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> RetrievalQueryResponse:
    return application.query_retrieval(
        db,
        workspace=current_workspace,
        user=current_user,
        request=payload,
    )


@router.get("/sources", response_model=RetrievalSourceListResponse)
def list_workspace_retrieval_sources(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> RetrievalSourceListResponse:
    return application.list_retrieval_sources(
        db,
        workspace=current_workspace,
        user=current_user,
    )
