from __future__ import annotations

import base64
import binascii
from collections.abc import Mapping
from typing import Any

from fastapi import status

from ai_do_api.core.i18n import localized_http_exception
from ai_do_api.core.settings import get_settings


TUS_RESUMABLE_VERSION = "1.0.0"
TUS_EXTENSION_HEADER = "creation,creation-defer-length,checksum"
TUS_UPLOAD_LENGTH_META_KEY = "__tus_upload_length"


def response_headers(
    *,
    upload_offset: int | None = None,
    upload_length: int | None = None,
    max_size_bytes: int | None = None,
) -> dict[str, str]:
    headers = {
        "Tus-Resumable": TUS_RESUMABLE_VERSION,
        "Tus-Version": TUS_RESUMABLE_VERSION,
        "Tus-Extension": TUS_EXTENSION_HEADER,
        "Access-Control-Expose-Headers": (
            "Tus-Resumable,Tus-Version,Tus-Extension,Tus-Max-Size,"
            "Upload-Offset,Upload-Length,Location"
        ),
        "Tus-Max-Size": str(
            max_size_bytes
            if max_size_bytes is not None
            else get_settings().recording_max_size_bytes
        ),
    }
    if upload_offset is not None:
        headers["Upload-Offset"] = str(upload_offset)
    if upload_length is not None:
        headers["Upload-Length"] = str(upload_length)
    return headers


def require_version(value: str | None) -> None:
    if value == TUS_RESUMABLE_VERSION:
        return
    raise localized_http_exception(
        status_code=status.HTTP_412_PRECONDITION_FAILED,
        code="recording.tus_version_required",
        headers=response_headers(),
    )


def parse_upload_metadata(value: str | None) -> dict[str, str]:
    if not value:
        return {}
    parsed: dict[str, str] = {}
    for raw_item in value.split(","):
        item = raw_item.strip()
        if not item:
            continue
        key, _, encoded = item.partition(" ")
        key = key.strip()
        if not key:
            raise _invalid_metadata()
        if not encoded:
            parsed[key] = ""
            continue
        try:
            parsed[key] = base64.b64decode(encoded, validate=True).decode("utf-8")
        except (binascii.Error, UnicodeDecodeError) as exc:
            raise _invalid_metadata() from exc
    return parsed


def parse_checksum(value: str | None) -> str | None:
    if not value:
        return None
    algorithm, _, encoded = value.partition(" ")
    if algorithm.lower() != "sha256" or not encoded:
        raise _invalid_checksum()
    try:
        return base64.b64decode(encoded, validate=True).hex()
    except binascii.Error as exc:
        raise _invalid_checksum() from exc


def upload_length_from_meta(chunks_meta: Mapping[str, Any] | None) -> int | None:
    value = (chunks_meta or {}).get(TUS_UPLOAD_LENGTH_META_KEY)
    if value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def with_upload_length(
    chunks_meta: Mapping[str, Any] | None,
    upload_length: int,
) -> dict[str, Any]:
    meta = dict(chunks_meta or {})
    meta[TUS_UPLOAD_LENGTH_META_KEY] = str(upload_length)
    return meta


def _invalid_metadata():
    return localized_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="recording.tus_metadata_invalid",
        headers=response_headers(),
    )


def _invalid_checksum():
    return localized_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="recording.tus_checksum_invalid",
        headers=response_headers(),
    )
