from __future__ import annotations

from datetime import datetime
from tempfile import SpooledTemporaryFile
from typing import Literal

from fastapi import APIRouter, Depends, File, Form, Request, Response, UploadFile, status
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.app_gate import require_app_access
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.content_access.dependencies import require_content_grant_issuer
from open_work_hub_api.domains.content_access.grants import ContentGrantIssuer
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files.app_catalog import FILES_APP
from open_work_hub_api.domains.files.browse_projection import (
    FileBrowseResponse,
    FileFolderItem,
    FileItem,
    build_file_browse_response,
    serialize_file_item,
    serialize_folder_item,
)
from open_work_hub_api.domains.files.content_access import (
    build_file_content_url,
    is_previewable_image,
)
from open_work_hub_api.domains.files.rag_status import load_file_rag_states
from open_work_hub_api.domains.files.search import (
    FileSearchRequest,
    FileSearchResponse,
    FileSearchUnavailable,
    query_files,
    resolve_file_search_runtime,
)

require_files_app_enabled = require_app_access(
    FILES_APP.app_id,
    error_code="files.app_disabled",
)


router = APIRouter(
    prefix="/files",
    tags=["files"],
    dependencies=[Depends(require_files_app_enabled)],
)


FileVisibility = Literal["private", "company"]
MAX_MULTIPART_UPLOAD_OVERHEAD_BYTES = 1024 * 1024


class FileFolderCreateRequest(BaseModel):
    company_admin_read_acknowledged: bool = False
    name: str = Field(min_length=1, max_length=255)
    parent_id: str | None = Field(default=None, max_length=36)
    visibility: FileVisibility = "private"
    corpus_id: str | None = Field(default=None, max_length=36)


class FileFolderUpdateRequest(BaseModel):
    name: str | None = Field(default=None, min_length=1, max_length=255)
    visibility: FileVisibility | None = None


class FileDownloadResponse(BaseModel):
    url: str


class FileBulkRequest(BaseModel):
    file_ids: list[str] = Field(default_factory=list, max_length=500)
    folder_ids: list[str] = Field(default_factory=list, max_length=500)


class FileCorpusCreateRequest(BaseModel):
    name: str = Field(min_length=1, max_length=255)


class FileCorpusItem(BaseModel):
    id: str
    name: str
    access_scope_kind: Literal["company"]
    retrieval_partition_id: str
    metadata_version: int
    created_by_id: str
    created_at: datetime
    updated_at: datetime


@router.get("", response_model=FileBrowseResponse)
def browse_files(
    folder_id: str | None = None,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> FileBrowseResponse:
    accessible_folders = files_service.list_accessible_folders(
        db,
        user=current_user,
    )
    accessible_folder_ids = {folder.id for folder in accessible_folders}
    if folder_id is not None and folder_id not in accessible_folder_ids:
        raise localized_http_exception(status_code=404, code="files.folder_not_found")
    accessible_files = files_service.list_accessible_files(
        db,
        user=current_user,
        accessible_folder_ids=accessible_folder_ids,
    )
    is_admin = files_service.is_corpus_admin(db, user=current_user)
    visible_files = [file for file in accessible_files if file.folder_id == folder_id]
    rag_states = load_file_rag_states(db, files=visible_files)
    return build_file_browse_response(
        folders=accessible_folders,
        files=accessible_files,
        folder_id=folder_id,
        user=current_user,
        is_admin=is_admin,
        rag_states=rag_states,
    )


def require_file_search_runtime(
    db: Session = Depends(get_db_session),
):
    try:
        return resolve_file_search_runtime(db)
    except FileSearchUnavailable as error:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="files.search_unavailable",
        ) from error


@router.post("/search", response_model=FileSearchResponse)
def search_files(
    payload: FileSearchRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    runtime=Depends(require_file_search_runtime),
) -> FileSearchResponse:
    return query_files(
        db,
        user=current_user,
        request=payload,
        runtime=runtime,
    )


@router.post("/folders", response_model=FileFolderItem, status_code=status.HTTP_201_CREATED)
def create_folder(
    payload: FileFolderCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> FileFolderItem:
    try:
        folder = files_service.create_folder(
            db,
            user=current_user,
            name=payload.name,
            parent_id=payload.parent_id,
            visibility=payload.visibility,
            company_admin_read_acknowledged=payload.company_admin_read_acknowledged,
            corpus_id=payload.corpus_id,
        )
    except files_service.FileCorpusError as error:
        _raise_file_corpus_http_error(error)
    db.commit()
    db.refresh(folder)
    is_admin = files_service.is_corpus_admin(db, user=current_user)
    return serialize_folder_item(folder, user=current_user, is_admin=is_admin)


@router.get("/corpora", response_model=list[FileCorpusItem])
def list_file_corpora(
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> list[FileCorpusItem]:
    try:
        corpora = files_service.list_managed_file_corpora(
            db,
            user=current_user,
        )
    except files_service.FileCorpusError as error:
        _raise_file_corpus_http_error(error)
    return [_serialize_file_corpus(corpus) for corpus in corpora]


@router.post(
    "/corpora",
    response_model=FileCorpusItem,
    status_code=status.HTTP_201_CREATED,
)
def create_file_corpus(
    payload: FileCorpusCreateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> FileCorpusItem:
    try:
        corpus = files_service.create_file_corpus(
            db,
            user=current_user,
            name=payload.name,
        )
    except files_service.FileCorpusError as error:
        _raise_file_corpus_http_error(error)
    db.commit()
    db.refresh(corpus)
    return _serialize_file_corpus(corpus)


@router.patch("/folders/{folder_id}", response_model=FileFolderItem)
def update_folder(
    folder_id: str,
    payload: FileFolderUpdateRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> FileFolderItem:
    try:
        folder = files_service.update_folder(
            db,
            user=current_user,
            folder_id=folder_id,
            name=payload.name,
            visibility=payload.visibility,
        )
    except files_service.FileCorpusError as error:
        _raise_file_corpus_http_error(error)
    db.commit()
    db.refresh(folder)
    is_admin = files_service.is_corpus_admin(db, user=current_user)
    return serialize_folder_item(folder, user=current_user, is_admin=is_admin)


@router.delete("/folders/{folder_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_folder(
    folder_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    try:
        storage_keys = files_service.delete_folder(
            db,
            user=current_user,
            folder_id=folder_id,
        )
    except files_service.FileCorpusError as error:
        _raise_file_corpus_http_error(error)
    db.commit()
    files_service.remove_storage_objects(db, storage_keys)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.post("/upload", response_model=FileItem, status_code=status.HTTP_201_CREATED)
async def upload_file(
    request: Request,
    file: UploadFile = File(...),
    folder_id: str | None = Form(default=None),
    visibility: FileVisibility = Form(default="private"),
    company_admin_read_acknowledged: bool = Form(default=False),
    corpus_id: str | None = Form(default=None, max_length=36),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> FileItem:
    upload_buffer, size_bytes = await _read_upload_to_spooled_file(file, request=request)
    try:
        try:
            row = files_service.upload_file(
                db,
                user=current_user,
                filename=file.filename,
                content_type=file.content_type,
                content=upload_buffer,
                size_bytes=size_bytes,
                folder_id=folder_id,
                visibility=visibility,
                company_admin_read_acknowledged=company_admin_read_acknowledged,
                corpus_id=corpus_id,
            )
        except files_service.FileCorpusError as error:
            db.rollback()
            _raise_file_corpus_http_error(error)
        try:
            db.commit()
        except Exception:
            db.rollback()
            files_service.remove_storage_object_immediately(row.storage_key)
            raise
    finally:
        upload_buffer.close()
    db.refresh(row)
    is_admin = files_service.is_corpus_admin(db, user=current_user)
    rag_state = load_file_rag_states(db, files=[row])[row.id]
    return serialize_file_item(
        row,
        user=current_user,
        is_admin=is_admin,
        rag_state=rag_state,
    )


def _serialize_file_corpus(corpus) -> FileCorpusItem:
    return FileCorpusItem(
        id=corpus.id,
        name=corpus.name,
        access_scope_kind=corpus.access_scope_kind,
        retrieval_partition_id=str(corpus.retrieval_partition_id),
        metadata_version=corpus.metadata_version,
        created_by_id=corpus.created_by_id,
        created_at=corpus.created_at,
        updated_at=corpus.updated_at,
    )


def _raise_file_corpus_http_error(error: files_service.FileCorpusError) -> None:
    if isinstance(error, files_service.FileCorpusNotFound):
        raise localized_http_exception(status_code=404, code="files.corpus_not_found") from error
    if isinstance(error, files_service.FileCorpusAccessDenied):
        raise localized_http_exception(
            status_code=403,
            code="files.corpus_access_required",
        ) from error
    raise localized_http_exception(status_code=409, code="files.corpus_conflict") from error


@router.get("/{file_id}/download", response_model=FileDownloadResponse)
def get_file_download(
    file_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> FileDownloadResponse:
    file = files_service.require_file_access(
        db,
        user=current_user,
        file_id=file_id,
    )
    return FileDownloadResponse(
        url=build_file_content_url(
            file,
            issuer=content_grant_issuer,
            disposition="attachment",
        )
    )


@router.get("/{file_id}/preview", response_model=FileDownloadResponse)
def get_file_preview(
    file_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    content_grant_issuer: ContentGrantIssuer = Depends(require_content_grant_issuer),
) -> FileDownloadResponse:
    file = files_service.require_file_access(
        db,
        user=current_user,
        file_id=file_id,
    )
    if not is_previewable_image(file):
        raise localized_http_exception(status_code=415, code="files.preview_unsupported_type")
    return FileDownloadResponse(
        url=build_file_content_url(
            file,
            issuer=content_grant_issuer,
            disposition="inline",
        )
    )


@router.post("/archive")
def download_archive(
    payload: FileBulkRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> StreamingResponse:
    archive_file = files_service.build_archive(
        db,
        user=current_user,
        file_ids=payload.file_ids,
        folder_ids=payload.folder_ids,
    )

    def body():
        try:
            while chunk := archive_file.read(1024 * 1024):
                yield chunk
        finally:
            archive_file.close()

    return StreamingResponse(
        body(),
        media_type="application/zip",
        headers={
            "Content-Disposition": 'attachment; filename="files.zip"',
            "Cache-Control": "private, max-age=0",
        },
    )


@router.post("/bulk-delete", status_code=status.HTTP_204_NO_CONTENT)
def bulk_delete(
    payload: FileBulkRequest,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    try:
        storage_keys = files_service.delete_items(
            db,
            user=current_user,
            file_ids=payload.file_ids,
            folder_ids=payload.folder_ids,
        )
    except files_service.FileCorpusError as error:
        _raise_file_corpus_http_error(error)
    db.commit()
    files_service.remove_storage_objects(db, storage_keys)
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


@router.delete("/{file_id}", status_code=status.HTTP_204_NO_CONTENT)
def delete_file(
    file_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> Response:
    try:
        storage_key = files_service.delete_file(
            db,
            user=current_user,
            file_id=file_id,
        )
    except files_service.FileCorpusError as error:
        _raise_file_corpus_http_error(error)
    db.commit()
    files_service.remove_storage_objects(db, [storage_key])
    db.commit()
    return Response(status_code=status.HTTP_204_NO_CONTENT)


async def _read_upload_to_spooled_file(
    file: UploadFile,
    *,
    request: Request,
) -> tuple[SpooledTemporaryFile[bytes], int]:
    content_length = request.headers.get("content-length")
    if content_length is not None:
        try:
            request_size = int(content_length)
        except ValueError:
            request_size = 0
        max_request_size = files_service.MAX_FILE_UPLOAD_SIZE + MAX_MULTIPART_UPLOAD_OVERHEAD_BYTES
        if request_size > max_request_size:
            raise localized_http_exception(
                status_code=413,
                code="files.file_size_limit_exceeded",
                limit_mb=files_service.MAX_FILE_UPLOAD_SIZE // (1024 * 1024),
            )

    buffer: SpooledTemporaryFile[bytes] = SpooledTemporaryFile(
        max_size=files_service.ARCHIVE_SPOOL_LIMIT_BYTES
    )
    size_bytes = 0
    try:
        while chunk := await file.read(files_service.ARCHIVE_CHUNK_BYTES):
            size_bytes += len(chunk)
            if size_bytes > files_service.MAX_FILE_UPLOAD_SIZE:
                raise localized_http_exception(
                    status_code=413,
                    code="files.file_size_limit_exceeded",
                    limit_mb=files_service.MAX_FILE_UPLOAD_SIZE // (1024 * 1024),
                )
            buffer.write(chunk)
        buffer.seek(0)
        return buffer, size_bytes
    except Exception:
        buffer.close()
        raise
