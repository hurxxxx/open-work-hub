from __future__ import annotations

from collections.abc import Mapping
from datetime import date
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator
from pydantic_core import PydanticCustomError
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.registry import (
    AiCapabilityRegistry,
    ApprovalPreview,
    PreviewField,
    WorkspaceContext,
)
from aidoo_api.domains.auth.models import User, Workspace


class _ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class SearchIssuesArgs(_ToolArgsModel):
    q: str = ""
    list_id: str | None = None
    assignee_id: str | None = None
    status_filter: list[str] | None = None
    archived: bool | None = None
    limit: int = Field(default=20, ge=1)


class GetIssueArgs(_ToolArgsModel):
    issue_id: str = Field(..., min_length=1)


class ListSpacesArgs(_ToolArgsModel):
    pass


class ListTaskListsArgs(_ToolArgsModel):
    page: int = Field(default=1, ge=1)
    page_size: int = Field(default=20, ge=1)
    sort_by: str = "updated_at"
    sort_dir: Literal["asc", "desc"] = "desc"
    q: str = ""
    archived: bool | None = None
    team_id: str | None = None


class PmsCreateIssueAiInput(_ToolArgsModel):
    list_id: str = Field(..., min_length=1)
    title: str = Field(..., min_length=1)
    body: str | None = None
    assignee_ids: list[str] | None = Field(default=None, max_length=20)
    labels: list[str] | None = Field(default=None, max_length=20)
    due_date: date | None = None


class PmsUpdateIssueAiInput(_ToolArgsModel):
    issue_id: str = Field(..., min_length=1)
    title: str | None = None
    body: str | None = None
    status: str | None = None
    assignee_ids: list[str] | None = Field(default=None, max_length=20)
    due_date: date | None = None

    @model_validator(mode="after")
    def _validate_has_mutation(self) -> "PmsUpdateIssueAiInput":
        if self.model_fields_set.intersection({"title", "body", "status", "assignee_ids", "due_date"}):
            return self
        raise PydanticCustomError(
            "pms.update_mutable_field_required",
            "PMS issue updates must provide at least one mutable field.",
            {},
        )


class PmsAddCommentAiInput(_ToolArgsModel):
    issue_id: str = Field(..., min_length=1)
    body: str = Field(..., min_length=1)


class PmsDeleteIssueAiInput(_ToolArgsModel):
    issue_id: str = Field(..., min_length=1)


def _pms_service():
    from aidoo_api.domains.pms import service as pms_service

    return pms_service


def _search_issues(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return _pms_service().search_issues(
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


def _get_issue(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    return _pms_service().get_issue_detail(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        issue_id=str(arguments["issue_id"]),
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


def _create_issue(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return _pms_service().create_issue(
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


def _update_issue(
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
    return _pms_service().update_issue(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        issue_id=str(arguments["issue_id"]),
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
    return _pms_service().add_issue_comment(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        issue_id=str(arguments["issue_id"]),
        body=str(arguments["body"]),
        approved_call_id=approved_call_id,
    )


def _delete_issue(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None = None,
) -> dict[str, Any]:
    return _pms_service().delete_issue(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        issue_id=str(arguments["issue_id"]),
        approved_call_id=approved_call_id,
    )


def _string_list_or_none(value: Any) -> list[str] | None:
    if value is None:
        return None
    return [str(item) for item in value]


def _preview_values(parsed_args: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(parsed_args, BaseModel):
        return parsed_args.model_dump(mode="python", by_alias=True, exclude_none=True)
    return dict(parsed_args)


def _preview_summary(value: Any, *, fallback: str, limit: int = 180) -> str:
    text = str(value or "").strip()
    if not text:
        return fallback
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def _preview_field_list(values: list[str] | None, *, empty_value: str = "-") -> str:
    if not values:
        return empty_value
    if len(values) <= 3:
        return ", ".join(values)
    return f"{', '.join(values[:3])} (+{len(values) - 3})"


def _build_create_issue_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    fields: list[PreviewField] = [
        PreviewField(label="List", value=str(values.get("list_id", "-"))),
        PreviewField(label="Title", value=str(values.get("title", "-"))),
    ]
    assignee_ids = _string_list_or_none(values.get("assignee_ids"))
    if assignee_ids is not None:
        fields.append(PreviewField(label="Assignees", value=_preview_field_list(assignee_ids)))
    labels = _string_list_or_none(values.get("labels"))
    if labels is not None:
        fields.append(PreviewField(label="Labels", value=_preview_field_list(labels)))
    if values.get("due_date") is not None:
        fields.append(PreviewField(label="Due", value=str(values["due_date"])))
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Create PMS issue",
        summary=_preview_summary(values.get("body"), fallback="Create a PMS issue from AI."),
        fields=tuple(fields),
    )


def _build_update_issue_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    fields: list[PreviewField] = [
        PreviewField(label="Issue", value=str(values.get("issue_id", "-"))),
    ]
    if values.get("title") is not None:
        fields.append(PreviewField(label="Title", value=str(values["title"])))
    if values.get("status") is not None:
        fields.append(PreviewField(label="Status", value=str(values["status"])))
    assignee_ids = _string_list_or_none(values.get("assignee_ids"))
    if assignee_ids is not None:
        fields.append(PreviewField(label="Assignees", value=_preview_field_list(assignee_ids)))
    if values.get("due_date") is not None:
        fields.append(PreviewField(label="Due", value=str(values["due_date"])))
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Update PMS issue",
        summary=_preview_summary(values.get("body"), fallback="Update a PMS issue from AI."),
        fields=tuple(fields),
    )


def _build_add_comment_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Add PMS comment",
        summary=_preview_summary(values.get("body"), fallback="Add a comment to a PMS issue."),
        fields=(
            PreviewField(label="Issue", value=str(values.get("issue_id", "-"))),
        ),
    )


def _build_delete_issue_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Delete PMS issue",
        summary="Delete one PMS issue from AI.",
        fields=(
            PreviewField(label="Issue", value=str(values.get("issue_id", "-"))),
        ),
    )


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_preview_builder(
        preview_builder_id="pms.issue_create_preview",
        builder=_build_create_issue_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="pms.issue_update_preview",
        builder=_build_update_issue_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="pms.issue_comment_preview",
        builder=_build_add_comment_preview,
    )
    registry.register_preview_builder(
        preview_builder_id="pms.issue_delete_preview",
        builder=_build_delete_issue_preview,
    )
    registry.register_tool(
        name="pms.search_issues",
        description="Search issues in the current workspace.",
        owner_domain="pms",
        handler=_search_issues,
        args_model=SearchIssuesArgs,
    )
    registry.register_tool(
        name="pms.get_issue",
        description="Load one issue in the current workspace.",
        owner_domain="pms",
        handler=_get_issue,
        args_model=GetIssueArgs,
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
        name="pms.create_issue",
        description="Create a PMS issue in the current workspace.",
        owner_domain="pms",
        handler=_create_issue,
        args_model=PmsCreateIssueAiInput,
        mode="write",
        approval_required=True,
        discoverability_predicate_id="pms.issue_write",
        preview_builder_id="pms.issue_create_preview",
        output_projection="resource_ids",
    )
    registry.register_tool(
        name="pms.update_issue",
        description="Update one PMS issue in the current workspace.",
        owner_domain="pms",
        handler=_update_issue,
        args_model=PmsUpdateIssueAiInput,
        mode="write",
        approval_required=True,
        discoverability_predicate_id="pms.issue_write",
        preview_builder_id="pms.issue_update_preview",
        output_projection="resource_ids",
    )
    registry.register_tool(
        name="pms.add_comment",
        description="Add a comment to one PMS issue in the current workspace.",
        owner_domain="pms",
        handler=_add_comment,
        args_model=PmsAddCommentAiInput,
        mode="write",
        approval_required=True,
        discoverability_predicate_id="pms.issue_write",
        preview_builder_id="pms.issue_comment_preview",
        output_projection="resource_ids",
    )
    registry.register_tool(
        name="pms.delete_issue",
        description="Delete one PMS issue in the current workspace.",
        owner_domain="pms",
        handler=_delete_issue,
        args_model=PmsDeleteIssueAiInput,
        mode="write",
        approval_required=True,
        discoverability_predicate_id="pms.issue_write",
        preview_builder_id="pms.issue_delete_preview",
        output_projection="resource_ids",
    )
