from __future__ import annotations

from dataclasses import dataclass

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import is_platform_admin_user
from open_work_hub_api.domains.auth.app_access import can_use_app
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.groups.service import user_group_ids_query
from open_work_hub_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardGroupShare,
    WhiteboardLinkShare,
    WhiteboardTarget,
    WhiteboardUserShare,
)
from open_work_hub_api.domains.whiteboard.registry import (
    TargetRef,
    project_target_access,
)

TEAM_ACCESS_LEVEL_RANK = {
    "read": 10,
    "edit": 20,
}


@dataclass
class WhiteboardAccess:
    access_level: str | None
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool


@dataclass(frozen=True)
class WhiteboardAccessContext:
    whiteboard: Whiteboard
    access: WhiteboardAccess


def max_access_level(*levels: str | None) -> str | None:
    ranked = [level for level in levels if level in TEAM_ACCESS_LEVEL_RANK]
    if not ranked:
        return None
    return max(ranked, key=lambda item: TEAM_ACCESS_LEVEL_RANK[item])


def ensure_whiteboard_app_access(db: Session, user: User) -> None:
    if not can_use_app(db, user_id=user.id, app_id="whiteboard"):
        raise localized_http_exception(status_code=403, code="platform.app_disabled")


def primary_target(whiteboard: Whiteboard) -> WhiteboardTarget | None:
    active = list(whiteboard.targets)
    if not active:
        return None
    active.sort(
        key=lambda item: (
            0 if item.is_primary else 1,
            item.sort_order,
            item.created_at,
        )
    )
    return active[0]


def target_access_level(
    db: Session,
    whiteboard: Whiteboard,
    user: User,
) -> tuple[str | None, bool]:
    best_level: str | None = None
    can_manage = False
    for target in db.scalars(
        select(WhiteboardTarget).where(WhiteboardTarget.whiteboard_id == whiteboard.id)
    ):
        projection = project_target_access(
            db=db,
            user=user,
            ref=TargetRef(
                app=target.target_app,
                type=target.target_type,
                id=target.target_id,
            ),
        )
        if projection.can_manage:
            can_manage = True
        candidate = (
            "edit"
            if projection.can_edit or projection.can_manage
            else "read"
            if projection.can_view
            else None
        )
        best_level = max_access_level(best_level, candidate)
    return best_level, can_manage


def resolve_whiteboard_access(
    db: Session, whiteboard: Whiteboard, user: User, share_token: str | None = None
) -> WhiteboardAccess:
    if not can_use_app(db, user_id=user.id, app_id="whiteboard"):
        return WhiteboardAccess(None, False, False, False, False)
    if share_token is not None:
        link = db.scalar(
            select(WhiteboardLinkShare).where(
                WhiteboardLinkShare.whiteboard_id == whiteboard.id,
                WhiteboardLinkShare.active.is_(True),
                WhiteboardLinkShare.token == share_token,
            )
        )
        level = getattr(link, "access_level", None)
        return WhiteboardAccess(
            level, level in TEAM_ACCESS_LEVEL_RANK, level == "edit", False, False
        )
    if whiteboard.owner_id == user.id:
        return WhiteboardAccess("edit", True, True, True, True)
    direct = db.scalar(
        select(WhiteboardUserShare.access_level).where(
            WhiteboardUserShare.whiteboard_id == whiteboard.id,
            WhiteboardUserShare.user_id == user.id,
        )
    )
    groups = list(
        db.scalars(
            select(WhiteboardGroupShare.access_level).where(
                WhiteboardGroupShare.whiteboard_id == whiteboard.id,
                WhiteboardGroupShare.group_id.in_(user_group_ids_query(user.id)),
            )
        )
    )
    target_level, target_manage = target_access_level(db, whiteboard, user)
    admin_level = (
        "read"
        if whiteboard.ownership_kind == "company" and is_platform_admin_user(user, db)
        else None
    )
    level = max_access_level(
        direct, target_level, admin_level, "read" if whiteboard.company_visible else None, *groups
    )
    return WhiteboardAccess(
        level, level in TEAM_ACCESS_LEVEL_RANK, level == "edit", target_manage, target_manage
    )


def whiteboard_query():
    return select(Whiteboard).options(
        selectinload(Whiteboard.owner),
        selectinload(Whiteboard.targets),
        selectinload(Whiteboard.user_shares).selectinload(WhiteboardUserShare.user),
        selectinload(Whiteboard.link_shares),
    )


def load_accessible_whiteboards(db: Session, user: User) -> list[Whiteboard]:
    whiteboards = list(db.scalars(whiteboard_query().where()))
    return [
        whiteboard
        for whiteboard in whiteboards
        if resolve_whiteboard_access(db, whiteboard, user).can_view
    ]


def load_whiteboard_for_access(db: Session, whiteboard_id: str) -> Whiteboard | None:
    query = whiteboard_query().where(Whiteboard.id == whiteboard_id)
    return db.scalar(query)


def load_whiteboard_for_user_or_404(
    db: Session,
    item_id: str,
    current_user: User,
    share_token: str | None = None,
) -> WhiteboardAccessContext:
    whiteboard = load_whiteboard_for_access(db, item_id)
    if whiteboard is None:
        raise localized_http_exception(status_code=404, code="whiteboard.not_found")
    access = resolve_whiteboard_access(db, whiteboard, current_user, share_token=share_token)
    if not access.can_view or (whiteboard.trashed_at is not None and not access.can_manage):
        raise localized_http_exception(status_code=404, code="whiteboard.not_found")
    return WhiteboardAccessContext(whiteboard=whiteboard, access=access)


def load_whiteboard_for_share_token_or_404(
    db: Session,
    share_token: str,
    current_user: User,
) -> WhiteboardAccessContext:
    whiteboard = db.scalar(
        whiteboard_query()
        .join(WhiteboardLinkShare, WhiteboardLinkShare.whiteboard_id == Whiteboard.id)
        .where(
            WhiteboardLinkShare.token == share_token,
            WhiteboardLinkShare.active.is_(True),
        )
    )
    if whiteboard is None or whiteboard.trashed_at is not None:
        raise localized_http_exception(status_code=404, code="whiteboard.shared_link_not_found")
    access = resolve_whiteboard_access(db, whiteboard, current_user, share_token=share_token)
    if not access.can_view:
        raise localized_http_exception(status_code=404, code="whiteboard.shared_link_not_found")
    return WhiteboardAccessContext(whiteboard=whiteboard, access=access)


def load_whiteboard_for_share_or_403(
    db: Session,
    item_id: str,
    current_user: User,
) -> Whiteboard:
    context = load_whiteboard_for_user_or_404(db, item_id, current_user)
    if not context.access.can_share:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="whiteboard.share_access_required",
        )
    return context.whiteboard
