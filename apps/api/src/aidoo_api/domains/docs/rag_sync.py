from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.docs.models import NativeDoc
from aidoo_api.domains.rag.contracts import RagSyncOperation
from aidoo_api.domains.rag.docs_projection import NATIVE_DOC_RESOURCE_TYPE
from aidoo_api.domains.rag.outbox import enqueue_rag_sync_job


def enqueue_native_doc_rag_sync(
    db: Session,
    *,
    doc: NativeDoc,
    operation: RagSyncOperation,
) -> None:
    if not get_settings().rag_enabled:
        return

    enqueue_rag_sync_job(
        db,
        workspace_id=doc.workspace_id,
        resource_type=NATIVE_DOC_RESOURCE_TYPE,
        resource_id=doc.id,
        operation=operation,
    )


def enqueue_native_doc_rag_sync_by_id(
    db: Session,
    *,
    doc_id: str,
    operation: RagSyncOperation,
) -> None:
    doc = db.scalar(
        select(NativeDoc).where(NativeDoc.id == doc_id)
    )
    if doc is None:
        return
    enqueue_native_doc_rag_sync(
        db,
        doc=doc,
        operation=operation,
    )
