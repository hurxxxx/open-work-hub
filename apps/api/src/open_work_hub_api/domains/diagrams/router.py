from __future__ import annotations

from datetime import UTC, datetime
from typing import Literal
import uuid

from fastapi import APIRouter, Depends, Query, Response, status
from minio.error import S3Error
from pydantic import BaseModel, Field
from sqlalchemy import func, or_, select
from sqlalchemy.orm import Session, selectinload

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.access import (
    resolve_workspace_role,
    workspace_role_allows,
)
from open_work_hub_api.domains.auth.dependencies import (
    require_current_user,
    require_current_workspace,
)
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.auth.workspace_app_gate import require_workspace_app_enabled
from open_work_hub_api.domains.diagrams.app_catalog import DIAGRAMS_WORKSPACE_APP
from open_work_hub_api.domains.diagrams.models import Diagram
from open_work_hub_api.domains.diagrams.storage import (
    DIAGRAM_PNG_CONTENT_TYPE,
    DIAGRAM_PREVIEW_MAX_BYTES,
    DIAGRAM_SOURCE_MAX_BYTES,
    DIAGRAM_XML_CONTENT_TYPE,
    decode_preview_data_url,
    diagram_preview_storage_key,
    diagram_source_storage_key,
    put_diagram_object,
    read_diagram_object,
    remove_diagram_object,
)


require_diagrams_app_enabled = require_workspace_app_enabled(
    DIAGRAMS_WORKSPACE_APP.app_id,
    error_code="workspace.app_disabled",
)

router = APIRouter(
    prefix="/diagrams",
    tags=["diagrams"],
    dependencies=[Depends(require_diagrams_app_enabled)],
)

DiagramHubView = Literal["all", "mine", "archived"]
DiagramSortBy = Literal["updated_at", "created_at", "title"]
DiagramSortDir = Literal["asc", "desc"]
DiagramVisibility = Literal["personal", "workspace"]
DIAGRAM_VISIBILITY_PERSONAL = "personal"
DIAGRAM_VISIBILITY_WORKSPACE = "workspace"

EMPTY_DIAGRAM_XML = (
    '<mxfile host="Open Work Hub">'
    '<diagram id="page-1" name="Page-1">'
    '<mxGraphModel dx="1200" dy="800" grid="1" gridSize="10" guides="1" '
    'tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" '
    'pageWidth="850" pageHeight="1100" math="0" shadow="0">'
    '<root><mxCell id="0"/><mxCell id="1" parent="0"/></root>'
    "</mxGraphModel>"
    "</diagram>"
    "</mxfile>"
)


def _utcnow() -> datetime:
    return datetime.now(UTC).replace(tzinfo=None)


class CreateDiagramRequest(BaseModel):
    title: str = Field(..., min_length=1, max_length=200)
    visibility: DiagramVisibility = DIAGRAM_VISIBILITY_PERSONAL
    xml: str = Field(default=EMPTY_DIAGRAM_XML)
    preview_png_data_url: str | None = None


class UpdateDiagramRequest(BaseModel):
    version: int = Field(..., ge=1)
    title: str | None = Field(default=None, min_length=1, max_length=200)
    visibility: DiagramVisibility | None = None
    xml: str | None = None
    preview_png_data_url: str | None = None


class DiagramItem(BaseModel):
    id: str
    workspace_id: str
    title: str
    visibility: DiagramVisibility
    version: int
    created_by_id: str
    created_by_name: str
    created_at: datetime
    updated_at: datetime
    archived_at: datetime | None
    preview_available: bool
    preview_url: str | None
    can_edit: bool
    can_manage: bool


class DiagramDetail(DiagramItem):
    xml: str


class DiagramHubResponse(BaseModel):
    items: list[DiagramItem]
    view: DiagramHubView
    page: int
    page_size: int
    total: int


def _serialize_diagram_item(
    diagram: Diagram,
    *,
    current_user: User,
    workspace_role: str | None,
) -> DiagramItem:
    can_manage = _can_manage_diagram(
        diagram,
        current_user=current_user,
        workspace_role=workspace_role,
    )
    preview_url = (
        f"/api/v1/diagrams/items/{diagram.id}/preview.png" if diagram.preview_storage_key else None
    )
    return DiagramItem(
        id=diagram.id,
        workspace_id=diagram.workspace_id,
        title=diagram.title,
        visibility=diagram.visibility,
        version=diagram.version,
        created_by_id=diagram.owner_id,
        created_by_name=diagram.owner.full_name if diagram.owner else "",
        created_at=diagram.created_at,
        updated_at=diagram.updated_at,
        archived_at=diagram.archived_at,
        preview_available=diagram.preview_storage_key is not None,
        preview_url=preview_url,
        can_edit=True,
        can_manage=can_manage,
    )


def _serialize_diagram_detail(
    diagram: Diagram,
    *,
    current_user: User,
    workspace_role: str | None,
    xml: str,
) -> DiagramDetail:
    item = _serialize_diagram_item(
        diagram,
        current_user=current_user,
        workspace_role=workspace_role,
    )
    return DiagramDetail(**item.model_dump(), xml=xml)


def _diagram_access_clause(current_user: User):
    return or_(
        Diagram.owner_id == current_user.id,
        Diagram.visibility == DIAGRAM_VISIBILITY_WORKSPACE,
    )


def _can_manage_diagram(
    diagram: Diagram,
    *,
    current_user: User,
    workspace_role: str | None,
) -> bool:
    if diagram.owner_id == current_user.id:
        return True
    return diagram.visibility == DIAGRAM_VISIBILITY_WORKSPACE and workspace_role_allows(
        workspace_role,
        "admin",
    )


def _load_diagram_or_404(
    db: Session,
    *,
    workspace_id: str,
    diagram_id: str,
    current_user: User,
) -> Diagram:
    diagram = db.scalar(
        select(Diagram)
        .options(selectinload(Diagram.owner))
        .where(
            Diagram.id == diagram_id,
            Diagram.workspace_id == workspace_id,
            _diagram_access_clause(current_user),
        )
    )
    if diagram is None:
        raise localized_http_exception(status_code=404, code="diagrams.not_found")
    return diagram


def _validate_xml_size(xml: str) -> bytes:
    data = xml.encode("utf-8")
    if len(data) > DIAGRAM_SOURCE_MAX_BYTES:
        raise localized_http_exception(
            status_code=413,
            code="diagrams.source_too_large",
        )
    return data


def _preview_payload_from_data_url(value: str | None) -> bytes | None:
    if value is None:
        return None
    data = decode_preview_data_url(value)
    if data is None:
        raise localized_http_exception(status_code=400, code="diagrams.invalid_preview")
    if len(data) > DIAGRAM_PREVIEW_MAX_BYTES:
        raise localized_http_exception(status_code=413, code="diagrams.preview_too_large")
    return data


def _put_object_or_503(*, storage_key: str, data: bytes, content_type: str) -> None:
    try:
        put_diagram_object(storage_key=storage_key, data=data, content_type=content_type)
    except Exception as exc:
        raise localized_http_exception(
            status_code=503, code="diagrams.storage_unavailable"
        ) from exc


def _read_object_or_503(storage_key: str) -> bytes:
    try:
        return read_diagram_object(storage_key)
    except S3Error as exc:
        raise localized_http_exception(status_code=404, code="diagrams.preview_not_found") from exc
    except Exception as exc:
        raise localized_http_exception(
            status_code=503, code="diagrams.storage_unavailable"
        ) from exc


@router.get("/hub", response_model=DiagramHubResponse)
def list_diagram_hub(
    view: DiagramHubView = Query(default="all"),
    q: str = Query(default=""),
    sort_by: DiagramSortBy = Query(default="updated_at"),
    sort_dir: DiagramSortDir = Query(default="desc"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=50, ge=1, le=200),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> DiagramHubResponse:
    clauses = [
        Diagram.workspace_id == workspace.id,
        _diagram_access_clause(current_user),
    ]
    if view == "archived":
        clauses.append(Diagram.archived_at.is_not(None))
    else:
        clauses.append(Diagram.archived_at.is_(None))
    if view == "mine":
        clauses.append(Diagram.owner_id == current_user.id)
    if q.strip():
        clauses.append(Diagram.title.ilike(f"%{q.strip()}%"))

    total = db.scalar(select(func.count()).select_from(Diagram).where(*clauses)) or 0
    sort_column = {
        "created_at": Diagram.created_at,
        "title": Diagram.title,
        "updated_at": Diagram.updated_at,
    }[sort_by]
    order_by = sort_column.asc() if sort_dir == "asc" else sort_column.desc()
    diagrams = db.scalars(
        select(Diagram)
        .options(selectinload(Diagram.owner))
        .where(*clauses)
        .order_by(order_by, Diagram.id.asc())
        .offset((page - 1) * page_size)
        .limit(page_size)
    ).all()
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    return DiagramHubResponse(
        items=[
            _serialize_diagram_item(
                diagram,
                current_user=current_user,
                workspace_role=workspace_role,
            )
            for diagram in diagrams
        ],
        view=view,
        page=page,
        page_size=page_size,
        total=total,
    )


@router.post("/items", response_model=DiagramDetail, status_code=status.HTTP_201_CREATED)
def create_diagram_item(
    payload: CreateDiagramRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> DiagramDetail:
    diagram_id = str(uuid.uuid4())
    source_key = diagram_source_storage_key(workspace_id=workspace.id, diagram_id=diagram_id)
    xml_data = _validate_xml_size(payload.xml)
    _put_object_or_503(
        storage_key=source_key,
        data=xml_data,
        content_type=DIAGRAM_XML_CONTENT_TYPE,
    )

    preview_key: str | None = None
    preview_data = _preview_payload_from_data_url(payload.preview_png_data_url)
    if preview_data is not None:
        preview_key = diagram_preview_storage_key(workspace_id=workspace.id, diagram_id=diagram_id)
        _put_object_or_503(
            storage_key=preview_key,
            data=preview_data,
            content_type=DIAGRAM_PNG_CONTENT_TYPE,
        )

    now = _utcnow()
    diagram = Diagram(
        id=diagram_id,
        workspace_id=workspace.id,
        owner_id=current_user.id,
        title=payload.title,
        visibility=payload.visibility,
        source_storage_key=source_key,
        preview_storage_key=preview_key,
        version=1,
        created_at=now,
        updated_at=now,
    )
    db.add(diagram)
    db.commit()
    db.refresh(diagram)
    diagram = _load_diagram_or_404(
        db,
        workspace_id=workspace.id,
        diagram_id=diagram.id,
        current_user=current_user,
    )
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    return _serialize_diagram_detail(
        diagram,
        current_user=current_user,
        workspace_role=workspace_role,
        xml=payload.xml,
    )


@router.get("/items/{item_id}", response_model=DiagramDetail)
def get_diagram_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> DiagramDetail:
    diagram = _load_diagram_or_404(
        db,
        workspace_id=workspace.id,
        diagram_id=item_id,
        current_user=current_user,
    )
    xml = _read_object_or_503(diagram.source_storage_key).decode("utf-8")
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    return _serialize_diagram_detail(
        diagram,
        current_user=current_user,
        workspace_role=workspace_role,
        xml=xml,
    )


@router.patch("/items/{item_id}", response_model=DiagramDetail)
def update_diagram_item(
    item_id: str,
    payload: UpdateDiagramRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> DiagramDetail:
    diagram = _load_diagram_or_404(
        db,
        workspace_id=workspace.id,
        diagram_id=item_id,
        current_user=current_user,
    )
    if payload.version != diagram.version:
        raise localized_http_exception(status_code=409, code="diagrams.version_conflict")
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)

    changed = False
    if "title" in payload.model_fields_set and payload.title is not None:
        diagram.title = payload.title
        changed = True

    if "visibility" in payload.model_fields_set and payload.visibility is not None:
        if not _can_manage_diagram(
            diagram,
            current_user=current_user,
            workspace_role=workspace_role,
        ):
            raise localized_http_exception(
                status_code=403,
                code="diagrams.manage_access_required",
            )
        if diagram.visibility != payload.visibility:
            diagram.visibility = payload.visibility
            changed = True

    source_xml: str | None = None
    if "xml" in payload.model_fields_set and payload.xml is not None:
        source_xml = payload.xml
        _put_object_or_503(
            storage_key=diagram.source_storage_key,
            data=_validate_xml_size(payload.xml),
            content_type=DIAGRAM_XML_CONTENT_TYPE,
        )
        changed = True

    if "preview_png_data_url" in payload.model_fields_set:
        if payload.preview_png_data_url is None:
            if diagram.preview_storage_key:
                remove_diagram_object(storage_key=diagram.preview_storage_key)
            diagram.preview_storage_key = None
        else:
            preview_data = _preview_payload_from_data_url(payload.preview_png_data_url)
            preview_key = diagram.preview_storage_key or diagram_preview_storage_key(
                workspace_id=workspace.id,
                diagram_id=diagram.id,
            )
            _put_object_or_503(
                storage_key=preview_key,
                data=preview_data or b"",
                content_type=DIAGRAM_PNG_CONTENT_TYPE,
            )
            diagram.preview_storage_key = preview_key
        changed = True

    if changed:
        diagram.version += 1
        diagram.updated_at = _utcnow()
        db.add(diagram)
        db.commit()
        db.refresh(diagram)

    if source_xml is None:
        source_xml = _read_object_or_503(diagram.source_storage_key).decode("utf-8")
    return _serialize_diagram_detail(
        diagram,
        current_user=current_user,
        workspace_role=workspace_role,
        xml=source_xml,
    )


@router.delete("/items/{item_id}", status_code=status.HTTP_204_NO_CONTENT)
def archive_diagram_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    diagram = _load_diagram_or_404(
        db,
        workspace_id=workspace.id,
        diagram_id=item_id,
        current_user=current_user,
    )
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    if not _can_manage_diagram(
        diagram,
        current_user=current_user,
        workspace_role=workspace_role,
    ):
        raise localized_http_exception(status_code=403, code="diagrams.manage_access_required")
    if diagram.archived_at is None:
        diagram.archived_at = _utcnow()
        diagram.updated_at = _utcnow()
        diagram.version += 1
        db.add(diagram)
        db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/items/{item_id}/restore", response_model=DiagramDetail)
def restore_diagram_item(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> DiagramDetail:
    diagram = _load_diagram_or_404(
        db,
        workspace_id=workspace.id,
        diagram_id=item_id,
        current_user=current_user,
    )
    workspace_role = resolve_workspace_role(db, current_user, workspace.id)
    if not _can_manage_diagram(
        diagram,
        current_user=current_user,
        workspace_role=workspace_role,
    ):
        raise localized_http_exception(status_code=403, code="diagrams.manage_access_required")
    if diagram.archived_at is not None:
        diagram.archived_at = None
        diagram.updated_at = _utcnow()
        diagram.version += 1
        db.add(diagram)
        db.commit()
        db.refresh(diagram)
    xml = _read_object_or_503(diagram.source_storage_key).decode("utf-8")
    return _serialize_diagram_detail(
        diagram,
        current_user=current_user,
        workspace_role=workspace_role,
        xml=xml,
    )


@router.get("/items/{item_id}/preview.png")
def get_diagram_preview(
    item_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    diagram = _load_diagram_or_404(
        db,
        workspace_id=workspace.id,
        diagram_id=item_id,
        current_user=current_user,
    )
    if not diagram.preview_storage_key:
        raise localized_http_exception(status_code=404, code="diagrams.preview_not_found")
    return Response(
        content=_read_object_or_503(diagram.preview_storage_key),
        media_type=DIAGRAM_PNG_CONTENT_TYPE,
        headers={"Cache-Control": "private, max-age=60"},
    )
