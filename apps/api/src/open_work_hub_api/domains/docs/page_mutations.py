from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.docs import service as docs_service
from open_work_hub_api.domains.docs.access_context import (
    PAGE_SOURCE_NATIVE_DOC,
    NativePageContext,
    load_native_doc_for_access,
    load_native_page,
    native_doc_from_item_or_404,
    native_page_context_from_page_or_404,
    normalize_page_id,
    require_actor,
    require_user_write_principal,
    resolve_native_doc_access,
    validate_native_parent,
)
from open_work_hub_api.domains.docs.collab import (
    block_content_equal,
    delete_collab_document,
    sync_collab_record_from_rest_patch,
)
from open_work_hub_api.domains.docs.hub_projection import serialize_native_page
from open_work_hub_api.domains.docs.models import NativeDocPage
from open_work_hub_api.domains.docs.rag_sync import enqueue_native_doc_rag_sync
from open_work_hub_api.domains.docs.timestamps import touch_native_doc
from open_work_hub_api.domains.media.service import cleanup_media_for_resource, sync_embedded_media
from open_work_hub_api.domains.rag.contracts import RagSyncOperation


@dataclass(frozen=True)
class CreateNativePageCommand:
    item_id: str
    title: str
    parent_id: str | None = None
    content_format: str = "block"
    content_blocks: list[dict] | None = None
    content_blocks_present: bool = False
    content_text: str | None = None
    content_text_present: bool = False
    sort_order: int | None = None
    page_id: str | None = None


@dataclass(frozen=True)
class PageMutationResult:
    page: dict[str, Any]
    doc_id: str
    page_id: str
    created: bool
    changed: bool = True
    metadata_changed: bool = False


@dataclass(frozen=True)
class UpdateNativePageCommand:
    page_id: str
    parent_id: str | None = None
    parent_id_present: bool = False
    title: str | None = None
    content_blocks: list[dict] | None = None
    content_blocks_present: bool = False
    content_text: str | None = None
    content_text_present: bool = False
    sort_order: int | None = None


@dataclass(frozen=True)
class DeleteNativePageCommand:
    page_id: str


@dataclass(frozen=True)
class DeleteNativePageResult:
    doc_id: str
    page_id: str
    media_keys: list[str]


def create_native_page(
    db: Session,
    *,
    user: User,
    command: CreateNativePageCommand,
    principal: CallerPrincipal | None = None,
    share_token: str | None = None,
) -> PageMutationResult:
    if principal is not None:
        require_user_write_principal(principal)
        require_actor(
            db,
            principal=principal,
            user=user,
        )

    if command.page_id is not None:
        existing = _load_existing_page_for_idempotency(
            db,
            user=user,
            page_id=command.page_id,
            share_token=share_token,
        )
        if existing is not None:
            return existing

    _validate_create_page_content(command)
    doc, access = native_doc_from_item_or_404(
        db,
        command.item_id,
        user,
        share_token=share_token,
    )
    if not access.can_edit:
        raise localized_http_exception(
            status_code=403,
            code="docs.doc_edit_access_required",
        )

    parent_id = normalize_page_id(command.parent_id) if command.parent_id else None
    validate_native_parent(doc, parent_id)
    sibling_count = len(
        [page for page in doc.pages if page.trashed_at is None and page.parent_id == parent_id]
    )
    page_format = command.content_format
    page = NativeDocPage(
        id=command.page_id or new_id(),
        doc_id=doc.id,
        parent_id=parent_id,
        title=command.title.strip(),
        content_format=page_format,
        content_blocks=command.content_blocks if page_format == "block" else None,
        content_text=command.content_text if page_format != "block" else None,
        sort_order=command.sort_order if command.sort_order is not None else sibling_count,
        created_by_id=user.id,
    )
    db.add(page)
    db.flush()
    if page_format == "block" and command.content_blocks is not None:
        sync_embedded_media(db, command.content_blocks, "docs_native_page", page.id, user)
        sync_collab_record_from_rest_patch(
            db,
            source_type=PAGE_SOURCE_NATIVE_DOC,
            source_page_id=page.id,
            snapshot_content_blocks=command.content_blocks,
        )
    touch_native_doc(doc)
    db.add(doc)
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
    )
    db.commit()
    loaded_page = load_native_page(db, page.id)
    assert loaded_page is not None
    return PageMutationResult(
        page=serialize_native_page(loaded_page, can_edit=access.can_edit),
        doc_id=doc.id,
        page_id=loaded_page.id,
        created=True,
    )


def create_native_page_from_markdown(
    db: Session,
    *,
    principal: CallerPrincipal,
    user: User,
    hub_id: str,
    title: str,
    content_markdown: str | None = None,
    parent_id: str | None = None,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    content_blocks = docs_service._markdown_to_blocks(content_markdown)
    result = create_native_page(
        db,
        principal=principal,
        user=user,
        command=CreateNativePageCommand(
            item_id=hub_id,
            title=title,
            parent_id=parent_id,
            content_format="block",
            content_blocks=content_blocks,
            content_blocks_present=content_blocks is not None,
            page_id=approved_call_id,
        ),
    )
    return result.page


def update_native_page(
    db: Session,
    *,
    user: User,
    command: UpdateNativePageCommand,
    share_token: str | None = None,
) -> PageMutationResult:
    context = _load_editable_page_context(
        db,
        user=user,
        page_id=command.page_id,
        share_token=share_token,
    )
    page = context.page
    doc = context.doc
    access = context.access

    changed = False
    metadata_changed = False
    if command.parent_id_present:
        next_parent_id = normalize_page_id(command.parent_id) if command.parent_id else None
        validate_native_parent(doc, next_parent_id, page_id=page.id)
        if page.parent_id != next_parent_id:
            page.parent_id = next_parent_id
            changed = True
            metadata_changed = True
    if command.title is not None:
        next_title = command.title.strip()
        if page.title != next_title:
            page.title = next_title
            changed = True
            metadata_changed = True
    if command.content_blocks_present:
        if page.content_format != "block":
            raise localized_http_exception(status_code=400, code="docs.content_format_mismatch")
        if (
            not block_content_equal(page.content_blocks, command.content_blocks)
            or page.content_text is not None
        ):
            page.content_blocks = command.content_blocks
            page.content_text = None
            sync_embedded_media(
                db,
                command.content_blocks,
                "docs_native_page",
                page.id,
                user,
            )
            sync_collab_record_from_rest_patch(
                db,
                source_type=PAGE_SOURCE_NATIVE_DOC,
                source_page_id=page.id,
                snapshot_content_blocks=command.content_blocks,
            )
            changed = True
    if command.content_text_present:
        if page.content_format == "block":
            raise localized_http_exception(status_code=400, code="docs.content_format_mismatch")
        if page.content_text != command.content_text:
            page.content_text = command.content_text
            changed = True
    if command.sort_order is not None and page.sort_order != command.sort_order:
        page.sort_order = command.sort_order
        changed = True
        metadata_changed = True

    if changed:
        db.add(page)
        touch_native_doc(doc)
        db.add(doc)
        enqueue_native_doc_rag_sync(
            db,
            doc=doc,
            operation=RagSyncOperation.UPSERT,
        )
        db.commit()

    loaded_page = load_native_page(db, page.id)
    assert loaded_page is not None
    return PageMutationResult(
        page=serialize_native_page(loaded_page, can_edit=access.can_edit),
        doc_id=doc.id,
        page_id=loaded_page.id,
        created=False,
        changed=changed,
        metadata_changed=metadata_changed,
    )


def delete_native_page(
    db: Session,
    *,
    user: User,
    command: DeleteNativePageCommand,
    share_token: str | None = None,
) -> DeleteNativePageResult:
    context = _load_editable_page_context(
        db,
        user=user,
        page_id=command.page_id,
        share_token=share_token,
    )
    page = context.page
    doc = context.doc

    deleted_at = _utcnow()
    media_keys: list[str] = []
    for node in _collect_native_page_subtree(
        [item for item in doc.pages if item.trashed_at is None],
        page.id,
    ):
        node.trashed_at = deleted_at
        db.add(node)
        delete_collab_document(
            db,
            source_type=PAGE_SOURCE_NATIVE_DOC,
            source_page_id=node.id,
        )
        media_keys.extend(cleanup_media_for_resource(db, "docs_native_page", node.id))
    touch_native_doc(doc)
    db.add(doc)
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=RagSyncOperation.UPSERT,
    )
    deleted_page_id = page.id
    db.commit()
    return DeleteNativePageResult(
        doc_id=doc.id,
        page_id=deleted_page_id,
        media_keys=media_keys,
    )


def _load_existing_page_for_idempotency(
    db: Session,
    *,
    user: User,
    page_id: str,
    share_token: str | None,
) -> PageMutationResult | None:
    existing_page = load_native_page(db, page_id)
    if existing_page is None or existing_page.doc is None:
        return None
    existing_doc = load_native_doc_for_access(db, existing_page.doc_id)
    if existing_doc is None:
        return None
    access = resolve_native_doc_access(
        db,
        existing_doc,
        user,
        share_token=share_token,
    )
    if not access.can_view:
        return None
    return PageMutationResult(
        page=serialize_native_page(existing_page, can_edit=access.can_edit),
        doc_id=existing_doc.id,
        page_id=existing_page.id,
        created=False,
    )


def _validate_create_page_content(command: CreateNativePageCommand) -> None:
    if command.content_format == "block" and command.content_text_present:
        raise localized_http_exception(status_code=400, code="docs.content_format_mismatch")
    if command.content_format != "block" and command.content_blocks_present:
        raise localized_http_exception(status_code=400, code="docs.content_format_mismatch")


def _load_editable_page_context(
    db: Session,
    *,
    user: User,
    page_id: str,
    share_token: str | None,
) -> NativePageContext:
    return native_page_context_from_page_or_404(
        db,
        page_id=page_id,
        user=user,
        share_token=share_token,
        require="edit",
    )


def _collect_native_page_subtree(
    pages: list[NativeDocPage],
    root_page_id: str,
) -> list[NativeDocPage]:
    by_parent: dict[str | None, list[NativeDocPage]] = {}
    by_id = {page.id: page for page in pages}
    for page in pages:
        by_parent.setdefault(page.parent_id, []).append(page)
    root = by_id.get(root_page_id)
    if root is None:
        return []
    result: list[NativeDocPage] = []
    stack = [root]
    seen: set[str] = set()
    while stack:
        current = stack.pop()
        if current.id in seen:
            continue
        seen.add(current.id)
        result.append(current)
        stack.extend(by_parent.get(current.id, []))
    return result


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)
