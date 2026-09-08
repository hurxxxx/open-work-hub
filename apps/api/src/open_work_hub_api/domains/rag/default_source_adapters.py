from __future__ import annotations

from sqlalchemy import select

from open_work_hub_api.domains.docs.app_catalog import DOCS_APP
from open_work_hub_api.domains.docs.models import NativeDoc
from open_work_hub_api.domains.files.app_catalog import FILES_APP
from open_work_hub_api.domains.meeting.app_catalog import MEETING_APP
from open_work_hub_api.domains.planner.app_catalog import PLANNER_APP
from open_work_hub_api.domains.pms.app_catalog import PMS_APP
from open_work_hub_api.domains.rag.contracts import RagSyncLane, RagSyncOperation
from open_work_hub_api.domains.rag.source_adapter_registry import (
    RagResourceAdapter,
    RagSourceAdapter,
    RagVisibilityScopeAdapter,
    company_reindex_rag_resource_adapters,
    has_rag_resource_adapter,
    has_rag_source_adapter,
    has_rag_visibility_scope_adapter,
    listed_rag_source_adapters,
    rag_resource_adapters,
    rag_source_adapters,
    register_rag_resource_adapter,
    register_rag_source_adapter,
    register_rag_visibility_scope_adapter,
    resource_types_for_rag_source_kinds,
    searchable_rag_app_ids,
    reindex_rag_resource_adapters,
)
from open_work_hub_api.domains.rag.source_registry import (
    OFFICIAL_NATIVE_DOC_SOURCE_KIND_LABELS,
)
from open_work_hub_api.domains.retrieval.partition_adapter_ids import (
    DOCS_RETRIEVAL_PARTITION_ADAPTER_ID,
    FILES_RETRIEVAL_PARTITION_ADAPTER_ID,
    MEETING_RETRIEVAL_PARTITION_ADAPTER_ID,
    PLANNER_RETRIEVAL_PARTITION_ADAPTER_ID,
    PMS_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_work_hub_api.domains.source_access.resource_types import (
    MEETING_RESOURCE_TYPE,
    NATIVE_DOC_RESOURCE_TYPE,
    PLANNER_EVENT_RESOURCE_TYPE,
    PMS_TASK_RESOURCE_TYPE,
)


def ensure_rag_source_adapters_registered() -> None:
    from open_work_hub_api.domains.docs.rag_sync import (
        MEETING_VISIBILITY_SCOPE,
        collect_meeting_visibility_doc_ids,
    )
    from open_work_hub_api.domains.files.rag_projection import (
        FILES_RAG_SOURCE_KIND,
        load_file_rag_projection,
        file_resource_ids,
    )
    from open_work_hub_api.domains.files.rag_sync import (
        mark_file_projection_deleted,
        mark_file_projection_failed,
        mark_file_projection_prepared,
    )
    from open_work_hub_api.domains.files.retrieval_contract import FILES_RETRIEVAL_ACTIVE
    from open_work_hub_api.domains.pms.rag_sync import (
        PMS_LABEL_RECOMPUTE_SCOPE,
        PMS_MEETING_VISIBILITY_SCOPE,
        PMS_MILESTONE_RECOMPUTE_SCOPE,
        PMS_TASK_LIST_RECOMPUTE_SCOPE,
        collect_label_task_ids,
        collect_meeting_task_ids,
        collect_milestone_task_ids,
        collect_task_list_task_ids,
    )
    from open_work_hub_api.domains.rag.docs_projection import load_native_doc_projection
    from open_work_hub_api.domains.rag.meeting_projection import load_meeting_projection
    from open_work_hub_api.domains.rag.planner_projection import load_planner_event_projection
    from open_work_hub_api.domains.rag.pms_projection import load_task_projection
    from open_work_hub_api.domains.source_access.resource_types import (
        FILE_MANAGER_FILE_RESOURCE_TYPE,
    )

    _register_default_resource_adapter(
        RagResourceAdapter(
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            app_id=FILES_APP.app_id,
            partition_adapter_id=FILES_RETRIEVAL_PARTITION_ADAPTER_ID,
            load_projection=lambda db, resource_id, rag_service: load_file_rag_projection(
                db,
                file_id=resource_id,
                rag_service=rag_service,
            ),
            company_resource_ids=file_resource_ids,
            include_in_default_query=FILES_RETRIEVAL_ACTIVE,
            include_in_reindex=FILES_RETRIEVAL_ACTIVE,
            on_projection_deleted=lambda db, resource_id: mark_file_projection_deleted(
                db,
                file_id=resource_id,
            ),
            on_projection_prepared_event=lambda db, resource_id, projection_event: (
                mark_file_projection_prepared(
                    db,
                    file_id=resource_id,
                    projection_event=projection_event,
                )
            ),
            on_projection_failed=lambda db, resource_id, error, phase: mark_file_projection_failed(
                db,
                file_id=resource_id,
                error=error,
                phase=phase,
            ),
        )
    )
    _register_default_resource_adapter(
        RagResourceAdapter(
            resource_type=NATIVE_DOC_RESOURCE_TYPE,
            app_id=DOCS_APP.app_id,
            partition_adapter_id=DOCS_RETRIEVAL_PARTITION_ADAPTER_ID,
            load_projection=lambda db, resource_id, rag_service: load_native_doc_projection(
                db,
                doc_id=resource_id,
            ),
            company_resource_ids=_company_official_native_doc_ids,
            include_in_default_query=True,
            include_in_reindex=True,
        )
    )
    _register_default_resource_adapter(
        RagResourceAdapter(
            resource_type=MEETING_RESOURCE_TYPE,
            app_id=MEETING_APP.app_id,
            partition_adapter_id=MEETING_RETRIEVAL_PARTITION_ADAPTER_ID,
            load_projection=lambda db, resource_id, rag_service: load_meeting_projection(
                db,
                meeting_id=resource_id,
            ),
        )
    )
    _register_default_resource_adapter(
        RagResourceAdapter(
            resource_type=PMS_TASK_RESOURCE_TYPE,
            app_id=PMS_APP.app_id,
            partition_adapter_id=PMS_RETRIEVAL_PARTITION_ADAPTER_ID,
            load_projection=lambda db, resource_id, rag_service: load_task_projection(
                db,
                task_id=resource_id,
            ),
        )
    )
    _register_default_resource_adapter(
        RagResourceAdapter(
            resource_type=PLANNER_EVENT_RESOURCE_TYPE,
            app_id=PLANNER_APP.app_id,
            partition_adapter_id=PLANNER_RETRIEVAL_PARTITION_ADAPTER_ID,
            load_projection=lambda db, resource_id, rag_service: load_planner_event_projection(
                db,
                event_id=resource_id,
            ),
        )
    )
    for source_kind in OFFICIAL_NATIVE_DOC_SOURCE_KIND_LABELS:
        _register_default_source_adapter(
            RagSourceAdapter(
                source_kind=source_kind,
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                app_id=DOCS_APP.app_id,
                label=_native_doc_source_label(source_kind),
                include_in_source_listing=True,
                visible=_source_kind_in_visible_rag_native_docs,
            )
        )
    for adapter in (
        RagSourceAdapter(
            source_kind=FILES_RAG_SOURCE_KIND,
            resource_type=FILE_MANAGER_FILE_RESOURCE_TYPE,
            app_id=FILES_APP.app_id,
            label="Files / Uploaded files",
            include_in_source_listing=FILES_RETRIEVAL_ACTIVE,
        ),
        RagSourceAdapter(
            source_kind="meeting",
            resource_type=MEETING_RESOURCE_TYPE,
            app_id=MEETING_APP.app_id,
            label="Meeting / Meetings",
        ),
        RagSourceAdapter(
            source_kind="pms_task",
            resource_type=PMS_TASK_RESOURCE_TYPE,
            app_id=PMS_APP.app_id,
            label="PMS / Tasks",
        ),
        RagSourceAdapter(
            source_kind="planner_event",
            resource_type=PLANNER_EVENT_RESOURCE_TYPE,
            app_id=PLANNER_APP.app_id,
            label="Planner / Events",
        ),
    ):
        _register_default_source_adapter(adapter)

    for adapter in (
        RagVisibilityScopeAdapter(
            scope_type=MEETING_VISIBILITY_SCOPE,
            resource_type=NATIVE_DOC_RESOURCE_TYPE,
            resource_ids=lambda db, job: collect_meeting_visibility_doc_ids(
                db,
                meeting_id=job.scope_id,
                cursor=job.cursor,
            ),
        ),
        RagVisibilityScopeAdapter(
            scope_type=PMS_MEETING_VISIBILITY_SCOPE,
            resource_type=PMS_TASK_RESOURCE_TYPE,
            resource_ids=lambda db, job: collect_meeting_task_ids(
                db,
                meeting_id=job.scope_id,
                cursor=job.cursor,
            ),
        ),
        RagVisibilityScopeAdapter(
            scope_type=PMS_TASK_LIST_RECOMPUTE_SCOPE,
            resource_type=PMS_TASK_RESOURCE_TYPE,
            operation=RagSyncOperation.UPSERT.value,
            resource_ids=lambda db, job: collect_task_list_task_ids(
                db,
                list_id=job.scope_id,
            ),
        ),
        RagVisibilityScopeAdapter(
            scope_type=PMS_LABEL_RECOMPUTE_SCOPE,
            resource_type=PMS_TASK_RESOURCE_TYPE,
            operation=RagSyncOperation.UPSERT.value,
            resource_ids=lambda db, job: collect_label_task_ids(
                db,
                label_id=job.scope_id,
                cursor=job.cursor,
            ),
        ),
        RagVisibilityScopeAdapter(
            scope_type=PMS_MILESTONE_RECOMPUTE_SCOPE,
            resource_type=PMS_TASK_RESOURCE_TYPE,
            operation=RagSyncOperation.UPSERT.value,
            resource_ids=lambda db, job: collect_milestone_task_ids(
                db,
                milestone_id=job.scope_id,
            ),
        ),
    ):
        _register_default_visibility_scope_adapter(adapter)


def resolve_rag_resource_types_for_source_kinds(source_kinds: list[str]) -> tuple[str, ...]:
    ensure_rag_source_adapters_registered()
    return resource_types_for_rag_source_kinds(source_kinds)


def list_registered_rag_sources(
    policy, enabled_app_ids: set[str]
) -> list[dict[str, str]]:
    ensure_rag_source_adapters_registered()
    sources: list[dict[str, str]] = []
    visible_native_doc_source_kinds = _visible_rag_native_doc_source_kinds(policy)
    emitted_source_kinds: set[str] = set()
    dynamic_native_sources_inserted = False
    for adapter in listed_rag_source_adapters():
        if (
            not dynamic_native_sources_inserted
            and adapter.resource_type != NATIVE_DOC_RESOURCE_TYPE
        ):
            _append_dynamic_native_doc_sources(
                sources,
                enabled_app_ids=enabled_app_ids,
                visible_source_kinds=visible_native_doc_source_kinds,
                emitted_source_kinds=emitted_source_kinds,
            )
            dynamic_native_sources_inserted = True

        if adapter.app_id not in enabled_app_ids:
            continue
        visible = _source_adapter_visible(
            policy,
            adapter,
            visible_native_doc_source_kinds=visible_native_doc_source_kinds,
        )
        if not visible:
            continue
        sources.append(_source_adapter_item(adapter))
        emitted_source_kinds.add(adapter.source_kind)
    if not dynamic_native_sources_inserted:
        _append_dynamic_native_doc_sources(
            sources,
            enabled_app_ids=enabled_app_ids,
            visible_source_kinds=visible_native_doc_source_kinds,
            emitted_source_kinds=emitted_source_kinds,
        )
    return sources


def registered_searchable_rag_app_ids() -> frozenset[str]:
    ensure_rag_source_adapters_registered()
    return searchable_rag_app_ids()


def registered_rag_app_ids() -> frozenset[str]:
    ensure_rag_source_adapters_registered()
    return frozenset(
        app_id
        for adapter in (*rag_resource_adapters(), *rag_source_adapters())
        if (app_id := adapter.app_id)
    )


def reindex_resource_adapters(
    enabled_app_ids: set[str],
) -> tuple[RagResourceAdapter, ...]:
    ensure_rag_source_adapters_registered()
    return reindex_rag_resource_adapters(enabled_app_ids)


def company_reindex_resource_adapters(
    enabled_app_ids: set[str] | None = None,
) -> tuple[RagResourceAdapter, ...]:
    ensure_rag_source_adapters_registered()
    return company_reindex_rag_resource_adapters(enabled_app_ids)


def _register_default_resource_adapter(adapter: RagResourceAdapter) -> None:
    if has_rag_resource_adapter(adapter.resource_type):
        return
    register_rag_resource_adapter(adapter)


def _register_default_source_adapter(adapter: RagSourceAdapter) -> None:
    if has_rag_source_adapter(adapter.source_kind):
        return
    register_rag_source_adapter(adapter)


def _register_default_visibility_scope_adapter(adapter: RagVisibilityScopeAdapter) -> None:
    if has_rag_visibility_scope_adapter(adapter.scope_type):
        return
    register_rag_visibility_scope_adapter(
        RagVisibilityScopeAdapter(
            scope_type=adapter.scope_type,
            resource_type=adapter.resource_type,
            resource_ids=adapter.resource_ids,
            operation=adapter.operation,
            lane=adapter.lane or RagSyncLane.BACKFILL.value,
            scope_label=adapter.scope_label,
        )
    )


def _source_kind_in_visible_rag_native_docs(policy, adapter: RagSourceAdapter) -> bool:
    return adapter.source_kind in set(policy.visible_rag_native_doc_source_kinds())


def _native_doc_source_label(source_kind: str) -> str:
    from open_work_hub_api.domains.rag.source_registry import OFFICIAL_NATIVE_DOC_SOURCE_KIND_LABELS

    return OFFICIAL_NATIVE_DOC_SOURCE_KIND_LABELS.get(
        source_kind,
        f"Docs / {source_kind.replace('_', ' ').title()}",
    )


def _visible_rag_native_doc_source_kinds(policy) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(
            str(source_kind).strip()
            for source_kind in policy.visible_rag_native_doc_source_kinds()
            if str(source_kind).strip()
        )
    )


def _source_adapter_visible(
    policy,
    adapter: RagSourceAdapter,
    *,
    visible_native_doc_source_kinds: tuple[str, ...],
) -> bool:
    if adapter.resource_type == NATIVE_DOC_RESOURCE_TYPE:
        return adapter.source_kind in set(visible_native_doc_source_kinds)
    if adapter.visible is not None:
        return adapter.visible(policy, adapter)
    return policy.has_accessible_source(adapter.resource_type)


def _source_adapter_item(adapter: RagSourceAdapter) -> dict[str, str]:
    return {
        "source_kind": adapter.source_kind,
        "resource_type": adapter.resource_type,
        "label": adapter.label or adapter.source_kind.replace("_", " ").title(),
        "app_id": adapter.app_id or "",
    }


def _append_dynamic_native_doc_sources(
    sources: list[dict[str, str]],
    *,
    enabled_app_ids: set[str],
    visible_source_kinds: tuple[str, ...],
    emitted_source_kinds: set[str],
) -> None:
    if DOCS_APP.app_id not in enabled_app_ids:
        return
    for source_kind in visible_source_kinds:
        if source_kind in emitted_source_kinds:
            continue
        sources.append(
            {
                "source_kind": source_kind,
                "resource_type": NATIVE_DOC_RESOURCE_TYPE,
                "label": _native_doc_source_label(source_kind),
                "app_id": DOCS_APP.app_id,
            }
        )
        emitted_source_kinds.add(source_kind)


def _company_official_native_doc_ids(
    db,
) -> list[str]:
    return list(
        db.scalars(
            select(NativeDoc.id).where(
                NativeDoc.trashed_at.is_(None),
                NativeDoc.rag_scope == "official",
            )
        )
    )


__all__ = [
    "ensure_rag_source_adapters_registered",
    "company_reindex_resource_adapters",
    "list_registered_rag_sources",
    "registered_rag_app_ids",
    "registered_searchable_rag_app_ids",
    "resolve_rag_resource_types_for_source_kinds",
    "reindex_resource_adapters",
]
