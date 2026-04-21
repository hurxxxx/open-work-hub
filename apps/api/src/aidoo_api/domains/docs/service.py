from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import HTTPException, status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.auth.access import bind_current_workspace, get_current_workspace
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.collab import sync_collab_record_from_rest_patch
from aidoo_api.domains.docs.models import (
    DocMeetingAccess,
    NativeDoc,
    NativeDocContainer,
    NativeDocLinkShare,
    NativeDocPage,
)
from aidoo_api.domains.docs.registry import ContainerRef, project_container_access
from aidoo_api.domains.media.router import sync_embedded_media


TEAM_ACCESS_LEVEL_RANK = {
    "read": 10,
    "edit": 20,
}


def create_native_doc_for_user(
    db: Session,
    *,
    workspace_id: str,
    owner_id: str,
    title: str,
    first_page_title: str | None = None,
    content_blocks: list[dict] | None = None,
    source_app: str = "docs",
    source_kind: str = "manual",
    source_ref: str | None = None,
    generation_kind: str = "human",
    primary_container: tuple[str, str, str, int] | None = None,
) -> tuple[NativeDoc, NativeDocPage]:
    doc = NativeDoc(
        id=new_id(),
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=title.strip(),
        source_app=source_app,
        source_kind=source_kind,
        source_ref=source_ref,
        generation_kind=generation_kind,
    )
    db.add(doc)
    page = NativeDocPage(
        id=new_id(),
        doc_id=doc.id,
        parent_id=None,
        title=(first_page_title or title).strip(),
        content_blocks=content_blocks or [],
        sort_order=0,
        created_by_id=owner_id,
    )
    db.add(page)
    if primary_container is not None:
        container_app, container_type, container_id, sort_order = primary_container
        db.add(
            NativeDocContainer(
                id=new_id(),
                doc_id=doc.id,
                container_app=container_app,
                container_type=container_type,
                container_id=container_id,
                is_primary=True,
                sort_order=sort_order,
            )
        )
    db.flush()
    return doc, page


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _split_prefixed_id(value: str) -> tuple[str | None, str]:
    if "__" not in value:
        return None, value
    prefix, raw_id = value.split("__", 1)
    return prefix, raw_id


def _normalize_doc_id(value: str) -> str:
    prefix, raw_id = _split_prefixed_id(value)
    if prefix not in {None, "native_doc"}:
        raise HTTPException(status_code=404, detail="Doc not found.")
    return raw_id


def _normalize_page_id(value: str) -> str:
    prefix, raw_id = _split_prefixed_id(value)
    if prefix not in {None, "native_doc_page"}:
        raise HTTPException(status_code=404, detail="Page not found.")
    return raw_id


def _max_access_level(*levels: str | None) -> str | None:
    ranked = [level for level in levels if level in TEAM_ACCESS_LEVEL_RANK]
    if not ranked:
        return None
    return max(ranked, key=lambda item: TEAM_ACCESS_LEVEL_RANK[item])


@dataclass
class NativeAccess:
    access_level: str | None
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool
    matched_link: NativeDocLinkShare | None


def _bind_workspace_context(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
) -> None:
    bind_current_workspace(db, workspace)
    if principal.workspace_id != workspace.id:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Docs principal workspace mismatch.",
        )
    if principal.kind == "user" and principal.user_id not in {None, user.id}:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Docs principal user mismatch.",
        )


def _require_user_write_principal(principal: CallerPrincipal) -> None:
    if principal.kind != "user":
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Docs write operations require a user principal.",
        )


def _paragraph_block(text: str) -> dict[str, Any]:
    return {
        "type": "paragraph",
        "content": [{"type": "text", "text": text}],
    }


def _heading_block(text: str, *, level: int) -> dict[str, Any]:
    return {
        "type": "heading",
        "props": {"level": level},
        "content": [{"type": "text", "text": text}],
    }


def _markdown_to_blocks(content_markdown: str | None) -> list[dict[str, Any]] | None:
    if content_markdown is None:
        return None
    lines = [line.rstrip() for line in content_markdown.splitlines()]
    blocks: list[dict[str, Any]] = []
    for raw_line in lines:
        line = raw_line.strip()
        if not line:
            continue
        if line.startswith("### "):
            blocks.append(_heading_block(line[4:].strip(), level=3))
            continue
        if line.startswith("## "):
            blocks.append(_heading_block(line[3:].strip(), level=2))
            continue
        if line.startswith("# "):
            blocks.append(_heading_block(line[2:].strip(), level=1))
            continue
        blocks.append(_paragraph_block(line))
    return blocks


def _workspace_for_doc(db: Session, doc: NativeDoc) -> Workspace:
    current_workspace = get_current_workspace(db)
    if current_workspace is not None and current_workspace.id == doc.workspace_id:
        return current_workspace
    workspace = db.scalar(
        select(Workspace).where(
            Workspace.id == doc.workspace_id,
            Workspace.active.is_(True),
        )
    )
    if workspace is None:
        raise HTTPException(status_code=404, detail="Workspace not found.")
    return workspace


def _container_access_level(
    db: Session,
    doc: NativeDoc,
    user: User,
) -> tuple[str | None, bool]:
    workspace = _workspace_for_doc(db, doc)
    best_level: str | None = None
    can_manage = False
    for container in doc.containers:
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


def _resolve_native_doc_access(
    db: Session,
    doc: NativeDoc,
    user: User,
    *,
    share_token: str | None = None,
) -> NativeAccess:
    if doc.owner_id == user.id:
        link_match = next((item for item in doc.link_shares if item.active), None)
        return NativeAccess(
            access_level="edit",
            can_view=True,
            can_edit=True,
            can_share=True,
            can_manage=True,
            matched_link=link_match,
        )

    direct_share = next((item for item in doc.user_shares if item.user_id == user.id), None)
    matched_link = next(
        (
            item
            for item in doc.link_shares
            if item.active and share_token and item.token == share_token
        ),
        None,
    )
    meeting_grant = db.scalar(
        select(DocMeetingAccess).where(
            DocMeetingAccess.doc_id == doc.id,
            DocMeetingAccess.user_id == user.id,
            DocMeetingAccess.revoked_at.is_(None),
            (
                DocMeetingAccess.expires_at.is_(None)
                | (DocMeetingAccess.expires_at > _utcnow())
            ),
        )
    )
    container_access_level, container_can_manage = _container_access_level(db, doc, user)
    access_level = _max_access_level(
        getattr(direct_share, "access_level", None),
        getattr(matched_link, "access_level", None),
        getattr(meeting_grant, "access_level", None),
        container_access_level,
    )
    return NativeAccess(
        access_level=access_level,
        can_view=access_level in TEAM_ACCESS_LEVEL_RANK,
        can_edit=access_level == "edit",
        can_share=container_can_manage,
        can_manage=container_can_manage,
        matched_link=matched_link,
    )


def _doc_query():
    return (
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages).selectinload(NativeDocPage.created_by),
            selectinload(NativeDoc.user_shares),
            selectinload(NativeDoc.link_shares),
            selectinload(NativeDoc.containers),
        )
    )


def _load_native_doc_for_access(
    db: Session,
    doc_id: str,
) -> NativeDoc | None:
    current_workspace = get_current_workspace(db)
    query = _doc_query().where(NativeDoc.id == doc_id)
    if current_workspace is not None:
        query = query.where(NativeDoc.workspace_id == current_workspace.id)
    return db.scalar(query)


def _load_native_page(db: Session, page_id: str) -> NativeDocPage | None:
    return db.scalar(
        select(NativeDocPage)
        .options(selectinload(NativeDocPage.created_by), joinedload(NativeDocPage.doc))
        .where(NativeDocPage.id == page_id)
    )


def _serialize_native_page(
    page: NativeDocPage,
    *,
    can_edit: bool,
) -> dict[str, Any]:
    return {
        "id": page.id,
        "doc_id": page.doc_id,
        "source_type": "native_doc_page",
        "source_page_id": page.id,
        "parent_id": page.parent_id,
        "title": page.title,
        "content_blocks": page.content_blocks,
        "sort_order": page.sort_order,
        "created_by_id": page.created_by_id,
        "created_by_name": getattr(page.created_by, "full_name", ""),
        "created_at": page.created_at,
        "updated_at": page.updated_at,
        "trashed_at": page.trashed_at,
        "can_edit": can_edit,
        "realtime_collab": True,
    }


def _validate_native_parent(
    doc: NativeDoc,
    parent_id: str | None,
    *,
    page_id: str | None = None,
) -> None:
    if parent_id is None:
        return
    active_pages = {
        page.id: page
        for page in doc.pages
        if page.trashed_at is None
    }
    parent = active_pages.get(parent_id)
    if parent is None:
        raise HTTPException(status_code=404, detail="Parent page not found.")
    if page_id is not None and parent.id == page_id:
        raise HTTPException(status_code=409, detail="Page cannot be its own parent.")

    ancestor = parent
    visited: set[str] = set()
    while ancestor is not None:
        if ancestor.id in visited:
            raise HTTPException(
                status_code=409,
                detail="Page parent relationship cannot contain a cycle.",
            )
        visited.add(ancestor.id)
        if page_id is not None and ancestor.parent_id == page_id:
            raise HTTPException(
                status_code=409,
                detail="Page parent relationship cannot contain a cycle.",
            )
        if ancestor.parent_id is None:
            break
        ancestor = active_pages.get(ancestor.parent_id)


def _native_doc_from_item_or_404(
    db: Session,
    item_id: str,
    current_user: User,
    *,
    share_token: str | None,
) -> tuple[NativeDoc, NativeAccess]:
    doc = _load_native_doc_for_access(db, _normalize_doc_id(item_id))
    if doc is None:
        raise HTTPException(status_code=404, detail="Doc not found.")
    access = _resolve_native_doc_access(db, doc, current_user, share_token=share_token)
    if not access.can_view or (doc.trashed_at is not None and not access.can_manage):
        raise HTTPException(status_code=404, detail="Doc not found.")
    return doc, access


def _router():
    from aidoo_api.domains.docs import router as docs_router

    return docs_router


def create_page(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    hub_id: str,
    title: str,
    content_markdown: str | None = None,
    parent_id: str | None = None,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    _require_user_write_principal(principal)
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)

    if approved_call_id is not None:
        existing_page = _load_native_page(db, approved_call_id)
        if existing_page is not None and existing_page.doc is not None:
            existing_doc = _load_native_doc_for_access(db, existing_page.doc_id)
            if existing_doc is not None:
                access = _resolve_native_doc_access(db, existing_doc, user, share_token=None)
                if access.can_view:
                    return _serialize_native_page(
                        existing_page,
                        can_edit=access.can_edit,
                    )

    doc, access = _native_doc_from_item_or_404(
        db,
        hub_id,
        user,
        share_token=None,
    )
    if not access.can_edit:
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Doc edit access required.")

    normalized_parent_id = _normalize_page_id(parent_id) if parent_id else None
    _validate_native_parent(doc, normalized_parent_id)
    sibling_count = len(
        [
            page
            for page in doc.pages
            if page.trashed_at is None and page.parent_id == normalized_parent_id
        ]
    )
    content_blocks = _markdown_to_blocks(content_markdown)
    page = NativeDocPage(
        id=approved_call_id or new_id(),
        doc_id=doc.id,
        parent_id=normalized_parent_id,
        title=title.strip(),
        content_blocks=content_blocks,
        sort_order=sibling_count,
        created_by_id=user.id,
    )
    db.add(page)
    db.flush()
    if content_blocks is not None:
        sync_embedded_media(db, content_blocks, "docs_native_page", page.id, user)
        sync_collab_record_from_rest_patch(
            db,
            source_type="native_doc_page",
            source_page_id=page.id,
            snapshot_content_blocks=content_blocks,
        )
    db.commit()
    page = _load_native_page(db, page.id)
    assert page is not None
    return _serialize_native_page(page, can_edit=access.can_edit)


def list_hub(
    db: Session,
    *,
    user,
    view: str = "all",
    q: str = "",
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 50,
    source_app: str | None = None,
    source_kind: str | None = None,
    container_app: str | None = None,
    container_type: str | None = None,
    container_id: str | None = None,
) -> dict[str, Any]:
    helpers = _router()
    query = helpers.DocsHubQuery(
        view=view,
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
    return helpers.list_hub_internal(db, user=user, query=query).model_dump()


def get_item(
    db: Session,
    *,
    user,
    item_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    helpers = _router()
    return helpers.get_item_internal(
        db,
        user=user,
        item_id=item_id,
        share_token=share_token,
    ).model_dump()


def list_pages(
    db: Session,
    *,
    user,
    item_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    helpers = _router()
    return helpers.list_pages_internal(
        db,
        user=user,
        item_id=item_id,
        share_token=share_token,
    ).model_dump()


def read_page(
    db: Session,
    *,
    user,
    page_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    helpers = _router()
    return helpers.read_page_internal(
        db,
        user=user,
        page_id=page_id,
        share_token=share_token,
    ).model_dump()
