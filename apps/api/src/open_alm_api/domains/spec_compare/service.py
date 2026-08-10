from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
import json
import logging
from pathlib import Path
from uuid import uuid4

from sqlalchemy import delete, desc, select
from sqlalchemy.orm import Session

from open_alm_api.core.i18n import localized_http_exception
from open_alm_api.domains.auth.models import User, Workspace
from open_alm_api.domains.spec_compare.artifacts import (
    SpecCompareUpload,
    result_json_key,
    result_markdown_key,
    spec_compare_artifact_store,
)
from open_alm_api.domains.spec_compare import report_export
from open_alm_api.domains.spec_compare.dispatch import spec_compare_job_dispatcher
from open_alm_api.domains.spec_compare.models import SpecCompareJob, SpecCompareSpecItem
from open_alm_api.domains.spec_compare.pipeline import SpecComparePipelineResult, SpecItem
from open_alm_api.domains.spec_compare.result_projection import (
    project_spec_compare_job,
    project_spec_compare_result,
    project_spec_item_record,
)
from open_alm_api.domains.spec_compare.schemas import (
    SpecCompareJobListResponse,
    SpecCompareJobOut,
    SpecCompareResultResponse,
)


logger = logging.getLogger(__name__)

_MAX_UPLOAD_BYTES = 100 * 1024 * 1024
_SUPPORTED_EXTENSIONS = {".pptx", ".docx", ".pdf"}


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _new_id() -> str:
    return str(uuid4())


def _validate_upload(*, filename: str, content: bytes) -> None:
    if not content:
        raise localized_http_exception(status_code=422, code="spec_compare.empty_upload")
    if len(content) > _MAX_UPLOAD_BYTES:
        raise localized_http_exception(status_code=413, code="spec_compare.upload_too_large")
    if Path(filename or "").suffix.lower() not in _SUPPORTED_EXTENSIONS:
        raise localized_http_exception(status_code=422, code="spec_compare.invalid_file_type")


def _load_job(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    job_id: str,
) -> SpecCompareJob:
    row = db.get(SpecCompareJob, job_id)
    if row is None or row.workspace_id != workspace.id:
        raise localized_http_exception(status_code=404, code="spec_compare.not_found")
    if row.owner_id != user.id:
        raise localized_http_exception(status_code=403, code="spec_compare.forbidden")
    return row


def create_job(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    title: str,
    base_filename: str,
    base_mime_type: str,
    base_content: bytes,
    target_filename: str,
    target_mime_type: str,
    target_content: bytes,
) -> SpecCompareJobOut:
    _validate_upload(filename=base_filename, content=base_content)
    _validate_upload(filename=target_filename, content=target_content)

    job_id = _new_id()
    try:
        artifacts = spec_compare_artifact_store().upload_inputs(
            workspace_id=workspace.id,
            job_id=job_id,
            base=SpecCompareUpload(
                filename=base_filename,
                mime_type=base_mime_type,
                content=base_content,
            ),
            target=SpecCompareUpload(
                filename=target_filename,
                mime_type=target_mime_type,
                content=target_content,
            ),
        )
    except Exception as exc:
        logger.exception("spec_compare.create: upload failed")
        raise localized_http_exception(status_code=502, code="spec_compare.upload_failed") from exc

    row = SpecCompareJob(
        id=job_id,
        workspace_id=workspace.id,
        owner_id=user.id,
        title=title.strip()[:200],
        status="queued",
        progress=0,
        status_message="queued",
        base_file_name=artifacts.base.filename,
        base_mime_type=artifacts.base.mime_type,
        base_size_bytes=artifacts.base.size_bytes,
        base_storage_key=artifacts.base.storage_key,
        target_file_name=artifacts.target.filename,
        target_mime_type=artifacts.target.mime_type,
        target_size_bytes=artifacts.target.size_bytes,
        target_storage_key=artifacts.target.storage_key,
    )
    db.add(row)
    db.commit()

    try:
        row.celery_task_id = spec_compare_job_dispatcher().dispatch(row.id)
        row.updated_at = _utcnow()
        db.add(row)
        db.commit()
    except Exception as exc:
        logger.exception("spec_compare.create: dispatch failed")
        row.status = "failed"
        row.progress = 100
        row.failure_reason = "Dispatch failed"
        row.updated_at = _utcnow()
        db.add(row)
        db.commit()
        raise localized_http_exception(
            status_code=502, code="spec_compare.dispatch_failed"
        ) from exc

    db.refresh(row)
    return project_spec_compare_job(row)


def delete_job(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    job_id: str,
) -> None:
    row = _load_job(db, workspace=workspace, user=user, job_id=job_id)
    storage_keys = [
        row.base_storage_key,
        row.target_storage_key,
        row.result_json_storage_key,
        row.report_markdown_storage_key,
    ]
    db.execute(delete(SpecCompareSpecItem).where(SpecCompareSpecItem.job_id == row.id))
    db.delete(row)
    db.commit()
    try:
        spec_compare_artifact_store().remove_job_artifacts(storage_keys=storage_keys)
    except Exception:
        logger.warning(
            "spec_compare.delete: artifact cleanup failed for %s", job_id, exc_info=True
        )


def list_jobs(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    limit: int,
) -> SpecCompareJobListResponse:
    rows = (
        db.execute(
            select(SpecCompareJob)
            .where(SpecCompareJob.workspace_id == workspace.id, SpecCompareJob.owner_id == user.id)
            .order_by(desc(SpecCompareJob.created_at))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    return SpecCompareJobListResponse(items=[project_spec_compare_job(row) for row in rows])


def get_job(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    job_id: str,
) -> SpecCompareJobOut:
    return project_spec_compare_job(_load_job(db, workspace=workspace, user=user, job_id=job_id))


def get_result(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    job_id: str,
) -> SpecCompareResultResponse:
    row = _load_job(db, workspace=workspace, user=user, job_id=job_id)
    if row.status != "succeeded" or not row.result_json_storage_key:
        raise localized_http_exception(status_code=409, code="spec_compare.not_ready")
    try:
        payload = spec_compare_artifact_store().read_result_payload(row.result_json_storage_key)
    except Exception as exc:
        logger.exception("spec_compare.result: read failed for %s", job_id)
        raise localized_http_exception(status_code=409, code="spec_compare.not_ready") from exc
    return project_spec_compare_result(row, payload)


def get_report_document(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    job_id: str,
    fmt: str,
) -> tuple[bytes, str, str]:
    row = _load_job(db, workspace=workspace, user=user, job_id=job_id)
    if row.status != "succeeded" or not row.result_json_storage_key:
        raise localized_http_exception(status_code=409, code="spec_compare.not_ready")
    try:
        payload = spec_compare_artifact_store().read_result_payload(row.result_json_storage_key)
    except Exception as exc:
        logger.exception("spec_compare.report: read failed for %s", job_id)
        raise localized_http_exception(status_code=409, code="spec_compare.not_ready") from exc
    summary = payload.get("summary")
    rendered = report_export.render_report(
        fmt,
        title=row.title or "",
        base_filename=row.base_file_name,
        target_filename=row.target_file_name,
        summary=summary if isinstance(summary, dict) else {},
        payload=payload,
    )
    base_name = (row.title or "spec-compare-report").strip() or "spec-compare-report"
    filename = f"{base_name}.{rendered.extension}"
    return rendered.content, rendered.media_type, filename


def mark_running(db: Session, row: SpecCompareJob, *, message: str, progress: int) -> None:
    row.status = "running"
    row.status_message = message
    row.progress = progress
    row.failure_reason = None
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()


def mark_failed(db: Session, row: SpecCompareJob, reason: str) -> None:
    db.rollback()
    row.status = "failed"
    row.progress = 100
    row.status_message = "failed"
    row.failure_reason = reason[:2000]
    row.celery_task_id = None
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()


def persist_result(
    db: Session,
    row: SpecCompareJob,
    *,
    result: SpecComparePipelineResult,
    put_object: Callable[[str, bytes, str], None],
) -> None:
    payload = result.to_payload()
    json_bytes = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
    markdown_bytes = result.report_markdown.encode("utf-8")
    json_key = result_json_key(row.workspace_id, row.id)
    markdown_key = result_markdown_key(row.workspace_id, row.id)
    put_object(json_key, json_bytes, "application/json; charset=utf-8")
    put_object(markdown_key, markdown_bytes, "text/markdown; charset=utf-8")
    row.result_json_storage_key = json_key
    row.report_markdown_storage_key = markdown_key
    row.result_summary = result.summary
    _replace_spec_items(db, row, role="base", items=result.base_spec_items or [])
    _replace_spec_items(db, row, role="target", items=result.target_spec_items or [])
    row.status = "succeeded"
    row.progress = 100
    row.status_message = "succeeded"
    row.failure_reason = None
    row.completed_at = _utcnow()
    row.celery_task_id = None
    row.updated_at = _utcnow()
    db.add(row)
    db.commit()


def _replace_spec_items(
    db: Session,
    row: SpecCompareJob,
    *,
    role: str,
    items: list[SpecItem],
) -> None:
    db.execute(
        delete(SpecCompareSpecItem).where(
            SpecCompareSpecItem.job_id == row.id,
            SpecCompareSpecItem.document_role == role,
        )
    )
    for index, item in enumerate(items, start=1):
        db.add(project_spec_item_record(row, role, index, item))
