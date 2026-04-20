import json
from dataclasses import dataclass, field
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
    resolve_chat_execution,
)
from aidoo_api.core.llm_adapters import StreamChunk, supports_tool_calling
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.agent import run_agent_turn_stream
from aidoo_api.domains.ai.artifact_parser import (
    ArtifactStreamParser,
    ParsedArtifactBody,
    ParsedArtifactEnd,
    ParsedArtifactStart,
    ParsedText,
)
from aidoo_api.domains.ai.events import (
    EnvelopeEncoder,
    make_envelope,
    serialize_sse,
)
from aidoo_api.domains.ai.mcp import AiMcpClient
from aidoo_api.domains.ai.registry import get_ai_capability_registry
from aidoo_api.domains.ai.tool_runtime import (
    ToolCallExecution,
    execute_tool_call,
    iter_tool_call_events,
)
from aidoo_api.domains.ai.tool_service import (
    execute_tool as execute_ai_tool,
    render_tool_result_message,
)
from aidoo_api.domains.auth.dependencies import require_current_user, require_current_workspace
from aidoo_api.domains.auth.models import User, Workspace
from aidoo_api.domains.auth.workspace_apps import WORKSPACE_APP_IDS
from aidoo_api.domains.auth.security import new_id
from aidoo_api.domains.conversations import service as conversations_service
from aidoo_api.domains.conversations.models import Conversation


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


class ConversationBoundChatRequest(ChatRequest):
    # If set, append to the named conversation (must belong to the caller).
    conversation_id: str | None = None
    # Opt-in flag to have the server allocate a fresh conversation row when
    # ``conversation_id`` is absent. Defaults to False so legacy callers
    # don't silently fragment their history into one-turn conversations.
    persist: bool = False


class ChatUsage(BaseModel):
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None


class ChatArtifact(BaseModel):
    """Server-parsed artifact returned with a sync /chat response so the
    client doesn't have to re-parse the markup (which would invent its own
    ids that wouldn't match the persisted row on reload)."""

    id: str
    type: str
    title: str | None = None
    # Only populated for ``type="code"`` artifacts. Other types leave it
    # null so the client falls back to highlight.js auto-detection.
    language: str | None = None
    content: str


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
    conversation_id: str | None = None
    artifacts: list[ChatArtifact] = Field(default_factory=list)


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


@router.get("/capabilities/manifest")
def capability_manifest(
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> dict[str, Any]:
    _ensure_mcp_bridge_enabled()
    principal = _build_request_principal(
        current_user,
        request,
        source="api.ai.capabilities.manifest",
    )
    _ = current_workspace
    return AiMcpClient().build_manifest(
        db,
        workspace=_require_request_workspace(request),
        principal=principal,
        include_meta=True,
    )


@router.get("/apps/{app_id}/manifest")
def app_capability_manifest(
    app_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> dict[str, Any]:
    _ensure_mcp_bridge_enabled()
    _ensure_known_workspace_app(app_id)
    principal = _build_request_principal(
        current_user,
        request,
        source=f"api.ai.apps.{app_id}.manifest",
    )
    _ = current_workspace
    return AiMcpClient().build_manifest(
        db,
        workspace=_require_request_workspace(request),
        principal=principal,
        app_id=app_id,
        include_meta=True,
    )


@router.get("/capabilities/openapi.json")
def capability_openapi_export(
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> dict[str, Any]:
    _ensure_mcp_bridge_enabled()
    principal = _build_request_principal(
        current_user,
        request,
        source="api.ai.capabilities.openapi",
    )
    _ = current_workspace
    return AiMcpClient().build_openapi_export(
        db,
        workspace=_require_request_workspace(request),
        principal=principal,
    )


@router.get("/apps/{app_id}/openapi.json")
def app_capability_openapi_export(
    app_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
    current_workspace: Workspace = Depends(require_current_workspace),
) -> dict[str, Any]:
    _ensure_mcp_bridge_enabled()
    _ensure_known_workspace_app(app_id)
    principal = _build_request_principal(
        current_user,
        request,
        source=f"api.ai.apps.{app_id}.openapi",
    )
    _ = current_workspace
    return AiMcpClient().build_openapi_export(
        db,
        workspace=_require_request_workspace(request),
        principal=principal,
        app_id=app_id,
    )


@router.get("/health", response_model=LlmDualHealthResponse)
def ai_health() -> LlmDualHealthResponse:
    """Pool-scoped AI readiness. Each pool's status is reported independently;
    overall ``ready`` is true if at least one pool is usable. Routing decisions
    are still policy-driven, not fallback-driven.
    """
    return LlmDualHealthResponse.model_validate(check_all_pools_health().public_dict())


@router.post("/chat", response_model=ChatResponse)
def chat(
    payload: ConversationBoundChatRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ChatResponse:
    _ensure_configured_model(payload.model)
    _ensure_supported_backend_mode(payload.backend_mode)
    workspace = _require_request_workspace(request)
    principal = _build_request_principal(current_user, request, source="api.chat")
    conversation = _resolve_requested_conversation(
        db=db,
        workspace=workspace,
        user=current_user,
        conversation_id=payload.conversation_id,
    )
    command = _parse_tool_chat_command(payload.messages)
    is_tool_command_response = command is not None
    tool_execution: ToolCallExecution | None = None
    if is_tool_command_response:
        response, tool_execution = _execute_tool_chat_command(
            payload,
            db,
            workspace=workspace,
            principal=principal,
            current_user=current_user,
            command=command,
        )
    else:
        context = _task_context_from_principal(principal)
        response = _complete_via_policy(
            context,
            payload,
            db,
            pool_hint="local" if payload.backend_mode == "local" else None,
        )

    # Parse `<artifact>` markup out of the sync reply once — using the same
    # parser the streaming path uses. This gives us canonical server-side
    # artifact ids that both the wire response (``response.artifacts``) and
    # the persisted row (``turn.meta.artifacts``) reference, so a client
    # URL like ``?a=<id>`` still resolves after reload. Without this
    # step the client would invent its own ids during fallback parsing and
    # they would drift from the saved thread.
    #
    # Skip parsing for direct tool-command responses — those contain
    # serialized tool output (arbitrary JSON / user data) and the streaming
    # path's ``_tool_command_events`` also bypasses the artifact parser.
    # Routing them through the parser here would strip any literal
    # ``<artifact>`` text in tool output and diverge the sync/stream
    # transports.
    if is_tool_command_response:
        assert tool_execution is not None
        sync_buffer = _assistant_buffer_from_sync_response(
            response,
            parse_artifacts=False,
            tool_execution=tool_execution,
        )
    else:
        sync_buffer = _assistant_buffer_from_sync_response(response)
        response.content = sync_buffer.content
        response.artifacts = [
            ChatArtifact(
                id=record["id"],
                type=record.get("type") or "document",
                title=record.get("title"),
                language=record.get("language"),
                content=record.get("content") or "",
            )
            for record in sync_buffer.artifacts
        ]

    # Never let a persistence failure turn a successful model reply into a
    # 500 — history is best-effort, the actual answer is already in hand.
    # Log the failure and return the reply without a conversation_id so the
    # client at least shows what the model produced. The streaming publisher
    # has an equivalent guard in `_persist_assistant_turn`.
    try:
        response.conversation_id = _persist_sync_chat_response(
            db=db,
            workspace=workspace,
            user=current_user,
            payload=payload,
            conversation=conversation,
            buffer=sync_buffer,
        )
    except Exception as exc:  # noqa: BLE001 - persistence is best-effort
        import logging

        logging.getLogger(__name__).exception(
            "sync chat persistence failed conversation_id=%s: %s",
            conversation.id if conversation is not None else None,
            exc,
        )
        db.rollback()
        response.conversation_id = conversation.id if conversation is not None else None
    return response


class ChatStreamRequest(ConversationBoundChatRequest):
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
    pool_hint: LlmPoolHint | None = "local" if payload.backend_mode == "local" else None

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
    settings = get_settings()
    if settings.ai_mcp_bridge_enabled:
        response = AiMcpClient().call_tool(
            db,
            workspace=current_workspace,
            principal=principal,
            user=current_user,
            tool_name=tool_name,
            arguments=payload.arguments,
            source="api.tool_invoke",
        )
    else:
        response = execute_ai_tool(
            db,
            workspace=current_workspace,
            principal=principal,
            user=current_user,
            tool_name=tool_name,
            arguments=payload.arguments,
            source="api.tool_invoke",
        )
    return ToolInvokeResponse.model_validate(response)


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


def _ensure_mcp_bridge_enabled() -> None:
    settings = get_settings()
    if settings.ai_mcp_bridge_enabled:
        return
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail="AI MCP bridge inspection endpoints are disabled.",
    )


def _ensure_known_workspace_app(app_id: str) -> None:
    if app_id in WORKSPACE_APP_IDS:
        return
    raise HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail=f"Unknown workspace app: {app_id}",
    )


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
            detail='Tool command syntax: /tool <tool_name> {"arg":"value"}',
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
) -> tuple[ChatResponse, ToolCallExecution]:
    """Run a direct ``/tool ...`` chat command.

    Returns both the wire response and the underlying tool execution so
    the sync path can synthesize the same ``tool_call_started`` /
    ``tool_result`` envelopes the streaming path records — keeping the
    persisted turn's ``tool_calls`` metadata identical across transports.
    """
    execution = execute_tool_call(
        db,
        workspace=workspace,
        principal=principal,
        user=current_user,
        tool_name=command.tool_name,
        arguments=command.arguments,
        source="api.chat",
    )
    if execution.status == "ok":
        assert execution.response is not None
        tool_name = execution.response["tool"]
        result_payload = execution.response["result"]
        content = render_tool_result_message(tool_name, result_payload)
        finish_reason = "stop"
    elif execution.status == "blocked":
        tool_name = execution.tool_name
        content = execution.error_message or f"도구 {tool_name} 실행에는 승인 절차가 필요합니다."
        finish_reason = "stop"
    else:
        tool_name = execution.tool_name
        content = execution.error_message or "AI tool execution failed."
        finish_reason = "error"
    response = ChatResponse(
        model=f"tool://{tool_name}",
        content=content,
        usage=None,
        finish_reason=finish_reason,
        provider="tool",
        backend="primary",
        fallback_used=False,
        canonical_model=f"tool://{tool_name}",
        requested_backend_mode=payload.backend_mode,
        policy=None,
        chosen_pool=None,
        decision_reason="direct_tool_command",
        forced_local=False,
        pii_hits=[],
    )
    return response, execution


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
        conversation_id=None,
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
    reasoning_gate = payload.stream_reasoning and payload.reasoning_effort != "none"
    messages_dict = [message.model_dump() for message in payload.messages]
    settings = get_settings()

    last_decision: PolicyDecision | None = None
    last_config: LlmPoolConfig | None = None
    chosen_model: str | None = None

    # Bind the turn-persistence context before any events fire. On a
    # validation-style error the helper returns a full terminal
    # (error, done) envelope pair so the client leaves the streaming state
    # cleanly; on success the stream proceeds normally.
    conversation, terminal_envelopes = _bind_conversation_for_stream(
        db=db,
        workspace=workspace,
        user=current_user,
        payload=payload,
    )
    if terminal_envelopes is not None:
        for envelope in terminal_envelopes:
            yield envelope
        return

    if conversation is not None:
        yield serialize_sse(
            make_envelope(
                "conversation_attached",
                encoder.next_seq(),
                {"conversation_id": conversation.id},
            )
        )
        # Persist the user turn inside the SSE error contract — if the write
        # fails (retry budget exhausted on a concurrent insert, DB down),
        # surface it as a normal error+done pair rather than tearing the
        # stream down mid-flight, which would leave the client hanging.
        try:
            _record_user_turn(
                db=db,
                conversation=conversation,
                messages=payload.messages,
            )
        except Exception as exc:  # noqa: BLE001
            import logging

            logging.getLogger(__name__).exception(
                "user turn persistence failed conversation_id=%s: %s",
                conversation.id,
                exc,
            )
            yield serialize_sse(
                make_envelope(
                    "error",
                    encoder.next_seq(),
                    {
                        "code": "conversation_persist_error",
                        "message": "채팅 기록 저장 중 오류가 발생했습니다.",
                        "retryable": True,
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
                        "meta": None,
                    },
                )
            )
            return

    buffer = _AssistantTurnBuffer()
    # Artifact parser is stateful across the entire stream (one per request).
    # It converts `<artifact>...</artifact>` markup embedded in content_deltas
    # into artifact_started/delta/completed envelopes so the client renders
    # those bodies in a side panel instead of the chat bubble.
    artifact_parser = ArtifactStreamParser()

    try:
        command = _parse_tool_chat_command(payload.messages)
        if command is not None:
            # Direct tool commands bypass the LLM so they can never produce
            # artifact markup — no parser wiring needed on this path.
            for event in _tool_command_events(
                encoder=encoder,
                db=db,
                workspace=workspace,
                principal=principal,
                current_user=current_user,
                command=command,
            ):
                buffer.observe(event)
                yield event
            return

        execution = resolve_chat_execution(
            context,
            db,
            messages=messages_dict,
            max_tokens=payload.max_tokens,
            reasoning_effort=payload.reasoning_effort,
            model=payload.model,
            pool_hint=pool_hint,
        )
        last_decision = execution.decision
        last_config = execution.config
        chosen_model = execution.chosen_model

        mcp_client = AiMcpClient()
        filtered_tool_specs = (
            mcp_client.list_openai_function_specs(
                db,
                workspace=workspace,
                principal=principal,
                include_approval_required=False,
            )
            if settings.ai_mcp_bridge_enabled
            else get_ai_capability_registry().openai_tool_specs()
        )
        if (
            settings.ai_tool_calling_enabled
            and supports_tool_calling(execution.pool)
            and bool(filtered_tool_specs)
        ):
            agent_run_id = new_id()
            async for event in run_agent_turn_stream(
                context=context,
                execution=execution,
                db=db,
                workspace=workspace,
                principal=principal,
                user=current_user,
                messages=messages_dict,
                temperature=payload.temperature,
                stream_reasoning=payload.stream_reasoning,
                encoder=encoder,
                max_turns=settings.ai_agent_max_turns,
                max_tool_calls=settings.ai_agent_max_tool_calls,
                max_consecutive_tool_errors=settings.ai_agent_max_consecutive_tool_errors,
                agent_run_id=agent_run_id,
                tool_specs=filtered_tool_specs,
            ):
                # Route content_delta through the artifact parser so embedded
                # `<artifact>` blocks become their own envelope stream. All
                # other event types pass through as-is. Before the agent's
                # terminal `done` event, flush the parser so any artifacts
                # still open (malformed close, model cut off) get synthetic
                # artifact_completed envelopes — the client's buffers must
                # terminate before it reads `done`.
                if event.type == "done":
                    # Flush any dangling artifact first. When flush emits
                    # synthesized ``artifact_completed`` envelopes they
                    # consume fresh seqs from the shared encoder, which has
                    # already moved past the agent's pre-allocated ``done``
                    # seq — in that case re-allocate ``done`` so the wire
                    # stays monotone (events_schema.md guarantee). When
                    # flush is a no-op, keep the original seq to avoid a
                    # gap in the common case.
                    flushed_envelopes = _flush_parser(artifact_parser, encoder=encoder)
                    for flushed in flushed_envelopes:
                        buffer.observe(flushed)
                        yield flushed
                    if flushed_envelopes:
                        reissued = serialize_sse(
                            make_envelope(
                                "done",
                                encoder.next_seq(),
                                event.data.model_dump(),
                                timestamp_ms=event.timestamp_ms,
                            )
                        )
                        buffer.observe(reissued)
                        yield reissued
                    else:
                        serialized = serialize_sse(event)
                        buffer.observe(serialized)
                        yield serialized
                elif event.type == "content_delta":
                    text = event.data.text
                    parsed_events = artifact_parser.feed(text)
                    # Fast path: the parser saw only plain text (no markup,
                    # no buffered partial tag). Reuse the agent's pre-
                    # allocated seq so seqs stay contiguous for the common
                    # case; the slow path accepts a rare gap when markup
                    # produces multiple envelopes from one input chunk.
                    if (
                        len(parsed_events) == 1
                        and isinstance(parsed_events[0], ParsedText)
                        and parsed_events[0].text == text
                    ):
                        serialized = serialize_sse(event)
                        buffer.observe(serialized)
                        yield serialized
                    else:
                        for parsed_out in _parser_events_to_envelopes(
                            parsed_events, encoder=encoder
                        ):
                            buffer.observe(parsed_out)
                            yield parsed_out
                else:
                    serialized = serialize_sse(event)
                    buffer.observe(serialized)
                    yield serialized
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
            resolved_execution=execution,
        ):
            last_decision, last_config = decision, config
            chosen_model = execution.chosen_model
            # Content chunks feed the artifact parser; every other kind
            # (reasoning/usage/tool_*/done) goes through _chunk_to_envelope.
            # The ``done`` chunk must be preceded by a parser flush so the
            # client receives terminal artifact_completed envelopes before
            # it reads ``done``.
            if chunk.kind == "content" and chunk.text:
                for parsed_event in _emit_content_through_parser(
                    chunk.text,
                    parser=artifact_parser,
                    encoder=encoder,
                ):
                    buffer.observe(parsed_event)
                    yield parsed_event
                continue
            if chunk.kind == "done":
                for flushed in _flush_parser(artifact_parser, encoder=encoder):
                    buffer.observe(flushed)
                    yield flushed
            event = _chunk_to_envelope(
                chunk,
                encoder=encoder,
                reasoning_gate=reasoning_gate,
                decision=last_decision,
                config=last_config,
                model=chosen_model,
            )
            if event is not None:
                buffer.observe(event)
                yield event
    except (asyncio.CancelledError, GeneratorExit):
        # Client aborted mid-stream. The SSE framework can close the
        # generator with either exception depending on how the disconnect
        # propagates — both must mark the assistant turn as cancelled so the
        # reload path matches what the user saw. The finally block still
        # runs and persists the partial response with
        # ``response_status="cancelled"``.
        buffer.cancelled = True
        # Drain the artifact parser into the buffer (not the wire — the
        # generator is already being torn down) so any in-flight artifact
        # lands on disk with an artifact_completed synthesized by flush().
        for flushed in _flush_parser(artifact_parser, encoder=encoder):
            buffer.observe(flushed)
        return
    except Exception as error:  # noqa: BLE001 - converted to SSE contract
        # Flush artifact parser before the terminal error/done pair so the
        # client finalizes any open artifact buffers before acting on `done`.
        for flushed in _flush_parser(artifact_parser, encoder=encoder):
            buffer.observe(flushed)
            yield flushed
        error_event = serialize_sse(
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
        done_event = serialize_sse(
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
        buffer.observe(error_event)
        buffer.observe(done_event)
        yield error_event
        yield done_event
    finally:
        if conversation is not None:
            _persist_assistant_turn(
                db,
                conversation=conversation,
                buffer=buffer,
                last_decision=last_decision,
                last_config=last_config,
                chosen_model=chosen_model,
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
    execution = execute_tool_call(
        db,
        workspace=workspace,
        principal=principal,
        user=current_user,
        tool_name=command.tool_name,
        arguments=command.arguments,
        source="api.stream",
    )
    for event in iter_tool_call_events(encoder=encoder, execution=execution):
        yield serialize_sse(event)

    if execution.status == "blocked":
        message = (
            execution.error_message or f"도구 {command.tool_name} 실행에는 승인 절차가 필요합니다."
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

    if execution.status == "error":
        message = execution.error_message or "AI tool execution failed."
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

    assert execution.response is not None
    yield serialize_sse(
        make_envelope(
            "content_delta",
            encoder.next_seq(),
            {
                "text": render_tool_result_message(
                    execution.response["tool"],
                    execution.response["result"],
                ),
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
                "meta": _tool_done_meta(execution.response["tool"]),
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
    # `content` chunks are routed through the artifact parser in the
    # publisher loop, not this helper — see `_emit_content_through_parser`.
    if chunk.kind == "content":
        return None
    if chunk.kind == "reasoning" and chunk.text and reasoning_gate:
        return serialize_sse(
            make_envelope(
                "reasoning_delta",
                encoder.next_seq(),
                {"text": chunk.text},
            )
        )
    if chunk.kind == "usage" and chunk.usage:
        return serialize_sse(make_envelope("usage", encoder.next_seq(), chunk.usage))
    if chunk.kind == "tool_call_start" and chunk.tool_call_id and chunk.tool_name:
        return serialize_sse(
            make_envelope(
                "tool_call_started",
                encoder.next_seq(),
                {"call_id": chunk.tool_call_id, "name": chunk.tool_name},
            )
        )
    if chunk.kind == "tool_call_args" and chunk.tool_call_id and chunk.args_delta:
        return serialize_sse(
            make_envelope(
                "tool_call_args_delta",
                encoder.next_seq(),
                {"call_id": chunk.tool_call_id, "delta": chunk.args_delta},
            )
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


# ---------------------------------------------------------------------------
# Artifact parser emission helpers
# ---------------------------------------------------------------------------


def _parser_events_to_envelopes(
    parsed_events: list[Any],
    *,
    encoder: EnvelopeEncoder,
) -> list[dict[str, str]]:
    """Turn ArtifactStreamParser output into serialized SSE envelopes.

    Keeps the envelope construction in one place so both the agent and the
    direct chat paths emit identical wire shapes. Plain text outside artifacts
    is rewrapped as ``content_delta`` — it looks the same to the client as if
    the parser weren't in the pipeline at all.
    """
    envelopes: list[dict[str, str]] = []
    for parsed in parsed_events:
        if isinstance(parsed, ParsedText):
            if not parsed.text:
                continue
            envelopes.append(
                serialize_sse(
                    make_envelope(
                        "content_delta",
                        encoder.next_seq(),
                        {"text": parsed.text},
                    )
                )
            )
        elif isinstance(parsed, ParsedArtifactStart):
            envelopes.append(
                serialize_sse(
                    make_envelope(
                        "artifact_started",
                        encoder.next_seq(),
                        {
                            "artifact_id": parsed.artifact_id,
                            "artifact_type": parsed.attrs.get("type", "document"),
                            "title": parsed.attrs.get("title"),
                            "language": parsed.attrs.get("language"),
                        },
                    )
                )
            )
        elif isinstance(parsed, ParsedArtifactBody):
            if not parsed.text:
                continue
            envelopes.append(
                serialize_sse(
                    make_envelope(
                        "artifact_delta",
                        encoder.next_seq(),
                        {
                            "artifact_id": parsed.artifact_id,
                            "delta": parsed.text,
                        },
                    )
                )
            )
        elif isinstance(parsed, ParsedArtifactEnd):
            envelopes.append(
                serialize_sse(
                    make_envelope(
                        "artifact_completed",
                        encoder.next_seq(),
                        {"artifact_id": parsed.artifact_id},
                    )
                )
            )
    return envelopes


def _emit_content_through_parser(
    text: str,
    *,
    parser: ArtifactStreamParser,
    encoder: EnvelopeEncoder,
) -> list[dict[str, str]]:
    return _parser_events_to_envelopes(parser.feed(text), encoder=encoder)


def _flush_parser(
    parser: ArtifactStreamParser,
    *,
    encoder: EnvelopeEncoder,
) -> list[dict[str, str]]:
    return _parser_events_to_envelopes(parser.flush(), encoder=encoder)


# ---------------------------------------------------------------------------
# Conversation turn persistence helpers
# ---------------------------------------------------------------------------


def _resolve_requested_conversation(
    *,
    db: Session,
    workspace: Workspace,
    user: User,
    conversation_id: str | None,
) -> Conversation | None:
    if not conversation_id:
        return None
    return conversations_service.get_conversation(
        db,
        workspace=workspace,
        user=user,
        conversation_id=conversation_id,
    )


def _bind_conversation_for_stream(
    *,
    db: Session,
    workspace: Workspace,
    user: User,
    payload: "ChatStreamRequest",
) -> tuple[Conversation | None, list[dict[str, str]] | None]:
    """Resolve (or create) the Conversation row the stream will append to.

    Returns ``(conversation, None)`` on success, where ``conversation`` may be
    ``None`` when the caller hasn't opted into persistence yet. On a
    validation-style failure (client asked for an unknown/foreign
    ``conversation_id``) returns ``(None, [error_envelope, done_envelope])`` so
    the publisher yields the full terminal pair — the SSE contract requires
    every stream to close with a ``done`` envelope so clients leave the
    streaming state.
    """
    encoder_for_errors = EnvelopeEncoder()
    try:
        conversation = _resolve_requested_conversation(
            db=db,
            workspace=workspace,
            user=user,
            conversation_id=payload.conversation_id,
        )
    except HTTPException as exc:
        error_envelope = serialize_sse(
            make_envelope(
                "error",
                encoder_for_errors.next_seq(),
                {
                    "code": "conversation_not_found",
                    "message": exc.detail
                    if isinstance(exc.detail, str)
                    else "Conversation not found.",
                    "retryable": False,
                },
            )
        )
        done_envelope = serialize_sse(
            make_envelope(
                "done",
                encoder_for_errors.next_seq(),
                {
                    "finish_reason": "error",
                    "audit_id": None,
                    "meta": None,
                },
            )
        )
        return None, [error_envelope, done_envelope]
    if conversation is not None:
        return conversation, None

    if not payload.persist:
        # Legacy caller that hasn't flipped the opt-in flag yet — keep the
        # stream running but skip persistence. Phase 3.3 will set persist=True
        # on the web client so new user sessions get their own Conversation.
        return None, None

    conversation = conversations_service.create_conversation(
        db, workspace=workspace, user=user, title=""
    )
    return conversation, None


def _record_user_turn(
    *,
    db: Session,
    conversation: Conversation,
    messages: list[ChatMessage],
) -> None:
    """Persist the caller-supplied history onto the attached conversation.

    If the conversation is empty (just created) we persist every non-system
    turn in ``messages`` so the saved thread matches the exact context the
    model is about to see — a client that sent
    ``[user, assistant, user]`` on the first persisted request would
    otherwise reload with only the last turn. If the conversation already
    has turns we only store the new trailing user message; the earlier
    history is already on disk from prior requests.
    """
    non_system = [m for m in messages if m.role in ("user", "assistant")]
    if not non_system:
        return
    conversation_is_empty = len(conversation.turns) == 0
    if conversation_is_empty:
        first_user = next((m for m in non_system if m.role == "user"), None)
        if first_user is not None:
            conversations_service.autotitle_from_turn(
                db,
                conversation=conversation,
                first_user_content=first_user.content,
            )
        for message in non_system:
            conversations_service.append_turn(
                db,
                conversation=conversation,
                role=message.role,
                content=message.content,
            )
        return

    last_user_content: str | None = None
    for message in reversed(messages):
        if message.role == "user":
            last_user_content = message.content
            break
    if not last_user_content:
        return
    conversations_service.append_turn(
        db,
        conversation=conversation,
        role="user",
        content=last_user_content,
    )


def _persist_sync_chat_response(
    *,
    db: Session,
    workspace: Workspace,
    user: User,
    payload: ConversationBoundChatRequest,
    conversation: Conversation | None,
    buffer: "_AssistantTurnBuffer",
) -> str | None:
    if conversation is None and not payload.persist:
        return None

    bound_conversation = conversation
    if bound_conversation is None:
        bound_conversation = conversations_service.create_conversation(
            db, workspace=workspace, user=user, title=""
        )

    _record_user_turn(
        db=db,
        conversation=bound_conversation,
        messages=payload.messages,
    )
    _persist_assistant_turn(
        db,
        conversation=bound_conversation,
        buffer=buffer,
        last_decision=None,
        last_config=None,
        chosen_model=None,
    )
    return bound_conversation.id


@dataclass
class _AssistantTurnBuffer:
    """Accumulates streamed envelopes so we can persist a final assistant turn.

    Observes the already-serialized ``{event, data}`` dicts as they flow
    through the publisher — JSON-parsing the tiny ``data`` payloads is cheaper
    than refactoring every yield site to pass an envelope object. Tool call
    state is threaded across three event types (``tool_call_started`` →
    ``tool_call_args_delta`` → ``tool_result``) into one record per
    ``call_id`` so a reloaded turn can render the same cards the live UI did.
    Artifacts are threaded across ``artifact_started`` → ``artifact_delta`` →
    ``artifact_completed`` the same way so the reload path reopens the side
    panel with the original body.
    """

    content: str = ""
    reasoning: str = ""
    tool_call_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    tool_call_order: list[str] = field(default_factory=list)
    artifact_records: dict[str, dict[str, Any]] = field(default_factory=dict)
    artifact_order: list[str] = field(default_factory=list)
    pending_approvals: list[dict[str, Any]] = field(default_factory=list)
    done_meta: dict[str, Any] | None = None
    finish_reason: str | None = None
    response_status: str = "done"
    cancelled: bool = False
    # Captured from ``error`` envelopes so a stream that fails before any
    # content_delta still persists with the failure text the live UI showed
    # — MessageBubble reads ``content`` for all roles, so an empty-content
    # turn would reload as a blank bubble otherwise.
    error_message: str | None = None

    def _touch_tool_call(self, call_id: str) -> dict[str, Any]:
        # Mirrors the frontend ToolCallBuffer shape so a reloaded turn renders
        # the same tool card — `result` is a nested object with its own status
        # + preview + error, not top-level fields.
        if call_id not in self.tool_call_records:
            self.tool_call_order.append(call_id)
            self.tool_call_records[call_id] = {
                "call_id": call_id,
                "name": None,
                "args_preview": None,
                "argsBuffer": "",
                "status": "running",
                "result": None,
                "startedAtMs": None,
                "completedAtMs": None,
            }
        return self.tool_call_records[call_id]

    def _touch_artifact(self, artifact_id: str) -> dict[str, Any]:
        # Persisted artifact shape mirrors the client's ArtifactEntry: one
        # record per artifact_id collecting the full body text so reload
        # can re-open the side panel with the same content. ``language`` is
        # only set for ``type="code"`` artifacts — other types leave it
        # null and the client falls back to highlight.js auto-detection.
        if artifact_id not in self.artifact_records:
            self.artifact_order.append(artifact_id)
            self.artifact_records[artifact_id] = {
                "id": artifact_id,
                "type": "document",
                "title": None,
                "language": None,
                "content": "",
                "status": "open",
            }
        return self.artifact_records[artifact_id]

    @property
    def tool_calls(self) -> list[dict[str, Any]]:
        return [self.tool_call_records[call_id] for call_id in self.tool_call_order]

    @property
    def artifacts(self) -> list[dict[str, Any]]:
        return [self.artifact_records[artifact_id] for artifact_id in self.artifact_order]

    def observe(self, event_dict: dict[str, str]) -> None:
        # serialize_sse serialises the full envelope `{seq, timestamp_ms,
        # type, data: {...}}` into the SSE `data` field, so the interesting
        # payload we want to inspect sits at `envelope["data"]`.
        try:
            envelope = json.loads(event_dict.get("data", ""))
        except (ValueError, TypeError):
            return
        event_type = event_dict.get("event")
        payload = envelope.get("data") or {}
        timestamp_ms = envelope.get("timestamp_ms")
        if event_type == "content_delta":
            self.content += payload.get("text", "")
        elif event_type == "reasoning_delta":
            self.reasoning += payload.get("text", "")
        elif event_type == "tool_call_started":
            call_id = payload.get("call_id")
            if call_id:
                record = self._touch_tool_call(call_id)
                record["name"] = payload.get("name") or record["name"]
                record["args_preview"] = payload.get("args_preview") or record["args_preview"]
                if record["startedAtMs"] is None:
                    record["startedAtMs"] = timestamp_ms
        elif event_type == "tool_call_args_delta":
            call_id = payload.get("call_id")
            if call_id:
                record = self._touch_tool_call(call_id)
                record["argsBuffer"] += payload.get("delta", "")
        elif event_type == "tool_result":
            call_id = payload.get("call_id")
            if call_id:
                record = self._touch_tool_call(call_id)
                status = payload.get("status") or record["status"]
                record["status"] = status
                record["result"] = {
                    "status": status,
                    "preview": payload.get("result_preview"),
                    "error": payload.get("error"),
                }
                record["completedAtMs"] = timestamp_ms
        elif event_type == "approval_required":
            self.pending_approvals.append(payload)
        elif event_type == "artifact_started":
            artifact_id = payload.get("artifact_id")
            if artifact_id:
                record = self._touch_artifact(artifact_id)
                record["type"] = payload.get("artifact_type") or record["type"]
                record["title"] = payload.get("title") or record["title"]
                # ``language`` is an optional code-artifact hint; only
                # overwrite when the envelope actually carries a value.
                language = payload.get("language")
                if language:
                    record["language"] = language
        elif event_type == "artifact_delta":
            artifact_id = payload.get("artifact_id")
            if artifact_id:
                record = self._touch_artifact(artifact_id)
                record["content"] += payload.get("delta", "")
        elif event_type == "artifact_completed":
            artifact_id = payload.get("artifact_id")
            if artifact_id:
                record = self._touch_artifact(artifact_id)
                record["status"] = "closed"
        elif event_type == "error":
            message = payload.get("message")
            if isinstance(message, str) and message.strip():
                self.error_message = message
        elif event_type == "done":
            self.done_meta = payload.get("meta") or {}
            self.finish_reason = payload.get("finish_reason")
            if self.finish_reason == "error":
                self.response_status = "error"


_SYNC_FINISH_REASONS = {"stop", "length", "cancelled", "error"}


def _assistant_buffer_from_sync_response(
    response: ChatResponse,
    *,
    parse_artifacts: bool = True,
    tool_execution: ToolCallExecution | None = None,
) -> _AssistantTurnBuffer:
    buffer = _AssistantTurnBuffer(
        done_meta={
            "policy": response.policy,
            "chosen_pool": response.chosen_pool,
            "decision_reason": response.decision_reason,
            "forced_local": response.forced_local,
            "pii_hits": list(response.pii_hits),
            "model": response.model,
            "chosen_model": response.model,
            "canonical_model": response.canonical_model,
            "provider": response.provider,
        },
        finish_reason=(
            response.finish_reason if response.finish_reason in _SYNC_FINISH_REASONS else None
        ),
        response_status="error" if response.finish_reason == "error" else "done",
    )
    if not parse_artifacts:
        # Tool-command responses go straight into ``content`` without
        # re-parsing — the caller already knows the payload is serialized
        # tool output, not model prose that might embed ``<artifact>``.
        # When the caller hands us the underlying ToolCallExecution, feed
        # synthetic ``tool_call_started`` / ``tool_result`` envelopes
        # through the buffer so the persisted turn ships the same
        # ``tool_calls`` metadata the streaming transport records.
        if tool_execution is not None:
            encoder = EnvelopeEncoder()
            for event in iter_tool_call_events(encoder=encoder, execution=tool_execution):
                buffer.observe(serialize_sse(event))
        buffer.content = response.content or ""
        return buffer
    parser = ArtifactStreamParser()
    encoder = EnvelopeEncoder()
    for event in _emit_content_through_parser(
        response.content or "",
        parser=parser,
        encoder=encoder,
    ):
        buffer.observe(event)
    for event in _flush_parser(parser, encoder=encoder):
        buffer.observe(event)
    return buffer


def _persist_assistant_turn(
    db: Session,
    *,
    conversation: Conversation,
    buffer: _AssistantTurnBuffer,
    last_decision: PolicyDecision | None,
    last_config: LlmPoolConfig | None,
    chosen_model: str | None,
) -> None:
    """Write a single assistant turn summarizing the streamed response.

    Runs from the publisher's ``finally`` so the row lands on every exit
    path — normal completion, mid-stream error, and client cancellation.
    Empty streams still get persisted when the finish reason was terminal
    (error/cancelled) so the reloaded conversation reflects that the live
    UI showed a failure response rather than an absent assistant turn.
    """
    response_status = "cancelled" if buffer.cancelled else buffer.response_status
    has_body = bool(
        buffer.content
        or buffer.reasoning
        or buffer.tool_calls
        or buffer.pending_approvals
        # Artifact-only responses (the model emitted only an <artifact> block
        # with no surrounding summary) still need persistence so reload
        # restores the generated document.
        or buffer.artifacts
    )
    # A terminal failure OR a length-limited reply should still persist even
    # with an empty body — the live UI renders a "token limit reached" /
    # error bubble in those cases, so a reloaded conversation must show the
    # same assistant turn rather than look unanswered.
    is_terminal_failure = response_status in {"cancelled", "error"} or (
        buffer.finish_reason in {"cancelled", "error", "length"}
    )
    if not has_body and not is_terminal_failure:
        return

    # Fall back to the streamed error text when the provider failed before
    # any content_delta — MessageBubble renders `content` for every role, so
    # an empty assistant turn would reload as a blank bubble otherwise.
    persisted_content = buffer.content
    if not persisted_content and buffer.error_message:
        persisted_content = buffer.error_message

    fallback_meta = _build_done_meta(last_decision, last_config, model=chosen_model)
    done_meta = buffer.done_meta or fallback_meta or {}

    # Propagate the stream's terminal state onto the reasoning panel too so
    # reloaded threads don't falsely show a completed ThinkingPanel after an
    # error or cancellation. MessageBubble treats a missing field as "done",
    # which would misrepresent the live behavior.
    reasoning_status = response_status if buffer.reasoning and response_status != "done" else None

    meta: dict[str, Any] = {
        "reasoning": buffer.reasoning or None,
        "reasoning_status": reasoning_status,
        "policy": done_meta.get("policy"),
        "chosen_pool": done_meta.get("chosen_pool"),
        "decision_reason": done_meta.get("decision_reason"),
        "forced_local": done_meta.get("forced_local"),
        "pii_hits": done_meta.get("pii_hits") or [],
        "provider": done_meta.get("provider"),
        "finish_reason": buffer.finish_reason,
        "response_status": response_status,
        "tool_calls": buffer.tool_calls,
        "pending_approvals": buffer.pending_approvals,
        "artifacts": buffer.artifacts,
    }
    # Drop None values so the persisted JSON isn't noisy with defaults.
    meta = {key: value for key, value in meta.items() if value not in (None, [], "")}

    try:
        conversations_service.append_turn(
            db,
            conversation=conversation,
            role="assistant",
            content=persisted_content,
            meta=meta or None,
        )
    except Exception as exc:  # noqa: BLE001 - persistence failure must not crash the stream
        # The stream has already delivered its terminal done/error envelope
        # to the client, so failing to persist history shouldn't rewrite
        # that contract — log and roll back instead of raising.
        import logging

        logging.getLogger(__name__).exception(
            "conversation turn persistence failed conversation_id=%s: %s",
            conversation.id,
            exc,
        )
        db.rollback()
