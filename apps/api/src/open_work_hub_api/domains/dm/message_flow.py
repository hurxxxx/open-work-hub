from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.dm import conversation_lifecycle
from open_work_hub_api.domains.dm import participants as participant_rules
from open_work_hub_api.domains.dm.models import (
    DmConversation,
    DmConversationParticipant,
    DmMessage,
    DmMessageAttachment,
)

__all__ = ["DmMessageDraft", "compose_dm_message", "message_attachments_to_link"]


@dataclass(frozen=True)
class DmMessageDraft:
    conversation: DmConversation
    sender_participant: DmConversationParticipant
    message: DmMessage
    attachments: list[DmMessageAttachment]
    recipients: list[User]
    body: str


def compose_dm_message(
    db: Session,
    *,
    conversation: DmConversation,
    sender: User,
    body: str,
    attachment_ids: list[str],
    now: datetime,
    reply_to_message_id: str | None = None,
) -> DmMessageDraft:
    request = _DmMessageComposeRequest(
        db=db,
        conversation=conversation,
        sender=sender,
        body=body,
        attachment_ids=attachment_ids,
        reply_to_message_id=reply_to_message_id,
        now=now,
    )
    plan = _DmMessageComposePlanner().plan(request)
    return _DmMessageDraftBuilder(plan).build()


def message_attachments_to_link(
    db: Session,
    *,
    sender: User,
    conversation: DmConversation,
    attachment_ids: list[str],
) -> list[DmMessageAttachment]:
    return _DmAttachmentLinkBuilder(
        db=db,
        sender=sender,
        conversation=conversation,
        attachment_ids=attachment_ids,
    ).build()


@dataclass(frozen=True)
class _DmMessageComposeRequest:
    db: Session
    conversation: DmConversation
    sender: User
    body: str
    attachment_ids: list[str]
    reply_to_message_id: str | None
    now: datetime


@dataclass(frozen=True)
class _DmMessageComposePlan:
    conversation: DmConversation
    sender: User
    sender_participant: DmConversationParticipant
    recipients: list[User]
    body: str
    attachments: list[DmMessageAttachment]
    reply_to_message: DmMessage | None
    now: datetime


class _DmMessageComposePlanner:
    def plan(self, request: _DmMessageComposeRequest) -> _DmMessageComposePlan:
        trimmed = request.body.strip()
        sender_participant = self._sender_participant(request)
        attachments = message_attachments_to_link(
            request.db,
            sender=request.sender,
            conversation=request.conversation,
            attachment_ids=request.attachment_ids,
        )
        if not trimmed and not attachments:
            raise localized_http_exception(status_code=422, code="dm.message_body_required")

        reply_to_message = self._reply_to_message(request, sender_participant=sender_participant)
        recipients = self._recipients(request)
        if not recipients:
            raise localized_http_exception(status_code=404, code="dm.thread_not_found")

        return _DmMessageComposePlan(
            conversation=request.conversation,
            sender=request.sender,
            sender_participant=sender_participant,
            recipients=recipients,
            body=trimmed,
            attachments=attachments,
            reply_to_message=reply_to_message,
            now=request.now,
        )

    def _sender_participant(
        self,
        request: _DmMessageComposeRequest,
    ) -> DmConversationParticipant:
        sender_participant = participant_rules.active_participant(
            request.conversation,
            request.sender.id,
        )
        if sender_participant is None:
            raise localized_http_exception(status_code=404, code="dm.thread_not_found")
        return sender_participant

    def _recipients(self, request: _DmMessageComposeRequest) -> list[User]:
        return [
            participant.user
            for participant in participant_rules.active_participants(request.conversation)
            if participant.user_id != request.sender.id and participant.user is not None
        ]

    def _reply_to_message(
        self,
        request: _DmMessageComposeRequest,
        *,
        sender_participant: DmConversationParticipant,
    ) -> DmMessage | None:
        if request.reply_to_message_id is None:
            return None
        message = request.db.scalar(
            select(DmMessage)
            .where(
                DmMessage.id == request.reply_to_message_id,
                DmMessage.conversation_id == request.conversation.id,
            )
            .options(selectinload(DmMessage.sender))
            .options(selectinload(DmMessage.attachments))
            .limit(1)
        )
        if (
            message is None
            or message.conversation_id != request.conversation.id
            or message.created_at < sender_participant.joined_at
        ):
            raise localized_http_exception(status_code=404, code="dm.message_not_found")
        return message


@dataclass(frozen=True)
class _DmMessageDraftBuilder:
    plan: _DmMessageComposePlan

    def build(self) -> DmMessageDraft:
        sequence = self._next_message_sequence()
        message = self._new_message(sequence)
        message.reply_to = self.plan.reply_to_message
        self.plan.sender_participant.last_read_message_id = message.id
        for attachment in self.plan.attachments:
            attachment.message_id = message.id

        return DmMessageDraft(
            conversation=self.plan.conversation,
            sender_participant=self.plan.sender_participant,
            message=message,
            attachments=self.plan.attachments,
            recipients=self.plan.recipients,
            body=self.plan.body,
        )

    def _next_message_sequence(self) -> int:
        self.plan.conversation.message_seq += 1
        self.plan.conversation.updated_at = self.plan.now
        return self.plan.conversation.message_seq

    def _new_message(self, sequence: int) -> DmMessage:
        return DmMessage(
            id=new_id(),
            conversation_id=self.plan.conversation.id,
            sequence=sequence,
            sender_id=self.plan.sender.id,
            reply_to_message_id=(
                self.plan.reply_to_message.id if self.plan.reply_to_message is not None else None
            ),
            body=self.plan.body,
            created_at=self.plan.now,
        )


@dataclass(frozen=True)
class _DmAttachmentLinkRequest:
    db: Session
    sender: User
    conversation: DmConversation
    attachment_ids: list[str]


@dataclass(frozen=True)
class _DmAttachmentLinkValidator:
    request: _DmAttachmentLinkRequest

    def validate(self, attachment: DmMessageAttachment) -> None:
        if (
            attachment.conversation_id != self.request.conversation.id
            or attachment.uploader_id != self.request.sender.id
        ):
            raise localized_http_exception(status_code=404, code="dm.attachment_not_found")
        if attachment.message_id is not None:
            raise localized_http_exception(status_code=422, code="dm.attachment_already_sent")


@dataclass(frozen=True)
class _DmAttachmentLinkBuilder:
    db: Session
    sender: User
    conversation: DmConversation
    attachment_ids: list[str]

    def build(self) -> list[DmMessageAttachment]:
        request = _DmAttachmentLinkRequest(
            db=self.db,
            sender=self.sender,
            conversation=self.conversation,
            attachment_ids=self.attachment_ids,
        )
        ids = conversation_lifecycle.unique_user_ids(request.attachment_ids)
        if not ids:
            return []

        by_id = self._attachments_by_id(request, ids)
        if set(by_id) != set(ids):
            raise localized_http_exception(status_code=404, code="dm.attachment_not_found")

        ordered = [by_id[attachment_id] for attachment_id in ids]
        validator = _DmAttachmentLinkValidator(request)
        for attachment in ordered:
            validator.validate(attachment)
        return ordered

    def _attachments_by_id(
        self,
        request: _DmAttachmentLinkRequest,
        attachment_ids: list[str],
    ) -> dict[str, DmMessageAttachment]:
        attachments = request.db.scalars(
            select(DmMessageAttachment).where(DmMessageAttachment.id.in_(attachment_ids))
        )
        return {attachment.id: attachment for attachment in attachments}
