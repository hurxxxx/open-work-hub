from __future__ import annotations

import base64

import pytest
from fastapi import HTTPException, status

from ai_do_api.domains.recording import tus_protocol


def _encoded(value: str) -> str:
    return base64.b64encode(value.encode("utf-8")).decode("ascii")


def test_response_headers_include_tus_contract_and_optional_offset() -> None:
    assert tus_protocol.response_headers(
        upload_offset=128,
        upload_length=512,
        max_size_bytes=1024,
    ) == {
        "Tus-Resumable": "1.0.0",
        "Tus-Version": "1.0.0",
        "Tus-Extension": "creation,creation-defer-length,checksum",
        "Access-Control-Expose-Headers": (
            "Tus-Resumable,Tus-Version,Tus-Extension,Tus-Max-Size,"
            "Upload-Offset,Upload-Length,Location"
        ),
        "Tus-Max-Size": "1024",
        "Upload-Offset": "128",
        "Upload-Length": "512",
    }


def test_require_version_rejects_missing_or_unsupported_tus_version() -> None:
    tus_protocol.require_version("1.0.0")

    with pytest.raises(HTTPException) as exc_info:
        tus_protocol.require_version(None)

    assert exc_info.value.status_code == status.HTTP_412_PRECONDITION_FAILED
    assert exc_info.value.headers is not None
    assert exc_info.value.headers["Tus-Resumable"] == "1.0.0"


def test_parse_upload_metadata_decodes_base64_values_and_empty_entries() -> None:
    assert tus_protocol.parse_upload_metadata(
        f"idempotency_key {_encoded('upload-1')},"
        f"mime_type {_encoded('audio/webm')},"
        "defer,"
        f"title {_encoded('Daily notes')}"
    ) == {
        "idempotency_key": "upload-1",
        "mime_type": "audio/webm",
        "defer": "",
        "title": "Daily notes",
    }


def test_parse_upload_metadata_rejects_invalid_values() -> None:
    with pytest.raises(HTTPException) as exc_info:
        tus_protocol.parse_upload_metadata("mime_type !!!")

    assert exc_info.value.status_code == status.HTTP_400_BAD_REQUEST


def test_parse_checksum_accepts_sha256_and_returns_hex_digest() -> None:
    checksum = tus_protocol.parse_checksum(f"sha256 {_encoded('abc')}")

    assert checksum == "616263"
    assert tus_protocol.parse_checksum(None) is None


def test_parse_checksum_rejects_unsupported_algorithm_or_bad_base64() -> None:
    with pytest.raises(HTTPException) as algorithm_exc:
        tus_protocol.parse_checksum(f"md5 {_encoded('abc')}")
    with pytest.raises(HTTPException) as value_exc:
        tus_protocol.parse_checksum("sha256 !!!")

    assert algorithm_exc.value.status_code == status.HTTP_400_BAD_REQUEST
    assert value_exc.value.status_code == status.HTTP_400_BAD_REQUEST


def test_upload_length_meta_helpers_preserve_existing_metadata() -> None:
    meta = tus_protocol.with_upload_length({"title": "demo"}, 4096)

    assert meta == {
        "title": "demo",
        tus_protocol.TUS_UPLOAD_LENGTH_META_KEY: "4096",
    }
    assert tus_protocol.upload_length_from_meta(meta) == 4096
    assert tus_protocol.upload_length_from_meta({"__tus_upload_length": "bad"}) is None
    assert tus_protocol.upload_length_from_meta(None) is None
