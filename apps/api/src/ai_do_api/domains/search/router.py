from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.domains.auth.dependencies import require_current_user, require_current_workspace
from ai_do_api.domains.auth.models import User, Workspace
from ai_do_api.domains.retrieval import application as retrieval_application
from ai_do_api.domains.search.schemas import KeywordSearchRequest, KeywordSearchResponse


router = APIRouter(prefix="/search", tags=["search"])


@router.post("/query", response_model=KeywordSearchResponse)
def query_workspace_search(
    payload: KeywordSearchRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> KeywordSearchResponse:
    return retrieval_application.query_workspace_keyword_search_response(
        db,
        workspace=current_workspace,
        user=current_user,
        request=payload,
    )
