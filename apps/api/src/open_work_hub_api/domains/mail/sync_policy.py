from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.auth.models import utcnow_naive
from open_work_hub_api.domains.mail.models import MailAccount, MailSyncJob


class MailSyncAccessRevoked(Exception):
    """A personal sync lost its current account or app authority; never retry it."""


def require_mail_sync_access(db: Session, *, account_id: str) -> None:
    # Read scalar authority rather than a possibly cached account/user relationship.
    owner_id = db.scalar(
        select(MailAccount.user_id).where(
            MailAccount.id == account_id,
            MailAccount.deleted_at.is_(None),
        )
    )
    if owner_id is None or not can_use_app(db, user_id=owner_id, app_id="mail"):
        raise MailSyncAccessRevoked("Mail sync access was revoked.")


def cancel_mail_sync_job(db: Session, *, job: MailSyncJob, error: str) -> None:
    """Terminalize in the caller's transaction without scheduling another attempt."""
    job.status = "cancelled"
    job.last_error = error
    job.lease_owner = None
    job.lease_expires_at = None
    job.next_retry_at = None
    job.updated_at = utcnow_naive()
    db.add(job)
