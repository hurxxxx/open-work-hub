from __future__ import annotations

from typing import Any, Literal, Protocol

from open_work_hub_api.domains.docs.models import (
    DocsCollection,
    NativeDoc,
    NativeDocPage,
    NativeDocTarget,
)

SOURCE_NATIVE_DOC = "native_doc"
PAGE_SOURCE_NATIVE_DOC = "native_doc_page"
DOC_CONTENT_FORMAT_VALUES = {"block", "html"}
DocsHubContentFormat = Literal["block", "html", "mixed"]


class NativeAccessLike(Protocol):
    can_view: bool
    can_edit: bool
    can_share: bool
    can_manage: bool


class DocsUserItemPrefLike(Protocol):
    is_favorite: bool
    last_viewed_at: Any


class UserLike(Protocol):
    id: str


def select_primary_target(doc: NativeDoc) -> NativeDocTarget | None:
    active = list(doc.targets)
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


def serialize_primary_target(
    target: NativeDocTarget | None,
) -> dict[str, Any] | None:
    if target is None:
        return None
    return {
        "app": target.target_app,
        "type": target.target_type,
        "id": target.target_id,
        "sort_order": target.sort_order,
    }


def serialize_collection_summary(
    collection: DocsCollection | None,
) -> dict[str, Any] | None:
    if collection is None:
        return None
    return {
        "id": collection.id,
        "name": collection.name,
        "scope": collection.scope,
    }


def collection_visible_to_user(collection: DocsCollection | None, user: UserLike) -> bool:
    if collection is None:
        return False
    return collection.scope == "company" or collection.owner_id == user.id


def serialize_native_share_summary(doc: NativeDoc) -> dict[str, Any]:
    active_link = next((item for item in doc.link_shares if item.active), None)
    user_share_count = len(doc.user_shares)
    primary_target = select_primary_target(doc)
    is_target_shared = primary_target is not None
    is_meeting_note = doc.source_app == "meeting" and doc.source_kind == "meeting_notes"
    return {
        "visibility": (
            "shared"
            if doc.ownership_kind == "company"
            or doc.company_visible
            or user_share_count > 0
            or doc.group_shares
            or active_link is not None
            or is_target_shared
            or is_meeting_note
            else "private"
        ),
        "user_share_count": user_share_count,
        "link_active": active_link is not None,
        "link_access_level": active_link.access_level if active_link is not None else None,
    }


def resolve_doc_content_format_summary(doc: NativeDoc) -> DocsHubContentFormat:
    formats = {
        page.content_format
        for page in doc.pages
        if page.trashed_at is None and page.content_format in DOC_CONTENT_FORMAT_VALUES
    }
    if not formats:
        return "block"
    if len(formats) == 1:
        return "html" if "html" in formats else "block"
    return "mixed"


def serialize_native_hub_item(
    *,
    doc: NativeDoc,
    user: UserLike,
    access: NativeAccessLike,
    pref: DocsUserItemPrefLike | None,
    location_label: str,
    source_badge: str,
    source_deeplink: str | None,
    primary_target: NativeDocTarget | None,
    include_rag_scope: bool = False,
) -> dict[str, Any]:
    active_pages = [page for page in doc.pages if page.trashed_at is None]
    sharing_summary = serialize_native_share_summary(doc)
    item = {
        "id": doc.id,
        "ownership_kind": doc.ownership_kind,
        "company_visible": doc.company_visible,
        "source_app": doc.source_app,
        "source_type": SOURCE_NATIVE_DOC,
        "source_id": doc.id,
        "source_kind": doc.source_kind,
        "source_ref": doc.source_ref,
        "generation_kind": doc.generation_kind,
        "doc_type": doc.doc_type,
        "content_format": resolve_doc_content_format_summary(doc),
        "structure_kind": "page_tree",
        "location_label": location_label,
        "target_label": location_label,
        "collection": (
            serialize_collection_summary(doc.collection)
            if collection_visible_to_user(doc.collection, user)
            else None
        ),
        "primary_target": serialize_primary_target(primary_target),
        "source_badge": source_badge,
        "source_deeplink": source_deeplink,
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
    if include_rag_scope:
        item["rag_scope"] = doc.rag_scope
    return item


def serialize_native_page(
    page: NativeDocPage,
    *,
    can_edit: bool,
) -> dict[str, Any]:
    return {
        "id": page.id,
        "doc_id": page.doc_id,
        "source_type": PAGE_SOURCE_NATIVE_DOC,
        "source_page_id": page.id,
        "parent_id": page.parent_id,
        "title": page.title,
        "content_blocks": page.content_blocks,
        "content_text": page.content_text,
        "sort_order": page.sort_order,
        "created_by_id": page.created_by_id,
        "created_by_name": getattr(page.created_by, "full_name", ""),
        "created_at": page.created_at,
        "updated_at": page.updated_at,
        "trashed_at": page.trashed_at,
        "can_edit": can_edit,
        "content_format": page.content_format,
        "realtime_collab": page.content_format == "block",
    }
