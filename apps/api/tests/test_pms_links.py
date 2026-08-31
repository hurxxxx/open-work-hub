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


def test_pms_links_use_canonical_workspace_routes() -> None:
    workspace = SimpleNamespace(key="delivery-hub")
    task = SimpleNamespace(id="task-1", list_id="list-1")

    assert pms_root_path(workspace) == "/apps/pms/workspaces/delivery-hub"
    assert (
        pms_task_path(workspace, task)
        == "/apps/pms/workspaces/delivery-hub/lists/list-1?task=task-1"
    )
    assert (
        pms_task_list_path(workspace, "list-1", query={"tab": "whiteboard"})
        == "/apps/pms/workspaces/delivery-hub/lists/list-1?tab=whiteboard"
    )
    assert (
        pms_space_path(workspace, "space-1")
        == "/apps/pms/workspaces/delivery-hub/spaces/space-1"
    )
    assert (
        pms_space_docs_path(workspace, "space-1")
        == "/apps/pms/workspaces/delivery-hub/spaces/space-1/docs"
    )
    assert (
        pms_space_docs_path(workspace, "space-1", doc_id="doc-1")
        == "/apps/pms/workspaces/delivery-hub/spaces/space-1/docs/doc-1"
    )
    assert (
        pms_space_whiteboards_path(workspace, "space-1")
        == "/apps/pms/workspaces/delivery-hub/spaces/space-1/whiteboards"
    )
    assert (
        pms_space_whiteboards_path(workspace, "space-1", whiteboard_id="board-1")
        == "/apps/pms/workspaces/delivery-hub/spaces/space-1/whiteboards/board-1"
    )


def test_pms_links_encode_workspace_and_resource_segments() -> None:
    workspace = SimpleNamespace(key="기술 연구소")
    task = SimpleNamespace(id="task 1", list_id="list/1")

    assert pms_task_path(workspace, task) == (
        "/apps/pms/workspaces/"
        "%EA%B8%B0%EC%88%A0%20%EC%97%B0%EA%B5%AC%EC%86%8C/"
        "lists/list%2F1?task=task+1"
    )
