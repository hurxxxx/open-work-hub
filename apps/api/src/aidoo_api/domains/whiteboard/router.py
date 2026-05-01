from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.core.db import get_db_session
from aidoo_api.domains.auth.access import bind_current_workspace, get_current_workspace, resolve_workspaces
from aidoo_api.domains.auth.dependencies import require_current_user
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.whiteboard.models import (
    Whiteboard,
    WhiteboardContainer,
    WhiteboardUserItemPref,
    empty_scene,
)
from aidoo_api.domains.whiteboard.registry import (
    ContainerRef,
    container_write_allowed,
    describe_source,
    project_container_access,
    resolve_container_label,
)
from aidoo_api.domains.whiteboard.service import create_whiteboard_for_user


router = APIRouter(prefix="/whiteboard", tags=["whiteboard"])

TEAM_ACCESS_LEVEL_RANK = {
    "read": 10,
    "edit": 20,
}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _max_access_level(*levels: str | None) -> str | None:
    ranked = [level for level in levels if level in TEAM_ACCESS_LEVEL_RANK]
    if not ranked:
        return None
    return max(ranked, key=lambda item: TEAM_ACCESS_LEVEL_RANK[item])


@dataclass
class WhiteboardAccess:
    access_level: str | None
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool


class WhiteboardPrimaryContainer(BaseModel):
    app: str
    type: str
    id: str
    sort_order: int


class WhiteboardHubItem(BaseModel):
    id: str
    source_app: str
    source_type: Literal["whiteboard"] = "whiteboard"
    source_id: str
    source_kind: str
    source_ref: str | None = None
    generation_kind: str
    location_label: str
    container_label: str
    primary_container: WhiteboardPrimaryContainer | None = None
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
    view: Literal["all", "mine", "recent", "archived"] = "all"
    q: str = ""
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    page: int = 1
    page_size: int = 50
    source_app: str | None = None
    source_kind: str | None = None
    container_app: str | None = None
    container_type: str | None = None
    container_id: str | None = None


class WhiteboardContainerPayload(BaseModel):
    app: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., min_length=1, max_length=64)
    id: str = Field(..., min_length=1, max_length=128)
    sort_order: int = 0


class CreateWhiteboardRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    scene: dict[str, Any] | None = None
    source_app: str = Field(default="whiteboard", min_length=1, max_length=64)
    source_kind: str = Field(default="manual", min_length=1, max_length=64)
    source_ref: str | None = Field(default=None, max_length=128)
    generation_kind: str = Field(default="human", min_length=1, max_length=32)
    primary_container: WhiteboardContainerPayload | None = None


class UpdateWhiteboardRequest(BaseModel):
    title: str | None = Field(default=None, min_length=1, max_length=200)
    scene: dict[str, Any] | None = None


class UpdateWhiteboardContainerRequest(BaseModel):
    app: str = Field(..., min_length=1, max_length=64)
    type: str = Field(..., min_length=1, max_length=64)
    id: str = Field(..., min_length=1, max_length=128)
    sort_order: int = 0


class ToggleFavoriteResponse(BaseModel):
    is_favorite: bool


def _ensure_whiteboard_workspace_access(db: Session, user: User) -> Workspace:
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
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Whiteboard requests require a workspace context.",
        )
    return current_workspace


def _workspace_for_whiteboard(db: Session, whiteboard: Whiteboard) -> Workspace:
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
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


def _primary_container(whiteboard: Whiteboard) -> WhiteboardContainer | None:
    active = list(whiteboard.containers)
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


def _serialize_primary_container(
    container: WhiteboardContainer | None,
) -> WhiteboardPrimaryContainer | None:
    if container is None:
        return None
    return WhiteboardPrimaryContainer(
        app=container.container_app,
        type=container.container_type,
        id=container.container_id,
        sort_order=container.sort_order,
    )


def _container_access_level(
    db: Session,
    whiteboard: Whiteboard,
    user: User,
) -> tuple[str | None, bool]:
    workspace = _workspace_for_whiteboard(db, whiteboard)
    best_level: str | None = None
    can_manage = False
    for container in whiteboard.containers:
        projection = project_container_access(
            db=db,
            user=user,
            workspace=workspace,
            ref=ContainerRef(
                app=container.container_app,
                type=container.container_type,
                id=container.container_id,
            ),
        )
        if projection.can_manage:
            can_manage = True
        candidate = (
            "edit"
            if projection.can_edit or projection.can_manage
            else "read" if projection.can_view else None
        )
        best_level = _max_access_level(best_level, candidate)
    return best_level, can_manage


def _resolve_whiteboard_access(
    db: Session,
    whiteboard: Whiteboard,
    user: User,
) -> WhiteboardAccess:
    if whiteboard.owner_id == user.id:
        return WhiteboardAccess(
            access_level="edit",
            can_view=True,
            can_edit=True,
            can_share=True,
            can_manage=True,
        )
    container_access_level, container_can_manage = _container_access_level(db, whiteboard, user)
    return WhiteboardAccess(
        access_level=container_access_level,
        can_view=container_access_level in TEAM_ACCESS_LEVEL_RANK,
        can_edit=container_access_level == "edit",
        can_share=container_can_manage,
        can_manage=container_can_manage,
    )


def _whiteboard_query() -> select[tuple[Whiteboard]]:
    return (
        select(Whiteboard)
        .options(
            selectinload(Whiteboard.owner),
            selectinload(Whiteboard.containers),
        )
    )


def _load_accessible_whiteboards(db: Session, user: User) -> list[Whiteboard]:
    current_workspace = get_current_workspace(db)
    if current_workspace is None:
        return []
    whiteboards = list(
        db.scalars(
            _whiteboard_query().where(Whiteboard.workspace_id == current_workspace.id)
        )
    )
    return [
        whiteboard
        for whiteboard in whiteboards
        if _resolve_whiteboard_access(db, whiteboard, user).can_view
    ]


def _load_whiteboard_for_access(db: Session, whiteboard_id: str) -> Whiteboard | None:
    current_workspace = get_current_workspace(db)
    query = _whiteboard_query().where(Whiteboard.id == whiteboard_id)
    if current_workspace is not None:
        query = query.where(Whiteboard.workspace_id == current_workspace.id)
    return db.scalar(query)


def _get_pref_map(db: Session, user_id: str) -> dict[str, WhiteboardUserItemPref]:
    rows = list(
        db.scalars(
            select(WhiteboardUserItemPref).where(WhiteboardUserItemPref.user_id == user_id)
        )
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
) -> WhiteboardHubItem:
    workspace = _workspace_for_whiteboard(db, whiteboard)
    primary_container = _primary_container(whiteboard)
    location_label = resolve_container_label(
        db=db,
        workspace=workspace,
        container=primary_container,
    )
    source_badge, source_deeplink = describe_source(
        workspace=workspace,
        whiteboard=whiteboard,
        primary_container=primary_container,
    )
    return WhiteboardHubItem(
        id=whiteboard.id,
        source_app=whiteboard.source_app,
        source_id=whiteboard.id,
        source_kind=whiteboard.source_kind,
        source_ref=whiteboard.source_ref,
        generation_kind=whiteboard.generation_kind,
        location_label=location_label,
        container_label=location_label,
        primary_container=_serialize_primary_container(primary_container),
        source_badge=source_badge,
        source_deeplink=source_deeplink,
        title=whiteboard.title,
        created_by_id=whiteboard.owner_id,
        created_by_name=getattr(whiteboard.owner, "full_name", ""),
        created_at=whiteboard.created_at,
        updated_at=whiteboard.updated_at,
        trashed_at=whiteboard.trashed_at,
        is_favorite=bool(pref and pref.is_favorite),
        is_private=primary_container is None,
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
) -> WhiteboardDetail:
    item = _serialize_whiteboard_item(db, whiteboard, access, pref)
    return WhiteboardDetail(
        **item.model_dump(),
        scene=whiteboard.scene or empty_scene(),
    )


def _whiteboard_from_item_or_404(
    db: Session,
    item_id: str,
    current_user: User,
) -> tuple[Whiteboard, WhiteboardAccess]:
    whiteboard = _load_whiteboard_for_access(db, item_id)
    if whiteboard is None:
        raise HTTPException(status_code=404, detail="Whiteboard not found.")
    access = _resolve_whiteboard_access(db, whiteboard, current_user)
    if not access.can_view or (whiteboard.trashed_at is not None and not access.can_manage):
        raise HTTPException(status_code=404, detail="Whiteboard not found.")
    return whiteboard, access


def _lookup_item(db: Session, item_id: str, current_user: User) -> WhiteboardDetail:
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    return _serialize_whiteboard_detail(
        db,
        whiteboard,
        access,
        _get_pref_map(db, current_user.id).get(whiteboard.id),
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
            item
            for item in filtered
            if item.trashed_at is None and item.last_viewed_at is not None
        ]
    elif query.view == "archived":
        filtered = [item for item in filtered if item.trashed_at is not None]
    else:
        filtered = [item for item in filtered if item.trashed_at is None]

    if query.source_app:
        filtered = [item for item in filtered if item.source_app == query.source_app]
    if query.source_kind:
        filtered = [item for item in filtered if item.source_kind == query.source_kind]
    if query.container_app:
        filtered = [
            item
            for item in filtered
            if item.primary_container is not None and item.primary_container.app == query.container_app
        ]
    if query.container_type:
        filtered = [
            item
            for item in filtered
            if item.primary_container is not None and item.primary_container.type == query.container_type
        ]
    if query.container_id:
        filtered = [
            item
            for item in filtered
            if item.primary_container is not None and item.primary_container.id == query.container_id
        ]

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
        if sort_by == "container_sort_order":
            return item.primary_container.sort_order if item.primary_container is not None else 0
        return item.updated_at

    return sorted(whiteboards, key=sort_key, reverse=reverse)


def _upsert_primary_container(
    db: Session,
    *,
    whiteboard: Whiteboard,
    payload: UpdateWhiteboardContainerRequest,
    current_user: User,
) -> WhiteboardContainer:
    workspace = _workspace_for_whiteboard(db, whiteboard)
    ref = ContainerRef(app=payload.app, type=payload.type, id=payload.id)
    if not container_write_allowed(
        db=db,
        user=current_user,
        workspace=workspace,
        ref=ref,
    ):
        raise HTTPException(status_code=403, detail="Container edit access required.")

    for container in whiteboard.containers:
        container.is_primary = False
        db.add(container)

    existing = next(
        (
            container
            for container in whiteboard.containers
            if container.container_app == payload.app
            and container.container_type == payload.type
            and container.container_id == payload.id
        ),
        None,
    )
    if existing is None:
        existing = WhiteboardContainer(
            id=new_id(),
            whiteboard_id=whiteboard.id,
            container_app=payload.app,
            container_type=payload.type,
            container_id=payload.id,
            is_primary=True,
            sort_order=payload.sort_order,
        )
        db.add(existing)
        whiteboard.containers.append(existing)
    else:
        existing.is_primary = True
        existing.sort_order = payload.sort_order
        db.add(existing)
    db.flush()
    return existing


def _delete_primary_container(db: Session, whiteboard: Whiteboard) -> None:
    for container in list(whiteboard.containers):
        if container.is_primary:
            db.delete(container)


@router.get("/hub", response_model=WhiteboardHubResponse)
def list_whiteboard_hub(
    view: Literal["all", "mine", "recent", "archived"] | None = Query(default=None),
    category: str | None = Query(default=None),
    q: str = Query(default=""),
    sort_by: str = Query(default="updated_at"),
    sort_dir: Literal["asc", "desc"] = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    source_app: str | None = Query(default=None),
    source_kind: str | None = Query(default=None),
    container_app: str | None = Query(default=None),
    container_type: str | None = Query(default=None),
    container_id: str | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardHubResponse:
    resolved_view = view or {
        "all": "all",
        "my": "mine",
        "mine": "mine",
        "recent": "recent",
        "archived": "archived",
    }.get(category or "all", "all")
    query = WhiteboardHubQuery(
        view=resolved_view,
        q=q,
        sort_by=sort_by,
        sort_dir=sort_dir,
        page=page,
        page_size=page_size,
        source_app=source_app,
        source_kind=source_kind,
        container_app=container_app,
        container_type=container_type,
        container_id=container_id,
    )
    _ensure_whiteboard_workspace_access(db, current_user)
    pref_map = _get_pref_map(db, current_user.id)
    whiteboards = [
        _serialize_whiteboard_item(
            db,
            whiteboard,
            _resolve_whiteboard_access(db, whiteboard, current_user),
            pref_map.get(whiteboard.id),
        )
        for whiteboard in _load_accessible_whiteboards(db, current_user)
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


@router.post("/items", response_model=WhiteboardDetail, status_code=status.HTTP_201_CREATED)
def create_whiteboard_item(
    payload: CreateWhiteboardRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    workspace = _ensure_whiteboard_workspace_access(db, current_user)
    container_payload = payload.primary_container
    if container_payload is not None and not container_write_allowed(
        db=db,
        user=current_user,
        workspace=workspace,
        ref=ContainerRef(
            app=container_payload.app,
            type=container_payload.type,
            id=container_payload.id,
        ),
    ):
        raise HTTPException(status_code=403, detail="Container edit access required.")

    whiteboard = create_whiteboard_for_user(
        db,
        workspace_id=workspace.id,
        owner_id=current_user.id,
        title=payload.title,
        scene=payload.scene,
        source_app=payload.source_app,
        source_kind=payload.source_kind,
        source_ref=payload.source_ref,
        generation_kind=payload.generation_kind,
        primary_container=(
            (
                container_payload.app,
                container_payload.type,
                container_payload.id,
                container_payload.sort_order,
            )
            if container_payload is not None
            else None
        ),
    )
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.get("/items/{item_id}", response_model=WhiteboardDetail)
def get_whiteboard_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    return _lookup_item(db, item_id, current_user)


@router.patch("/items/{item_id}", response_model=WhiteboardDetail)
def update_whiteboard_item(
    item_id: str,
    payload: UpdateWhiteboardRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Whiteboard edit access required.")
    if payload.title is not None:
        if not access.can_manage:
            raise HTTPException(status_code=403, detail="Whiteboard manage access required.")
        whiteboard.title = payload.title.strip()
    if "scene" in payload.model_fields_set:
        whiteboard.scene = payload.scene or empty_scene()
    whiteboard.updated_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_whiteboard_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_manage:
        raise HTTPException(status_code=403, detail="Whiteboard manage access required.")
    whiteboard.trashed_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.put("/items/{item_id}/container", response_model=WhiteboardDetail)
def update_whiteboard_container(
    item_id: str,
    payload: UpdateWhiteboardContainerRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Whiteboard edit access required.")
    _upsert_primary_container(db, whiteboard=whiteboard, payload=payload, current_user=current_user)
    whiteboard.updated_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.delete("/items/{item_id}/container", response_model=WhiteboardDetail)
def delete_whiteboard_container(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> WhiteboardDetail:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, access = _whiteboard_from_item_or_404(db, item_id, current_user)
    if not access.can_edit:
        raise HTTPException(status_code=403, detail="Whiteboard edit access required.")
    _delete_primary_container(db, whiteboard)
    whiteboard.updated_at = _utcnow()
    db.add(whiteboard)
    db.commit()
    return _lookup_item(db, whiteboard.id, current_user)


@router.patch("/items/{item_id}/favorite", response_model=ToggleFavoriteResponse)
def toggle_whiteboard_favorite(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ToggleFavoriteResponse:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, _access = _whiteboard_from_item_or_404(db, item_id, current_user)
    pref = _get_or_create_pref(db, current_user.id, whiteboard.id)
    pref.is_favorite = not pref.is_favorite
    db.add(pref)
    db.commit()
    return ToggleFavoriteResponse(is_favorite=pref.is_favorite)


@router.post("/items/{item_id}/view", status_code=status.HTTP_204_NO_CONTENT)
def record_whiteboard_view(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    _ensure_whiteboard_workspace_access(db, current_user)
    whiteboard, _access = _whiteboard_from_item_or_404(db, item_id, current_user)
    pref = _get_or_create_pref(db, current_user.id, whiteboard.id)
    pref.last_viewed_at = _utcnow()
    db.add(pref)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)

