from __future__ import annotations

from uuid import UUID, uuid5


RETRIEVAL_PROJECTION_UUID_NAMESPACE = UUID("f644b350-f797-5bc6-b048-b19d25fe2ce8")
_IDENTITY_VERSION = "ai-do-retrieval-v1"


class RetrievalProjectionIdentityError(ValueError):
    pass


def canonical_resource_key(*, resource_type: object, resource_id: object) -> str:
    return _encode_identity(
        "resource",
        _normalize_component(resource_type, label="resource_type"),
        _normalize_component(resource_id, label="resource_id"),
    )


def canonical_search_document_id(*, resource_type: object, resource_id: object) -> str:
    return str(
        uuid5(
            RETRIEVAL_PROJECTION_UUID_NAMESPACE,
            canonical_resource_key(
                resource_type=resource_type,
                resource_id=resource_id,
            ),
        )
    )


def canonical_vector_point_id(
    *,
    resource_type: object,
    resource_id: object,
    chunk_id: object,
) -> str:
    return str(
        uuid5(
            RETRIEVAL_PROJECTION_UUID_NAMESPACE,
            _encode_identity(
                "chunk",
                _normalize_component(resource_type, label="resource_type"),
                _normalize_component(resource_id, label="resource_id"),
                _normalize_component(chunk_id, label="chunk_id"),
            ),
        )
    )


def _encode_identity(purpose: str, *components: str) -> str:
    values = (_IDENTITY_VERSION, purpose, *components)
    return "|".join(f"{len(value.encode('utf-8'))}:{value}" for value in values)


def _normalize_component(value: object, *, label: str) -> str:
    if value is None:
        raise RetrievalProjectionIdentityError(f"{label} must not be blank")
    normalized = str(value).strip()
    if not normalized:
        raise RetrievalProjectionIdentityError(f"{label} must not be blank")
    return normalized


__all__ = [
    "RETRIEVAL_PROJECTION_UUID_NAMESPACE",
    "RetrievalProjectionIdentityError",
    "canonical_resource_key",
    "canonical_search_document_id",
    "canonical_vector_point_id",
]
