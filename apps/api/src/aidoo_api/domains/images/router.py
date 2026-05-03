from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Query, Response, UploadFile, status
from sqlalchemy.orm import Session

from aidoo_api.core.db import get_db_session
from aidoo_api.core.i18n import localized_http_exception
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.auth.dependencies import require_current_user, require_current_workspace
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.images import service as images_service
from aidoo_api.domains.images.schemas import (
    BriefRequest,
    BriefVersionOut,
    ImageDownloadResponse,
    ImageGenerationCreateRequest,
    ImageGenerationListResponse,
    ImageGenerationOut,
    ImageGenerationPatchRequest,
    ReferenceImageRole,
    ReferenceImageUploadOut,
)


router = APIRouter(prefix="/images", tags=["images"])

_UPLOAD_CHUNK_BYTES = 1024 * 1024


async def _read_reference_upload(file: UploadFile) -> bytes:
    settings = get_settings()
    if not settings.image_enabled:
        raise localized_http_exception(status_code=503, code="images.feature_disabled")

    data = bytearray()
    while True:
        chunk = await file.read(_UPLOAD_CHUNK_BYTES)
        if not chunk:
            break
        data.extend(chunk)
        if len(data) > settings.image_reference_max_bytes:
            raise localized_http_exception(status_code=413, code="images.upload_too_large")
    return bytes(data)


@router.post(
    "/generations",
    response_model=ImageGenerationOut,
    status_code=status.HTTP_201_CREATED,
)
def create_generation(
    payload: ImageGenerationCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImageGenerationOut:
    return images_service.create_generation(
        db,
        workspace=workspace,
        user=current_user,
        payload=payload,
    )


@router.get("/generations", response_model=ImageGenerationListResponse)
def list_generations(
    limit: int = Query(default=20, ge=1, le=100),
    image_status: Literal[
        "idle", "queued", "running", "succeeded", "failed", "cancelled"
    ]
    | None = Query(default=None),
    use_case: str | None = Query(default=None, max_length=64),
    is_template: bool | None = Query(default=None),
    has_image_activity: bool | None = Query(default=None),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImageGenerationListResponse:
    return images_service.list_generations(
        db,
        workspace=workspace,
        user=current_user,
        limit=limit,
        image_status=image_status,
        use_case=use_case,
        is_template=is_template,
        has_image_activity=has_image_activity,
    )


@router.get("/generations/{generation_id}", response_model=ImageGenerationOut)
def get_generation(
    generation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImageGenerationOut:
    return images_service.get_generation(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
    )


@router.patch("/generations/{generation_id}", response_model=ImageGenerationOut)
def patch_generation(
    generation_id: str,
    payload: ImageGenerationPatchRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImageGenerationOut:
    return images_service.patch_generation(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
        payload=payload,
    )


@router.post("/generations/{generation_id}/cancel", response_model=ImageGenerationOut)
def cancel_generation(
    generation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImageGenerationOut:
    return images_service.cancel_generation(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
    )


@router.put("/generations/{generation_id}/template", response_model=ImageGenerationOut)
def mark_generation_template(
    generation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImageGenerationOut:
    return images_service.set_generation_template(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
        is_template=True,
    )


@router.delete("/generations/{generation_id}/template", response_model=ImageGenerationOut)
def unmark_generation_template(
    generation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImageGenerationOut:
    return images_service.set_generation_template(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
        is_template=False,
    )


@router.delete("/generations/{generation_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_generation(
    generation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    images_service.delete_generation(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/generations/{generation_id}/reference-images",
    response_model=ReferenceImageUploadOut,
    status_code=status.HTTP_201_CREATED,
)
async def upload_reference_image(
    generation_id: str,
    file: UploadFile = File(...),
    role: ReferenceImageRole = Form("style"),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ReferenceImageUploadOut:
    data = await _read_reference_upload(file)
    return images_service.upload_reference_image(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
        role=role,
        content_type=file.content_type or "application/octet-stream",
        data=data,
        original_name=file.filename or "",
    )


@router.delete(
    "/generations/{generation_id}/reference-images",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_reference_image(
    generation_id: str,
    storage_key: str = Query(..., min_length=1, max_length=512),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    images_service.delete_reference_image(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
        storage_key=storage_key,
    )
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post(
    "/generations/{generation_id}/brief",
    response_model=BriefVersionOut,
)
def generate_brief(
    generation_id: str,
    payload: BriefRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> BriefVersionOut:
    return images_service.generate_brief(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
        payload=payload,
    )


@router.post(
    "/generations/{generation_id}/approve",
    response_model=ImageGenerationOut,
)
def approve_generation(
    generation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImageGenerationOut:
    return images_service.approve_and_dispatch(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
    )


@router.get(
    "/generations/{generation_id}/download",
    response_model=ImageDownloadResponse,
)
def get_download_url(
    generation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> ImageDownloadResponse:
    return images_service.presign_download(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
    )


@router.get("/generations/{generation_id}/download/content")
def download_image_content(
    generation_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    workspace: Workspace = Depends(require_current_workspace),
) -> Response:
    data, content_type = images_service.read_result_image(
        db,
        workspace=workspace,
        user=current_user,
        generation_id=generation_id,
    )
    return Response(
        content=data,
        media_type=content_type,
        headers={
            "Cache-Control": "private, max-age=60",
            "Content-Disposition": f'inline; filename="image-generation-{generation_id}.png"',
        },
    )
