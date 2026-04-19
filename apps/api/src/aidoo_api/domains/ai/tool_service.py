from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai.registry import get_ai_capability_registry
from aidoo_api.domains.auth.models import User, Workspace


def execute_tool(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    tool_name: str,
    arguments: Mapping[str, Any],
) -> dict[str, Any]:
    registry = get_ai_capability_registry()
    definition = registry.tools.get(tool_name)
    if definition is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown AI tool: {tool_name}",
        )
    if definition.handler is None:
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"AI tool is registered but not executable yet: {tool_name}",
        )
    if definition.approval_required:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"AI tool requires approval before execution: {tool_name}",
        )

    result = definition.handler(
        db,
        workspace,
        principal,
        user,
        arguments,
    )
    return {
        "tool": definition.name,
        "owner_domain": definition.owner_domain,
        "approval_required": definition.approval_required,
        "result": jsonable_encoder(result),
    }
