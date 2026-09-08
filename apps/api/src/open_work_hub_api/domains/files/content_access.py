from __future__ import annotations

import hashlib
import json
from collections.abc import Iterator
from typing import Literal
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.domains.auth.app_gate import (
    can_use_app,
)
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.content_access.contracts import ContentStream
from open_work_hub_api.domains.content_access.grants import (
    ContentGrantClaims,
    ContentGrantIssuer,
    InvalidContentGrant,
    build_content_grant_url,
)
from open_work_hub_api.domains.files import service as files_service
from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.files.storage_adapter import FileStorageObject, open_file_object

FileContentDisposition = Literal["attachment", "inline"]
# Content URLs are bearer capabilities. Every fetch rechecks the current source
# ACL; the short lifetime also limits replay while the issuing principal remains
# authorized. Corpus metadata and object identity revoke stale grants eagerly.
FILE_CONTENT_URL_EXPIRES_SECONDS = 5 * 60
FILE_CONTENT_CHUNK_SIZE = 1024 * 1024
_INLINE_IMAGE_SIGNATURE_BYTES = 12
_SAFE_INLINE_IMAGE_CONTENT_TYPES = frozenset(
    {
        "image/gif",
        "image/jpeg",
        "image/png",
        "image/webp",
    }
)
_LEGACY_CORPUS_ID = "legacy"
_LEGACY_ACL_EPOCH = "0"


def build_file_content_url(
    file: FileManagerFile,
    *,
    issuer: ContentGrantIssuer,
    disposition: FileContentDisposition,
    now: float | None = None,
    expires_seconds: int = FILE_CONTENT_URL_EXPIRES_SECONDS,
) -> str:
    corpus_id, acl_epoch = _file_content_acl_binding(file)
    return build_content_grant_url(
        resource_kind="files.file",
        resource_id=file.id,
        owner_app_id="files",
        issuer=issuer,
        execution_context_kind="company",
        route_id=None,
        source_type="file_corpus",
        source_id=corpus_id,
        object_identity=_file_content_object_identity(file),
        resource_version=str(acl_epoch),
        disposition=disposition,
        expires_seconds=expires_seconds,
        now=now,
    )


def open_file_content_grant(db: Session, *, claims: ContentGrantClaims) -> ContentStream:
    file = db.scalar(
        select(FileManagerFile)
        .options(joinedload(FileManagerFile.corpus))
        .where(
            FileManagerFile.id == claims.resource_id,
            FileManagerFile.deleted_at.is_(None),
        )
    )
    if file is None:
        raise InvalidContentGrant("resource")
    corpus_id, acl_epoch = _file_content_acl_binding(file)
    if (
        claims.owner_app_id != "files"
        or claims.source_type != "file_corpus"
        or claims.source_id != corpus_id
        or claims.object_identity != _file_content_object_identity(file)
        or claims.resource_version != str(acl_epoch)
    ):
        raise InvalidContentGrant("binding")

    user = db.get(User, claims.issuer_user_id)
    if user is None or user.status != "active" or user.login_blocked:
        raise InvalidContentGrant("principal")
    if claims.execution_context_kind != "company":
        raise InvalidContentGrant("app")
    app_enabled = (
        can_use_app(
            db,
            app_id="files",
            user_id=user.id,
        )
        if file.corpus is not None and file.corpus.access_scope_kind == "company"
        else can_use_app(
            db,
            app_id="files",
            user_id=user.id,
        )
    )
    if not app_enabled:
        raise InvalidContentGrant("app")
    try:
        authorized_file = files_service.require_file_access(
            db,
            user=user,
            file_id=file.id,
        )
    except HTTPException as error:
        raise InvalidContentGrant("source_acl") from error
    if claims.disposition == "inline" and not is_previewable_image(authorized_file):
        raise InvalidContentGrant("disposition")
    return _open_file_stream(authorized_file, disposition=claims.disposition)


def _open_file_stream(
    file: FileManagerFile,
    *,
    disposition: FileContentDisposition,
) -> ContentStream:
    try:
        obj = open_file_object(file.storage_key)
    except Exception as exc:
        raise localized_http_exception(
            status_code=502, code="files.storage_download_failed"
        ) from exc

    chunks: Iterator[bytes] | None = None
    buffered_chunks: list[bytes] = []
    if disposition == "inline":
        chunks = iter(obj.stream(FILE_CONTENT_CHUNK_SIZE))
        try:
            buffered_chunks, signature_prefix = _buffer_signature_prefix(chunks)
        except Exception as exc:
            _release_file_object(obj)
            raise localized_http_exception(
                status_code=502, code="files.storage_download_failed"
            ) from exc
        if not _matches_inline_image_signature(
            content_type=_normalized_content_type(file),
            prefix=signature_prefix,
        ):
            _release_file_object(obj)
            raise localized_http_exception(status_code=415, code="files.preview_unsupported_type")

    def body() -> Iterator[bytes]:
        try:
            if chunks is None:
                yield from obj.stream(FILE_CONTENT_CHUNK_SIZE)
            else:
                yield from buffered_chunks
                yield from chunks
        finally:
            _release_file_object(obj)

    filename = quote(file.filename, safe="")
    return ContentStream(
        body=body(),
        media_type=(
            _normalized_content_type(file)
            if disposition == "inline"
            else file.content_type or "application/octet-stream"
        ),
        headers={
            "Cache-Control": "private, no-store",
            "Content-Disposition": f"{disposition}; filename*=UTF-8''{filename}",
            "X-Content-Type-Options": "nosniff",
        },
    )


def _file_content_acl_binding(file: FileManagerFile) -> tuple[str, int | str]:
    if file.corpus_id is None:
        updated_at = file.updated_at
        return (
            _LEGACY_CORPUS_ID,
            updated_at.isoformat(timespec="microseconds")
            if updated_at is not None
            else _LEGACY_ACL_EPOCH,
        )
    corpus = file.corpus
    if corpus is None or corpus.id != file.corpus_id:
        raise ValueError("file content signing requires the current file corpus")
    return corpus.id, corpus.metadata_version


def _file_content_object_identity(file: FileManagerFile) -> str:
    updated_at = file.updated_at
    identity = json.dumps(
        {
            "storage_key": file.storage_key,
            "size_bytes": file.size_bytes,
            "updated_at": (
                updated_at.isoformat(timespec="microseconds") if updated_at is not None else None
            ),
        },
        ensure_ascii=True,
        separators=(",", ":"),
        sort_keys=True,
    ).encode("utf-8")
    return hashlib.sha256(identity).hexdigest()


def is_previewable_image(file: FileManagerFile) -> bool:
    return _normalized_content_type(file) in _SAFE_INLINE_IMAGE_CONTENT_TYPES


def _normalized_content_type(file: FileManagerFile) -> str:
    return (file.content_type or "").split(";", 1)[0].strip().lower()


def _buffer_signature_prefix(chunks: Iterator[bytes]) -> tuple[list[bytes], bytes]:
    buffered_chunks: list[bytes] = []
    prefix = bytearray()
    while len(prefix) < _INLINE_IMAGE_SIGNATURE_BYTES:
        try:
            chunk = next(chunks)
        except StopIteration:
            break
        buffered_chunks.append(chunk)
        prefix.extend(chunk[: _INLINE_IMAGE_SIGNATURE_BYTES - len(prefix)])
    return buffered_chunks, bytes(prefix)


def _matches_inline_image_signature(*, content_type: str, prefix: bytes) -> bool:
    if content_type == "image/png":
        return prefix.startswith(b"\x89PNG\r\n\x1a\n")
    if content_type == "image/jpeg":
        return prefix.startswith(b"\xff\xd8\xff")
    if content_type == "image/gif":
        return prefix.startswith((b"GIF87a", b"GIF89a"))
    if content_type == "image/webp":
        return prefix.startswith(b"RIFF") and prefix[8:12] == b"WEBP"
    return False


def _release_file_object(obj: FileStorageObject) -> None:
    try:
        obj.close()
    finally:
        obj.release_conn()
