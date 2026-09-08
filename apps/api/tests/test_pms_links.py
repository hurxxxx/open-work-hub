from __future__ import annotations

from types import SimpleNamespace

from open_work_hub_api.domains.pms.links import (
    pms_root_path,
    pms_space_docs_path,
    pms_space_path,
    pms_space_whiteboards_path,
    pms_task_list_path,
    pms_task_path,
)


def test_pms_links_use_canonical_app_routes() -> None:
    task = SimpleNamespace(id="task-1", list_id="list-1")

    assert pms_root_path() == "/apps/pms"
    assert pms_task_path(task) == "/apps/pms/lists/list-1?task=task-1"
    assert (
        pms_task_list_path("list-1", query={"tab": "whiteboard"})
        == "/apps/pms/lists/list-1?tab=whiteboard"
    )
    assert pms_space_path("space-1") == "/apps/pms/spaces/space-1"
    assert pms_space_docs_path("space-1") == "/apps/pms/spaces/space-1/docs"
    assert pms_space_docs_path("space-1", doc_id="doc-1") == "/apps/pms/spaces/space-1/docs/doc-1"
    assert pms_space_whiteboards_path("space-1") == "/apps/pms/spaces/space-1/whiteboards"
    assert (
        pms_space_whiteboards_path("space-1", whiteboard_id="board-1")
        == "/apps/pms/spaces/space-1/whiteboards/board-1"
    )


def test_pms_links_encode_resource_segments() -> None:
    task = SimpleNamespace(id="task 1", list_id="list/1")

    assert pms_task_path(task) == ("/apps/pms/lists/list%2F1?task=task+1")
