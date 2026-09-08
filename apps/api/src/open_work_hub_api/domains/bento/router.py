from __future__ import annotations

import json
import uuid
from datetime import UTC, datetime
from typing import Any, Literal

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    resolve_ai_model_workload_route,
)
from open_work_hub_api.domains.ai_graph.contracts import (
    AiGraphNodeSpec,
    AiGraphRunRequest,
    AiGraphSpec,
)
from open_work_hub_api.domains.ai_graph.dispatch import stage_graph_dispatch
from open_work_hub_api.domains.ai_graph.models import AiGraphRun
from open_work_hub_api.domains.ai_graph.publication import publish_pending_graph_dispatches
from open_work_hub_api.domains.ai_graph.repository import (
    AiGraphRunInputRepository,
    AiGraphRunRepository,
)
from open_work_hub_api.domains.auth.app_gate import require_app_access
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.bento import (
    BENTO_EDIT_WORKLOAD_ID,
    BENTO_GENERATE_WORKLOAD_ID,
)
from open_work_hub_api.domains.bento.app_catalog import BENTO_APP
from open_work_hub_api.domains.bento.execution import (
    BENTO_AGENT_GRAPH_ID,
    BENTO_AGENT_GRAPH_VERSION,
)
from open_work_hub_api.domains.bento.generation import (
    BENTO_GENERATION_MAX_SLIDES,
    BentoGenerationLanguage,
)
from open_work_hub_api.domains.bento.models import BentoAiJob, BentoAiJobInput, BentoDocument
from open_work_hub_api.domains.content_access.ownership import record_ownership_transition

require_bento_app_enabled = require_app_access(
    BENTO_APP.app_id,
    error_code="app.access_required",
)

router = APIRouter(
    prefix="/bento",
    tags=["bento"],
    dependencies=[Depends(require_bento_app_enabled)],
)

BentoHubView = Literal["all", "mine", "archived"]
BentoSortBy = Literal["updated_at", "created_at", "title"]
BentoSortDir = Literal["asc", "desc"]
BentoVisibility = Literal["personal", "company"]
BENTO_DOCUMENT_MAX_BYTES = 25 * 1024 * 1024
_DEFAULT_FONT_STACK = (
    "-apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


def _default_document_json(title: str) -> str:
    now = datetime.now(UTC).isoformat()
    return json.dumps(
        {
            "format": "bento/slides",
            "version": 1,
            "docId": str(uuid.uuid4()),
            "title": title,
            "size": {"width": 1280, "height": 720},
            "theme": {
                "background": "#FFFFFF",
                "color": "#1E2A3A",
                "accent": "#F7A600",
                "fontFamily": _DEFAULT_FONT_STACK,
            },
            "slides": [
                {
                    "id": f"slide-{uuid.uuid4()}",
                    "background": "#FFFFFF",
                    "transition": "fade",
                    "elements": [],
                    "notes": "",
                }
            ],
            "modified": now,
        },
        ensure_ascii=False,
        separators=(",", ":"),
    )


def _validated_document_json(value: str) -> tuple[str, dict[str, Any]]:
    if len(value.encode("utf-8")) > BENTO_DOCUMENT_MAX_BYTES:
        raise localized_http_exception(status_code=413, code="bento.document_too_large")
    try:
        document = json.loads(value)
    except json.JSONDecodeError as exc:
        raise localized_http_exception(status_code=400, code="bento.invalid_document") from exc
    if (
        not isinstance(document, dict)
        or document.get("format") != "bento/slides"
        or not isinstance(document.get("slides"), list)
        or len(document["slides"]) == 0
    ):
        raise localized_http_exception(status_code=400, code="bento.invalid_document")
    title = document.get("title")
    if not isinstance(title, str) or not title.strip() or len(title.strip()) > 200:
        raise localized_http_exception(status_code=400, code="bento.invalid_document_title")
    return (
        json.dumps(document, ensure_ascii=False, separators=(",", ":")),
        document,
    )


class CreateBentoDocumentRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    company_admin_read_acknowledged: bool = False
    visibility: BentoVisibility = "personal"
    document_json: str | None = Field(default=None, max_length=BENTO_DOCUMENT_MAX_BYTES)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str) -> str:
        title = value.strip()
        if not title:
            raise ValueError("title must not be blank")
        return title


class UpdateBentoDocumentRequest(BaseModel):
    version: int = Field(..., ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    company_admin_read_acknowledged: bool = False
    visibility: BentoVisibility | None = None
    document_json: str | None = Field(default=None, max_length=BENTO_DOCUMENT_MAX_BYTES)

    @field_validator("title")
    @classmethod
    def validate_title(cls, value: str | None) -> str | None:
        if value is None:
            return None
        title = value.strip()
        if not title:
            raise ValueError("title must not be blank")
        return title


class GenerateBentoDocumentRequest(BaseModel):
    prompt: str = Field(..., min_length=3, max_length=12_000)
    slide_count: int = Field(default=6, ge=3, le=BENTO_GENERATION_MAX_SLIDES)
    language: BentoGenerationLanguage = "auto"
    company_admin_read_acknowledged: bool = False
    visibility: Literal["personal"] = "personal"

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        prompt = value.strip()
        if len(prompt) < 3:
            raise ValueError("prompt must not be blank")
        return prompt


class EditBentoDocumentWithAiRequest(BaseModel):
    version: int = Field(..., ge=1)
    prompt: str = Field(..., min_length=3, max_length=12_000)
    language: BentoGenerationLanguage = "auto"

    @field_validator("prompt")
    @classmethod
    def validate_prompt(cls, value: str) -> str:
        prompt = value.strip()
        if len(prompt) < 3:
            raise ValueError("prompt must not be blank")
        return prompt


class BentoDocumentItem(BaseModel):
    id: str
    title: str
    visibility: BentoVisibility
    version: int
    created_by_id: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    can_edit: bool
    can_manage: bool


class BentoDocumentDetail(BentoDocumentItem):
    document_json: str


class BentoHubResponse(BaseModel):
    items: list[BentoDocumentItem]
    view: BentoHubView
    page: int
    page_size: int
    total: int


class BentoAiJobResponse(BaseModel):
    id: str
    kind: Literal["create", "edit"]
    status: Literal["queued", "running", "succeeded", "failed", "cancelled"]
    runtime_adapter_id: str
    stage: str | None
    progress_percent: int
    status_message_key: str | None
    error_code: str | None
    target_document_id: str | None
    result_document_id: str | None
    result_version: int | None
    cancellable: bool
    created_at: datetime
    updated_at: datetime


def _access_clause(current_user: User):
    return or_(
        BentoDocument.owner_id == current_user.id,
        BentoDocument.visibility == "company",
    )


def _can_manage(document: BentoDocument, *, current_user: User) -> bool:
    return document.owner_id == current_user.id


def _load_or_404(
    db: Session,
    *,
    document_id: str,
    current_user: User,
) -> BentoDocument:
    document = db.scalar(
        select(BentoDocument)
        .options(selectinload(BentoDocument.owner))
        .where(
            BentoDocument.id == document_id,
            _access_clause(current_user),
        )
    )
    if document is None:
        raise localized_http_exception(status_code=404, code="bento.not_found")
    return document


def _serialize_item(
    document: BentoDocument,
    *,
    current_user: User,
) -> BentoDocumentItem:
    can_manage = _can_manage(
        document,
        current_user=current_user,
    )
    return BentoDocumentItem(
        id=document.id,
        title=document.title,
        visibility=document.visibility,
        version=document.version,
        created_by_id=document.owner_id,
        created_by_name=document.owner.full_name if document.owner else "",
        created_at=document.created_at,
        updated_at=document.updated_at,
        archived_at=document.archived_at,
        can_edit=document.owner_id == current_user.id and document.archived_at is None,
        can_manage=can_manage,
    )


def _serialize_detail(
    document: BentoDocument,
    *,
    current_user: User,
) -> BentoDocumentDetail:
    item = _serialize_item(
        document,
        current_user=current_user,
    )
    return BentoDocumentDetail(**item.model_dump(), document_json=document.document_json)


def _persist_document(
    db: Session,
    *,
    current_user: User,
    title: str,
    visibility: BentoVisibility,
    document_json: str,
    company_admin_read_acknowledged: bool,
) -> BentoDocument:
    now = _utcnow()
    document = BentoDocument(
        id=str(uuid.uuid4()),
        owner_id=current_user.id,
        title=title,
        visibility=visibility,
        document_json=document_json,
        version=1,
        created_at=now,
        updated_at=now,
    )
    record_ownership_transition(
        db,
        actor_user_id=current_user.id,
        resource_kind="bento",
        resource_id=document.id,
        current_kind="personal",
        next_kind=visibility,
        company_admin_read_acknowledged=company_admin_read_acknowledged,
    )
    db.add(document)
    db.commit()
    return _load_or_404(
        db,
        document_id=document.id,
        current_user=current_user,
    )


def _serialize_ai_job(job: BentoAiJob, run: AiGraphRun) -> BentoAiJobResponse:
    return BentoAiJobResponse(
        id=job.id,
        kind=job.kind,  # type: ignore[arg-type]
        status=job.status,  # type: ignore[arg-type]
        runtime_adapter_id=job.runtime_adapter_id,
        stage=run.stage,
        progress_percent=run.progress_percent,
        status_message_key=run.status_message_key,
        error_code=job.error_code or run.error_code,
        target_document_id=job.target_document_id,
        result_document_id=job.result_document_id,
        result_version=job.result_version,
        cancellable=job.status in {"queued", "running"},
        created_at=job.created_at,
        updated_at=max(job.updated_at, run.updated_at),
    )


def _resolve_bento_runtime(db: Session, *, workload_id: str) -> str:
    try:
        route = resolve_ai_model_workload_route(db, workload_id=workload_id)
    except AiModelSettingsError as exc:
        raise localized_http_exception(status_code=exc.status_code, code=exc.code) from exc
    return route.runtime_adapter_id


def _stage_bento_ai_job(
    db: Session,
    *,
    current_user: User,
    kind: Literal["create", "edit"],
    prompt: str,
    language: BentoGenerationLanguage,
    runtime_adapter_id: str,
    visibility: BentoVisibility,
    slide_count: int | None,
    target_document: BentoDocument | None = None,
) -> BentoAiJobResponse:
    if kind == "edit" and target_document is not None:
        existing = db.scalar(
            select(BentoAiJob).where(
                BentoAiJob.target_document_id == target_document.id,
                BentoAiJob.status.in_(("queued", "running")),
            )
        )
        if existing is not None:
            raise localized_http_exception(
                status_code=409,
                code="bento.ai_edit_already_running",
            )
    prepared = stage_graph_dispatch(
        db,
        run_request=AiGraphRunRequest(
            requested_by_user_id=current_user.id,
            app_id="bento",
            graph=AiGraphSpec(
                graph_id=BENTO_AGENT_GRAPH_ID,
                graph_version=BENTO_AGENT_GRAPH_VERSION,
                nodes=(
                    AiGraphNodeSpec(
                        node_id="bento.agent.run",
                        purpose="Create or revise and validate an editable Bento document",
                    ),
                ),
            ),
            inputs={"kind": kind},
            visibility="private",
        ),
    )
    now = _utcnow()
    job = BentoAiJob(
        id=prepared.graph_run.id,
        requested_by_id=current_user.id,
        kind=kind,
        status="queued",
        runtime_adapter_id=runtime_adapter_id,
        target_document_id=target_document.id if target_document else None,
        base_version=target_document.version if target_document else None,
        visibility=visibility,
        slide_count=slide_count,
        language=language,
        created_at=now,
        updated_at=now,
    )
    db.add(job)
    db.add(
        BentoAiJobInput(
            job_id=job.id,
            prompt=prompt,
            current_document_json=(target_document.document_json if target_document else None),
            created_at=now,
        )
    )
    try:
        db.commit()
    except IntegrityError as exc:
        db.rollback()
        constraint_name = getattr(getattr(exc.orig, "diag", None), "constraint_name", None)
        if constraint_name == "uq_bento_ai_jobs_active_target":
            raise localized_http_exception(
                status_code=409,
                code="bento.ai_edit_already_running",
            ) from exc
        raise
    db.refresh(prepared.graph_run)
    db.refresh(job)
    publish_pending_graph_dispatches(db, limit=25)
    return _serialize_ai_job(job, prepared.graph_run)


@router.get("/hub", response_model=BentoHubResponse)
def list_bento_hub(
    view: BentoHubView = Query(default="all"),
    q: str = Query(default=""),
    sort_by: BentoSortBy = Query(default="updated_at"),
    sort_dir: BentoSortDir = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BentoHubResponse:
    clauses = [
        _access_clause(current_user),
    ]
    clauses.append(
        BentoDocument.archived_at.is_not(None)
        if view == "archived"
        else BentoDocument.archived_at.is_(None)
    )
    if view == "mine":
        clauses.append(BentoDocument.owner_id == current_user.id)
    if q.strip():
        clauses.append(BentoDocument.title.ilike(f"%{q.strip()}%"))

    total = db.scalar(select(func.count()).select_from(BentoDocument).where(*clauses)) or 0
    sort_column = {
        "created_at": BentoDocument.created_at,
        "title": BentoDocument.title,
        "updated_at": BentoDocument.updated_at,
    }[sort_by]
    order_by = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
    documents = db.scalars(
        select(BentoDocument)
        .options(selectinload(BentoDocument.owner))
        .where(*clauses)
        .order_by(order_by, BentoDocument.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    return BentoHubResponse(
        items=[
            _serialize_item(
                document,
                current_user=current_user,
            )
            for document in documents
        ],
        view=view,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post(
    "/items",
    response_model=BentoDocumentDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_bento_document(
    payload: CreateBentoDocumentRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BentoDocumentDetail:
    title = payload.title.strip()
    raw_document = payload.document_json or _default_document_json(title)
    document_json, parsed = _validated_document_json(raw_document)
    parsed["title"] = title
    document_json = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    document = _persist_document(
        db,
        current_user=current_user,
        title=title,
        visibility=payload.visibility,
        document_json=document_json,
        company_admin_read_acknowledged=payload.company_admin_read_acknowledged,
    )
    return _serialize_detail(
        document,
        current_user=current_user,
    )


@router.post(
    "/items/generate",
    response_model=BentoAiJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def generate_bento_document(
    payload: GenerateBentoDocumentRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BentoAiJobResponse:
    return _stage_bento_ai_job(
        db,
        current_user=current_user,
        kind="create",
        prompt=payload.prompt,
        language=payload.language,
        runtime_adapter_id=_resolve_bento_runtime(db, workload_id=BENTO_GENERATE_WORKLOAD_ID),
        visibility=payload.visibility,
        slide_count=payload.slide_count,
    )


@router.post(
    "/items/{document_id}/ai-edit",
    response_model=BentoAiJobResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
def edit_bento_document_with_ai(
    document_id: str,
    payload: EditBentoDocumentWithAiRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BentoAiJobResponse:
    document = _load_or_404(
        db,
        document_id=document_id,
        current_user=current_user,
    )
    if document.owner_id != current_user.id:
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    if document.archived_at is not None:
        raise localized_http_exception(status_code=409, code="bento.archived")
    if document.version != payload.version:
        raise localized_http_exception(status_code=409, code="bento.version_conflict")

    return _stage_bento_ai_job(
        db,
        current_user=current_user,
        kind="edit",
        prompt=payload.prompt,
        language=payload.language,
        runtime_adapter_id=_resolve_bento_runtime(db, workload_id=BENTO_EDIT_WORKLOAD_ID),
        visibility=document.visibility,  # type: ignore[arg-type]
        slide_count=None,
        target_document=document,
    )


@router.get("/ai-jobs", response_model=list[BentoAiJobResponse])
def list_bento_ai_jobs(
    limit: int = Query(default=20, ge=1, le=100),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[BentoAiJobResponse]:
    rows = db.execute(
        select(BentoAiJob, AiGraphRun)
        .join(AiGraphRun, AiGraphRun.id == BentoAiJob.id)
        .where(
            BentoAiJob.requested_by_id == current_user.id,
        )
        .order_by(BentoAiJob.created_at.desc())
        .limit(limit)
    ).all()
    return [_serialize_ai_job(job, run) for job, run in rows]


@router.get("/ai-jobs/{job_id}", response_model=BentoAiJobResponse)
def get_bento_ai_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BentoAiJobResponse:
    row = db.execute(
        select(BentoAiJob, AiGraphRun)
        .join(AiGraphRun, AiGraphRun.id == BentoAiJob.id)
        .where(
            BentoAiJob.id == job_id,
            BentoAiJob.requested_by_id == current_user.id,
        )
    ).one_or_none()
    if row is None:
        raise localized_http_exception(status_code=404, code="bento.ai_job_not_found")
    return _serialize_ai_job(row[0], row[1])


@router.post("/ai-jobs/{job_id}/cancel", response_model=BentoAiJobResponse)
def cancel_bento_ai_job(
    job_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BentoAiJobResponse:
    row = db.execute(
        select(BentoAiJob, AiGraphRun)
        .join(AiGraphRun, AiGraphRun.id == BentoAiJob.id)
        .where(
            BentoAiJob.id == job_id,
            BentoAiJob.requested_by_id == current_user.id,
        )
        .with_for_update()
    ).one_or_none()
    if row is None:
        raise localized_http_exception(status_code=404, code="bento.ai_job_not_found")
    job, run = row
    if job.status == "queued":
        now = _utcnow()
        job.status = "cancelled"
        job.cancel_requested_at = now
        job.finished_at = now
        job.updated_at = now
        AiGraphRunRepository(db).transition(
            job.id,
            "cancelled",
            stage="bento.ai.cancelled",
            status_message_key="bento.ai.cancelled",
        )
        job_input = db.get(BentoAiJobInput, job.id)
        if job_input is not None:
            db.delete(job_input)
        AiGraphRunInputRepository(db).delete_after_terminal(job.id)
    elif job.status == "running" and job.cancel_requested_at is None:
        job.cancel_requested_at = _utcnow()
        job.updated_at = _utcnow()
    db.commit()
    db.refresh(job)
    db.refresh(run)
    return _serialize_ai_job(job, run)


@router.get("/items/{document_id}", response_model=BentoDocumentDetail)
def get_bento_document(
    document_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BentoDocumentDetail:
    document = _load_or_404(
        db,
        document_id=document_id,
        current_user=current_user,
    )
    return _serialize_detail(
        document,
        current_user=current_user,
    )


@router.patch("/items/{document_id}", response_model=BentoDocumentDetail)
def update_bento_document(
    document_id: str,
    payload: UpdateBentoDocumentRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BentoDocumentDetail:
    document = _load_or_404(
        db,
        document_id=document_id,
        current_user=current_user,
    )
    if document.owner_id != current_user.id:
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    record_ownership_transition(
        db,
        actor_user_id=current_user.id,
        resource_kind="bento",
        resource_id=document.id,
        current_kind=document.visibility,
        next_kind=payload.visibility or document.visibility,
        company_admin_read_acknowledged=payload.company_admin_read_acknowledged,
    )
    if document.archived_at is not None:
        raise localized_http_exception(status_code=409, code="bento.archived")
    if payload.visibility is not None and not _can_manage(
        document,
        current_user=current_user,
    ):
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")

    values: dict[str, Any] = {"updated_at": _utcnow(), "version": payload.version + 1}
    next_document_json = document.document_json
    parsed: dict[str, Any] | None = None
    if payload.document_json is not None:
        next_document_json, parsed = _validated_document_json(payload.document_json)
        values["document_json"] = next_document_json
        values["title"] = str(parsed["title"]).strip()
    if payload.title is not None:
        next_title = payload.title.strip()
        if parsed is None:
            next_document_json, parsed = _validated_document_json(next_document_json)
        parsed["title"] = next_title
        parsed["modified"] = datetime.now(UTC).isoformat()
        values["title"] = next_title
        values["document_json"] = json.dumps(
            parsed,
            ensure_ascii=False,
            separators=(",", ":"),
        )
    if payload.visibility is not None:
        values["visibility"] = payload.visibility

    result = db.execute(
        update(BentoDocument)
        .where(
            BentoDocument.id == document.id,
            BentoDocument.version == payload.version,
        )
        .values(**values)
    )
    if result.rowcount != 1:
        db.rollback()
        raise localized_http_exception(status_code=409, code="bento.version_conflict")
    db.commit()
    updated_document = db.scalar(
        select(BentoDocument)
        .options(selectinload(BentoDocument.owner))
        .where(
            BentoDocument.id == document_id,
        )
        .execution_options(populate_existing=True)
    )
    if updated_document is None:
        raise localized_http_exception(status_code=404, code="bento.not_found")
    return _serialize_detail(
        updated_document,
        current_user=current_user,
    )


@router.delete("/items/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_bento_document(
    document_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    document = _load_or_404(
        db,
        document_id=document_id,
        current_user=current_user,
    )
    if document.owner_id != current_user.id:
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    if not _can_manage(
        document,
        current_user=current_user,
    ):
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    if document.archived_at is None:
        document.archived_at = _utcnow()
        document.updated_at = _utcnow()
        document.version += 1
        db.add(document)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items/{document_id}/restore", response_model=BentoDocumentDetail)
def restore_bento_document(
    document_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> BentoDocumentDetail:
    document = _load_or_404(
        db,
        document_id=document_id,
        current_user=current_user,
    )
    if document.owner_id != current_user.id:
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    if not _can_manage(
        document,
        current_user=current_user,
    ):
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    if document.archived_at is not None:
        document.archived_at = None
        document.updated_at = _utcnow()
        document.version += 1
        db.add(document)
        db.commit()
    restored = _load_or_404(
        db,
        document_id=document_id,
        current_user=current_user,
    )
    return _serialize_detail(
        restored,
        current_user=current_user,
    )


@router.delete("/items/{document_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_bento_document(
    document_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    document = _load_or_404(
        db,
        document_id=document_id,
        current_user=current_user,
    )
    if document.owner_id != current_user.id:
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    if not _can_manage(
        document,
        current_user=current_user,
    ):
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    if document.archived_at is None:
        raise localized_http_exception(status_code=409, code="bento.archive_before_delete")
    db.delete(document)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
