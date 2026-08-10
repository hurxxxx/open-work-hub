from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from open_work_hub_api.domains.dm.request_normalization import (
    DM_CONVERSATION_TITLE_MAX_LENGTH,
    DM_MESSAGE_ATTACHMENT_IDS_MAX_LENGTH,
    DM_MESSAGE_BODY_MAX_LENGTH,
    DM_PARTICIPANT_IDS_MAX_LENGTH,
    DM_ROUTE_ID_MAX_LENGTH,
    normalize_dm_route_id_list,
    normalize_message_body,
    normalize_optional_dm_route_id,
    normalize_optional_title,
)


class DmUserItem(BaseModel):
    id: str
    email: str
    full_name: str
    display_name: str | None = None


class DmConversationParticipantItem(BaseModel):
    user: DmUserItem
    role: Literal["owner", "admin", "member"]
    joined_at: datetime
    left_at: datetime | None = None
    muted_at: datetime | None = None
    last_read_message_id: str | None = None


class DmMessageAttachmentItem(BaseModel):
    id: str
    conversation_id: str
    message_id: str | None = None
    filename: str
    content_type: str
    size_bytes: int
    is_image: bool
    download_url: str
    preview_url: str | None = None
    created_at: datetime


class DmAttachmentUrlResponse(BaseModel):
    url: str


class DmMessageReadStateItem(BaseModel):
    unread_count: int = Field(ge=0)
    read_by_all: bool


class DmMessageReplyToItem(BaseModel):
    id: str
    sender_id: str
    sender_name: str
    body_preview: str
    attachment_count: int = Field(ge=0)
    created_at: datetime


class DmMessageItem(BaseModel):
    id: str
    conversation_id: str
    thread_id: str
    sequence: int
    sender_id: str
    sender_name: str
    read_state: DmMessageReadStateItem
    reply_to: DmMessageReplyToItem | None = None
    body: str
    attachments: list[DmMessageAttachmentItem] = Field(default_factory=list)
    created_at: datetime


class DmConversationItem(BaseModel):
    id: str
    conversation_type: Literal["direct", "group"]
    thread_type: Literal["direct", "group"]
    title: str | None = None
    display_name: str
    other_user: DmUserItem | None = None
    participants: list[DmConversationParticipantItem]
    participant_count: int
    last_message: DmMessageItem | None = None
    unread_count: int
    last_read_message_id: str | None = None
    muted_at: datetime | None = None
    created_by_id: str
    created_at: datetime
    updated_at: datetime


class DmConversationListResponse(BaseModel):
    items: list[DmConversationItem]


class DmMessageListResponse(BaseModel):
    items: list[DmMessageItem]


class DmCreateConversationRequest(BaseModel):
    recipient_user_id: str | None = Field(
        default=None,
        min_length=1,
        max_length=DM_ROUTE_ID_MAX_LENGTH,
    )
    participant_user_ids: list[str] = Field(
        default_factory=list,
        max_length=DM_PARTICIPANT_IDS_MAX_LENGTH,
    )
    title: str | None = Field(default=None, max_length=DM_CONVERSATION_TITLE_MAX_LENGTH)

    @field_validator("recipient_user_id", mode="before")
    @classmethod
    def normalize_recipient_user_id(cls, value: object) -> str | None | object:
        return normalize_optional_dm_route_id(value)

    @field_validator("participant_user_ids", mode="before")
    @classmethod
    def normalize_participant_user_ids(cls, value: object) -> list[str] | object:
        return normalize_dm_route_id_list(value, allow_empty=True)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> str | None | object:
        return normalize_optional_title(value)

    @model_validator(mode="after")
    def validate_recipient_shape(self) -> DmCreateConversationRequest:
        if self.recipient_user_id and self.participant_user_ids:
            raise ValueError("recipient_user_id and participant_user_ids are mutually exclusive")
        if not self.recipient_user_id and not self.participant_user_ids:
            raise ValueError("recipient_user_id or participant_user_ids is required")
        return self


class DmUpdateConversationRequest(BaseModel):
    title: str | None = Field(default=None, max_length=DM_CONVERSATION_TITLE_MAX_LENGTH)

    @field_validator("title", mode="before")
    @classmethod
    def normalize_title(cls, value: object) -> str | None | object:
        return normalize_optional_title(value)


class DmAddParticipantsRequest(BaseModel):
    user_ids: list[str] = Field(min_length=1, max_length=DM_PARTICIPANT_IDS_MAX_LENGTH)

    @field_validator("user_ids", mode="before")
    @classmethod
    def normalize_user_ids(cls, value: object) -> list[str] | object:
        return normalize_dm_route_id_list(value, allow_empty=False)


class DmSendMessageRequest(BaseModel):
    body: str = Field(default="", max_length=DM_MESSAGE_BODY_MAX_LENGTH)
    attachment_ids: list[str] = Field(
        default_factory=list,
        max_length=DM_MESSAGE_ATTACHMENT_IDS_MAX_LENGTH,
    )
    reply_to_message_id: str | None = Field(default=None, max_length=DM_ROUTE_ID_MAX_LENGTH)

    @field_validator("body", mode="before")
    @classmethod
    def normalize_body(cls, value: object) -> str | object:
        return normalize_message_body(value)

    @field_validator("attachment_ids", mode="before")
    @classmethod
    def normalize_attachment_ids(cls, value: object) -> list[str] | object:
        return normalize_dm_route_id_list(value, allow_empty=True)

    @field_validator("reply_to_message_id", mode="before")
    @classmethod
    def normalize_reply_to_message_id(cls, value: object) -> str | None | object:
        return normalize_optional_dm_route_id(value)

    @model_validator(mode="after")
    def validate_message_content(self) -> DmSendMessageRequest:
        if not self.body and not self.attachment_ids:
            raise ValueError("body or attachment_ids is required")
        return self


# Backward-compatible names for old imports while the UI migrates to conversation language.
DmThreadItem = DmConversationItem
DmThreadListResponse = DmConversationListResponse
DmCreateThreadRequest = DmCreateConversationRequest
