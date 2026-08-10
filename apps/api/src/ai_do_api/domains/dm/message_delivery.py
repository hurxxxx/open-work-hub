from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import User, utcnow_naive
from ai_do_api.domains.dm import conversation_queries, message_flow
from ai_do_api.domains.dm.models import DmMessage


@dataclass(frozen=True)
class DmMessageSendResult:
    message: DmMessage
    recipients: list[User]


@dataclass(frozen=True)
class _MessageDeliveryDraft:
    draft: message_flow.DmMessageDraft


def send_message(
    db: Session,
    *,
    sender: User,
    conversation_id: str,
    body: str,
    attachment_ids: list[str],
    reply_to_message_id: str | None = None,
) -> DmMessageSendResult:
    conversation = conversation_queries.require_user_conversation(
        db,
        current_user=sender,
        conversation_id=conversation_id,
    )
    compose_kwargs = {
        "conversation": conversation,
        "sender": sender,
        "body": body,
        "attachment_ids": attachment_ids,
        "now": utcnow_naive(),
    }
    if reply_to_message_id is not None:
        compose_kwargs["reply_to_message_id"] = reply_to_message_id
    draft = message_flow.compose_dm_message(db, **compose_kwargs)
    return _persist_delivery(
        db,
        delivery=_MessageDeliveryDraft(draft=draft),
        commit=True,
    )


def _persist_delivery(
    db: Session,
    *,
    delivery: _MessageDeliveryDraft,
    commit: bool,
) -> DmMessageSendResult:
    draft = delivery.draft
    for row in (draft.message, draft.conversation, draft.sender_participant):
        db.add(row)
    db.add_all(draft.attachments)
    if commit:
        db.commit()
        db.refresh(draft.message)
    else:
        db.flush()
    draft.message.attachments = draft.attachments
    return DmMessageSendResult(
        message=draft.message,
        recipients=draft.recipients,
    )


def persist_message_draft(
    db: Session,
    *,
    draft: message_flow.DmMessageDraft,
    commit: bool = False,
) -> DmMessageSendResult:
    return _persist_delivery(
        db,
        delivery=_MessageDeliveryDraft(draft=draft),
        commit=commit,
    )
