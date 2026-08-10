from __future__ import annotations

from collections.abc import Mapping
import re
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit, unquote

from open_work_hub_api.domains.auth.models import Workspace
from open_work_hub_api.domains.auth.workspace_apps import iter_workspace_app_catalog
from open_work_hub_api.domains.pms.models import Task

_LEGACY_WORKSPACE_PMS_TOOL_RE = re.compile(r"^/w/([^/]+)/pms/tool/([^/]+)$")
_LEGACY_WORKSPACE_PMS_RE = re.compile(r"^/w/([^/]+)/pms(?P<suffix>/.*)?$")
_WORKSPACE_ROUTE_RE = re.compile(r"^(?P<prefix>/w/[^/?#]+)(?P<suffix>/.*)?$")
_PMS_SPACE_TOOL_PREFIX = "pms-space-"
_PMS_TASK_LIST_TOOL_PREFIX = "pms-list-"
_WORKSPACE_APP_ROUTE_BASES = tuple(
    sorted(
        {
            item.route_base.rstrip("/")
            for item in iter_workspace_app_catalog()
            if item.route_base.startswith("/")
        },
        key=len,
        reverse=True,
    )
)


def _path_segment(value: str) -> str:
    return quote(value, safe="")


def _pms_root_path_for_key(workspace_key: str) -> str:
    return f"/w/{_path_segment(workspace_key)}/pms"


def _append_query(path: str, query: Mapping[str, str] | None = None) -> str:
    return f"{path}?{urlencode(query)}" if query else path


def _append_query_pairs(path: str, query: list[tuple[str, str]]) -> str:
    return f"{path}?{urlencode(query)}" if query else path


def pms_root_path(workspace: Workspace) -> str:
    return _pms_root_path_for_key(workspace.key)


def pms_task_list_path(
    workspace: Workspace,
    task_list_id: str,
    *,
    query: Mapping[str, str] | None = None,
) -> str:
    return _append_query(
        f"{pms_root_path(workspace)}/lists/{_path_segment(task_list_id)}",
        query,
    )


def pms_task_path(workspace: Workspace, task: Task) -> str:
    return pms_task_list_path(workspace, task.list_id, query={"task": task.id})


def pms_space_path(workspace: Workspace, space_id: str) -> str:
    return f"{pms_root_path(workspace)}/spaces/{_path_segment(space_id)}"


def pms_space_docs_path(
    workspace: Workspace,
    space_id: str,
    *,
    doc_id: str | None = None,
) -> str:
    path = f"{pms_space_path(workspace, space_id)}/docs"
    return f"{path}/{_path_segment(doc_id)}" if doc_id else path


def pms_space_whiteboards_path(
    workspace: Workspace,
    space_id: str,
    *,
    whiteboard_id: str | None = None,
) -> str:
    path = f"{pms_space_path(workspace, space_id)}/whiteboards"
    return f"{path}/{_path_segment(whiteboard_id)}" if whiteboard_id else path


def normalize_pms_deep_link(action_url: str | None) -> str | None:
    if not action_url:
        return action_url

    action_url = _normalize_duplicate_workspace_app_deep_link(action_url)

    parsed = urlsplit(action_url)
    workspace_key, query = _extract_workspace_query(parsed.query)
    if workspace_key:
        legacy_tool = _normalize_legacy_pms_tool_path(
            workspace_key=workspace_key,
            tool_path=parsed.path.removeprefix("/tool/"),
            query=query,
        )
        if legacy_tool is not None:
            return legacy_tool

    workspace_tool_match = _LEGACY_WORKSPACE_PMS_TOOL_RE.match(parsed.path)
    if workspace_tool_match:
        legacy_tool = _normalize_legacy_pms_tool_path(
            workspace_key=unquote(workspace_tool_match.group(1)),
            tool_path=unquote(workspace_tool_match.group(2)),
            query=query,
        )
        if legacy_tool is not None:
            return legacy_tool

    workspace_route_match = _LEGACY_WORKSPACE_PMS_RE.match(parsed.path)
    if workspace_route_match:
        suffix = workspace_route_match.group("suffix") or ""
        path = f"{_pms_root_path_for_key(unquote(workspace_route_match.group(1)))}{suffix}"
        return _append_query_pairs(path, query)

    return action_url


def _normalize_duplicate_workspace_app_deep_link(action_url: str) -> str:
    parsed = urlsplit(action_url)
    normalized_path = _normalize_duplicate_workspace_app_path(parsed.path)
    if normalized_path == parsed.path:
        return action_url
    return urlunsplit(("", "", normalized_path, parsed.query, parsed.fragment))


def _normalize_duplicate_workspace_app_path(path: str) -> str:
    match = _WORKSPACE_ROUTE_RE.match(path)
    if not match:
        return path

    prefix = match.group("prefix")
    suffix = match.group("suffix") or ""
    normalized_suffix = suffix
    changed = True
    while changed:
        changed = False
        for route_base in _WORKSPACE_APP_ROUTE_BASES:
            duplicate = f"{route_base}{route_base}"
            if normalized_suffix == duplicate:
                normalized_suffix = route_base
                changed = True
                break
            duplicate_prefix = f"{duplicate}/"
            if normalized_suffix.startswith(duplicate_prefix):
                normalized_suffix = f"{route_base}/{normalized_suffix.removeprefix(duplicate_prefix)}"
                changed = True
                break

    return f"{prefix}{normalized_suffix}"


def _extract_workspace_query(query_string: str) -> tuple[str | None, list[tuple[str, str]]]:
    workspace_key: str | None = None
    query: list[tuple[str, str]] = []
    for key, value in parse_qsl(query_string, keep_blank_values=True):
        if key == "workspace" and workspace_key is None:
            workspace_key = value
            continue
        query.append((key, value))
    return workspace_key, query


def _normalize_legacy_pms_tool_path(
    *,
    workspace_key: str,
    tool_path: str,
    query: list[tuple[str, str]],
) -> str | None:
    if tool_path.startswith(_PMS_TASK_LIST_TOOL_PREFIX):
        task_list_id = unquote(tool_path.removeprefix(_PMS_TASK_LIST_TOOL_PREFIX))
        return _append_query_pairs(
            f"{_pms_root_path_for_key(workspace_key)}/lists/{_path_segment(task_list_id)}",
            query,
        )

    if not tool_path.startswith(_PMS_SPACE_TOOL_PREFIX):
        return None

    suffix = unquote(tool_path.removeprefix(_PMS_SPACE_TOOL_PREFIX))
    space_id, space_suffix = _split_legacy_space_suffix(suffix)
    if not space_id:
        return None

    path = f"{_pms_root_path_for_key(workspace_key)}/spaces/{_path_segment(space_id)}"
    if space_suffix:
        path = f"{path}{space_suffix}"
    return _append_query_pairs(path, query)


def _split_legacy_space_suffix(value: str) -> tuple[str, str]:
    for marker, segment in (("-whiteboards-", "whiteboards"), ("-docs-", "docs")):
        if marker in value:
            space_id, resource_id = value.split(marker, 1)
            return space_id, f"/{segment}/{_path_segment(resource_id)}"
    for marker, segment in (("-whiteboards", "whiteboards"), ("-docs", "docs")):
        if value.endswith(marker):
            return value[: -len(marker)], f"/{segment}"
    return value, ""
