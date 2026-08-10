from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta
import logging
from typing import Any

from sqlalchemy import event, func, or_, select
from sqlalchemy.orm import Session, selectinload

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.llm import LlmRuntimeError, LlmTaskContext
from ai_do_api.core.settings import get_settings
from ai_do_api.domains.ai.gateway import (
    LlmWorkloadContext,
    execute_llm,
)
from ai_do_api.domains.auth.access import record_audit_log
from ai_do_api.domains.auth.models import User, Workspace, utcnow_naive
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.auth.workspace_app_gate import is_platform_app_enabled
from ai_do_api.domains.mail.clients import (
    MailConnectionSettings,
    MailConnectionPolicyError,
    MailProtocolClient,
    StdlibMailClient,
)
from ai_do_api.domains.mail.connection_profile import (
    enforce_connection_profile,
    encrypt_connection_secrets,
    incoming_identity,
    settings_from_account,
    settings_from_account_update,
    settings_from_payload,
    validate_connection_profile,
)
from ai_do_api.domains.mail.crypto import MailCredentialError
from ai_do_api.domains.mail.models import (
    MailAccount,
    MailAttachment,
    MailDraft,
    MailMailbox,
    MailMessage,
    MailMessageBody,
    MailSendAttempt,
    MailSyncJob,
    MailSyncState,
)
from ai_do_api.domains.mail.message_projection import (
    build_message_detail,
    build_message_list_response,
    mail_prompt_context,
    message_text,
    reply_subject,
)
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
    MailSummaryResponse,
)
from ai_do_api.domains.mail.sync_batch import (
    MailSyncResult,
    apply_sync_batch,
    cursor_for_mailbox_sync,
)
from ai_do_api.domains.mail.sync_mailboxes import (
    ensure_inbox_mailbox,
    sync_targets_for_account,
)
from ai_do_api.domains.mail.sync_jobs import (
    MailSyncRetryScheduled,
    clear_pending_mail_sync_job_publications,
    enqueue_sync_job as _enqueue_sync_job,
    mark_sync_job_failed,
    pop_pending_mail_sync_job_publications,
    publish_due_mail_sync_jobs as _publish_due_mail_sync_jobs,
    publish_sync_job,
    seconds_until,
)


logger = logging.getLogger(__name__)
MAIL_APP_ID = "mail"
PERSONAL_MAIL_LLM_SCOPE = "personal"


def mail_background_sync_enabled(db: Session) -> bool:
    return is_platform_app_enabled(db, MAIL_APP_ID)


def _mail_client() -> MailProtocolClient:
    return StdlibMailClient()


def test_connection(
    payload: MailAccountConnectionRequest,
    *,
    client: MailProtocolClient | None = None,
) -> MailConnectionTestResponse:
    return _test_connection_settings(settings_from_payload(payload), client=client)


def _test_connection_settings(
    settings: MailConnectionSettings,
    *,
    client: MailProtocolClient | None = None,
) -> MailConnectionTestResponse:
    mail_client = client or _mail_client()
    incoming_error = validate_connection_profile(settings, incoming=True, smtp=False)
    smtp_error = validate_connection_profile(settings, incoming=False, smtp=True)
    if incoming_error is None:
        try:
            mail_client.test_incoming(settings)
        except Exception as exc:
            incoming_error = _public_error(exc)
    if smtp_error is None:
        try:
            mail_client.test_smtp(settings)
        except Exception as exc:
            smtp_error = _public_error(exc)
    return MailConnectionTestResponse(
        incoming_ok=incoming_error is None,
        smtp_ok=smtp_error is None,
        incoming_error=incoming_error,
        smtp_error=smtp_error,
    )


def create_account(
    db: Session,
    *,
    user: User,
    payload: MailAccountConnectionRequest,
    client: MailProtocolClient | None = None,
) -> MailAccountOut:
    settings = settings_from_payload(payload)
    email_address = settings.email_address
    result = test_connection(payload, client=client)
    if not result.incoming_ok or not result.smtp_ok:
        raise localized_http_exception(
            status_code=400,
            code="mail.connection_failed",
            error=result.incoming_error or result.smtp_error or "connection failed",
        )
    secrets = encrypt_connection_secrets(settings)

    row = MailAccount(
        id=new_id(),
        user_id=user.id,
        email_address=email_address,
    )
    row.display_name = settings.display_name
    row.account_label = payload.account_label.strip() or settings.display_name or email_address
    row.protocol = settings.protocol
    row.provider_kind = settings.provider_kind
    row.incoming_host = settings.incoming_host
    row.incoming_port = settings.incoming_port
    row.incoming_security = settings.incoming_security
    row.incoming_username = settings.incoming_username
    row.incoming_password_encrypted = secrets.incoming_password_encrypted
    row.smtp_host = settings.smtp_host
    row.smtp_port = settings.smtp_port
    row.smtp_security = settings.smtp_security
    row.smtp_username = settings.smtp_username
    row.smtp_password_encrypted = secrets.smtp_password_encrypted
    row.sync_enabled = True
    row.status = "ready"
    row.last_error = None
    row.last_sync_new_count = 0
    row.last_sync_updated_count = 0
    row.last_sync_deleted_count = 0
    row.deleted_at = None
    row.updated_at = utcnow_naive()
    db.add(row)
    ensure_inbox_mailbox(db, account=row)
    db.commit()
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="mail.account.create",
        entity_kind="mail_account",
        entity_id=row.id,
        summary=f"Connected mail account {row.email_address}",
        payload={"scope": "personal", "protocol": row.protocol},
    )
    db.commit()
    db.refresh(row)
    return MailAccountOut.model_validate(row)


def update_account(
    db: Session,
    *,
    user: User,
    account_id: str,
    payload: MailAccountUpdateRequest,
    client: MailProtocolClient | None = None,
) -> MailAccountOut:
    row = _load_account(db, user=user, account_id=account_id, for_update=True)
    settings = settings_from_account_update(row, payload)
    result = _test_connection_settings(settings, client=client)
    if not result.incoming_ok or not result.smtp_ok:
        raise localized_http_exception(
            status_code=400,
            code="mail.connection_failed",
            error=result.incoming_error or result.smtp_error or "connection failed",
        )

    incoming_identity_changed = incoming_identity(row) != incoming_identity(settings)
    secrets = (
        encrypt_connection_secrets(settings)
        if payload.incoming_password or payload.smtp_password
        else None
    )

    if incoming_identity_changed:
        _purge_account_mailbox_data(db, account=row)
        row.last_sync_at = None
        row.last_sync_new_count = 0
        row.last_sync_updated_count = 0
        row.last_sync_deleted_count = 0

    row.email_address = settings.email_address
    row.display_name = settings.display_name
    if payload.account_label is not None:
        row.account_label = (
            payload.account_label.strip() or settings.display_name or settings.email_address
        )
    row.protocol = settings.protocol
    row.provider_kind = settings.provider_kind
    row.incoming_host = settings.incoming_host
    row.incoming_port = settings.incoming_port
    row.incoming_security = settings.incoming_security
    row.incoming_username = settings.incoming_username
    if payload.incoming_password and secrets is not None:
        row.incoming_password_encrypted = secrets.incoming_password_encrypted
    row.smtp_host = settings.smtp_host
    row.smtp_port = settings.smtp_port
    row.smtp_security = settings.smtp_security
    row.smtp_username = settings.smtp_username
    if payload.smtp_password and secrets is not None:
        row.smtp_password_encrypted = secrets.smtp_password_encrypted
    row.sync_enabled = True
    row.status = "ready"
    row.last_error = None
    row.updated_at = utcnow_naive()
    db.add(row)
    ensure_inbox_mailbox(db, account=row)
    db.commit()
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="mail.account.update",
        entity_kind="mail_account",
        entity_id=row.id,
        summary=f"Updated mail account {row.email_address}",
        payload={
            "scope": "personal",
            "protocol": row.protocol,
            "incoming_identity_changed": incoming_identity_changed,
        },
    )
    db.commit()
    db.refresh(row)
    return MailAccountOut.model_validate(row)


def list_accounts(db: Session, *, user: User) -> list[MailAccountOut]:
    rows = db.scalars(
        select(MailAccount)
        .where(
            MailAccount.user_id == user.id,
            MailAccount.deleted_at.is_(None),
        )
        .order_by(MailAccount.created_at.asc(), MailAccount.id.asc())
    ).all()
    return [MailAccountOut.model_validate(row) for row in rows]


def delete_account(db: Session, *, user: User, account_id: str) -> None:
    row = _load_account(db, user=user, account_id=account_id)
    email_address = row.email_address
    _purge_account_data(db, account=row)
    record_audit_log(
        db,
        actor_user_id=user.id,
        action="mail.account.delete",
        entity_kind="mail_account",
        entity_id=account_id,
        summary=f"Disconnected mail account {email_address}",
        payload={"scope": "personal"},
    )
    db.commit()


def enqueue_account_sync(
    db: Session,
    *,
    user: User,
    account_id: str,
) -> tuple[MailAccountOut, str]:
    if not mail_background_sync_enabled(db):
        raise localized_http_exception(status_code=403, code="platform.app_disabled")
    row = _load_account(db, user=user, account_id=account_id, for_update=True)
    mailbox, state = ensure_inbox_mailbox(db, account=row)
    operation = "initial" if not state.cursor_json else "incremental"
    job = _enqueue_sync_job(db, account=row, mailbox=mailbox, operation=operation)
    row.status = "sync_queued"
    row.last_error = None
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()
    db.refresh(row)
    return MailAccountOut.model_validate(row), job.id


def sync_account(
    db: Session,
    *,
    account_id: str,
    client: MailProtocolClient | None = None,
    limit: int | None = None,
    operation: str | None = None,
) -> MailSyncResult:
    if not mail_background_sync_enabled(db):
        return MailSyncResult(new_count=0, updated_count=0, deleted_count=0)
    row = db.get(MailAccount, account_id)
    if row is None or row.deleted_at is not None:
        return MailSyncResult(new_count=0, updated_count=0, deleted_count=0)
    mail_client = client or _mail_client()
    max_messages = limit or get_settings().mail_sync_max_messages
    row.status = "syncing"
    row.last_error = None
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()
    states: list[MailSyncState] = []
    try:
        settings = settings_from_account(row)
        enforce_connection_profile(settings, incoming=True, smtp=False)
        targets = sync_targets_for_account(
            db,
            account=row,
            settings=settings,
            client=mail_client,
        )
        states = [state for _mailbox, state in targets]
        for state in states:
            state.status = "syncing"
            state.last_error = None
            state.updated_at = utcnow_naive()
            db.add(state)
        db.commit()
        result = MailSyncResult(new_count=0, updated_count=0, deleted_count=0)
        for mailbox, state in targets:
            sync_operation = operation or ("initial" if not state.cursor_json else "incremental")
            sync_cursor = cursor_for_mailbox_sync(
                db,
                account=row,
                mailbox=mailbox,
                cursor=dict(state.cursor_json or {}),
            )
            batch = mail_client.sync_mailbox(
                settings,
                mailbox=mailbox.provider_mailbox_id,
                cursor=sync_cursor,
                initial_limit=max_messages,
            )
            mailbox_result = apply_sync_batch(
                db,
                account=row,
                mailbox=mailbox,
                batch=batch,
            )
            result = MailSyncResult(
                new_count=result.new_count + mailbox_result.new_count,
                updated_count=result.updated_count + mailbox_result.updated_count,
                deleted_count=result.deleted_count + mailbox_result.deleted_count,
            )
            now = utcnow_naive()
            state.status = "idle"
            state.cursor_json = batch.cursor
            state.last_error = None
            if sync_operation == "initial" or batch.reset_mailbox:
                state.last_full_sync_at = now
            else:
                state.last_incremental_sync_at = now
            state.updated_at = now
            db.add(state)
        now = utcnow_naive()
        row.status = "ready"
        row.last_sync_at = now
        row.last_error = None
        row.last_sync_new_count = result.new_count
        row.last_sync_updated_count = result.updated_count
        row.last_sync_deleted_count = result.deleted_count
        row.updated_at = now
        db.add(row)
        db.commit()
        return result
    except Exception as exc:
        db.rollback()
        row = db.get(MailAccount, account_id)
        if row is not None:
            row.status = "failed"
            row.last_error = _public_error(exc)
            row.updated_at = utcnow_naive()
            db.add(row)
        for state in states:
            state.status = "failed"
            state.last_error = _public_error(exc)
            state.updated_at = utcnow_naive()
            db.add(state)
        if row is not None or states:
            db.commit()
        logger.warning("mail sync failed for account %s", account_id, exc_info=exc)
        raise


def list_messages(
    db: Session,
    *,
    user: User,
    account_id: str | None = None,
    query: str | None = None,
    unread: bool | None = None,
    starred: bool | None = None,
    limit: int = 50,
) -> MailMessageListResponse:
    if account_id is not None:
        _load_account(db, user=user, account_id=account_id)
    stmt = (
        select(MailMessage)
        .join(MailAccount, MailMessage.account_id == MailAccount.id)
        .where(
            MailAccount.user_id == user.id,
            MailAccount.deleted_at.is_(None),
            MailMessage.remote_deleted_at.is_(None),
        )
    )
    count_stmt = (
        select(func.count(MailMessage.id))
        .select_from(MailMessage)
        .join(MailAccount, MailMessage.account_id == MailAccount.id)
        .where(
            MailAccount.user_id == user.id,
            MailAccount.deleted_at.is_(None),
            MailMessage.remote_deleted_at.is_(None),
        )
    )
    filters = []
    if account_id:
        filters.append(MailMessage.account_id == account_id)
    if unread is not None:
        filters.append(MailMessage.is_read.is_(not unread))
    if starred is not None:
        filters.append(MailMessage.is_starred.is_(starred))
    if query:
        pattern = f"%{query.strip()}%"
        filters.append(
            or_(
                MailMessage.subject.ilike(pattern),
                MailMessage.from_text.ilike(pattern),
                MailMessage.snippet.ilike(pattern),
            )
        )
    if filters:
        stmt = stmt.where(*filters)
        count_stmt = count_stmt.where(*filters)
    rows = db.scalars(
        stmt.order_by(
            MailMessage.received_at.desc().nullslast(), MailMessage.created_at.desc()
        ).limit(limit)
    ).all()
    total = db.scalar(count_stmt) or 0
    return build_message_list_response(rows, total=total)


def get_message(
    db: Session,
    *,
    user: User,
    message_id: str,
) -> MailMessageDetail:
    row = _load_message(db, user=user, message_id=message_id)
    return build_message_detail(row)


def update_message_flags(
    db: Session,
    *,
    user: User,
    message_id: str,
    payload: MailMessageFlagsRequest,
) -> MailMessageSummary:
    row = _load_message(db, user=user, message_id=message_id)
    local_state = dict(row.local_state_json or {})
    if payload.is_read is not None:
        row.is_read = payload.is_read
        local_state["is_read"] = payload.is_read
    if payload.is_starred is not None:
        row.is_starred = payload.is_starred
        local_state["is_starred"] = payload.is_starred
    row.local_state_json = local_state
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()
    db.refresh(row)
    return MailMessageSummary.model_validate(row)


def summarize_message(
    db: Session,
    *,
    user: User,
    message_id: str,
) -> MailSummaryResponse:
    row = _load_message(db, user=user, message_id=message_id)
    body_text = message_text(row)
    try:
        completion = execute_llm(
            "mail_summarize",
            LlmWorkloadContext.from_task_context(
                LlmTaskContext(
                    source="api.mail.summarize",
                    actor_user_id=user.id,
                    workspace_id=PERSONAL_MAIL_LLM_SCOPE,
                    task_kind="mail_summarize",
                    app_id="mail",
                )
            ),
            db,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You summarize internal business emails in Korean. "
                        "Use only the supplied email content. Keep it concise."
                    ),
                },
                {
                    "role": "user",
                    "content": mail_prompt_context(row, body_text),
                },
            ],
            temperature=0,
            max_tokens=1200,
            reasoning_effort="none",
            audit_entity_id=row.id,
        ).completion
    except LlmRuntimeError as exc:
        raise localized_http_exception(status_code=502, code="mail.ai_failed") from exc
    summary = completion.text.strip()
    return MailSummaryResponse(message_id=row.id, summary=summary)


def create_reply_draft(
    db: Session,
    *,
    user: User,
    message_id: str,
    instruction: str = "",
) -> MailDraftOut:
    row = _load_message(db, user=user, message_id=message_id)
    account = _load_account(db, user=user, account_id=row.account_id)
    body_text = message_text(row)
    try:
        completion = execute_llm(
            "mail_reply_draft",
            LlmWorkloadContext.from_task_context(
                LlmTaskContext(
                    source="api.mail.reply_draft",
                    actor_user_id=user.id,
                    workspace_id=PERSONAL_MAIL_LLM_SCOPE,
                    task_kind="mail_reply_draft",
                    app_id="mail",
                )
            ),
            db,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "Draft a professional Korean business email reply. "
                        "Return only the reply body. Do not invent facts."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        f"Original email:\n{mail_prompt_context(row, body_text)}\n\n"
                        f"User instruction:\n{instruction.strip() or 'Reply appropriately.'}"
                    ),
                },
            ],
            temperature=0.2,
            max_tokens=2500,
            reasoning_effort="none",
            audit_entity_id=row.id,
        ).completion
    except LlmRuntimeError as exc:
        raise localized_http_exception(status_code=502, code="mail.ai_failed") from exc
    draft = MailDraft(
        id=new_id(),
        account_id=account.id,
        source_message_id=row.id,
        to_text=row.from_text,
        cc_text="",
        bcc_text="",
        subject=reply_subject(row.subject),
        text_body=completion.text.strip(),
        html_body="",
        ai_generated=True,
        status="draft",
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return MailDraftOut.model_validate(draft)


def list_drafts(db: Session, *, user: User) -> list[MailDraftOut]:
    rows = db.scalars(
        select(MailDraft)
        .join(MailAccount, MailDraft.account_id == MailAccount.id)
        .where(
            MailAccount.user_id == user.id,
            MailAccount.deleted_at.is_(None),
        )
        .order_by(MailDraft.updated_at.desc(), MailDraft.created_at.desc())
        .limit(50)
    ).all()
    return [MailDraftOut.model_validate(row) for row in rows]


def update_draft(
    db: Session,
    *,
    user: User,
    draft_id: str,
    payload: MailDraftUpdateRequest,
) -> MailDraftOut:
    row = _load_draft(db, user=user, draft_id=draft_id)
    if row.status != "draft":
        raise localized_http_exception(status_code=409, code="mail.draft_not_sendable")
    for field in payload.model_fields_set:
        value = getattr(payload, field)
        if value is not None:
            setattr(row, field, value)
    row.updated_at = utcnow_naive()
    db.add(row)
    db.commit()
    db.refresh(row)
    return MailDraftOut.model_validate(row)


def send_draft(
    db: Session,
    *,
    user: User,
    draft_id: str,
    client: MailProtocolClient | None = None,
) -> MailDraftOut:
    row = _load_draft(db, user=user, draft_id=draft_id)
    if row.status != "draft":
        raise localized_http_exception(status_code=409, code="mail.draft_not_sendable")
    account = _load_account(db, user=user, account_id=row.account_id)
    mail_client = client or _mail_client()
    attempt = MailSendAttempt(
        id=new_id(),
        draft_id=row.id,
        account_id=account.id,
        status="running",
    )
    db.add(attempt)
    db.commit()
    try:
        settings = settings_from_account(account)
        enforce_connection_profile(settings, incoming=False, smtp=True)
        provider_message_id = mail_client.send_draft(
            settings,
            to_text=row.to_text,
            cc_text=row.cc_text,
            bcc_text=row.bcc_text,
            subject=row.subject,
            text_body=row.text_body,
            html_body=row.html_body,
        )
        row.status = "sent"
        row.sent_at = utcnow_naive()
        row.sent_message_id = provider_message_id
        row.send_error = None
        attempt.status = "succeeded"
        attempt.provider_message_id = provider_message_id
        record_audit_log(
            db,
            actor_user_id=user.id,
            action="mail.draft.send",
            entity_kind="mail_draft",
            entity_id=row.id,
            summary=f"Sent mail draft {row.subject}",
            payload={"scope": "personal", "account_id": account.id},
        )
    except Exception as exc:
        row.status = "failed"
        row.send_error = _public_error(exc)
        attempt.status = "failed"
        attempt.error = row.send_error
        db.add_all([row, attempt])
        db.commit()
        raise localized_http_exception(
            status_code=502,
            code="mail.smtp_failed",
            error=row.send_error,
        ) from exc
    db.add_all([row, attempt])
    db.commit()
    db.refresh(row)
    return MailDraftOut.model_validate(row)


def process_mail_sync_job(
    db: Session,
    job_id: str,
    *,
    client: MailProtocolClient | None = None,
    lease_owner: str | None = None,
) -> str:
    job = db.scalar(select(MailSyncJob).where(MailSyncJob.id == job_id).with_for_update())
    if job is None:
        return "missing"
    if job.status not in {"pending", "processing"}:
        return job.status
    now = utcnow_naive()
    if not mail_background_sync_enabled(db):
        job.status = "cancelled"
        job.last_error = "mail app is disabled"
        job.lease_owner = None
        job.lease_expires_at = None
        job.next_retry_at = None
        job.updated_at = now
        db.add(job)
        db.commit()
        return "cancelled"
    if job.status == "pending" and job.next_retry_at and job.next_retry_at > now:
        raise MailSyncRetryScheduled(seconds_until(job.next_retry_at, now=now))
    if job.status == "processing" and job.lease_expires_at and job.lease_expires_at > now:
        raise MailSyncRetryScheduled(seconds_until(job.lease_expires_at, now=now))
    account = db.scalar(
        select(MailAccount).where(
            MailAccount.id == job.account_id,
            MailAccount.deleted_at.is_(None),
        )
    )
    mailbox = db.scalar(
        select(MailMailbox).where(
            MailMailbox.id == job.mailbox_id,
            MailMailbox.account_id == job.account_id,
        )
    )
    if account is None or mailbox is None:
        job.status = "cancelled"
        job.last_error = "mail sync target no longer exists"
        job.lease_owner = None
        job.lease_expires_at = None
        job.next_retry_at = None
        job.updated_at = now
        db.add(job)
        db.commit()
        return "cancelled"
    job.status = "processing"
    job.attempts += 1
    job.last_error = None
    job.next_retry_at = None
    job.lease_owner = lease_owner
    job.lease_expires_at = now + timedelta(
        seconds=get_settings().mail_sync_processing_lease_seconds
    )
    job.updated_at = now
    db.add(job)
    db.commit()
    try:
        result = sync_account(
            db,
            account_id=job.account_id,
            client=client,
            operation=job.operation,
        )
    except Exception as exc:
        db.rollback()
        job = db.get(MailSyncJob, job_id)
        if job is not None:
            retry_countdown = mark_sync_job_failed(
                db,
                job=job,
                error_text=_public_error(exc),
            )
            if retry_countdown is not None:
                raise MailSyncRetryScheduled(retry_countdown) from exc
        raise
    job = db.get(MailSyncJob, job_id)
    if job is not None:
        job.status = "succeeded"
        job.last_error = None
        job.next_retry_at = None
        job.lease_owner = None
        job.lease_expires_at = None
        job.updated_at = utcnow_naive()
        db.add(job)
        db.commit()
    return f"synced:{result.changed_count}"


def publish_due_mail_sync_jobs(db: Session, *, limit: int = 50) -> int:
    if not mail_background_sync_enabled(db):
        return 0
    return _publish_due_mail_sync_jobs(
        db,
        limit=limit,
        publisher=_publish_sync_job,
    )


@event.listens_for(Session, "after_commit")
def _publish_pending_mail_sync_jobs(session: Session) -> None:
    if session.in_nested_transaction():
        return
    pending = pop_pending_mail_sync_job_publications(session)
    if not pending:
        return
    for job_id in sorted(pending):
        try:
            _publish_sync_job(job_id=job_id)
        except Exception:
            logger.warning("Failed to publish mail sync job after commit", exc_info=True)


@event.listens_for(Session, "after_rollback")
def _clear_pending_mail_sync_job_publications(session: Session) -> None:
    if session.in_nested_transaction():
        return
    clear_pending_mail_sync_job_publications(session)


def _publish_sync_job(*, job_id: str) -> None:
    publish_sync_job(job_id=job_id)


def _purge_account_data(db: Session, *, account: MailAccount) -> None:
    _purge_account_mailbox_data(db, account=account)
    db.query(MailSendAttempt).filter(MailSendAttempt.account_id == account.id).delete(
        synchronize_session=False
    )
    db.query(MailDraft).filter(MailDraft.account_id == account.id).delete(synchronize_session=False)
    db.delete(account)


def _purge_account_mailbox_data(db: Session, *, account: MailAccount) -> None:
    message_ids = select(MailMessage.id).where(MailMessage.account_id == account.id)
    db.query(MailAttachment).filter(MailAttachment.message_id.in_(message_ids)).delete(
        synchronize_session=False
    )
    db.query(MailMessageBody).filter(MailMessageBody.message_id.in_(message_ids)).delete(
        synchronize_session=False
    )
    db.query(MailMessage).filter(MailMessage.account_id == account.id).delete(
        synchronize_session=False
    )
    db.query(MailSyncJob).filter(MailSyncJob.account_id == account.id).delete(
        synchronize_session=False
    )
    db.query(MailSyncState).filter(MailSyncState.account_id == account.id).delete(
        synchronize_session=False
    )
    db.query(MailMailbox).filter(MailMailbox.account_id == account.id).delete(
        synchronize_session=False
    )


def _load_account(
    db: Session,
    *,
    user: User,
    account_id: str,
    for_update: bool = False,
) -> MailAccount:
    stmt = select(MailAccount).where(
        MailAccount.id == account_id,
        MailAccount.user_id == user.id,
        MailAccount.deleted_at.is_(None),
    )
    if for_update:
        stmt = stmt.with_for_update()
    row = db.scalar(stmt)
    if row is None:
        raise localized_http_exception(status_code=404, code="mail.account_not_found")
    return row


def _load_message(
    db: Session,
    *,
    user: User,
    message_id: str,
) -> MailMessage:
    row = db.scalar(
        select(MailMessage)
        .join(MailAccount, MailMessage.account_id == MailAccount.id)
        .options(selectinload(MailMessage.body), selectinload(MailMessage.attachments))
        .where(
            MailMessage.id == message_id,
            MailAccount.user_id == user.id,
            MailMessage.remote_deleted_at.is_(None),
            MailAccount.deleted_at.is_(None),
        )
    )
    if row is None:
        raise localized_http_exception(status_code=404, code="mail.message_not_found")
    return row


def _load_draft(
    db: Session,
    *,
    user: User,
    draft_id: str,
) -> MailDraft:
    row = db.scalar(
        select(MailDraft)
        .join(MailAccount, MailDraft.account_id == MailAccount.id)
        .where(
            MailDraft.id == draft_id,
            MailAccount.user_id == user.id,
            MailAccount.deleted_at.is_(None),
        )
    )
    if row is None:
        raise localized_http_exception(status_code=404, code="mail.draft_not_found")
    return row


def _public_error(exc: Exception) -> str:
    if isinstance(exc, MailConnectionPolicyError):
        return str(exc)
    if isinstance(exc, MailCredentialError):
        return "Mail credential encryption key is not configured."
    if isinstance(exc, MailSyncRetryScheduled):
        return "Mail sync retry scheduled."
    return "Mail provider request failed."


def tool_list_messages(
    db: Session,
    workspace: Workspace,
    principal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    del workspace, principal
    result = list_messages(
        db,
        user=user,
        query=str(arguments.get("query") or "") or None,
        unread=arguments.get("unread"),
        starred=arguments.get("starred"),
        limit=int(arguments.get("limit") or 10),
    )
    return result.model_dump(mode="json")


def tool_get_message(
    db: Session,
    workspace: Workspace,
    principal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    del workspace, principal
    result = get_message(
        db,
        user=user,
        message_id=str(arguments["message_id"]),
    )
    return result.model_dump(mode="json")
