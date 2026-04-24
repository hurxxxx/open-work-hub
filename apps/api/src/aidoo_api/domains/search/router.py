from __future__ import annotations

from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.dependencies import require_current_user, require_current_workspace
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.search import service
from aidoo_api.domains.search.schemas import KeywordSearchRequest, KeywordSearchResponse


router = APIRouter(prefix="/search", tags=["search"])


@router.post("/query", response_model=KeywordSearchResponse)
def query_workspace_search(
    payload: KeywordSearchRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> KeywordSearchResponse:
    return service.query_workspace_keyword_search(
        db,
        workspace=current_workspace,
        user=current_user,
        request=payload,
    )
