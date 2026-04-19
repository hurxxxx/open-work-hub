from __future__ import annotations

from typing import Any

from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.auth.access import bind_current_workspace
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.models import NativeDoc, NativeDocPage


def create_native_doc_for_user(
    db: Session,
    *,
    workspace_id: str,
    owner_id: str,
    title: str,
    first_page_title: str | None = None,
    content_blocks: list[dict] | None = None,
) -> tuple[NativeDoc, NativeDocPage]:
    doc = NativeDoc(
        id=new_id(),
        workspace_id=workspace_id,
        owner_id=owner_id,
        title=title.strip(),
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
    db.flush()
    return doc, page


def _router():
    from aidoo_api.domains.docs import router as docs_router

    return docs_router


def _bind_workspace_context(
    db: Session,
    *,
    workspace: Workspace | None,
    principal: CallerPrincipal | None,
    user: User,
) -> None:
    if workspace is None or principal is None:
        return
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


def list_hub(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal | None,
    user: User,
    category: str = "all",
    q: str = "",
    sort_by: str = "updated_at",
    sort_dir: str = "desc",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()

    helpers._ensure_docs_workspace_access(db, user)
    pref_map = helpers._get_pref_map(db, user.id)

    native_items = [
        helpers._serialize_native_item(
            doc,
            helpers._resolve_native_doc_access(db, doc, user),
            pref_map.get((helpers.SOURCE_NATIVE_DOC, doc.id)),
        )
        for doc in helpers._load_accessible_native_docs(db, user)
        if helpers._resolve_native_doc_access(db, doc, user).can_view
    ]

    space_items: list[Any] = []
    for doc in helpers._load_accessible_space_docs(db, user):
        role = helpers._resolve_pms_team_role(db, user, doc.team_id)
        if role is None:
            continue
        space_items.append(
            helpers._serialize_space_doc_item(
                doc,
                location_label=helpers._space_location_label(db, doc.team_id),
                role=role,
                pref=pref_map.get((helpers.SOURCE_PMS_SPACE_DOC, doc.id)),
            )
        )

    docs = helpers._filter_docs_by_category(
        [*native_items, *space_items],
        current_user_id=user.id,
        category=category,
        q=q,
    )
    docs = helpers._sort_docs(docs, sort_by=sort_by, sort_dir=sort_dir)
    total = len(docs)
    start = (page - 1) * page_size
    end = start + page_size
    return {
        "items": [item.model_dump() for item in docs[start:end]],
        "total": total,
        "page": page,
        "page_size": page_size,
    }


def get_item(
    db: Session,
    *,
    workspace: Workspace | None,
    principal: CallerPrincipal | None,
    user: User,
    item_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()

    if share_token is None or not helpers._share_token_allows_item_without_docs_access(item_id):
        helpers._ensure_docs_workspace_access(db, user)
    item = helpers._lookup_item(db, item_id, user, share_token=share_token)
    return item.model_dump()


def list_pages(
    db: Session,
    *,
    workspace: Workspace | None,
    principal: CallerPrincipal | None,
    user: User,
    item_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()

    if share_token is None or not helpers._share_token_allows_item_without_docs_access(item_id):
        helpers._ensure_docs_workspace_access(db, user)
    item = helpers._lookup_item(db, item_id, user, share_token=share_token)
    if item.source_type == helpers.SOURCE_NATIVE_DOC:
        doc, access = helpers._native_doc_from_item_or_404(db, item_id, user, share_token=share_token)
        items = [
            helpers._serialize_native_page(doc, page, can_edit=access.can_edit).model_dump()
            for page in sorted(
                [page for page in doc.pages if page.trashed_at is None],
                key=lambda page: (
                    "" if page.parent_id is None else page.parent_id,
                    page.sort_order,
                    page.created_at,
                ),
            )
        ]
        return {"items": items}

    if item.source_type == helpers.SOURCE_PMS_SPACE_DOC:
        doc, role = helpers._space_doc_from_item_or_404(db, item_id, user)
        items = [
            helpers._serialize_space_page(
                doc,
                page,
                can_edit=helpers._team_role_allows(role, "member"),
            ).model_dump()
            for page in sorted(
                [page for page in doc.pages if page.trashed_at is None],
                key=lambda page: (
                    "" if page.parent_id is None else page.parent_id,
                    page.sort_order,
                    page.created_at,
                ),
            )
        ]
        return {"items": items}

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Doc not found.")


def read_page(
    db: Session,
    *,
    workspace: Workspace | None,
    principal: CallerPrincipal | None,
    user: User,
    page_id: str,
    share_token: str | None = None,
) -> dict[str, Any]:
    _bind_workspace_context(db, workspace=workspace, principal=principal, user=user)
    helpers = _router()

    if share_token is None or not helpers._share_token_allows_page_without_docs_access(db, page_id):
        helpers._ensure_docs_workspace_access(db, user)

    prefix, raw_id = helpers._split_prefixed_id(page_id)
    if prefix in {None, helpers.PAGE_SOURCE_NATIVE_DOC}:
        page = helpers._load_native_page(db, raw_id)
        if page is None or page.doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found.")
        access = helpers._resolve_native_doc_access(db, page.doc, user, share_token=share_token)
        if not access.can_view:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Page access required.")
        return helpers._serialize_native_page(page.doc, page, can_edit=access.can_edit).model_dump()

    if prefix == helpers.PAGE_SOURCE_PMS_SPACE_DOC:
        page = helpers._load_space_doc_page_with_doc(db, raw_id)
        if page is None or page.doc is None:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found.")
        role = helpers._resolve_pms_team_role(db, user, page.doc.team_id)
        if role is None:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Page access required.")
        return helpers._serialize_space_page(
            page.doc,
            page,
            can_edit=helpers._team_role_allows(role, "member"),
        ).model_dump()

    raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Page not found.")
