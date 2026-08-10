from __future__ import annotations

from dataclasses import dataclass
from typing import BinaryIO

from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.dm import (
    attachment_links,
    attachment_persistence,
    attachment_policy,
    conversation_queries,
)
from ai_do_api.domains.dm.models import DmConversation, DmMessageAttachment


@dataclass(frozen=True)
class DmAttachmentCreationPlan:
    prepared_upload: attachment_policy.PreparedDmAttachment
    attachment_id: str
    storage_key: str
    row: DmMessageAttachment
    object_write: attachment_persistence.DmAttachmentObjectWrite

    def persist(self, db: Session) -> DmMessageAttachment:
        return attachment_persistence.persist_created_attachment(
            db,
            row=self.row,
            object_write=self.object_write,
        )


@dataclass(frozen=True)
class DmAttachmentAccessGate:
    db: Session
    current_user: User

    def require_conversation(self, conversation_id: str) -> DmConversation:
        return conversation_queries.require_user_conversation(
            self.db,
            current_user=self.current_user,
            conversation_id=conversation_id,
        )

    def require_attachment(self, attachment_id: str) -> DmMessageAttachment:
        attachment = self.db.get(DmMessageAttachment, attachment_id)
        if attachment is None:
            raise localized_http_exception(status_code=404, code="dm.attachment_not_found")
        self.require_conversation(attachment.conversation_id)
        return attachment


@dataclass(frozen=True)
class DmAttachmentRecordBuilder:
    db: Session
    current_user: User
    conversation_id: str
    filename: str | None
    content_type: str | None
    content: BinaryIO
    size_bytes: int
    sniff_bytes: bytes = b""

    def build(self) -> DmAttachmentCreationPlan:
        conversation = self.access_gate.require_conversation(self.conversation_id)
        self.validate_size()
        prepared_upload = self.prepare_upload()
        attachment_id = new_id()
        storage_key = self.build_storage_key(
            conversation_id=conversation.id,
            attachment_id=attachment_id,
            filename=prepared_upload.filename,
        )
        row = self.build_row(
            conversation_id=conversation.id,
            attachment_id=attachment_id,
            prepared_upload=prepared_upload,
            storage_key=storage_key,
        )
        return DmAttachmentCreationPlan(
            prepared_upload=prepared_upload,
            attachment_id=attachment_id,
            storage_key=storage_key,
            row=row,
            object_write=self.build_object_write(row),
        )

    @property
    def access_gate(self) -> DmAttachmentAccessGate:
        return DmAttachmentAccessGate(db=self.db, current_user=self.current_user)

    def validate_size(self) -> None:
        if self.size_bytes <= 0:
            raise localized_http_exception(status_code=422, code="dm.attachment_empty")
        if not attachment_policy.is_dm_attachment_size_allowed(self.size_bytes):
            raise localized_http_exception(
                status_code=413,
                code="dm.attachment_size_limit_exceeded",
                limit_mb=attachment_policy.dm_attachment_size_limit_mb(),
            )

    def prepare_upload(self) -> attachment_policy.PreparedDmAttachment:
        return attachment_policy.prepare_attachment_upload(
            filename=self.filename,
            content_type=self.content_type,
            sniff_bytes=self.sniff_bytes,
        )

    def build_row(
        self,
        *,
        conversation_id: str,
        attachment_id: str,
        prepared_upload: attachment_policy.PreparedDmAttachment,
        storage_key: str,
    ) -> DmMessageAttachment:
        return DmMessageAttachment(
            id=attachment_id,
            conversation_id=conversation_id,
            message_id=None,
            uploader_id=self.current_user.id,
            filename=prepared_upload.filename,
            content_type=prepared_upload.content_type,
            size_bytes=self.size_bytes,
            storage_key=storage_key,
        )

    def build_object_write(
        self,
        row: DmMessageAttachment,
    ) -> attachment_persistence.DmAttachmentObjectWrite:
        return attachment_persistence.DmAttachmentObjectWrite(
            storage_key=row.storage_key,
            content=self.content,
            size_bytes=self.size_bytes,
            content_type=row.content_type,
        )

    @staticmethod
    def build_storage_key(
        *,
        conversation_id: str,
        attachment_id: str,
        filename: str,
    ) -> str:
        return f"dm/{conversation_id}/{attachment_id}/{filename}"


def create_attachment(
    db: Session,
    *,
    current_user: User,
    conversation_id: str,
    filename: str | None,
    content_type: str | None,
    content: BinaryIO,
    size_bytes: int,
    sniff_bytes: bytes = b"",
) -> DmMessageAttachment:
    plan = DmAttachmentRecordBuilder(
        db=db,
        current_user=current_user,
        conversation_id=conversation_id,
        filename=filename,
        content_type=content_type,
        content=content,
        size_bytes=size_bytes,
        sniff_bytes=sniff_bytes,
    ).build()
    return plan.persist(db)


def attachment_download_url(
    db: Session,
    *,
    current_user: User,
    attachment_id: str,
) -> str:
    attachment = require_attachment_access(
        db,
        current_user=current_user,
        attachment_id=attachment_id,
    )
    return attachment_links.build_dm_attachment_download_url(attachment)


def attachment_preview_url(
    db: Session,
    *,
    current_user: User,
    attachment_id: str,
) -> str:
    attachment = require_attachment_access(
        db,
        current_user=current_user,
        attachment_id=attachment_id,
    )
    url = attachment_links.build_dm_attachment_preview_url(attachment)
    if url is None:
        raise localized_http_exception(status_code=415, code="dm.attachment_preview_unsupported")
    return url


def require_attachment_access(
    db: Session,
    *,
    current_user: User,
    attachment_id: str,
) -> DmMessageAttachment:
    return DmAttachmentAccessGate(db=db, current_user=current_user).require_attachment(attachment_id)
