from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from ai_do_api.domains.auth.models import utcnow_naive
from ai_do_api.domains.auth.security import new_id
from ai_do_api.domains.mail.clients import (
    MailboxInfo,
    MailConnectionSettings,
    MailProtocolClient,
)
from ai_do_api.domains.mail.models import MailAccount, MailMailbox, MailSyncState


def ensure_inbox_mailbox(
    db: Session,
    *,
    account: MailAccount,
) -> tuple[MailMailbox, MailSyncState]:
    return ensure_mailbox(
        db,
        account=account,
        mailbox=MailboxInfo(
            provider_mailbox_id="INBOX",
            display_name="INBOX",
            role="inbox",
        ),
    )


def sync_targets_for_account(
    db: Session,
    *,
    account: MailAccount,
    settings: MailConnectionSettings,
    client: MailProtocolClient,
) -> list[tuple[MailMailbox, MailSyncState]]:
    mailbox_infos = list_syncable_mailboxes(settings, client)
    targets: list[tuple[MailMailbox, MailSyncState]] = []
    for mailbox_info in mailbox_infos:
        mailbox, state = ensure_mailbox(db, account=account, mailbox=mailbox_info)
        if mailbox.sync_enabled:
            targets.append((mailbox, state))
    if targets:
        return targets
    return [ensure_inbox_mailbox(db, account=account)]


def list_syncable_mailboxes(
    settings: MailConnectionSettings,
    client: MailProtocolClient,
) -> list[MailboxInfo]:
    list_mailboxes = getattr(client, "list_mailboxes", None)
    if callable(list_mailboxes):
        mailboxes = list_mailboxes(settings)
    else:
        mailboxes = [MailboxInfo(provider_mailbox_id="INBOX", display_name="INBOX", role="inbox")]
    if settings.protocol == "pop3":
        return [MailboxInfo(provider_mailbox_id="INBOX", display_name="INBOX", role="inbox")]
    return deduplicate_mailboxes(mailboxes)


def deduplicate_mailboxes(mailboxes: list[MailboxInfo]) -> list[MailboxInfo]:
    rows: dict[str, MailboxInfo] = {}
    for mailbox in mailboxes:
        provider_mailbox_id = mailbox.provider_mailbox_id.strip()
        if not provider_mailbox_id:
            continue
        rows.setdefault(
            provider_mailbox_id,
            MailboxInfo(
                provider_mailbox_id=provider_mailbox_id,
                display_name=mailbox.display_name.strip() or provider_mailbox_id,
                role=mailbox.role.strip() or "folder",
                sync_enabled=mailbox.sync_enabled,
            ),
        )
    if not any(mailbox.role == "inbox" for mailbox in rows.values()):
        rows["INBOX"] = MailboxInfo(
            provider_mailbox_id="INBOX",
            display_name="INBOX",
            role="inbox",
        )
    return sorted(
        rows.values(),
        key=lambda mailbox: (
            0 if mailbox.role == "inbox" else 1,
            mailbox.display_name.lower(),
            mailbox.provider_mailbox_id.lower(),
        ),
    )


def ensure_mailbox(
    db: Session,
    *,
    account: MailAccount,
    mailbox: MailboxInfo,
) -> tuple[MailMailbox, MailSyncState]:
    provider_mailbox_id = mailbox.provider_mailbox_id.strip()
    row = db.scalar(
        select(MailMailbox).where(
            MailMailbox.account_id == account.id,
            MailMailbox.provider_mailbox_id == provider_mailbox_id,
        )
    )
    if row is None:
        row = MailMailbox(
            id=new_id(),
            account_id=account.id,
            provider_mailbox_id=provider_mailbox_id,
            role=mailbox.role,
            display_name=mailbox.display_name,
            sync_enabled=mailbox.sync_enabled,
        )
        db.add(row)
    else:
        row.role = mailbox.role
        row.display_name = mailbox.display_name
        row.sync_enabled = mailbox.sync_enabled
        row.updated_at = utcnow_naive()
        db.add(row)
    state = db.scalar(select(MailSyncState).where(MailSyncState.mailbox_id == row.id))
    if state is None:
        state = MailSyncState(
            id=new_id(),
            account_id=account.id,
            mailbox_id=row.id,
            status="idle",
            cursor_json={},
        )
        db.add(state)
    return row, state
