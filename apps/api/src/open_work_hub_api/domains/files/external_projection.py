from __future__ import annotations

from datetime import UTC, datetime
from hashlib import sha256
from typing import Any

from open_work_hub_api.domains.files.models import FileManagerFile
from open_work_hub_api.domains.files.retrieval_contract import FILES_RAG_SOURCE_KIND


EXTERNAL_SOURCE_TARGET_APP = "files"
EXTERNAL_SOURCE_TARGET_TYPES = {
    "origin_source_kind": "file_origin_source",
    "author": "file_author",
    "department": "file_department",
    "document_type": "file_document_type",
}
EXTERNAL_SOURCE_SAFE_METADATA_KEYS = frozenset(
    {
        "origin_source_kind",
        "origin_source_kind_filter",
        "source_title",
        "author",
        "author_filter",
        "authored_at",
        "department",
        "department_filter",
        "document_type",
        "document_type_filter",
        "source_updated_at",
    }
)


def external_source_kind(file: FileManagerFile) -> str:
    metadata = _source_metadata(file)
    return metadata.source_kind if metadata is not None else FILES_RAG_SOURCE_KIND


def external_source_title(file: FileManagerFile) -> str:
    metadata = _source_metadata(file)
    if metadata is not None and metadata.title:
        return metadata.title
    return file.filename


def external_source_updated_at(file: FileManagerFile) -> datetime:
    metadata = _source_metadata(file)
    if metadata is not None and metadata.source_updated_at is not None:
        return metadata.source_updated_at
    return file.updated_at


def external_source_keywords(file: FileManagerFile) -> tuple[str, ...]:
    metadata = _source_metadata(file)
    values = [file.filename, external_source_kind(file)]
    if metadata is not None:
        values.extend(
            [
                metadata.title,
                metadata.author,
                metadata.department,
                metadata.document_type,
            ]
        )
    return tuple(dict.fromkeys(value for value in values if value))


def external_source_targets(file: FileManagerFile) -> list[dict[str, str]]:
    metadata = _source_metadata(file)
    values: dict[str, str | None] = {
        "origin_source_kind": external_source_kind(file),
        "author": metadata.author if metadata is not None else None,
        "department": metadata.department if metadata is not None else None,
        "document_type": metadata.document_type if metadata is not None else None,
    }
    return [
        {
            "app": EXTERNAL_SOURCE_TARGET_APP,
            "type": EXTERNAL_SOURCE_TARGET_TYPES[field],
            "id": external_source_target_id(value),
            "label": value,
        }
        for field, value in values.items()
        if value
    ]


def external_source_target_id(value: str) -> str:
    normalized = external_source_filter_value(value)
    return sha256(normalized.encode("utf-8")).hexdigest()


def external_source_filter_value(value: str) -> str:
    return " ".join(value.split()).casefold()


def external_source_date_markers(file: FileManagerFile) -> dict[str, str]:
    metadata = _source_metadata(file)
    if metadata is None:
        return {}
    return {
        key: value.isoformat()
        for key, value in {
            "authored_at": metadata.authored_at,
            "source_updated_at": metadata.source_updated_at,
        }.items()
        if value is not None
    }


def safe_external_source_metadata(file: FileManagerFile) -> dict[str, Any]:
    """Return searchable source fields without private identity, raw ACL, or URI."""

    metadata = _source_metadata(file)
    if metadata is None:
        return {
            "origin_source_kind": FILES_RAG_SOURCE_KIND,
            "origin_source_kind_filter": FILES_RAG_SOURCE_KIND,
        }
    values: dict[str, Any] = {
        "origin_source_kind": metadata.source_kind,
        "origin_source_kind_filter": external_source_filter_value(metadata.source_kind),
        "source_title": metadata.title,
        "author": metadata.author,
        "author_filter": (
            external_source_filter_value(metadata.author) if metadata.author else None
        ),
        "authored_at": (
            _utc_isoformat(metadata.authored_at) if metadata.authored_at is not None else None
        ),
        "department": metadata.department,
        "department_filter": (
            external_source_filter_value(metadata.department) if metadata.department else None
        ),
        "document_type": metadata.document_type,
        "document_type_filter": (
            external_source_filter_value(metadata.document_type) if metadata.document_type else None
        ),
        "source_updated_at": (
            _utc_isoformat(metadata.source_updated_at)
            if metadata.source_updated_at is not None
            else None
        ),
    }
    return {key: value for key, value in values.items() if value is not None}


def _utc_isoformat(value: datetime) -> str:
    aware = value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)
    return aware.isoformat()


def _source_metadata(file: FileManagerFile) -> Any | None:
    """Support canonical ORM rows and bounded projection snapshots alike."""

    return getattr(file, "source_metadata", None)


def refresh_safe_external_source_metadata(
    indexed_metadata: dict[str, Any],
    *,
    file: FileManagerFile,
) -> dict[str, Any]:
    """Replace projected source fields with the current PostgreSQL values."""

    refreshed = dict(indexed_metadata)
    for key in EXTERNAL_SOURCE_SAFE_METADATA_KEYS:
        refreshed.pop(key, None)
    refreshed.update(safe_external_source_metadata(file))
    return refreshed


__all__ = [
    "EXTERNAL_SOURCE_TARGET_APP",
    "EXTERNAL_SOURCE_TARGET_TYPES",
    "EXTERNAL_SOURCE_SAFE_METADATA_KEYS",
    "external_source_date_markers",
    "external_source_filter_value",
    "external_source_keywords",
    "external_source_kind",
    "external_source_target_id",
    "external_source_targets",
    "external_source_title",
    "external_source_updated_at",
    "refresh_safe_external_source_metadata",
    "safe_external_source_metadata",
]
