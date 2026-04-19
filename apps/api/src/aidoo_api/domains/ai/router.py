import json
from dataclasses import dataclass
import asyncio
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from openai import OpenAIError
from pydantic import BaseModel, Field
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from aidoo_api.core.db import get_db_session
from aidoo_api.core.principal import CallerPrincipal, user_principal
from aidoo_api.core.llm import (
    LlmPoolConfig,
    LlmPoolHint,
    LlmPoolName,
    LlmTaskContext,
    PolicyDecision,
    check_all_pools_health,
    complete_chat,
    complete_chat_stream,
)
from aidoo_api.core.llm_adapters import StreamChunk
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.events import (
    EnvelopeEncoder,
    make_envelope,
    serialize_sse,
)
from aidoo_api.domains.ai.registry import get_ai_capability_registry
from aidoo_api.domains.ai.tool_service import execute_tool as execute_ai_tool
from aidoo_api.domains.auth.dependencies import require_current_user, require_current_workspace
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.security import new_id


LlmRequestBackendMode = Literal["auto", "local", "openrouter"]


class LlmPoolHealthResponse(BaseModel):
    pool: str
    provider: str
    base_url: str
    model: str
    canonical_model: str
    status: str
    ready: bool
    detail: str | None = None


class LlmDualHealthResponse(BaseModel):
    ready: bool
    local: LlmPoolHealthResponse
    external: LlmPoolHealthResponse | None = None


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
    backend_mode: LlmRequestBackendMode = "auto"
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=262144)
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = None


class ChatUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatResponse(BaseModel):
    model: str
    content: str
    usage: ChatUsage | None = None
    finish_reason: str | None = None
    provider: str
    backend: str
    fallback_used: bool = False
    canonical_model: str
    requested_backend_mode: str
    policy: str | None = None
    chosen_pool: str | None = None
    decision_reason: str | None = None
    forced_local: bool = False
    pii_hits: list[str] = Field(default_factory=list)


class ToolInvokeRequest(BaseModel):
    arguments: dict[str, Any] = Field(default_factory=dict)


class ToolInvokeResponse(BaseModel):
    tool: str
    owner_domain: str
    approval_required: bool
    result: Any


@dataclass(frozen=True)
class ToolChatCommand:
    tool_name: str
    arguments: dict[str, Any]


router = APIRouter(prefix="/ai", tags=["ai"])


@router.get("/health", response_model=LlmDualHealthResponse)
def ai_health() -> LlmDualHealthResponse:
    """Pool-scoped AI readiness. Each pool's status is reported independently;
    overall ``ready`` is true if at least one pool is usable. Routing decisions
    are still policy-driven, not fallback-driven.
    """
    return LlmDualHealthResponse.model_validate(check_all_pools_health().public_dict())


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ChatRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ChatResponse:
    _ensure_configured_model(payload.model)
    _ensure_supported_backend_mode(payload.backend_mode)
    workspace = _require_request_workspace(request)
    principal = _build_request_principal(current_user, request, source="api.chat")
    command = _parse_tool_chat_command(payload.messages)
    if command is not None:
        return _execute_tool_chat_command(
            payload,
            db,
            workspace=workspace,
            principal=principal,
            current_user=current_user,
            command=command,
        )
    context = _task_context_from_principal(principal)
    return _complete_via_policy(
        context,
        payload,
        db,
        pool_hint="local" if payload.backend_mode == "local" else None,
    )


class ChatStreamRequest(ChatRequest):
    stream_reasoning: bool = True


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> EventSourceResponse:
    """Agent-aware SSE stream.

    Wire protocol is documented in
    ``apps/api/src/aidoo_api/domains/ai/events_schema.md``. HTTP status is
    always 200 once the stream opens — failures surface as ``error`` +
    ``done(finish_reason=error)`` envelopes.
    """
    _ensure_configured_model(payload.model)
    _ensure_supported_backend_mode(payload.backend_mode)
    workspace = _require_request_workspace(request)
    principal = _build_request_principal(current_user, request, source="api.stream")
    context = _task_context_from_principal(principal)
    pool_hint: LlmPoolHint | None = (
        "local" if payload.backend_mode == "local" else None
    )

    return EventSourceResponse(
        _chat_stream_publisher(
            payload=payload,
            db=db,
            context=context,
            pool_hint=pool_hint,
            workspace=workspace,
            principal=principal,
            current_user=current_user,
        ),
        ping=25,
    )


@router.post("/tools/{tool_name}/invoke", response_model=ToolInvokeResponse)
def invoke_tool(
    tool_name: str,
    payload: ToolInvokeRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> ToolInvokeResponse:
    auth_context = getattr(request.state, "auth_context", None)
    principal = user_principal(
        workspace_id=current_workspace.id,
        user_id=current_user.id,
        source=f"api.ai.tool.{tool_name}",
        session_id=getattr(getattr(auth_context, "session", None), "id", None),
    )
    return ToolInvokeResponse.model_validate(
        execute_ai_tool(
            db,
            workspace=current_workspace,
            principal=principal,
            user=current_user,
            tool_name=tool_name,
            arguments=payload.arguments,
        )
    )


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _require_request_workspace(request: Request) -> Workspace:
    workspace = getattr(request.state, "current_workspace", None)
    if workspace is None:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=(
                "Workspace context missing on request.state; the AI router "
                "must be mounted behind a workspace membership dependency."
            ),
        )
    return workspace


def _build_request_principal(
    current_user: User,
    request: Request,
    *,
    source: str,
) -> CallerPrincipal:
    workspace = _require_request_workspace(request)
    auth_context = getattr(request.state, "auth_context", None)
    return user_principal(
        workspace_id=workspace.id,
        user_id=current_user.id,
        source=source,
        session_id=getattr(getattr(auth_context, "session", None), "id", None),
    )


def _task_context_from_principal(principal: CallerPrincipal) -> LlmTaskContext:
    return LlmTaskContext(
        source=principal.source,
        actor_user_id=principal.user_id,
        principal_kind=principal.kind,
        principal_id=principal.principal_id,
        workspace_id=principal.workspace_id,
        task_kind="chatbot",
    )


def _parse_tool_chat_command(messages: list[ChatMessage]) -> ToolChatCommand | None:
    last_user_message = next(
        (message.content.strip() for message in reversed(messages) if message.role == "user"),
        None,
    )
    if not last_user_message or not last_user_message.startswith("/tool"):
        return None

    parts = last_user_message.split(maxsplit=2)
    if len(parts) < 2 or parts[0] != "/tool":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Tool command syntax: /tool <tool_name> {\"arg\":\"value\"}",
        )

    arguments: dict[str, Any] = {}
    if len(parts) == 3 and parts[2].strip():
        try:
            parsed = json.loads(parts[2])
        except json.JSONDecodeError as error:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid tool argument JSON: {error.msg}",
            ) from error
        if not isinstance(parsed, dict):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Tool arguments must decode to a JSON object.",
            )
        arguments = parsed

    return ToolChatCommand(tool_name=parts[1], arguments=arguments)


def _execute_tool_chat_command(
    payload: ChatRequest,
    db: Session,
    *,
    workspace: Workspace,
    principal: CallerPrincipal,
    current_user: User,
    command: ToolChatCommand,
) -> ChatResponse:
    result = execute_ai_tool(
        db,
        workspace=workspace,
        principal=principal,
        user=current_user,
        tool_name=command.tool_name,
        arguments=command.arguments,
    )
    return ChatResponse(
        model=f"tool://{result['tool']}",
        content=_render_tool_result_message(result["tool"], result["result"]),
        usage=None,
        finish_reason="stop",
        provider="tool",
        backend="primary",
        fallback_used=False,
        canonical_model=f"tool://{result['tool']}",
        requested_backend_mode=payload.backend_mode,
        policy=None,
        chosen_pool=None,
        decision_reason="direct_tool_command",
        forced_local=False,
        pii_hits=[],
    )


def _complete_via_policy(
    context: LlmTaskContext,
    payload: ChatRequest,
    db: Session,
    *,
    pool_hint: LlmPoolHint | None,
) -> ChatResponse:
    try:
        response, decision, config = complete_chat(
            context,
            db,
            messages=[message.model_dump() for message in payload.messages],
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            reasoning_effort=payload.reasoning_effort,
            model=payload.model,
            pool_hint=pool_hint,
        )
    except OpenAIError as error:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail={
                "message": (
                    "Local LLM pool unavailable for the requested override."
                    if pool_hint == "local"
                    else "LLM pool unavailable for the resolved policy."
                ),
                "error": str(error),
            },
        ) from error

    return _build_response(
        response,
        config,
        payload,
        decision_policy=decision.policy,
        decision_pool=decision.chosen_pool,
        decision_reason=decision.reason,
        decision_forced_local=decision.forced_local,
        decision_pii=list(decision.pii_hits),
    )


def _build_response(
    raw_response,
    config,
    payload: ChatRequest,
    *,
    decision_policy: str | None,
    decision_pool: LlmPoolName | None,
    decision_reason: str | None,
    decision_forced_local: bool,
    decision_pii: list[str],
) -> ChatResponse:
    choice = raw_response.choices[0]
    message = choice.message
    usage = None
    if raw_response.usage is not None:
        usage = ChatUsage(
            prompt_tokens=raw_response.usage.prompt_tokens,
            completion_tokens=raw_response.usage.completion_tokens,
            total_tokens=raw_response.usage.total_tokens,
        )

    backend_name = "fallback" if decision_pool == "external" else "primary"

    return ChatResponse(
        model=raw_response.model,
        content=message.content or "",
        usage=usage,
        finish_reason=getattr(choice, "finish_reason", None),
        provider=config.provider,
        backend=backend_name,
        fallback_used=backend_name == "fallback",
        canonical_model=config.canonical_model,
        requested_backend_mode=payload.backend_mode,
        policy=decision_policy,
        chosen_pool=decision_pool,
        decision_reason=decision_reason,
        forced_local=decision_forced_local,
        pii_hits=decision_pii,
    )


def _ensure_configured_model(requested_model: str | None) -> None:
    if requested_model is None:
        return

    settings = get_settings()
    allowed_models = {
        settings.llm_local_default_model,
        settings.llm_local_canonical_model,
        settings.llm_external_default_model,
        settings.llm_external_canonical_model,
    }
    if requested_model in allowed_models:
        return

    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "Only the configured LLM model is allowed. "
            f"Use {settings.llm_local_canonical_model} for quality control."
        ),
    )


def _ensure_supported_backend_mode(mode: LlmRequestBackendMode) -> None:
    if mode != "openrouter":
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail=(
            "backend_mode=openrouter is no longer supported. "
            "Use auto for policy-based routing or local to pin the local pool."
        ),
    )


# ---------------------------------------------------------------------------
# SSE stream publisher
# ---------------------------------------------------------------------------


async def _chat_stream_publisher(
    *,
    payload: "ChatStreamRequest",
    db: Session,
    context: LlmTaskContext,
    pool_hint: LlmPoolHint | None,
    workspace: Workspace,
    principal: CallerPrincipal,
    current_user: User,
):
    encoder = EnvelopeEncoder()
    reasoning_gate = (
        payload.stream_reasoning and payload.reasoning_effort != "none"
    )
    messages_dict = [message.model_dump() for message in payload.messages]

    last_decision: PolicyDecision | None = None
    last_config: LlmPoolConfig | None = None
    chosen_model: str | None = None

    try:
        command = _parse_tool_chat_command(payload.messages)
        if command is not None:
            for event in _tool_command_events(
                encoder=encoder,
                db=db,
                workspace=workspace,
                principal=principal,
                current_user=current_user,
                command=command,
            ):
                yield event
            return

        async for chunk, decision, config in complete_chat_stream(
            context,
            db,
            messages=messages_dict,
            temperature=payload.temperature,
            max_tokens=payload.max_tokens,
            reasoning_effort=payload.reasoning_effort,
            model=payload.model,
            pool_hint=pool_hint,
            stream_reasoning=payload.stream_reasoning,
        ):
            last_decision, last_config = decision, config
            chosen_model = payload.model or config.default_model
            event = _chunk_to_envelope(
                chunk,
                encoder=encoder,
                reasoning_gate=reasoning_gate,
                decision=last_decision,
                config=last_config,
                model=chosen_model,
            )
            if event is not None:
                yield event
    except asyncio.CancelledError:
        return
    except Exception as error:  # noqa: BLE001 - converted to SSE contract
        yield serialize_sse(
            make_envelope(
                "error",
                encoder.next_seq(),
                {
                    "code": _error_code(error),
                    "message": _error_message(error),
                    "retryable": False,
                },
            )
        )
        yield serialize_sse(
            make_envelope(
                "done",
                encoder.next_seq(),
                {
                    "finish_reason": "error",
                    "audit_id": None,
                    "meta": _build_done_meta(
                        last_decision,
                        last_config,
                        model=chosen_model,
                    ),
                },
            )
        )


def _tool_command_events(
    *,
    encoder: EnvelopeEncoder,
    db: Session,
    workspace: Workspace,
    principal: CallerPrincipal,
    current_user: User,
    command: ToolChatCommand,
):
    call_id = new_id()
    arguments_json = json.dumps(command.arguments, ensure_ascii=False, sort_keys=True)
    yield serialize_sse(
        make_envelope(
            "tool_call_started",
            encoder.next_seq(),
            {
                "call_id": call_id,
                "name": command.tool_name,
                "args_preview": _preview_text(arguments_json, limit=240),
            },
        )
    )
    yield serialize_sse(
        make_envelope(
            "tool_call_args_delta",
            encoder.next_seq(),
            {
                "call_id": call_id,
                "delta": arguments_json,
            },
        )
    )

    registry = get_ai_capability_registry()
    definition = registry.tools.get(command.tool_name)
    if definition is None:
        message = f"Unknown AI tool: {command.tool_name}"
        yield serialize_sse(
            make_envelope(
                "tool_result",
                encoder.next_seq(),
                {
                    "call_id": call_id,
                    "status": "error",
                    "error": message,
                },
            )
        )
        yield serialize_sse(
            make_envelope(
                "error",
                encoder.next_seq(),
                {
                    "code": "request_error",
                    "message": message,
                    "retryable": False,
                },
            )
        )
        yield serialize_sse(
            make_envelope(
                "done",
                encoder.next_seq(),
                {
                    "finish_reason": "error",
                    "audit_id": None,
                    "meta": _tool_done_meta(command.tool_name),
                },
            )
        )
        return

    if definition.approval_required:
        approval_id = new_id()
        message = f"도구 {command.tool_name} 실행에는 승인 절차가 필요합니다."
        yield serialize_sse(
            make_envelope(
                "approval_required",
                encoder.next_seq(),
                {
                    "approval_id": approval_id,
                    "tool": command.tool_name,
                    "resource_preview": _preview_text(arguments_json, limit=240),
                },
            )
        )
        yield serialize_sse(
            make_envelope(
                "content_delta",
                encoder.next_seq(),
                {"text": message},
            )
        )
        yield serialize_sse(
            make_envelope(
                "done",
                encoder.next_seq(),
                {
                    "finish_reason": "stop",
                    "audit_id": None,
                    "meta": _tool_done_meta(command.tool_name),
                },
            )
        )
        return

    try:
        result = execute_ai_tool(
            db,
            workspace=workspace,
            principal=principal,
            user=current_user,
            tool_name=command.tool_name,
            arguments=command.arguments,
        )
    except HTTPException as error:
        message = _error_message(error)
        yield serialize_sse(
            make_envelope(
                "tool_result",
                encoder.next_seq(),
                {
                    "call_id": call_id,
                    "status": "error",
                    "error": message,
                },
            )
        )
        yield serialize_sse(
            make_envelope(
                "error",
                encoder.next_seq(),
                {
                    "code": "request_error",
                    "message": message,
                    "retryable": False,
                },
            )
        )
        yield serialize_sse(
            make_envelope(
                "done",
                encoder.next_seq(),
                {
                    "finish_reason": "error",
                    "audit_id": None,
                    "meta": _tool_done_meta(command.tool_name),
                },
            )
        )
        return

    yield serialize_sse(
        make_envelope(
            "tool_result",
            encoder.next_seq(),
            {
                "call_id": call_id,
                "status": "ok",
                "result_preview": _preview_text(_dump_json(result["result"]), limit=1200),
            },
        )
    )
    yield serialize_sse(
        make_envelope(
            "content_delta",
            encoder.next_seq(),
            {
                "text": _render_tool_result_message(result["tool"], result["result"]),
            },
        )
    )
    yield serialize_sse(
        make_envelope(
            "done",
            encoder.next_seq(),
            {
                "finish_reason": "stop",
                "audit_id": None,
                "meta": _tool_done_meta(result["tool"]),
            },
        )
    )


def _chunk_to_envelope(
    chunk: StreamChunk,
    *,
    encoder: EnvelopeEncoder,
    reasoning_gate: bool,
    decision: PolicyDecision | None,
    config: LlmPoolConfig | None,
    model: str | None,
) -> dict[str, str] | None:
    if chunk.kind == "content" and chunk.text:
        return serialize_sse(
            make_envelope(
                "content_delta",
                encoder.next_seq(),
                {"text": chunk.text},
            )
        )
    if chunk.kind == "reasoning" and chunk.text and reasoning_gate:
        return serialize_sse(
            make_envelope(
                "reasoning_delta",
                encoder.next_seq(),
                {"text": chunk.text},
            )
        )
    if chunk.kind == "usage" and chunk.usage:
        return serialize_sse(
            make_envelope("usage", encoder.next_seq(), chunk.usage)
        )
    if chunk.kind == "done":
        return serialize_sse(
            make_envelope(
                "done",
                encoder.next_seq(),
                {
                    "finish_reason": chunk.finish_reason or "stop",
                    "audit_id": None,
                    "meta": _build_done_meta(decision, config, model=model),
                },
            )
        )
    return None


def _dump_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, indent=2, sort_keys=True)


def _preview_text(text: str, *, limit: int) -> str:
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1]}…"


def _render_tool_result_message(tool_name: str, result: Any) -> str:
    return (
        f"도구 {tool_name} 실행 결과입니다.\n"
        f"{_preview_text(_dump_json(result), limit=4000)}"
    )


def _tool_done_meta(tool_name: str) -> dict[str, Any]:
    tool_model = f"tool://{tool_name}"
    return {
        "policy": None,
        "chosen_pool": None,
        "decision_reason": "direct_tool_command",
        "forced_local": False,
        "pii_hits": [],
        "model": tool_model,
        "chosen_model": tool_model,
        "canonical_model": tool_model,
        "provider": "tool",
    }


def _build_done_meta(
    decision: PolicyDecision | None,
    config: LlmPoolConfig | None,
    *,
    model: str | None,
) -> dict[str, Any] | None:
    if decision is None or config is None:
        return None
    return {
        "policy": decision.policy,
        "chosen_pool": decision.chosen_pool,
        "decision_reason": decision.reason,
        "forced_local": decision.forced_local,
        "pii_hits": list(decision.pii_hits),
        "model": model or config.default_model,
        "chosen_model": model or config.default_model,
        "canonical_model": config.canonical_model,
        "provider": config.provider,
    }


def _error_code(error: Exception) -> str:
    if isinstance(error, HTTPException):
        return "request_error"
    if isinstance(error, OpenAIError):
        return "provider_error"
    return "adapter_error"


def _error_message(error: Exception) -> str:
    if isinstance(error, HTTPException):
        detail = error.detail
        if isinstance(detail, str):
            return detail
        if isinstance(detail, dict):
            message = detail.get("message")
            if isinstance(message, str) and message.strip():
                return message
        return "AI request failed."
    return str(error)
