from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.registry import AiCapabilityRegistry
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.planner import service as planner_service


class _ToolArgsModel(BaseModel):
    model_config = ConfigDict(extra="forbid", populate_by_name=True)


class ListEventsArgs(_ToolArgsModel):
    from_at: str | None = Field(default=None, alias="from")
    to_at: str | None = Field(default=None, alias="to")


def _parse_optional_range_arg(arguments: Mapping[str, Any], key: str):
    value = arguments.get(key)
    if value is None:
        return None
    try:
        return planner_service.parse_iso_or_date(str(value))
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Invalid ISO date/datetime for '{key}': {exc}",
        ) from exc


def _list_events(
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    result = planner_service.list_events(
        db,
        workspace=workspace,
        principal=principal,
        user=user,
        from_at=_parse_optional_range_arg(arguments, "from"),
        to_at=_parse_optional_range_arg(arguments, "to"),
    )
    return result.model_dump(mode="json", by_alias=True)


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_tool(
        name="planner.list_events",
        description="List the caller's planner events in the current workspace.",
        owner_domain="planner",
        handler=_list_events,
        args_model=ListEventsArgs,
    )
