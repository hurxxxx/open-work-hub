from __future__ import annotations

from fastapi import APIRouter, Depends, Query, Response, status
from sqlalchemy.orm import Session

from ai_do_api.core.db import get_db_session
from ai_do_api.domains.auth.dependencies import require_current_user
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.auth.workspace_app_gate import require_platform_app_enabled
from ai_do_api.domains.mail import service
from ai_do_api.domains.mail.app_catalog import MAIL_WORKSPACE_APP
from ai_do_api.domains.mail.schemas import (
    MailAccountConnectionRequest,
    MailAccountOut,
    MailAccountUpdateRequest,
    MailConnectionTestResponse,
    MailDraftOut,
    MailDraftUpdateRequest,
    MailMessageDetail,
    MailMessageFlagsRequest,
    MailMessageListResponse,
    MailMessageSummary,
    MailReplyDraftRequest,
    MailSummaryResponse,
    MailSyncResponse,
)


require_mail_app_enabled = require_platform_app_enabled(
    MAIL_WORKSPACE_APP.app_id,
    error_code="platform.app_disabled",
)

router = APIRouter(
    prefix="/mail",
    tags=["mail"],
    dependencies=[Depends(require_mail_app_enabled)],
)


@router.post("/accounts/test", response_model=MailConnectionTestResponse)
def test_mail_account_connection(
    payload: MailAccountConnectionRequest,
    current_user: User = Depends(require_current_user),
) -> MailConnectionTestResponse:
    del current_user
    return service.test_connection(payload)


@router.post("/accounts", response_model=MailAccountOut, status_code=status.HTTP_201_CREATED)
def create_mail_account(
    payload: MailAccountConnectionRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailAccountOut:
    return service.create_account(db, user=current_user, payload=payload)


@router.get("/accounts", response_model=list[MailAccountOut])
def list_mail_accounts(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[MailAccountOut]:
    return service.list_accounts(db, user=current_user)


@router.patch("/accounts/{account_id}", response_model=MailAccountOut)
def update_mail_account(
    account_id: str,
    payload: MailAccountUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailAccountOut:
    return service.update_account(
        db,
        user=current_user,
        account_id=account_id,
        payload=payload,
    )


@router.delete("/accounts/{account_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_mail_account(
    account_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    service.delete_account(db, user=current_user, account_id=account_id)
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/accounts/{account_id}/sync", response_model=MailSyncResponse, status_code=202)
def sync_mail_account(
    account_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailSyncResponse:
    account, job_id = service.enqueue_account_sync(
        db,
        user=current_user,
        account_id=account_id,
    )
    return MailSyncResponse(account=account, queued=True, job_id=job_id, task_id=job_id)


@router.get("/messages", response_model=MailMessageListResponse)
def list_mail_messages(
    account_id: str | None = Query(default=None),
    query: str | None = Query(default=None, max_length=200),
    unread: bool | None = Query(default=None),
    starred: bool | None = Query(default=None),
    limit: int = Query(default=50, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailMessageListResponse:
    return service.list_messages(
        db,
        user=current_user,
        account_id=account_id,
        query=query,
        unread=unread,
        starred=starred,
        limit=limit,
    )


@router.get("/messages/{message_id}", response_model=MailMessageDetail)
def get_mail_message(
    message_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailMessageDetail:
    return service.get_message(db, user=current_user, message_id=message_id)


@router.patch("/messages/{message_id}/flags", response_model=MailMessageSummary)
def update_mail_message_flags(
    message_id: str,
    payload: MailMessageFlagsRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailMessageSummary:
    return service.update_message_flags(
        db,
        user=current_user,
        message_id=message_id,
        payload=payload,
    )


@router.post("/messages/{message_id}/summarize", response_model=MailSummaryResponse)
def summarize_mail_message(
    message_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailSummaryResponse:
    return service.summarize_message(
        db,
        user=current_user,
        message_id=message_id,
    )


@router.post("/messages/{message_id}/reply-draft", response_model=MailDraftOut)
def create_mail_reply_draft(
    message_id: str,
    payload: MailReplyDraftRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailDraftOut:
    return service.create_reply_draft(
        db,
        user=current_user,
        message_id=message_id,
        instruction=payload.instruction,
    )


@router.get("/drafts", response_model=list[MailDraftOut])
def list_mail_drafts(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[MailDraftOut]:
    return service.list_drafts(db, user=current_user)


@router.patch("/drafts/{draft_id}", response_model=MailDraftOut)
def update_mail_draft(
    draft_id: str,
    payload: MailDraftUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailDraftOut:
    return service.update_draft(
        db,
        user=current_user,
        draft_id=draft_id,
        payload=payload,
    )


@router.post("/drafts/{draft_id}/send", response_model=MailDraftOut)
def send_mail_draft(
    draft_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> MailDraftOut:
    return service.send_draft(db, user=current_user, draft_id=draft_id)
