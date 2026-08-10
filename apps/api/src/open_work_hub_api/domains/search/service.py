from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, replace
from typing import Any

from fastapi import status
from sqlalchemy import select
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.core.telemetry import current_trace_id
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.auth.access import resolve_workspace_enabled_app_ids
from open_work_hub_api.domains.docs.content_text import extract_page_text
from open_work_hub_api.domains.docs.models import NativeDocPage
from open_work_hub_api.domains.files.search_projection import (
    hydrate_file_search_rows_from_source,
)
from open_work_hub_api.domains.search.backend_contracts import (
    KeywordAclFilter,
    KeywordSearchBackendError,
    KeywordSearchClient,
    KeywordSearchTextOperator,
)
from open_work_hub_api.domains.search.backend_factory import build_keyword_search_client
from open_work_hub_api.domains.search.projections import all_workspace_search_documents
from open_work_hub_api.domains.search.entity_adapter_registry import (
    WorkspaceKeywordSearchScope,
    resolve_workspace_keyword_search_scope,
)
from open_work_hub_api.domains.search.query_policy import (
    DEFAULT_KEYWORD_SEARCH_CANDIDATE_SIZE,
    build_keyword_search_query,
    filter_and_sort_keyword_search_rows,
)
from open_work_hub_api.domains.search.result_projection import project_keyword_search_response
from open_work_hub_api.domains.search.schemas import KeywordSearchRequest, KeywordSearchResponse
from open_work_hub_api.domains.search.resource_mapping import maybe_resource_type_for_search_entity
from open_work_hub_api.domains.retrieval.partitioning import (
    flatten_read_scope,
    resolve_resource_read_scope,
)
from open_work_hub_api.domains.source_access import SourceAclPolicy


_MAX_KEYWORD_ACL_REFILL_PAGES = 5
_KEYWORD_PIT_KEEP_ALIVE = "1m"


@dataclass(frozen=True)
class KeywordIndexRefreshSummary:
    total: int
    entity_counts: dict[str, int]


def query_workspace_keyword_search(
    db: Session,
    *,
    workspace: Workspace,
    user: User,
    request: KeywordSearchRequest,
    backend_timeout_seconds: float | None = None,
    client: KeywordSearchClient | None = None,
    evaluation_entity_types: tuple[str, ...] = (),
    text_operator: KeywordSearchTextOperator = "and",
    text_minimum_should_match: str | int | None = None,
    backend_candidate_size: int | None = None,
    partitioned_generation: bool = False,
) -> KeywordSearchResponse:
    scope = resolve_workspace_keyword_search_scope(
        resolve_workspace_enabled_app_ids(db, workspace.id),
        include_inactive_entity_types=evaluation_entity_types,
    )
    if not scope.has_sources:
        raise localized_http_exception(
            status_code=status.HTTP_403_FORBIDDEN,
            code="search.workspace_keyword_search_disabled",
        )
    requested_entity_types = tuple(request.entity_types)
    allowed_entity_types = scope.constrain_entity_types(requested_entity_types)
    effective_request = request.model_copy(
        update={
            "workspace_id": workspace.id,
            "entity_types": list(allowed_entity_types),
        }
    )
    if requested_entity_types and not allowed_entity_types:
        return project_keyword_search_response(
            [],
            [],
            request=effective_request,
            trace_id=current_trace_id(),
            doc_page_lookup=lambda _doc_id: [],
        )

    retrieval_partition_ids = _resolve_keyword_partition_ids(
        db,
        scope=scope,
        allowed_entity_types=allowed_entity_types,
        workspace=workspace,
        user=user,
        partitioned_generation=partitioned_generation,
    )
    if partitioned_generation and not retrieval_partition_ids:
        return project_keyword_search_response(
            [],
            [],
            request=effective_request,
            trace_id=current_trace_id(),
            doc_page_lookup=lambda _doc_id: [],
        )

    policy = SourceAclPolicy.for_workspace(db, workspace=workspace, user=user)
    resolved_client = client or _search_client()
    try:
        _ensure_workspace_keyword_index_ready(
            workspace_id=workspace.id,
            client=resolved_client,
        )
        accessible_rows = _load_authorized_ranked_candidates(
            workspace_id=workspace.id,
            # A partitioned generation uses its partition predicate as the
            # complete candidate envelope. Legacy backend ACL fields are only
            # stale hints after workspace/company transitions and may not
            # remove candidates before the source-owned final ACL.
            acl_filter=(
                None
                if retrieval_partition_ids is not None
                else policy.build_keyword_acl_filter()
            ),
            policy=policy,
            allowed_entity_types=frozenset(allowed_entity_types),
            request=effective_request,
            backend_timeout_seconds=backend_timeout_seconds,
            client=resolved_client,
            text_operator=text_operator,
            text_minimum_should_match=text_minimum_should_match,
            size=backend_candidate_size or DEFAULT_KEYWORD_SEARCH_CANDIDATE_SIZE,
            retrieval_partition_ids=retrieval_partition_ids,
        )
    except KeywordSearchBackendError as error:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="search.keyword_backend_unavailable",
            reason=str(error),
        ) from error
    if retrieval_partition_ids is not None:
        accessible_rows = hydrate_file_search_rows_from_source(
            db,
            rows=accessible_rows,
            execution_workspace=workspace,
        )
    # Recheck immediately before facets/counts/highlights and response
    # projection so a concurrent revoke cannot leak derived information.
    accessible_rows = _filter_accessible_search_rows(
        accessible_rows,
        policy,
        workspace_id=workspace.id,
        allowed_entity_types=frozenset(allowed_entity_types),
        authorized_partition_ids=retrieval_partition_ids,
    )
    page_rows = accessible_rows[
        effective_request.offset : effective_request.offset + effective_request.limit
    ]
    return project_keyword_search_response(
        accessible_rows,
        page_rows,
        request=effective_request,
        trace_id=current_trace_id(),
        doc_page_lookup=lambda doc_id: _load_doc_pages_for_link(db, doc_id=doc_id),
    )


def refresh_workspace_keyword_index(
    db: Session,
    *,
    workspace: Workspace,
    client: KeywordSearchClient | None = None,
) -> KeywordIndexRefreshSummary:
    rows = all_workspace_search_documents(db, workspace=workspace)
    (client or _search_client()).rebuild_workspace(
        workspace_id=workspace.id,
        documents=rows,
    )
    return KeywordIndexRefreshSummary(
        total=len(rows),
        entity_counts=dict(
            sorted(Counter(str(row.get("entity_type") or "") for row in rows).items())
        ),
    )


def _ensure_workspace_keyword_index_ready(
    *,
    workspace_id: str,
    client: KeywordSearchClient | None = None,
) -> None:
    del workspace_id
    resolved_client = client or _search_client()
    if not resolved_client.index_exists():
        raise KeywordSearchBackendError(
            "Keyword search index is not initialized. Run keyword search backfill first."
        )


def _load_ranked_candidates(
    *,
    workspace_id: str,
    acl_filter: KeywordAclFilter | None,
    request: KeywordSearchRequest,
    backend_timeout_seconds: float | None = None,
    client: KeywordSearchClient | None = None,
    text_operator: KeywordSearchTextOperator = "and",
    text_minimum_should_match: str | int | None = None,
    size: int = DEFAULT_KEYWORD_SEARCH_CANDIDATE_SIZE,
    retrieval_partition_ids: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    rows, _, _ = _load_ranked_candidate_page(
        workspace_id=workspace_id,
        acl_filter=acl_filter,
        request=request,
        backend_timeout_seconds=backend_timeout_seconds,
        client=client,
        text_operator=text_operator,
        text_minimum_should_match=text_minimum_should_match,
        size=size,
        retrieval_partition_ids=retrieval_partition_ids,
    )
    return rows


def _load_authorized_ranked_candidates(
    *,
    workspace_id: str,
    acl_filter: KeywordAclFilter | None,
    policy: SourceAclPolicy,
    allowed_entity_types: frozenset[str],
    request: KeywordSearchRequest,
    backend_timeout_seconds: float | None,
    client: KeywordSearchClient,
    text_operator: KeywordSearchTextOperator,
    text_minimum_should_match: str | int | None,
    size: int,
    retrieval_partition_ids: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    open_pit = getattr(client, "open_point_in_time", None)
    close_pit = getattr(client, "close_point_in_time", None)
    point_in_time_id = (
        open_pit(keep_alive=_KEYWORD_PIT_KEEP_ALIVE)
        if callable(open_pit) and callable(close_pit)
        else None
    )
    search_after: tuple[Any, ...] = ()
    accessible_rows: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    required_count = request.offset + request.limit
    try:
        for _page in range(_MAX_KEYWORD_ACL_REFILL_PAGES):
            rows, next_search_after, exhausted = _load_ranked_candidate_page(
                workspace_id=workspace_id,
                acl_filter=acl_filter,
                request=request,
                backend_timeout_seconds=backend_timeout_seconds,
                client=client,
                text_operator=text_operator,
                text_minimum_should_match=text_minimum_should_match,
                size=size,
                search_after=search_after,
                point_in_time_id=point_in_time_id,
                retrieval_partition_ids=retrieval_partition_ids,
            )
            new_rows = []
            for row in rows:
                identity = (
                    str(row.get("entity_type") or ""),
                    str(row.get("entity_id") or ""),
                )
                if identity in seen:
                    continue
                seen.add(identity)
                new_rows.append(row)
            accessible_rows.extend(
                _filter_accessible_search_rows(
                    new_rows,
                    policy,
                    workspace_id=workspace_id,
                    allowed_entity_types=allowed_entity_types,
                    authorized_partition_ids=retrieval_partition_ids,
                )
            )
            if len(accessible_rows) >= required_count or exhausted:
                break
            if point_in_time_id is None:
                break
            if not next_search_after:
                raise KeywordSearchBackendError(
                    "Keyword ACL refill requires a stable search_after cursor"
                )
            search_after = next_search_after
    finally:
        if point_in_time_id is not None and callable(close_pit):
            try:
                close_pit(point_in_time_id)
            except KeywordSearchBackendError:
                # PITs expire server-side; closing is best effort after the
                # response snapshot has already been consumed.
                pass
    return filter_and_sort_keyword_search_rows(accessible_rows, request)


def _load_ranked_candidate_page(
    *,
    workspace_id: str,
    acl_filter: KeywordAclFilter | None,
    request: KeywordSearchRequest,
    backend_timeout_seconds: float | None,
    client: KeywordSearchClient | None,
    text_operator: KeywordSearchTextOperator,
    text_minimum_should_match: str | int | None,
    size: int,
    search_after: tuple[Any, ...] = (),
    point_in_time_id: str | None = None,
    retrieval_partition_ids: tuple[str, ...] | None = None,
) -> tuple[list[dict[str, Any]], tuple[Any, ...], bool]:
    query = build_keyword_search_query(
        workspace_id=workspace_id,
        acl_filter=acl_filter,
        request=request,
        retrieval_partition_ids=retrieval_partition_ids,
        request_timeout_seconds=backend_timeout_seconds,
        text_operator=text_operator,
        text_minimum_should_match=text_minimum_should_match,
        size=size,
    )
    result = (client or _search_client()).search(
        replace(
            query,
            search_after=search_after,
            point_in_time_id=point_in_time_id,
            point_in_time_keep_alive=_KEYWORD_PIT_KEEP_ALIVE,
        )
    )
    next_search_after = result.hits[-1].sort_values if result.hits else ()
    rows: list[dict[str, Any]] = []
    for hit in result.hits:
        source = dict(hit.document)
        source["_search_score"] = hit.score
        if hit.sort_values:
            source["_search_sort"] = list(hit.sort_values)
        rows.append(source)
    return (
        filter_and_sort_keyword_search_rows(rows, request),
        next_search_after,
        len(result.hits) < size,
    )


def _filter_accessible_search_rows(
    candidate_rows: list[dict[str, Any]],
    policy: SourceAclPolicy,
    *,
    workspace_id: str,
    allowed_entity_types: frozenset[str],
    authorized_partition_ids: tuple[str, ...] | None = None,
) -> list[dict[str, Any]]:
    candidates: list[tuple[dict[str, Any], str, str]] = []
    for row in candidate_rows:
        if authorized_partition_ids is None:
            if str(row.get("workspace_id") or "") != workspace_id:
                continue
        elif str(row.get("retrieval_partition_id") or "") not in authorized_partition_ids:
            continue
        if str(row.get("entity_type") or "") not in allowed_entity_types:
            continue
        resource_type = maybe_resource_type_for_search_entity(row.get("entity_type"))
        if resource_type is None:
            continue
        resource_id = str(row.get("entity_id") or "")
        if resource_id:
            candidates.append((row, resource_type, resource_id))
    authorize_many = getattr(policy, "authorize_many_resources", None)
    if callable(authorize_many):
        allowed = authorize_many(
            (resource_type, resource_id) for _, resource_type, resource_id in candidates
        )
    else:
        allowed = {
            (resource_type, resource_id)
            for _, resource_type, resource_id in candidates
            if policy.can_read_resource(resource_type, resource_id)
        }
    return [
        row
        for row, resource_type, resource_id in candidates
        if (resource_type, resource_id) in allowed
    ]


def _resolve_keyword_partition_ids(
    db: Session,
    *,
    scope: WorkspaceKeywordSearchScope,
    allowed_entity_types: tuple[str, ...],
    workspace: Workspace,
    user: User,
    partitioned_generation: bool,
) -> tuple[str, ...] | None:
    if not partitioned_generation:
        return None
    allowed = frozenset(allowed_entity_types)
    resource_types = [
        descriptor.resource_type
        for descriptor in scope.descriptors
        if descriptor.entity_type in allowed
    ]
    read_scope = resolve_resource_read_scope(
        db,
        resource_types=resource_types,
        workspace_id=workspace.id,
        user_id=user.id,
    )
    return tuple(str(partition_id) for partition_id in flatten_read_scope(read_scope))


def _search_client() -> KeywordSearchClient:
    return build_keyword_search_client(get_settings())


def _load_doc_pages_for_link(db: Session, *, doc_id: str) -> list[dict[str, str]]:
    pages = db.scalars(
        select(NativeDocPage)
        .where(NativeDocPage.doc_id == doc_id, NativeDocPage.trashed_at.is_(None))
        .order_by(
            NativeDocPage.sort_order.asc(), NativeDocPage.created_at.asc(), NativeDocPage.id.asc()
        )
    ).all()
    return [
        {
            "id": page.id,
            "title": page.title,
            "text": extract_page_text(
                content_format=page.content_format,
                content_blocks=page.content_blocks,
                content_text=page.content_text,
                block_extractor=_extract_blocks_text,
            ),
        }
        for page in pages
    ]


def _extract_blocks_text(blocks: Any) -> str:
    parts: list[str] = []

    def visit(value: Any) -> None:
        if isinstance(value, dict):
            text = value.get("text")
            if isinstance(text, str):
                parts.append(text)
            for child in value.values():
                visit(child)
        elif isinstance(value, list):
            for child in value:
                visit(child)

    visit(blocks)
    return " ".join(part.strip() for part in parts if part and part.strip())
