"""Worker task for AI specification comparison jobs."""

from __future__ import annotations

import io
import logging

from celery.exceptions import Ignore

from open_work_hub_worker.celery_app import celery_app
from open_work_hub_worker.runtime import (
    db_session as _db_session,
    ensure_api_src_on_path as _ensure_api_src_on_path,
    minio_client as _minio_client,
)
from open_work_hub_worker.settings import get_settings


_ensure_api_src_on_path()

from open_work_hub_api.domains.spec_compare.models import SpecCompareJob  # noqa: E402
from open_work_hub_api.domains.spec_compare.pipeline import (  # noqa: E402
    SpecCompareCancelled,
    compare_spec_documents,
)
from open_work_hub_api.domains.spec_compare import service as spec_compare_service  # noqa: E402


logger = logging.getLogger(__name__)


def _read_object(key: str) -> bytes:
    response = _minio_client().get_object(get_settings().minio_bucket, key)
    try:
        return response.read()
    finally:
        response.close()
        response.release_conn()


def _put_object(key: str, content: bytes, content_type: str) -> None:
    _minio_client().put_object(
        get_settings().minio_bucket,
        key,
        io.BytesIO(content),
        length=len(content),
        content_type=content_type,
    )


@celery_app.task(
    name="spec_compare.run_job",
    bind=True,
    acks_late=True,
    max_retries=1,
    task_time_limit=1800,
    task_soft_time_limit=1740,
)
def run_job(self, job_id: str) -> str:
    session = _db_session()
    try:
        row = session.get(SpecCompareJob, job_id)
        if row is None:
            raise Ignore()
        if row.status == "succeeded":
            return row.id
        if row.status not in {"queued", "running"}:
            raise Ignore()
        task_id = getattr(self.request, "id", None)
        if task_id and row.celery_task_id and row.celery_task_id != task_id:
            raise Ignore()

        spec_compare_service.mark_running(
            session,
            row,
            message="extracting",
            progress=10,
        )
        base_content = _read_object(row.base_storage_key)
        target_content = _read_object(row.target_storage_key)

        row = session.get(SpecCompareJob, job_id)
        if row is None or row.status not in {"queued", "running"}:
            raise Ignore()

        def report_progress(message: str, progress: int) -> None:
            current = session.get(SpecCompareJob, job_id)
            if current is None or current.status not in {"queued", "running"}:
                raise SpecCompareCancelled()
            spec_compare_service.mark_running(
                session,
                current,
                message=message,
                progress=progress,
            )

        spec_compare_service.mark_running(
            session,
            row,
            message="comparing",
            progress=45,
        )
        result = compare_spec_documents(
            session,
            workspace_id=row.workspace_id,
            actor_user_id=row.owner_id,
            job_id=row.id,
            base_filename=row.base_file_name,
            base_mime_type=row.base_mime_type,
            base_content=base_content,
            target_filename=row.target_file_name,
            target_mime_type=row.target_mime_type,
            target_content=target_content,
            progress_callback=report_progress,
        )

        row = session.get(SpecCompareJob, job_id)
        if row is None:
            raise Ignore()
        if row.status not in {"queued", "running"}:
            raise Ignore()
        spec_compare_service.persist_result(
            session,
            row,
            result=result,
            put_object=_put_object,
        )
        return row.id
    except Ignore:
        raise
    except SpecCompareCancelled:
        raise Ignore()
    except Exception as exc:
        logger.exception("spec_compare.run_job: unexpected error for %s", job_id)
        row = session.get(SpecCompareJob, job_id)
        if row is not None and self.request.retries >= self.max_retries:
            spec_compare_service.mark_failed(session, row, "Specification comparison failed")
        if self.request.retries >= self.max_retries:
            raise Ignore()
        raise self.retry(exc=exc, countdown=30)
    finally:
        session.close()
