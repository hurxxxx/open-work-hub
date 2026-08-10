from __future__ import annotations

from datetime import datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.core.principal import CallerPrincipal
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.auth.security import new_id
from open_alm_api.domains.docs.access_context import (
    SOURCE_NATIVE_DOC,
    NativeAccess,
    ensure_docs_workspace_access as _ensure_docs_workspace_access,
    ensure_workspace_for_item_request as _ensure_workspace_for_item_request,
    ensure_workspace_for_page_request as _ensure_workspace_for_page_request,
    load_accessible_native_docs as _load_accessible_native_docs,
    native_doc_from_item_or_404 as _native_doc_from_item_or_404,
    native_page_context_from_page_or_404 as _native_page_context_from_page_or_404,
    primary_target as _primary_target,
    resolve_native_doc_access as _resolve_native_doc_access,
    workspace_for_doc as _workspace_for_doc,
)
from open_alm_api.domains.docs.hub_projection import (
    serialize_native_hub_item,
    serialize_native_page,
)
from open_alm_api.domains.docs.models import (
    DocsUserItemPref,
    NativeDoc,
    NativeDocTarget,
    NativeDocPage,
)
from open_alm_api.domains.docs.partitioning import ensure_native_doc_partition
from open_alm_api.domains.docs.rag_sync import enqueue_native_doc_rag_sync
from open_alm_api.domains.docs.registry import describe_source
from open_alm_api.domains.pms.models import Task, TaskDocLink, TaskList
from open_alm_api.domains.rag.contracts import RagSyncOperation
from open_alm_api.domains.rag.source_registry import RAG_SCOPE_OFFICIAL, RAG_SCOPE_VALUES
from open_alm_api.domains.source_access import can_read_native_doc
from open_alm_api.domains.source_access.targets import resolve_target_label
from open_alm_api.domains.source_access.policy import SourceAclPolicy


DOC_TYPE_VALUES = {
    "general",
    "meeting_notes",
    "project_brief",
    "spec",
    "policy",
    "guide",
    "memo",
}
DOC_CONTENT_FORMAT_VALUES = {"block", "html"}


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
    rag_scope: str = RAG_SCOPE_OFFICIAL,
    doc_type: str | None = None,
    content_format: str = "block",
    content_text: str | None = None,
    primary_target: tuple[str, str, str, int] | None = None,
) -> tuple[NativeDoc, NativeDocPage]:
    resolved_doc_type = doc_type or _default_doc_type_for_source(source_app, source_kind)
    if resolved_doc_type not in DOC_TYPE_VALUES:
        raise ValueError(f"Unsupported docs doc_type: {resolved_doc_type}")
    if content_format not in DOC_CONTENT_FORMAT_VALUES:
        raise ValueError(f"Unsupported docs content_format: {content_format}")
    if content_format == "block" and content_text is not None:
        raise ValueError("Block docs do not accept content_text")
    if content_format != "block" and content_blocks is not None:
        raise ValueError(f"{content_format} docs do not accept content_blocks")
    if rag_scope not in RAG_SCOPE_VALUES:
        raise ValueError(f"Unsupported docs rag_scope: {rag_scope}")
    doc = NativeDoc(
        id=new_id(),
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=title.strip(),
        doc_type=resolved_doc_type,
        source_app=source_app,
        source_kind=source_kind,
        source_ref=source_ref,
        generation_kind=generation_kind,
        rag_scope=rag_scope,
    )
    ensure_native_doc_partition(db, doc=doc)
    db.add(doc)
    page = NativeDocPage(
        id=new_id(),
        doc_id=doc.id,
        parent_id=None,
        title=(first_page_title or title).strip(),
        content_format=content_format,
        content_blocks=(content_blocks or []) if content_format == "block" else None,
        content_text=content_text if content_format != "block" else None,
        sort_order=0,
        created_by_id=owner_id,
    )
    db.add(page)
    if primary_target is not None:
        target_app, target_type, target_id, sort_order = primary_target
        db.add(
            NativeDocTarget(
                id=new_id(),
                doc_id=doc.id,
                target_app=target_app,
                target_type=target_type,
                target_id=target_id,
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


def _default_doc_type_for_source(source_app: str, source_kind: str) -> str:
    if source_app == "meeting" or source_kind == "meeting_notes":
        return "meeting_notes"
    return "general"


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


def _list_item_block(block_type: str, text: str, *, checked: bool | None = None) -> dict[str, Any]:
    block: dict[str, Any] = {
        "type": block_type,
        "content": [{"type": "text", "text": text}],
    }
    if checked is not None:
        block["props"] = {"checked": checked}
    return block


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
        if line.startswith("- [ ] "):
            blocks.append(_list_item_block("checkListItem", line[6:].strip(), checked=False))
            continue
        if line.startswith("- [x] ") or line.startswith("- [X] "):
            blocks.append(_list_item_block("checkListItem", line[6:].strip(), checked=True))
            continue
        if line.startswith("- ") or line.startswith("* "):
            blocks.append(_list_item_block("bulletListItem", line[2:].strip()))
            continue
        if len(line) > 3 and line[0].isdigit() and ". " in line[:4]:
            blocks.append(_list_item_block("numberedListItem", line.split(". ", 1)[1].strip()))
            continue
        blocks.append(_paragraph_block(line))
    return blocks


def can_read_native_doc_for_rag(
    db: Session,
    *,
    user: User,
    doc_id: str,
) -> bool:
    return can_read_native_doc(db, user=user, doc_id=doc_id)


def _serialize_native_page(page: NativeDocPage, *, can_edit: bool) -> dict[str, Any]:
    return serialize_native_page(page, can_edit=can_edit)


def _get_pref_map(
    db: Session,
    user_id: str,
) -> dict[tuple[str, str], DocsUserItemPref]:
    rows = list(db.scalars(select(DocsUserItemPref).where(DocsUserItemPref.user_id == user_id)))
    return {(row.source_type, row.source_doc_id): row for row in rows}


def _serialize_native_item(
    db: Session,
    doc: NativeDoc,
    user: User,
    access: NativeAccess,
    pref: DocsUserItemPref | None,
) -> dict[str, Any]:
    workspace = _workspace_for_doc(db, doc)
    primary_target = _primary_target(doc)
    location_label = resolve_target_label(
        db=db,
        workspace=workspace,
        target=primary_target,
    )
    source = describe_source(
        workspace=workspace,
        doc=doc,
        primary_target=primary_target,
    )
    return serialize_native_hub_item(
        doc=doc,
        user=user,
        access=access,
        pref=pref,
        location_label=location_label,
        source_badge=source.badge,
        source_deeplink=source.deep_link,
        primary_target=primary_target,
    )


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
        current_user,
        access,
        pref_map.get((SOURCE_NATIVE_DOC, doc.id)),
    )


def _filter_docs(
    docs: list[dict[str, Any]],
    *,
    current_user_id: str,
    query: dict[str, Any],
    matching_space_doc_ids: set[str],
) -> list[dict[str, Any]]:
    search = query["q"].strip().lower()
    return [
        item
        for item in docs
        if _matches_doc_view(item, view=query["view"], current_user_id=current_user_id)
        and _matches_doc_source_filters(item, query)
        and _matches_doc_collection_filter(item, query["collection_id"])
        and _matches_doc_type_filter(item, query["doc_type"])
        and _matches_doc_space_filter(item, query["space_id"], matching_space_doc_ids)
        and _matches_doc_search(item, search)
    ]


def _matches_doc_view(
    item: dict[str, Any],
    *,
    view: str,
    current_user_id: str,
) -> bool:
    if view == "mine":
        return item["trashed_at"] is None and item["created_by_id"] == current_user_id
    if view == "shared":
        return item["trashed_at"] is None and item["created_by_id"] != current_user_id
    if view == "private":
        return (
            item["trashed_at"] is None
            and item["created_by_id"] == current_user_id
            and item["is_private"]
        )
    if view == "meeting_notes":
        return (
            item["trashed_at"] is None
            and item["source_app"] == "meeting"
            and item["source_kind"] == "meeting_notes"
        )
    if view == "recent":
        return item["trashed_at"] is None and item["last_viewed_at"] is not None
    if view == "archived":
        return item["trashed_at"] is not None
    return item["trashed_at"] is None


def _matches_doc_source_filters(
    item: dict[str, Any],
    query: dict[str, Any],
) -> bool:
    for key in ("source_app", "source_kind"):
        if query[key] and item[key] != query[key]:
            return False
    return True


def _matches_doc_collection_filter(
    item: dict[str, Any],
    collection_id: str | None,
) -> bool:
    if not collection_id:
        return True
    return item["collection"] is not None and item["collection"]["id"] == collection_id


def _matches_doc_type_filter(item: dict[str, Any], doc_type: str | None) -> bool:
    return not doc_type or item["doc_type"] == doc_type


def _matches_doc_space_filter(
    item: dict[str, Any],
    space_id: str | None,
    matching_space_doc_ids: set[str],
) -> bool:
    return not space_id or item["id"] in matching_space_doc_ids


def _linked_pms_space_doc_ids(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    space_id: str | None,
) -> set[str]:
    if not space_id:
        return set()

    from open_alm_api.domains.pms.source_access import accessible_pms_task_query

    policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
    accessible_task_ids = accessible_pms_task_query(policy).subquery()
    doc_ids = db.scalars(
        select(TaskDocLink.doc_id)
        .join(accessible_task_ids, TaskDocLink.task_id == accessible_task_ids.c.id)
        .join(Task, Task.id == TaskDocLink.task_id)
        .join(TaskList, TaskList.id == Task.list_id)
        .where(TaskList.team_id == space_id)
        .distinct()
    )
    return {str(doc_id) for doc_id in doc_ids if doc_id}


def _direct_space_doc_ids(db: Session, space_id: str | None) -> set[str]:
    if not space_id:
        return set()
    doc_ids = db.scalars(
        select(NativeDocTarget.doc_id)
        .where(
            NativeDocTarget.target_app == "pms",
            NativeDocTarget.target_type == "space",
            NativeDocTarget.target_id == space_id,
        )
        .distinct()
    )
    return {str(doc_id) for doc_id in doc_ids if doc_id}


def _matching_space_doc_ids(
    db: Session,
    *,
    user: User,
    workspace: Workspace,
    space_id: str | None,
) -> set[str]:
    return _direct_space_doc_ids(db, space_id) | _linked_pms_space_doc_ids(
        db,
        user=user,
        workspace=workspace,
        space_id=space_id,
    )


def _matches_doc_search(item: dict[str, Any], search: str) -> bool:
    if not search:
        return True
    return (
        search in item["title"].lower()
        or search in item["location_label"].lower()
        or search in item["source_badge"].lower()
    )


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
        if sort_by == "target_sort_order":
            return item["primary_target"]["sort_order"] if item["primary_target"] else 0
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
    from open_alm_api.domains.docs.page_mutations import create_native_page_from_markdown

    return create_native_page_from_markdown(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        hub_id=hub_id,
        title=title,
        content_markdown=content_markdown,
        parent_id=parent_id,
        approved_call_id=approved_call_id,
    )


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
    collection_id: str | None = None,
    doc_type: str | None = None,
    space_id: str | None = None,
) -> dict[str, Any]:
    workspace = _ensure_docs_workspace_access(db, user)
    query = {
        "view": view,
        "q": q,
        "sort_by": sort_by,
        "sort_dir": sort_dir,
        "page": page,
        "page_size": page_size,
        "source_app": source_app,
        "source_kind": source_kind,
        "collection_id": collection_id,
        "doc_type": doc_type,
        "space_id": space_id,
    }
    pref_map = _get_pref_map(db, user.id)
    docs = [
        _serialize_native_item(
            db,
            doc,
            user,
            _resolve_native_doc_access(db, doc, user),
            pref_map.get((SOURCE_NATIVE_DOC, doc.id)),
        )
        for doc in _load_accessible_native_docs(db, user)
    ]
    matching_space_doc_ids = _matching_space_doc_ids(
        db,
        user=user,
        workspace=workspace,
        space_id=space_id,
    )
    docs = _filter_docs(
        docs,
        current_user_id=user.id,
        query=query,
        matching_space_doc_ids=matching_space_doc_ids,
    )
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
    _ensure_workspace_for_item_request(db, user, item_id=item_id, share_token=share_token)
    return _lookup_item(db, item_id, user, share_token=share_token)


def list_pages(
    db: Session,
    *,
    user,
    item_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    _ensure_workspace_for_item_request(db, user, item_id=item_id, share_token=share_token)
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
    _ensure_workspace_for_page_request(db, user, page_id=page_id, share_token=share_token)
    context = _native_page_context_from_page_or_404(
        db,
        page_id=page_id,
        user=user,
        share_token=share_token,
        require="view",
    )
    return _serialize_native_page(context.page, can_edit=context.access.can_edit)
