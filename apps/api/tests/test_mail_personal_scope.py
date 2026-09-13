from __future__ import annotations

from collections.abc import Callable
from datetime import datetime

from fastapi import HTTPException
import pytest
from sqlalchemy import create_engine, select, update
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import Base
from open_work_hub_api.domains.auth.app_access_models import (
    AppAccessPolicy,
    AppGroupGrant,
    AppUserGrant,
)
from open_work_hub_api.domains.auth.models import CompanyAppControl, User
from open_work_hub_api.domains.groups.models import Group, GroupMember
from open_work_hub_api.domains.mail import service
from open_work_hub_api.domains.mail.clients import (
    FetchedMessage,
    MailboxInfo,
    MailboxSyncBatch,
    MailConnectionSettings,
)
from open_work_hub_api.domains.mail.models import (
    MailAccount,
    MailAttachment,
    MailMailbox,
    MailMessage,
    MailMessageBody,
    MailSyncJob,
    MailSyncState,
)
from open_work_hub_api.domains.mail.sync_policy import MailSyncAccessRevoked


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
    from company_admission_fixture import company_authority_tables, seed_company_app_access

    tables = [
        *company_authority_tables(),
        MailAccount.__table__,
        MailMailbox.__table__,
        MailMessage.__table__,
        MailMessageBody.__table__,
        MailAttachment.__table__,
        MailSyncJob.__table__,
        MailSyncState.__table__,
    ]
    Base.metadata.create_all(engine, tables=tables)
    with Session(engine) as session:
        seed_company_app_access(session, app_ids=["mail"])
        yield session
    Base.metadata.drop_all(engine, tables=tables)
    engine.dispose()


def test_personal_mail_supports_distinct_accounts_and_enforces_owner_join(db: Session) -> None:
    owner = _user("owner")
    other = _user("other")
    first = _account("account-1", owner.id, label="Primary")
    duplicate = _account("account-2", owner.id, label="Archive")
    duplicate.email_address = "archive@example.test"
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


class SyncClient:
    def __init__(self) -> None:
        self.list_calls = 0
        self.sync_calls = 0
        self.on_list: Callable[[], None] = lambda: None
        self.on_sync: Callable[[], None] = lambda: None

    def list_mailboxes(self, _settings: MailConnectionSettings) -> list[MailboxInfo]:
        self.list_calls += 1
        self.on_list()
        return [MailboxInfo(provider_mailbox_id="INBOX", display_name="Inbox", role="inbox")]

    def sync_mailbox(self, _settings: MailConnectionSettings, **_kwargs) -> MailboxSyncBatch:
        self.sync_calls += 1
        self.on_sync()
        return MailboxSyncBatch(
            messages=(
                FetchedMessage(
                    provider_uid="uid-1",
                    provider_message_id="message@example.test",
                    thread_key=None,
                    subject="Synthetic sync result",
                    from_text="sender@example.test",
                    to_text="owner@example.test",
                    cc_text="",
                    text_body="Disposable mail fixture",
                    html_body="",
                    snippet="Disposable mail fixture",
                    received_at=datetime(2026, 9, 8),
                    sent_at=None,
                    is_read=False,
                ),
            ),
            cursor={"highest_seen_uid": 1},
        )


@pytest.fixture
def sync_job(db: Session, monkeypatch: pytest.MonkeyPatch) -> MailSyncJob:
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
    settings = MailConnectionSettings(
        protocol="imap",
        incoming_host="imap.example.test",
        incoming_port=993,
        incoming_security="ssl",
        incoming_username="fixture",
        incoming_password="fixture",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="fixture",
        smtp_password="fixture",
        email_address="owner@example.test",
    )
    monkeypatch.setattr(service, "settings_from_account", lambda _row: settings)
    monkeypatch.setattr(service, "enforce_connection_profile", lambda *_args, **_kwargs: None)
    return job


def _restrict_and_revoke(db: Session, reason: str) -> None:
    owner = db.get(User, "owner")
    if reason in {"inactive", "blocked", "temporary_password"}:
        if reason == "inactive":
            owner.status = "inactive"
        elif reason == "blocked":
            owner.login_blocked = True
        else:
            owner.must_change_password = True
    elif reason == "company_disabled":
        db.get(CompanyAppControl, "mail").enabled = False
    elif reason == "account_deleted":
        db.get(MailAccount, "account-1").deleted_at = datetime(2026, 9, 8)
    else:
        db.get(AppAccessPolicy, "mail").audience = "selected"
        if reason == "direct_grant":
            grant = AppUserGrant(app_id="mail", user_id=owner.id)
            db.add(grant)
            db.flush()
            db.delete(grant)
        else:
            group = Group(source="local", id="group-1", name="Mail users", active=True)
            db.add(group)
            db.flush()
            db.add(AppGroupGrant(app_id="mail", group_id=group.id))
            if reason.startswith("organization_"):
                group.source = "hr"
                group.slug = "mail-team"
                group.unit_type = "department"
                owner.primary_organization_unit_id = group.id
                if reason == "organization_inactive":
                    group.active = False
                else:
                    owner.primary_organization_unit_id = None
            else:
                membership = GroupMember(group_id=group.id, user_id=owner.id)
                db.add(membership)
                db.flush()
                if reason == "group_inactive":
                    group.active = False
                else:
                    db.delete(membership)
    db.commit()


@pytest.mark.parametrize(
    "reason",
    [
        "inactive",
        "blocked",
        "temporary_password",
        "company_disabled",
        "direct_grant",
        "group_member_removed",
        "group_inactive",
        "organization_inactive",
        "organization_assignment_removed",
        "account_deleted",
    ],
)
def test_queued_sync_rechecks_current_owner_before_provider(
    db: Session, sync_job: MailSyncJob, reason: str
) -> None:
    _restrict_and_revoke(db, reason)
    client = SyncClient()

    assert service.process_mail_sync_job(db, sync_job.id, client=client) == "cancelled"

    db.refresh(sync_job)
    assert sync_job.status == "cancelled"
    assert sync_job.attempts == 0
    assert sync_job.lease_owner is None
    assert sync_job.lease_expires_at is None
    assert sync_job.next_retry_at is None
    assert (client.list_calls, client.sync_calls) == (0, 0)
    assert list(db.scalars(select(MailMessage))) == []


@pytest.mark.parametrize("stage", ["discovery", "fetch"])
@pytest.mark.parametrize("reason", ["temporary_password", "direct_grant", "company_disabled"])
def test_inflight_sync_revocation_discards_provider_response(
    db: Session, sync_job: MailSyncJob, stage: str, reason: str
) -> None:
    client = SyncClient()

    def revoke() -> None:
        _restrict_and_revoke(db, reason)

    if stage == "discovery":
        client.on_list = revoke
    else:
        client.on_sync = revoke

    assert service.process_mail_sync_job(db, sync_job.id, client=client) == "cancelled"

    db.refresh(sync_job)
    assert sync_job.status == "cancelled"
    assert sync_job.attempts == 1
    assert sync_job.next_retry_at is None
    assert sync_job.lease_owner is None
    assert sync_job.lease_expires_at is None
    assert client.list_calls == 1
    assert client.sync_calls == (1 if stage == "fetch" else 0)
    assert list(db.scalars(select(MailMessage))) == []
    assert list(db.scalars(select(MailMessageBody))) == []
    assert all(not state.cursor_json for state in db.scalars(select(MailSyncState)))


def test_dispatcher_terminalizes_revoked_owner_without_publishing(
    db: Session, sync_job: MailSyncJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    _restrict_and_revoke(db, "group_inactive")
    published: list[str] = []
    monkeypatch.setattr(service, "_publish_sync_job", lambda *, job_id: published.append(job_id))

    assert service.publish_due_mail_sync_jobs(db) == 0

    db.refresh(sync_job)
    assert sync_job.status == "cancelled"
    assert sync_job.last_published_at is None
    assert published == []


def test_direct_sync_uses_same_owner_gate(db: Session, sync_job: MailSyncJob) -> None:
    _restrict_and_revoke(db, "blocked")
    client = SyncClient()

    with pytest.raises(MailSyncAccessRevoked):
        service.sync_account(db, account_id=sync_job.account_id, client=client)

    assert (client.list_calls, client.sync_calls) == (0, 0)


def test_enqueue_denial_is_an_api_forbidden_result(db: Session, sync_job: MailSyncJob) -> None:
    _restrict_and_revoke(db, "direct_grant")

    with pytest.raises(HTTPException) as error:
        service.enqueue_account_sync(db, user=db.get(User, "owner"), account_id=sync_job.account_id)

    assert error.value.status_code == 403
    assert error.value.detail.code == "app.access_required"
    assert list(db.scalars(select(MailSyncState))) == []


def test_sync_does_not_trust_an_already_loaded_owner(db: Session, sync_job: MailSyncJob) -> None:
    cached_owner = db.get(User, "owner")
    with Session(db.get_bind()) as administrator:
        administrator.execute(update(User).where(User.id == "owner").values(login_blocked=True))
        administrator.commit()
    assert cached_owner.login_blocked is False
    client = SyncClient()

    assert service.process_mail_sync_job(db, sync_job.id, client=client) == "cancelled"

    assert (client.list_calls, client.sync_calls) == (0, 0)


def test_revocation_after_job_claim_is_terminal(
    db: Session, sync_job: MailSyncJob, monkeypatch: pytest.MonkeyPatch
) -> None:
    original_sync = service.sync_account

    def revoke_then_sync(session, **kwargs):
        _restrict_and_revoke(session, "direct_grant")
        return original_sync(session, **kwargs)

    monkeypatch.setattr(service, "sync_account", revoke_then_sync)
    client = SyncClient()

    assert service.process_mail_sync_job(db, sync_job.id, client=client) == "cancelled"

    db.refresh(sync_job)
    assert sync_job.attempts == 1
    assert sync_job.status == "cancelled"
    assert sync_job.next_retry_at is None
    assert (client.list_calls, client.sync_calls) == (0, 0)


def test_provider_failure_still_uses_existing_retry_policy(
    db: Session, sync_job: MailSyncJob
) -> None:
    client = SyncClient()

    def provider_failure():
        raise RuntimeError("Synthetic provider failure")

    client.on_sync = provider_failure

    with pytest.raises(service.MailSyncRetryScheduled):
        service.process_mail_sync_job(db, sync_job.id, client=client)

    db.refresh(sync_job)
    assert sync_job.status == "pending"
    assert sync_job.attempts == 1
    assert sync_job.next_retry_at is not None
    assert sync_job.lease_owner is None
    assert list(db.scalars(select(MailMessage))) == []


def test_admitted_owner_sync_still_persists_messages_and_checkpoint(
    db: Session, sync_job: MailSyncJob
) -> None:
    client = SyncClient()

    assert service.process_mail_sync_job(db, sync_job.id, client=client) == "synced:1"

    db.refresh(sync_job)
    assert sync_job.status == "succeeded"
    assert (client.list_calls, client.sync_calls) == (1, 1)
    message = db.scalar(select(MailMessage))
    assert message.account_id == sync_job.account_id
    assert message.body.text_body == "Disposable mail fixture"
    assert db.scalar(select(MailSyncState)).cursor_json == {"highest_seen_uid": 1}
