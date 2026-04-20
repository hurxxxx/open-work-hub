from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.docs.models import NativeDoc, NativeDocContainer, NativeDocPage


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


def _router():
    from aidoo_api.domains.docs import router as docs_router

    return docs_router


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
