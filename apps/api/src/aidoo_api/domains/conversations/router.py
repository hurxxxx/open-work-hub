"""FastAPI endpoints for chat conversation history.

Mirrors the planner pattern: router mounted twice from ``app.py`` — once
under the legacy ``/api/v1`` prefix (for tools that pre-date workspace
scoping) and once under ``/api/v1/workspaces/{workspace_slug}``. All
handlers use the same ``require_current_workspace`` + ``require_current_user``
dependencies so both mount points enforce membership uniformly.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query, status
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.ai import approvals as ai_approvals
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.meeting import service as meeting_service

from .schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
    ConversationUpdateRequest,
    conversation_detail_from_row,
    conversation_summary_from_row,
)
from .service import (
    create_conversation,
    get_conversation,
    list_conversations,
    rename_conversation,
    soft_delete_conversation,
)


# TODO(phase4): remove this legacy router once all callers have migrated to
# `/ai/conversations`; it remains mounted for backward compatibility only.
router = APIRouter(prefix="/conversations", tags=["conversations"])


@router.get("", response_model=ConversationListResponse)
def list_conversations_endpoint(
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ConversationListResponse:
    rows, next_cursor = list_conversations(
        db,
        workspace=workspace,
        user=current_user,
        limit=limit,
        cursor=cursor,
    )
    return ConversationListResponse(
        items=[conversation_summary_from_row(row) for row in rows],
        next_cursor=next_cursor,
    )


@router.post(
    "",
    response_model=ConversationDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_conversation_endpoint(
    payload: ConversationCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ConversationDetail:
    if payload.scope_ref == "meeting" and payload.scope_resource_id is not None:
        meeting_service.ensure_meeting_scope_access(
            db,
            workspace=workspace,
            user=current_user,
            meeting_id=payload.scope_resource_id,
        )
    conversation = create_conversation(
        db,
        workspace=workspace,
        user=current_user,
        title=payload.title,
        scope_ref=payload.scope_ref,
        scope_resource_id=payload.scope_resource_id,
    )
    return conversation_detail_from_row(conversation)


@router.get("/{conversation_id}", response_model=ConversationDetail)
def get_conversation_endpoint(
    conversation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ConversationDetail:
    conversation = get_conversation(
        db,
        workspace=workspace,
        user=current_user,
        conversation_id=conversation_id,
    )
    live_pending_approval = ai_approvals.get_live_pending_approval(
        db,
        workspace=workspace,
        user=current_user,
        conversation_id=conversation_id,
    )
    return conversation_detail_from_row(
        conversation,
        live_pending_approval=live_pending_approval,
    )


@router.patch("/{conversation_id}", response_model=ConversationDetail)
def rename_conversation_endpoint(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ConversationDetail:
    conversation = rename_conversation(
        db,
        workspace=workspace,
        user=current_user,
        conversation_id=conversation_id,
        title=payload.title,
    )
    return conversation_detail_from_row(conversation)


@router.delete("/{conversation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_conversation_endpoint(
    conversation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> None:
    soft_delete_conversation(
        db,
        workspace=workspace,
        user=current_user,
        conversation_id=conversation_id,
    )
