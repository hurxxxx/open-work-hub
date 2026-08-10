from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from open_alm_api.domains.ai.registry import ApprovalPreview, PreviewField, WorkspaceContext

if TYPE_CHECKING:
    from open_alm_api.core.principal import CallerPrincipal


def _preview_values(parsed_args: BaseModel | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(parsed_args, BaseModel):
        return parsed_args.model_dump(mode="python", by_alias=True, exclude_none=True)
    return dict(parsed_args)


def _string_list_or_none(value: Any) -> list[str] | None:
    if value is None:
        return None
    return [str(item) for item in value]


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


def build_create_task_preview(
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
        title=f"[{workspace.display_name}] Create PMS task",
        summary=_preview_summary(values.get("body"), fallback="Create a PMS task from AI."),
        fields=tuple(fields),
    )


def build_update_task_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    fields: list[PreviewField] = [
        PreviewField(label="Task", value=str(values.get("task_id", "-"))),
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
        title=f"[{workspace.display_name}] Update PMS task",
        summary=_preview_summary(values.get("body"), fallback="Update a PMS task from AI."),
        fields=tuple(fields),
    )


def build_add_comment_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Add PMS comment",
        summary=_preview_summary(values.get("body"), fallback="Add a comment to a PMS task."),
        fields=(
            PreviewField(label="Task", value=str(values.get("task_id", "-"))),
        ),
    )


def build_delete_task_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    return ApprovalPreview(
        title=f"[{workspace.display_name}] Delete PMS task",
        summary="Delete one PMS task from AI.",
        fields=(
            PreviewField(label="Task", value=str(values.get("task_id", "-"))),
        ),
    )


__all__ = [
    "build_add_comment_preview",
    "build_create_task_preview",
    "build_delete_task_preview",
    "build_update_task_preview",
]
