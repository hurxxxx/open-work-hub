from __future__ import annotations

from collections.abc import Collection
from typing import Any

from open_work_hub_api.domains.search.index_gateway import keyword_acl_query_field_names


class SearchProjectionIdentityError(RuntimeError):
    pass


def ensure_search_document_identity(
    document: dict[str, Any],
    *,
    workspace_id: str,
    allowed_entity_types: Collection[str],
    expected_entity_id: str | None = None,
    context: str,
) -> None:
    entity_id = str(document.get("entity_id") or "")
    mismatches: list[str] = []
    if str(document.get("workspace_id") or "") != workspace_id:
        mismatches.append("workspace_id")
    if str(document.get("entity_type") or "") not in allowed_entity_types:
        mismatches.append("entity_type")
    if not entity_id or (expected_entity_id is not None and entity_id != expected_entity_id):
        mismatches.append("entity_id")
    if mismatches:
        raise SearchProjectionIdentityError(
            f"Search projection identity mismatch for {context}: {', '.join(mismatches)}"
        )
    ensure_search_document_acl_shape(document, context=context)


def ensure_search_document_acl_shape(
    document: dict[str, Any],
    *,
    context: str,
) -> None:
    required_fields = keyword_acl_query_field_names()
    missing_fields = sorted(required_fields - document.keys())
    invalid_fields: list[str] = []
    owner_user_id = document.get("owner_user_id")
    if (
        "owner_user_id" in document
        and owner_user_id is not None
        and not isinstance(owner_user_id, str)
    ):
        invalid_fields.append("owner_user_id")
    visibility = document.get("visibility")
    if "visibility" in document and visibility is not None and not isinstance(visibility, str):
        invalid_fields.append("visibility")
    for field in sorted(required_fields - {"owner_user_id", "visibility"}):
        if field not in document:
            continue
        value = document[field]
        if not isinstance(value, list) or any(not isinstance(item, str) for item in value):
            invalid_fields.append(field)
    if missing_fields or invalid_fields:
        details: list[str] = []
        if missing_fields:
            details.append("missing=" + ",".join(missing_fields))
        if invalid_fields:
            details.append("invalid=" + ",".join(invalid_fields))
        raise SearchProjectionIdentityError(
            f"Search projection ACL shape mismatch for {context}: {'; '.join(details)}"
        )


__all__ = [
    "SearchProjectionIdentityError",
    "ensure_search_document_acl_shape",
    "ensure_search_document_identity",
]
