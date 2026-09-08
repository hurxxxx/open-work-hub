from __future__ import annotations

from collections.abc import Iterable, Mapping
from typing import Any

from sqlalchemy.orm import Session

from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.ai.registry import (
    AiCapabilityRegistry,
    get_ai_capability_registry,
)
from open_work_hub_api.domains.ai.tool_contracts import agent_tool_spec_to_openai_function
from open_work_hub_api.domains.ai.tool_service import (
    ToolRequiresApproval,
    approval_required_http_exception,
    execute_tool,
)
from open_work_hub_api.domains.ai.tool_surface import (
    FilteredCapabilityTool,
    descriptor_matches_app,
    resolve_filtered_capability_tools,
)
from open_work_hub_api.domains.ai.tool_surface_projection import (
    build_tool_manifest,
    build_tool_openapi_export,
)
from open_work_hub_api.domains.auth.models import User


class InProcTransport:
    def call_tool(
        self,
        db: Session,
        *,
        principal: CallerPrincipal,
        user: User,
        tool_name: str,
        arguments: Mapping[str, Any],
        source: str,
        call_id: str | None = None,
        agent_run_id: str | None = None,
        conversation_id: str | None = None,
        externally_approved_call_id: str | None = None,
    ) -> dict[str, Any]:
        try:
            return execute_tool(
                db,
                principal=principal,
                user=user,
                tool_name=tool_name,
                arguments=arguments,
                source=source,
                call_id=call_id,
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
                externally_approved_call_id=externally_approved_call_id,
            )
        except ToolRequiresApproval as error:
            raise approval_required_http_exception(error) from error


class AiMcpClient:
    def __init__(
        self,
        *,
        registry: AiCapabilityRegistry | None = None,
        transport: InProcTransport | None = None,
    ) -> None:
        self._registry = registry or get_ai_capability_registry()
        self._transport = transport or InProcTransport()

    def list_tools(
        self,
        db: Session,
        *,
        principal: CallerPrincipal,
        app_id: str | None = None,
        app_ids: Iterable[str] | None = None,
        include_meta: bool = False,
        include_approval_required: bool = True,
    ) -> list[FilteredCapabilityTool]:
        return resolve_filtered_capability_tools(
            db,
            registry=self._registry,
            principal=principal,
            app_id=app_id,
            app_ids=app_ids,
            include_meta=include_meta,
            include_approval_required=include_approval_required,
        )

    def list_openai_function_specs(
        self,
        db: Session,
        *,
        principal: CallerPrincipal,
        include_approval_required: bool = False,
    ) -> list[dict[str, Any]]:
        return [
            agent_tool_spec_to_openai_function(item.tool_spec)
            for item in self.list_tools(
                db,
                principal=principal,
                include_meta=False,
                include_approval_required=include_approval_required,
            )
        ]

    def build_manifest(
        self,
        db: Session,
        *,
        principal: CallerPrincipal,
        app_id: str | None = None,
        include_meta: bool = True,
        include_approval_required: bool = False,
    ) -> dict[str, Any]:
        tools = self.list_tools(
            db,
            principal=principal,
            app_id=app_id,
            include_meta=include_meta,
            include_approval_required=include_approval_required,
        )
        return build_tool_manifest(tools, app_id=app_id)

    def build_openapi_export(
        self,
        db: Session,
        *,
        principal: CallerPrincipal,
        app_id: str | None = None,
        include_approval_required: bool = False,
    ) -> dict[str, Any]:
        tools = self.list_tools(
            db,
            principal=principal,
            app_id=app_id,
            include_meta=False,
            include_approval_required=include_approval_required,
        )
        return build_tool_openapi_export(tools, app_id=app_id)

    def call_tool(
        self,
        db: Session,
        *,
        principal: CallerPrincipal,
        user: User,
        tool_name: str,
        arguments: Mapping[str, Any],
        source: str,
        call_id: str | None = None,
        agent_run_id: str | None = None,
        conversation_id: str | None = None,
        externally_approved_call_id: str | None = None,
    ) -> dict[str, Any]:
        return self._transport.call_tool(
            db,
            principal=principal,
            user=user,
            tool_name=tool_name,
            arguments=arguments,
            source=source,
            call_id=call_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
            externally_approved_call_id=externally_approved_call_id,
        )


def _descriptor_matches_app(*args: Any, **kwargs: Any) -> bool:
    return descriptor_matches_app(*args, **kwargs)
