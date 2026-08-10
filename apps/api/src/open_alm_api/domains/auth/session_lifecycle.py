from __future__ import annotations

from datetime import datetime

from sqlalchemy import or_, update
from sqlalchemy.orm import Session

from open_alm_api.domains.auth.models import AuthSession


def revoke_active_user_sessions(
    db: Session,
    *,
    user_id: str,
    revoked_at: datetime,
) -> int:
    """Revoke sessions owned by, or impersonated by, the blocked user."""

    result = db.execute(
        update(AuthSession)
        .where(
            or_(
                AuthSession.user_id == user_id,
                AuthSession.impersonator_user_id == user_id,
            ),
            AuthSession.revoked_at.is_(None),
            AuthSession.expires_at > revoked_at,
        )
        .values(revoked_at=revoked_at)
    )
    return max(result.rowcount or 0, 0)


__all__ = ["revoke_active_user_sessions"]
