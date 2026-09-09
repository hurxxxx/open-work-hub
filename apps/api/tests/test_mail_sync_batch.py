from __future__ import annotations

from datetime import datetime

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.mail.clients import (
    FetchedAttachment,
    FetchedMessage,
    MailboxSyncBatch,
)
from open_work_hub_api.domains.mail.models import (
    MailAccount,
    MailAttachment,
    MailMailbox,
    MailMessage,
    MailMessageBody,
)
from open_work_hub_api.domains.mail.sync_batch import apply_sync_batch, cursor_for_mailbox_sync


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            User.__table__,
            MailAccount.__table__,
            MailMailbox.__table__,
            MailMessage.__table__,
            MailMessageBody.__table__,
            MailAttachment.__table__,
        ],
    )
    return Session(engine)


def _user() -> User:
    return User(
        id="user-1",
        login_id="user-1",
        email="user-1@open-work-hub.local",
        full_name="User One",
        password_hash="hash",
        status="active",
    )


def _account(protocol: str = "imap") -> MailAccount:
    return MailAccount(
        id="account-1",
        user_id="user-1",
        email_address="user-1@example.test",
        display_name="User One",
        protocol=protocol,
        provider_kind=protocol,
        incoming_host="mail.example.test",
        incoming_port=993,
        incoming_security="ssl",
        incoming_username="user-1",
        incoming_password_encrypted="encrypted",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="user-1",
        smtp_password_encrypted="encrypted",
    )


def _mailbox() -> MailMailbox:
    return MailMailbox(
        id="mailbox-1",
        account_id="account-1",
        provider_mailbox_id="INBOX",
        display_name="INBOX",
        role="inbox",
    )


def _message(**overrides: object) -> MailMessage:
    defaults = {
        "id": "message-1",
        "account_id": "account-1",
        "mailbox_id": "mailbox-1",
        "folder": "INBOX",
        "provider_uid": "uid-1",
        "remote_identity": "imap:uid-1",
        "provider_message_id": "<message-1@example.test>",
        "thread_key": "<message-1@example.test>",
        "subject": "Original",
        "from_text": "sender@example.test",
        "to_text": "user-1@example.test",
        "cc_text": "",
        "snippet": "Original",
        "received_at": datetime(2026, 5, 12, 9, 0, 0),
        "sent_at": datetime(2026, 5, 12, 9, 0, 0),
        "is_read": False,
        "is_starred": False,
        "has_attachments": False,
        "body_status": "ready",
        "remote_flags_json": {},
        "local_state_json": {},
    }
    defaults.update(overrides)
    return MailMessage(**defaults)


def _fetched_message(**overrides: object) -> FetchedMessage:
    defaults = {
        "provider_uid": "uid-1",
        "provider_message_id": "<message-1@example.test>",
        "thread_key": "<message-1@example.test>",
        "subject": "Updated",
        "from_text": "sender@example.test",
        "to_text": "user-1@example.test",
        "cc_text": "",
        "text_body": "Updated body",
        "html_body": "",
        "snippet": "Updated body",
        "received_at": datetime(2026, 5, 12, 9, 0, 0),
        "sent_at": datetime(2026, 5, 12, 9, 0, 0),
        "is_read": True,
        "remote_identity": "imap:uid-1",
        "remote_flags": {"seen": True},
    }
    defaults.update(overrides)
    return FetchedMessage(**defaults)


def test_cursor_for_mailbox_sync_repairs_pop3_uidls_to_fetched_messages() -> None:
    session = _session()
    try:
        account = _account(protocol="pop3")
        mailbox = _mailbox()
        session.add_all([_user(), account, mailbox, _message(provider_uid="uid-synced")])
        session.commit()

        cursor = cursor_for_mailbox_sync(
            session,
            account=account,
            mailbox=mailbox,
            cursor={"uidls": ["uid-synced", "uid-never-fetched"]},
        )

        assert cursor == {"uidls": ["uid-synced"]}
    finally:
        session.close()


def test_apply_sync_batch_updates_legacy_message_and_preserves_local_flags() -> None:
    session = _session()
    try:
        account = _account()
        mailbox = _mailbox()
        session.add_all(
            [
                _user(),
                account,
                mailbox,
                _message(
                    id="legacy-message",
                    remote_identity="legacy:legacy-message",
                    local_state_json={"is_read": False, "is_starred": True},
                ),
                MailMessageBody(
                    message_id="legacy-message",
                    text_body="Original body",
                    html_body="",
                    content_hash="legacy",
                ),
            ]
        )
        session.commit()

        result = apply_sync_batch(
            session,
            account=account,
            mailbox=mailbox,
            batch=MailboxSyncBatch(
                messages=(
                    _fetched_message(
                        attachments=(
                            FetchedAttachment(
                                filename="report.pdf",
                                content_type="application/pdf",
                                size_bytes=128,
                            ),
                        ),
                    ),
                ),
                cursor={},
            ),
        )
        session.flush()

        row = session.get(MailMessage, "legacy-message")
        assert row is not None
        assert result.new_count == 0
        assert result.updated_count == 1
        assert row.remote_identity == "imap:uid-1"
        assert row.subject == "Updated"
        assert row.is_read is False
        assert row.is_starred is True
        assert row.body is not None
        assert row.body.text_body == "Updated body"
        assert len(row.attachments) == 1
        assert row.attachments[0].filename == "report.pdf"
    finally:
        session.close()


def test_apply_sync_batch_marks_remote_deletes_and_purges_body_and_attachments() -> None:
    session = _session()
    try:
        account = _account()
        mailbox = _mailbox()
        session.add_all(
            [
                _user(),
                account,
                mailbox,
                _message(),
                MailMessageBody(
                    message_id="message-1",
                    text_body="Body",
                    html_body="",
                    content_hash="hash",
                ),
                MailAttachment(
                    id="attachment-1",
                    message_id="message-1",
                    filename="report.pdf",
                    content_type="application/pdf",
                    size_bytes=128,
                ),
            ]
        )
        session.commit()

        result = apply_sync_batch(
            session,
            account=account,
            mailbox=mailbox,
            batch=MailboxSyncBatch(
                messages=(),
                cursor={},
                deleted_remote_identities=("imap:uid-1",),
            ),
        )
        session.flush()

        row = session.get(MailMessage, "message-1")
        assert row is not None
        assert result.deleted_count == 1
        assert row.remote_deleted_at is not None
        assert row.has_attachments is False
        assert row.body_status == "remote_deleted"
        assert session.get(MailMessageBody, "message-1") is None
        assert session.query(MailAttachment).filter_by(message_id="message-1").count() == 0
    finally:
        session.close()
