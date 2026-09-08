import asyncio
import json
from dataclasses import replace
from datetime import datetime
from typing import Any, Literal, cast

from fastapi import APIRouter, Depends, HTTPException, Query, Request, status
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.orm import Session
from sse_starlette.sse import EventSourceResponse

from open_work_hub_api.core.db import get_db_session
from open_work_hub_api.core.i18n import (
    LocalizedApiMessage,
    localized_http_exception,
    select_locale,
    translate_message,
)
from open_work_hub_api.core.llm import (
    LlmModelConfigurationError,
    LlmPoolConfig,
    LlmPoolName,
    LlmProviderError,
    LlmTaskContext,
    PolicyDecision,
)
from open_work_hub_api.core.llm_execution_adapters import supports_tool_calling
from open_work_hub_api.core.principal import CallerPrincipal, user_principal
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai import approvals as ai_approvals
from open_work_hub_api.domains.ai.agent import (
    AGENT_SYSTEM_PROMPT,
    resume_agent_run,
    run_agent_turn_stream,
)
from open_work_hub_api.domains.ai.artifact_parser import ArtifactStreamParser
from open_work_hub_api.domains.ai.artifact_stream_envelopes import (
    emit_content_through_parser,
    flush_parser,
    serialize_agent_event_through_artifacts,
)
from open_work_hub_api.domains.ai.assistant_turns import (
    AssistantTurnBuffer,
    assistant_buffer_from_sync_response,
    build_assistant_turn_record,
)
from open_work_hub_api.domains.ai.audit import log_llm_tool_approval_resolved
from open_work_hub_api.domains.ai.chat_context_policy import (
    normalize_business_chat_allowed_app_ids,
)
from open_work_hub_api.domains.ai.chat_stream_envelopes import (
    build_done_meta as _build_done_meta,
)
from open_work_hub_api.domains.ai.chat_stream_envelopes import (
    chunk_to_envelope as _chunk_to_envelope,
)
from open_work_hub_api.domains.ai.conversation_binding import (
    complete_live_conversation_run as _complete_live_conversation_run,
)
from open_work_hub_api.domains.ai.conversation_binding import (
    record_user_turn as _record_user_turn,
)
from open_work_hub_api.domains.ai.conversation_binding import (
    resolve_requested_conversation as _resolve_requested_conversation,
)
from open_work_hub_api.domains.ai.conversation_binding import (
    start_live_conversation_run as _start_live_conversation_run,
)
from open_work_hub_api.domains.ai.conversation_scope import (
    conversation_scope_server_owned_artifact_types,
    conversation_scope_turn_context,
    messages_with_scope_prompt,
    validate_requested_conversation_scope,
)
from open_work_hub_api.domains.ai.events import (
    EnvelopeEncoder,
    make_envelope,
    serialize_sse,
)
from open_work_hub_api.domains.ai.gateway import (
    AiGatewayPolicyViolation,
    AiGatewayRequest,
    LlmWorkloadContext,
    build_llm_workload_request,
    complete_gateway_chat,
    complete_resolved_gateway_chat_stream,
    resolve_gateway_execution,
)
from open_work_hub_api.domains.ai.mcp import AiMcpClient
from open_work_hub_api.domains.ai.registry import (
    get_ai_capability_registry,
    get_chatbot_capable_app_ids,
    resolve_llm_workload,
)
from open_work_hub_api.domains.ai.runtime.agent_definitions import resolve_agent_definitions
from open_work_hub_api.domains.ai.runtime.external_egress import (
    ExternalCapability,
    evaluate_external_egress,
)
from open_work_hub_api.domains.ai.runtime.external_trace import (
    external_planner_trace_summaries,
    external_search_trace_summaries,
)
from open_work_hub_api.domains.ai.runtime.graph_execution import (
    attach_graph_execution_adapter_decision,
)
from open_work_hub_api.domains.ai.runtime.graph_scheduler import (
    GraphSchedulerError,
    build_graph_execution_schedule,
    summarize_graph_execution_schedule,
    summarize_graph_schedule_failure,
)
from open_work_hub_api.domains.ai.runtime.graph_stream import (
    attach_graph_execution_adapter_error_summary,
    run_graph_execution_adapter_stream,
    should_use_graph_execution_adapter,
)
from open_work_hub_api.domains.ai.runtime.inspection_projection import (
    RuntimeRunInspectionResponse,
    runtime_run_inspection_response,
)
from open_work_hub_api.domains.ai.runtime.manager_candidate import (
    build_deterministic_manager_candidate,
    summarize_execution_graph,
)
from open_work_hub_api.domains.ai.runtime.manager_validation import ManagerGraphValidator
from open_work_hub_api.domains.ai.runtime.metrics import (
    record_inspection_request,
)
from open_work_hub_api.domains.ai.runtime.models import AgentInvocation, AgentRun, AgentTraceEvent
from open_work_hub_api.domains.ai.runtime.persistence import (
    persist_graph_execution_runtime_shadow,
    persist_single_loop_fallback_runtime_shadow,
)
from open_work_hub_api.domains.ai.runtime.routing import (
    RuntimeRoutingDecision,
    attach_manager_graph_validation_result,
    attach_trace_only_graph_validation,
    select_runtime_profile,
)
from open_work_hub_api.domains.ai.runtime.routing_metadata import (
    runtime_routing_stream_kwargs,
)
from open_work_hub_api.domains.ai.runtime.tool_calling import stream_tool_calling_enabled
from open_work_hub_api.domains.ai.runtime_status import inspect_registered_llm_runtime
from open_work_hub_api.domains.ai.tool_contracts import AgentToolSpec
from open_work_hub_api.domains.ai.tool_pipeline import (
    ToolChatCommand,
    ToolChatCommandError,
    build_tool_chat_response_payload,
    execute_tool_chat_command_sse_events,
    parse_tool_chat_command,
)
from open_work_hub_api.domains.ai.tool_pipeline import (
    execute_tool_chat_command as run_tool_chat_command,
)
from open_work_hub_api.domains.ai.tool_runtime import ToolCallExecution
from open_work_hub_api.domains.ai.tool_service import (
    ToolRequiresApproval,
    approval_required_http_exception,
)
from open_work_hub_api.domains.ai.tool_service import (
    execute_tool as execute_ai_tool,
)
from open_work_hub_api.domains.ai.tool_surface import (
    AgentToolSurface,
    owner_app_id_for_tool,
    resolve_agent_tool_surface,
)
from open_work_hub_api.domains.auth.app_availability import resolve_company_enabled_app_ids
from open_work_hub_api.domains.auth.app_catalog import get_app_catalog_item
from open_work_hub_api.domains.auth.app_gate import can_use_app
from open_work_hub_api.domains.auth.dependencies import require_current_user
from open_work_hub_api.domains.auth.models import User
from open_work_hub_api.domains.auth.security import new_id
from open_work_hub_api.domains.conversations import service as conversations_service
from open_work_hub_api.domains.conversations.app_catalog import CHATBOT_APP
from open_work_hub_api.domains.conversations.default_scope_adapters import (
    ensure_conversation_scope_adapters_registered,
)
from open_work_hub_api.domains.conversations.models import Conversation
from open_work_hub_api.domains.conversations.projections import (
    conversation_detail_from_row,
    conversation_summary_from_row,
)
from open_work_hub_api.domains.conversations.schemas import (
    ConversationCreateRequest,
    ConversationDetail,
    ConversationListResponse,
    ConversationUpdateRequest,
)
from open_work_hub_api.domains.conversations.scope_contract import (
    SCOPE_REF_MAX_LEN,
    SCOPE_RESOURCE_ID_MAX_LEN,
)
from open_work_hub_api.domains.conversations.scope_registry import (
    ConversationExperience,
    ConversationScopeArtifact,
    ConversationScopeTurnContext,
    conversation_scope_adapters,
    get_conversation_scope_adapter,
)

LlmRequestBackendMode = Literal["auto", "local"]


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
    external_providers: list[LlmPoolHealthResponse] = Field(default_factory=list)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant"]
    content: str = Field(..., min_length=1)


class ChatRequest(BaseModel):
    messages: list[ChatMessage] = Field(..., min_length=1)
    model: str | None = None
    backend_mode: LlmRequestBackendMode = "auto"
    external_provider: str | None = None
    temperature: float = Field(default=0.2, ge=0, le=2)
    max_tokens: int | None = Field(default=None, ge=1, le=262144)
    reasoning_effort: Literal["none", "low", "medium", "high"] | None = None
    # User-selected tool-owner apps the business chatbot may invoke. The server
    # intersects this scope with registered, enabled, and discoverable apps.
    allowed_app_ids: list[str] | None = None

    @field_validator("allowed_app_ids")
    @classmethod
    def _validate_allowed_app_ids(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_allowed_app_ids(value)


class ConversationBoundChatRequest(ChatRequest):
    # If set, append to the named conversation (must belong to the caller).
    conversation_id: str | None = None
    # Optional scope for a newly persisted conversation. Existing
    # conversations keep their stored scope and reject mismatched payloads.
    scope_ref: str | None = Field(default=None, max_length=SCOPE_REF_MAX_LEN)
    scope_resource_id: str | None = Field(
        default=None,
        max_length=SCOPE_RESOURCE_ID_MAX_LEN,
    )
    # Opt-in flag to have the server allocate a fresh conversation row when
    # ``conversation_id`` is absent. Defaults to False so legacy callers
    # don't silently fragment their history into one-turn conversations.
    persist: bool = False
    # Claude-style edit/retry support: when set, delete all turns from this
    # sequence onward before appending the current request's new turn/response.
    replace_from_seq: int | None = Field(default=None, ge=0)
    # Optimistic version check for the exact persisted turn being edited or
    # retried. Required whenever ``replace_from_seq`` is present.
    replace_from_turn_id: str | None = None
    # Optimistic version check for the tail the client had loaded when it
    # chose to rewrite. Prevents a stale tab from deleting newer turns that
    # were appended after its local copy was rendered.
    replace_tail_seq: int | None = Field(default=None, ge=0)
    replace_tail_turn_id: str | None = None
    # Retry reuses the existing trailing user turn after truncating an assistant
    # response, so it must not append another copy of the same user prompt.
    persist_user_turn: bool = True


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


router = APIRouter(prefix="/chatbot", tags=["chatbot"])

DEFAULT_CHATBOT_CONVERSATION_EXPERIENCE = ConversationExperience(
    owner_app_id=CHATBOT_APP.app_id,
    chat_workload_id="chatbot",
)


def _resolve_conversation_experience(
    scope_ref: str | None,
    *,
    allow_retired_scope: bool = False,
) -> ConversationExperience:
    normalized_scope_ref = (scope_ref or "").strip()
    if not normalized_scope_ref:
        return DEFAULT_CHATBOT_CONVERSATION_EXPERIENCE
    ensure_conversation_scope_adapters_registered()
    adapter = get_conversation_scope_adapter(normalized_scope_ref)
    if adapter is None:
        if allow_retired_scope:
            # Legacy rows can contain retired scope refs. Keep them behind the
            # standalone chatbot hard gate instead of granting an unknown owner.
            return DEFAULT_CHATBOT_CONVERSATION_EXPERIENCE
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.unsupported_conversation_scope",
            scope_ref=normalized_scope_ref,
        )
    return adapter.experience


def _require_conversation_experience_enabled(
    db: Session,
    user: User,
    *,
    scope_ref: str | None,
    allow_retired_scope: bool = False,
) -> ConversationExperience:
    experience = _resolve_conversation_experience(
        scope_ref,
        allow_retired_scope=allow_retired_scope,
    )
    if can_use_app(db, user_id=user.id, app_id=experience.owner_app_id):
        return experience
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="app.access_required",
    )


def _require_conversation_chat_workload(
    experience: ConversationExperience,
    *,
    scope_ref: str | None,
) -> None:
    if experience.chat_workload_id is not None:
        return
    raise localized_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="ai.unsupported_conversation_scope",
        scope_ref=(scope_ref or ""),
    )


def _require_conversation_persistence(
    experience: ConversationExperience,
    *,
    conversation: Conversation | None,
    persist: bool,
) -> None:
    if not experience.requires_persistence or conversation is not None or persist:
        return
    raise localized_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="ai.conversation_persistence_required",
    )


def _constrain_conversation_tool_app_ids(
    experience: ConversationExperience,
    requested_app_ids: list[str] | None,
) -> list[str] | None:
    if experience.allowed_tool_app_ids is None:
        return requested_app_ids
    return list(experience.allowed_tool_app_ids)


def _enabled_conversation_scope_refs(
    db: Session,
    user: User,
) -> frozenset[str]:
    ensure_conversation_scope_adapters_registered()
    return frozenset(
        adapter.scope_ref
        for adapter in conversation_scope_adapters()
        if can_use_app(db, user_id=user.id, app_id=adapter.experience.owner_app_id)
    )


def require_requested_app_access(
    app_id: str,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> None:
    """Gate app-scoped capability exports against the requested registry app."""
    _ensure_known_app(app_id)
    if can_use_app(db, user_id=current_user.id, app_id=app_id):
        return
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="app.access_required",
    )


def _business_chat_system_prompt(scope_system_prompt: str | None = None) -> str:
    scope_prompt = (scope_system_prompt or "").strip()
    if not scope_prompt:
        return AGENT_SYSTEM_PROMPT
    return f"{AGENT_SYSTEM_PROMPT}\n\n{scope_prompt}"


def _messages_with_business_chat_prompt(
    messages: list[dict[str, Any]],
    *,
    scope_system_prompt: str | None,
) -> list[dict[str, Any]]:
    return messages_with_scope_prompt(
        messages,
        scope_system_prompt=_business_chat_system_prompt(scope_system_prompt),
    )


@router.get("/capabilities/manifest")
def capability_manifest(
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> dict[str, Any]:
    _ensure_mcp_bridge_enabled()
    settings = get_settings()
    principal = _build_request_principal(
        current_user,
        request,
        source="api.chatbot.capabilities.manifest",
    )
    return AiMcpClient().build_manifest(
        db,
        principal=principal,
        include_meta=True,
        include_approval_required=settings.ai_write_tools_enabled,
    )


@router.get(
    "/apps/{app_id}/manifest",
    dependencies=[Depends(require_requested_app_access)],
)
def app_capability_manifest(
    app_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> dict[str, Any]:
    _ensure_mcp_bridge_enabled()
    _ensure_known_app(app_id)
    settings = get_settings()
    principal = _build_request_principal(
        current_user,
        request,
        source=f"api.chatbot.apps.{app_id}.manifest",
    )
    return AiMcpClient().build_manifest(
        db,
        principal=principal,
        app_id=app_id,
        include_meta=True,
        include_approval_required=settings.ai_write_tools_enabled,
    )


@router.get("/capabilities/openapi.json")
def capability_openapi_export(
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> dict[str, Any]:
    _ensure_mcp_bridge_enabled()
    settings = get_settings()
    principal = _build_request_principal(
        current_user,
        request,
        source="api.chatbot.capabilities.openapi",
    )
    return AiMcpClient().build_openapi_export(
        db,
        principal=principal,
        include_approval_required=settings.ai_write_tools_enabled,
    )


@router.get(
    "/apps/{app_id}/openapi.json",
    dependencies=[Depends(require_requested_app_access)],
)
def app_capability_openapi_export(
    app_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> dict[str, Any]:
    _ensure_mcp_bridge_enabled()
    _ensure_known_app(app_id)
    settings = get_settings()
    principal = _build_request_principal(
        current_user,
        request,
        source=f"api.chatbot.apps.{app_id}.openapi",
    )
    return AiMcpClient().build_openapi_export(
        db,
        principal=principal,
        app_id=app_id,
        include_approval_required=settings.ai_write_tools_enabled,
    )


@router.get("/health", response_model=LlmDualHealthResponse)
def ai_health(
    request: Request,
    db: Session = Depends(get_db_session),
) -> LlmDualHealthResponse:
    """Pool-scoped AI readiness. Each pool's status is reported independently;
    overall ``ready`` is true if at least one pool is usable. Routing decisions
    are still policy-driven, not fallback-driven.
    """
    locale = select_locale(
        explicit_locale=request.headers.get("x-open-work-hub-locale"),
        accept_language=request.headers.get("accept-language"),
    )
    runtime = inspect_registered_llm_runtime(db, probe="live")
    return LlmDualHealthResponse.model_validate(runtime.pools.public_dict(locale=locale))


@router.post(
    "/chat",
    response_model=ChatResponse,
)
def chat(
    payload: ConversationBoundChatRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ChatResponse:
    _prepare_business_chat_request(payload)
    _ensure_supported_backend_mode(payload.backend_mode)
    locale = select_locale(
        explicit_locale=request.headers.get("x-open-work-hub-locale"),
        accept_language=request.headers.get("accept-language"),
    )
    principal = _build_request_principal(current_user, request, source="api.chat")
    conversation = _resolve_requested_conversation(
        db=db,
        user=current_user,
        conversation_id=payload.conversation_id,
    )
    experience = _require_conversation_experience_enabled(
        db,
        current_user,
        scope_ref=conversation.scope_ref if conversation is not None else payload.scope_ref,
        allow_retired_scope=conversation is not None,
    )
    _require_conversation_chat_workload(
        experience,
        scope_ref=conversation.scope_ref if conversation is not None else payload.scope_ref,
    )
    _require_conversation_persistence(
        experience,
        conversation=conversation,
        persist=payload.persist,
    )
    payload.allowed_app_ids = _constrain_conversation_tool_app_ids(
        experience,
        payload.allowed_app_ids,
    )
    if experience.execution_mode == "durable_background":
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.durable_stream_required",
        )
    conversation = _apply_conversation_rewrite_if_requested(
        db=db,
        user=current_user,
        conversation=conversation,
        payload=payload,
    )
    if conversation is not None:
        _ensure_payload_scope_matches_conversation(conversation, payload)
    elif payload.persist:
        validate_requested_conversation_scope(
            db,
            principal=principal,
            user=current_user,
            scope_ref=payload.scope_ref,
            scope_resource_id=payload.scope_resource_id,
        )
        conversation = conversations_service.create_conversation(
            db,
            user=current_user,
            title="",
            scope_ref=payload.scope_ref,
            scope_resource_id=payload.scope_resource_id,
        )
    live_run_lock = _start_live_conversation_run(
        db=db,
        user=current_user,
        conversation=conversation,
    )
    try:
        command = _parse_tool_chat_command(payload.messages)
        is_tool_command_response = command is not None
        tool_execution: ToolCallExecution | None = None
        scope_artifacts: tuple[ConversationScopeArtifact, ...] = ()
        scope_context: ConversationScopeTurnContext | None = None
        if is_tool_command_response:
            response, tool_execution = _execute_tool_chat_command(
                payload,
                db,
                principal=principal,
                current_user=current_user,
                command=command,
            )
        else:
            raw_messages_dict = [message.model_dump() for message in payload.messages]
            scope_context = conversation_scope_turn_context(
                db,
                principal=principal,
                user=current_user,
                conversation=conversation,
                messages=raw_messages_dict,
            )
            scope_artifacts = scope_context.artifacts
            if scope_context.direct_response is not None:
                response = _scope_direct_chat_response(
                    scope_context.direct_response,
                    requested_backend_mode=payload.backend_mode,
                )
            else:
                messages_dict = _messages_with_business_chat_prompt(
                    raw_messages_dict,
                    scope_system_prompt=scope_context.prompt,
                )
                context = _task_context_from_principal(principal, experience=experience)
                try:
                    response = _complete_via_policy(
                        context,
                        payload,
                        db,
                        messages=messages_dict,
                    )
                except Exception as error:
                    if payload.replace_from_seq is None or conversation is None:
                        raise
                    response = _build_sync_error_response(
                        payload,
                        error,
                        locale=locale,
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
            sync_buffer = assistant_buffer_from_sync_response(
                response,
                parse_artifacts=False,
                tool_execution=tool_execution,
            )
        else:
            assert scope_context is not None
            sync_buffer = assistant_buffer_from_sync_response(
                response,
                server_owned_artifact_types=scope_context.server_owned_artifact_types,
            )
            _append_scope_artifacts_to_buffer(sync_buffer, scope_artifacts)
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
                user=current_user,
                payload=payload,
                conversation=conversation,
                buffer=sync_buffer,
                assistant_turn_persisted=bool(
                    scope_context and scope_context.assistant_turn_persisted
                ),
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
    finally:
        _complete_live_conversation_run(db, live_run_lock)


class ChatStreamRequest(ConversationBoundChatRequest):
    stream_reasoning: bool = True


class ApprovalResolveRequest(BaseModel):
    decision: Literal["approved", "rejected"]
    reason: str | None = None


class ApprovalAbandonRequest(BaseModel):
    reason: str | None = None


class ApprovalStatusResponse(BaseModel):
    id: str
    conversation_id: str
    agent_run_id: str
    tool_call_id: str
    tool_name: str
    arguments_json: str
    resource_preview: str | None = None
    status: str
    requested_by_user_id: str
    resolved_by_user_id: str | None = None
    reject_reason: str | None = None
    resolved_at: datetime | None = None
    expires_at: datetime
    execution_result_json: Any | None = None
    error_message: str | None = None
    created_at: datetime
    snapshot_status: str | None = None


class ChatResumeRequest(BaseModel):
    conversation_id: str
    approval_id: str
    # Mirrors ``ChatRequest.allowed_app_ids``. If omitted, resume uses the
    # scope frozen when the approval was requested. If provided, it must be
    # equal to or narrower than that frozen scope.
    allowed_app_ids: list[str] | None = None

    @field_validator("allowed_app_ids")
    @classmethod
    def _validate_allowed_app_ids(cls, value: list[str] | None) -> list[str] | None:
        return _normalize_allowed_app_ids(value)


@router.get(
    "/conversations",
    response_model=ConversationListResponse,
)
def list_ai_conversations(
    request: Request,
    limit: int = Query(default=20, ge=1, le=100),
    cursor: str | None = Query(default=None),
    scope_ref: str | None = Query(default=None, max_length=SCOPE_REF_MAX_LEN),
    scope_resource_id: str | None = Query(
        default=None,
        max_length=SCOPE_RESOURCE_ID_MAX_LEN,
    ),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ConversationListResponse:
    _require_conversation_experience_enabled(db, current_user, scope_ref=scope_ref)
    rows, next_cursor = conversations_service.list_conversations(
        db,
        user=current_user,
        limit=limit,
        cursor=cursor,
        scope_ref=scope_ref,
        scope_resource_id=scope_resource_id,
        allowed_scope_refs=(
            _enabled_conversation_scope_refs(db, current_user) if scope_ref is None else None
        ),
    )
    return ConversationListResponse(
        items=[conversation_summary_from_row(row) for row in rows],
        next_cursor=next_cursor,
    )


@router.post(
    "/conversations",
    response_model=ConversationDetail,
    status_code=status.HTTP_201_CREATED,
)
def create_ai_conversation(
    payload: ConversationCreateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ConversationDetail:
    _require_conversation_experience_enabled(db, current_user, scope_ref=payload.scope_ref)
    principal = _build_request_principal(
        current_user,
        request,
        source="api.chatbot.conversations.create",
    )
    validate_requested_conversation_scope(
        db,
        principal=principal,
        user=current_user,
        scope_ref=payload.scope_ref,
        scope_resource_id=payload.scope_resource_id,
    )
    conversation = conversations_service.create_conversation(
        db,
        user=current_user,
        title=payload.title,
        scope_ref=payload.scope_ref,
        scope_resource_id=payload.scope_resource_id,
    )
    return conversation_detail_from_row(conversation)


@router.get(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
)
def get_ai_conversation(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ConversationDetail:
    conversation = conversations_service.get_conversation(
        db,
        user=current_user,
        conversation_id=conversation_id,
    )
    _require_conversation_experience_enabled(
        db,
        current_user,
        scope_ref=conversation.scope_ref,
        allow_retired_scope=True,
    )
    live_pending_approval = ai_approvals.get_live_pending_approval(
        db,
        user=current_user,
        conversation_id=conversation_id,
    )
    return conversation_detail_from_row(
        conversation,
        live_pending_approval=live_pending_approval,
    )


@router.patch(
    "/conversations/{conversation_id}",
    response_model=ConversationDetail,
)
def rename_ai_conversation(
    conversation_id: str,
    payload: ConversationUpdateRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ConversationDetail:
    existing = conversations_service.get_conversation(
        db,
        user=current_user,
        conversation_id=conversation_id,
    )
    _require_conversation_experience_enabled(
        db,
        current_user,
        scope_ref=existing.scope_ref,
        allow_retired_scope=True,
    )
    conversation = conversations_service.rename_conversation(
        db,
        user=current_user,
        conversation_id=conversation_id,
        title=payload.title,
    )
    return conversation_detail_from_row(conversation)


@router.delete(
    "/conversations/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
)
def delete_ai_conversation(
    conversation_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> None:
    existing = conversations_service.get_conversation(
        db,
        user=current_user,
        conversation_id=conversation_id,
    )
    _require_conversation_experience_enabled(
        db,
        current_user,
        scope_ref=existing.scope_ref,
        allow_retired_scope=True,
    )
    conversations_service.soft_delete_conversation(
        db,
        user=current_user,
        conversation_id=conversation_id,
    )


@router.post("/chat/stream")
async def chat_stream(
    payload: ChatStreamRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> EventSourceResponse:
    """Agent-aware SSE stream.

    Wire protocol is documented in
    ``apps/api/src/open_work_hub_api/domains/ai/events_schema.md``. HTTP status is
    always 200 once the stream opens — failures surface as ``error`` +
    ``done(finish_reason=error)`` envelopes.
    """
    _prepare_business_chat_request(payload)
    _ensure_supported_backend_mode(payload.backend_mode)
    principal = _build_request_principal(current_user, request, source="api.stream")
    try:
        requested_conversation = _resolve_requested_conversation(
            db=db,
            user=current_user,
            conversation_id=payload.conversation_id,
        )
    except HTTPException as exc:
        if exc.status_code != status.HTTP_404_NOT_FOUND:
            raise
        # Keep the established SSE contract for missing conversations: the
        # publisher emits error + done after the HTTP 200 stream opens.
        requested_conversation = None
    experience = _require_conversation_experience_enabled(
        db,
        current_user,
        scope_ref=(
            requested_conversation.scope_ref
            if requested_conversation is not None
            else payload.scope_ref
        ),
        allow_retired_scope=requested_conversation is not None,
    )
    _require_conversation_chat_workload(
        experience,
        scope_ref=(
            requested_conversation.scope_ref
            if requested_conversation is not None
            else payload.scope_ref
        ),
    )
    _require_conversation_persistence(
        experience,
        conversation=requested_conversation,
        persist=payload.persist,
    )
    payload.allowed_app_ids = _constrain_conversation_tool_app_ids(
        experience,
        payload.allowed_app_ids,
    )
    context = _task_context_from_principal(principal, experience=experience)
    locale = select_locale(
        explicit_locale=request.headers.get("x-open-work-hub-locale"),
        accept_language=request.headers.get("accept-language"),
    )
    return EventSourceResponse(
        _chat_stream_publisher(
            payload=payload,
            db=db,
            context=context,
            principal=principal,
            current_user=current_user,
            locale=locale,
        ),
        ping=25,
    )


@router.get("/approvals/{approval_id}", response_model=ApprovalStatusResponse)
def get_approval_status(
    approval_id: str,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ApprovalStatusResponse:
    approval = ai_approvals.get_approval(
        db,
        user=current_user,
        approval_id=approval_id,
    )
    snapshot = ai_approvals.load_snapshot(db, agent_run_id=approval.agent_run_id)
    return ApprovalStatusResponse.model_validate(
        ai_approvals.approval_to_payload(approval, snapshot=snapshot)
    )


@router.post("/approvals/{approval_id}/resolve", response_model=ApprovalStatusResponse)
def resolve_approval(
    approval_id: str,
    payload: ApprovalResolveRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ApprovalStatusResponse:
    approval = ai_approvals.resolve_approval(
        db,
        approval_id=approval_id,
        decision=payload.decision,
        reason=payload.reason,
        resolver_user=current_user,
    )
    db.commit()
    if approval.resolved_at is not None:
        elapsed_since_request_ms = max(
            0,
            int((approval.resolved_at - approval.created_at).total_seconds() * 1000),
        )
        log_llm_tool_approval_resolved(
            actor_user_id=current_user.id,
            approval_id=approval.id,
            tool_name=approval.tool_name,
            decision=approval.status,
            resolver_user_id=current_user.id,
            elapsed_since_request_ms=elapsed_since_request_ms,
        )
    snapshot = ai_approvals.load_snapshot(db, agent_run_id=approval.agent_run_id)
    return ApprovalStatusResponse.model_validate(
        ai_approvals.approval_to_payload(approval, snapshot=snapshot)
    )


@router.post("/approvals/{approval_id}/abandon", response_model=ApprovalStatusResponse)
def abandon_approval(
    approval_id: str,
    payload: ApprovalAbandonRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> ApprovalStatusResponse:
    approval = ai_approvals.abandon_approval(
        db,
        approval_id=approval_id,
        reason=payload.reason,
        resolver_user=current_user,
    )
    db.commit()
    if approval.resolved_at is not None:
        elapsed_since_request_ms = max(
            0,
            int((approval.resolved_at - approval.created_at).total_seconds() * 1000),
        )
        log_llm_tool_approval_resolved(
            actor_user_id=current_user.id,
            approval_id=approval.id,
            tool_name=approval.tool_name,
            decision=approval.status,
            resolver_user_id=current_user.id,
            elapsed_since_request_ms=elapsed_since_request_ms,
        )
    snapshot = ai_approvals.load_snapshot(db, agent_run_id=approval.agent_run_id)
    return ApprovalStatusResponse.model_validate(
        ai_approvals.approval_to_payload(approval, snapshot=snapshot)
    )


@router.get("/runtime/runs/{run_id}", response_model=RuntimeRunInspectionResponse)
def inspect_runtime_run(
    run_id: str,
    request: Request,
    after_seq: int | None = Query(default=None, ge=0),
    limit: int = Query(default=200, ge=1, le=500),
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> RuntimeRunInspectionResponse:
    runtime_run = db.scalar(
        select(AgentRun).where(
            AgentRun.id == run_id,
            AgentRun.requested_by_user_id == current_user.id,
        )
    )
    if runtime_run is None:
        record_inspection_request(result="not_found")
        raise localized_http_exception(
            status_code=status.HTTP_404_NOT_FOUND,
            code="ai.runtime_run_not_found",
        )

    invocations = db.scalars(
        select(AgentInvocation)
        .where(AgentInvocation.agent_run_id == runtime_run.id)
        .order_by(AgentInvocation.invocation_seq.asc(), AgentInvocation.created_at.asc())
        .limit(limit)
    ).all()
    trace_query = select(AgentTraceEvent).where(AgentTraceEvent.agent_run_id == runtime_run.id)
    if after_seq is not None:
        trace_query = trace_query.where(AgentTraceEvent.event_seq > after_seq)
    trace_events = db.scalars(
        trace_query.order_by(AgentTraceEvent.event_seq.asc()).limit(limit)
    ).all()

    record_inspection_request(result="ok")
    return runtime_run_inspection_response(
        runtime_run,
        invocations=invocations,
        trace_events=trace_events,
    )


@router.post("/chat/resume")
async def chat_resume(
    payload: ChatResumeRequest,
    request: Request,
    db: Session = Depends(get_db_session),
    current_user: User = Depends(require_current_user),
) -> EventSourceResponse:
    principal = _build_request_principal(
        current_user,
        request,
        source="api.chatbot.chat.resume",
    )
    approval, snapshot = ai_approvals.get_resume_context(
        db,
        user=current_user,
        conversation_id=payload.conversation_id,
        approval_id=payload.approval_id,
    )
    conversation = conversations_service.get_conversation(
        db,
        user=current_user,
        conversation_id=payload.conversation_id,
    )
    experience = _require_conversation_experience_enabled(
        db,
        current_user,
        scope_ref=conversation.scope_ref,
        allow_retired_scope=True,
    )
    _require_conversation_chat_workload(experience, scope_ref=conversation.scope_ref)
    payload.allowed_app_ids = _constrain_conversation_tool_app_ids(
        experience,
        payload.allowed_app_ids,
    )
    effective_allowed_app_ids = ai_approvals.resolve_resume_allowed_app_ids(
        snapshot,
        payload.allowed_app_ids,
    )
    effective_allowed_app_ids = normalize_business_chat_allowed_app_ids(effective_allowed_app_ids)
    filtered_tool_specs, _has_approval_required_tools = _resolve_agent_tool_specs(
        db,
        principal=principal,
        allowed_app_ids=effective_allowed_app_ids,
    )
    del _has_approval_required_tools
    ai_approvals.ensure_resume_approved_tool_scope(
        approval,
        allowed_app_ids=effective_allowed_app_ids,
        approved_tool_app_id=owner_app_id_for_tool(
            approval.tool_name,
            registry=get_ai_capability_registry(),
        ),
    )
    filtered_tool_specs = ai_approvals.filter_resume_tool_specs(
        snapshot,
        filtered_tool_specs,
    )
    return EventSourceResponse(
        _chat_resume_publisher(
            db=db,
            principal=principal,
            current_user=current_user,
            conversation=conversation,
            approval_id=payload.approval_id,
            allowed_app_ids=effective_allowed_app_ids,
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
) -> ToolInvokeResponse:
    auth_context = getattr(request.state, "auth_context", None)
    principal = user_principal(
        user_id=current_user.id,
        source=f"api.chatbot.tool.{tool_name}",
        session_id=getattr(getattr(auth_context, "session", None), "id", None),
    )
    settings = get_settings()
    try:
        if settings.ai_mcp_bridge_enabled:
            response = AiMcpClient().call_tool(
                db,
                principal=principal,
                user=current_user,
                tool_name=tool_name,
                arguments=payload.arguments,
                source="api.tool_invoke",
            )
        else:
            response = execute_ai_tool(
                db,
                principal=principal,
                user=current_user,
                tool_name=tool_name,
                arguments=payload.arguments,
                source="api.tool_invoke",
            )
    except ToolRequiresApproval as error:
        raise approval_required_http_exception(error) from error
    return ToolInvokeResponse.model_validate(response)


# ---------------------------------------------------------------------------
# Internals
# ---------------------------------------------------------------------------


def _ensure_mcp_bridge_enabled() -> None:
    settings = get_settings()
    if settings.ai_mcp_bridge_enabled:
        return
    raise localized_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        code="ai.mcp_bridge_inspection_disabled",
    )


def _ensure_known_app(app_id: str) -> None:
    if get_app_catalog_item(app_id) is not None:
        return
    if app_id in get_chatbot_capable_app_ids():
        return
    raise localized_http_exception(
        status_code=status.HTTP_404_NOT_FOUND,
        code="ai.unknown_app",
        app_id=app_id,
    )


def _normalize_allowed_app_ids(value: list[str] | None) -> list[str] | None:
    if value is None:
        return None
    seen: set[str] = set()
    out: list[str] = []
    for item in value:
        normalized = item.strip() if isinstance(item, str) else ""
        if not normalized:
            continue
        if normalized not in seen:
            out.append(normalized)
            seen.add(normalized)
    return out


def _prepare_business_chat_request(payload: ChatRequest) -> None:
    # Provider/model/backend fields remain wire-compatible for older clients,
    # but callers no longer participate in routing. The registered workload's
    # administrator-selected execution plan is authoritative.
    payload.model = None
    payload.external_provider = None
    payload.backend_mode = "auto"
    payload.allowed_app_ids = normalize_business_chat_allowed_app_ids(payload.allowed_app_ids)


def _ensure_tool_command_allowed_for_business_chat(
    command: ToolChatCommand,
    allowed_app_ids: list[str] | None,
) -> None:
    tool_app_id = owner_app_id_for_tool(
        command.tool_name,
        registry=get_ai_capability_registry(),
    )
    allowed_contexts = set(normalize_business_chat_allowed_app_ids(allowed_app_ids))
    if tool_app_id is not None and tool_app_id in allowed_contexts:
        return
    raise localized_http_exception(
        status_code=status.HTTP_403_FORBIDDEN,
        code="ai.chat_context_tool_not_allowed",
        app_id=tool_app_id or "unknown",
    )


def _build_request_principal(
    current_user: User,
    request: Request,
    *,
    source: str,
) -> CallerPrincipal:
    auth_context = getattr(request.state, "auth_context", None)
    return user_principal(
        user_id=current_user.id,
        source=source,
        session_id=getattr(getattr(auth_context, "session", None), "id", None),
    )


async def _chat_resume_publisher(
    *,
    db: Session,
    principal: CallerPrincipal,
    current_user: User,
    conversation: Conversation,
    approval_id: str,
    allowed_app_ids: list[str] | None = None,
):
    encoder = EnvelopeEncoder()
    artifact_parser = ArtifactStreamParser(
        server_owned_artifact_types=conversation_scope_server_owned_artifact_types(conversation)
    )
    buffer = AssistantTurnBuffer()

    try:
        settings = get_settings()
        approval, snapshot = ai_approvals.get_resume_context(
            db,
            user=current_user,
            conversation_id=conversation.id,
            approval_id=approval_id,
        )
        effective_allowed_app_ids = ai_approvals.resolve_resume_allowed_app_ids(
            snapshot,
            allowed_app_ids,
        )
        effective_allowed_app_ids = normalize_business_chat_allowed_app_ids(
            effective_allowed_app_ids
        )
        filtered_tool_specs, _has_approval_required_tools = _resolve_agent_tool_specs(
            db,
            principal=principal,
            allowed_app_ids=effective_allowed_app_ids,
        )
        ai_approvals.ensure_resume_approved_tool_scope(
            approval,
            allowed_app_ids=effective_allowed_app_ids,
            approved_tool_app_id=owner_app_id_for_tool(
                approval.tool_name,
                registry=get_ai_capability_registry(),
            ),
        )
        filtered_tool_specs = ai_approvals.filter_resume_tool_specs(
            snapshot,
            filtered_tool_specs,
        )
        async for event in resume_agent_run(
            context=_task_context_from_principal(
                principal,
                experience=_resolve_conversation_experience(
                    conversation.scope_ref,
                    allow_retired_scope=True,
                ),
            ),
            db=db,
            principal=principal,
            user=current_user,
            conversation=conversation,
            approval_id=approval_id,
            encoder=encoder,
            max_turns=settings.ai_agent_max_turns,
            max_tool_calls=settings.ai_agent_max_tool_calls,
            max_consecutive_tool_errors=settings.ai_agent_max_consecutive_tool_errors,
            tool_specs=filtered_tool_specs,
        ):
            for serialized in serialize_agent_event_through_artifacts(
                event=event,
                artifact_parser=artifact_parser,
                buffer=buffer,
                encoder=encoder,
            ):
                yield serialized
    except (asyncio.CancelledError, GeneratorExit):
        if buffer.finish_reason is None:
            buffer.cancelled = True
        for flushed in flush_parser(artifact_parser, encoder=encoder):
            buffer.observe(flushed)
        return
    except Exception as error:  # noqa: BLE001 - converted to SSE contract
        for flushed in flush_parser(artifact_parser, encoder=encoder):
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
                    "meta": None,
                },
            )
        )
        buffer.observe(error_event)
        buffer.observe(done_event)
        yield error_event
        yield done_event
    finally:
        _persist_assistant_turn(
            db,
            conversation=conversation,
            buffer=buffer,
            last_decision=None,
            last_config=None,
            chosen_model=None,
        )


def _task_context_from_principal(
    principal: CallerPrincipal,
    *,
    experience: ConversationExperience = DEFAULT_CHATBOT_CONVERSATION_EXPERIENCE,
) -> LlmTaskContext:
    workload_id = experience.chat_workload_id
    if workload_id is None:
        raise ValueError(f"Conversation experience {experience.owner_app_id} has no chat workload")
    workload = resolve_llm_workload(workload_id)
    if experience.owner_app_id not in workload.app_ids:
        raise ValueError(
            "Conversation experience owner is not allowed by its chat workload: "
            f"{experience.owner_app_id}/{workload_id}"
        )
    return LlmTaskContext(
        source=principal.source,
        actor_user_id=principal.user_id,
        principal_kind=principal.kind,
        principal_id=principal.principal_id,
        task_kind=workload.task_kind,
        app_id=experience.owner_app_id,
        workload_id=workload.workload_id,
    )


def _resolve_agent_tool_specs(
    db: Session,
    *,
    principal: CallerPrincipal,
    messages: list[dict[str, Any]] | None = None,
    allowed_app_ids: list[str] | None = None,
) -> tuple[list[AgentToolSpec], bool]:
    surface = _resolve_agent_tool_surface(
        db,
        principal=principal,
        messages=messages,
        allowed_app_ids=allowed_app_ids,
    )
    return surface.tool_specs, surface.has_approval_required_tools


def _resolve_agent_tool_surface(
    db: Session,
    *,
    principal: CallerPrincipal,
    messages: list[dict[str, Any]] | None = None,
    allowed_app_ids: list[str] | None = None,
) -> AgentToolSurface:
    surface = resolve_agent_tool_surface(
        db,
        principal=principal,
        messages=messages,
        allowed_app_ids=allowed_app_ids,
        registry=get_ai_capability_registry(),
    )
    return surface


def _parse_tool_chat_command(messages: list[ChatMessage]) -> ToolChatCommand | None:
    try:
        return parse_tool_chat_command(messages)
    except ToolChatCommandError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code=error.code,
            **error.params,
        ) from error


def _execute_tool_chat_command(
    payload: ChatRequest,
    db: Session,
    *,
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
    _ensure_tool_command_allowed_for_business_chat(
        command,
        payload.allowed_app_ids,
    )
    result = run_tool_chat_command(
        db,
        principal=principal,
        user=current_user,
        source="api.chat",
        command=command,
        conversation_id=getattr(payload, "conversation_id", None),
    )
    response = ChatResponse(
        **build_tool_chat_response_payload(
            result,
            requested_backend_mode=payload.backend_mode,
        )
    )
    return response, result.execution


def _scope_direct_chat_response(
    content: str,
    *,
    requested_backend_mode: LlmRequestBackendMode,
) -> ChatResponse:
    """Build a deterministic scope-owned response without invoking an LLM."""

    return ChatResponse(
        model="scope-direct",
        content=content,
        usage=None,
        finish_reason="stop",
        provider="server",
        backend="server",
        fallback_used=False,
        canonical_model="scope-direct",
        requested_backend_mode=requested_backend_mode,
        policy="scope_direct_response",
        chosen_pool=None,
        decision_reason="scope_direct_response",
    )


def _scope_direct_response_meta(
    scope_context: ConversationScopeTurnContext | None = None,
) -> dict[str, Any]:
    meta = {
        "policy": "scope_direct_response",
        "chosen_pool": None,
        "decision_reason": "scope_direct_response",
        "forced_local": False,
        "pii_hits": [],
        "model": "scope-direct",
        "chosen_model": "scope-direct",
        "canonical_model": "scope-direct",
        "provider": "server",
    }
    if scope_context is not None:
        if scope_context.background_run_id:
            meta["background_run_id"] = scope_context.background_run_id
        if scope_context.background_artifact_id:
            meta["background_artifact_id"] = scope_context.background_artifact_id
    return meta


def _complete_via_policy(
    context: LlmTaskContext,
    payload: ChatRequest,
    db: Session,
    *,
    messages: list[dict[str, Any]],
) -> ChatResponse:
    try:
        gateway_response = complete_gateway_chat(
            _gateway_request_from_chat_payload(
                context,
                payload,
                db,
                messages=messages,
            ),
            db,
        )
    except LlmModelConfigurationError as error:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.configured_llm_model_required",
            canonical_model=error.canonical_model,
        ) from error
    except AiGatewayPolicyViolation as error:
        raise localized_http_exception(
            status_code=(
                status.HTTP_403_FORBIDDEN
                if error.reason_code == "external_transfer_blocked"
                else status.HTTP_400_BAD_REQUEST
            ),
            code=(
                "ai.external_transfer_blocked"
                if error.reason_code == "external_transfer_blocked"
                else "ai.gateway_policy_violation"
            ),
            reason=error.reason_code,
        ) from error
    except LlmProviderError as error:
        raise localized_http_exception(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code=("ai.llm_pool_unavailable_policy"),
            error=str(error),
        ) from error

    decision = gateway_response.decision
    return _build_response(
        gateway_response.response,
        gateway_response.config,
        payload,
        decision_policy=decision.policy,
        decision_pool=cast(LlmPoolName, decision.chosen_pool),
        decision_reason=",".join(decision.reason_codes) if decision.reason_codes else None,
        decision_forced_local=decision.forced_local,
        decision_pii=list(decision.pii_hits),
    )


def _gateway_request_from_chat_payload(
    context: LlmTaskContext,
    payload: ChatRequest,
    db: Session,
    *,
    messages: list[dict[str, Any]],
    stream: bool = False,
) -> AiGatewayRequest:
    if context.workload_id is None:
        raise ValueError("Registered chat workload_id is required")
    workload = resolve_llm_workload(context.workload_id)
    if workload.task_kind != context.task_kind or context.app_id not in workload.app_ids:
        raise ValueError(
            "Registered chat workload does not match its task context: "
            f"{context.workload_id}/{context.app_id}/{context.task_kind}"
        )
    return build_llm_workload_request(
        workload.workload_id,
        LlmWorkloadContext.from_task_context(context),
        db,
        messages=messages,
        temperature=payload.temperature,
        max_tokens=payload.max_tokens,
        reasoning_effort=payload.reasoning_effort,
        stream=stream,
        stream_reasoning=payload.stream_reasoning
        if isinstance(payload, ChatStreamRequest)
        else True,
        conversation_id=getattr(payload, "conversation_id", None),
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


def _build_sync_error_response(
    payload: ChatRequest,
    error: Exception,
    *,
    locale: str,
) -> ChatResponse:
    detail = error.detail if isinstance(error, HTTPException) else None
    if isinstance(detail, LocalizedApiMessage):
        content = translate_message(detail, locale)
    else:
        content = _error_message(error) or "AI request failed."
    model = payload.model or "unknown"
    return ChatResponse(
        model=model,
        content=content,
        usage=None,
        finish_reason="error",
        provider="error",
        backend="primary",
        fallback_used=False,
        canonical_model=model,
        requested_backend_mode=payload.backend_mode,
        policy=None,
        chosen_pool=None,
        decision_reason=_error_code(error),
        forced_local=False,
        pii_hits=[],
        conversation_id=None,
    )


def _ensure_supported_backend_mode(mode: LlmRequestBackendMode) -> None:
    _ = mode


def _reject_unsupported_external_tool_provider(provider: str) -> None:
    raise localized_http_exception(
        status_code=status.HTTP_400_BAD_REQUEST,
        code="ai.external_provider_tools_unsupported",
        provider=provider,
    )


# ---------------------------------------------------------------------------
# SSE stream publisher
# ---------------------------------------------------------------------------


async def _chat_stream_publisher(
    *,
    payload: "ChatStreamRequest",
    db: Session,
    context: LlmTaskContext,
    principal: CallerPrincipal,
    current_user: User,
    locale: str,
):
    encoder = EnvelopeEncoder()
    reasoning_gate = payload.stream_reasoning and payload.reasoning_effort != "none"
    raw_messages_dict = [message.model_dump() for message in payload.messages]
    settings = get_settings()
    runtime_routing = select_runtime_profile(
        messages=raw_messages_dict,
        allowed_app_ids=payload.allowed_app_ids,
        max_tokens=payload.max_tokens,
        graph_enabled=settings.ai_runtime_graph_enabled,
    )
    runtime_routing = _attach_graph_gate_trace_metadata(
        runtime_routing,
        db=db,
        allowed_app_ids=payload.allowed_app_ids,
    )
    runtime_routing = attach_graph_execution_adapter_decision(
        runtime_routing,
        graph_execution_enabled=settings.ai_runtime_graph_execution_enabled,
    )
    runtime_routing = _attach_external_egress_trace_metadata(
        runtime_routing,
        messages=raw_messages_dict,
        settings=settings,
    )

    last_decision: PolicyDecision | None = None
    last_config: LlmPoolConfig | None = None
    chosen_model: str | None = None

    # Bind the turn-persistence context before any events fire. On a
    # validation-style error the helper returns a full terminal
    # (error, done) envelope pair so the client leaves the streaming state
    # cleanly; on success the stream proceeds normally.
    conversation, live_run_lock, terminal_envelopes = _bind_conversation_for_stream(
        db=db,
        principal=principal,
        user=current_user,
        payload=payload,
        locale=locale,
    )
    if terminal_envelopes is not None:
        for envelope in terminal_envelopes:
            yield envelope
        return
    if conversation is not None:
        # Persist the user turn before advertising the conversation id. This
        # makes `conversation_attached` a durable-read barrier: a client that
        # remounts and immediately hydrates the attached conversation can
        # already read the submitted question.
        try:
            if payload.replace_from_seq is None and payload.persist_user_turn:
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
                        "message": translate_message(
                            LocalizedApiMessage("ai.conversation_persist_error"),
                            locale,
                        ),
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
            _complete_live_conversation_run(db, live_run_lock)
            return
        yield serialize_sse(
            make_envelope(
                "conversation_attached",
                encoder.next_seq(),
                {"conversation_id": conversation.id},
            )
        )

    buffer = AssistantTurnBuffer()
    # Artifact parser is stateful across the entire stream (one per request).
    # It converts `<artifact>...</artifact>` markup embedded in content_deltas
    # into artifact_started/delta/completed envelopes so the client renders
    # those bodies in a side panel instead of the chat bubble.
    artifact_parser = ArtifactStreamParser(
        server_owned_artifact_types=conversation_scope_server_owned_artifact_types(conversation)
    )
    pending_scope_artifacts: list[ConversationScopeArtifact] = []
    fallback_runtime_run_id: str | None = None
    graph_execution_runtime_run_id: str | None = None
    scope_context = ConversationScopeTurnContext()

    try:
        scope_context = conversation_scope_turn_context(
            db,
            principal=principal,
            user=current_user,
            conversation=conversation,
            messages=raw_messages_dict,
        )
        artifact_parser = ArtifactStreamParser(
            server_owned_artifact_types=scope_context.server_owned_artifact_types
        )
        messages_dict = _messages_with_business_chat_prompt(
            raw_messages_dict,
            scope_system_prompt=scope_context.prompt,
        )
        pending_scope_artifacts = list(scope_context.artifacts)

        command = _parse_tool_chat_command(payload.messages)
        if command is not None:
            # Direct tool commands bypass the LLM so they can never produce
            # artifact markup — no parser wiring needed on this path.
            for event in _tool_command_events(
                encoder=encoder,
                db=db,
                principal=principal,
                current_user=current_user,
                command=command,
                allowed_app_ids=payload.allowed_app_ids,
            ):
                buffer.observe(event)
                yield event
            return
        if scope_context.direct_response is not None:
            for content_event in emit_content_through_parser(
                scope_context.direct_response,
                parser=artifact_parser,
                encoder=encoder,
            ):
                buffer.observe(content_event)
                yield content_event
            for flushed in flush_parser(artifact_parser, encoder=encoder):
                buffer.observe(flushed)
                yield flushed
            done_event = serialize_sse(
                make_envelope(
                    "done",
                    encoder.next_seq(),
                    {
                        "finish_reason": "stop",
                        "audit_id": None,
                        "meta": _scope_direct_response_meta(scope_context),
                    },
                )
            )
            for scope_artifact_event in _consume_scope_artifacts_before_done(
                done_event,
                pending_scope_artifacts=pending_scope_artifacts,
                buffer=buffer,
                encoder=encoder,
            ):
                yield scope_artifact_event
            buffer.observe(done_event)
            yield done_event
            return

        gateway_execution = resolve_gateway_execution(
            _gateway_request_from_chat_payload(
                context,
                payload,
                db,
                messages=messages_dict,
                stream=True,
            ),
            db,
        )
        execution = gateway_execution.llm_execution
        last_decision = execution.decision
        last_config = execution.config
        chosen_model = execution.chosen_model

        tool_surface = _resolve_agent_tool_surface(
            db,
            principal=principal,
            messages=raw_messages_dict,
            allowed_app_ids=payload.allowed_app_ids,
        )
        filtered_tool_specs = tool_surface.tool_specs
        has_approval_required_tools = tool_surface.has_approval_required_tools
        if (
            execution.pool == "external"
            and bool(filtered_tool_specs)
            and not supports_tool_calling(execution.pool, execution.config.provider)
        ):
            _reject_unsupported_external_tool_provider(execution.config.provider)
        if should_use_graph_execution_adapter(runtime_routing):
            graph_execution_runtime_run_id = new_id()
            graph_event_stream = run_graph_execution_adapter_stream(
                context=context,
                execution=execution,
                db=db,
                principal=principal,
                user=current_user,
                messages=raw_messages_dict,
                temperature=payload.temperature,
                stream_reasoning=payload.stream_reasoning,
                encoder=encoder,
                settings=settings,
                agent_run_id=graph_execution_runtime_run_id,
                filtered_tool_specs=filtered_tool_specs,
                bound_conversation=conversation,
                scope_system_prompt=scope_context.prompt,
                allowed_app_ids=payload.allowed_app_ids,
                runtime_routing=runtime_routing,
            )
            async for event in graph_event_stream:
                for serialized in serialize_agent_event_through_artifacts(
                    event=event,
                    artifact_parser=artifact_parser,
                    buffer=buffer,
                    encoder=encoder,
                ):
                    for scope_artifact_event in _consume_scope_artifacts_before_done(
                        serialized,
                        pending_scope_artifacts=pending_scope_artifacts,
                        buffer=buffer,
                        encoder=encoder,
                    ):
                        yield scope_artifact_event
                    yield serialized
            return

        if stream_tool_calling_enabled(
            settings, execution.pool, execution.config.provider
        ) and bool(filtered_tool_specs):
            agent_run_id = new_id()
            async for event in run_agent_turn_stream(
                context=context,
                execution=execution,
                db=db,
                principal=principal,
                user=current_user,
                messages=raw_messages_dict,
                temperature=payload.temperature,
                stream_reasoning=payload.stream_reasoning,
                encoder=encoder,
                max_turns=settings.ai_agent_max_turns,
                max_tool_calls=settings.ai_agent_max_tool_calls,
                max_consecutive_tool_errors=settings.ai_agent_max_consecutive_tool_errors,
                agent_run_id=agent_run_id,
                tool_specs=filtered_tool_specs,
                bound_conversation=conversation,
                scope_system_prompt=scope_context.prompt,
                allowed_app_ids=payload.allowed_app_ids,
                **runtime_routing_stream_kwargs(runtime_routing),
                parallel_tool_calls=False if has_approval_required_tools else None,
            ):
                for serialized in serialize_agent_event_through_artifacts(
                    event=event,
                    artifact_parser=artifact_parser,
                    buffer=buffer,
                    encoder=encoder,
                ):
                    for scope_artifact_event in _consume_scope_artifacts_before_done(
                        serialized,
                        pending_scope_artifacts=pending_scope_artifacts,
                        buffer=buffer,
                        encoder=encoder,
                    ):
                        yield scope_artifact_event
                    yield serialized
            return

        if (
            conversation is not None
            and runtime_routing.graph_gate == "eligible"
            and settings.ai_runtime_shadow_write_enabled
        ):
            fallback_runtime_run_id = new_id()

        stream_gateway_execution = gateway_execution
        if conversation is not None and conversation.id != payload.conversation_id:
            stream_gateway_execution = replace(
                gateway_execution,
                request=replace(
                    gateway_execution.request,
                    conversation_id=conversation.id,
                ),
            )

        async for chunk, _decision, config in complete_resolved_gateway_chat_stream(
            stream_gateway_execution,
            db,
        ):
            last_decision = execution.decision
            last_config = config
            chosen_model = execution.chosen_model
            # Content chunks feed the artifact parser; every other kind
            # (reasoning/usage/tool_*/done) goes through _chunk_to_envelope.
            # The ``done`` chunk must be preceded by a parser flush so the
            # client receives terminal artifact_completed envelopes before
            # it reads ``done``.
            if chunk.kind == "content" and chunk.text:
                for parsed_event in emit_content_through_parser(
                    chunk.text,
                    parser=artifact_parser,
                    encoder=encoder,
                ):
                    buffer.observe(parsed_event)
                    yield parsed_event
                continue
            if chunk.kind == "done":
                for flushed in flush_parser(artifact_parser, encoder=encoder):
                    buffer.observe(flushed)
                    yield flushed
            event = _chunk_to_envelope(
                chunk,
                encoder=encoder,
                reasoning_gate=reasoning_gate,
                decision=last_decision,
                config=last_config,
                model=chosen_model,
                runtime_routing=runtime_routing,
                agent_run_id=fallback_runtime_run_id,
            )
            if event is not None:
                for scope_artifact_event in _consume_scope_artifacts_before_done(
                    event,
                    pending_scope_artifacts=pending_scope_artifacts,
                    buffer=buffer,
                    encoder=encoder,
                ):
                    yield scope_artifact_event
                buffer.observe(event)
                yield event
    except (asyncio.CancelledError, GeneratorExit):
        # Client aborted mid-stream. If a terminal ``done`` envelope was
        # already observed, the disconnect is just normal SSE teardown and
        # must not overwrite a completed assistant turn as cancelled.
        if buffer.finish_reason is None:
            buffer.cancelled = True
        # Drain the artifact parser into the buffer (not the wire — the
        # generator is already being torn down) so any in-flight artifact
        # lands on disk with an artifact_completed synthesized by flush().
        for flushed in flush_parser(artifact_parser, encoder=encoder):
            buffer.observe(flushed)
        return
    except Exception as error:  # noqa: BLE001 - converted to SSE contract
        # Flush artifact parser before the terminal error/done pair so the
        # client finalizes any open artifact buffers before acting on `done`.
        for flushed in flush_parser(artifact_parser, encoder=encoder):
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
        done_meta = _build_done_meta(
            last_decision,
            last_config,
            model=chosen_model,
            runtime_routing=runtime_routing,
            agent_run_id=graph_execution_runtime_run_id or fallback_runtime_run_id,
        )
        if graph_execution_runtime_run_id is not None and done_meta is not None:
            done_meta = attach_graph_execution_adapter_error_summary(
                done_meta,
                runtime_routing=runtime_routing,
                messages=raw_messages_dict,
                error_class=_error_code(error),
            )
        done_event = serialize_sse(
            make_envelope(
                "done",
                encoder.next_seq(),
                {
                    "finish_reason": "error",
                    "audit_id": None,
                    "meta": done_meta,
                },
            )
        )
        buffer.observe(error_event)
        buffer.observe(done_event)
        yield error_event
        yield done_event
    finally:
        if conversation is not None and not scope_context.assistant_turn_persisted:
            _persist_assistant_turn(
                db,
                conversation=conversation,
                buffer=buffer,
                last_decision=last_decision,
                last_config=last_config,
                chosen_model=chosen_model,
                runtime_routing=runtime_routing,
                agent_run_id=graph_execution_runtime_run_id or fallback_runtime_run_id,
            )
            if (
                graph_execution_runtime_run_id is not None
                and buffer.finish_reason != "awaiting_approval"
            ):
                done_meta = buffer.done_meta or _build_done_meta(
                    last_decision,
                    last_config,
                    model=chosen_model,
                    runtime_routing=runtime_routing,
                    agent_run_id=graph_execution_runtime_run_id,
                )
                persist_graph_execution_runtime_shadow(
                    db,
                    agent_run_id=graph_execution_runtime_run_id,
                    conversation_id=conversation.id,
                    requested_by_user_id=current_user.id,
                    runtime_metadata=done_meta or {},
                    finish_reason=buffer.finish_reason,
                    response_status=("cancelled" if buffer.cancelled else buffer.response_status),
                )
            if fallback_runtime_run_id is not None:
                done_meta = buffer.done_meta or _build_done_meta(
                    last_decision,
                    last_config,
                    model=chosen_model,
                    runtime_routing=runtime_routing,
                    agent_run_id=fallback_runtime_run_id,
                )
                persist_single_loop_fallback_runtime_shadow(
                    db,
                    agent_run_id=fallback_runtime_run_id,
                    conversation_id=conversation.id,
                    requested_by_user_id=current_user.id,
                    runtime_metadata=done_meta or {},
                    finish_reason=buffer.finish_reason,
                    response_status=("cancelled" if buffer.cancelled else buffer.response_status),
                )
            _complete_live_conversation_run(db, live_run_lock)


def _attach_graph_gate_trace_metadata(
    runtime_routing: RuntimeRoutingDecision,
    *,
    db: Session,
    allowed_app_ids: list[str] | None,
) -> RuntimeRoutingDecision:
    if runtime_routing.graph_gate != "eligible":
        return runtime_routing
    resolved_agents = resolve_agent_definitions(
        enabled_app_ids=resolve_company_enabled_app_ids(
            db,
        ),
        allowed_app_ids=allowed_app_ids,
    )
    candidate = build_deterministic_manager_candidate(
        runtime_profile=runtime_routing.runtime_profile,
        resolved_agents=resolved_agents,
    )
    if candidate is not None:
        validation = ManagerGraphValidator.for_resolved_agents(resolved_agents).validate(candidate)
        return attach_manager_graph_validation_result(
            runtime_routing,
            validation=validation,
            registry_agent_count=len(resolved_agents.agent_ids),
            write_agent_count=len(resolved_agents.write_agent_ids),
            graph_candidate_summary=summarize_execution_graph(validation.graph)
            if validation.graph is not None
            else None,
            graph_schedule_summary=_build_graph_schedule_summary_or_failure(validation.graph),
        )
    return attach_trace_only_graph_validation(
        runtime_routing,
        registry_agent_count=len(resolved_agents.agent_ids),
        write_agent_count=len(resolved_agents.write_agent_ids),
    )


def _attach_external_egress_trace_metadata(
    runtime_routing: RuntimeRoutingDecision,
    *,
    messages: list[dict[str, Any]],
    settings: Any,
) -> RuntimeRoutingDecision:
    if (
        runtime_routing.graph_gate != "eligible"
        or runtime_routing.graph_execution_status != "adapter_selected"
    ):
        return runtime_routing
    user_text = _latest_message_text(messages)
    capabilities = ["planning"]
    if runtime_routing.runtime_profile == "grounded_report":
        capabilities.append("search")
    decisions = [
        evaluate_external_egress(
            capability=cast(ExternalCapability, capability),
            provider=None,
            text=user_text,
            settings=settings,
        ).model_dump(mode="json")
        for capability in capabilities
    ]
    planner_summaries = external_planner_trace_summaries(
        runtime_profile=runtime_routing.runtime_profile,
        graph_candidate_summary=runtime_routing.graph_candidate_summary,
        decisions=decisions,
        execution_enabled=bool(getattr(settings, "ai_external_planner_execution_enabled", False)),
        settings=settings,
    )
    search_summaries = external_search_trace_summaries(
        decisions=decisions,
        execution_enabled=bool(getattr(settings, "ai_external_search_execution_enabled", False)),
        settings=settings,
    )
    return replace(
        runtime_routing,
        external_egress_summary={
            "policy_version": "external_egress.v1",
            "decision_count": len(decisions),
            "allow_external": any(bool(decision.get("allow_external")) for decision in decisions),
            "denied_count": sum(1 for decision in decisions if not decision.get("allow_external")),
            "capabilities": [decision.get("capability") for decision in decisions],
            "decisions": decisions,
        },
        external_planner_summary=planner_summaries.request_summary,
        external_search_summary=search_summaries.request_summary,
        external_planner_execution_summary=planner_summaries.execution_summary,
        external_search_execution_summary=search_summaries.execution_summary,
    )


def _latest_message_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
    return ""


def _build_graph_schedule_summary_or_failure(validation_graph) -> dict[str, Any] | None:
    if validation_graph is None:
        return None
    try:
        return summarize_graph_execution_schedule(build_graph_execution_schedule(validation_graph))
    except GraphSchedulerError as error:
        return summarize_graph_schedule_failure(error)


def _tool_command_events(
    *,
    encoder: EnvelopeEncoder,
    db: Session,
    principal: CallerPrincipal,
    current_user: User,
    command: ToolChatCommand,
    allowed_app_ids: list[str] | None,
):
    _ensure_tool_command_allowed_for_business_chat(command, allowed_app_ids)
    yield from execute_tool_chat_command_sse_events(
        db,
        principal=principal,
        user=current_user,
        source="api.stream",
        command=command,
        encoder=encoder,
    )


def _append_scope_artifacts_to_buffer(
    buffer: AssistantTurnBuffer,
    artifacts: tuple[ConversationScopeArtifact, ...],
) -> None:
    if not artifacts:
        return
    encoder = EnvelopeEncoder()
    for event in _scope_artifact_events(artifacts, encoder=encoder):
        buffer.observe(event)


def _consume_scope_artifacts_before_done(
    event: dict[str, str],
    *,
    pending_scope_artifacts: list[ConversationScopeArtifact],
    buffer: AssistantTurnBuffer,
    encoder: EnvelopeEncoder,
) -> list[dict[str, str]]:
    if not pending_scope_artifacts or event.get("event") != "done":
        return []
    if _serialized_done_finish_reason(event) == "error":
        pending_scope_artifacts.clear()
        return []
    artifacts = tuple(pending_scope_artifacts)
    pending_scope_artifacts.clear()
    out = _scope_artifact_events(artifacts, encoder=encoder)
    for artifact_event in out:
        buffer.observe(artifact_event)
    return out


def _scope_artifact_events(
    artifacts: tuple[ConversationScopeArtifact, ...],
    *,
    encoder: EnvelopeEncoder,
) -> list[dict[str, str]]:
    out: list[dict[str, str]] = []
    for artifact in artifacts:
        out.append(
            serialize_sse(
                make_envelope(
                    "artifact_started",
                    encoder.next_seq(),
                    {
                        "artifact_id": artifact.id,
                        "artifact_type": artifact.type,
                        "title": artifact.title,
                        "language": artifact.language,
                    },
                )
            )
        )
        for chunk in _artifact_content_chunks(artifact.content):
            out.append(
                serialize_sse(
                    make_envelope(
                        "artifact_delta",
                        encoder.next_seq(),
                        {
                            "artifact_id": artifact.id,
                            "delta": chunk,
                        },
                    )
                )
            )
        out.append(
            serialize_sse(
                make_envelope(
                    "artifact_completed",
                    encoder.next_seq(),
                    {"artifact_id": artifact.id},
                )
            )
        )
    return out


def _artifact_content_chunks(content: str, *, chunk_size: int = 12000) -> list[str]:
    if not content:
        return []
    return [content[index : index + chunk_size] for index in range(0, len(content), chunk_size)]


def _serialized_done_finish_reason(event: dict[str, str]) -> str | None:
    try:
        envelope = json.loads(event.get("data", ""))
    except (TypeError, ValueError):
        return None
    data = envelope.get("data") if isinstance(envelope, dict) else None
    if not isinstance(data, dict):
        return None
    finish_reason = data.get("finish_reason")
    return finish_reason if isinstance(finish_reason, str) else None


def _error_code(error: Exception) -> str:
    if isinstance(error, HTTPException):
        return "request_error"
    if isinstance(error, AiGatewayPolicyViolation):
        if error.reason_code == "external_transfer_blocked":
            return "ai.external_transfer_blocked"
        return "request_error"
    if isinstance(error, LlmModelConfigurationError):
        return "request_error"
    if isinstance(error, LlmProviderError):
        return "provider_error"
    return "adapter_error"


def _error_message(error: Exception) -> str:
    if isinstance(error, HTTPException):
        detail = error.detail
        if isinstance(detail, str):
            return detail
        if isinstance(detail, LocalizedApiMessage):
            return detail.code
        if isinstance(detail, dict):
            message = detail.get("message")
            if isinstance(message, str) and message.strip():
                return message
        return "AI request failed."
    if isinstance(error, LlmModelConfigurationError):
        return "ai.configured_llm_model_required"
    if isinstance(error, AiGatewayPolicyViolation):
        if error.reason_code == "external_transfer_blocked":
            return "ai.external_transfer_blocked"
        return error.reason_code
    return str(error)


# ---------------------------------------------------------------------------
# Conversation turn persistence helpers
# ---------------------------------------------------------------------------


def _apply_conversation_rewrite_if_requested(
    *,
    db: Session,
    user: User,
    conversation: Conversation | None,
    payload: ConversationBoundChatRequest,
) -> Conversation | None:
    if payload.replace_from_seq is None:
        if not payload.persist_user_turn:
            raise localized_http_exception(
                status_code=status.HTTP_400_BAD_REQUEST,
                code="ai.conversation_retry_requires_rewrite",
            )
        return conversation

    if conversation is None or not payload.conversation_id:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.conversation_rewrite_requires_persisted_thread",
        )
    if not payload.replace_from_turn_id:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.conversation_rewrite_turn_id_required",
        )
    if payload.replace_tail_seq is None or not payload.replace_tail_turn_id:
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.conversation_rewrite_tail_required",
        )

    live_pending = ai_approvals.has_live_conversation_run(
        db,
        user=user,
        conversation_id=conversation.id,
        for_update=True,
    )
    if live_pending:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.conversation_rewrite_approval_pending",
        )

    last_request_user = next(
        (message for message in reversed(payload.messages) if message.role == "user"),
        None,
    )
    if last_request_user is None:
        raise localized_http_exception(
            status_code=status.HTTP_409_CONFLICT,
            code="ai.conversation_retry_context_mismatch",
        )

    return conversations_service.rewrite_turns_from_target(
        db,
        user=user,
        conversation_id=conversation.id,
        target_turn_id=payload.replace_from_turn_id,
        from_seq=payload.replace_from_seq,
        expected_tail_turn_id=payload.replace_tail_turn_id,
        expected_tail_seq=payload.replace_tail_seq,
        persist_user_turn=payload.persist_user_turn,
        replacement_user_content=last_request_user.content if payload.persist_user_turn else None,
        expected_retry_user_content=last_request_user.content,
    )


def _bind_conversation_for_stream(
    *,
    db: Session,
    principal: CallerPrincipal,
    user: User,
    payload: "ChatStreamRequest",
    locale: str,
) -> tuple[
    Conversation | None,
    ai_approvals.ConversationRunLock | None,
    list[dict[str, str]] | None,
]:
    """Resolve (or create) the Conversation row the stream will append to.

    Returns ``(conversation, lock, None)`` on success, where both values may be
    ``None`` when the caller hasn't opted into persistence yet. On a
    validation-style failure returns ``(None, None, [error, done])`` so the
    publisher yields the full terminal pair and clients leave streaming state.
    """
    encoder_for_errors = EnvelopeEncoder()

    def terminal_from_http_exception(exc: HTTPException) -> list[dict[str, str]]:
        detail = exc.detail
        if isinstance(detail, LocalizedApiMessage):
            code = (
                "conversation_not_found"
                if detail.code == "conversations.not_found"
                else detail.code
            )
            message = translate_message(detail, locale)
        elif isinstance(detail, str):
            code = (
                exc.headers.get("X-Open-Work-Hub-Error-Code", "conversation_error")
                if exc.headers
                else "conversation_error"
            )
            message = detail
        else:
            code = "conversation_error"
            message = "Conversation request failed."
        error_envelope = serialize_sse(
            make_envelope(
                "error",
                encoder_for_errors.next_seq(),
                {
                    "code": code,
                    "message": message,
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
        return [error_envelope, done_envelope]

    try:
        conversation = _resolve_requested_conversation(
            db=db,
            user=user,
            conversation_id=payload.conversation_id,
        )
        if conversation is not None:
            _ensure_payload_scope_matches_conversation(conversation, payload)
    except HTTPException as exc:
        return None, None, terminal_from_http_exception(exc)

    try:
        conversation = _apply_conversation_rewrite_if_requested(
            db=db,
            user=user,
            conversation=conversation,
            payload=payload,
        )
    except HTTPException as exc:
        return None, None, terminal_from_http_exception(exc)

    if conversation is not None:
        try:
            live_run_lock = _start_live_conversation_run(
                db=db,
                user=user,
                conversation=conversation,
            )
        except HTTPException as exc:
            return None, None, terminal_from_http_exception(exc)
        return conversation, live_run_lock, None

    if not payload.persist:
        # Legacy caller that has not opted into persistence yet: keep the
        # stream running but skip persistence.
        return None, None, None

    try:
        validate_requested_conversation_scope(
            db,
            principal=principal,
            user=user,
            scope_ref=payload.scope_ref,
            scope_resource_id=payload.scope_resource_id,
        )
        conversation = conversations_service.create_conversation(
            db,
            user=user,
            title="",
            scope_ref=payload.scope_ref,
            scope_resource_id=payload.scope_resource_id,
        )
    except HTTPException as exc:
        return None, None, terminal_from_http_exception(exc)
    try:
        live_run_lock = _start_live_conversation_run(
            db=db,
            user=user,
            conversation=conversation,
        )
    except HTTPException as exc:
        return None, None, terminal_from_http_exception(exc)
    return conversation, live_run_lock, None


def _ensure_payload_scope_matches_conversation(
    conversation: Conversation,
    payload: ConversationBoundChatRequest,
) -> None:
    if payload.scope_ref is None and payload.scope_resource_id is None:
        return
    if (
        payload.scope_ref != conversation.scope_ref
        or payload.scope_resource_id != conversation.scope_resource_id
    ):
        raise localized_http_exception(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="ai.conversation_scope_mismatch",
        )


def _persist_sync_chat_response(
    *,
    db: Session,
    user: User,
    payload: ConversationBoundChatRequest,
    conversation: Conversation | None,
    buffer: AssistantTurnBuffer,
    assistant_turn_persisted: bool = False,
) -> str | None:
    if conversation is None and not payload.persist:
        return None

    bound_conversation = conversation
    if bound_conversation is None:
        bound_conversation = conversations_service.create_conversation(
            db,
            user=user,
            title="",
            scope_ref=payload.scope_ref,
            scope_resource_id=payload.scope_resource_id,
        )

    if payload.replace_from_seq is None and payload.persist_user_turn:
        _record_user_turn(
            db=db,
            conversation=bound_conversation,
            messages=payload.messages,
        )
    if not assistant_turn_persisted:
        _persist_assistant_turn(
            db,
            conversation=bound_conversation,
            buffer=buffer,
            last_decision=None,
            last_config=None,
            chosen_model=None,
        )
    return bound_conversation.id


def _persist_assistant_turn(
    db: Session,
    *,
    conversation: Conversation,
    buffer: AssistantTurnBuffer,
    last_decision: PolicyDecision | None,
    last_config: LlmPoolConfig | None,
    chosen_model: str | None,
    runtime_routing: RuntimeRoutingDecision | None = None,
    agent_run_id: str | None = None,
) -> None:
    """Write a single assistant turn summarizing the streamed response.

    Runs from the publisher's ``finally`` so the row lands on every exit
    path — normal completion, mid-stream error, and client cancellation.
    Empty streams still get persisted when the finish reason was terminal
    (error/cancelled) so the reloaded conversation reflects that the live
    UI showed a failure response rather than an absent assistant turn.
    """
    fallback_meta = _build_done_meta(
        last_decision,
        last_config,
        model=chosen_model,
        runtime_routing=runtime_routing,
        agent_run_id=agent_run_id,
    )
    record = build_assistant_turn_record(buffer, fallback_meta=fallback_meta)
    if record is None:
        return

    try:
        conversations_service.append_turn(
            db,
            conversation=conversation,
            role="assistant",
            content=record.content,
            meta=record.meta,
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
