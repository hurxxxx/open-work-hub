from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session, selectinload

from aidoo_api.domains.docs.models import NativeDoc
from aidoo_api.domains.rag.contracts import RagProjection
from aidoo_api.domains.rag.projection import build_projection


NATIVE_DOC_RESOURCE_TYPE = "docs_native_doc"


def load_native_doc_projection(
    db: Session,
    *,
    doc_id: str,
) -> RagProjection | None:
    doc = db.scalar(
        select(NativeDoc)
        .options(
            selectinload(NativeDoc.owner),
            selectinload(NativeDoc.pages),
            selectinload(NativeDoc.containers),
            selectinload(NativeDoc.user_shares),
            selectinload(NativeDoc.link_shares),
            selectinload(NativeDoc.meeting_access_grants),
        )
        .where(NativeDoc.id == doc_id, NativeDoc.trashed_at.is_(None))
    )
    if doc is None:
        return None
    return build_native_doc_projection(doc)


def build_native_doc_projection(doc: NativeDoc) -> RagProjection:
    active_pages = sorted(
        (page for page in doc.pages if page.trashed_at is None),
        key=lambda page: (page.sort_order, page.created_at, page.id),
    )
    page_sections: list[str] = []
    for page in active_pages:
        if page.title.strip():
            page_sections.append(page.title.strip())
        page_text = _extract_blocks_text(page.content_blocks)
        if page_text:
            page_sections.append(page_text)

    text_sections = [doc.title.strip(), *page_sections]
    text_content = "\n\n".join(section for section in text_sections if section)
    summary = _summarize_text(page_sections[0] if page_sections else doc.title)
    container_refs = [
        f"{container.container_app}:{container.container_type}:{container.container_id}"
        for container in sorted(
            doc.containers,
            key=lambda container: (container.sort_order, container.container_app, container.id),
        )
    ]
    visibility_refs = _build_visibility_refs(doc)

    return build_projection(
        workspace_id=doc.workspace_id,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id=doc.id,
        source_kind=doc.source_kind,
        title=doc.title,
        summary=summary,
        text_content=text_content,
        owner_label=getattr(doc.owner, "full_name", None),
        visibility_refs=visibility_refs,
        metadata={
            "source_app": doc.source_app,
            "generation_kind": doc.generation_kind,
            "origin_ref": doc.source_ref,
            "page_count": len(active_pages),
            "container_refs": container_refs,
            "link_share_active": any(share.active for share in doc.link_shares),
        },
    )


def _build_visibility_refs(doc: NativeDoc) -> list[str]:
    refs = {
        f"workspace:{doc.workspace_id}",
        f"owner:{doc.owner_id}",
    }

    for container in doc.containers:
        refs.add(
            f"container:{container.container_app}:{container.container_type}:{container.container_id}"
        )

    for share in doc.user_shares:
        refs.add(f"share_user:{share.user_id}")

    for share in doc.link_shares:
        if share.active:
            refs.add(f"link_share_ref:{share.id}")

    now = datetime.now(UTC).replace(tzinfo=None)
    for grant in doc.meeting_access_grants:
        if grant.revoked_at is not None:
            continue
        if grant.expires_at is not None and grant.expires_at <= now:
            continue
        refs.add(f"meeting_grant:{grant.user_id}")
        if grant.granted_by_meeting_id:
            refs.add(f"meeting_source:{grant.granted_by_meeting_id}")

    return sorted(refs)


def _extract_blocks_text(blocks: list[dict[str, Any]] | None) -> str:
    if not blocks:
        return ""

    parts: list[str] = []
    for block in blocks:
        _collect_text_parts(block, parts)
    return " ".join(part for part in parts if part).strip()


def _collect_text_parts(value: Any, parts: list[str]) -> None:
    if isinstance(value, str):
        normalized = " ".join(value.split()).strip()
        if normalized:
            parts.append(normalized)
        return

    if isinstance(value, list):
        for item in value:
            _collect_text_parts(item, parts)
        return

    if not isinstance(value, dict):
        return

    if isinstance(value.get("text"), str):
        normalized = " ".join(value["text"].split()).strip()
        if normalized:
            parts.append(normalized)

    for key in ("content", "children"):
        nested = value.get(key)
        if nested is not None:
            _collect_text_parts(nested, parts)


def _summarize_text(text: str, *, max_chars: int = 240) -> str | None:
    normalized = " ".join(text.split()).strip()
    if not normalized:
        return None
    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 3].rstrip() + "..."
