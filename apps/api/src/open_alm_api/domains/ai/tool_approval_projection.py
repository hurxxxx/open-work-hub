from __future__ import annotations

from collections.abc import Mapping
from typing import TYPE_CHECKING, Any

from pydantic import BaseModel

from open_alm_api.core.principal import CallerPrincipal
from open_alm_api.domains.ai.registry import (
    AiCapabilityDescriptor,
    ApprovalPreview,
    build_workspace_context,
    get_ai_capability_registry,
)
from open_alm_api.domains.ai.tool_result_projection import build_rejected_tool_response_payload

if TYPE_CHECKING:
    from open_alm_api.domains.auth.models import Workspace


def build_rejected_approval_payload(
    *,
    tool_name: str,
    owner_domain: str,
    approval_required: bool,
    reject_reason: str | None,
) -> dict[str, Any]:
    return build_rejected_tool_response_payload(
        tool_name=tool_name,
        owner_domain=owner_domain,
        approval_required=approval_required,
        reject_reason=reject_reason,
    )


def build_resource_preview(
    *,
    descriptor: AiCapabilityDescriptor | None,
    workspace: Workspace,
    principal: CallerPrincipal,
    parsed_args: BaseModel | Mapping[str, Any],
) -> str | None:
    if descriptor is None or descriptor.preview_builder_id is None:
        return None
    registry = get_ai_capability_registry()
    builder = registry.resolve_preview_builder(descriptor.preview_builder_id)
    if builder is None:
        return None
    preview = builder(principal, build_workspace_context(workspace), parsed_args)
    return render_approval_preview(preview)


def render_approval_preview(preview: ApprovalPreview | None) -> str | None:
    if preview is None:
        return None
    lines = [preview.title.strip(), preview.summary.strip()]
    for field in preview.fields:
        label = field.label.strip()
        value = field.value.strip()
        if label or value:
            lines.append(f"{label}: {value}".strip(": "))
    rendered = "\n".join(line for line in lines if line)
    return rendered or None


__all__ = [
    "build_rejected_approval_payload",
    "build_resource_preview",
    "render_approval_preview",
]
