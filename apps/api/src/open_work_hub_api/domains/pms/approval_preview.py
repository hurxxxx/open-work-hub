from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from open_work_hub_api.domains.ai.registry import ApprovalPreview, PreviewField

if TYPE_CHECKING:
    from open_work_hub_api.core.principal import CallerPrincipal


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
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    fields: list[PreviewField] = [
        PreviewField(label="List", value=str(values.get("list_id", "-"))),
        PreviewField(label="Title", value=str(values.get("title", "-"))),
        PreviewField(label="Status", value=str(values.get("status", "-"))),
        PreviewField(label="Priority", value=str(values.get("priority", "medium"))),
    ]
    assignee_ids = _string_list_or_none(values.get("assignee_ids"))
    if assignee_ids is not None:
        fields.append(PreviewField(label="Assignees", value=_preview_field_list(assignee_ids)))
    labels = _string_list_or_none(values.get("labels"))
    if labels is not None:
        fields.append(PreviewField(label="Labels", value=_preview_field_list(labels)))
    if values.get("parent_id") is not None:
        fields.append(PreviewField(label="Parent", value=str(values["parent_id"])))
    if values.get("start_date") is not None:
        fields.append(PreviewField(label="Start", value=str(values["start_date"])))
    if values.get("due_date") is not None:
        fields.append(PreviewField(label="Due", value=str(values["due_date"])))
    return ApprovalPreview(
        title="Create PMS task",
        summary=_preview_summary(values.get("body"), fallback="Create a PMS task from AI."),
        fields=tuple(fields),
    )


def build_update_task_preview(
    principal: CallerPrincipal,
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
    if values.get("priority") is not None:
        fields.append(PreviewField(label="Priority", value=str(values["priority"])))
    if "body" in values and not str(values["body"]).strip():
        fields.append(PreviewField(label="Body", value="Clear"))
    assignee_ids = _string_list_or_none(values.get("assignee_ids"))
    if assignee_ids is not None:
        fields.append(PreviewField(label="Assignees", value=_preview_field_list(assignee_ids)))
    labels = _string_list_or_none(values.get("labels"))
    if labels is not None:
        fields.append(PreviewField(label="Labels", value=_preview_field_list(labels)))
    if values.get("parent_id") is not None:
        fields.append(PreviewField(label="Parent", value=str(values["parent_id"])))
    if values.get("start_date") is not None:
        fields.append(PreviewField(label="Start", value=str(values["start_date"])))
    if values.get("due_date") is not None:
        fields.append(PreviewField(label="Due", value=str(values["due_date"])))
    if values.get("archived") is not None:
        fields.append(
            PreviewField(
                label="Archive state",
                value="Archive" if values["archived"] else "Restore",
            )
        )
    cleared_fields = _string_list_or_none(values.get("clear_fields")) or []
    clear_labels = {
        "parent_id": "Parent",
        "start_date": "Start",
        "due_date": "Due",
    }
    fields.extend(
        PreviewField(label=clear_labels[field_name], value="Clear")
        for field_name in cleared_fields
        if field_name in clear_labels
    )
    return ApprovalPreview(
        title="Update PMS task",
        summary=_preview_summary(values.get("body"), fallback="Update a PMS task from AI."),
        fields=tuple(fields),
    )


def build_add_comment_preview(
    principal: CallerPrincipal,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    return ApprovalPreview(
        title="Add PMS comment",
        summary=_preview_summary(values.get("body"), fallback="Add a comment to a PMS task."),
        fields=(PreviewField(label="Task", value=str(values.get("task_id", "-"))),),
    )


def build_delete_task_preview(
    principal: CallerPrincipal,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    return ApprovalPreview(
        title="Permanently delete PMS task",
        summary="This permanently deletes the task and cannot be undone.",
        fields=(PreviewField(label="Task", value=str(values.get("task_id", "-"))),),
    )


__all__ = [
    "build_add_comment_preview",
    "build_create_task_preview",
    "build_delete_task_preview",
    "build_update_task_preview",
]
