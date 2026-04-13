from __future__ import annotations

from sqlalchemy.orm import Session

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
