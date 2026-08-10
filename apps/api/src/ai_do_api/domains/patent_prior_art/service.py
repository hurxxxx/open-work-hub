from __future__ import annotations

from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
import hashlib
from io import BytesIO
import json
import logging
from pathlib import Path
import re
from typing import Any
from urllib.parse import quote
from uuid import uuid4
import zipfile

from fastapi import Response
from pydantic import BaseModel
from sqlalchemy import and_, delete, desc, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.domains.auth.models import User, Workspace, WorkspaceUserBinding
from ai_do_api.domains.auth.workspace_app_gate import is_workspace_app_enabled
from ai_do_api.domains.document_processing import (
    UnsupportedDocumentType,
    extract_document,
)
from ai_do_api.domains.patent_prior_art import PATENT_PRIOR_ART_APP_ID
from ai_do_api.domains.patent_prior_art.artifacts import (
    StoredArtifact,
    patent_prior_art_artifact_store,
    storage_key_belongs_to_job,
)
from ai_do_api.domains.patent_prior_art.catalog import (
    PATENT_PRIOR_ART_CATEGORY_CATALOG,
)
from ai_do_api.domains.patent_prior_art.dispatch import (
    PatentPriorArtJobDispatcher,
    patent_prior_art_job_dispatcher,
)
from ai_do_api.domains.patent_prior_art.models import (
    PatentPriorArtArtifact,
    PatentPriorArtCandidate,
    PatentPriorArtExecutedQuery,
    PatentPriorArtJob,
)
from ai_do_api.domains.patent_prior_art.report_export import render_report_export
from ai_do_api.domains.patent_prior_art.result_projection import (
    project_job,
    project_result,
)
from ai_do_api.domains.patent_prior_art.schemas import (
    PatentPriorArtCandidateOut,
    PatentPriorArtCategoryOption,
    PatentPriorArtConfigResponse,
    PatentPriorArtDeleteResponse,
    PatentPriorArtExecutedQueryOut,
    PatentPriorArtFileParseResponse,
    PatentPriorArtJobCreateRequest,
    PatentPriorArtJobListResponse,
    PatentPriorArtJobOut,
    PatentPriorArtJurisdictionOption,
    PatentPriorArtQueryPreviewRequest,
    PatentPriorArtQueryPreviewResponse,
    PatentPriorArtReportFormat,
    PatentPriorArtResultResponse,
)


logger = logging.getLogger(__name__)

_MAX_UPLOAD_BYTES = 30 * 1024 * 1024
_MAX_EXTRACTED_CHARS = 200_000
_MAX_OFFICE_ARCHIVE_ENTRIES = 1000
_MAX_OFFICE_ARCHIVE_UNCOMPRESSED_BYTES = 120 * 1024 * 1024
_MAX_OFFICE_ARCHIVE_MEMBER_BYTES = 25 * 1024 * 1024
_MAX_OFFICE_ARCHIVE_EXPANSION_RATIO = 100
_SUPPORTED_EXTENSIONS = {".pdf", ".docx", ".xlsx", ".pptx"}
_CANONICAL_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": ("application/vnd.openxmlformats-officedocument.wordprocessingml.document"),
    ".xlsx": ("application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"),
    ".pptx": ("application/vnd.openxmlformats-officedocument.presentationml.presentation"),
}
_ALLOWED_MIME_TYPES = {
    extension: {
        canonical,
        "application/octet-stream",
        *({"application/zip"} if extension != ".pdf" else set()),
    }
    for extension, canonical in _CANONICAL_MIME_TYPES.items()
}
_OFFICE_MARKERS = {
    ".docx": "word/document.xml",
    ".xlsx": "xl/workbook.xml",
    ".pptx": "ppt/presentation.xml",
}
_OFFICE_MEDIA_PREFIXES = ("word/media/", "xl/media/", "ppt/media/")
_OFFICE_EMBEDDING_PREFIXES = ("word/embeddings/", "xl/embeddings/", "ppt/embeddings/")
_STAGES = {
    "queued",
    "retry_waiting",
    "loading_input",
    "searching",
    "ranking",
    "assessing",
    "reporting",
    "persisting",
    "completed",
    "failed",
    "cancelled",
    "cleanup_pending",
}
_SAFE_FAILURE_CODES = frozenset(
    {
        "access_revoked",
        "pipeline_failed",
        "provider_timeout",
        "worker_lost",
    }
)
_DISPATCH_RESERVATION_GRACE = timedelta(minutes=5)
_EXECUTION_LEASE_DURATION = timedelta(minutes=3)
_AUTOMATIC_RESTART_DELAY = timedelta(seconds=60)
_MAX_DISPATCH_BATCH = 1_000


class PatentPriorArtPersistenceCancelled(RuntimeError):
    """Raised when a worker loses the terminal-state race to cancellation."""


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _new_id() -> str:
    return str(uuid4())


def config() -> PatentPriorArtConfigResponse:
    return PatentPriorArtConfigResponse(
        min_invention_chars=30,
        max_invention_chars=200_000,
        max_plan_values_per_field=30,
        max_plan_value_chars=256,
        max_upload_bytes=_MAX_UPLOAD_BYTES,
        allowed_upload_extensions=[".pdf", ".docx", ".xlsx", ".pptx"],
        categories=[
            PatentPriorArtCategoryOption(
                id=definition.id,
                label_key=f"ai.patentPriorArt.categories.{definition.id}.label",
                fallback_label=definition.fallback_label,
                description_key=(f"ai.patentPriorArt.categories.{definition.id}.description"),
                fallback_description=(
                    f"{definition.fallback_label} 범위를 검색 계획의 입력 문맥으로 사용합니다."
                ),
                selected_by_default=True,
            )
            for definition in PATENT_PRIOR_ART_CATEGORY_CATALOG.values()
        ],
        jurisdictions=[
            PatentPriorArtJurisdictionOption(
                id="KR",
                label_key="ai.patentPriorArt.jurisdictions.KR",
                fallback_label="대한민국",
                selected_by_default=True,
            ),
            PatentPriorArtJurisdictionOption(
                id="US",
                label_key="ai.patentPriorArt.jurisdictions.US",
                fallback_label="미국",
            ),
            PatentPriorArtJurisdictionOption(
                id="EP",
                label_key="ai.patentPriorArt.jurisdictions.EP",
                fallback_label="유럽",
            ),
            PatentPriorArtJurisdictionOption(
                id="WO",
                label_key="ai.patentPriorArt.jurisdictions.WO",
                fallback_label="PCT",
            ),
            PatentPriorArtJurisdictionOption(
                id="CN",
                label_key="ai.patentPriorArt.jurisdictions.CN",
                fallback_label="중국",
            ),
            PatentPriorArtJurisdictionOption(
                id="JP",
                label_key="ai.patentPriorArt.jurisdictions.JP",
                fallback_label="일본",
            ),
        ],
        report_formats=["html", "pdf", "docx", "summary_pdf", "summary_docx"],
        # Visual/OCR extraction is not part of this delivery: the merged parse-file
        # contract accepts only `file` (no per-call `visual` input), so there is no
        # way for a client to request it. The contract response field is retained
        # (reported False) for compatibility; enabling it is a Core-enablement
        # follow-up that would add a typed input and provider-routed OCR + limits.
        visual_extraction_available=False,
    )


def parse_file(
    _db: Session,
    *,
    workspace: Workspace,
    user: User,
    filename: str,
    mime_type: str,
    content: bytes,
) -> PatentPriorArtFileParseResponse:
    del workspace, user
    safe_filename, canonical_mime = _validate_upload(
        filename=filename,
        mime_type=mime_type,
        content=content,
    )
    try:
        bundle = extract_document(
            document_id="patent-prior-art-upload",
            filename=safe_filename,
            mime_type=canonical_mime,
            content=content,
        )
    except UnsupportedDocumentType as error:
        raise localized_http_exception(
            status_code=422,
            code="patent_prior_art.parse_failed",
        ) from error

    fast_text = bundle.normalized_text.strip()
    extracted_text = fast_text
    warnings: list[str] = []

    # Embedded-office (OLE) recursive extraction is intentionally not performed here:
    # the shared extractor does not bound the *inner* archive's members/expansion, so
    # a nested Office zip-bomb could bypass the per-request memory/CPU limits. Hardening
    # that inner path is a document_processing (Core) change; until then this app path
    # relies only on the outer, already-bounded `extract_document` fast text. Embedded
    # media are still counted for metadata below (namelist only; no decompression).
    if not extracted_text:
        raise localized_http_exception(
            status_code=422,
            code="patent_prior_art.extraction_empty",
        )
    if len(extracted_text) > _MAX_EXTRACTED_CHARS:
        extracted_text = extracted_text[:_MAX_EXTRACTED_CHARS]
        warnings.append("extraction_truncated")
    return PatentPriorArtFileParseResponse(
        filename=safe_filename,
        mime_type=canonical_mime,
        extracted_text=extracted_text,
        character_count=len(extracted_text),
        embedded_object_count=_count_embedded_objects(
            content, extension=Path(safe_filename).suffix.lower()
        ),
        warnings=warnings,
    )


def preview_query(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: PatentPriorArtQueryPreviewRequest,
) -> PatentPriorArtQueryPreviewResponse:
    invention_text = request.invention_text.strip()
    category_ids, jurisdictions = _validate_scope(
        category_ids=request.category_ids,
        jurisdictions=request.jurisdictions,
    )
    from ai_do_api.domains.patent_prior_art.pipeline import (  # noqa: PLC0415
        preview_patent_prior_art_search,
    )

    return preview_patent_prior_art_search(
        db,
        workspace_id=workspace.id,
        actor_user_id=user.id,
        invention_text=invention_text,
        category_ids=category_ids,
        jurisdictions=jurisdictions,
        explicit_applicants=(),
    )


_JOB_TITLE_MAX_CHARS = 60


def _derive_job_title(*, technology_summary: str, invention_text: str) -> str:
    """Compose a concise job title from the request (의뢰서) when the user left it blank.

    Prefers the already-summarised technology summary and falls back to the raw
    invention text: takes the leading sentence/line and trims to a short display
    length so the job list shows something meaningful instead of a blank title.
    """
    basis = (technology_summary or "").strip() or (invention_text or "").strip()
    if not basis:
        return "특허 선행기술 조사"
    basis = re.sub(r"\s+", " ", basis).strip()
    for terminator in ("다. ", ". ", "。", "! ", "? "):
        index = basis.find(terminator)
        if 10 <= index <= _JOB_TITLE_MAX_CHARS:
            end = index + (len(terminator.strip()) if terminator.strip() else 0)
            return basis[:end].strip()[:200]
    if len(basis) <= _JOB_TITLE_MAX_CHARS:
        return basis[:200]
    trimmed = basis[:_JOB_TITLE_MAX_CHARS].rstrip()
    space = trimmed.rfind(" ")
    if space >= 20:
        trimmed = trimmed[:space].rstrip()
    return (trimmed + "…")[:200]


def create_job(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: PatentPriorArtJobCreateRequest,
) -> PatentPriorArtJobOut:
    category_ids, jurisdictions = _validate_scope(
        category_ids=request.search_plan.category_ids.values,
        jurisdictions=request.jurisdictions,
    )
    normalized_plan = request.search_plan.model_copy(
        update={
            "category_ids": request.search_plan.category_ids.model_copy(
                update={"values": category_ids}
            )
        }
    )
    from ai_do_api.domains.patent_prior_art.planning import (  # noqa: PLC0415
        build_display_query,
        build_v1_idempotency_display_query,
        compile_provider_queries,
    )

    try:
        compiled_queries = compile_provider_queries(normalized_plan, jurisdictions)
    except ValueError as error:
        raise localized_http_exception(
            status_code=422,
            code="patent_prior_art.invalid_scope",
        ) from error
    # Keep the deployed v1 idempotency fingerprint stable across rollout and
    # rollback. The stored request may use a server-derived title and a de-duplicated
    # display query, but those presentation improvements must not turn an otherwise
    # identical retry into a 409 when the first job was created by the prior version.
    fingerprint_plan = normalized_plan.model_copy(
        update={
            "display_query": build_v1_idempotency_display_query(
                normalized_plan,
                jurisdictions,
            )
        }
    )
    fingerprint_request = request.model_copy(
        update={
            "title": request.title.strip()[:200],
            "idempotency_key": request.idempotency_key.strip(),
            "invention_text": request.invention_text.strip(),
            "technology_summary": request.technology_summary.strip(),
            "jurisdictions": list(jurisdictions),
            "search_plan": fingerprint_plan,
        }
    )
    normalized_plan = normalized_plan.model_copy(
        update={"display_query": build_display_query(compiled_queries)}
    )
    normalized_request = request.model_copy(
        update={
            "title": request.title.strip()[:200]
            or _derive_job_title(
                technology_summary=request.technology_summary,
                invention_text=request.invention_text,
            ),
            "idempotency_key": request.idempotency_key.strip(),
            "invention_text": request.invention_text.strip(),
            "technology_summary": request.technology_summary.strip(),
            "jurisdictions": list(jurisdictions),
            "search_plan": normalized_plan,
        }
    )
    if len(normalized_request.invention_text) < 30:
        raise localized_http_exception(
            status_code=422,
            code="patent_prior_art.invalid_scope",
        )

    request_fingerprint = _request_fingerprint(fingerprint_request)
    existing = _find_idempotent_job(
        db,
        workspace_id=workspace.id,
        owner_id=user.id,
        idempotency_key=normalized_request.idempotency_key,
    )
    if existing is not None:
        return project_job(_require_matching_idempotent_request(existing, request_fingerprint))

    job_id = _new_id()
    task_id = _new_id()
    store = patent_prior_art_artifact_store()
    try:
        input_storage_key = store.put_input_payload(
            workspace_id=workspace.id,
            job_id=job_id,
            payload=normalized_request.model_dump(mode="json"),
        )
    except Exception as error:
        logger.exception("patent_prior_art.create: input storage failed")
        raise localized_http_exception(
            status_code=502,
            code="patent_prior_art.storage_failed",
        ) from error

    row = PatentPriorArtJob(
        id=job_id,
        workspace_id=workspace.id,
        owner_id=user.id,
        title=normalized_request.title,
        idempotency_key=normalized_request.idempotency_key,
        request_fingerprint=request_fingerprint,
        status="queued",
        stage="queued",
        progress_percent=0,
        jurisdictions=jurisdictions,
        search_plan=normalized_plan.model_dump(mode="json"),
        input_storage_key=input_storage_key,
        celery_task_id=task_id,
        dispatch_attempts=1,
        dispatch_published_at=None,
    )
    try:
        db.add(row)
        db.commit()
    except IntegrityError:
        db.rollback()
        try:
            store.remove_objects([input_storage_key])
        except Exception:
            logger.exception("patent_prior_art.create: input compensation failed")
        existing = _find_idempotent_job(
            db,
            workspace_id=workspace.id,
            owner_id=user.id,
            idempotency_key=normalized_request.idempotency_key,
        )
        if existing is None:
            raise
        return project_job(_require_matching_idempotent_request(existing, request_fingerprint))
    except Exception:
        db.rollback()
        logger.exception("patent_prior_art.create: job persistence failed")
        try:
            store.remove_objects([input_storage_key])
        except Exception:
            logger.exception("patent_prior_art.create: input compensation failed")
        raise

    db.refresh(row)
    _publish_reserved_job(db, job_id=row.id, task_id=task_id)
    db.refresh(row)
    return project_job(row)


def republish_pending_jobs(
    db: Session,
    *,
    limit: int = 100,
    now: datetime | None = None,
    dispatcher: PatentPriorArtJobDispatcher | None = None,
) -> int:
    """Reserve and republish durable jobs using DB state as the authority."""

    reservation_time = now or _utcnow()
    rows = list(
        db.scalars(
            select(PatentPriorArtJob)
            .where(
                PatentPriorArtJob.status == "queued",
                PatentPriorArtJob.deletion_requested_at.is_(None),
                or_(
                    and_(
                        PatentPriorArtJob.stage == "retry_waiting",
                        PatentPriorArtJob.next_attempt_at.is_not(None),
                        PatentPriorArtJob.next_attempt_at <= reservation_time,
                    ),
                    and_(
                        PatentPriorArtJob.stage == "queued",
                        PatentPriorArtJob.dispatch_published_at.is_(None),
                        PatentPriorArtJob.updated_at
                        <= reservation_time - _DISPATCH_RESERVATION_GRACE,
                    ),
                ),
            )
            .order_by(PatentPriorArtJob.created_at.asc(), PatentPriorArtJob.id.asc())
            .limit(max(1, min(int(limit), _MAX_DISPATCH_BATCH)))
            .with_for_update(skip_locked=True)
        )
    )
    publications: list[tuple[str, str]] = []
    for row in rows:
        task_id = _new_id()
        row.celery_task_id = task_id
        row.dispatch_attempts += 1
        row.stage = "queued"
        row.next_attempt_at = None
        row.dispatch_published_at = None
        row.updated_at = reservation_time
        db.add(row)
        publications.append((row.id, task_id))
    db.commit()

    return sum(
        _publish_reserved_job(
            db,
            job_id=job_id,
            task_id=task_id,
            dispatcher=dispatcher,
        )
        for job_id, task_id in publications
    )


def recover_expired_jobs(
    db: Session,
    *,
    limit: int = 100,
    now: datetime | None = None,
) -> tuple[int, int]:
    """Fence expired executions, recovering once and terminalizing recurrence."""

    recovery_time = now or _utcnow()
    rows = list(
        db.scalars(
            select(PatentPriorArtJob)
            .where(
                PatentPriorArtJob.status == "running",
                PatentPriorArtJob.deletion_requested_at.is_(None),
                or_(
                    PatentPriorArtJob.execution_lease_expires_at <= recovery_time,
                    and_(
                        PatentPriorArtJob.execution_lease_expires_at.is_(None),
                        PatentPriorArtJob.updated_at <= recovery_time - _EXECUTION_LEASE_DURATION,
                    ),
                ),
            )
            .order_by(PatentPriorArtJob.updated_at.asc(), PatentPriorArtJob.id.asc())
            .limit(max(1, min(int(limit), _MAX_DISPATCH_BATCH)))
            .with_for_update(skip_locked=True)
        )
    )
    restarted = 0
    failed = 0
    for row in rows:
        if row.automatic_restart_count < 1:
            row.status = "queued"
            row.stage = "retry_waiting"
            row.failure_code = None
            row.celery_task_id = None
            row.dispatch_published_at = None
            row.execution_id = None
            row.execution_lease_expires_at = None
            row.next_attempt_at = recovery_time
            row.automatic_restart_count += 1
            row.completed_at = None
            row.updated_at = recovery_time
            restarted += 1
        else:
            row.status = "failed"
            row.stage = "failed"
            row.progress_percent = 100
            row.failure_code = "worker_lost"
            row.celery_task_id = None
            row.dispatch_published_at = None
            row.execution_id = None
            row.execution_lease_expires_at = None
            row.next_attempt_at = None
            row.completed_at = recovery_time
            row.updated_at = recovery_time
            failed += 1
        db.add(row)
    db.commit()
    return restarted, failed


def recover_jobs(
    db: Session,
    *,
    limit: int = 100,
    now: datetime | None = None,
) -> dict[str, int]:
    recovery_time = now or _utcnow()
    restarted, failed = recover_expired_jobs(
        db,
        limit=limit,
        now=recovery_time,
    )
    published = republish_pending_jobs(
        db,
        limit=limit,
        now=recovery_time,
    )
    return {
        "restarted": restarted,
        "failed": failed,
        "published": published,
    }


def _publish_reserved_job(
    db: Session,
    *,
    job_id: str,
    task_id: str,
    dispatcher: PatentPriorArtJobDispatcher | None = None,
) -> bool:
    try:
        (dispatcher or patent_prior_art_job_dispatcher()).dispatch(
            job_id,
            task_id=task_id,
        )
    except Exception:
        logger.warning(
            "patent_prior_art.dispatch: publication deferred for job %s",
            job_id,
            exc_info=True,
        )
        db.rollback()
        return False

    try:
        db.execute(
            update(PatentPriorArtJob)
            .where(
                PatentPriorArtJob.id == job_id,
                PatentPriorArtJob.status.in_(("queued", "running")),
                PatentPriorArtJob.celery_task_id == task_id,
                PatentPriorArtJob.dispatch_published_at.is_(None),
                PatentPriorArtJob.deletion_requested_at.is_(None),
            )
            .values(dispatch_published_at=_utcnow())
        )
        db.commit()
    except Exception:
        db.rollback()
        logger.warning(
            "patent_prior_art.dispatch: publication confirmation deferred for job %s",
            job_id,
            exc_info=True,
        )
    return True


def _request_fingerprint(request: PatentPriorArtJobCreateRequest) -> str:
    encoded = json.dumps(
        request.model_dump(mode="json"),
        ensure_ascii=False,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(encoded).hexdigest()


def _find_idempotent_job(
    db: Session,
    *,
    workspace_id: str,
    owner_id: str,
    idempotency_key: str,
) -> PatentPriorArtJob | None:
    return db.scalar(
        select(PatentPriorArtJob)
        .where(
            PatentPriorArtJob.workspace_id == workspace_id,
            PatentPriorArtJob.owner_id == owner_id,
            PatentPriorArtJob.idempotency_key == idempotency_key,
        )
        .limit(1)
    )


def _require_matching_idempotent_request(
    row: PatentPriorArtJob,
    request_fingerprint: str,
) -> PatentPriorArtJob:
    if row.request_fingerprint != request_fingerprint:
        raise localized_http_exception(
            status_code=409,
            code="patent_prior_art.invalid_scope",
        )
    return row


def list_jobs(
    db: Session, *, workspace: Workspace, user: User, limit: int
) -> PatentPriorArtJobListResponse:
    filters = (
        PatentPriorArtJob.workspace_id == workspace.id,
        PatentPriorArtJob.owner_id == user.id,
    )
    rows = (
        db.execute(
            select(PatentPriorArtJob)
            .where(*filters)
            .order_by(desc(PatentPriorArtJob.created_at))
            .limit(limit)
        )
        .scalars()
        .all()
    )
    total = db.execute(
        select(func.count()).select_from(PatentPriorArtJob).where(*filters)
    ).scalar_one()
    return PatentPriorArtJobListResponse(
        items=[project_job(row) for row in rows],
        total=total,
    )


def get_job(db: Session, *, workspace: Workspace, user: User, job_id: str) -> PatentPriorArtJobOut:
    return project_job(
        _load_job(
            db,
            workspace=workspace,
            user=user,
            job_id=job_id,
            include_deleted=True,
        )
    )


def cancel_job(
    db: Session, *, workspace: Workspace, user: User, job_id: str
) -> PatentPriorArtJobOut:
    row = _load_job(db, workspace=workspace, user=user, job_id=job_id)
    if row.status == "cancelled":
        return project_job(row)
    if row.status not in {"queued", "running"}:
        raise localized_http_exception(
            status_code=409,
            code="patent_prior_art.not_cancellable",
        )

    now = _utcnow()
    db.execute(
        update(PatentPriorArtJob)
        .where(
            PatentPriorArtJob.id == row.id,
            PatentPriorArtJob.workspace_id == workspace.id,
            PatentPriorArtJob.owner_id == user.id,
            PatentPriorArtJob.status.in_(("queued", "running")),
            PatentPriorArtJob.deletion_requested_at.is_(None),
        )
        .values(
            status="cancelled",
            stage="cancelled",
            failure_code=None,
            celery_task_id=None,
            dispatch_published_at=None,
            execution_id=None,
            execution_lease_expires_at=None,
            next_attempt_at=None,
            completed_at=now,
            updated_at=now,
        )
    )
    db.commit()
    db.expire(row)
    db.refresh(row)
    if row.status != "cancelled":
        raise localized_http_exception(
            status_code=409,
            code="patent_prior_art.not_cancellable",
        )
    return project_job(row)


def get_result(
    db: Session, *, workspace: Workspace, user: User, job_id: str
) -> PatentPriorArtResultResponse:
    row = _load_job(db, workspace=workspace, user=user, job_id=job_id)
    if row.status != "succeeded":
        raise localized_http_exception(
            status_code=409,
            code="patent_prior_art.not_ready",
        )

    candidates = (
        db.execute(
            select(PatentPriorArtCandidate)
            .where(
                PatentPriorArtCandidate.workspace_id == workspace.id,
                PatentPriorArtCandidate.job_id == row.id,
            )
            .order_by(PatentPriorArtCandidate.rank)
        )
        .scalars()
        .all()
    )
    executed_queries = (
        db.execute(
            select(PatentPriorArtExecutedQuery)
            .where(
                PatentPriorArtExecutedQuery.workspace_id == workspace.id,
                PatentPriorArtExecutedQuery.job_id == row.id,
            )
            .order_by(PatentPriorArtExecutedQuery.position)
        )
        .scalars()
        .all()
    )
    artifacts = (
        db.execute(
            select(PatentPriorArtArtifact)
            .where(
                PatentPriorArtArtifact.workspace_id == workspace.id,
                PatentPriorArtArtifact.job_id == row.id,
            )
            .order_by(PatentPriorArtArtifact.kind)
        )
        .scalars()
        .all()
    )
    report = next(
        (artifact for artifact in artifacts if artifact.kind == "report_markdown"),
        None,
    )
    if report is None:
        raise localized_http_exception(
            status_code=409,
            code="patent_prior_art.not_ready",
        )
    try:
        report_markdown = (
            patent_prior_art_artifact_store()
            .read_artifact(
                report.storage_key,
                expected_size=report.size_bytes,
            )
            .decode("utf-8")
        )
    except Exception as error:
        logger.exception("patent_prior_art.result: report read failed")
        raise localized_http_exception(
            status_code=409,
            code="patent_prior_art.not_ready",
        ) from error
    return project_result(
        row,
        candidates=list(candidates),
        executed_queries=list(executed_queries),
        artifacts=list(artifacts),
        report_markdown=report_markdown,
    )


def get_artifact(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    job_id: str,
    artifact_id: str,
) -> Response:
    row = _load_job(db, workspace=workspace, user=user, job_id=job_id)
    artifact = db.get(PatentPriorArtArtifact, artifact_id)
    if (
        artifact is None
        or artifact.workspace_id != workspace.id
        or artifact.job_id != row.id
        or artifact.kind not in {"result_json", "report_markdown"}
        or not storage_key_belongs_to_job(
            artifact.storage_key,
            workspace_id=workspace.id,
            job_id=row.id,
        )
    ):
        raise localized_http_exception(
            status_code=404,
            code="patent_prior_art.artifact_not_found",
        )
    try:
        content = patent_prior_art_artifact_store().read_artifact(
            artifact.storage_key,
            expected_size=artifact.size_bytes,
        )
    except Exception as error:
        logger.exception("patent_prior_art.artifact: read failed")
        raise localized_http_exception(
            status_code=502,
            code="patent_prior_art.artifact_read_failed",
        ) from error
    encoded_filename = quote(artifact.filename, safe="")
    return Response(
        content=content,
        media_type=artifact.mime_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": (f"attachment; filename*=UTF-8''{encoded_filename}"),
            "X-Content-Type-Options": "nosniff",
        },
    )


def get_report(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    job_id: str,
    report_format: PatentPriorArtReportFormat,
) -> Response:
    """Render a job-local structured result into a safe attachment response."""

    row = _load_job(db, workspace=workspace, user=user, job_id=job_id)
    if row.status != "succeeded":
        raise localized_http_exception(
            status_code=409,
            code="patent_prior_art.not_ready",
        )
    artifact = db.scalar(
        select(PatentPriorArtArtifact).where(
            PatentPriorArtArtifact.workspace_id == workspace.id,
            PatentPriorArtArtifact.job_id == row.id,
            PatentPriorArtArtifact.kind == "result_json",
        )
    )
    if (
        artifact is None
        or artifact.execution_id != row.execution_id
        or not storage_key_belongs_to_job(
            artifact.storage_key,
            workspace_id=workspace.id,
            job_id=row.id,
        )
    ):
        raise localized_http_exception(
            status_code=409,
            code="patent_prior_art.not_ready",
        )
    try:
        content = patent_prior_art_artifact_store().read_artifact(
            artifact.storage_key,
            expected_size=artifact.size_bytes,
        )
        payload = json.loads(content.decode("utf-8"))
        if not isinstance(payload, Mapping):
            raise ValueError("prior-art result payload must be an object")
    except Exception as error:
        logger.exception("patent_prior_art.report: structured result read failed")
        raise localized_http_exception(
            status_code=409,
            code="patent_prior_art.not_ready",
        ) from error
    # DB-authoritative header fields for the rich report (조사 ID / 조사 시작 /
    # 작성자) — these are not captured in the job-time rich context.
    rich_ctx = payload.get("rich")
    if isinstance(rich_ctx, dict):
        rich_ctx["job_id"] = row.id
        if row.created_at is not None:
            rich_ctx["created_at"] = row.created_at.isoformat(timespec="seconds")
        owner = db.get(User, row.owner_id)
        if owner is not None:
            rich_ctx["username"] = owner.display_name or owner.full_name
        # Fill the 선별 기준 method rows with accurate, provider/model-neutral text.
        # The engine's stored criteria hardcoded stale source-server model IDs
        # (e.g. multilingual-e5-base / Claude) that do not match this deployment's
        # inference-gateway embedding and admin-routed LLM workloads, so they are
        # stripped at job time and described at the method level here instead.
        rationale = rich_ctx.get("selection_rationale")
        criteria = rationale.get("criteria") if isinstance(rationale, dict) else None
        if isinstance(criteria, dict):
            criteria.setdefault("embedding_model", "다국어 문장 임베딩 (인퍼런스 게이트웨이 경유)")
            criteria.setdefault(
                "embedding_method",
                "제목·초록 임베딩 코사인 유사도 + BM25 희소검색 하이브리드, cross-encoder 재순위화",
            )
            # LLM 평가 모델 — 실제 워크로드 라우팅(로컬/외부)을 반영.
            llm_label = "등록 LLM 워크로드 (관리자 설정 라우팅 — 로컬/외부 모델)"
            try:
                from ai_do_api.domains.ai.model_settings_service import (  # noqa: PLC0415
                    resolve_ai_model_workload_route,
                )

                resolved_route = resolve_ai_model_workload_route(
                    db, workload_id="patent_prior_art.candidate_assessment"
                )
                route_label = "로컬 LLM" if resolved_route.route == "local" else "외부 LLM"
                llm_label = f"{route_label} — 등록 워크로드(관리자 설정 라우팅)"
            except Exception:  # noqa: BLE001 - best-effort; keep the neutral label
                logger.debug("patent_prior_art.report: LLM route resolve failed", exc_info=True)
            criteria["llm_judge_model"] = llm_label

    try:
        rendered = render_report_export(
            payload,
            report_format=report_format,
            job_id=row.id,
        )
    except ValueError:
        raise
    except Exception as error:
        logger.exception("patent_prior_art.report: rendering failed")
        raise localized_http_exception(
            status_code=502,
            code="patent_prior_art.artifact_read_failed",
        ) from error
    encoded_filename = quote(rendered.filename, safe="")
    return Response(
        content=rendered.content,
        media_type=rendered.media_type,
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"attachment; filename*=UTF-8''{encoded_filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


def delete_job(
    db: Session, *, workspace: Workspace, user: User, job_id: str
) -> PatentPriorArtDeleteResponse:
    row = _load_job(
        db,
        workspace=workspace,
        user=user,
        job_id=job_id,
        include_deleted=True,
    )
    now = row.deletion_requested_at or _utcnow()
    values: dict[str, object] = {
        "deletion_requested_at": now,
        "cleanup_failure_code": None,
        "status": "cancelled",
        "stage": "cancelled",
        "failure_code": None,
        "celery_task_id": None,
        "dispatch_published_at": None,
        "execution_id": None,
        "execution_lease_expires_at": None,
        "next_attempt_at": None,
        "completed_at": _utcnow(),
        "updated_at": _utcnow(),
    }
    db.execute(
        update(PatentPriorArtJob)
        .where(
            PatentPriorArtJob.id == row.id,
            PatentPriorArtJob.workspace_id == workspace.id,
            PatentPriorArtJob.owner_id == user.id,
        )
        .values(**values)
    )
    db.commit()
    db.refresh(row)

    recorded_keys = db.execute(
        select(PatentPriorArtArtifact.storage_key).where(
            PatentPriorArtArtifact.workspace_id == workspace.id,
            PatentPriorArtArtifact.job_id == row.id,
        )
    ).scalars()
    try:
        patent_prior_art_artifact_store().remove_job_objects(
            workspace_id=workspace.id,
            job_id=row.id,
            recorded_storage_keys=list(recorded_keys),
        )
    except Exception:
        logger.exception("patent_prior_art.delete: object cleanup failed")
        row.stage = "cleanup_pending"
        row.cleanup_failure_code = "storage_cleanup_failed"
        row.updated_at = _utcnow()
        db.add(row)
        db.commit()
        return PatentPriorArtDeleteResponse(id=row.id, deleted=False)

    db.delete(row)
    db.commit()
    return PatentPriorArtDeleteResponse(id=job_id, deleted=True)


def claim_job(
    db: Session,
    *,
    job_id: str,
    task_id: str | None = None,
) -> PatentPriorArtJob | None:
    """Atomically claim one precommitted delivery with a fresh execution fence."""

    now = _utcnow()
    execution_id = _new_id()
    if task_id is None:
        claimable = and_(
            PatentPriorArtJob.status == "queued",
            PatentPriorArtJob.stage == "queued",
        )
        claim_values: dict[str, object] = {}
    else:
        claimable = and_(
            PatentPriorArtJob.status == "queued",
            PatentPriorArtJob.stage == "queued",
            PatentPriorArtJob.celery_task_id == task_id,
        )
        claim_values = {"celery_task_id": task_id}
    claimed_id = db.execute(
        update(PatentPriorArtJob)
        .where(
            PatentPriorArtJob.id == job_id,
            claimable,
            PatentPriorArtJob.deletion_requested_at.is_(None),
        )
        .values(
            status="running",
            stage="loading_input",
            progress_percent=5,
            failure_code=None,
            execution_id=execution_id,
            execution_attempts=PatentPriorArtJob.execution_attempts + 1,
            execution_lease_expires_at=now + _EXECUTION_LEASE_DURATION,
            next_attempt_at=None,
            completed_at=None,
            updated_at=now,
            **claim_values,
        )
        .returning(PatentPriorArtJob.id)
    ).scalar_one_or_none()
    db.commit()
    if claimed_id is None:
        return None
    return db.get(PatentPriorArtJob, claimed_id)


def load_job_input(row: PatentPriorArtJob) -> PatentPriorArtJobCreateRequest:
    if not storage_key_belongs_to_job(
        row.input_storage_key,
        workspace_id=row.workspace_id,
        job_id=row.id,
    ):
        raise ValueError("prior-art job input key is outside the job scope")
    payload = patent_prior_art_artifact_store().read_input_payload(row.input_storage_key)
    return PatentPriorArtJobCreateRequest.model_validate(payload)


def can_execute_job(
    db: Session,
    row: PatentPriorArtJob,
    *,
    execution_id: str | None = None,
) -> bool:
    """Revalidate both the fenced delivery and owner access before provider work."""

    fenced_execution_id = execution_id or row.execution_id
    if fenced_execution_id is None:
        return False
    accessible_job_id = db.scalar(
        select(PatentPriorArtJob.id)
        .join(User, User.id == PatentPriorArtJob.owner_id)
        .join(
            WorkspaceUserBinding,
            WorkspaceUserBinding.user_id == User.id,
        )
        .join(
            Workspace,
            Workspace.id == WorkspaceUserBinding.workspace_id,
        )
        .where(
            PatentPriorArtJob.id == row.id,
            PatentPriorArtJob.workspace_id == row.workspace_id,
            PatentPriorArtJob.owner_id == row.owner_id,
            PatentPriorArtJob.status == "running",
            PatentPriorArtJob.execution_id == fenced_execution_id,
            PatentPriorArtJob.deletion_requested_at.is_(None),
            User.id == row.owner_id,
            User.status == "active",
            User.login_blocked.is_(False),
            Workspace.id == row.workspace_id,
            Workspace.active.is_(True),
            WorkspaceUserBinding.workspace_id == row.workspace_id,
        )
        .limit(1)
    )
    if accessible_job_id is None:
        return False
    return is_workspace_app_enabled(
        db,
        row.workspace_id,
        PATENT_PRIOR_ART_APP_ID,
    )


def update_stage(
    db: Session,
    row: PatentPriorArtJob,
    *,
    execution_id: str,
    stage: str,
    progress_percent: int,
) -> bool:
    if stage not in _STAGES - {
        "queued",
        "retry_waiting",
        "completed",
        "failed",
        "cancelled",
        "cleanup_pending",
    }:
        raise ValueError(f"invalid prior-art worker stage: {stage}")
    progress = max(1, min(int(progress_percent), 99))
    updated = db.execute(
        update(PatentPriorArtJob)
        .where(
            PatentPriorArtJob.id == row.id,
            PatentPriorArtJob.status == "running",
            PatentPriorArtJob.execution_id == execution_id,
            PatentPriorArtJob.deletion_requested_at.is_(None),
        )
        .values(
            stage=stage,
            progress_percent=progress,
            execution_lease_expires_at=_utcnow() + _EXECUTION_LEASE_DURATION,
            updated_at=_utcnow(),
        )
    ).rowcount
    db.commit()
    if updated:
        db.expire(row)
        return True
    return False


def renew_execution_lease(
    db: Session,
    *,
    job_id: str,
    execution_id: str,
    now: datetime | None = None,
) -> bool:
    heartbeat_time = now or _utcnow()
    updated = db.execute(
        update(PatentPriorArtJob)
        .where(
            PatentPriorArtJob.id == job_id,
            PatentPriorArtJob.status == "running",
            PatentPriorArtJob.execution_id == execution_id,
            PatentPriorArtJob.deletion_requested_at.is_(None),
        )
        .values(
            execution_lease_expires_at=heartbeat_time + _EXECUTION_LEASE_DURATION,
            updated_at=heartbeat_time,
        )
    ).rowcount
    db.commit()
    return bool(updated)


def schedule_automatic_restart(
    db: Session,
    row: PatentPriorArtJob,
    *,
    execution_id: str,
    now: datetime | None = None,
    delay: timedelta = _AUTOMATIC_RESTART_DELAY,
) -> bool:
    """Move a transient total-provider failure into one durable retry wait."""

    restart_time = now or _utcnow()
    updated = db.execute(
        update(PatentPriorArtJob)
        .where(
            PatentPriorArtJob.id == row.id,
            PatentPriorArtJob.status == "running",
            PatentPriorArtJob.execution_id == execution_id,
            PatentPriorArtJob.automatic_restart_count < 1,
            PatentPriorArtJob.deletion_requested_at.is_(None),
        )
        .values(
            status="queued",
            stage="retry_waiting",
            failure_code=None,
            celery_task_id=None,
            dispatch_published_at=None,
            execution_id=None,
            execution_lease_expires_at=None,
            next_attempt_at=restart_time + delay,
            automatic_restart_count=PatentPriorArtJob.automatic_restart_count + 1,
            completed_at=None,
            updated_at=restart_time,
        )
    ).rowcount
    db.commit()
    if updated:
        db.expire(row)
    return bool(updated)


def is_cancelled(db: Session, *, job_id: str, execution_id: str) -> bool:
    state = db.execute(
        select(
            PatentPriorArtJob.status,
            PatentPriorArtJob.deletion_requested_at,
            PatentPriorArtJob.execution_id,
        ).where(PatentPriorArtJob.id == job_id)
    ).one_or_none()
    return (
        state is None or state[0] != "running" or state[1] is not None or state[2] != execution_id
    )


def persist_result(
    db: Session,
    row: PatentPriorArtJob,
    *,
    execution_id: str,
    result: object,
) -> None:
    result_json = str(getattr(result, "result_json"))
    report_markdown = str(getattr(result, "report_markdown"))
    candidates = list(getattr(result, "candidates"))
    executed_queries = list(getattr(result, "executed_queries"))
    store = patent_prior_art_artifact_store()
    stored_artifacts: tuple[StoredArtifact, StoredArtifact] | None = None
    commit_attempted = False
    try:
        locked_row = db.execute(
            select(PatentPriorArtJob)
            .where(
                PatentPriorArtJob.id == row.id,
                PatentPriorArtJob.status == "running",
                PatentPriorArtJob.execution_id == execution_id,
                PatentPriorArtJob.deletion_requested_at.is_(None),
            )
            .with_for_update()
        ).scalar_one_or_none()
        if locked_row is None:
            raise PatentPriorArtPersistenceCancelled(row.id)
        store.remove_stale_execution_objects(
            workspace_id=locked_row.workspace_id,
            job_id=locked_row.id,
            keep_execution_id=execution_id,
        )
        stored_artifacts = store.put_result_artifacts(
            workspace_id=locked_row.workspace_id,
            job_id=locked_row.id,
            execution_id=execution_id,
            result_json=result_json,
            report_markdown=report_markdown,
        )
        now = _utcnow()
        succeeded = db.execute(
            update(PatentPriorArtJob)
            .where(
                PatentPriorArtJob.id == row.id,
                PatentPriorArtJob.status == "running",
                PatentPriorArtJob.execution_id == execution_id,
                PatentPriorArtJob.deletion_requested_at.is_(None),
            )
            .values(
                status="succeeded",
                stage="completed",
                progress_percent=100,
                failure_code=None,
                celery_task_id=None,
                dispatch_published_at=None,
                execution_lease_expires_at=None,
                next_attempt_at=None,
                completed_at=now,
                updated_at=now,
            )
        ).rowcount
        if not succeeded:
            raise PatentPriorArtPersistenceCancelled(row.id)
        _replace_candidates(db, locked_row, candidates)
        _replace_executed_queries(db, locked_row, executed_queries)
        _replace_artifacts(
            db,
            locked_row,
            execution_id=execution_id,
            artifacts=stored_artifacts,
        )
        commit_attempted = True
        db.commit()
    except Exception:
        db.rollback()
        if stored_artifacts is not None and not commit_attempted:
            try:
                store.remove_objects([artifact.storage_key for artifact in stored_artifacts])
            except Exception:
                logger.exception("patent_prior_art.persist: failed projection cleanup failed")
        elif stored_artifacts is not None:
            logger.warning(
                "patent_prior_art.persist: commit outcome ambiguous; retaining fenced artifacts"
            )
        raise
    db.expire(row)


def mark_failed(
    db: Session,
    row: PatentPriorArtJob,
    *,
    execution_id: str,
    failure_code: str = "pipeline_failed",
) -> bool:
    db.rollback()
    code = failure_code if failure_code in _SAFE_FAILURE_CODES else "pipeline_failed"
    now = _utcnow()
    updated = db.execute(
        update(PatentPriorArtJob)
        .where(
            PatentPriorArtJob.id == row.id,
            PatentPriorArtJob.status.in_(("queued", "running")),
            PatentPriorArtJob.execution_id == execution_id,
            PatentPriorArtJob.deletion_requested_at.is_(None),
        )
        .values(
            status="failed",
            stage="failed",
            progress_percent=100,
            failure_code=code,
            celery_task_id=None,
            dispatch_published_at=None,
            execution_lease_expires_at=None,
            next_attempt_at=None,
            completed_at=now,
            updated_at=now,
        )
    ).rowcount
    db.commit()
    if updated:
        db.expire(row)
    return bool(updated)


def mark_cancelled(
    db: Session,
    row: PatentPriorArtJob,
    *,
    execution_id: str,
) -> bool:
    now = _utcnow()
    updated = db.execute(
        update(PatentPriorArtJob)
        .where(
            PatentPriorArtJob.id == row.id,
            PatentPriorArtJob.status.in_(("queued", "running")),
            PatentPriorArtJob.execution_id == execution_id,
        )
        .values(
            status="cancelled",
            stage="cancelled",
            failure_code=None,
            celery_task_id=None,
            dispatch_published_at=None,
            execution_id=None,
            execution_lease_expires_at=None,
            next_attempt_at=None,
            completed_at=now,
            updated_at=now,
        )
    ).rowcount
    db.commit()
    if updated:
        db.expire(row)
    return bool(updated)


def _load_job(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    job_id: str,
    include_deleted: bool = False,
) -> PatentPriorArtJob:
    row = db.get(PatentPriorArtJob, job_id)
    if (
        row is None
        or row.workspace_id != workspace.id
        or row.owner_id != user.id
        or (row.deletion_requested_at is not None and not include_deleted)
    ):
        raise localized_http_exception(
            status_code=404,
            code="patent_prior_art.not_found",
        )
    return row


def _validate_scope(
    *, category_ids: list[str], jurisdictions: list[str]
) -> tuple[list[str], list[str]]:
    allowed_categories = {option.id for option in config().categories}
    allowed_jurisdictions = {option.id for option in config().jurisdictions}
    normalized_categories = list(dict.fromkeys(category_ids))
    normalized_jurisdictions = list(dict.fromkeys(value.upper() for value in jurisdictions))
    if (
        any(value not in allowed_categories for value in normalized_categories)
        or not normalized_jurisdictions
        or any(value not in allowed_jurisdictions for value in normalized_jurisdictions)
    ):
        raise localized_http_exception(
            status_code=422,
            code="patent_prior_art.invalid_scope",
        )
    return normalized_categories, normalized_jurisdictions


def _validate_upload(*, filename: str, mime_type: str, content: bytes) -> tuple[str, str]:
    if not content:
        raise localized_http_exception(
            status_code=422,
            code="patent_prior_art.empty_upload",
        )
    if len(content) > _MAX_UPLOAD_BYTES:
        raise localized_http_exception(
            status_code=413,
            code="patent_prior_art.request_too_large",
        )
    safe_filename = Path((filename or "").replace("\\", "/")).name.strip()
    extension = Path(safe_filename).suffix.lower()
    normalized_mime = (mime_type or "").split(";", 1)[0].strip().lower()
    if (
        not safe_filename
        or extension not in _SUPPORTED_EXTENSIONS
        or normalized_mime
        and normalized_mime not in _ALLOWED_MIME_TYPES[extension]
    ):
        raise localized_http_exception(
            status_code=422,
            code="patent_prior_art.invalid_file_type",
        )
    if extension == ".pdf":
        valid_magic = content.startswith(b"%PDF-")
    else:
        valid_magic = _office_package_has_marker(
            content,
            marker=_OFFICE_MARKERS[extension],
        )
    if not valid_magic:
        raise localized_http_exception(
            status_code=422,
            code="patent_prior_art.invalid_file_type",
        )
    return safe_filename[:180], _CANONICAL_MIME_TYPES[extension]


def _office_package_has_marker(content: bytes, *, marker: str) -> bool:
    if not content.startswith((b"PK\x03\x04", b"PK\x05\x06", b"PK\x07\x08")):
        return False
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            infos = archive.infolist()
            return not _office_archive_exceeds_limits(infos) and marker in archive.namelist()
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError):
        return False


def _office_archive_exceeds_limits(infos: list[zipfile.ZipInfo]) -> bool:
    entry_count = 0
    compressed_bytes = 0
    uncompressed_bytes = 0
    for info in infos:
        if info.is_dir():
            continue
        entry_count += 1
        compressed_size = max(0, info.compress_size)
        uncompressed_size = max(0, info.file_size)
        compressed_bytes += compressed_size
        uncompressed_bytes += uncompressed_size
        if (
            info.flag_bits & 0x1
            or entry_count > _MAX_OFFICE_ARCHIVE_ENTRIES
            or uncompressed_size > _MAX_OFFICE_ARCHIVE_MEMBER_BYTES
            or uncompressed_bytes > _MAX_OFFICE_ARCHIVE_UNCOMPRESSED_BYTES
        ):
            return True
    return bool(
        compressed_bytes
        and uncompressed_bytes / compressed_bytes > _MAX_OFFICE_ARCHIVE_EXPANSION_RATIO
    )


def _count_embedded_objects(content: bytes, *, extension: str) -> int:
    """Count embedded media parts (images/figures) inside an office package."""
    if extension == ".pdf":
        return 0
    try:
        with zipfile.ZipFile(BytesIO(content)) as archive:
            return sum(
                1
                for name in archive.namelist()
                if name.startswith(_OFFICE_MEDIA_PREFIXES + _OFFICE_EMBEDDING_PREFIXES)
                and not name.endswith("/")
            )
    except (zipfile.BadZipFile, zipfile.LargeZipFile, RuntimeError):
        return 0


def _object_mapping(value: object) -> dict[str, Any]:
    if isinstance(value, BaseModel):
        return value.model_dump(mode="json")
    if isinstance(value, Mapping):
        return {str(key): item for key, item in value.items()}
    return {
        name: getattr(value, name)
        for name in (
            "rank",
            "publication_number",
            "title",
            "assignees",
            "jurisdiction",
            "filing_date",
            "publication_date",
            "classification_codes",
            "abstract",
            "summary",
            "relevance_band",
            "match_reasons",
            "external_url",
            "source_id",
            "source_label",
            "query_text",
            "result_count",
            "status",
            "failure_code",
        )
        if hasattr(value, name)
    }


def _replace_candidates(db: Session, row: PatentPriorArtJob, candidates: list[object]) -> None:
    db.execute(delete(PatentPriorArtCandidate).where(PatentPriorArtCandidate.job_id == row.id))
    for position, candidate in enumerate(candidates, start=1):
        data = _object_mapping(candidate)
        data.setdefault("rank", position)
        projected = PatentPriorArtCandidateOut.model_validate(data)
        db.add(
            PatentPriorArtCandidate(
                id=_new_id(),
                workspace_id=row.workspace_id,
                job_id=row.id,
                rank=position,
                publication_number=projected.publication_number[:96],
                title=projected.title[:1000],
                assignees=list(projected.assignees[:30]),
                jurisdiction=projected.jurisdiction[:8],
                filing_date=projected.filing_date,
                publication_date=projected.publication_date,
                classification_codes=list(projected.classification_codes[:50]),
                abstract=projected.abstract,
                summary=projected.summary,
                relevance_band=projected.relevance_band,
                match_reasons=list(projected.match_reasons[:30]),
                external_url=(projected.external_url or "")[:2048] or None,
            )
        )


def _replace_executed_queries(
    db: Session, row: PatentPriorArtJob, executed_queries: list[object]
) -> None:
    db.execute(
        delete(PatentPriorArtExecutedQuery).where(PatentPriorArtExecutedQuery.job_id == row.id)
    )
    for position, executed_query in enumerate(executed_queries, start=1):
        projected = PatentPriorArtExecutedQueryOut.model_validate(_object_mapping(executed_query))
        db.add(
            PatentPriorArtExecutedQuery(
                id=_new_id(),
                workspace_id=row.workspace_id,
                job_id=row.id,
                position=position,
                source_id=projected.source_id[:80],
                source_label=projected.source_label[:160],
                jurisdiction=projected.jurisdiction[:8],
                query_text=projected.query_text,
                result_count=projected.result_count,
                status=projected.status,
                failure_code=projected.failure_code,
            )
        )


def _replace_artifacts(
    db: Session,
    row: PatentPriorArtJob,
    *,
    execution_id: str,
    artifacts: tuple[StoredArtifact, StoredArtifact],
) -> None:
    db.execute(delete(PatentPriorArtArtifact).where(PatentPriorArtArtifact.job_id == row.id))
    for artifact in artifacts:
        db.add(
            PatentPriorArtArtifact(
                id=_new_id(),
                workspace_id=row.workspace_id,
                job_id=row.id,
                execution_id=execution_id,
                kind=artifact.kind,
                filename=artifact.filename,
                mime_type=artifact.mime_type,
                size_bytes=artifact.size_bytes,
                storage_key=artifact.storage_key,
            )
        )


__all__ = [
    "PatentPriorArtPersistenceCancelled",
    "can_execute_job",
    "cancel_job",
    "claim_job",
    "config",
    "create_job",
    "delete_job",
    "get_artifact",
    "get_job",
    "get_report",
    "get_result",
    "is_cancelled",
    "list_jobs",
    "load_job_input",
    "mark_cancelled",
    "mark_failed",
    "parse_file",
    "persist_result",
    "preview_query",
    "recover_expired_jobs",
    "recover_jobs",
    "renew_execution_lease",
    "republish_pending_jobs",
    "schedule_automatic_restart",
    "update_stage",
]
