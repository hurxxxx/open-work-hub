from __future__ import annotations

from dataclasses import dataclass

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import (
    bind_current_workspace,
    get_current_workspace,
    resolve_workspaces,
)
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardTarget,
    WhiteboardLinkShare,
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


def ensure_whiteboard_workspace_access(db: Session, user: User) -> Workspace:
    current_workspace = get_current_workspace(db)
    if current_workspace is None:
        for summary in resolve_workspaces(db, user):
            workspace = db.scalar(
                select(Workspace).where(
                    Workspace.id == summary["id"],
                    Workspace.active.is_(True),
                )
            )
            if workspace is None:
                continue
            current_workspace = workspace
            bind_current_workspace(db, current_workspace)
            break
    if current_workspace is None:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="whiteboard.workspace_context_required",
        )
    return current_workspace


def workspace_for_whiteboard(db: Session, whiteboard: Whiteboard) -> Workspace:
    current_workspace = get_current_workspace(db)
    if current_workspace is not None and current_workspace.id == whiteboard.workspace_id:
        return current_workspace
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == whiteboard.workspace_id,
            Workspace.active.is_(True),
        )
    )
    if workspace is None:
        raise localized_http_exception(status_code=404, code="workspace.not_found")
    return workspace


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
    workspace = workspace_for_whiteboard(db, whiteboard)
    best_level: str | None = None
    can_manage = False
    for target in whiteboard.targets:
        projection = project_target_access(
            db=db,
            user=user,
            workspace=workspace,
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
    db: Session,
    whiteboard: Whiteboard,
    user: User,
    share_token: str | None = None,
) -> WhiteboardAccess:
    if whiteboard.owner_id == user.id:
        return WhiteboardAccess(
            access_level="edit",
            can_view=True,
            can_edit=True,
            can_share=True,
            can_manage=True,
        )
    direct_share = next((item for item in whiteboard.user_shares if item.user_id == user.id), None)
    matched_link = (
        next(
            (item for item in whiteboard.link_shares if item.active and item.token == share_token),
            None,
        )
        if share_token
        else None
    )
    target_level, target_can_manage = target_access_level(db, whiteboard, user)
    access_level = max_access_level(
        getattr(direct_share, "access_level", None),
        getattr(matched_link, "access_level", None),
        target_level,
    )
    return WhiteboardAccess(
        access_level=access_level,
        can_view=access_level in TEAM_ACCESS_LEVEL_RANK,
        can_edit=access_level == "edit",
        can_share=target_can_manage,
        can_manage=target_can_manage,
    )


def whiteboard_query():
    return select(Whiteboard).options(
        selectinload(Whiteboard.owner),
        selectinload(Whiteboard.targets),
        selectinload(Whiteboard.user_shares).selectinload(WhiteboardUserShare.user),
        selectinload(Whiteboard.link_shares),
    )


def load_accessible_whiteboards(db: Session, user: User) -> list[Whiteboard]:
    current_workspace = get_current_workspace(db)
    if current_workspace is None:
        return []
    whiteboards = list(
        db.scalars(whiteboard_query().where(Whiteboard.workspace_id == current_workspace.id))
    )
    return [
        whiteboard
        for whiteboard in whiteboards
        if resolve_whiteboard_access(db, whiteboard, user).can_view
    ]


def load_whiteboard_for_access(db: Session, whiteboard_id: str) -> Whiteboard | None:
    current_workspace = get_current_workspace(db)
    query = whiteboard_query().where(Whiteboard.id == whiteboard_id)
    if current_workspace is not None:
        query = query.where(Whiteboard.workspace_id == current_workspace.id)
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
