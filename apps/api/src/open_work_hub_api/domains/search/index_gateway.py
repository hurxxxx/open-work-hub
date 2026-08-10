from __future__ import annotations

import json
import re
from collections.abc import Iterable, Mapping
from typing import Any

from open_work_hub_api.domains.retrieval.projection_identity import canonical_search_document_id


_KEYWORD_ACL_QUERY_FIELDS = (
    "owner_user_id",
    "visibility",
    "team_ids",
    "participant_user_ids",
    "shared_user_ids",
    "granted_user_ids",
    "target_keys",
)

KEYWORD_SEARCH_INDEX_SCHEMA_VERSION = 2
RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION = 3
_INDEX_GENERATION_PATTERN = re.compile(r"^[a-z0-9][a-z0-9_-]{0,63}$")


def keyword_search_index_alias(index_prefix: str) -> str:
    return f"{index_prefix}_keyword_search_documents"


def keyword_search_partitioned_index_alias(index_prefix: str) -> str:
    """Return the dedicated alias for partition-aware retrieval generations.

    Legacy search sources continue to use :func:`keyword_search_index_alias`
    until they are migrated. Keeping the aliases distinct prevents a Files-only
    v3 cutover from redirecting legacy writers into the partitioned schema.
    """

    return f"{keyword_search_index_alias(index_prefix)}_v3"


def keyword_search_index_name(index_prefix: str) -> str:
    """Return the stable read/write alias used by application callers."""

    return keyword_search_index_alias(index_prefix)


def keyword_search_legacy_index_name(index_prefix: str) -> str:
    return f"{keyword_search_index_alias(index_prefix)}_v1"


def keyword_search_versioned_index_name(
    index_prefix: str,
    *,
    generation: str = "bootstrap",
) -> str:
    normalized_generation = str(generation or "").strip().lower()
    if not _INDEX_GENERATION_PATTERN.fullmatch(normalized_generation):
        raise ValueError(
            "Keyword search index generation must contain only lowercase letters, "
            "digits, underscores, or hyphens"
        )
    return (
        f"{keyword_search_index_alias(index_prefix)}"
        f"_v{KEYWORD_SEARCH_INDEX_SCHEMA_VERSION}_{normalized_generation}"
    )


def keyword_search_partitioned_index_name(
    index_prefix: str,
    *,
    generation: str,
) -> str:
    normalized_generation = _normalize_index_generation(generation)
    return (
        f"{keyword_search_index_alias(index_prefix)}"
        f"_v{RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION}_{normalized_generation}"
    )


def keyword_index_definition() -> dict[str, Any]:
    return {
        "settings": {
            "number_of_replicas": 0,
            "similarity": {
                "keyword_bm25": {
                    "type": "BM25",
                    "k1": 1.2,
                    "b": 0.75,
                }
            },
            "analysis": {
                "normalizer": {
                    "normalized_keyword": {
                        "type": "custom",
                        "filter": ["lowercase", "asciifolding"],
                    },
                },
                "tokenizer": {
                    "korean_nori_tokenizer": {
                        "type": "nori_tokenizer",
                        "decompound_mode": "mixed",
                        "discard_punctuation": True,
                    },
                    "korean_ngram_tokenizer": {
                        "type": "ngram",
                        "min_gram": 2,
                        "max_gram": 3,
                        "token_chars": ["letter", "digit"],
                    },
                },
                "analyzer": {
                    "korean_nori": {
                        "type": "custom",
                        "tokenizer": "korean_nori_tokenizer",
                        "filter": ["lowercase"],
                    },
                    "korean_ngram_partial": {
                        "type": "custom",
                        "tokenizer": "korean_ngram_tokenizer",
                        "filter": ["lowercase"],
                    },
                },
            },
        },
        "mappings": {
            "_meta": {
                "schema": "keyword_search_documents",
                "schema_version": KEYWORD_SEARCH_INDEX_SCHEMA_VERSION,
            },
            "dynamic": "false",
            "properties": {
                "workspace_id": {"type": "keyword"},
                "dataset_id": {"type": "keyword"},
                "entity_type": {"type": "keyword"},
                "entity_id": {"type": "keyword"},
                **keyword_acl_query_properties(),
                "title": keyword_text_field(include_legacy_keyword=True),
                "summary": keyword_text_field(),
                "body": keyword_text_field(),
                "keywords": keyword_text_field(),
                "search_text": keyword_text_field(),
                "status": {"type": "keyword"},
                "status_label": {"type": "keyword"},
                "visibility": {"type": "keyword"},
                "people": {
                    "properties": {
                        "role": {"type": "keyword"},
                        "user_id": {"type": "keyword"},
                        "label": {"type": "keyword"},
                    }
                },
                "targets": {
                    "properties": {
                        "app": {"type": "keyword"},
                        "type": {"type": "keyword"},
                        "id": {"type": "keyword"},
                        "label": {"type": "keyword"},
                    }
                },
                "date_markers": {"type": "object", "dynamic": "true"},
                "deep_link": {"type": "keyword"},
                "preview_url": {"type": "keyword"},
                "metadata": {"type": "object", "enabled": True},
                "rank_boost": {"type": "float"},
                "source_updated_at": {"type": "date"},
                "created_at": {"type": "date"},
            },
        },
    }


def keyword_partitioned_index_definition() -> dict[str, Any]:
    """Return the non-live v3 schema used by ADR 0009 generation rebuilds."""

    definition = keyword_index_definition()
    mappings = definition["mappings"]
    mappings["_meta"] = {
        "schema": "keyword_search_documents",
        "schema_version": RETRIEVAL_PARTITIONED_INDEX_SCHEMA_VERSION,
        "identity": "canonical_resource_v1",
    }
    mappings["properties"].update(
        {
            "resource_type": {"type": "keyword"},
            "retrieval_partition_id": {"type": "keyword"},
            "projection_version": {"type": "long"},
        }
    )
    return definition


def keyword_text_field(*, include_legacy_keyword: bool = False) -> dict[str, Any]:
    fields: dict[str, Any] = {
        "partial": {
            "type": "text",
            "analyzer": "korean_ngram_partial",
            "search_analyzer": "korean_ngram_partial",
            "similarity": "keyword_bm25",
        },
        "exact": {
            "type": "keyword",
            "normalizer": "normalized_keyword",
            "ignore_above": 2048,
        },
    }
    if include_legacy_keyword:
        fields["keyword"] = {"type": "keyword", "ignore_above": 2048}
    return {
        "type": "text",
        "analyzer": "korean_nori",
        "search_analyzer": "korean_nori",
        "similarity": "keyword_bm25",
        "fields": fields,
    }


def keyword_acl_query_properties() -> dict[str, Any]:
    return {field: {"type": "keyword"} for field in _KEYWORD_ACL_QUERY_FIELDS}


def keyword_acl_query_field_names() -> frozenset[str]:
    return frozenset(_KEYWORD_ACL_QUERY_FIELDS)


def keyword_existing_index_mapping_properties() -> dict[str, Any]:
    return {
        "dataset_id": {"type": "keyword"},
        **keyword_acl_query_properties(),
    }


def search_index_document_key(*, workspace_id: str, entity_type: str, entity_id: str) -> str:
    return f"{workspace_id}:{entity_type}:{entity_id}"


def search_index_document_id(document: Mapping[str, Any]) -> str:
    return search_index_document_key(
        workspace_id=str(document["workspace_id"]),
        entity_type=str(document["entity_type"]),
        entity_id=str(document["entity_id"]),
    )


def build_bulk_index_ndjson(*, index_name: str, documents: Iterable[Mapping[str, Any]]) -> str:
    lines: list[str] = []
    for document in documents:
        lines.append(
            _json_dumps(
                {"index": {"_index": index_name, "_id": search_index_document_id(document)}}
            )
        )
        lines.append(_json_dumps(document))
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def build_partitioned_bulk_index_ndjson(
    *,
    index_name: str,
    documents: Iterable[Mapping[str, Any]],
) -> str:
    """Build strict external-version actions for a clean v3 generation."""

    lines: list[str] = []
    for document in documents:
        resource_type, resource_id, projection_version = _partitioned_document_identity(document)
        lines.append(
            _json_dumps(
                {
                    "index": {
                        "_index": index_name,
                        "_id": canonical_search_document_id(
                            resource_type=resource_type,
                            resource_id=resource_id,
                        ),
                        "version": projection_version,
                        "version_type": "external",
                    }
                }
            )
        )
        lines.append(_json_dumps(document))
    if not lines:
        return ""
    return "\n".join(lines) + "\n"


def bulk_index_error_message(payload: Mapping[str, Any]) -> str | None:
    if not payload.get("errors"):
        return None
    return f"OpenSearch bulk indexing failed: {str(payload)[:500]}"


def _json_dumps(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def _normalize_index_generation(generation: object) -> str:
    normalized_generation = str(generation or "").strip().lower()
    if not _INDEX_GENERATION_PATTERN.fullmatch(normalized_generation):
        raise ValueError(
            "Keyword search index generation must contain only lowercase letters, "
            "digits, underscores, or hyphens"
        )
    return normalized_generation


def _partitioned_document_identity(document: Mapping[str, Any]) -> tuple[str, str, int]:
    resource_type = str(document.get("resource_type") or "").strip()
    resource_id = str(document.get("entity_id") or "").strip()
    partition_id = str(document.get("retrieval_partition_id") or "").strip()
    projection_version = document.get("projection_version")
    if not resource_type or not resource_id or not partition_id:
        raise ValueError(
            "Partitioned keyword documents require resource_type, entity_id, and "
            "retrieval_partition_id"
        )
    if isinstance(projection_version, bool) or not isinstance(projection_version, int):
        raise ValueError("Partitioned keyword documents require an integer projection_version")
    if projection_version <= 0:
        raise ValueError("Partitioned keyword projection_version must be greater than zero")
    return resource_type, resource_id, projection_version
