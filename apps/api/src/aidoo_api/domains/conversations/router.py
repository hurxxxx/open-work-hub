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
from aidoo_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from aidoo_api.domains.auth.models import User, Workspace

from .schemas import (
    ArtifactOut,
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
    ConversationSummary,
    ConversationTurnOut,
    ConversationUpdateRequest,
)
from .service import (
    create_conversation,
    get_conversation,
    list_conversations,
    rename_conversation,
    soft_delete_conversation,
)


router = APIRouter(prefix="/conversations", tags=["conversations"])


def _to_summary(row) -> ConversationSummary:
    return ConversationSummary(
        id=row.id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
    )


def _turn_out(turn) -> ConversationTurnOut:
    # The stored meta dict is a loose bag of fields the streaming agent emits.
    # Keys are lifted into explicit typed properties so the frontend renders a
    # reloaded conversation identically to a live one; unknown extra keys are
    # dropped silently rather than leaking into the API contract.
    meta = turn.meta or {}
    raw_artifacts = meta.get("artifacts") or []
    artifacts: list[ArtifactOut] = []
    for record in raw_artifacts:
        if not isinstance(record, dict):
            continue
        artifact_id = record.get("id")
        if not artifact_id:
            continue
        artifacts.append(
            ArtifactOut(
                id=artifact_id,
                type=record.get("type") or "document",
                title=record.get("title"),
                content=record.get("content") or "",
                status=record.get("status"),
            )
        )
    return ConversationTurnOut(
        id=turn.id,
        seq=turn.seq,
        role=turn.role,
        content=turn.content,
        reasoning=meta.get("reasoning"),
        reasoning_status=meta.get("reasoning_status"),
        finish_reason=meta.get("finish_reason"),
        response_status=meta.get("response_status"),
        provider=meta.get("provider"),
        policy=meta.get("policy"),
        chosen_pool=meta.get("chosen_pool"),
        decision_reason=meta.get("decision_reason"),
        forced_local=meta.get("forced_local"),
        pii_hits=list(meta.get("pii_hits") or []),
        tool_calls=list(meta.get("tool_calls") or []),
        pending_approvals=list(meta.get("pending_approvals") or []),
        artifacts=artifacts,
        created_at=turn.created_at,
    )


def _to_detail(row) -> ConversationDetail:
    return ConversationDetail(
        id=row.id,
        title=row.title,
        created_at=row.created_at,
        updated_at=row.updated_at,
        turns=[_turn_out(t) for t in row.turns],
    )


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
        items=[_to_summary(row) for row in rows],
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
    conversation = create_conversation(
        db,
        workspace=workspace,
        user=current_user,
        title=payload.title,
    )
    return _to_detail(conversation)


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
    return _to_detail(conversation)


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
    return _to_detail(conversation)


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
