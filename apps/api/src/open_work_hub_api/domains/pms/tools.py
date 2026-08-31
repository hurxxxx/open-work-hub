from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.orm import Session

from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import AiCapabilityRegistry
from open_work_hub_api.domains.auth.models import User, Workspace
from open_work_hub_api.domains.pms.app_catalog import PMS_WORKSPACE_APP
from open_work_hub_api.domains.pms.approval_preview import (
    build_add_comment_preview,
    build_create_task_preview,
    build_delete_task_preview,
    build_update_task_preview,
)


class _ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SearchTasksArgs(_ToolArgsModel):
    q: str = ""
    list_id: str | None = None
    assignee_id: str | None = None
    status_filter: list[str] | None = None
    archived: bool | None = None
    limit: int = Field(default=20, ge=1)


class GetTaskArgs(_ToolArgsModel):
    task_id: str = Field(..., min_length=1)


class ListSpacesArgs(_ToolArgsModel):
    pass


class ListTaskListsArgs(_ToolArgsModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    q: str = ""
    archived: bool | None = False
    team_id: str | None = None


class PmsCreateTaskAiInput(_ToolArgsModel):
    list_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    body: str | None = None
    assignee_ids: list[str] | None = Field(default=None, max_length=20)
    labels: list[str] | None = Field(default=None, max_length=20)
    due_date: date | None = None


class PmsUpdateTaskAiInput(_ToolArgsModel):
    task_id: str = Field(..., min_length=1)
    title: str | None = None
    body: str | None = None
    status: str | None = None
    assignee_ids: list[str] | None = Field(default=None, max_length=20)
    due_date: date | None = None

    @model_validator(mode="after")
    def _validate_has_mutation(self) -> "PmsUpdateTaskAiInput":
        if self.model_fields_set.intersection(
            {"title", "body", "status", "assignee_ids", "due_date"}
        ):
            return self
        raise PydanticCustomError(
            "pms.update_mutable_field_required",
            "PMS task updates must provide at least one mutable field.",
            {},
        )


class PmsAddCommentAiInput(_ToolArgsModel):
    task_id: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)


class PmsDeleteTaskAiInput(_ToolArgsModel):
    task_id: str = Field(..., min_length=1)


def _pms_service():
    from open_work_hub_api.domains.pms import service as pms_service

    return pms_service


def _search_tasks(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    result = _pms_service().search_tasks(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        q=str(arguments.get("q", "")),
        list_id=arguments.get("list_id"),
        assignee_id=arguments.get("assignee_id"),
        status_filter=arguments.get("status_filter"),
        archived=arguments.get("archived"),
        limit=int(arguments.get("limit", 20)),
    )
    items = result.get("items") if isinstance(result, dict) else None
    if isinstance(items, list):
        result["resource_ids"] = [
            str(item["id"]) for item in items if isinstance(item, dict) and item.get("id")
        ]
    return result


def _get_task(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return _pms_service().get_task_detail_for_ai(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        task_id=str(arguments["task_id"]),
    )


def _list_spaces(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return {
        "items": _pms_service().list_spaces(
            db,
            workspace=workspace,
            principal=principal,
            user=user,
        )
    }


def _list_task_lists(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    sort_dir = str(arguments.get("sort_dir", "desc"))
    return _pms_service().list_task_lists(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        page=int(arguments.get("page", 1)),
        page_size=int(arguments.get("page_size", 20)),
        sort_by=str(arguments.get("sort_by", "updated_at")),
        sort_dir=sort_dir,
        q=str(arguments.get("q", "")),
        archived=arguments.get("archived"),
        team_id=arguments.get("team_id"),
    )


def _create_task(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return _pms_service().create_task(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        list_id=str(arguments["list_id"]),
        title=str(arguments["title"]),
        description=str(arguments.get("body") or ""),
        assignee_ids=_string_list_or_none(arguments.get("assignee_ids")),
        due_date=arguments.get("due_date"),
        label_ids=_string_list_or_none(arguments.get("labels")),
        approved_call_id=approved_call_id,
    )


def _update_task(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    provided_fields: set[str] = set()
    for field_name, service_field_name in (
        ("title", "title"),
        ("body", "description"),
        ("status", "status"),
        ("assignee_ids", "assignee_ids"),
        ("due_date", "due_date"),
    ):
        if field_name in arguments:
            provided_fields.add(service_field_name)
    return _pms_service().update_task(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        task_id=str(arguments["task_id"]),
        provided_fields=provided_fields,
        title=arguments.get("title"),
        description=arguments.get("body"),
        status=arguments.get("status"),
        assignee_ids=_string_list_or_none(arguments.get("assignee_ids")),
        due_date=arguments.get("due_date"),
        approved_call_id=approved_call_id,
    )


def _add_comment(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return _pms_service().add_task_comment(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        task_id=str(arguments["task_id"]),
        body=str(arguments["body"]),
        approved_call_id=approved_call_id,
    )


def _delete_task(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return _pms_service().delete_task(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        task_id=str(arguments["task_id"]),
        approved_call_id=approved_call_id,
    )


def _string_list_or_none(value: Any) -> list[str] | None:
    if value is None:
        return None
    return [str(item) for item in value]


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    app_enabled_predicate_id = f"{PMS_WORKSPACE_APP.app_id}.enabled"
    registry.register_preview_builder(
        preview_builder_id="pms.task_create_preview",
        builder=build_create_task_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="pms.task_update_preview",
        builder=build_update_task_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="pms.task_comment_preview",
        builder=build_add_comment_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="pms.task_delete_preview",
        builder=build_delete_task_preview,
    )
    registry.register_tool(
        name="pms.search_tasks",
        description="Search tasks in the current workspace.",
        owner_domain="pms",
        handler=_search_tasks,
        args_model=SearchTasksArgs,
    )
    registry.register_tool(
        name="pms.get_task",
        description="Load one task in the current workspace.",
        owner_domain="pms",
        handler=_get_task,
        args_model=GetTaskArgs,
    )
    registry.register_tool(
        name="pms.list_spaces",
        description="List PMS spaces in the current workspace.",
        owner_domain="pms",
        handler=_list_spaces,
        args_model=ListSpacesArgs,
    )
    registry.register_tool(
        name="pms.list_task_lists",
        description="List PMS task lists in the current workspace.",
        owner_domain="pms",
        handler=_list_task_lists,
        args_model=ListTaskListsArgs,
    )

    if not get_settings().ai_write_tools_enabled:
        return

    registry.register_tool(
        name="pms.create_task",
        description="Create a PMS task in the current workspace.",
        owner_domain="pms",
        handler=_create_task,
        args_model=PmsCreateTaskAiInput,
        mode="write",
        approval_required=True,
        discoverability_predicate_id=app_enabled_predicate_id,
        preview_builder_id="pms.task_create_preview",
        output_projection="resource_ids",
    )
    registry.register_tool(
        name="pms.update_task",
        description="Update one PMS task in the current workspace.",
        owner_domain="pms",
        handler=_update_task,
        args_model=PmsUpdateTaskAiInput,
        mode="write",
        approval_required=True,
        discoverability_predicate_id=app_enabled_predicate_id,
        preview_builder_id="pms.task_update_preview",
        output_projection="resource_ids",
    )
    registry.register_tool(
        name="pms.add_comment",
        description="Add a comment to one PMS task in the current workspace.",
        owner_domain="pms",
        handler=_add_comment,
        args_model=PmsAddCommentAiInput,
        mode="write",
        approval_required=True,
        discoverability_predicate_id=app_enabled_predicate_id,
        preview_builder_id="pms.task_comment_preview",
        output_projection="resource_ids",
    )
    registry.register_tool(
        name="pms.delete_task",
        description="Delete one PMS task in the current workspace.",
        owner_domain="pms",
        handler=_delete_task,
        args_model=PmsDeleteTaskAiInput,
        mode="write",
        approval_required=True,
        discoverability_predicate_id=app_enabled_predicate_id,
        preview_builder_id="pms.task_delete_preview",
        output_projection="resource_ids",
    )
