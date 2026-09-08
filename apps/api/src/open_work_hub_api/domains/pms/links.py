from __future__ import annotations

from collections.abc import Mapping

from open_work_hub_api.core.app_routes import InternalAppLocation, build_app_href
from open_work_hub_api.domains.pms.models import Task


def pms_root_path() -> str:
    return build_app_href(
        InternalAppLocation(
            route_id="pms.root",
        )
    )


def pms_task_list_path(
    task_list_id: str,
    *,
    query: Mapping[str, str] | None = None,
) -> str:
    return build_app_href(
        InternalAppLocation(
            route_id="pms.list",
            path_params={"taskListId": task_list_id},
            query_params=query or {},
        )
    )


def pms_task_path(task: Task) -> str:
    return pms_task_list_path(task.list_id, query={"task": task.id})


def pms_space_path(space_id: str) -> str:
    return build_app_href(
        InternalAppLocation(
            route_id="pms.space",
            path_params={"spaceId": space_id},
        )
    )


def pms_space_docs_path(
    space_id: str,
    *,
    doc_id: str | None = None,
) -> str:
    return build_app_href(
        InternalAppLocation(
            route_id="pms.space-doc" if doc_id else "pms.space-docs",
            path_params={
                "spaceId": space_id,
                **({"docId": doc_id} if doc_id else {}),
            },
        )
    )


def pms_space_whiteboards_path(
    space_id: str,
    *,
    whiteboard_id: str | None = None,
) -> str:
    return build_app_href(
        InternalAppLocation(
            route_id=("pms.space-whiteboard" if whiteboard_id else "pms.space-whiteboards"),
            path_params={
                "spaceId": space_id,
                **({"whiteboardId": whiteboard_id} if whiteboard_id else {}),
            },
        )
    )


__all__ = [
    "pms_root_path",
    "pms_space_docs_path",
    "pms_space_path",
    "pms_space_whiteboards_path",
    "pms_task_list_path",
    "pms_task_path",
]
