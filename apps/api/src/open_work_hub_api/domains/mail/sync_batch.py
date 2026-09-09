from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.mail.clients import FetchedMessage, MailboxSyncBatch
from open_work_hub_api.domains.mail.models import (
    MailAccount,
    MailAttachment,
    MailMailbox,
    MailMessage,
    MailMessageBody,
)


@dataclass(frozen=True)
class MailSyncResult:
    new_count: int
    updated_count: int
    deleted_count: int

    @property
    def changed_count(self) -> int:
        return self.new_count + self.updated_count + self.deleted_count


def cursor_for_mailbox_sync(
    db: Session,
    *,
    account: MailAccount,
    mailbox: MailMailbox,
    cursor: dict[str, Any],
) -> dict[str, Any]:
    provider_kind = (account.provider_kind or account.protocol).lower()
    if provider_kind != "pop3" or not cursor.get("uidls"):
        return cursor
    synced_uidls = set(
        db.scalars(
            select(MailMessage.provider_uid).where(
                MailMessage.account_id == account.id,
                MailMessage.mailbox_id == mailbox.id,
                MailMessage.remote_deleted_at.is_(None),
            )
        )
    )
    cursor_uidls = {str(uid) for uid in cursor.get("uidls") or [] if uid}
    if cursor_uidls - synced_uidls:
        cursor["uidls"] = sorted(synced_uidls)
    return cursor


def apply_sync_batch(
    db: Session,
    *,
    account: MailAccount,
    mailbox: MailMailbox,
    batch: MailboxSyncBatch,
) -> MailSyncResult:
    new_count = 0
    updated_count = 0
    deleted_count = 0
    seen_at = utcnow_naive()
    if batch.reset_mailbox:
        deleted_count += mark_messages_remote_deleted(
            db,
            db.scalars(
                select(MailMessage).where(
                    MailMessage.account_id == account.id,
                    MailMessage.mailbox_id == mailbox.id,
                    MailMessage.remote_deleted_at.is_(None),
                )
            ).all(),
            seen_at=seen_at,
        )
    for item in batch.messages:
        remote_identity = item.remote_identity or default_remote_identity(account, item)
        row = db.scalar(
            select(MailMessage).where(
                MailMessage.account_id == account.id,
                MailMessage.remote_identity == remote_identity,
            )
        )
        if row is None:
            row = find_legacy_message_for_sync(
                db,
                account=account,
                mailbox=mailbox,
                item=item,
            )
        if row is None:
            new_count += 1
            row = MailMessage(
                id=new_id(),
                account_id=account.id,
                mailbox_id=mailbox.id,
                folder=mailbox.provider_mailbox_id,
                provider_uid=item.provider_uid,
                remote_identity=remote_identity,
            )
        else:
            updated_count += 1
            row.mailbox_id = mailbox.id
            row.folder = mailbox.provider_mailbox_id
            row.provider_uid = item.provider_uid
            row.remote_identity = remote_identity
        row.provider_message_id = (
            item.provider_message_id[:512] if item.provider_message_id else None
        )
        row.thread_key = item.thread_key[:512] if item.thread_key else None
        row.subject = item.subject[:512]
        row.from_text = item.from_text
        row.to_text = item.to_text
        row.cc_text = item.cc_text
        row.snippet = item.snippet
        row.received_at = item.received_at
        row.sent_at = item.sent_at
        row.remote_flags_json = dict(item.remote_flags or {})
        local_state = dict(row.local_state_json or {})
        if "is_read" in local_state:
            row.is_read = bool(local_state["is_read"])
        else:
            row.is_read = item.is_read
        if "is_starred" in local_state:
            row.is_starred = bool(local_state["is_starred"])
        elif row.is_starred is None:
            row.is_starred = False
        row.has_attachments = bool(item.attachments)
        row.body_status = "ready"
        row.sync_seen_at = seen_at
        row.remote_deleted_at = None
        row.updated_at = seen_at
        db.add(row)
        db.flush()
        body = row.body or MailMessageBody(message_id=row.id)
        body.text_body = item.text_body
        body.html_body = item.html_body
        body.content_hash = content_hash(item.text_body, item.html_body)
        body.updated_at = seen_at
        db.add(body)
        db.query(MailAttachment).filter(MailAttachment.message_id == row.id).delete()
        for attachment in item.attachments:
            db.add(
                MailAttachment(
                    id=new_id(),
                    message_id=row.id,
                    filename=attachment.filename[:512],
                    content_type=attachment.content_type,
                    size_bytes=attachment.size_bytes,
                    content_id=attachment.content_id,
                    disposition=attachment.disposition,
                    provider_part_id=attachment.provider_part_id,
                )
            )
    for remote_identity in batch.deleted_remote_identities:
        row = db.scalar(
            select(MailMessage).where(
                MailMessage.account_id == account.id,
                MailMessage.remote_identity == remote_identity,
                MailMessage.remote_deleted_at.is_(None),
            )
        )
        if row is None:
            continue
        deleted_count += mark_messages_remote_deleted(db, [row], seen_at=seen_at)
    return MailSyncResult(
        new_count=new_count,
        updated_count=updated_count,
        deleted_count=deleted_count,
    )


def find_legacy_message_for_sync(
    db: Session,
    *,
    account: MailAccount,
    mailbox: MailMailbox,
    item: FetchedMessage,
) -> MailMessage | None:
    if not item.provider_uid:
        return None
    return db.scalar(
        select(MailMessage)
        .where(
            MailMessage.account_id == account.id,
            MailMessage.mailbox_id == mailbox.id,
            MailMessage.folder == mailbox.provider_mailbox_id,
            MailMessage.provider_uid == item.provider_uid,
            MailMessage.remote_identity.like("legacy:%"),
            MailMessage.remote_deleted_at.is_(None),
        )
        .limit(1)
        .with_for_update()
    )


def mark_messages_remote_deleted(
    db: Session,
    rows: list[MailMessage],
    *,
    seen_at,
) -> int:
    deleted_count = 0
    for row in rows:
        row.remote_deleted_at = seen_at
        row.has_attachments = False
        row.body_status = "remote_deleted"
        row.updated_at = seen_at
        db.query(MailAttachment).filter(MailAttachment.message_id == row.id).delete(
            synchronize_session=False
        )
        db.query(MailMessageBody).filter(MailMessageBody.message_id == row.id).delete(
            synchronize_session=False
        )
        db.add(row)
        deleted_count += 1
    return deleted_count


def default_remote_identity(account: MailAccount, item: FetchedMessage) -> str:
    provider_kind = account.provider_kind or account.protocol
    return f"{provider_kind}:{item.provider_uid}"


def content_hash(*parts: str) -> str:
    digest = hashlib.sha256()
    for part in parts:
        digest.update(part.encode("utf-8"))
        digest.update(b"\0")
    return digest.hexdigest()
