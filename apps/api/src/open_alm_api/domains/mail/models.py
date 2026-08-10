from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    DateTime,
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import utcnow_naive


JSONB_COMPAT = JSONB(astext_type=Text()).with_variant(JSON(), "sqlite")


class MailAccount(Base):
    __tablename__ = "mail_accounts"
    __table_args__ = (
        UniqueConstraint(
            "workspace_id",
            "user_id",
            "email_address",
            name="uq_mail_accounts_workspace_user_email",
        ),
        Index("ix_mail_accounts_workspace_user", "workspace_id", "user_id"),
        Index("ix_mail_accounts_user_created", "user_id", "created_at"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    # Preserve pre-global scope for audit and rollback without using it for
    # personal ownership. New rows intentionally leave this value empty.
    legacy_workspace_id: Mapped[str | None] = mapped_column(
        "workspace_id",
        ForeignKey("workspaces.id"),
        nullable=True,
        index=True,
    )
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), nullable=False, index=True)
    email_address: Mapped[str] = mapped_column(String(320), nullable=False, index=True)
    display_name: Mapped[str] = mapped_column(String(160), default="", nullable=False)
    account_label: Mapped[str] = mapped_column(
        String(160),
        default="",
        server_default=text("''"),
        nullable=False,
    )
    protocol: Mapped[str] = mapped_column(String(16), default="imap", nullable=False)
    provider_kind: Mapped[str] = mapped_column(
        String(32), default="imap", server_default=text("'imap'"), nullable=False
    )
    incoming_host: Mapped[str] = mapped_column(String(255), nullable=False)
    incoming_port: Mapped[int] = mapped_column(Integer, nullable=False)
    incoming_security: Mapped[str] = mapped_column(String(16), default="ssl", nullable=False)
    incoming_username: Mapped[str] = mapped_column(String(320), nullable=False)
    incoming_password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    smtp_host: Mapped[str] = mapped_column(String(255), nullable=False)
    smtp_port: Mapped[int] = mapped_column(Integer, nullable=False)
    smtp_security: Mapped[str] = mapped_column(String(16), default="starttls", nullable=False)
    smtp_username: Mapped[str] = mapped_column(String(320), nullable=False)
    smtp_password_encrypted: Mapped[str] = mapped_column(Text, nullable=False)
    sync_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default="not_tested", server_default=text("'not_tested'"), nullable=False
    )
    last_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_sync_new_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    last_sync_updated_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    last_sync_deleted_count: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    messages: Mapped[list["MailMessage"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )
    mailboxes: Mapped[list["MailMailbox"]] = relationship(
        back_populates="account",
        cascade="all, delete-orphan",
    )


class MailMailbox(Base):
    __tablename__ = "mail_mailboxes"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "provider_mailbox_id",
            name="uq_mail_mailboxes_account_provider_id",
        ),
        Index("ix_mail_mailboxes_account_role", "account_id", "role"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    legacy_workspace_id: Mapped[str | None] = mapped_column(
        "workspace_id",
        ForeignKey("workspaces.id"),
        nullable=True,
        index=True,
    )
    legacy_user_id: Mapped[str | None] = mapped_column(
        "user_id",
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    provider_mailbox_id: Mapped[str] = mapped_column(String(512), nullable=False)
    role: Mapped[str] = mapped_column(String(32), default="inbox", nullable=False)
    display_name: Mapped[str] = mapped_column(String(160), default="INBOX", nullable=False)
    sync_enabled: Mapped[bool] = mapped_column(
        Boolean, default=True, server_default=text("true"), nullable=False
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    account: Mapped[MailAccount] = relationship(back_populates="mailboxes")
    sync_state: Mapped["MailSyncState | None"] = relationship(
        back_populates="mailbox",
        cascade="all, delete-orphan",
        uselist=False,
    )


class MailMessage(Base):
    __tablename__ = "mail_messages"
    __table_args__ = (
        UniqueConstraint(
            "account_id",
            "remote_identity",
            name="uq_mail_messages_account_remote_identity",
        ),
        Index("ix_mail_messages_account_received", "account_id", "received_at"),
        Index(
            "ix_mail_messages_account_flags",
            "account_id",
            "is_read",
            "is_starred",
        ),
        Index(
            "ix_mail_messages_workspace_user_received",
            "workspace_id",
            "user_id",
            "received_at",
        ),
        Index(
            "ix_mail_messages_workspace_user_flags",
            "workspace_id",
            "user_id",
            "is_read",
            "is_starred",
        ),
        Index("ix_mail_messages_account_mailbox", "account_id", "mailbox_id"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    legacy_workspace_id: Mapped[str | None] = mapped_column(
        "workspace_id",
        ForeignKey("workspaces.id"),
        nullable=True,
        index=True,
    )
    legacy_user_id: Mapped[str | None] = mapped_column(
        "user_id",
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mailbox_id: Mapped[str | None] = mapped_column(
        ForeignKey("mail_mailboxes.id", ondelete="SET NULL"), nullable=True, index=True
    )
    folder: Mapped[str] = mapped_column(String(160), default="INBOX", nullable=False)
    provider_uid: Mapped[str] = mapped_column(String(256), nullable=False)
    remote_identity: Mapped[str] = mapped_column(String(768), nullable=False)
    provider_message_id: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    thread_key: Mapped[str | None] = mapped_column(String(512), nullable=True, index=True)
    subject: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    from_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    to_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cc_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    snippet: Mapped[str] = mapped_column(Text, default="", nullable=False)
    received_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    is_read: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    is_starred: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    has_attachments: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    body_status: Mapped[str] = mapped_column(String(24), default="ready", nullable=False)
    remote_flags_json: Mapped[dict] = mapped_column(JSONB_COMPAT, default=dict, nullable=False)
    local_state_json: Mapped[dict] = mapped_column(JSONB_COMPAT, default=dict, nullable=False)
    sync_seen_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    remote_deleted_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    account: Mapped[MailAccount] = relationship(back_populates="messages")
    mailbox: Mapped[MailMailbox | None] = relationship()
    body: Mapped["MailMessageBody | None"] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
        uselist=False,
    )
    attachments: Mapped[list["MailAttachment"]] = relationship(
        back_populates="message",
        cascade="all, delete-orphan",
    )


class MailMessageBody(Base):
    __tablename__ = "mail_message_bodies"

    message_id: Mapped[str] = mapped_column(
        ForeignKey("mail_messages.id", ondelete="CASCADE"), primary_key=True
    )
    text_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    html_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    content_hash: Mapped[str | None] = mapped_column(String(128), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    message: Mapped[MailMessage] = relationship(back_populates="body")


class MailAttachment(Base):
    __tablename__ = "mail_attachments"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    message_id: Mapped[str] = mapped_column(
        ForeignKey("mail_messages.id", ondelete="CASCADE"), nullable=False, index=True
    )
    filename: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    content_type: Mapped[str] = mapped_column(
        String(160), default="application/octet-stream", nullable=False
    )
    size_bytes: Mapped[int] = mapped_column(Integer, default=0, nullable=False)
    content_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    disposition: Mapped[str] = mapped_column(String(40), default="attachment", nullable=False)
    provider_part_id: Mapped[str | None] = mapped_column(String(256), nullable=True)
    storage_provider: Mapped[str | None] = mapped_column(String(40), nullable=True)
    storage_key: Mapped[str | None] = mapped_column(String(1024), nullable=True)
    downloaded_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)

    message: Mapped[MailMessage] = relationship(back_populates="attachments")


class MailDraft(Base):
    __tablename__ = "mail_drafts"
    __table_args__ = (
        Index(
            "ix_mail_drafts_workspace_user_status",
            "workspace_id",
            "user_id",
            "status",
        ),
        Index("ix_mail_drafts_account_status", "account_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    legacy_workspace_id: Mapped[str | None] = mapped_column(
        "workspace_id",
        ForeignKey("workspaces.id"),
        nullable=True,
        index=True,
    )
    legacy_user_id: Mapped[str | None] = mapped_column(
        "user_id",
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey("mail_accounts.id"), nullable=False, index=True
    )
    source_message_id: Mapped[str | None] = mapped_column(
        ForeignKey("mail_messages.id", ondelete="SET NULL"), nullable=True, index=True
    )
    to_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    cc_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    bcc_text: Mapped[str] = mapped_column(Text, default="", nullable=False)
    subject: Mapped[str] = mapped_column(String(512), default="", nullable=False)
    text_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    html_body: Mapped[str] = mapped_column(Text, default="", nullable=False)
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    status: Mapped[str] = mapped_column(String(24), default="draft", nullable=False)
    send_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    sent_message_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )


class MailSendAttempt(Base):
    __tablename__ = "mail_send_attempts"
    __table_args__ = (Index("ix_mail_send_attempts_draft_created", "draft_id", "created_at"),)

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    draft_id: Mapped[str] = mapped_column(ForeignKey("mail_drafts.id"), nullable=False, index=True)
    account_id: Mapped[str] = mapped_column(
        ForeignKey("mail_accounts.id"), nullable=False, index=True
    )
    legacy_user_id: Mapped[str | None] = mapped_column(
        "user_id",
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    status: Mapped[str] = mapped_column(String(24), nullable=False)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    provider_message_id: Mapped[str | None] = mapped_column(String(512), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)


class MailSyncState(Base):
    __tablename__ = "mail_sync_states"
    __table_args__ = (
        UniqueConstraint("mailbox_id", name="uq_mail_sync_states_mailbox"),
        Index("ix_mail_sync_states_account_status", "account_id", "status"),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    legacy_workspace_id: Mapped[str | None] = mapped_column(
        "workspace_id",
        ForeignKey("workspaces.id"),
        nullable=True,
        index=True,
    )
    legacy_user_id: Mapped[str | None] = mapped_column(
        "user_id",
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mailbox_id: Mapped[str] = mapped_column(
        ForeignKey("mail_mailboxes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    status: Mapped[str] = mapped_column(
        String(24), default="idle", server_default=text("'idle'"), nullable=False
    )
    cursor_json: Mapped[dict] = mapped_column(JSONB_COMPAT, default=dict, nullable=False)
    last_full_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_incremental_sync_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )

    mailbox: Mapped[MailMailbox] = relationship(back_populates="sync_state")


class MailSyncJob(Base):
    __tablename__ = "mail_sync_jobs"
    __table_args__ = (
        CheckConstraint(
            "operation IN ('initial','incremental','reconcile','fetch_body')",
            name="ck_mail_sync_jobs_operation",
        ),
        CheckConstraint(
            "status IN ('pending','processing','succeeded','failed','cancelled')",
            name="ck_mail_sync_jobs_status",
        ),
        Index(
            "ix_mail_sync_jobs_account_status_retry",
            "account_id",
            "status",
            "next_retry_at",
        ),
        Index(
            "uq_mail_sync_jobs_active_scope",
            "account_id",
            "mailbox_id",
            "operation",
            unique=True,
            postgresql_where=text("status IN ('pending', 'processing')"),
            sqlite_where=text("status IN ('pending', 'processing')"),
        ),
    )

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    legacy_workspace_id: Mapped[str | None] = mapped_column(
        "workspace_id",
        ForeignKey("workspaces.id"),
        nullable=True,
        index=True,
    )
    legacy_user_id: Mapped[str | None] = mapped_column(
        "user_id",
        ForeignKey("users.id"),
        nullable=True,
        index=True,
    )
    account_id: Mapped[str] = mapped_column(
        ForeignKey("mail_accounts.id", ondelete="CASCADE"), nullable=False, index=True
    )
    mailbox_id: Mapped[str] = mapped_column(
        ForeignKey("mail_mailboxes.id", ondelete="CASCADE"), nullable=False, index=True
    )
    operation: Mapped[str] = mapped_column(
        String(24), default="incremental", server_default=text("'incremental'"), nullable=False
    )
    status: Mapped[str] = mapped_column(
        String(24), default="pending", server_default=text("'pending'"), nullable=False
    )
    attempts: Mapped[int] = mapped_column(
        Integer, default=0, server_default=text("0"), nullable=False
    )
    last_error: Mapped[str | None] = mapped_column(Text, nullable=True)
    next_retry_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    last_published_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True, index=True)
    lease_owner: Mapped[str | None] = mapped_column(String(120), nullable=True)
    lease_expires_at: Mapped[datetime | None] = mapped_column(DateTime, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime, default=utcnow_naive, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime,
        default=utcnow_naive,
        onupdate=utcnow_naive,
        nullable=False,
    )
