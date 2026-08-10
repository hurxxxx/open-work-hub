from __future__ import annotations

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import User
from open_alm_api.domains.mail import service
from open_alm_api.domains.mail.models import (
    MailAccount,
    MailMailbox,
    MailMessage,
    MailMessageBody,
    MailSyncJob,
)


def _user(user_id: str) -> User:
    return User(
        id=user_id,
        login_id=user_id,
        email=f"{user_id}@example.test",
        full_name=user_id,
        password_hash="test",
    )


def _account(account_id: str, user_id: str, *, label: str) -> MailAccount:
    return MailAccount(
        id=account_id,
        user_id=user_id,
        email_address="shared@example.test",
        display_name="Shared mailbox",
        account_label=label,
        protocol="imap",
        provider_kind="imap",
        incoming_host="imap.example.test",
        incoming_port=993,
        incoming_security="ssl",
        incoming_username="shared@example.test",
        incoming_password_encrypted=f"incoming-{account_id}",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="shared@example.test",
        smtp_password_encrypted=f"smtp-{account_id}",
    )


def _message(message_id: str, account_id: str) -> MailMessage:
    return MailMessage(
        id=message_id,
        account_id=account_id,
        folder="INBOX",
        provider_uid="provider-1",
        remote_identity="imap:provider-1",
        subject=message_id,
    )


@pytest.fixture
def db() -> Session:
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as session:
        yield session
    Base.metadata.drop_all(engine)
    engine.dispose()


def test_personal_mail_preserves_duplicate_accounts_and_enforces_owner_join(db: Session) -> None:
    owner = _user("owner")
    other = _user("other")
    first = _account("account-1", owner.id, label="Primary")
    duplicate = _account("account-2", owner.id, label="Archive")
    foreign = _account("account-3", other.id, label="Other user")
    first_message = _message("message-1", first.id)
    duplicate_message = _message("message-2", duplicate.id)
    foreign_message = _message("message-3", foreign.id)
    db.add_all(
        [
            owner,
            other,
            first,
            duplicate,
            foreign,
            first_message,
            duplicate_message,
            foreign_message,
            MailMessageBody(message_id=first_message.id, text_body="first"),
            MailMessageBody(message_id=duplicate_message.id, text_body="duplicate"),
            MailMessageBody(message_id=foreign_message.id, text_body="foreign"),
        ]
    )
    db.commit()

    accounts = service.list_accounts(db, user=owner)
    messages = service.list_messages(db, user=owner)

    assert [row.id for row in accounts] == [first.id, duplicate.id]
    assert {row.id for row in messages.items} == {first_message.id, duplicate_message.id}
    assert first.incoming_password_encrypted == "incoming-account-1"
    assert duplicate.incoming_password_encrypted == "incoming-account-2"
    with pytest.raises(HTTPException) as exc_info:
        service.get_message(db, user=owner, message_id=foreign_message.id)
    assert exc_info.value.status_code == 404
    with pytest.raises(HTTPException) as account_exc_info:
        service.list_messages(db, user=owner, account_id=foreign.id)
    assert account_exc_info.value.status_code == 404


def test_disabled_platform_gate_cancels_sync_before_provider_io(
    db: Session,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    owner = _user("owner")
    account = _account("account-1", owner.id, label="Primary")
    mailbox = MailMailbox(
        id="mailbox-1",
        account_id=account.id,
        provider_mailbox_id="INBOX",
        role="inbox",
        display_name="INBOX",
    )
    job = MailSyncJob(
        id="job-1",
        account_id=account.id,
        mailbox_id=mailbox.id,
        operation="initial",
        status="pending",
    )
    db.add_all([owner, account, mailbox, job])
    db.commit()
    monkeypatch.setattr(service, "mail_background_sync_enabled", lambda _db: False)

    assert service.publish_due_mail_sync_jobs(db) == 0
    db.refresh(job)
    assert job.status == "pending"
    assert job.last_published_at is None

    class FailingClient:
        def __getattr__(self, _name: str):
            raise AssertionError("mail provider must not be called while disabled")

    result = service.process_mail_sync_job(db, job.id, client=FailingClient())

    db.refresh(job)
    assert result == "cancelled"
    assert job.status == "cancelled"
    assert job.last_error == "mail app is disabled"
