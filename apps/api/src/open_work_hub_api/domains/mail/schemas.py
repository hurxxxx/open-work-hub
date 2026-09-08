from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

MailProtocol = Literal["imap", "pop3"]
MailSecurity = Literal["ssl", "starttls", "none"]


class MailAccountBase(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_address: str = Field(..., min_length=3, max_length=320)
    display_name: str = Field(default="", max_length=160)
    account_label: str = Field(default="", max_length=160)
    protocol: MailProtocol = "imap"
    incoming_host: str = Field(..., min_length=1, max_length=255)
    incoming_port: int = Field(..., ge=1, le=65535)
    incoming_security: MailSecurity = "ssl"
    incoming_username: str = Field(..., min_length=1, max_length=320)
    smtp_host: str = Field(..., min_length=1, max_length=255)
    smtp_port: int = Field(..., ge=1, le=65535)
    smtp_security: MailSecurity = "starttls"
    smtp_username: str = Field(..., min_length=1, max_length=320)


class MailAccountConnectionRequest(MailAccountBase):
    incoming_password: str = Field(..., min_length=1, max_length=1024)
    smtp_password: str = Field(..., min_length=1, max_length=1024)


class MailAccountUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    email_address: str | None = Field(default=None, min_length=3, max_length=320)
    display_name: str | None = Field(default=None, max_length=160)
    account_label: str | None = Field(default=None, max_length=160)
    protocol: MailProtocol | None = None
    incoming_host: str | None = Field(default=None, min_length=1, max_length=255)
    incoming_port: int | None = Field(default=None, ge=1, le=65535)
    incoming_security: MailSecurity | None = None
    incoming_username: str | None = Field(default=None, min_length=1, max_length=320)
    incoming_password: str | None = Field(default=None, max_length=1024)
    smtp_host: str | None = Field(default=None, min_length=1, max_length=255)
    smtp_port: int | None = Field(default=None, ge=1, le=65535)
    smtp_security: MailSecurity | None = None
    smtp_username: str | None = Field(default=None, min_length=1, max_length=320)
    smtp_password: str | None = Field(default=None, max_length=1024)


class MailConnectionTestResponse(BaseModel):
    incoming_ok: bool
    smtp_ok: bool
    incoming_error: str | None = None
    smtp_error: str | None = None


class MailAccountOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email_address: str
    display_name: str
    account_label: str
    protocol: str
    provider_kind: str
    incoming_host: str
    incoming_port: int
    incoming_security: str
    incoming_username: str
    smtp_host: str
    smtp_port: int
    smtp_security: str
    smtp_username: str
    sync_enabled: bool
    status: str
    last_sync_at: datetime | None
    last_error: str | None
    last_sync_new_count: int = 0
    last_sync_updated_count: int = 0
    last_sync_deleted_count: int = 0
    created_at: datetime
    updated_at: datetime


class MailSyncResponse(BaseModel):
    account: MailAccountOut
    queued: bool
    job_id: str
    task_id: str | None = None


class MailMessageSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    folder: str
    subject: str
    from_text: str
    to_text: str
    cc_text: str
    snippet: str
    received_at: datetime | None
    is_read: bool
    is_starred: bool
    has_attachments: bool


class MailAttachmentOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    filename: str
    content_type: str
    size_bytes: int
    disposition: str
    downloaded_at: datetime | None


class MailMessageBodyOut(BaseModel):
    text_body: str
    html_body: str


class MailMessageDetail(MailMessageSummary):
    body: MailMessageBodyOut
    attachments: list[MailAttachmentOut] = Field(default_factory=list)


class MailMessageListResponse(BaseModel):
    items: list[MailMessageSummary]
    total: int


class MailMessageFlagsRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    is_read: bool | None = None
    is_starred: bool | None = None


class MailSummaryResponse(BaseModel):
    message_id: str
    summary: str


class MailReplyDraftRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    instruction: str = Field(default="", max_length=2000)


class MailDraftUpdateRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    to_text: str | None = Field(default=None, max_length=4000)
    cc_text: str | None = Field(default=None, max_length=4000)
    bcc_text: str | None = Field(default=None, max_length=4000)
    subject: str | None = Field(default=None, max_length=512)
    text_body: str | None = Field(default=None, max_length=120000)
    html_body: str | None = Field(default=None, max_length=120000)


class MailDraftOut(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    account_id: str
    source_message_id: str | None
    to_text: str
    cc_text: str
    bcc_text: str
    subject: str
    text_body: str
    html_body: str
    ai_generated: bool
    status: str
    send_error: str | None
    sent_message_id: str | None
    sent_at: datetime | None
    created_at: datetime
    updated_at: datetime
