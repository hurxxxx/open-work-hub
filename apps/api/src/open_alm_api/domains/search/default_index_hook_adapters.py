from __future__ import annotations

from open_alm_api.core.workspace_app_registry import WorkspaceAppRegistration
from open_alm_api.domains.docs.app_catalog import DOCS_WORKSPACE_APP
from open_alm_api.domains.files.app_catalog import FILES_WORKSPACE_APP
from open_alm_api.domains.meeting.app_catalog import MEETING_WORKSPACE_APP
from open_alm_api.domains.pms.app_catalog import PMS_WORKSPACE_APP
from open_alm_api.domains.search.hook_registry import (
    SearchIndexHook,
    SearchIndexOperation,
    has_search_index_hook,
    register_search_index_hook,
)
from open_alm_api.domains.search.schemas import SearchEntityType


def ensure_search_index_hooks_registered() -> None:
    from open_alm_api.domains.docs import search_hooks as docs_hooks
    from open_alm_api.domains.files import search_hooks as files_hooks
    from open_alm_api.domains.meeting import search_hooks as meeting_hooks
    from open_alm_api.domains.pms import search_hooks as pms_hooks

    _register_default_search_index_hook(
        "docs.enqueue_doc_search_index",
        docs_hooks.enqueue_doc_search_index,
        owner_app=DOCS_WORKSPACE_APP,
        entity_type=SearchEntityType.DOC.value,
        operations=("create", "update", "delete"),
    )
    _register_default_search_index_hook(
        "docs.enqueue_doc_search_index_by_id",
        docs_hooks.enqueue_doc_search_index_by_id,
        owner_app=DOCS_WORKSPACE_APP,
        entity_type=SearchEntityType.DOC.value,
        operations=("update",),
    )
    _register_default_search_index_hook(
        "files.enqueue_file_search_index",
        files_hooks.enqueue_file_search_index,
        owner_app=FILES_WORKSPACE_APP,
        entity_type=SearchEntityType.FILE.value,
        operations=("create", "update", "delete"),
    )
    _register_default_search_index_hook(
        "files.enqueue_file_search_index_by_id",
        files_hooks.enqueue_file_search_index_by_id,
        owner_app=FILES_WORKSPACE_APP,
        entity_type=SearchEntityType.FILE.value,
        operations=("update",),
    )
    _register_default_search_index_hook(
        "meeting.enqueue_meeting_search_index",
        meeting_hooks.enqueue_meeting_search_index,
        owner_app=MEETING_WORKSPACE_APP,
        entity_type=SearchEntityType.MEETING.value,
        operations=("create", "update", "delete"),
    )
    _register_default_search_index_hook(
        "meeting.enqueue_meeting_search_index_by_id",
        meeting_hooks.enqueue_meeting_search_index_by_id,
        owner_app=MEETING_WORKSPACE_APP,
        entity_type=SearchEntityType.MEETING.value,
        operations=("update",),
    )
    _register_default_search_index_hook(
        "pms.enqueue_task_search_index",
        pms_hooks.enqueue_task_search_index,
        owner_app=PMS_WORKSPACE_APP,
        entity_type=SearchEntityType.PMS_TASK.value,
        operations=("create", "update", "delete"),
    )
    _register_default_search_index_hook(
        "pms.enqueue_task_search_index_by_id",
        pms_hooks.enqueue_task_search_index_by_id,
        owner_app=PMS_WORKSPACE_APP,
        entity_type=SearchEntityType.PMS_TASK.value,
        operations=("update",),
    )
    _register_default_search_index_hook(
        "pms.enqueue_task_list_task_search_recompute",
        pms_hooks.enqueue_task_list_task_search_recompute,
        owner_app=PMS_WORKSPACE_APP,
        entity_type=SearchEntityType.PMS_TASK.value,
        operations=("update",),
    )
    _register_default_search_index_hook(
        "pms.enqueue_label_task_search_recompute",
        pms_hooks.enqueue_label_task_search_recompute,
        owner_app=PMS_WORKSPACE_APP,
        entity_type=SearchEntityType.PMS_TASK.value,
        operations=("update",),
    )
    _register_default_search_index_hook(
        "pms.enqueue_task_list_status_task_search_recompute",
        pms_hooks.enqueue_task_list_status_task_search_recompute,
        owner_app=PMS_WORKSPACE_APP,
        entity_type=SearchEntityType.PMS_TASK.value,
        operations=("update",),
    )


def _register_default_search_index_hook(
    name: str,
    hook: SearchIndexHook,
    *,
    owner_app: WorkspaceAppRegistration,
    entity_type: str,
    operations: tuple[SearchIndexOperation, ...],
) -> None:
    if has_search_index_hook(name):
        return
    register_search_index_hook(
        name,
        hook,
        owner_app=owner_app,
        entity_type=entity_type,
        operations=operations,
    )


__all__ = ["ensure_search_index_hooks_registered"]
