from __future__ import annotations

from sqlalchemy import create_engine
from sqlalchemy.orm import Session

from open_alm_api.core.db import Base
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.mail.clients import MailboxInfo, MailConnectionSettings
from open_alm_api.domains.mail.models import MailAccount, MailMailbox, MailSyncState
from open_alm_api.domains.mail.sync_mailboxes import (
    deduplicate_mailboxes,
    ensure_inbox_mailbox,
    ensure_mailbox,
    list_syncable_mailboxes,
    sync_targets_for_account,
)


def _session() -> Session:
    engine = create_engine("sqlite:///:memory:")
    Base.metadata.create_all(
        engine,
        tables=[
            Workspace.__table__,
            User.__table__,
            MailAccount.__table__,
            MailMailbox.__table__,
            MailSyncState.__table__,
        ],
    )
    return Session(engine)


def _settings(protocol: str = "imap") -> MailConnectionSettings:
    return MailConnectionSettings(
        protocol=protocol,
        incoming_host="mail.example.test",
        incoming_port=993,
        incoming_security="ssl",
        incoming_username="user",
        incoming_password="password",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="user",
        smtp_password="password",
        email_address="user@example.test",
        display_name="User",
        provider_kind=protocol,
    )


def _account() -> MailAccount:
    return MailAccount(
        id="account-1",
        user_id="user-1",
        email_address="user@example.test",
        display_name="User",
        protocol="imap",
        provider_kind="imap",
        incoming_host="mail.example.test",
        incoming_port=993,
        incoming_security="ssl",
        incoming_username="user",
        incoming_password_encrypted="encrypted",
        smtp_host="smtp.example.test",
        smtp_port=587,
        smtp_security="starttls",
        smtp_username="user",
        smtp_password_encrypted="encrypted",
    )


def _seed_account(session: Session) -> MailAccount:
    account = _account()
    session.add_all(
        [
            Workspace(id="workspace-1", key="workspace", name="Workspace", description=""),
            User(
                id="user-1",
                login_id="user-1",
                email="user-1@open-alm.local",
                full_name="User One",
                password_hash="hash",
                status="active",
            ),
            account,
        ]
    )
    session.commit()
    return account


class MultiMailboxClient:
    def list_mailboxes(self, settings: MailConnectionSettings) -> list[MailboxInfo]:
        assert settings.incoming_password == "password"
        return [
            MailboxInfo(provider_mailbox_id="Projects", display_name="Projects"),
            MailboxInfo(provider_mailbox_id="INBOX", display_name="Inbox", role="inbox"),
            MailboxInfo(
                provider_mailbox_id="[Gmail]/Sent Mail",
                display_name="Sent",
                role="sent",
                sync_enabled=False,
            ),
        ]


def test_deduplicate_mailboxes_trims_sorts_and_injects_inbox() -> None:
    assert [
        (mailbox.provider_mailbox_id, mailbox.display_name, mailbox.role, mailbox.sync_enabled)
        for mailbox in deduplicate_mailboxes(
            [
                MailboxInfo(provider_mailbox_id=" Projects ", display_name=" Projects "),
                MailboxInfo(provider_mailbox_id="", display_name="Ignored"),
                MailboxInfo(
                    provider_mailbox_id="Projects",
                    display_name="Duplicate",
                    role="folder",
                    sync_enabled=False,
                ),
            ]
        )
    ] == [
        ("INBOX", "INBOX", "inbox", True),
        ("Projects", "Projects", "folder", True),
    ]


def test_pop3_syncable_mailboxes_forces_single_inbox() -> None:
    assert list_syncable_mailboxes(_settings(protocol="pop3"), MultiMailboxClient()) == [
        MailboxInfo(provider_mailbox_id="INBOX", display_name="INBOX", role="inbox")
    ]


def test_ensure_mailbox_updates_existing_row_and_creates_state() -> None:
    session = _session()
    try:
        account = _seed_account(session)
        mailbox, state = ensure_mailbox(
            session,
            account=account,
            mailbox=MailboxInfo(provider_mailbox_id="INBOX", display_name="Inbox", role="inbox"),
        )
        session.flush()

        updated, same_state = ensure_mailbox(
            session,
            account=account,
            mailbox=MailboxInfo(
                provider_mailbox_id="INBOX",
                display_name="Primary Inbox",
                role="inbox",
                sync_enabled=False,
            ),
        )
        session.flush()

        assert mailbox.id == updated.id
        assert state.id == same_state.id
        assert updated.display_name == "Primary Inbox"
        assert updated.sync_enabled is False
        assert session.query(MailSyncState).filter_by(mailbox_id=updated.id).count() == 1
    finally:
        session.close()


def test_sync_targets_include_only_enabled_mailboxes_and_fallback_to_inbox() -> None:
    session = _session()
    try:
        account = _seed_account(session)

        targets = sync_targets_for_account(
            session,
            account=account,
            settings=_settings(),
            client=MultiMailboxClient(),
        )
        assert [(mailbox.provider_mailbox_id, mailbox.sync_enabled) for mailbox, _ in targets] == [
            ("INBOX", True),
            ("Projects", True),
        ]

        for mailbox, _state in targets:
            mailbox.sync_enabled = False
            session.add(mailbox)
        session.commit()

        fallback_mailbox, fallback_state = ensure_inbox_mailbox(session, account=account)
        assert fallback_mailbox.provider_mailbox_id == "INBOX"
        assert fallback_state.mailbox_id == fallback_mailbox.id
    finally:
        session.close()
