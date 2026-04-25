from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.search.models import SearchIndexJob
from aidoo_api.domains.search.opensearch import OpenSearchKeywordClient
from aidoo_api.domains.search.projections import load_search_document


def process_search_index_job(
    db: Session,
    job_id: str,
    *,
    client: OpenSearchKeywordClient | None = None,
) -> str:
    job = db.get(SearchIndexJob, job_id)
    if job is None:
        return "missing"
    if job.status in {"succeeded", "cancelled"}:
        return "ignored"

    now = datetime.now(UTC).replace(tzinfo=None)
    job.status = "processing"
    job.attempts += 1
    job.last_error = None
    job.next_retry_at = None
    job.updated_at = now
    db.add(job)
    db.commit()
    db.refresh(job)

    search_client = client or _search_client()
    document = load_search_document(db, entity_type=job.entity_type, entity_id=job.entity_id)
    if document is None:
        search_client.delete_document(
            workspace_id=job.workspace_id,
            entity_type=job.entity_type,
            entity_id=job.entity_id,
        )
        result = "deleted_missing_projection"
    else:
        search_client.upsert_document(document)
        result = "upserted"

    job.status = "succeeded"
    job.last_error = None
    job.updated_at = datetime.now(UTC).replace(tzinfo=None)
    db.add(job)
    db.commit()
    return result


def _search_client() -> OpenSearchKeywordClient:
    settings = get_settings()
    return OpenSearchKeywordClient(base_url=settings.opensearch_url, index_prefix=settings.opensearch_index_prefix)
