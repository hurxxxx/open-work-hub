from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload, selectinload

from aidoo_api.core.i18n import localized_http_exception
from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.auth.access import bind_current_workspace, get_current_workspace, resolve_workspaces
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.collab import sync_collab_record_from_rest_patch
from aidoo_api.domains.docs.models import (
    DocMeetingAccess,
    DocsUserItemPref,
    NativeDoc,
    NativeDocContainer,
    NativeDocLinkShare,
    NativeDocPage,
)
from aidoo_api.domains.docs.rag_sync import enqueue_native_doc_rag_sync
from aidoo_api.domains.docs.registry import (
    ContainerRef,
    describe_source,
    project_container_access,
    resolve_container_label,
)
from aidoo_api.domains.media.service import sync_embedded_media
from aidoo_api.domains.rag.contracts import RagSyncOperation


TEAM_ACCESS_LEVEL_RANK = {
    "read": 10,
    "edit": 20,
}
SOURCE_NATIVE_DOC = "native_doc"
PAGE_SOURCE_NATIVE_DOC = "native_doc_page"


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
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
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
        raise localized_http_exception(status_code=404, code="docs.doc_not_found")
    return raw_id


def _normalize_page_id(value: str) -> str:
    prefix, raw_id = _split_prefixed_id(value)
    if prefix not in {None, "native_doc_page"}:
        raise localized_http_exception(status_code=404, code="docs.page_not_found")
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
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="docs.principal_workspace_mismatch",
        )
    if principal.kind == "user" and principal.user_id not in {None, user.id}:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="docs.principal_user_mismatch",
        )


def _require_user_write_principal(principal: CallerPrincipal) -> None:
    if principal.kind != "user":
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="docs.write_user_principal_required",
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
        raise localized_http_exception(status_code=404, code="workspace.not_found")
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


def can_read_native_doc_for_rag(
    db: Session,
    *,
    user: User,
    doc_id: str,
) -> bool:
    doc = _load_native_doc_for_access(db, doc_id)
    if doc is None:
        return False
    return _resolve_native_doc_access(db, doc, user).can_view


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
        raise localized_http_exception(status_code=404, code="docs.parent_page_not_found")
    if page_id is not None and parent.id == page_id:
        raise localized_http_exception(status_code=409, code="docs.page_cannot_be_own_parent")

    ancestor = parent
    visited: set[str] = set()
    while ancestor is not None:
        if ancestor.id in visited:
            raise localized_http_exception(
                status_code=409,
                code="docs.page_parent_cycle",
            )
        visited.add(ancestor.id)
        if page_id is not None and ancestor.parent_id == page_id:
            raise localized_http_exception(
                status_code=409,
                code="docs.page_parent_cycle",
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
        raise localized_http_exception(status_code=404, code="docs.doc_not_found")
    access = _resolve_native_doc_access(db, doc, current_user, share_token=share_token)
    if not access.can_view or (doc.trashed_at is not None and not access.can_manage):
        raise localized_http_exception(status_code=404, code="docs.doc_not_found")
    return doc, access


def _share_token_allows_item_without_docs_access(item_id: str) -> bool:
    prefix, _raw_id = _split_prefixed_id(item_id)
    return prefix in {None, SOURCE_NATIVE_DOC}


def _share_token_allows_page_without_docs_access(page_id: str) -> bool:
    prefix, _raw_id = _split_prefixed_id(page_id)
    return prefix in {None, PAGE_SOURCE_NATIVE_DOC}


def _ensure_docs_workspace_access(db: Session, user: User) -> Workspace:
    current_workspace = get_current_workspace(db)
    if current_workspace is not None:
        return current_workspace

    for summary in resolve_workspaces(db, user):
        workspace = db.scalar(
            select(Workspace).where(
                Workspace.id == summary["id"],
                Workspace.active.is_(True),
            )
        )
        if workspace is None:
            continue
        bind_current_workspace(db, workspace)
        return workspace

    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="docs.requests_workspace_context_required",
    )


def _primary_container(doc: NativeDoc) -> NativeDocContainer | None:
    active = list(doc.containers)
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


def _load_accessible_native_docs(db: Session, user: User) -> list[NativeDoc]:
    current_workspace = get_current_workspace(db)
    if current_workspace is None:
        return []
    docs = list(db.scalars(_doc_query().where(NativeDoc.workspace_id == current_workspace.id)))
    return [doc for doc in docs if _resolve_native_doc_access(db, doc, user).can_view]


def _get_pref_map(
    db: Session,
    user_id: str,
) -> dict[tuple[str, str], DocsUserItemPref]:
    rows = list(
        db.scalars(
            select(DocsUserItemPref).where(DocsUserItemPref.user_id == user_id)
        )
    )
    return {(row.source_type, row.source_doc_id): row for row in rows}


def _serialize_primary_container(container: NativeDocContainer | None) -> dict[str, Any] | None:
    if container is None:
        return None
    return {
        "app": container.container_app,
        "type": container.container_type,
        "id": container.container_id,
        "sort_order": container.sort_order,
    }


def _serialize_native_share_summary(doc: NativeDoc) -> dict[str, Any]:
    active_link = next((item for item in doc.link_shares if item.active), None)
    user_share_count = len(doc.user_shares)
    primary_container = _primary_container(doc)
    is_container_shared = primary_container is not None
    is_meeting_note = doc.source_app == "meeting" and doc.source_kind == "meeting_notes"
    return {
        "visibility": (
            "shared"
            if user_share_count > 0
            or active_link is not None
            or is_container_shared
            or is_meeting_note
            else "private"
        ),
        "user_share_count": user_share_count,
        "link_active": active_link is not None,
        "link_access_level": active_link.access_level if active_link is not None else None,
    }


def _serialize_native_item(
    db: Session,
    doc: NativeDoc,
    access: NativeAccess,
    pref: DocsUserItemPref | None,
) -> dict[str, Any]:
    workspace = _workspace_for_doc(db, doc)
    primary_container = _primary_container(doc)
    location_label = resolve_container_label(
        db=db,
        workspace=workspace,
        container=primary_container,
    )
    source = describe_source(
        workspace=workspace,
        doc=doc,
        primary_container=primary_container,
    )
    active_pages = [page for page in doc.pages if page.trashed_at is None]
    sharing_summary = _serialize_native_share_summary(doc)
    return {
        "id": doc.id,
        "source_app": doc.source_app,
        "source_type": SOURCE_NATIVE_DOC,
        "source_id": doc.id,
        "source_kind": doc.source_kind,
        "source_ref": doc.source_ref,
        "generation_kind": doc.generation_kind,
        "structure_kind": "page_tree",
        "location_label": location_label,
        "container_label": location_label,
        "primary_container": _serialize_primary_container(primary_container),
        "source_badge": source.badge,
        "source_deeplink": source.deep_link,
        "title": doc.title,
        "page_count": len(active_pages),
        "created_by_id": doc.owner_id,
        "created_by_name": getattr(doc.owner, "full_name", ""),
        "created_at": doc.created_at,
        "updated_at": doc.updated_at,
        "trashed_at": doc.trashed_at,
        "is_favorite": bool(pref and pref.is_favorite),
        "is_private": sharing_summary["visibility"] == "private",
        "last_viewed_at": pref.last_viewed_at if pref else None,
        "can_view": access.can_view,
        "can_edit": access.can_edit,
        "can_share": access.can_share,
        "can_manage": access.can_manage,
        "sharing_summary": sharing_summary,
    }


def _lookup_item(
    db: Session,
    item_id: str,
    current_user: User,
    *,
    share_token: str | None = None,
) -> dict[str, Any]:
    doc, access = _native_doc_from_item_or_404(
        db,
        item_id,
        current_user,
        share_token=share_token,
    )
    pref_map = _get_pref_map(db, current_user.id)
    return _serialize_native_item(
        db,
        doc,
        access,
        pref_map.get((SOURCE_NATIVE_DOC, doc.id)),
    )


def _filter_docs(
    docs: list[dict[str, Any]],
    *,
    current_user_id: str,
    query: dict[str, Any],
) -> list[dict[str, Any]]:
    filtered = docs
    view = query["view"]
    if view == "mine":
        filtered = [
            item
            for item in filtered
            if item["trashed_at"] is None and item["created_by_id"] == current_user_id
        ]
    elif view == "shared":
        filtered = [
            item
            for item in filtered
            if item["trashed_at"] is None and item["created_by_id"] != current_user_id
        ]
    elif view == "private":
        filtered = [
            item
            for item in filtered
            if item["trashed_at"] is None
            and item["created_by_id"] == current_user_id
            and item["is_private"]
        ]
    elif view == "meeting_notes":
        filtered = [
            item
            for item in filtered
            if item["trashed_at"] is None
            and item["source_app"] == "meeting"
            and item["source_kind"] == "meeting_notes"
        ]
    elif view == "recent":
        filtered = [
            item
            for item in filtered
            if item["trashed_at"] is None and item["last_viewed_at"] is not None
        ]
    elif view == "archived":
        filtered = [item for item in filtered if item["trashed_at"] is not None]
    else:
        filtered = [item for item in filtered if item["trashed_at"] is None]

    for key in ("source_app", "source_kind"):
        if query[key]:
            filtered = [item for item in filtered if item[key] == query[key]]

    for query_key, container_key in (
        ("container_app", "app"),
        ("container_type", "type"),
        ("container_id", "id"),
    ):
        if query[query_key]:
            filtered = [
                item
                for item in filtered
                if item["primary_container"] is not None
                and item["primary_container"][container_key] == query[query_key]
            ]

    search = query["q"].strip().lower()
    if search:
        filtered = [
            item
            for item in filtered
            if search in item["title"].lower()
            or search in item["location_label"].lower()
            or search in item["source_badge"].lower()
        ]
    return filtered


def _sort_docs(
    docs: list[dict[str, Any]],
    *,
    sort_by: str,
    sort_dir: str,
) -> list[dict[str, Any]]:
    reverse = sort_dir != "asc"

    def sort_key(item: dict[str, Any]):
        if sort_by == "title":
            return item["title"].lower()
        if sort_by == "created_at":
            return item["created_at"]
        if sort_by == "last_viewed_at":
            return item["last_viewed_at"] or datetime.min
        if sort_by == "container_sort_order":
            return item["primary_container"]["sort_order"] if item["primary_container"] else 0
        return item["updated_at"]

    return sorted(docs, key=sort_key, reverse=reverse)


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
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="docs.doc_edit_access_required",
        )

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
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
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
    _ensure_docs_workspace_access(db, user)
    query = {
        "view": view,
        "q": q,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "page": page,
        "page_size": page_size,
        "source_app": source_app,
        "source_kind": source_kind,
        "container_app": container_app,
        "container_type": container_type,
        "container_id": container_id,
    }
    pref_map = _get_pref_map(db, user.id)
    docs = [
        _serialize_native_item(
            db,
            doc,
            _resolve_native_doc_access(db, doc, user),
            pref_map.get((SOURCE_NATIVE_DOC, doc.id)),
        )
        for doc in _load_accessible_native_docs(db, user)
    ]
    docs = _filter_docs(docs, current_user_id=user.id, query=query)
    docs = _sort_docs(docs, sort_by=sort_by, sort_dir=sort_dir)
    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": docs[start:end],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_item(
    db: Session,
    *,
    user,
    item_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, user)
    return _lookup_item(db, item_id, user, share_token=share_token)


def list_pages(
    db: Session,
    *,
    user,
    item_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    if share_token is None or not _share_token_allows_item_without_docs_access(item_id):
        _ensure_docs_workspace_access(db, user)
    doc, access = _native_doc_from_item_or_404(db, item_id, user, share_token=share_token)
    pages = [
        _serialize_native_page(page, can_edit=access.can_edit)
        for page in sorted(
            [page for page in doc.pages if page.trashed_at is None],
            key=lambda page: (
                "" if page.parent_id is None else page.parent_id,
                page.sort_order,
                page.created_at,
            ),
        )
    ]
    return {"items": pages}


def read_page(
    db: Session,
    *,
    user,
    page_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    if share_token is None or not _share_token_allows_page_without_docs_access(page_id):
        _ensure_docs_workspace_access(db, user)
    page = _load_native_page(db, _normalize_page_id(page_id))
    if page is None or page.doc is None:
        raise localized_http_exception(status_code=404, code="docs.page_not_found")
    doc = _load_native_doc_for_access(db, page.doc_id)
    if doc is None:
        raise localized_http_exception(status_code=404, code="docs.page_not_found")
    access = _resolve_native_doc_access(db, doc, user, share_token=share_token)
    if not access.can_view or page.trashed_at is not None or doc.trashed_at is not None:
        raise localized_http_exception(status_code=403, code="docs.page_access_required")
    return _serialize_native_page(page, can_edit=access.can_edit)
