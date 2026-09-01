from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from time import perf_counter
from typing import Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from sqlalchemy.orm import Session

from open_work_hub_api.core.i18n import localized_http_exception
from open_work_hub_api.core.telemetry import get_tracer
from open_work_hub_api.core.principal import CallerPrincipal
from open_work_hub_api.domains.ai import approvals as ai_approvals
from open_work_hub_api.domains.ai.audit import log_llm_tool_call
from open_work_hub_api.domains.ai.tool_error_projection import tool_http_exception_message
from open_work_hub_api.domains.ai.tool_argument_validation import (
    ToolArgumentValidationFailure,
    validate_tool_arguments,
)
from open_work_hub_api.domains.ai.tool_approval_gate import (
    ToolRequiresApproval as ToolRequiresApproval,
    approval_required_http_exception as approval_required_http_exception,
    build_rejected_approval_payload,
    build_tool_requires_approval,
    validate_replayed_approval,
)
from open_work_hub_api.domains.ai.tool_context import ToolExecutionContext, bind_tool_execution_context
from open_work_hub_api.domains.ai.tool_result_projection import (
    dump_json as dump_json,
    preview_text as preview_text,
    render_tool_result_message as render_tool_result_message,
    sanitize_reject_reason_for_llm as sanitize_reject_reason_for_llm,
    serialize_rejected_tool_result_for_llm as serialize_rejected_tool_result_for_llm,
    serialize_tool_result_for_llm as serialize_tool_result_for_llm,
    tool_result_preview as tool_result_preview,
)
from open_work_hub_api.domains.ai.tool_surface import descriptor_owner_app_enabled
from open_work_hub_api.domains.ai.registry import (
    build_workspace_context,
    get_ai_capability_registry,
    resolve_workspace_entitlement_view,
)
from open_work_hub_api.domains.auth.models import User, Workspace


_AUDIT_TEXT_ARGUMENT_KEYS = frozenset(
    {
        "body",
        "content",
        "message",
        "messages",
        "prompt",
        "q",
        "query",
        "question",
        "summary",
        "text",
        "title",
    }
)


def execute_tool(
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    tool_name: str,
    arguments: Mapping[str, Any],
    source: str,
    call_id: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
    approved_call_id: str | None = None,
    externally_approved_call_id: str | None = None,
) -> dict[str, Any]:
    started = perf_counter()
    registry = get_ai_capability_registry()
    approval: ai_approvals.AiToolApproval | None = None
    definition = registry.tools.get(tool_name)
    descriptor = registry.get_descriptor(tool_name)
    args_summary = preview_text(
        json.dumps(_audit_argument_summary(arguments), ensure_ascii=False, default=str),
        limit=500,
    )
    if definition is None:
        _log_tool_call(
            source=source,
            principal=principal,
            workspace=workspace,
            tool_name=tool_name,
            args_summary=args_summary,
            status="error",
            latency_ms=_elapsed_ms(started),
            call_id=call_id,
            error=f"Unknown AI tool: {tool_name}",
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        )
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ai.unknown_tool",
            tool_name=tool_name,
        )
    handler = definition.handler
    if descriptor is not None:
        resolved_handler = registry.resolve_service_handler(descriptor.service_handler_id)
        if resolved_handler is not None:
            handler = resolved_handler
        predicate = registry.resolve_discoverability_predicate(
            descriptor.discoverability_predicate_id
        )
        if predicate is None:
            _log_tool_call(
                source=source,
                principal=principal,
                workspace=workspace,
                tool_name=tool_name,
                args_summary=args_summary,
                status="error",
                latency_ms=_elapsed_ms(started),
                call_id=call_id,
                error=(
                    "AI tool discoverability predicate is not registered: "
                    f"{descriptor.discoverability_predicate_id}"
                ),
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
            )
            raise localized_http_exception(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                code="ai.tool_discoverability_predicate_missing",
                tool_name=tool_name,
            )
        workspace_context = build_workspace_context(workspace)
        entitlements = resolve_workspace_entitlement_view(db, workspace=workspace)
        if not descriptor_owner_app_enabled(
            descriptor,
            enabled_app_ids=entitlements.effective_enabled_app_ids,
        ) or not predicate(principal, workspace_context, entitlements):
            _log_tool_call(
                source=source,
                principal=principal,
                workspace=workspace,
                tool_name=tool_name,
                args_summary=args_summary,
                status="blocked",
                latency_ms=_elapsed_ms(started),
                call_id=call_id,
                error=f"AI tool is not available in this workspace: {tool_name}",
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
            )
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="ai.tool_unavailable_in_workspace",
                tool_name=tool_name,
            )

    if handler is None:
        _log_tool_call(
            source=source,
            principal=principal,
            workspace=workspace,
            tool_name=tool_name,
            args_summary=args_summary,
            status="error",
            latency_ms=_elapsed_ms(started),
            call_id=call_id,
            error=f"AI tool is registered but not executable yet: {tool_name}",
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        )
        raise localized_http_exception(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            code="ai.tool_not_executable",
            tool_name=tool_name,
        )
    args_model = descriptor.ai_input_model if descriptor is not None else definition.args_model
    try:
        argument_validation = validate_tool_arguments(
            args_model=args_model,
            arguments=arguments,
        )
    except ToolArgumentValidationFailure as error:
        _log_tool_call(
            source=source,
            principal=principal,
            workspace=workspace,
            tool_name=tool_name,
            args_summary=args_summary,
            status="error",
            latency_ms=_elapsed_ms(started),
            call_id=call_id,
            error=error.message,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        )
        if error.localized_error is not None:
            code, params = error.localized_error
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code=code,
                **params,
            ) from error.validation_error
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.invalid_tool_arguments",
            reason=error.generic_reason,
        ) from error.validation_error
    validated_arguments = argument_validation.validated_arguments

    approval_required = (
        descriptor.approval_policy == "required"
        if descriptor is not None
        else definition.approval_required
    )
    if externally_approved_call_id is not None and source != "hermes-mcp":
        raise RuntimeError(
            "External approval evidence is restricted to the Hermes MCP bridge."
        )
    if approval_required:
        if principal.kind != "user":
            _log_tool_call(
                source=source,
                principal=principal,
                workspace=workspace,
                tool_name=tool_name,
                args_summary=args_summary,
                status="blocked",
                latency_ms=_elapsed_ms(started),
                call_id=call_id,
                error="Only user principals can resolve approval-gated AI tools.",
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
            )
            raise localized_http_exception(
                status_code=status.HTTP_403_FORBIDDEN,
                code="ai.only_user_principal_approval_tools",
            )
        if externally_approved_call_id is not None:
            approved_call_id = externally_approved_call_id
        elif approved_call_id is None:
            _log_tool_call(
                source=source,
                principal=principal,
                workspace=workspace,
                tool_name=tool_name,
                args_summary=args_summary,
                status="blocked",
                latency_ms=_elapsed_ms(started),
                call_id=call_id,
                error=f"AI tool requires approval before execution: {tool_name}",
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
            )
            raise build_tool_requires_approval(
                tool_call_id=call_id or "",
                tool_name=tool_name,
                validated_arguments=validated_arguments,
                descriptor=descriptor,
                workspace=workspace,
                principal=principal,
                parsed_args=argument_validation.parsed_args,
            )

        if externally_approved_call_id is None:
            approval = ai_approvals.get_approval(
                db,
                workspace=workspace,
                user=user,
                approval_id=approved_call_id,
                for_update=True,
            )
            validate_replayed_approval(
                approval=approval,
                tool_name=tool_name,
                call_id=call_id,
            )
            if approval.status == "approved":
                pass
            elif approval.status == "rejected":
                payload = build_rejected_approval_payload(
                    tool_name=definition.name,
                    owner_domain=definition.owner_domain,
                    approval_required=approval_required,
                    reject_reason=approval.reject_reason,
                )
                ai_approvals.record_approval_execution_result(
                    db,
                    approval=approval,
                    execution_result=payload["result"],
                    status="rejected",
                )
                _log_tool_call(
                    source=source,
                    principal=principal,
                    workspace=workspace,
                    tool_name=tool_name,
                    args_summary=args_summary,
                    status="ok",
                    latency_ms=_elapsed_ms(started),
                    call_id=call_id,
                    approval_id=approval.id,
                    agent_run_id=agent_run_id,
                    conversation_id=conversation_id,
                )
                return payload
            elif approval.status in {"cancelled", "expired"}:
                raise localized_http_exception(
                    status_code=status.HTTP_410_GONE,
                    code="ai.tool_approval_no_longer_usable",
                    status=approval.status,
                )
            else:
                raise localized_http_exception(
                    status_code=status.HTTP_409_CONFLICT,
                    code="ai.tool_approval_already_status",
                    status=approval.status,
                )

    tracer = get_tracer("open_work_hub_api.ai.tools")
    with bind_tool_execution_context(
        ToolExecutionContext(
            source=source,
            workspace_id=workspace.id,
            tool_name=tool_name,
            call_id=call_id,
            agent_run_id=agent_run_id,
            conversation_id=conversation_id,
        )
    ):
        try:
            with tracer.start_as_current_span(
                "ai.tool.execute",
                attributes={
                    "tool_name": tool_name,
                    "workspace_id": workspace.id,
                    "call_id": call_id or "",
                    "agent_run_id": agent_run_id or "",
                    "conversation_id": conversation_id or "",
                },
            ):
                result = _invoke_tool_handler(
                    handler,
                    db,
                    workspace,
                    principal,
                    user,
                    validated_arguments,
                    approved_call_id=approved_call_id,
                )
        except HTTPException as error:
            if approval_required and approval is not None:
                ai_approvals.record_approval_execution_result(
                    db,
                    approval=approval,
                    execution_result={
                        "status": "error",
                        "error": tool_http_exception_message(error),
                    },
                    status="failed",
                    error_message=tool_http_exception_message(error),
                )
            _log_tool_call(
                source=source,
                principal=principal,
                workspace=workspace,
                tool_name=tool_name,
                args_summary=args_summary,
                status="error",
                latency_ms=_elapsed_ms(started),
                call_id=call_id,
                approval_id=approval.id if approval is not None else None,
                error=tool_http_exception_message(error),
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
            )
            raise
        except Exception as error:
            if approval_required and approval is not None:
                ai_approvals.record_approval_execution_result(
                    db,
                    approval=approval,
                    execution_result={
                        "status": "error",
                        "error": str(error),
                    },
                    status="failed",
                    error_message=str(error),
                )
            _log_tool_call(
                source=source,
                principal=principal,
                workspace=workspace,
                tool_name=tool_name,
                args_summary=args_summary,
                status="error",
                latency_ms=_elapsed_ms(started),
                call_id=call_id,
                approval_id=approval.id if approval is not None else None,
                error=str(error),
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
            )
            raise

    encoded_result = jsonable_encoder(result)
    payload = {
        "tool": definition.name,
        "owner_domain": definition.owner_domain,
        "approval_required": approval_required,
        "result": encoded_result,
    }
    if approval_required and approval is not None:
        ai_approvals.record_approval_execution_result(
            db,
            approval=approval,
            execution_result=encoded_result,
            status="executed",
        )
    _log_tool_call(
        source=source,
        principal=principal,
        workspace=workspace,
        tool_name=tool_name,
        args_summary=args_summary,
        status="ok",
        latency_ms=_elapsed_ms(started),
        call_id=call_id,
        approval_id=approval.id if approval is not None else None,
        resource_ids=_extract_resource_ids(encoded_result),
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )
    return payload


def _extract_resource_ids(result: Any) -> list[str]:
    resource_ids: list[str] = []
    seen: set[str] = set()

    def add(value: Any) -> None:
        if not isinstance(value, str) or not value or value in seen:
            return
        seen.add(value)
        resource_ids.append(value)

    def visit(value: Any) -> None:
        if isinstance(value, Mapping):
            explicit_resource_ids = value.get("resource_ids")
            if isinstance(explicit_resource_ids, list):
                for resource_id in explicit_resource_ids:
                    add(resource_id)
            for nested_key in ("result", "aggregate_result", "items"):
                nested = value.get(nested_key)
                if isinstance(nested, (Mapping, list)):
                    visit(nested)
        elif isinstance(value, list):
            for item in value:
                visit(item)

    visit(result)
    return resource_ids


def _audit_argument_summary(value: Any, *, key: str | None = None) -> Any:
    if isinstance(value, Mapping):
        return {
            str(item_key): _audit_argument_summary(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [_audit_argument_summary(item, key=key) for item in value]
    if isinstance(value, str) and key is not None and key in _AUDIT_TEXT_ARGUMENT_KEYS:
        return f"<text:{len(value)} chars>"
    return value


def _invoke_tool_handler(
    handler,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    user: User,
    validated_arguments: Mapping[str, Any],
    *,
    approved_call_id: str | None,
) -> Any:
    signature = inspect.signature(handler)
    kwargs: dict[str, Any] = {}
    if approved_call_id is not None and "approved_call_id" in signature.parameters:
        kwargs["approved_call_id"] = approved_call_id
    return handler(
        db,
        workspace,
        principal,
        user,
        validated_arguments,
        **kwargs,
    )


def _log_tool_call(
    *,
    source: str,
    principal: CallerPrincipal,
    workspace: Workspace,
    tool_name: str,
    args_summary: str,
    status: str,
    latency_ms: int,
    call_id: str | None = None,
    approval_id: str | None = None,
    resource_ids: list[str] | None = None,
    error: str | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
) -> None:
    log_llm_tool_call(
        source=source,
        actor_user_id=principal.user_id,
        principal_kind=principal.kind,
        principal_id=principal.principal_id,
        workspace_id=workspace.id,
        tool_name=tool_name,
        args_summary=args_summary,
        status=status,
        resource_ids=resource_ids,
        error=error,
        latency_ms=latency_ms,
        call_id=call_id,
        approval_id=approval_id,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )


def _elapsed_ms(started: float) -> int:
    return int((perf_counter() - started) * 1000)
