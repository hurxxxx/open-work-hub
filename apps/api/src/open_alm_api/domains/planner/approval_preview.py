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


def build_create_event_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    return ApprovalPreview(
        title="Create personal planner event",
        summary=str(values.get("description") or "Create a planner event from AI.").strip()
        or "Create a planner event from AI.",
        fields=(
            PreviewField(label="Title", value=str(values.get("title", "-"))),
            PreviewField(label="Start", value=str(values.get("start_at", "-"))),
            PreviewField(label="Scope", value=str(values.get("scope", "personal"))),
        ),
    )


def build_update_event_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    fields: list[PreviewField] = [
        PreviewField(label="Event ID", value=str(values.get("event_id", "-"))),
    ]
    if values.get("title") is not None:
        fields.append(PreviewField(label="Title", value=str(values["title"])))
    if values.get("start_at") is not None:
        fields.append(PreviewField(label="Start", value=str(values["start_at"])))
    return ApprovalPreview(
        title="Update personal planner event",
        summary=str(values.get("description") or "Update a planner event from AI.").strip()
        or "Update a planner event from AI.",
        fields=tuple(fields),
    )


def build_delete_event_preview(
    principal: CallerPrincipal,
    workspace: WorkspaceContext,
    parsed_args: BaseModel | Mapping[str, Any],
) -> ApprovalPreview:
    values = _preview_values(parsed_args)
    return ApprovalPreview(
        title="Delete personal planner event",
        summary="Delete a planner event from AI.",
        fields=(PreviewField(label="Event ID", value=str(values.get("event_id", "-"))),),
    )


__all__ = [
    "build_create_event_preview",
    "build_delete_event_preview",
    "build_update_event_preview",
]
