from __future__ import annotations

from datetime import UTC, datetime
import json
from typing import Any, Literal
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, or_, select, update
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import resolve_workspace_role, workspace_role_allows
from open_work_hub_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_work_hub_api.domains.bento.app_catalog import BENTO_WORKSPACE_APP
from open_work_hub_api.domains.bento.models import BentoDocument


require_bento_app_enabled = require_workspace_app_enabled(
    BENTO_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/bento",
    tags=["bento"],
    dependencies=[Depends(require_bento_app_enabled)],
)

BentoHubView = Literal["all", "mine", "archived"]
BentoSortBy = Literal["updated_at", "created_at", "title"]
BentoSortDir = Literal["asc", "desc"]
BentoVisibility = Literal["personal", "workspace"]
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


class BentoDocumentItem(BaseModel):
    id: str
    workspace_id: str
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


def _access_clause(current_user: User):
    return or_(
        BentoDocument.owner_id == current_user.id,
        BentoDocument.visibility == "workspace",
    )


def _can_manage(
    document: BentoDocument,
    *,
    current_user: User,
    workspace_role: str | None,
) -> bool:
    if document.owner_id == current_user.id:
        return True
    return document.visibility == "workspace" and workspace_role_allows(
        workspace_role,
        "admin",
    )


def _load_or_404(
    db: Session,
    *,
    workspace_id: str,
    document_id: str,
    current_user: User,
) -> BentoDocument:
    document = db.scalar(
        select(BentoDocument)
        .options(selectinload(BentoDocument.owner))
        .where(
            BentoDocument.id == document_id,
            BentoDocument.workspace_id == workspace_id,
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
    workspace_role: str | None,
) -> BentoDocumentItem:
    can_manage = _can_manage(
        document,
        current_user=current_user,
        workspace_role=workspace_role,
    )
    return BentoDocumentItem(
        id=document.id,
        workspace_id=document.workspace_id,
        title=document.title,
        visibility=document.visibility,
        version=document.version,
        created_by_id=document.owner_id,
        created_by_name=document.owner.full_name if document.owner else "",
        created_at=document.created_at,
        updated_at=document.updated_at,
        archived_at=document.archived_at,
        can_edit=document.archived_at is None,
        can_manage=can_manage,
    )


def _serialize_detail(
    document: BentoDocument,
    *,
    current_user: User,
    workspace_role: str | None,
) -> BentoDocumentDetail:
    item = _serialize_item(
        document,
        current_user=current_user,
        workspace_role=workspace_role,
    )
    return BentoDocumentDetail(**item.model_dump(), document_json=document.document_json)


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
    workspace: Workspace = Depends(require_current_workspace),
) -> BentoHubResponse:
    clauses = [
        BentoDocument.workspace_id == workspace.id,
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
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    return BentoHubResponse(
        items=[
            _serialize_item(
                document,
                current_user=current_user,
                workspace_role=workspace_role,
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
    workspace: Workspace = Depends(require_current_workspace),
) -> BentoDocumentDetail:
    title = payload.title.strip()
    raw_document = payload.document_json or _default_document_json(title)
    document_json, parsed = _validated_document_json(raw_document)
    parsed["title"] = title
    document_json = json.dumps(parsed, ensure_ascii=False, separators=(",", ":"))
    now = _utcnow()
    document = BentoDocument(
        id=str(uuid.uuid4()),
        workspace_id=workspace.id,
        owner_id=current_user.id,
        title=title,
        visibility=payload.visibility,
        document_json=document_json,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(document)
    db.commit()
    document = _load_or_404(
        db,
        workspace_id=workspace.id,
        document_id=document.id,
        current_user=current_user,
    )
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    return _serialize_detail(
        document,
        current_user=current_user,
        workspace_role=workspace_role,
    )


@router.get("/items/{document_id}", response_model=BentoDocumentDetail)
def get_bento_document(
    document_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> BentoDocumentDetail:
    document = _load_or_404(
        db,
        workspace_id=workspace.id,
        document_id=document_id,
        current_user=current_user,
    )
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    return _serialize_detail(
        document,
        current_user=current_user,
        workspace_role=workspace_role,
    )


@router.patch("/items/{document_id}", response_model=BentoDocumentDetail)
def update_bento_document(
    document_id: str,
    payload: UpdateBentoDocumentRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> BentoDocumentDetail:
    document = _load_or_404(
        db,
        workspace_id=workspace.id,
        document_id=document_id,
        current_user=current_user,
    )
    if document.archived_at is not None:
        raise localized_http_exception(status_code=409, code="bento.archived")
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    if payload.visibility is not None and not _can_manage(
        document,
        current_user=current_user,
        workspace_role=workspace_role,
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
            BentoDocument.workspace_id == workspace.id,
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
            BentoDocument.workspace_id == workspace.id,
        )
        .execution_options(populate_existing=True)
    )
    if updated_document is None:
        raise localized_http_exception(status_code=404, code="bento.not_found")
    return _serialize_detail(
        updated_document,
        current_user=current_user,
        workspace_role=workspace_role,
    )


@router.delete("/items/{document_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_bento_document(
    document_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    document = _load_or_404(
        db,
        workspace_id=workspace.id,
        document_id=document_id,
        current_user=current_user,
    )
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    if not _can_manage(document, current_user=current_user, workspace_role=workspace_role):
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
    workspace: Workspace = Depends(require_current_workspace),
) -> BentoDocumentDetail:
    document = _load_or_404(
        db,
        workspace_id=workspace.id,
        document_id=document_id,
        current_user=current_user,
    )
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    if not _can_manage(document, current_user=current_user, workspace_role=workspace_role):
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    if document.archived_at is not None:
        document.archived_at = None
        document.updated_at = _utcnow()
        document.version += 1
        db.add(document)
        db.commit()
    restored = _load_or_404(
        db,
        workspace_id=workspace.id,
        document_id=document_id,
        current_user=current_user,
    )
    return _serialize_detail(
        restored,
        current_user=current_user,
        workspace_role=workspace_role,
    )


@router.delete("/items/{document_id}/permanent", status_code=status.HTTP_204_NO_CONTENT)
def permanently_delete_bento_document(
    document_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    document = _load_or_404(
        db,
        workspace_id=workspace.id,
        document_id=document_id,
        current_user=current_user,
    )
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    if not _can_manage(document, current_user=current_user, workspace_role=workspace_role):
        raise localized_http_exception(status_code=403, code="bento.manage_access_required")
    if document.archived_at is None:
        raise localized_http_exception(status_code=409, code="bento.archive_before_delete")
    db.delete(document)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)
