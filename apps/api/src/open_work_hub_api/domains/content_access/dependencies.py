from __future__ import annotations

from fastapi import Depends

from open_work_hub_api.domains.auth.dependencies import AuthContext, require_auth_context
from open_work_hub_api.domains.content_access.grants import ContentGrantIssuer


def require_content_grant_issuer(
    auth: AuthContext = Depends(require_auth_context),
) -> ContentGrantIssuer:
    """Project the authenticated HTTP session into an explicit grant issuer."""

    return ContentGrantIssuer(
        user_id=auth.user.id,
        session_id=auth.session.id,
    )
