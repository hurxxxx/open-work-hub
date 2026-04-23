from __future__ import annotations

import inspect
import json
from collections.abc import Mapping
from time import perf_counter
from typing import Any

from fastapi import HTTPException, status
from fastapi.encoders import jsonable_encoder
from pydantic import BaseModel, ValidationError
from sqlalchemy.orm import Session

from aidoo_api.core.telemetry import get_tracer
from aidoo_api.core.principal import CallerPrincipal
from aidoo_api.domains.ai import approvals as ai_approvals
from aidoo_api.domains.ai.audit import log_llm_tool_call
from aidoo_api.domains.ai.tool_context import ToolExecutionContext, bind_tool_execution_context
from aidoo_api.domains.ai.registry import (
    ApprovalPreview,
    build_workspace_context,
    get_ai_capability_registry,
    resolve_workspace_entitlement_view,
)
from aidoo_api.domains.auth.models import User, Workspace


class ToolRequiresApproval(Exception):
    def __init__(
        self,
        *,
        tool_call_id: str,
        tool_name: str,
        arguments_json: str,
        resource_preview: str | None,
    ) -> None:
        super().__init__(f"AI tool requires approval before execution: {tool_name}")
        self.tool_call_id = tool_call_id
        self.tool_name = tool_name
        self.arguments_json = arguments_json
        self.resource_preview = resource_preview


def approval_required_http_exception(error: ToolRequiresApproval) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail=str(error),
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
) -> dict[str, Any]:
    started = perf_counter()
    registry = get_ai_capability_registry()
    approval: ai_approvals.AiToolApproval | None = None
    definition = registry.tools.get(tool_name)
    descriptor = registry.get_descriptor(tool_name)
    args_summary = preview_text(
        json.dumps(dict(arguments), ensure_ascii=False, default=str),
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
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Unknown AI tool: {tool_name}",
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
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"AI tool discoverability predicate is not registered: {tool_name}",
            )
        workspace_context = build_workspace_context(workspace)
        entitlements = resolve_workspace_entitlement_view(db, workspace=workspace)
        if not predicate(principal, workspace_context, entitlements):
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
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"AI tool is not available in this workspace: {tool_name}",
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
        raise HTTPException(
            status_code=status.HTTP_501_NOT_IMPLEMENTED,
            detail=f"AI tool is registered but not executable yet: {tool_name}",
        )
    validated_arguments = dict(arguments)
    validated: BaseModel | None = None
    args_model = descriptor.ai_input_model if descriptor is not None else definition.args_model
    if args_model is not None:
        try:
            validated = args_model.model_validate(dict(arguments))
        except ValidationError as error:
            message = _validation_error_message(error)
            _log_tool_call(
                source=source,
                principal=principal,
                workspace=workspace,
                tool_name=tool_name,
                args_summary=args_summary,
                status="error",
                latency_ms=_elapsed_ms(started),
                call_id=call_id,
                error=message,
                agent_run_id=agent_run_id,
                conversation_id=conversation_id,
            )
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=message,
            ) from error
        assert validated is not None
        validated_arguments = validated.model_dump(
            mode="python",
            by_alias=True,
            exclude_none=True,
        )

    approval_required = (
        descriptor.approval_policy == "required"
        if descriptor is not None
        else definition.approval_required
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
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail="Only user principals can resolve approval-gated AI tools.",
            )
        if approved_call_id is None:
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
            raise ToolRequiresApproval(
                tool_call_id=call_id or "",
                tool_name=tool_name,
                arguments_json=json.dumps(
                    jsonable_encoder(validated_arguments),
                    ensure_ascii=False,
                    sort_keys=True,
                ),
                resource_preview=_build_resource_preview(
                    descriptor=descriptor,
                    workspace=workspace,
                    principal=principal,
                    parsed_args=validated if args_model is not None else validated_arguments,
                ),
            )

        approval = ai_approvals.get_approval(
            db,
            workspace=workspace,
            user=user,
            approval_id=approved_call_id,
            for_update=True,
        )
        _validate_replayed_approval(
            approval=approval,
            tool_name=tool_name,
            call_id=call_id,
        )
        if approval.status == "approved":
            pass
        elif approval.status == "rejected":
            payload = {
                "tool": definition.name,
                "owner_domain": definition.owner_domain,
                "approval_required": approval_required,
                "result": {
                    "status": "rejected",
                    "reason": approval.reject_reason,
                },
            }
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
            raise HTTPException(
                status_code=status.HTTP_410_GONE,
                detail=f"AI tool approval can no longer be used: {approval.status}.",
            )
        else:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"AI tool approval is already {approval.status}.",
            )

    tracer = get_tracer("aidoo_api.ai.tools")
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
                        "error": _error_message(error),
                    },
                    status="failed",
                    error_message=_error_message(error),
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
                error=_error_message(error),
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


def dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def preview_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def render_tool_result_message(tool_name: str, result: Any) -> str:
    return f"도구 {tool_name} 실행 결과입니다.\n{preview_text(dump_json(result), limit=4000)}"


def serialize_tool_result_for_llm(
    *,
    tool_name: str,
    result: Any | None = None,
    error: str | None = None,
    limit: int = 4000,
) -> str:
    if error is not None:
        return dump_json(
            {
                "tool": tool_name,
                "status": "error",
                "error": preview_text(error, limit=max(64, limit - 96)),
            }
        )

    if result is None:
        return dump_json({"tool": tool_name, "status": "ok", "result": None})

    candidate = {
        "tool": tool_name,
        "status": "ok",
        "result": result,
    }
    dumped = dump_json(candidate)
    if len(dumped) <= limit:
        return dumped

    return dump_json(
        {
            "tool": tool_name,
            "status": "ok",
            "result_preview": preview_text(dump_json(result), limit=max(256, limit - 128)),
            "truncated": True,
        }
    )


def tool_result_preview(result: Any) -> str:
    return preview_text(dump_json(result), limit=1200)


def sanitize_reject_reason_for_llm(reason: str | None, *, limit: int = 280) -> str | None:
    if reason is None:
        return None
    collapsed = " ".join(reason.split())
    if not collapsed:
        return None
    return preview_text(collapsed, limit=limit)


def serialize_rejected_tool_result_for_llm(
    *,
    tool_name: str,
    reason: str | None,
) -> str:
    return dump_json(
        {
            "tool": tool_name,
            "status": "rejected",
            "reason": sanitize_reject_reason_for_llm(reason),
        }
    )


def _extract_resource_ids(result: Any) -> list[str]:
    resource_ids: list[str] = []
    if isinstance(result, Mapping):
        top_level_id = result.get("id")
        if isinstance(top_level_id, str):
            resource_ids.append(top_level_id)
        items = result.get("items")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, Mapping):
                    continue
                item_id = item.get("id")
                if isinstance(item_id, str):
                    resource_ids.append(item_id)
    return resource_ids


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


def _build_resource_preview(
    *,
    descriptor,
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
    return _render_approval_preview(preview)


def _render_approval_preview(preview: ApprovalPreview | None) -> str | None:
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


def _validate_replayed_approval(
    *,
    approval: ai_approvals.AiToolApproval,
    tool_name: str,
    call_id: str | None,
) -> None:
    if approval.tool_name != tool_name:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval does not match the requested tool.",
        )
    if call_id is not None and approval.tool_call_id != call_id:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Approval does not match the requested tool call.",
        )


def _validation_error_message(error: ValidationError) -> str:
    parts: list[str] = []
    for item in error.errors():
        location = ".".join(str(part) for part in item.get("loc", []))
        message = item.get("msg", "Invalid value.")
        if location:
            parts.append(f"{location}: {message}")
        else:
            parts.append(str(message))
    if not parts:
        return "Invalid tool arguments."
    return "Invalid tool arguments: " + "; ".join(parts)


def _error_message(error: HTTPException) -> str:
    detail = error.detail
    if isinstance(detail, str):
        return detail
    return "AI tool execution failed."


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
