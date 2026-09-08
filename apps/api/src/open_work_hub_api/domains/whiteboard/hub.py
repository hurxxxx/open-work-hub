from __future__ import annotations

from datetime import datetime
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.content_access.ownership import record_ownership_transition
from open_work_hub_api.domains.whiteboard.access import (
    WhiteboardAccess,
    ensure_whiteboard_app_access,
    load_accessible_whiteboards,
    load_whiteboard_for_user_or_404,
    resolve_whiteboard_access,
)
from open_work_hub_api.domains.whiteboard.access import (
    primary_target as _primary_target,
)
from open_work_hub_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardTarget,
    WhiteboardUserItemPref,
    empty_scene,
)
from open_work_hub_api.domains.whiteboard.registry import (
    TargetRef,
    describe_source,
    resolve_target_label,
    target_write_allowed,
)


class WhiteboardTargetUpdatePayload(Protocol):
    company_admin_read_acknowledged: bool
    app: str
    type: str
    id: str
    sort_order: int


class WhiteboardPrimaryTarget(BaseModel):
    app: str
    type: str
    id: str
    sort_order: int


class WhiteboardTargetItem(WhiteboardPrimaryTarget):
    is_primary: bool


WhiteboardHubView = Literal["all", "mine", "recent", "favorites", "archived"]


class WhiteboardHubItem(BaseModel):
    ownership_kind: Literal["personal", "company"]
    company_visible: bool
    id: str
    source_app: str
    source_type: Literal["whiteboard"] = "whiteboard"
    source_id: str
    source_kind: str
    source_ref: str | None = None
    generation_kind: str
    location_label: str
    target_label: str
    primary_target: WhiteboardPrimaryTarget | None = None
    targets: list[WhiteboardTargetItem] = Field(default_factory=list)
    source_badge: str
    source_deeplink: str | None = None
    title: str
    created_by_id: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    trashed_at: datetime | None = None
    is_favorite: bool
    is_private: bool
    last_viewed_at: datetime | None = None
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool


class WhiteboardDetail(WhiteboardHubItem):
    scene: dict[str, Any]


class WhiteboardHubResponse(BaseModel):
    items: list[WhiteboardHubItem]
    total: int
    page: int
    page_size: int


class WhiteboardHubQuery(BaseModel):
    view: WhiteboardHubView = "all"
    q: str = ""
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = 1
    page_size: int = 50
    source_app: str | None = None
    source_kind: str | None = None
    space_id: str | None = None
    target_app: str | None = None
    target_type: str | None = None
    target_id: str | None = None


def resolve_whiteboard_hub_view(
    *,
    view: WhiteboardHubView | None,
    category: str | None,
) -> WhiteboardHubView:
    if view is not None:
        return view
    category_views: dict[str, WhiteboardHubView] = {
        "all": "all",
        "my": "mine",
        "mine": "mine",
        "recent": "recent",
        "favorite": "favorites",
        "favorites": "favorites",
        "archived": "archived",
    }
    return category_views.get(category or "all", "all")


def build_whiteboard_hub_response(
    db: Session,
    *,
    current_user: User,
    query: WhiteboardHubQuery,
) -> WhiteboardHubResponse:
    ensure_whiteboard_app_access(db, current_user)
    pref_map = _get_pref_map(db, current_user.id)
    whiteboards = [
        _serialize_whiteboard_item(
            db,
            whiteboard,
            resolve_whiteboard_access(db, whiteboard, current_user),
            pref_map.get(whiteboard.id),
            user=current_user,
        )
        for whiteboard in load_accessible_whiteboards(db, current_user)
    ]
    whiteboards = _filter_whiteboards(whiteboards, current_user_id=current_user.id, query=query)
    whiteboards = _sort_whiteboards(whiteboards, sort_by=query.sort_by, sort_dir=query.sort_dir)
    total = len(whiteboards)
    start = (query.page - 1) * query.page_size
    end = start + query.page_size
    return WhiteboardHubResponse(
        items=whiteboards[start:end],
        total=total,
        page=query.page,
        page_size=query.page_size,
    )


def _serialize_primary_target(
    target: WhiteboardTarget | None,
) -> WhiteboardPrimaryTarget | None:
    if target is None:
        return None
    return WhiteboardPrimaryTarget(
        app=target.target_app,
        type=target.target_type,
        id=target.target_id,
        sort_order=target.sort_order,
    )


def _serialize_target(target: WhiteboardTarget) -> WhiteboardTargetItem:
    return WhiteboardTargetItem(
        app=target.target_app,
        type=target.target_type,
        id=target.target_id,
        sort_order=target.sort_order,
        is_primary=target.is_primary,
    )


def _get_pref_map(db: Session, user_id: str) -> dict[str, WhiteboardUserItemPref]:
    rows = list(
        db.scalars(select(WhiteboardUserItemPref).where(WhiteboardUserItemPref.user_id == user_id))
    )
    return {row.whiteboard_id: row for row in rows}


def _get_or_create_pref(
    db: Session,
    user_id: str,
    whiteboard_id: str,
) -> WhiteboardUserItemPref:
    pref = db.scalar(
        select(WhiteboardUserItemPref).where(
            WhiteboardUserItemPref.user_id == user_id,
            WhiteboardUserItemPref.whiteboard_id == whiteboard_id,
        )
    )
    if pref is not None:
        return pref
    pref = WhiteboardUserItemPref(
        id=new_id(),
        user_id=user_id,
        whiteboard_id=whiteboard_id,
    )
    db.add(pref)
    db.flush()
    return pref


def _serialize_whiteboard_item(
    db: Session,
    whiteboard: Whiteboard,
    access: WhiteboardAccess,
    pref: WhiteboardUserItemPref | None,
    *,
    user: User,
) -> WhiteboardHubItem:
    primary_target = _primary_target(whiteboard)
    targets = sorted(
        whiteboard.targets,
        key=lambda item: (
            0 if item.is_primary else 1,
            item.target_app,
            item.target_type,
            item.sort_order,
            item.created_at,
        ),
    )
    location_label = resolve_target_label(
        db=db,
        user=user,
        target=primary_target,
    )
    source_badge, source_deeplink = describe_source(
        whiteboard=whiteboard,
        primary_target=primary_target,
    )
    return WhiteboardHubItem(
        id=whiteboard.id,
        ownership_kind=whiteboard.ownership_kind,
        company_visible=whiteboard.company_visible,
        source_app=whiteboard.source_app,
        source_id=whiteboard.id,
        source_kind=whiteboard.source_kind,
        source_ref=whiteboard.source_ref,
        generation_kind=whiteboard.generation_kind,
        location_label=location_label,
        target_label=location_label,
        primary_target=_serialize_primary_target(primary_target),
        targets=[_serialize_target(target) for target in targets],
        source_badge=source_badge,
        source_deeplink=source_deeplink,
        title=whiteboard.title,
        created_by_id=whiteboard.owner_id,
        created_by_name=getattr(whiteboard.owner, "full_name", ""),
        created_at=whiteboard.created_at,
        updated_at=whiteboard.updated_at,
        trashed_at=whiteboard.trashed_at,
        is_favorite=bool(pref and pref.is_favorite),
        is_private=(
            whiteboard.ownership_kind == "personal"
            and primary_target is None
            and not whiteboard.company_visible
            and not whiteboard.user_shares
            and not whiteboard.group_shares
            and not any(share.active for share in whiteboard.link_shares)
        ),
        last_viewed_at=pref.last_viewed_at if pref else None,
        can_view=access.can_view,
        can_edit=access.can_edit,
        can_share=access.can_share,
        can_manage=access.can_manage,
    )


def _serialize_whiteboard_detail(
    db: Session,
    whiteboard: Whiteboard,
    access: WhiteboardAccess,
    pref: WhiteboardUserItemPref | None,
    *,
    user: User,
) -> WhiteboardDetail:
    item = _serialize_whiteboard_item(db, whiteboard, access, pref, user=user)
    return WhiteboardDetail(
        **item.model_dump(),
        scene=whiteboard.scene or empty_scene(),
    )


def _lookup_item(
    db: Session,
    item_id: str,
    current_user: User,
    share_token: str | None = None,
) -> WhiteboardDetail:
    context = load_whiteboard_for_user_or_404(
        db,
        item_id,
        current_user,
        share_token=share_token,
    )
    return _serialize_whiteboard_detail(
        db,
        context.whiteboard,
        context.access,
        _get_pref_map(db, current_user.id).get(context.whiteboard.id),
        user=current_user,
    )


def _filter_whiteboards(
    whiteboards: list[WhiteboardHubItem],
    *,
    current_user_id: str,
    query: WhiteboardHubQuery,
) -> list[WhiteboardHubItem]:
    filtered = whiteboards
    if query.view == "mine":
        filtered = [
            item
            for item in filtered
            if item.trashed_at is None and item.created_by_id == current_user_id
        ]
    elif query.view == "recent":
        filtered = [
            item for item in filtered if item.trashed_at is None and item.last_viewed_at is not None
        ]
    elif query.view == "favorites":
        filtered = [item for item in filtered if item.trashed_at is None and item.is_favorite]
    elif query.view == "archived":
        filtered = [item for item in filtered if item.trashed_at is not None]
    else:
        filtered = [item for item in filtered if item.trashed_at is None]

    def target_matches(item: WhiteboardHubItem) -> bool:
        target_app = "pms" if query.space_id else query.target_app
        target_type = "space" if query.space_id else query.target_type
        target_id = query.space_id or query.target_id
        if not (target_app or target_type or target_id):
            return True
        return any(
            (target_app is None or target.app == target_app)
            and (target_type is None or target.type == target_type)
            and (target_id is None or target.id == target_id)
            for target in item.targets
        )

    if query.source_app:
        filtered = [item for item in filtered if item.source_app == query.source_app]
    if query.source_kind:
        filtered = [item for item in filtered if item.source_kind == query.source_kind]
    filtered = [item for item in filtered if target_matches(item)]

    search = query.q.strip().lower()
    if search:
        filtered = [
            item
            for item in filtered
            if search in item.title.lower()
            or search in item.location_label.lower()
            or search in item.source_badge.lower()
        ]
    return filtered


def _sort_whiteboards(
    whiteboards: list[WhiteboardHubItem],
    *,
    sort_by: str,
    sort_dir: Literal["asc", "desc"],
) -> list[WhiteboardHubItem]:
    reverse = sort_dir != "asc"

    def sort_key(item: WhiteboardHubItem):
        if sort_by == "title":
            return item.title.lower()
        if sort_by == "created_at":
            return item.created_at
        if sort_by == "last_viewed_at":
            return item.last_viewed_at or datetime.min
        if sort_by == "target_sort_order":
            return item.targets[0].sort_order if item.targets else 0
        return item.updated_at

    return sorted(whiteboards, key=sort_key, reverse=reverse)


def _upsert_primary_target(
    db: Session,
    *,
    whiteboard: Whiteboard,
    payload: WhiteboardTargetUpdatePayload,
    current_user: User,
) -> set[str]:
    _publish_for_target(
        db,
        whiteboard=whiteboard,
        current_user=current_user,
        company_admin_read_acknowledged=payload.company_admin_read_acknowledged,
    )
    ref = TargetRef(app=payload.app, type=payload.type, id=payload.id)
    if not target_write_allowed(
        db=db,
        user=current_user,
        ref=ref,
    ):
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.target_edit_access_required",
        )
    changed_board_ids = {whiteboard.id}
    if _is_singleton_context(ref):
        changed_board_ids.update(
            _delete_context_slot(db, ref=ref, except_whiteboard_id=whiteboard.id)
        )

    for target in whiteboard.targets:
        target.is_primary = False
        db.add(target)

    existing = next(
        (
            target
            for target in whiteboard.targets
            if target.target_app == payload.app
            and target.target_type == payload.type
            and target.target_id == payload.id
        ),
        None,
    )
    if existing is None:
        existing = WhiteboardTarget(
            id=new_id(),
            whiteboard_id=whiteboard.id,
            target_app=payload.app,
            target_type=payload.type,
            target_id=payload.id,
            is_primary=True,
            sort_order=payload.sort_order,
            created_by_id=current_user.id,
        )
        db.add(existing)
        whiteboard.targets.append(existing)
    else:
        existing.is_primary = True
        existing.sort_order = payload.sort_order
        db.add(existing)
    db.flush()
    return changed_board_ids


def _delete_primary_target(db: Session, whiteboard: Whiteboard) -> None:
    for target in list(whiteboard.targets):
        if target.is_primary:
            db.delete(target)


def _is_singleton_context(ref: TargetRef) -> bool:
    return (ref.app == "meeting" and ref.type == "meeting") or (
        ref.app == "pms" and ref.type == "task_list"
    )


def _require_context_write(
    db: Session,
    *,
    user: User,
    ref: TargetRef,
) -> None:
    if not target_write_allowed(db=db, user=user, ref=ref):
        raise localized_http_exception(
            status_code=403,
            code="whiteboard.target_edit_access_required",
        )


def _find_context_slot(db: Session, ref: TargetRef) -> WhiteboardTarget | None:
    return db.scalar(
        select(WhiteboardTarget)
        .options(selectinload(WhiteboardTarget.whiteboard))
        .where(
            WhiteboardTarget.target_app == ref.app,
            WhiteboardTarget.target_type == ref.type,
            WhiteboardTarget.target_id == ref.id,
        )
        .order_by(WhiteboardTarget.created_at.asc())
    )


def _delete_context_slot(
    db: Session,
    *,
    ref: TargetRef,
    except_whiteboard_id: str | None = None,
) -> set[str]:
    targets = list(
        db.scalars(
            select(WhiteboardTarget).where(
                WhiteboardTarget.target_app == ref.app,
                WhiteboardTarget.target_type == ref.type,
                WhiteboardTarget.target_id == ref.id,
            )
        )
    )
    changed_board_ids: set[str] = set()
    for target in targets:
        if except_whiteboard_id is not None and target.whiteboard_id == except_whiteboard_id:
            continue
        db.delete(target)
        changed_board_ids.add(target.whiteboard_id)
    if changed_board_ids:
        db.flush()
    return changed_board_ids


def _attach_context_slot(
    db: Session,
    *,
    whiteboard: Whiteboard,
    ref: TargetRef,
    current_user: User,
    is_primary: bool,
    company_admin_read_acknowledged: bool = False,
) -> WhiteboardTarget:
    _require_context_write(db, user=current_user, ref=ref)
    _publish_for_target(
        db,
        whiteboard=whiteboard,
        current_user=current_user,
        company_admin_read_acknowledged=company_admin_read_acknowledged,
    )
    existing = next(
        (
            target
            for target in whiteboard.targets
            if target.target_app == ref.app
            and target.target_type == ref.type
            and target.target_id == ref.id
        ),
        None,
    )
    if existing is None:
        existing = WhiteboardTarget(
            id=new_id(),
            whiteboard_id=whiteboard.id,
            target_app=ref.app,
            target_type=ref.type,
            target_id=ref.id,
            is_primary=is_primary,
            sort_order=0,
            created_by_id=current_user.id,
        )
        db.add(existing)
        whiteboard.targets.append(existing)
    else:
        existing.is_primary = existing.is_primary or is_primary
        existing.created_by_id = existing.created_by_id or current_user.id
        db.add(existing)
    db.flush()
    return existing


class ResolveWhiteboardSharedLinkResponse(BaseModel):
    item: WhiteboardHubItem


def _publish_for_target(
    db: Session,
    *,
    whiteboard: Whiteboard,
    current_user: User,
    company_admin_read_acknowledged: bool,
) -> None:
    db.scalar(select(Whiteboard).where(Whiteboard.id == whiteboard.id).with_for_update())
    if not resolve_whiteboard_access(db, whiteboard, current_user).can_share:
        raise localized_http_exception(status_code=403, code="whiteboard.share_access_required")
    record_ownership_transition(
        db,
        actor_user_id=current_user.id,
        resource_kind="whiteboard",
        resource_id=whiteboard.id,
        current_kind=whiteboard.ownership_kind,
        next_kind="company",
        company_admin_read_acknowledged=company_admin_read_acknowledged,
    )
    whiteboard.ownership_kind = "company"
