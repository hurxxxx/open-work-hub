from __future__ import annotations

from collections.abc import AsyncIterator, Mapping
from dataclasses import dataclass, field, replace
from typing import Any, Literal

from sqlalchemy.orm import Session

from open_work_hub_api.core.llm import (
    LlmCompletionResult,
    LlmPoolConfig,
    LlmPoolHint,
    LlmTaskContext,
    ResolvedLlmExecution,
    resolve_registered_chat_execution,
)
from open_work_hub_api.core.llm import (
    complete_chat as _complete_chat,
)
from open_work_hub_api.core.llm import (
    complete_chat_stream as _complete_chat_stream,
)
from open_work_hub_api.core.llm import (
    complete_chat_text as _complete_chat_text,
)
from open_work_hub_api.core.llm_adapters import StreamChunk
from open_work_hub_api.core.llm_errors import LlmProviderError
from open_work_hub_api.core.llm_provider_registry import parse_external_llm_provider_allowlist
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.audit import log_llm_call
from open_work_hub_api.domains.ai.boundary_safety import (
    ExternalPayloadSafetyDecision,
    evaluate_external_payload_safety,
    normalize_content_origin,
    normalize_external_safety_values,
)
from open_work_hub_api.domains.ai.masking import (
    ExternalPayloadMaskingResult,
    evaluate_external_payload_masking,
)
from open_work_hub_api.domains.ai.model_settings_service import (
    AiModelSettingsError,
    ResolvedLlmWorkloadRoute,
    resolve_ai_model_workload_route,
)
from open_work_hub_api.domains.ai.registry import get_ai_capability_registry
from open_work_hub_api.domains.ai.runtime_status import build_resolved_llm_pool_config
from open_work_hub_api.domains.ai.security_detected_values import (
    AiSecurityDetectedValueInput,
    collect_ai_security_detected_values,
    serialize_detected_values,
)
from open_work_hub_api.domains.ai.security_pipeline_exemption import (
    AI_SECURITY_PIPELINE_EXEMPT_REASON,
    AiSecurityPipelineExemptionDecision,
    resolve_ai_security_pipeline_exemption,
)
from open_work_hub_api.domains.ai.security_policy import (
    AI_SECURITY_ENFORCEMENT_DISABLED_REASON,
    AI_SECURITY_ENFORCEMENT_REQUIRED_REASON,
    AI_SECURITY_LLM_CAPABILITY,
    CUSTOM_BLOCK_ENTITY_TYPE,
    EXTERNAL_TRANSFER_EXCEPTION_REASON,
    AiSecurityExternalTransferExceptionDecision,
    AiSecurityPolicyContext,
    AiSecurityPolicyDecision,
    ai_security_data_protection_blocker_actions,
    ai_security_enforcement_enabled,
    ai_security_enforcement_required,
    evaluate_ai_security_policy,
    external_transfer_blockers_from_safety,
    hard_external_transfer_blockers,
    resolve_ai_security_external_transfer_exception,
)

_UNKNOWN_TASK_KIND_REASON = "unknown_task_kind_local_only"
_FORBIDDEN_GATEWAY_APP_IDS = frozenset({"unknown", "none", "null", "n/a", "na"})
LlmPolicyMode = Literal["local_only", "external"]


def _normalize_required_gateway_app_id(value: object) -> str:
    app_id = str(value or "").strip().lower()
    if not app_id or app_id in _FORBIDDEN_GATEWAY_APP_IDS:
        raise ValueError("LLM app_id is required")
    return app_id


class AiGatewayPolicyViolation(ValueError):
    def __init__(
        self,
        *,
        reason_code: str,
        task_kind: str,
        requested_provider: str | None = None,
    ) -> None:
        self.reason_code = reason_code
        self.task_kind = task_kind
        self.requested_provider = requested_provider
        super().__init__(f"AI gateway policy violation: {reason_code} for task_kind={task_kind}")


@dataclass(frozen=True)
class AiGatewayContextPack:
    messages: list[dict[str, Any]]
    context_strategy: str = "domain_context_pack"
    estimated_input_tokens: int | None = None
    source_kinds: tuple[str, ...] = ()
    sensitivity_labels: tuple[str, ...] = ()
    content_origin: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AiGatewayRequest:
    task_kind: str
    source: str
    messages: list[dict[str, Any]] = field(default_factory=list)
    actor_user_id: str | None = None
    app: str | None = None
    workload_id: str | None = None
    workload_route: Literal["local", "external"] | None = field(
        default=None,
        repr=False,
    )
    workload_config: LlmPoolConfig | None = field(default=None, repr=False)
    workload_local_max_output_tokens: int | None = field(default=None, repr=False)
    workload_external_max_output_tokens: int | None = field(default=None, repr=False)
    pool_hint: LlmPoolHint | None = None
    stream: bool = False
    stream_reasoning: bool = True
    audit_entity_id: str | None = None
    principal_kind: Literal["user", "service_account", "system"] = "user"
    principal_id: str | None = None
    requested_model: str | None = None
    requested_provider: str | None = None
    max_tokens: int | None = None
    reasoning_effort: str | None = None
    temperature: float | None = None
    extra_body: Mapping[str, Any] | None = None
    timeout_seconds: float | None = None
    tools: list[dict[str, Any]] | None = None
    tool_choice: str | dict[str, Any] | None = None
    parallel_tool_calls: bool | None = None
    context_pack: AiGatewayContextPack | None = None
    agent_run_id: str | None = None
    conversation_id: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "app", _normalize_required_gateway_app_id(self.app))
        if self.workload_id is not None:
            normalized_workload_id = self.workload_id.strip().lower()
            if not normalized_workload_id:
                raise ValueError("LLM workload_id must not be blank")
            object.__setattr__(self, "workload_id", normalized_workload_id)
        if self.workload_route is not None and self.workload_route not in {
            "local",
            "external",
        }:
            raise ValueError("Invalid LLM workload route")

    @property
    def resolved_messages(self) -> list[dict[str, Any]]:
        if self.context_pack is not None:
            return list(self.context_pack.messages)
        return list(self.messages)

    @property
    def context_strategy(self) -> str:
        if self.context_pack is not None:
            return self.context_pack.context_strategy
        return "raw_messages"

    @property
    def estimated_input_tokens(self) -> int | None:
        if self.context_pack is not None:
            return self.context_pack.estimated_input_tokens
        return None

    @property
    def source_kinds(self) -> tuple[str, ...]:
        if self.context_pack is not None:
            return normalize_external_safety_values(self.context_pack.source_kinds)
        return ()

    @property
    def sensitivity_labels(self) -> tuple[str, ...]:
        if self.context_pack is not None:
            return normalize_external_safety_values(self.context_pack.sensitivity_labels)
        return ()

    @property
    def content_origin(self) -> str:
        if self.context_pack is not None:
            return normalize_content_origin(self.context_pack.content_origin or "internal_context")
        return normalize_content_origin("user_prompt")

    def task_context(self) -> LlmTaskContext:
        return LlmTaskContext(
            source=self.source,
            actor_user_id=self.actor_user_id,
            task_kind=self.task_kind,
            app_id=self.app,
            workload_id=self.workload_id,
            principal_kind=self.principal_kind,
            principal_id=self.principal_id,
        )


def ai_gateway_request_from_task_context(
    context: LlmTaskContext,
    *,
    messages: list[dict[str, Any]] | None = None,
    app: str | None = None,
    pool_hint: LlmPoolHint | None = None,
    stream: bool = False,
    stream_reasoning: bool = True,
    audit_entity_id: str | None = None,
    requested_model: str | None = None,
    requested_provider: str | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    temperature: float | None = None,
    extra_body: Mapping[str, Any] | None = None,
    timeout_seconds: float | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    context_pack: AiGatewayContextPack | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
) -> AiGatewayRequest:
    resolved_app = _normalize_required_gateway_app_id(app or context.app_id)
    if app is not None and resolved_app != context.app_id:
        raise ValueError("LLM app_id mismatch")
    return AiGatewayRequest(
        task_kind=context.task_kind,
        source=context.source,
        messages=list(messages or []),
        actor_user_id=context.actor_user_id,
        app=resolved_app,
        workload_id=context.workload_id,
        pool_hint=pool_hint,
        stream=stream,
        stream_reasoning=stream_reasoning,
        audit_entity_id=audit_entity_id,
        principal_kind=context.principal_kind,
        principal_id=context.principal_id,
        requested_model=requested_model,
        requested_provider=requested_provider,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        temperature=temperature,
        extra_body=extra_body,
        timeout_seconds=timeout_seconds,
        tools=tools,
        tool_choice=tool_choice,
        parallel_tool_calls=parallel_tool_calls,
        context_pack=context_pack,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )


def ai_gateway_execution_from_resolved(
    request: AiGatewayRequest,
    execution: ResolvedLlmExecution,
) -> "AiGatewayExecution":
    return AiGatewayExecution(
        request=request,
        llm_context=request.task_context(),
        messages=request.resolved_messages,
        llm_execution=execution,
        decision=AiGatewayDecision.from_execution(
            request=request,
            execution=execution,
        ),
    )


@dataclass(frozen=True)
class AiGatewayDecision:
    task_kind: str
    workload_id: str | None
    policy: LlmPolicyMode
    chosen_pool: str
    provider: str
    model: str
    reason_codes: tuple[str, ...]
    forced_local: bool
    pii_hits: tuple[str, ...]
    blocked_entity_types: tuple[str, ...]
    sensitivity_labels: tuple[str, ...]
    content_origin: str
    source_kinds: tuple[str, ...]
    egress_reason: str | None
    ai_security_policy_effect: str | None
    ai_security_policy_rule_id: str | None
    ai_security_policy_reason: str | None
    ai_security_policy_audit_only: bool
    custom_block_term_count: int
    mask_applied: bool
    masked_entity_types: tuple[str, ...]
    masked_text_count: int
    privacy_filter_status: str | None
    privacy_filter_used: bool
    privacy_filter_entity_types: tuple[str, ...]
    privacy_filter_match_count: int
    external_transfer_exception_id: str | None
    external_transfer_exception_name: str | None
    external_transfer_exception_reason: str | None
    external_transfer_exception_blockers: tuple[str, ...]
    ai_security_pipeline_exemption_id: str | None
    ai_security_pipeline_exemption_name: str | None
    ai_security_pipeline_exemption_reason: str | None
    context_strategy: str
    estimated_input_tokens: int | None
    max_tokens: int

    @classmethod
    def from_execution(
        cls,
        *,
        request: AiGatewayRequest,
        execution: ResolvedLlmExecution,
        reason_codes: tuple[str, ...] | None = None,
        egress_decision: ExternalPayloadSafetyDecision | None = None,
        security_decision: AiSecurityPolicyDecision | None = None,
        external_transfer_exception: AiSecurityExternalTransferExceptionDecision | None = None,
        security_pipeline_exemption: AiSecurityPipelineExemptionDecision | None = None,
        masking_result: ExternalPayloadMaskingResult | None = None,
    ) -> "AiGatewayDecision":
        policy_decision = execution.decision
        resolved_reason_codes = reason_codes or tuple(
            code for code in (policy_decision.reason,) if code
        )
        pii_hits = tuple(
            _merge_tuple_values(
                tuple(policy_decision.pii_hits),
                egress_decision.pii_hits if egress_decision is not None else (),
                masking_result.pii_hits if masking_result is not None else (),
            )
        )
        return cls(
            task_kind=request.task_kind,
            workload_id=request.workload_id,
            policy=policy_decision.policy,
            chosen_pool=policy_decision.chosen_pool,
            provider=execution.config.provider,
            model=execution.chosen_model,
            reason_codes=resolved_reason_codes,
            forced_local=policy_decision.forced_local,
            pii_hits=pii_hits,
            blocked_entity_types=(
                _merge_tuple_values(
                    egress_decision.blocked_entity_types if egress_decision is not None else (),
                    (
                        _merge_tuple_values(
                            masking_result.masked_entity_types,
                            masking_result.blocker_types,
                        )
                        if masking_result is not None
                        else ()
                    ),
                    (
                        (CUSTOM_BLOCK_ENTITY_TYPE,)
                        if security_decision is not None
                        and security_decision.custom_block_term_count > 0
                        else ()
                    ),
                )
            ),
            sensitivity_labels=(
                egress_decision.sensitivity_labels
                if egress_decision is not None
                else request.sensitivity_labels
            ),
            content_origin=(
                egress_decision.content_origin
                if egress_decision is not None
                else request.content_origin
            ),
            source_kinds=(
                egress_decision.source_kinds
                if egress_decision is not None
                else request.source_kinds
            ),
            egress_reason=egress_decision.reason_code if egress_decision is not None else None,
            ai_security_policy_effect=(
                security_decision.effect if security_decision is not None else None
            ),
            ai_security_policy_rule_id=(
                security_decision.rule_id if security_decision is not None else None
            ),
            ai_security_policy_reason=(
                security_decision.reason_code if security_decision is not None else None
            ),
            ai_security_policy_audit_only=(
                security_decision.audit_only if security_decision is not None else False
            ),
            custom_block_term_count=(
                security_decision.custom_block_term_count if security_decision is not None else 0
            ),
            mask_applied=masking_result.mask_applied if masking_result is not None else False,
            masked_entity_types=(
                masking_result.masked_entity_types if masking_result is not None else ()
            ),
            masked_text_count=(
                masking_result.masked_text_count if masking_result is not None else 0
            ),
            privacy_filter_status=(
                masking_result.privacy_filter_status if masking_result is not None else None
            ),
            privacy_filter_used=(
                masking_result.privacy_filter_used if masking_result is not None else False
            ),
            privacy_filter_entity_types=(
                masking_result.privacy_filter_entity_types if masking_result is not None else ()
            ),
            privacy_filter_match_count=(
                masking_result.privacy_filter_match_count if masking_result is not None else 0
            ),
            external_transfer_exception_id=(
                external_transfer_exception.exception_id
                if external_transfer_exception is not None and external_transfer_exception.allowed
                else None
            ),
            external_transfer_exception_name=(
                external_transfer_exception.exception_name
                if external_transfer_exception is not None and external_transfer_exception.allowed
                else None
            ),
            external_transfer_exception_reason=(
                external_transfer_exception.reason_code
                if external_transfer_exception is not None and external_transfer_exception.allowed
                else None
            ),
            external_transfer_exception_blockers=(
                external_transfer_exception.matched_blocker_types
                if external_transfer_exception is not None and external_transfer_exception.allowed
                else ()
            ),
            ai_security_pipeline_exemption_id=(
                security_pipeline_exemption.exemption_id
                if security_pipeline_exemption is not None and security_pipeline_exemption.allowed
                else None
            ),
            ai_security_pipeline_exemption_name=(
                security_pipeline_exemption.exemption_name
                if security_pipeline_exemption is not None and security_pipeline_exemption.allowed
                else None
            ),
            ai_security_pipeline_exemption_reason=(
                security_pipeline_exemption.reason_code
                if security_pipeline_exemption is not None and security_pipeline_exemption.allowed
                else None
            ),
            context_strategy=request.context_strategy,
            estimated_input_tokens=request.estimated_input_tokens,
            max_tokens=execution.resolved_max_tokens,
        )


@dataclass(frozen=True)
class AiGatewayExecution:
    request: AiGatewayRequest
    llm_context: LlmTaskContext
    messages: list[dict[str, Any]]
    llm_execution: ResolvedLlmExecution
    decision: AiGatewayDecision
    detected_values: tuple[AiSecurityDetectedValueInput, ...] = ()


@dataclass(frozen=True)
class AiGatewayResponse:
    response: Any
    decision: AiGatewayDecision
    config: LlmPoolConfig


@dataclass(frozen=True)
class LlmWorkloadContext:
    source: str
    actor_user_id: str | None = None
    principal_kind: Literal["user", "service_account", "system"] = "user"
    principal_id: str | None = None
    app_id: str | None = None

    @classmethod
    def from_task_context(cls, context: LlmTaskContext) -> "LlmWorkloadContext":
        return cls(
            source=context.source,
            actor_user_id=context.actor_user_id,
            principal_kind=context.principal_kind,
            principal_id=context.principal_id,
            app_id=context.app_id,
        )


@dataclass(frozen=True)
class LlmWorkloadResult:
    completion: LlmCompletionResult
    decision: AiGatewayDecision
    config: LlmPoolConfig


def resolve_llm_workload_route(
    workload_id: str,
    db: Session,
    *,
    model_role: str = "default",
) -> ResolvedLlmWorkloadRoute:
    """Resolve the admin-selected route without executing it."""

    return resolve_ai_model_workload_route(
        db,
        workload_id=workload_id,
        model_role=model_role,
    )


def execute_llm(
    workload_id: str,
    context: LlmWorkloadContext,
    db: Session,
    *,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    timeout_seconds: float | None = None,
    extra_body: Mapping[str, Any] | None = None,
    stream_reasoning: bool = True,
    audit_entity_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    context_pack: AiGatewayContextPack | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
) -> LlmWorkloadResult:
    """Execute one registered workload without exposing route/model controls."""

    request = build_llm_workload_request(
        workload_id,
        context,
        db,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        extra_body=extra_body,
        stream=False,
        stream_reasoning=stream_reasoning,
        audit_entity_id=audit_entity_id,
        tools=tools,
        tool_choice=tool_choice,
        parallel_tool_calls=parallel_tool_calls,
        context_pack=context_pack,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )
    completion, decision, config = complete_gateway_chat_text(request, db)
    return LlmWorkloadResult(
        completion=completion,
        decision=decision,
        config=config,
    )


async def stream_llm(
    workload_id: str,
    context: LlmWorkloadContext,
    db: Session,
    *,
    messages: list[dict[str, Any]],
    temperature: float | None = None,
    max_tokens: int | None = None,
    reasoning_effort: str | None = None,
    timeout_seconds: float | None = None,
    extra_body: Mapping[str, Any] | None = None,
    stream_reasoning: bool = True,
    audit_entity_id: str | None = None,
    tools: list[dict[str, Any]] | None = None,
    tool_choice: str | dict[str, Any] | None = None,
    parallel_tool_calls: bool | None = None,
    context_pack: AiGatewayContextPack | None = None,
    agent_run_id: str | None = None,
    conversation_id: str | None = None,
) -> AsyncIterator[tuple[StreamChunk, AiGatewayDecision, LlmPoolConfig]]:
    """Stream one registered workload through the same routing seam."""

    request = build_llm_workload_request(
        workload_id,
        context,
        db,
        messages=messages,
        temperature=temperature,
        max_tokens=max_tokens,
        reasoning_effort=reasoning_effort,
        timeout_seconds=timeout_seconds,
        extra_body=extra_body,
        stream=True,
        stream_reasoning=stream_reasoning,
        audit_entity_id=audit_entity_id,
        tools=tools,
        tool_choice=tool_choice,
        parallel_tool_calls=parallel_tool_calls,
        context_pack=context_pack,
        agent_run_id=agent_run_id,
        conversation_id=conversation_id,
    )
    async for item in complete_gateway_chat_stream(request, db):
        yield item


def build_llm_workload_request(
    workload_id: str,
    context: LlmWorkloadContext,
    db: Session,
    **request_values: Any,
) -> AiGatewayRequest:
    try:
        route = resolve_llm_workload_route(workload_id, db)
    except AiModelSettingsError as error:
        raise LlmProviderError(error.code) from error
    workload = route.workload
    app_id = (context.app_id or workload.app_id).strip().lower()
    if app_id not in workload.app_ids:
        raise ValueError(f"LLM workload {workload.workload_id} is not registered for app {app_id}")
    if context.app_id is None and len(workload.app_ids) != 1:
        raise ValueError(
            f"LLM workload {workload.workload_id} requires an explicit registered app_id"
        )

    runtime_config = build_resolved_llm_pool_config(route)
    requested_max_tokens = request_values.get("max_tokens")
    request_values["max_tokens"] = min(
        int(requested_max_tokens) if requested_max_tokens is not None else route.max_output_tokens,
        route.max_output_tokens,
    )
    if route.route == "external":
        request_values["extra_body"] = None
    return AiGatewayRequest(
        task_kind=workload.task_kind,
        workload_id=workload.workload_id,
        workload_route=route.route,
        workload_config=runtime_config,
        workload_local_max_output_tokens=route.local_max_output_tokens,
        workload_external_max_output_tokens=route.external_max_output_tokens,
        source=context.source,
        actor_user_id=context.actor_user_id,
        app=app_id,
        principal_kind=context.principal_kind,
        principal_id=context.principal_id,
        pool_hint="local" if route.route == "local" else None,
        requested_provider=route.provider_id if route.route == "external" else None,
        requested_model=route.model_key,
        **request_values,
    )


def resolve_gateway_execution(
    request: AiGatewayRequest,
    db: Session,
) -> AiGatewayExecution:
    """Resolve one registered workload without allowing policy-driven rerouting."""

    _validate_registered_workload_request(request)
    llm_context = request.task_context()
    messages = request.resolved_messages
    if request.workload_route == "local":
        return _resolved_registered_gateway_execution(
            request=request,
            llm_context=llm_context,
            messages=messages,
        )

    security_scan_texts = tuple(_collect_gateway_text_inputs(messages))
    security_enforcement_enabled = ai_security_enforcement_enabled(db)
    if ai_security_enforcement_required(
        environment=get_settings().environment,
        enforcement_enabled=security_enforcement_enabled,
    ):
        _raise_ai_security_enforcement_required(request)
    security_pipeline_exemption = resolve_ai_security_pipeline_exemption(
        AiSecurityPolicyContext(
            actor_user_id=request.actor_user_id,
            app_id=request.app,
            task_kind=request.task_kind,
            capability=AI_SECURITY_LLM_CAPABILITY,
            provider=request.requested_provider,
        )
    )
    if security_pipeline_exemption.allowed:
        return _resolved_registered_gateway_execution(
            request=request,
            llm_context=llm_context,
            messages=messages,
            reason_codes=(AI_SECURITY_PIPELINE_EXEMPT_REASON,),
            egress_decision=_allowed_request_egress(
                request,
                reason_code=AI_SECURITY_PIPELINE_EXEMPT_REASON,
            ),
            security_pipeline_exemption=security_pipeline_exemption,
        )
    if not security_enforcement_enabled:
        return _resolved_registered_gateway_execution(
            request=request,
            llm_context=llm_context,
            messages=messages,
            reason_codes=(AI_SECURITY_ENFORCEMENT_DISABLED_REASON,),
            egress_decision=_allowed_request_egress(
                request,
                reason_code=AI_SECURITY_ENFORCEMENT_DISABLED_REASON,
            ),
            security_decision=AiSecurityPolicyDecision(
                reason_code=AI_SECURITY_ENFORCEMENT_DISABLED_REASON
            ),
        )
    egress_decision = _evaluate_request_egress(request, messages)
    security_decision = evaluate_ai_security_policy(
        db,
        AiSecurityPolicyContext(
            actor_user_id=request.actor_user_id,
            app_id=request.app,
            task_kind=request.task_kind,
            capability=AI_SECURITY_LLM_CAPABILITY,
            provider=request.requested_provider,
        ),
        security_scan_texts,
    )
    external_transfer_exception = AiSecurityExternalTransferExceptionDecision()
    masking_result: ExternalPayloadMaskingResult | None = None
    external_transfer_blockers = external_transfer_blockers_from_safety(
        egress_decision,
        custom_block_term_count=security_decision.custom_block_term_count,
        policy_block_external=security_decision.effect == "block_external",
    )
    hard_blockers = hard_external_transfer_blockers(external_transfer_blockers)
    if hard_blockers:
        _raise_external_transfer_blocked(
            request,
            egress_decision=egress_decision,
            security_decision=security_decision,
        )

    if security_decision.effect == "mask_and_send":
        masking_result = evaluate_external_payload_masking(
            _collect_gateway_text_inputs(messages),
            safety_decision=egress_decision,
            custom_block_term_count=security_decision.custom_block_term_count,
            unsupported_content=_has_unsupported_gateway_content(messages),
        )
        if masking_result.allowed:
            if masking_result.mask_applied:
                messages = _replace_gateway_text_inputs(messages, masking_result.masked_texts)
            external_transfer_blockers = ()
        else:
            _raise_external_transfer_blocked(
                request,
                egress_decision=egress_decision,
                security_decision=security_decision,
                masking_result=masking_result,
            )
    else:
        if external_transfer_blockers:
            external_transfer_exception = resolve_ai_security_external_transfer_exception(
                db,
                AiSecurityPolicyContext(
                    actor_user_id=request.actor_user_id,
                    app_id=request.app,
                    task_kind=request.task_kind,
                    capability=AI_SECURITY_LLM_CAPABILITY,
                    provider=request.requested_provider,
                ),
                external_transfer_blockers,
            )
            if external_transfer_exception.allowed:
                external_transfer_blockers = ()
        if not external_transfer_exception.allowed:
            global_action = _global_data_protection_action_for_blockers(
                db,
                external_transfer_blockers,
            )
            if global_action == "mask_and_send":
                masking_result = evaluate_external_payload_masking(
                    _collect_gateway_text_inputs(messages),
                    safety_decision=egress_decision,
                    custom_block_term_count=security_decision.custom_block_term_count,
                    unsupported_content=_has_unsupported_gateway_content(messages),
                )
                if masking_result.allowed:
                    if masking_result.mask_applied:
                        messages = _replace_gateway_text_inputs(
                            messages,
                            masking_result.masked_texts,
                        )
                    external_transfer_blockers = ()
                else:
                    _raise_external_transfer_blocked(
                        request,
                        egress_decision=egress_decision,
                        security_decision=security_decision,
                        masking_result=masking_result,
                    )
            elif global_action == "block":
                _raise_external_transfer_blocked(
                    request,
                    egress_decision=egress_decision,
                    security_decision=security_decision,
                )
    masking_allowed = masking_result is not None and masking_result.allowed
    if (
        not external_transfer_exception.allowed
        and not masking_allowed
        and external_transfer_blockers
    ):
        _raise_external_transfer_blocked(
            request,
            egress_decision=egress_decision,
            security_decision=security_decision,
            masking_result=masking_result,
        )

    reason_codes: tuple[str, ...] | None = None
    if external_transfer_exception.allowed:
        reason_codes = _merge_tuple_values(
            (EXTERNAL_TRANSFER_EXCEPTION_REASON,),
            _gateway_security_reason_codes(security_decision),
        )
    elif masking_result is not None and masking_result.allowed:
        reason_codes = _merge_tuple_values(
            (masking_result.reason_code,) if masking_result.mask_applied else (),
            _gateway_security_reason_codes(security_decision),
        )
    elif security_decision.audit_only:
        reason_codes = _gateway_security_reason_codes(security_decision)

    return _resolved_registered_gateway_execution(
        request=request,
        llm_context=llm_context,
        messages=messages,
        reason_codes=reason_codes,
        egress_decision=egress_decision,
        security_decision=security_decision,
        external_transfer_exception=external_transfer_exception,
        masking_result=masking_result,
        security_scan_texts=security_scan_texts,
    )


def _validate_registered_workload_request(request: AiGatewayRequest) -> None:
    if request.workload_id is None:
        raise AiGatewayPolicyViolation(
            reason_code=_UNKNOWN_TASK_KIND_REASON,
            task_kind=request.task_kind,
            requested_provider=request.requested_provider,
        )
    if request.workload_route == "external":
        allowed_providers = parse_external_llm_provider_allowlist(
            get_settings().llm_external_allowed_providers
        )
        if request.requested_provider not in allowed_providers:
            raise AiGatewayPolicyViolation(
                reason_code="provider_not_allowed",
                task_kind=request.task_kind,
                requested_provider=request.requested_provider,
            )
    workload = get_ai_capability_registry().get_llm_workload(request.workload_id)
    if (
        workload is None
        or request.task_kind != workload.task_kind
        or request.app not in workload.app_ids
        or request.workload_route not in workload.allowed_routes
        or request.workload_config is None
        or request.workload_config.pool != request.workload_route
    ):
        raise AiGatewayPolicyViolation(
            reason_code=_UNKNOWN_TASK_KIND_REASON,
            task_kind=request.task_kind,
            requested_provider=request.requested_provider,
        )


def _resolved_registered_gateway_execution(
    *,
    request: AiGatewayRequest,
    llm_context: LlmTaskContext,
    messages: list[dict[str, Any]],
    reason_codes: tuple[str, ...] | None = None,
    egress_decision: ExternalPayloadSafetyDecision | None = None,
    security_decision: AiSecurityPolicyDecision | None = None,
    external_transfer_exception: AiSecurityExternalTransferExceptionDecision | None = None,
    security_pipeline_exemption: AiSecurityPipelineExemptionDecision | None = None,
    masking_result: ExternalPayloadMaskingResult | None = None,
    security_scan_texts: tuple[str, ...] = (),
) -> AiGatewayExecution:
    config = request.workload_config
    if config is None:  # guarded by _validate_registered_workload_request
        raise RuntimeError("Registered LLM workload config is required")
    execution = resolve_registered_chat_execution(
        llm_context,
        config=config,
        max_tokens=request.max_tokens,
        reasoning_effort=request.reasoning_effort,
        model=request.requested_model,
    )
    execution = _clamp_workload_max_output_tokens(request, execution)
    decision = AiGatewayDecision.from_execution(
        request=request,
        execution=execution,
        reason_codes=reason_codes,
        egress_decision=egress_decision,
        security_decision=security_decision,
        external_transfer_exception=external_transfer_exception,
        security_pipeline_exemption=security_pipeline_exemption,
        masking_result=masking_result,
    )
    detected_values = (
        collect_ai_security_detected_values(
            security_scan_texts,
            custom_block_terms=(
                security_decision.custom_block_terms if security_decision is not None else ()
            ),
            privacy_filter_entity_types=decision.privacy_filter_entity_types,
            privacy_filter_match_count=decision.privacy_filter_match_count,
        )
        if security_scan_texts
        else ()
    )
    return AiGatewayExecution(
        request=request,
        llm_context=llm_context,
        messages=messages,
        llm_execution=execution,
        decision=decision,
        detected_values=detected_values,
    )


def _raise_external_transfer_blocked(
    request: AiGatewayRequest,
    *,
    egress_decision: ExternalPayloadSafetyDecision,
    security_decision: AiSecurityPolicyDecision,
    masking_result: ExternalPayloadMaskingResult | None = None,
) -> None:
    config = request.workload_config
    if config is not None:
        detected_values = collect_ai_security_detected_values(
            tuple(_collect_gateway_text_inputs(request.resolved_messages)),
            custom_block_terms=security_decision.custom_block_terms,
            privacy_filter_entity_types=(
                masking_result.privacy_filter_entity_types if masking_result is not None else ()
            ),
            privacy_filter_match_count=(
                masking_result.privacy_filter_match_count if masking_result is not None else 0
            ),
        )
        log_llm_call(
            source=request.source,
            actor_user_id=request.actor_user_id,
            principal_kind=request.principal_kind,
            principal_id=request.principal_id,
            task_kind=request.task_kind,
            workload_id=request.workload_id,
            app_id=request.app or "",
            policy="external",
            chosen_pool="external",
            decision_reason="external_transfer_blocked",
            forced_local=False,
            pii_hits=list(egress_decision.pii_hits),
            model=request.requested_model or config.default_model,
            status="blocked_external",
            latency_ms=0,
            max_tokens=request.max_tokens,
            context_strategy=request.context_strategy,
            estimated_input_tokens=request.estimated_input_tokens,
            sensitivity_labels=list(egress_decision.sensitivity_labels),
            blocked_entity_types=list(egress_decision.blocked_entity_types),
            content_origin=egress_decision.content_origin,
            source_kinds=list(egress_decision.source_kinds),
            ai_security_policy_effect=security_decision.effect,
            ai_security_policy_rule_id=security_decision.rule_id,
            ai_security_policy_reason=security_decision.reason_code,
            ai_security_policy_audit_only=security_decision.audit_only,
            custom_block_term_count=security_decision.custom_block_term_count,
            mask_applied=masking_result.mask_applied if masking_result is not None else False,
            masked_entity_types=(
                list(masking_result.masked_entity_types) if masking_result is not None else []
            ),
            masked_text_count=(
                masking_result.masked_text_count if masking_result is not None else 0
            ),
            privacy_filter_status=(
                masking_result.privacy_filter_status if masking_result is not None else None
            ),
            privacy_filter_used=(
                masking_result.privacy_filter_used if masking_result is not None else False
            ),
            entity_id=request.audit_entity_id,
            agent_run_id=request.agent_run_id,
            conversation_id=request.conversation_id,
            detected_values=serialize_detected_values(detected_values),
        )
    raise AiGatewayPolicyViolation(
        reason_code="external_transfer_blocked",
        task_kind=request.task_kind,
        requested_provider=request.requested_provider,
    )


def _raise_ai_security_enforcement_required(request: AiGatewayRequest) -> None:
    config = request.workload_config
    if config is not None:
        log_llm_call(
            source=request.source,
            actor_user_id=request.actor_user_id,
            principal_kind=request.principal_kind,
            principal_id=request.principal_id,
            task_kind=request.task_kind,
            workload_id=request.workload_id,
            app_id=request.app or "",
            policy="external",
            chosen_pool="external",
            decision_reason=AI_SECURITY_ENFORCEMENT_REQUIRED_REASON,
            forced_local=False,
            pii_hits=[],
            model=request.requested_model or config.default_model,
            status="blocked_external",
            latency_ms=0,
            max_tokens=request.max_tokens,
            context_strategy=request.context_strategy,
            estimated_input_tokens=request.estimated_input_tokens,
            sensitivity_labels=list(request.sensitivity_labels),
            blocked_entity_types=[],
            content_origin=normalize_content_origin(request.content_origin),
            source_kinds=list(request.source_kinds),
            ai_security_policy_reason=AI_SECURITY_ENFORCEMENT_REQUIRED_REASON,
            entity_id=request.audit_entity_id,
            agent_run_id=request.agent_run_id,
            conversation_id=request.conversation_id,
            detected_values=[],
        )
    raise AiGatewayPolicyViolation(
        reason_code=AI_SECURITY_ENFORCEMENT_REQUIRED_REASON,
        task_kind=request.task_kind,
        requested_provider=request.requested_provider,
    )


def complete_gateway_chat(
    request: AiGatewayRequest,
    db: Session,
) -> AiGatewayResponse:
    gateway_execution = resolve_gateway_execution(request, db)
    return complete_resolved_gateway_chat(gateway_execution, db)


def complete_resolved_gateway_chat(
    gateway_execution: AiGatewayExecution,
    db: Session,
) -> AiGatewayResponse:
    request = gateway_execution.request
    response, _decision, config = _complete_chat(
        gateway_execution.llm_context,
        db,
        messages=gateway_execution.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        reasoning_effort=request.reasoning_effort,
        extra_body=request.extra_body,
        timeout_seconds=request.timeout_seconds,
        model=request.requested_model,
        audit_entity_id=request.audit_entity_id,
        pool_hint=request.pool_hint,
        external_provider=request.requested_provider,
        tools=request.tools,
        tool_choice=request.tool_choice,
        parallel_tool_calls=request.parallel_tool_calls,
        resolved_execution=gateway_execution.llm_execution,
        agent_run_id=request.agent_run_id,
        conversation_id=request.conversation_id,
        audit_context_strategy=gateway_execution.decision.context_strategy,
        audit_estimated_input_tokens=gateway_execution.decision.estimated_input_tokens,
        audit_sensitivity_labels=gateway_execution.decision.sensitivity_labels,
        audit_blocked_entity_types=gateway_execution.decision.blocked_entity_types,
        audit_content_origin=gateway_execution.decision.content_origin,
        audit_source_kinds=gateway_execution.decision.source_kinds,
        audit_ai_security_policy_effect=(gateway_execution.decision.ai_security_policy_effect),
        audit_ai_security_policy_rule_id=(gateway_execution.decision.ai_security_policy_rule_id),
        audit_ai_security_policy_reason=(gateway_execution.decision.ai_security_policy_reason),
        audit_ai_security_policy_audit_only=(
            gateway_execution.decision.ai_security_policy_audit_only
        ),
        audit_custom_block_term_count=(gateway_execution.decision.custom_block_term_count),
        audit_external_transfer_exception_id=(
            gateway_execution.decision.external_transfer_exception_id
        ),
        audit_external_transfer_exception_name=(
            gateway_execution.decision.external_transfer_exception_name
        ),
        audit_external_transfer_exception_reason=(
            gateway_execution.decision.external_transfer_exception_reason
        ),
        audit_external_transfer_exception_blockers=(
            gateway_execution.decision.external_transfer_exception_blockers
        ),
        audit_ai_security_pipeline_exemption_id=(
            gateway_execution.decision.ai_security_pipeline_exemption_id
        ),
        audit_ai_security_pipeline_exemption_name=(
            gateway_execution.decision.ai_security_pipeline_exemption_name
        ),
        audit_ai_security_pipeline_exemption_reason=(
            gateway_execution.decision.ai_security_pipeline_exemption_reason
        ),
        audit_mask_applied=gateway_execution.decision.mask_applied,
        audit_masked_entity_types=gateway_execution.decision.masked_entity_types,
        audit_masked_text_count=gateway_execution.decision.masked_text_count,
        audit_privacy_filter_status=gateway_execution.decision.privacy_filter_status,
        audit_privacy_filter_used=gateway_execution.decision.privacy_filter_used,
        audit_detected_values=serialize_detected_values(
            gateway_execution.detected_values,
        ),
    )
    return AiGatewayResponse(
        response=response,
        decision=gateway_execution.decision,
        config=config,
    )


def complete_gateway_chat_text(
    request: AiGatewayRequest,
    db: Session,
) -> tuple[LlmCompletionResult, AiGatewayDecision, LlmPoolConfig]:
    gateway_execution = resolve_gateway_execution(request, db)
    return complete_resolved_gateway_chat_text(gateway_execution, db)


def complete_resolved_gateway_chat_text(
    gateway_execution: AiGatewayExecution,
    db: Session,
) -> tuple[LlmCompletionResult, AiGatewayDecision, LlmPoolConfig]:
    request = gateway_execution.request
    completion, _decision, config = _complete_chat_text(
        gateway_execution.llm_context,
        db,
        messages=gateway_execution.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        reasoning_effort=request.reasoning_effort,
        extra_body=request.extra_body,
        timeout_seconds=request.timeout_seconds,
        model=request.requested_model,
        audit_entity_id=request.audit_entity_id,
        pool_hint=request.pool_hint,
        external_provider=request.requested_provider,
        tools=request.tools,
        tool_choice=request.tool_choice,
        parallel_tool_calls=request.parallel_tool_calls,
        resolved_execution=gateway_execution.llm_execution,
        agent_run_id=request.agent_run_id,
        conversation_id=request.conversation_id,
        audit_context_strategy=gateway_execution.decision.context_strategy,
        audit_estimated_input_tokens=gateway_execution.decision.estimated_input_tokens,
        audit_sensitivity_labels=gateway_execution.decision.sensitivity_labels,
        audit_blocked_entity_types=gateway_execution.decision.blocked_entity_types,
        audit_content_origin=gateway_execution.decision.content_origin,
        audit_source_kinds=gateway_execution.decision.source_kinds,
        audit_ai_security_policy_effect=(gateway_execution.decision.ai_security_policy_effect),
        audit_ai_security_policy_rule_id=(gateway_execution.decision.ai_security_policy_rule_id),
        audit_ai_security_policy_reason=(gateway_execution.decision.ai_security_policy_reason),
        audit_ai_security_policy_audit_only=(
            gateway_execution.decision.ai_security_policy_audit_only
        ),
        audit_custom_block_term_count=(gateway_execution.decision.custom_block_term_count),
        audit_external_transfer_exception_id=(
            gateway_execution.decision.external_transfer_exception_id
        ),
        audit_external_transfer_exception_name=(
            gateway_execution.decision.external_transfer_exception_name
        ),
        audit_external_transfer_exception_reason=(
            gateway_execution.decision.external_transfer_exception_reason
        ),
        audit_external_transfer_exception_blockers=(
            gateway_execution.decision.external_transfer_exception_blockers
        ),
        audit_ai_security_pipeline_exemption_id=(
            gateway_execution.decision.ai_security_pipeline_exemption_id
        ),
        audit_ai_security_pipeline_exemption_name=(
            gateway_execution.decision.ai_security_pipeline_exemption_name
        ),
        audit_ai_security_pipeline_exemption_reason=(
            gateway_execution.decision.ai_security_pipeline_exemption_reason
        ),
        audit_mask_applied=gateway_execution.decision.mask_applied,
        audit_masked_entity_types=gateway_execution.decision.masked_entity_types,
        audit_masked_text_count=gateway_execution.decision.masked_text_count,
        audit_privacy_filter_status=gateway_execution.decision.privacy_filter_status,
        audit_privacy_filter_used=gateway_execution.decision.privacy_filter_used,
        audit_detected_values=serialize_detected_values(
            gateway_execution.detected_values,
        ),
    )
    return completion, gateway_execution.decision, config


async def complete_gateway_chat_stream(
    request: AiGatewayRequest,
    db: Session,
) -> AsyncIterator[tuple[StreamChunk, AiGatewayDecision, LlmPoolConfig]]:
    gateway_execution = resolve_gateway_execution(request, db)
    async for chunk, decision, config in complete_resolved_gateway_chat_stream(
        gateway_execution,
        db,
    ):
        yield chunk, decision, config


async def complete_resolved_gateway_chat_stream(
    gateway_execution: AiGatewayExecution,
    db: Session,
) -> AsyncIterator[tuple[StreamChunk, AiGatewayDecision, LlmPoolConfig]]:
    request = gateway_execution.request
    async for chunk, _decision, config in _complete_chat_stream(
        gateway_execution.llm_context,
        db,
        messages=gateway_execution.messages,
        temperature=request.temperature,
        max_tokens=request.max_tokens,
        reasoning_effort=request.reasoning_effort,
        extra_body=request.extra_body,
        timeout_seconds=request.timeout_seconds,
        model=request.requested_model,
        audit_entity_id=request.audit_entity_id,
        pool_hint=request.pool_hint,
        external_provider=request.requested_provider,
        stream_reasoning=request.stream_reasoning,
        tools=request.tools,
        tool_choice=request.tool_choice,
        parallel_tool_calls=request.parallel_tool_calls,
        resolved_execution=gateway_execution.llm_execution,
        agent_run_id=request.agent_run_id,
        conversation_id=request.conversation_id,
        audit_context_strategy=gateway_execution.decision.context_strategy,
        audit_estimated_input_tokens=gateway_execution.decision.estimated_input_tokens,
        audit_sensitivity_labels=gateway_execution.decision.sensitivity_labels,
        audit_blocked_entity_types=gateway_execution.decision.blocked_entity_types,
        audit_content_origin=gateway_execution.decision.content_origin,
        audit_source_kinds=gateway_execution.decision.source_kinds,
        audit_ai_security_policy_effect=(gateway_execution.decision.ai_security_policy_effect),
        audit_ai_security_policy_rule_id=(gateway_execution.decision.ai_security_policy_rule_id),
        audit_ai_security_policy_reason=(gateway_execution.decision.ai_security_policy_reason),
        audit_ai_security_policy_audit_only=(
            gateway_execution.decision.ai_security_policy_audit_only
        ),
        audit_custom_block_term_count=(gateway_execution.decision.custom_block_term_count),
        audit_external_transfer_exception_id=(
            gateway_execution.decision.external_transfer_exception_id
        ),
        audit_external_transfer_exception_name=(
            gateway_execution.decision.external_transfer_exception_name
        ),
        audit_external_transfer_exception_reason=(
            gateway_execution.decision.external_transfer_exception_reason
        ),
        audit_external_transfer_exception_blockers=(
            gateway_execution.decision.external_transfer_exception_blockers
        ),
        audit_ai_security_pipeline_exemption_id=(
            gateway_execution.decision.ai_security_pipeline_exemption_id
        ),
        audit_ai_security_pipeline_exemption_name=(
            gateway_execution.decision.ai_security_pipeline_exemption_name
        ),
        audit_ai_security_pipeline_exemption_reason=(
            gateway_execution.decision.ai_security_pipeline_exemption_reason
        ),
        audit_mask_applied=gateway_execution.decision.mask_applied,
        audit_masked_entity_types=gateway_execution.decision.masked_entity_types,
        audit_masked_text_count=gateway_execution.decision.masked_text_count,
        audit_privacy_filter_status=gateway_execution.decision.privacy_filter_status,
        audit_privacy_filter_used=gateway_execution.decision.privacy_filter_used,
        audit_detected_values=serialize_detected_values(
            gateway_execution.detected_values,
        ),
    ):
        yield chunk, gateway_execution.decision, config


def _evaluate_request_egress(
    request: AiGatewayRequest,
    messages: list[dict[str, Any]],
) -> ExternalPayloadSafetyDecision:
    return evaluate_external_payload_safety(
        _collect_gateway_text_inputs(messages),
        content_origin=request.content_origin,
        source_kinds=request.source_kinds,
        sensitivity_labels=request.sensitivity_labels,
    )


def _allowed_request_egress(
    request: AiGatewayRequest,
    *,
    reason_code: str = AI_SECURITY_ENFORCEMENT_DISABLED_REASON,
) -> ExternalPayloadSafetyDecision:
    return ExternalPayloadSafetyDecision(
        allow_external=True,
        reason_code=reason_code,
        content_origin=normalize_content_origin(request.content_origin),
        source_kinds=normalize_external_safety_values(request.source_kinds),
        sensitivity_labels=normalize_external_safety_values(request.sensitivity_labels),
    )


def _clamp_workload_max_output_tokens(
    request: AiGatewayRequest,
    execution: ResolvedLlmExecution,
) -> ResolvedLlmExecution:
    route_max_output_tokens = (
        request.workload_local_max_output_tokens
        if execution.pool == "local"
        else request.workload_external_max_output_tokens
    )
    if route_max_output_tokens is None:
        return execution
    return replace(
        execution,
        resolved_max_tokens=min(execution.resolved_max_tokens, route_max_output_tokens),
    )


def _collect_gateway_text_inputs(messages: list[dict[str, Any]]) -> list[str]:
    out: list[str] = []
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if isinstance(content, str):
            out.append(content)
            continue
        if isinstance(content, list):
            for part in content:
                if isinstance(part, dict):
                    text = part.get("text")
                    if isinstance(text, str):
                        out.append(text)
    return out


def _global_data_protection_action_for_blockers(
    db: Session,
    blocker_types: tuple[str, ...],
) -> str | None:
    if not blocker_types:
        return None
    blocker_actions = ai_security_data_protection_blocker_actions(db)
    actionable_blockers = [blocker for blocker in blocker_types if blocker in blocker_actions]
    if not actionable_blockers:
        return None
    if len(actionable_blockers) != len(blocker_types):
        return None
    if all(blocker_actions[blocker] == "mask_and_send" for blocker in actionable_blockers):
        return "mask_and_send"
    return "block"


def _has_unsupported_gateway_content(messages: list[dict[str, Any]]) -> bool:
    for message in messages:
        content = message.get("content") if isinstance(message, dict) else None
        if content is None or isinstance(content, str):
            continue
        if not isinstance(content, list):
            return True
        for part in content:
            if not isinstance(part, dict):
                return True
            text = part.get("text")
            part_type = str(part.get("type") or "").strip().lower()
            if isinstance(text, str) and part_type in {"", "text", "input_text"}:
                continue
            return True
    return False


def _replace_gateway_text_inputs(
    messages: list[dict[str, Any]],
    replacements: tuple[str, ...],
) -> list[dict[str, Any]]:
    text_index = 0
    out: list[dict[str, Any]] = []
    for message in messages:
        if not isinstance(message, dict):
            out.append(message)
            continue
        next_message = dict(message)
        content = next_message.get("content")
        if isinstance(content, str):
            if text_index < len(replacements):
                next_message["content"] = replacements[text_index]
            text_index += 1
        elif isinstance(content, list):
            next_content: list[Any] = []
            for part in content:
                if isinstance(part, dict) and isinstance(part.get("text"), str):
                    next_part = dict(part)
                    if text_index < len(replacements):
                        next_part["text"] = replacements[text_index]
                    text_index += 1
                    next_content.append(next_part)
                else:
                    next_content.append(part)
            next_message["content"] = next_content
        out.append(next_message)
    return out


def _gateway_security_reason_codes(
    security_decision: AiSecurityPolicyDecision,
) -> tuple[str, ...]:
    if security_decision.reason_code == "no_matching_rule":
        return ()
    return (security_decision.reason_code,)


def _merge_tuple_values(*groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for group in groups:
        for value in group:
            if value not in merged:
                merged.append(value)
    return tuple(merged)


__all__ = [
    "AiGatewayContextPack",
    "AiGatewayDecision",
    "AiGatewayExecution",
    "AiGatewayPolicyViolation",
    "AiGatewayRequest",
    "AiGatewayResponse",
    "LlmWorkloadContext",
    "LlmWorkloadResult",
    "ai_gateway_execution_from_resolved",
    "ai_gateway_request_from_task_context",
    "build_llm_workload_request",
    "complete_gateway_chat",
    "complete_resolved_gateway_chat",
    "complete_resolved_gateway_chat_stream",
    "complete_resolved_gateway_chat_text",
    "complete_gateway_chat_stream",
    "complete_gateway_chat_text",
    "execute_llm",
    "resolve_llm_workload_route",
    "resolve_gateway_execution",
    "stream_llm",
]
