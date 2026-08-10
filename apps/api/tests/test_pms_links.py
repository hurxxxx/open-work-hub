from __future__ import annotations

from types import SimpleNamespace

from open_alm_api.domains.auth.workspace_apps import iter_workspace_app_catalog
from open_alm_api.domains.pms.links import (
    normalize_pms_deep_link,
    pms_root_path,
    pms_space_docs_path,
    pms_space_path,
    pms_space_whiteboards_path,
    pms_task_list_path,
    pms_task_path,
)


def test_pms_links_use_collaboration_workspace_routes() -> None:
    workspace = SimpleNamespace(key="delivery-hub")
    task = SimpleNamespace(id="task-1", list_id="list-1")

    assert pms_root_path(workspace) == "/w/delivery-hub/pms"
    assert (
        pms_task_path(workspace, task)
        == "/w/delivery-hub/pms/lists/list-1?task=task-1"
    )
    assert (
        pms_task_list_path(workspace, "list-1", query={"tab": "whiteboard"})
        == "/w/delivery-hub/pms/lists/list-1?tab=whiteboard"
    )
    assert pms_space_path(workspace, "space-1") == "/w/delivery-hub/pms/spaces/space-1"
    assert (
        pms_space_docs_path(workspace, "space-1", doc_id="doc-1")
        == "/w/delivery-hub/pms/spaces/space-1/docs/doc-1"
    )
    assert (
        pms_space_whiteboards_path(workspace, "space-1", whiteboard_id="board-1")
        == "/w/delivery-hub/pms/spaces/space-1/whiteboards/board-1"
    )


def test_pms_links_encode_workspace_and_resource_segments() -> None:
    workspace = SimpleNamespace(key="기술 연구소")
    task = SimpleNamespace(id="task 1", list_id="list/1")

    assert (
        pms_task_path(workspace, task)
        == "/w/%EA%B8%B0%EC%88%A0%20%EC%97%B0%EA%B5%AC%EC%86%8C/pms/lists/list%2F1?task=task+1"
    )


def test_normalize_pms_deep_link_rewrites_legacy_tool_urls() -> None:
    assert (
        normalize_pms_deep_link("/tool/pms-list-list-1?workspace=hq&task=task-1")
        == "/w/hq/pms/lists/list-1?task=task-1"
    )
    assert (
        normalize_pms_deep_link(
            "https://open-alm.example/tool/pms-list-list-1?workspace=hq&task=task-1"
        )
        == "/w/hq/pms/lists/list-1?task=task-1"
    )
    assert (
        normalize_pms_deep_link("/tool/pms-space-space-1-whiteboards-board-1?workspace=hq")
        == "/w/hq/pms/spaces/space-1/whiteboards/board-1"
    )
    assert (
        normalize_pms_deep_link("/w/hq/pms/tool/pms-space-space-1-docs-doc-1")
        == "/w/hq/pms/spaces/space-1/docs/doc-1"
    )
    assert normalize_pms_deep_link("/tool/pms-later") == "/tool/pms-later"


def test_normalize_pms_deep_link_rewrites_legacy_workspace_urls() -> None:
    assert (
        normalize_pms_deep_link("/w/hq/pms/lists/list-1?task=task-1")
        == "/w/hq/pms/lists/list-1?task=task-1"
    )


def test_normalize_pms_deep_link_rewrites_duplicate_workspace_app_route_bases() -> None:
    assert (
        normalize_pms_deep_link("/w/hq/legacy-issues/legacy-issues/cooling-module")
        == "/w/hq/legacy-issues/cooling-module"
    )
    assert normalize_pms_deep_link("/w/hq/docs/docs?view=mine") == "/w/hq/docs?view=mine"
    assert (
        normalize_pms_deep_link("https://open-alm.example/w/hq/planner/planner?view=timeline")
        == "/w/hq/planner?view=timeline"
    )
    assert normalize_pms_deep_link("/w/hq/pms/pms/lists/list-1?task=task-1") == (
        "/w/hq/pms/lists/list-1?task=task-1"
    )
    assert normalize_pms_deep_link("/w/hq/pms/pms/tool/pms-space-space-1-docs-doc-1") == (
        "/w/hq/pms/spaces/space-1/docs/doc-1"
    )


def test_normalize_pms_deep_link_covers_every_workspace_app_route_base() -> None:
    route_bases = {
        item.route_base.rstrip("/")
        for item in iter_workspace_app_catalog()
        if item.route_base.startswith("/")
    }

    for route_base in route_bases:
        duplicated = f"/w/hq{route_base}{route_base}/probe?x=1"
        expected = f"/w/hq{route_base}/probe?x=1"
        assert normalize_pms_deep_link(duplicated) == expected
