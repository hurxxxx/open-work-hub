from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from open_alm_api.domains.qna.constants import (
    QNA_DEFAULT_CATEGORY,
    QNA_COMPANY_VISIBILITY_REF,
    QNA_DOC_SOURCE_KIND,
    QNA_DOCUMENT_RESOURCE_TYPE,
    QNA_SCOPE_KIND,
)
from open_alm_api.domains.qna.models import QnaDocument
from open_alm_api.domains.rag.contracts import RagProjection, RagScopeKind
from open_alm_api.domains.rag.projection_builders import build_text_projection


def build_qna_document_projection(doc: QnaDocument) -> RagProjection:
    sections: list[str | None] = [doc.title]
    if doc.category and doc.category != QNA_DEFAULT_CATEGORY:
        sections.append(f"분류: {doc.category}")
    if doc.author:
        sections.append(f"작성자: {doc.author}")
    if doc.posted_at:
        sections.append(f"날짜: {doc.posted_at}")
    if doc.body_text:
        sections.append(doc.body_text)

    return build_text_projection(
        scope_kind=RagScopeKind(QNA_SCOPE_KIND),
        workspace_id=None,
        resource_type=QNA_DOCUMENT_RESOURCE_TYPE,
        resource_id=doc.id,
        source_kind=QNA_DOC_SOURCE_KIND,
        title=doc.title,
        text_sections=sections,
        visibility_refs=[QNA_COMPANY_VISIBILITY_REF],
        metadata={
            "kind": doc.kind,
            "category": doc.category,
            "author": doc.author,
            "posted_at": doc.posted_at,
            "attachments": list(doc.attachments or []),
            "external_id": doc.external_id,
        },
    )


def load_qna_document_projection(db: Session, *, resource_id: str) -> RagProjection | None:
    doc = db.get(QnaDocument, resource_id)
    if doc is None:
        return None
    return build_qna_document_projection(doc)


def workspace_qna_document_ids(db: Session, workspace) -> list[str]:
    del db, workspace
    return []


def company_qna_document_ids(db: Session) -> list[str]:
    return list(
        db.scalars(select(QnaDocument.id).where(QnaDocument.scope_kind == QNA_SCOPE_KIND))
    )
