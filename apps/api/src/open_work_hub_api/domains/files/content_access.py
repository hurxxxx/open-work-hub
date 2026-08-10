from __future__ import annotations

import base64
import binascii
from collections.abc import Iterator
from dataclasses import dataclass
import hashlib
import hmac
import json
import time
from typing import Literal
from urllib.parse import quote

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.orm import Session, joinedload

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.auth.access import resolve_workspace_role
from open_work_hub_api.domains.auth.models import User, Workspace
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


@dataclass(frozen=True)
class FileContentStream:
    body: Iterator[bytes]
    media_type: str
    headers: dict[str, str]


@dataclass(frozen=True)
class _FileContentClaims:
    file_id: str
    issuer_user_id: str
    execution_workspace_id: str
    corpus_id: str
    acl_epoch: int | str
    object_identity: str
    expires: int
    disposition: FileContentDisposition


def build_file_content_url(
    file: FileManagerFile,
    *,
    issuer_user_id: str,
    execution_workspace_id: str,
    disposition: FileContentDisposition,
    now: float | None = None,
    expires_seconds: int = FILE_CONTENT_URL_EXPIRES_SECONDS,
) -> str:
    expires = int(time.time() if now is None else now) + expires_seconds
    signature = sign_file_content_url(
        file,
        issuer_user_id=issuer_user_id,
        execution_workspace_id=execution_workspace_id,
        expires=expires,
        disposition=disposition,
    )
    return (
        f"{get_settings().api_prefix}/files/content/{file.id}"
        f"?expires={expires}&signature={signature}&disposition={disposition}"
    )


def sign_file_content_url(
    file: FileManagerFile,
    *,
    issuer_user_id: str,
    execution_workspace_id: str,
    expires: int,
    disposition: FileContentDisposition,
) -> str:
    corpus_id, acl_epoch = _file_content_acl_binding(file)
    object_identity = _file_content_object_identity(file)
    payload = json.dumps(
        {
            "v": 2,
            "f": file.id,
            "u": issuer_user_id,
            "w": execution_workspace_id,
            "c": corpus_id,
            "a": acl_epoch,
            "o": object_identity,
            "x": expires,
            "d": disposition,
        },
        ensure_ascii=True,
        separators=(",", ":"),
    ).encode("utf-8")
    encoded_payload = _base64url_encode(payload)
    digest = hmac.new(
        get_settings().minio_secret_key.encode("utf-8"),
        encoded_payload.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return f"{encoded_payload}.{_base64url_encode(digest)}"


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


def open_file_content(
    db: Session,
    *,
    file_id: str,
    expires: int,
    signature: str,
    disposition: FileContentDisposition,
    now: float | None = None,
) -> FileContentStream:
    claims = _decode_file_content_claims(signature)
    if claims.file_id != file_id or claims.expires != expires or claims.disposition != disposition:
        _raise_invalid_content_url()
    if expires < int(time.time() if now is None else now):
        raise localized_http_exception(status_code=403, code="files.proxy_url_expired")

    file = db.scalar(
        select(FileManagerFile)
        .options(joinedload(FileManagerFile.corpus))
        .where(
            FileManagerFile.id == file_id,
            FileManagerFile.deleted_at.is_(None),
        )
    )
    if file is None:
        raise localized_http_exception(status_code=404, code="files.file_not_found")
    expected = sign_file_content_url(
        file,
        issuer_user_id=claims.issuer_user_id,
        execution_workspace_id=claims.execution_workspace_id,
        expires=expires,
        disposition=disposition,
    )
    if not hmac.compare_digest(signature, expected):
        _raise_invalid_content_url()

    user = db.get(User, claims.issuer_user_id)
    workspace = db.get(Workspace, claims.execution_workspace_id)
    if (
        user is None
        or user.status != "active"
        or user.login_blocked
        or workspace is None
        or not workspace.active
    ):
        _raise_invalid_content_url()
    company_corpus = file.corpus is not None and file.corpus.access_scope_kind == "company"
    if not company_corpus and resolve_workspace_role(db, user, workspace.id) is None:
        raise localized_http_exception(status_code=403, code="files.file_access_required")
    file = files_service.require_file_access(
        db,
        workspace=workspace,
        user=user,
        file_id=file_id,
    )
    if disposition == "inline" and not is_previewable_image(file):
        raise localized_http_exception(status_code=415, code="files.preview_unsupported_type")

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
    return FileContentStream(
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


def _decode_file_content_claims(signature: str) -> _FileContentClaims:
    try:
        encoded_payload, encoded_digest = signature.split(".", 1)
        supplied_digest = _base64url_decode(encoded_digest)
        expected_digest = hmac.new(
            get_settings().minio_secret_key.encode("utf-8"),
            encoded_payload.encode("ascii"),
            hashlib.sha256,
        ).digest()
        if not hmac.compare_digest(supplied_digest, expected_digest):
            _raise_invalid_content_url()
        payload = json.loads(_base64url_decode(encoded_payload))
        if not isinstance(payload, dict) or set(payload) != {
            "v",
            "f",
            "u",
            "w",
            "c",
            "a",
            "o",
            "x",
            "d",
        }:
            _raise_invalid_content_url()
        if payload["v"] != 2 or payload["d"] not in {"attachment", "inline"}:
            _raise_invalid_content_url()
        if not all(
            isinstance(payload[key], str) and payload[key] for key in ("f", "u", "w", "c", "o")
        ):
            _raise_invalid_content_url()
        if not isinstance(payload["x"], int) or isinstance(payload["x"], bool):
            _raise_invalid_content_url()
        if not isinstance(payload["a"], (int, str)) or isinstance(payload["a"], bool):
            _raise_invalid_content_url()
        return _FileContentClaims(
            file_id=payload["f"],
            issuer_user_id=payload["u"],
            execution_workspace_id=payload["w"],
            corpus_id=payload["c"],
            acl_epoch=payload["a"],
            object_identity=payload["o"],
            expires=payload["x"],
            disposition=payload["d"],
        )
    except HTTPException:
        raise
    except (binascii.Error, UnicodeDecodeError, ValueError, TypeError, json.JSONDecodeError):
        _raise_invalid_content_url()


def _base64url_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _base64url_decode(value: str) -> bytes:
    return base64.b64decode(
        value + "=" * (-len(value) % 4),
        altchars=b"-_",
        validate=True,
    )


def _raise_invalid_content_url() -> None:
    raise localized_http_exception(status_code=403, code="files.proxy_url_invalid")
