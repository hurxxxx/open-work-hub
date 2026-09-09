from __future__ import annotations

import secrets
from typing import Literal

from fastapi import status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.app_routes import InternalAppLocation, build_app_href
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.whiteboard.access import (
    load_whiteboard_for_access,
    load_whiteboard_for_share_or_403,
)
from open_work_hub_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardLinkShare,
    WhiteboardUserShare,
)


class WhiteboardUserShareItem(BaseModel):
    user_id: str
    email: str
    full_name: str
    access_level: Literal["read", "edit"]


class WhiteboardLinkShareItem(BaseModel):
    token: str
    access_level: Literal["read", "edit"]
    active: bool
    share_path: str


class WhiteboardSharingResponse(BaseModel):
    whiteboard_id: str
    owner_id: str
    users: list[WhiteboardUserShareItem]
    link_share: WhiteboardLinkShareItem | None = None


def get_whiteboard_sharing_response(
    db: Session,
    *,
    item_id: str,
    current_user: User,
) -> WhiteboardSharingResponse:
    whiteboard = load_whiteboard_for_share_or_403(db, item_id, current_user)
    return _serialize_sharing_response(whiteboard)


def upsert_whiteboard_user_share(
    db: Session,
    *,
    item_id: str,
    user_id: str,
    access_level: Literal["read", "edit"],
    current_user: User,
) -> WhiteboardSharingResponse:
    whiteboard = load_whiteboard_for_share_or_403(db, item_id, current_user)
    if user_id == current_user.id:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="whiteboard.owner_already_has_full_access",
        )
    target_user = db.scalar(
        select(User).where(
            User.id == user_id, User.status == "active", User.login_blocked.is_(False)
        )
    )
    if target_user is None:
        raise localized_http_exception(status_code=404, code="auth.user_not_found")
    share = next((item for item in whiteboard.user_shares if item.user_id == user_id), None)
    if share is None:
        share = WhiteboardUserShare(
            id=new_id(),
            whiteboard_id=whiteboard.id,
            user_id=user_id,
            access_level=access_level,
            created_by_id=current_user.id,
        )
        db.add(share)
    else:
        share.access_level = access_level
        db.add(share)
    db.commit()
    return _reload_sharing_response(db, whiteboard.id)


def delete_whiteboard_user_share(
    db: Session,
    *,
    item_id: str,
    user_id: str,
    current_user: User,
) -> WhiteboardSharingResponse:
    whiteboard = load_whiteboard_for_share_or_403(db, item_id, current_user)
    share = next((item for item in whiteboard.user_shares if item.user_id == user_id), None)
    if share is not None:
        db.delete(share)
        db.commit()
    return _reload_sharing_response(db, whiteboard.id)


def upsert_whiteboard_link_share(
    db: Session,
    *,
    item_id: str,
    access_level: Literal["read", "edit"],
    active: bool,
    regenerate_token: bool,
    current_user: User,
) -> WhiteboardSharingResponse:
    whiteboard = load_whiteboard_for_share_or_403(db, item_id, current_user)
    link_share = next(iter(whiteboard.link_shares), None)
    if link_share is None:
        link_share = WhiteboardLinkShare(
            id=new_id(),
            whiteboard_id=whiteboard.id,
            token=secrets.token_urlsafe(24),
            access_level=access_level,
            active=active,
            created_by_id=current_user.id,
        )
        db.add(link_share)
    else:
        if regenerate_token or not link_share.token:
            link_share.token = secrets.token_urlsafe(24)
        link_share.access_level = access_level
        link_share.active = active
        db.add(link_share)
    db.commit()
    return _reload_sharing_response(db, whiteboard.id)


def disable_whiteboard_link_share(
    db: Session,
    *,
    item_id: str,
    current_user: User,
) -> WhiteboardSharingResponse:
    whiteboard = load_whiteboard_for_share_or_403(db, item_id, current_user)
    link_share = next(iter(whiteboard.link_shares), None)
    if link_share is not None:
        link_share.active = False
        db.add(link_share)
        db.commit()
    return _reload_sharing_response(db, whiteboard.id)


def _serialize_sharing_response(whiteboard: Whiteboard) -> WhiteboardSharingResponse:
    link_share = next((item for item in whiteboard.link_shares if item.active), None)
    return WhiteboardSharingResponse(
        whiteboard_id=whiteboard.id,
        owner_id=whiteboard.owner_id,
        users=[
            WhiteboardUserShareItem(
                user_id=item.user_id,
                email=item.user.email,
                full_name=item.user.full_name,
                access_level=item.access_level,
            )
            for item in sorted(
                whiteboard.user_shares,
                key=lambda row: (row.user.full_name.lower(), row.user.email.lower()),
            )
        ],
        link_share=(
            WhiteboardLinkShareItem(
                token=link_share.token,
                access_level=link_share.access_level,
                active=link_share.active,
                share_path=build_app_href(
                    InternalAppLocation(
                        route_id="whiteboard.shared",
                        path_params={"shareToken": link_share.token},
                    )
                ),
            )
            if link_share is not None
            else None
        ),
    )


def _reload_sharing_response(db: Session, whiteboard_id: str) -> WhiteboardSharingResponse:
    whiteboard = load_whiteboard_for_access(db, whiteboard_id)
    assert whiteboard is not None
    return _serialize_sharing_response(whiteboard)
