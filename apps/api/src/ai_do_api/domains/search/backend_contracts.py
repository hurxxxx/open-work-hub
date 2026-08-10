from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Literal, Protocol, runtime_checkable


class KeywordSearchBackendError(RuntimeError):
    pass


KeywordSearchSortDirection = Literal["asc", "desc"]
KeywordSearchTextOperator = Literal["and", "or"]


@dataclass(frozen=True, slots=True)
class KeywordAclClause:
    field: str
    values: tuple[str, ...]

    def __post_init__(self) -> None:
        object.__setattr__(self, "field", str(self.field or "").strip())
        object.__setattr__(
            self,
            "values",
            tuple(str(value) for value in self.values if str(value).strip()),
        )
        if not self.field:
            raise ValueError("Keyword ACL clause field is required")


@dataclass(frozen=True, slots=True)
class KeywordAclBranch:
    entity_type: str
    clauses: tuple[KeywordAclClause, ...] = ()

    def __post_init__(self) -> None:
        entity_type = str(self.entity_type or "").strip()
        if not entity_type:
            raise ValueError("Keyword ACL branch entity_type is required")
        object.__setattr__(self, "entity_type", entity_type)


@dataclass(frozen=True, slots=True)
class KeywordAclFilter:
    branches: tuple[KeywordAclBranch, ...] = ()


@dataclass(frozen=True, slots=True)
class KeywordPeopleFilter:
    role: str = "any"
    user_ids: tuple[str, ...] = ()


@dataclass(frozen=True, slots=True)
class KeywordDateFilter:
    field: str
    from_value: str | None = None
    to_value: str | None = None


@dataclass(frozen=True, slots=True)
class KeywordSearchSortSpec:
    field: str
    direction: KeywordSearchSortDirection = "desc"
    unmapped_type: str | None = None


@dataclass(frozen=True, slots=True)
class KeywordSearchQuery:
    workspace_id: str
    retrieval_partition_ids: tuple[str, ...] | None = None
    text: str = ""
    entity_types: tuple[str, ...] = ()
    acl_filter: KeywordAclFilter | None = None
    status_by_type: tuple[tuple[str, tuple[str, ...]], ...] = ()
    people: KeywordPeopleFilter = field(default_factory=KeywordPeopleFilter)
    target_keys: tuple[str, ...] = ()
    target_key_groups: tuple[tuple[str, ...], ...] = ()
    date_filters: tuple[KeywordDateFilter, ...] = ()
    dataset_id: str | None = None
    include_missing_dataset: bool = False
    sort: tuple[KeywordSearchSortSpec, ...] = ()
    size: int = 10000
    search_after: tuple[Any, ...] = ()
    point_in_time_id: str | None = None
    point_in_time_keep_alive: str = "1m"
    text_operator: KeywordSearchTextOperator = "and"
    text_minimum_should_match: str | int | None = None
    phrase_match_fields: tuple[str, ...] = ()
    phrase_boost: float = 1.5
    request_timeout_seconds: float | None = None

    def __post_init__(self) -> None:
        if self.retrieval_partition_ids is None:
            return
        normalized = tuple(
            dict.fromkeys(
                str(partition_id).strip()
                for partition_id in self.retrieval_partition_ids
                if str(partition_id).strip()
            )
        )
        if not normalized or len(normalized) != len(self.retrieval_partition_ids):
            raise ValueError("retrieval_partition_ids must contain unique non-blank partition ids")
        object.__setattr__(self, "retrieval_partition_ids", normalized)


@dataclass(frozen=True, slots=True)
class KeywordSearchHit:
    document: dict[str, Any]
    score: float = 0.0
    sort_values: tuple[Any, ...] = ()


@dataclass(frozen=True, slots=True)
class KeywordSearchResult:
    hits: tuple[KeywordSearchHit, ...]


class KeywordSearchBackendSettings(Protocol):
    keyword_search_backend: str
    opensearch_url: str
    opensearch_index_prefix: str


class KeywordSearchClient(Protocol):
    def ensure_index(self) -> None: ...

    def index_exists(self) -> bool: ...

    def rebuild_workspace(
        self,
        *,
        workspace_id: str,
        documents: list[dict[str, Any]],
    ) -> None: ...

    def upsert_document(self, document: dict[str, Any]) -> None: ...

    def delete_document(
        self,
        *,
        workspace_id: str,
        entity_type: str,
        entity_id: str,
    ) -> None: ...

    def count_workspace_documents(
        self,
        *,
        workspace_id: str,
        entity_types: tuple[str, ...] = (),
    ) -> int: ...

    def search(self, query: KeywordSearchQuery) -> KeywordSearchResult: ...

    def open_point_in_time(self, *, keep_alive: str = "1m") -> str: ...

    def close_point_in_time(self, point_in_time_id: str) -> None: ...


@runtime_checkable
class PartitionedKeywordGenerationClient(Protocol):
    """Mutation surface required to materialize one isolated v3 generation."""

    def upsert_partitioned_document(self, document: dict[str, Any]) -> str: ...

    def delete_partitioned_document(
        self,
        *,
        resource_type: str,
        resource_id: str,
        projection_version: int,
    ) -> str: ...

    def refresh_partitioned_index(self) -> None: ...


def keyword_acl_clause(field: str, value: str | list[str] | tuple[str, ...]) -> KeywordAclClause:
    values = (value,) if isinstance(value, str) else tuple(value)
    return KeywordAclClause(field=field, values=tuple(str(item) for item in values))


__all__ = [
    "KeywordAclBranch",
    "KeywordAclClause",
    "KeywordAclFilter",
    "KeywordDateFilter",
    "KeywordPeopleFilter",
    "KeywordSearchBackendError",
    "KeywordSearchBackendSettings",
    "KeywordSearchClient",
    "KeywordSearchHit",
    "KeywordSearchQuery",
    "KeywordSearchResult",
    "KeywordSearchSortDirection",
    "KeywordSearchSortSpec",
    "KeywordSearchTextOperator",
    "PartitionedKeywordGenerationClient",
    "keyword_acl_clause",
]
