from __future__ import annotations

import asyncio
import time
from collections.abc import Awaitable, Callable, Mapping, Sequence
from dataclasses import dataclass, field
from typing import Any, TypeVar

from sqlalchemy.orm import Session

from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.domains.ai.audit import log_ai_external_call
from open_work_hub_api.domains.ai.boundary_safety import (
    ExternalPayloadSafetyDecision,
    evaluate_external_payload_safety,
    normalize_content_origin,
    normalize_external_safety_values,
)
from open_work_hub_api.domains.ai.masking import ExternalPayloadMaskingResult
from open_work_hub_api.domains.ai.masking import evaluate_external_payload_masking
from open_work_hub_api.domains.ai.runtime.external_egress import (
    ExternalCapability,
    allowed_external_providers,
    normalize_external_provider,
)
from open_work_hub_api.domains.ai.runtime.external_egress_sanitizer import (
    build_external_egress_sanitization,
)
from open_work_hub_api.domains.ai.security_detected_values import (
    collect_ai_security_detected_values,
    serialize_detected_values,
)
from open_work_hub_api.domains.ai.security_policy import (
    AI_SECURITY_ENFORCEMENT_DISABLED_REASON,
    AI_SECURITY_ENFORCEMENT_REQUIRED_REASON,
    CUSTOM_BLOCK_ENTITY_TYPE,
    CUSTOM_BLOCK_REASON,
    EXTERNAL_TRANSFER_EXCEPTION_REASON,
    POLICY_BLOCK_EXTERNAL_BLOCKER,
    POLICY_BLOCK_EXTERNAL_REASON,
    AiSecurityExternalTransferExceptionDecision,
    AiSecurityPolicyContext,
    AiSecurityPolicyDecision,
    ai_security_enforcement_enabled,
    ai_security_enforcement_required,
    ai_security_external_app_action_for_blockers,
    evaluate_ai_security_policy,
    external_transfer_blockers_from_safety,
    hard_external_transfer_blockers,
    resolve_ai_security_external_transfer_exception,
)
from open_work_hub_api.domains.ai.security_pipeline_exemption import (
    AI_SECURITY_PIPELINE_EXEMPT_REASON,
    AiSecurityPipelineExemptionDecision,
    resolve_ai_security_pipeline_exemption,
)


ResultT = TypeVar("ResultT")
ExternalGatewayStatus = str


class AiExternalCapabilityPolicyViolation(ValueError):
    def __init__(
        self,
        *,
        reason_code: str,
        capability: str,
        provider: str | None,
    ) -> None:
        self.reason_code = reason_code
        self.capability = capability
        self.provider = provider
        super().__init__(
            f"AI external capability policy violation: {reason_code} "
            f"for capability={capability} provider={provider}"
        )


@dataclass(frozen=True)
class AiExternalCapabilityRequest:
    source: str
    workspace_id: str
    task_kind: str
    capability: str
    provider: str | None
    app: str | None = None
    input_texts: Sequence[str] = ()
    actor_user_id: str | None = None
    principal_kind: str = "user"
    principal_id: str | None = None
    entity_id: str | None = None
    agent_run_id: str | None = None
    conversation_id: str | None = None
    source_kinds: Sequence[str] = ()
    sensitivity_labels: Sequence[str] = ()
    content_origin: str | None = None
    metadata: Mapping[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class AiExternalCapabilityDecision:
    allowed: bool
    provider: str | None
    reason_code: str
    pii_hits: tuple[str, ...] = ()
    removed_entity_types: tuple[str, ...] = ()
    blocked_entity_types: tuple[str, ...] = ()
    sensitivity_labels: tuple[str, ...] = ()
    content_origin: str = "user_prompt"
    source_kinds: tuple[str, ...] = ()
    sanitized_texts: tuple[str, ...] = ()
    ai_security_policy_effect: str | None = None
    ai_security_policy_rule_id: str | None = None
    ai_security_policy_reason: str | None = None
    ai_security_policy_audit_only: bool = False
    custom_block_term_count: int = 0
    external_transfer_exception_id: str | None = None
    external_transfer_exception_name: str | None = None
    external_transfer_exception_reason: str | None = None
    external_transfer_exception_blockers: tuple[str, ...] = ()
    ai_security_pipeline_exemption_id: str | None = None
    ai_security_pipeline_exemption_name: str | None = None
    ai_security_pipeline_exemption_reason: str | None = None
    mask_applied: bool = False
    masked_entity_types: tuple[str, ...] = ()
    masked_text_count: int = 0
    privacy_filter_status: str | None = None
    privacy_filter_used: bool = False
    privacy_filter_entity_types: tuple[str, ...] = ()
    privacy_filter_match_count: int = 0
    custom_block_terms: tuple[str, ...] = ()
    security_detection_enabled: bool = True


@dataclass
class AiExternalCapabilityExecution:
    request: AiExternalCapabilityRequest
    decision: AiExternalCapabilityDecision
    _started_at: float = field(default_factory=time.perf_counter)
    _recorded: bool = False

    def sanitized_text(self, index: int = 0, *, fallback: str = "") -> str:
        try:
            text = self.decision.sanitized_texts[index]
        except IndexError:
            return fallback
        return text or fallback

    def record_success(
        self,
        *,
        usage: Mapping[str, int] | None = None,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        self._record(status="ok", usage=usage, metadata=metadata)

    def record_cancelled(self) -> None:
        self._record(status="cancelled")

    def record_error(self, error: BaseException) -> None:
        self._record(status="error", error=_error_summary(error))

    def _record(
        self,
        *,
        status: ExternalGatewayStatus,
        usage: Mapping[str, int] | None = None,
        metadata: Mapping[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        if self._recorded:
            return
        self._recorded = True
        request = self.request
        decision = self.decision
        merged_metadata = {
            **_redacted_metadata(request.metadata),
            **_redacted_metadata(metadata or {}),
        }
        detected_values = (
            collect_ai_security_detected_values(
                request.input_texts,
                custom_block_terms=decision.custom_block_terms,
                privacy_filter_entity_types=decision.privacy_filter_entity_types,
                privacy_filter_match_count=decision.privacy_filter_match_count,
            )
            if decision.security_detection_enabled
            else ()
        )
        log_ai_external_call(
            source=request.source,
            actor_user_id=request.actor_user_id,
            principal_kind=request.principal_kind,
            principal_id=request.principal_id,
            workspace_id=request.workspace_id,
            task_kind=request.task_kind,
            capability=request.capability,
            provider=decision.provider,
            app_id=request.app,
            status=status,
            latency_ms=_elapsed_ms(self._started_at),
            policy_reason=decision.reason_code,
            pii_hits=list(decision.pii_hits),
            removed_entity_types=list(decision.removed_entity_types),
            blocked_entity_types=list(decision.blocked_entity_types),
            sensitivity_labels=list(decision.sensitivity_labels),
            content_origin=decision.content_origin,
            source_kinds=list(decision.source_kinds),
            ai_security_policy_effect=decision.ai_security_policy_effect,
            ai_security_policy_rule_id=decision.ai_security_policy_rule_id,
            ai_security_policy_reason=decision.ai_security_policy_reason,
            ai_security_policy_audit_only=decision.ai_security_policy_audit_only,
            custom_block_term_count=decision.custom_block_term_count,
            external_transfer_exception_id=decision.external_transfer_exception_id,
            external_transfer_exception_name=decision.external_transfer_exception_name,
            external_transfer_exception_reason=decision.external_transfer_exception_reason,
            external_transfer_exception_blockers=list(
                decision.external_transfer_exception_blockers
            ),
            ai_security_pipeline_exemption_id=decision.ai_security_pipeline_exemption_id,
            ai_security_pipeline_exemption_name=decision.ai_security_pipeline_exemption_name,
            ai_security_pipeline_exemption_reason=decision.ai_security_pipeline_exemption_reason,
            mask_applied=decision.mask_applied,
            masked_entity_types=list(decision.masked_entity_types),
            masked_text_count=decision.masked_text_count,
            privacy_filter_status=decision.privacy_filter_status,
            privacy_filter_used=decision.privacy_filter_used,
            input_text_count=len(request.input_texts),
            input_char_count=sum(len(text or "") for text in request.input_texts),
            usage=dict(usage) if usage else None,
            metadata=merged_metadata,
            error=error,
            entity_id=request.entity_id,
            agent_run_id=request.agent_run_id,
            conversation_id=request.conversation_id,
            detected_values=serialize_detected_values(detected_values),
        )


def begin_external_capability(
    request: AiExternalCapabilityRequest,
    *,
    settings: Settings | None = None,
    db: Session | None = None,
) -> AiExternalCapabilityExecution:
    decision = decide_external_capability(request, settings=settings, db=db)
    execution = AiExternalCapabilityExecution(request=request, decision=decision)
    if not decision.allowed:
        execution._record(status="blocked")
        raise AiExternalCapabilityPolicyViolation(
            reason_code=decision.reason_code,
            capability=request.capability,
            provider=decision.provider,
        )
    return execution


def decide_external_capability(
    request: AiExternalCapabilityRequest,
    *,
    settings: Settings | None = None,
    db: Session | None = None,
) -> AiExternalCapabilityDecision:
    resolved_settings = settings or get_settings()
    provider = normalize_external_provider(
        request.provider or _default_provider(request.capability, resolved_settings),
        capability=_egress_capability(request.capability),
    )
    content_origin = normalize_content_origin(request.content_origin)
    source_kinds = normalize_external_safety_values(request.source_kinds)
    sensitivity_labels = normalize_external_safety_values(request.sensitivity_labels)
    raw_texts = tuple(text or "" for text in request.input_texts)
    if provider is None:
        return _decision(
            provider=provider,
            reason_code="provider_not_supported",
            pii_hits=(),
            removed_entity_types=(),
            blocked_entity_types=(),
            sensitivity_labels=sensitivity_labels,
            content_origin=content_origin,
            source_kinds=source_kinds,
            sanitized_texts=raw_texts,
        )
    allowed = set(
        allowed_external_providers(
            resolved_settings,
            capability=_egress_capability(request.capability),
        )
    )
    if provider not in allowed:
        return _decision(
            provider=provider,
            reason_code="provider_not_allowed",
            pii_hits=(),
            removed_entity_types=(),
            blocked_entity_types=(),
            sensitivity_labels=sensitivity_labels,
            content_origin=content_origin,
            source_kinds=source_kinds,
            sanitized_texts=raw_texts,
        )
    security_enforcement_enabled = ai_security_enforcement_enabled(db) if db is not None else False
    if ai_security_enforcement_required(
        environment=resolved_settings.environment,
        enforcement_enabled=security_enforcement_enabled,
    ):
        return _decision(
            provider=provider,
            reason_code=AI_SECURITY_ENFORCEMENT_REQUIRED_REASON,
            pii_hits=(),
            removed_entity_types=(),
            blocked_entity_types=(),
            sensitivity_labels=sensitivity_labels,
            content_origin=content_origin,
            source_kinds=source_kinds,
            sanitized_texts=raw_texts,
            security_detection_enabled=False,
        )
    security_pipeline_exemption = resolve_ai_security_pipeline_exemption(
        AiSecurityPolicyContext(
            workspace_id=request.workspace_id,
            actor_user_id=request.actor_user_id,
            app_id=request.app,
            task_kind=request.task_kind,
            capability=request.capability,
            provider=provider,
        )
    )
    if security_pipeline_exemption.allowed:
        return _decision(
            allowed=True,
            provider=provider,
            reason_code=AI_SECURITY_PIPELINE_EXEMPT_REASON,
            pii_hits=(),
            removed_entity_types=(),
            blocked_entity_types=(),
            sensitivity_labels=sensitivity_labels,
            content_origin=content_origin,
            source_kinds=source_kinds,
            sanitized_texts=raw_texts,
            security_pipeline_exemption=security_pipeline_exemption,
            security_detection_enabled=False,
        )
    if db is not None and not security_enforcement_enabled:
        return _decide_external_capability_without_ai_security(
            request=request,
            settings=resolved_settings,
            provider=provider,
        )
    safety = evaluate_external_payload_safety(
        tuple(request.input_texts),
        content_origin=request.content_origin,
        source_kinds=tuple(request.source_kinds),
        sensitivity_labels=tuple(request.sensitivity_labels),
    )
    sanitizations = [build_external_egress_sanitization(text or "") for text in request.input_texts]
    pii_hits = safety.pii_hits
    removed_entity_types = _merge_tuple_values(
        safety.removed_entity_types,
        tuple(item for result in sanitizations for item in result.removed_entity_types),
    )
    blocked_entity_types = _merge_tuple_values(
        safety.blocked_entity_types,
        tuple(item for result in sanitizations for item in result.blocked_entity_types),
    )
    sanitized_texts = tuple(
        _sanitized_text_for_capability(request.capability, result) for result in sanitizations
    )
    security_decision = _evaluate_ai_security_policy(request, provider, db)

    external_transfer_blockers = external_transfer_blockers_from_safety(
        safety,
        custom_block_term_count=(
            security_decision.custom_block_term_count if security_decision is not None else 0
        ),
        policy_block_external=(
            security_decision.effect == "block_external" if security_decision is not None else False
        ),
    )
    external_transfer_exception = AiSecurityExternalTransferExceptionDecision()
    if db is not None and external_transfer_blockers:
        db_exception = resolve_ai_security_external_transfer_exception(
            db,
            AiSecurityPolicyContext(
                workspace_id=request.workspace_id,
                actor_user_id=request.actor_user_id,
                app_id=request.app,
                task_kind=request.task_kind,
                capability=request.capability,
                provider=provider,
            ),
            external_transfer_blockers,
        )
        if db_exception.allowed:
            external_transfer_exception = db_exception
    masking_result = _external_capability_masking_result(
        request=request,
        settings=resolved_settings,
        db=db,
        safety=safety,
        security_decision=security_decision,
        external_transfer_blockers=external_transfer_blockers,
        external_transfer_exception=external_transfer_exception,
    )
    if masking_result is not None:
        masked_sanitized_texts = _sanitized_texts_for_capability(
            request.capability,
            masking_result.masked_texts,
        )
        masked_removed_entity_types = _merge_tuple_values(
            removed_entity_types,
            masking_result.masked_entity_types,
        )
        masked_blocked_entity_types = _merge_tuple_values(
            blocked_entity_types,
            masking_result.hard_blocker_types,
        )
        if masking_result.allowed:
            if request.input_texts and not any(text.strip() for text in masked_sanitized_texts):
                return _decision(
                    provider=provider,
                    reason_code="sanitized_empty",
                    pii_hits=_merge_tuple_values(pii_hits, masking_result.pii_hits),
                    removed_entity_types=masked_removed_entity_types,
                    blocked_entity_types=masked_blocked_entity_types,
                    sensitivity_labels=safety.sensitivity_labels,
                    content_origin=safety.content_origin,
                    source_kinds=safety.source_kinds,
                    sanitized_texts=masked_sanitized_texts,
                    security_decision=security_decision,
                    external_transfer_exception=external_transfer_exception,
                    masking_result=masking_result,
                )
            return _decision(
                allowed=True,
                provider=provider,
                reason_code=masking_result.reason_code,
                pii_hits=_merge_tuple_values(pii_hits, masking_result.pii_hits),
                removed_entity_types=masked_removed_entity_types,
                blocked_entity_types=masked_blocked_entity_types,
                sensitivity_labels=safety.sensitivity_labels,
                content_origin=safety.content_origin,
                source_kinds=safety.source_kinds,
                sanitized_texts=masked_sanitized_texts,
                security_decision=security_decision,
                external_transfer_exception=external_transfer_exception,
                masking_result=masking_result,
            )
        return _decision(
            provider=provider,
            reason_code=masking_result.reason_code,
            pii_hits=_merge_tuple_values(pii_hits, masking_result.pii_hits),
            removed_entity_types=masked_removed_entity_types,
            blocked_entity_types=masked_blocked_entity_types,
            sensitivity_labels=safety.sensitivity_labels,
            content_origin=safety.content_origin,
            source_kinds=safety.source_kinds,
            sanitized_texts=masked_sanitized_texts,
            security_decision=security_decision,
            external_transfer_exception=external_transfer_exception,
            masking_result=masking_result,
        )
    if not safety.allow_external and not external_transfer_exception.allowed:
        blocked_reason_code = safety.reason_code
        if (
            security_decision is not None
            and security_decision.effect == "block_external"
            and not hard_external_transfer_blockers(external_transfer_blockers)
        ):
            blocked_reason_code = security_decision.reason_code or POLICY_BLOCK_EXTERNAL_REASON
        return _decision(
            provider=provider,
            reason_code=blocked_reason_code,
            pii_hits=pii_hits,
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            sensitivity_labels=safety.sensitivity_labels,
            content_origin=safety.content_origin,
            source_kinds=safety.source_kinds,
            sanitized_texts=sanitized_texts,
            security_decision=security_decision,
            external_transfer_exception=external_transfer_exception,
        )
    if blocked_entity_types and not external_transfer_exception.allowed:
        return _decision(
            provider=provider,
            reason_code="sensitive_entity_blocked",
            pii_hits=pii_hits,
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            sensitivity_labels=safety.sensitivity_labels,
            content_origin=safety.content_origin,
            source_kinds=safety.source_kinds,
            sanitized_texts=sanitized_texts,
            security_decision=security_decision,
            external_transfer_exception=external_transfer_exception,
        )
    if (
        security_decision is not None
        and security_decision.custom_block_term_count > 0
        and not external_transfer_exception.allowed
    ):
        return _decision(
            provider=provider,
            reason_code=CUSTOM_BLOCK_REASON,
            pii_hits=pii_hits,
            removed_entity_types=removed_entity_types,
            blocked_entity_types=_merge_tuple_values(
                blocked_entity_types,
                (CUSTOM_BLOCK_ENTITY_TYPE,),
            ),
            sensitivity_labels=safety.sensitivity_labels,
            content_origin=safety.content_origin,
            source_kinds=safety.source_kinds,
            sanitized_texts=sanitized_texts,
            security_decision=security_decision,
            external_transfer_exception=external_transfer_exception,
        )
    if (
        security_decision is not None
        and security_decision.effect == "block_external"
        and not external_transfer_exception.allowed
    ):
        return _decision(
            provider=provider,
            reason_code=POLICY_BLOCK_EXTERNAL_REASON,
            pii_hits=pii_hits,
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            sensitivity_labels=safety.sensitivity_labels,
            content_origin=safety.content_origin,
            source_kinds=safety.source_kinds,
            sanitized_texts=sanitized_texts,
            security_decision=security_decision,
            external_transfer_exception=external_transfer_exception,
        )
    if request.input_texts and not any(text.strip() for text in sanitized_texts):
        return _decision(
            provider=provider,
            reason_code="sanitized_empty",
            pii_hits=pii_hits,
            removed_entity_types=removed_entity_types,
            blocked_entity_types=blocked_entity_types,
            sensitivity_labels=safety.sensitivity_labels,
            content_origin=safety.content_origin,
            source_kinds=safety.source_kinds,
            sanitized_texts=sanitized_texts,
            security_decision=security_decision,
            external_transfer_exception=external_transfer_exception,
        )
    return _decision(
        allowed=True,
        provider=provider,
        reason_code=(
            EXTERNAL_TRANSFER_EXCEPTION_REASON if external_transfer_exception.allowed else "allowed"
        ),
        pii_hits=pii_hits,
        removed_entity_types=removed_entity_types,
        blocked_entity_types=blocked_entity_types,
        sensitivity_labels=safety.sensitivity_labels,
        content_origin=safety.content_origin,
        source_kinds=safety.source_kinds,
        sanitized_texts=sanitized_texts,
        security_decision=security_decision,
        external_transfer_exception=external_transfer_exception,
    )


def _decide_external_capability_without_ai_security(
    *,
    request: AiExternalCapabilityRequest,
    settings: Settings,
    provider: str | None,
) -> AiExternalCapabilityDecision:
    content_origin = normalize_content_origin(request.content_origin)
    source_kinds = normalize_external_safety_values(request.source_kinds)
    labels = normalize_external_safety_values(request.sensitivity_labels)
    sanitized_texts = tuple(text or "" for text in request.input_texts)
    if provider is None:
        return _decision(
            provider=provider,
            reason_code="provider_not_supported",
            pii_hits=(),
            removed_entity_types=(),
            blocked_entity_types=(),
            sensitivity_labels=labels,
            content_origin=content_origin,
            source_kinds=source_kinds,
            sanitized_texts=sanitized_texts,
            security_detection_enabled=False,
        )
    allowed = set(
        allowed_external_providers(
            settings,
            capability=_egress_capability(request.capability),
        )
    )
    if provider not in allowed:
        return _decision(
            provider=provider,
            reason_code="provider_not_allowed",
            pii_hits=(),
            removed_entity_types=(),
            blocked_entity_types=(),
            sensitivity_labels=labels,
            content_origin=content_origin,
            source_kinds=source_kinds,
            sanitized_texts=sanitized_texts,
            security_detection_enabled=False,
        )
    return _decision(
        allowed=True,
        provider=provider,
        reason_code=AI_SECURITY_ENFORCEMENT_DISABLED_REASON,
        pii_hits=(),
        removed_entity_types=(),
        blocked_entity_types=(),
        sensitivity_labels=labels,
        content_origin=content_origin,
        source_kinds=source_kinds,
        sanitized_texts=sanitized_texts,
        security_detection_enabled=False,
    )


def execute_external_capability(
    request: AiExternalCapabilityRequest,
    invoke: Callable[[AiExternalCapabilityExecution], ResultT],
    *,
    settings: Settings | None = None,
    db: Session | None = None,
    usage: Mapping[str, int] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ResultT:
    execution = begin_external_capability(request, settings=settings, db=db)
    try:
        result = invoke(execution)
    except Exception as error:
        execution.record_error(error)
        raise
    execution.record_success(usage=usage, metadata=metadata)
    return result


async def execute_external_capability_async(
    request: AiExternalCapabilityRequest,
    invoke: Callable[[AiExternalCapabilityExecution], Awaitable[ResultT]],
    *,
    settings: Settings | None = None,
    db: Session | None = None,
    usage: Mapping[str, int] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> ResultT:
    execution = begin_external_capability(request, settings=settings, db=db)
    try:
        result = await invoke(execution)
    except asyncio.CancelledError:
        execution.record_cancelled()
        raise
    except Exception as error:
        execution.record_error(error)
        raise
    execution.record_success(usage=usage, metadata=metadata)
    return result


def _decision(
    *,
    provider: str | None,
    reason_code: str,
    pii_hits: tuple[str, ...],
    removed_entity_types: tuple[str, ...],
    blocked_entity_types: tuple[str, ...],
    sensitivity_labels: tuple[str, ...],
    content_origin: str,
    source_kinds: tuple[str, ...],
    sanitized_texts: tuple[str, ...],
    security_decision: AiSecurityPolicyDecision | None = None,
    external_transfer_exception: AiSecurityExternalTransferExceptionDecision | None = None,
    security_pipeline_exemption: AiSecurityPipelineExemptionDecision | None = None,
    masking_result: ExternalPayloadMaskingResult | None = None,
    allowed: bool = False,
    security_detection_enabled: bool = True,
) -> AiExternalCapabilityDecision:
    return AiExternalCapabilityDecision(
        allowed=allowed,
        provider=provider,
        reason_code=reason_code,
        pii_hits=pii_hits,
        removed_entity_types=removed_entity_types,
        blocked_entity_types=blocked_entity_types,
        sensitivity_labels=sensitivity_labels,
        content_origin=content_origin,
        source_kinds=source_kinds,
        sanitized_texts=sanitized_texts,
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
        mask_applied=masking_result.mask_applied if masking_result is not None else False,
        masked_entity_types=(
            masking_result.masked_entity_types if masking_result is not None else ()
        ),
        masked_text_count=(masking_result.masked_text_count if masking_result is not None else 0),
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
        custom_block_terms=(
            security_decision.custom_block_terms if security_decision is not None else ()
        ),
        security_detection_enabled=security_detection_enabled,
    )


def _evaluate_ai_security_policy(
    request: AiExternalCapabilityRequest,
    provider: str | None,
    db: Session | None,
) -> AiSecurityPolicyDecision | None:
    if db is None:
        return None
    return evaluate_ai_security_policy(
        db,
        AiSecurityPolicyContext(
            workspace_id=request.workspace_id,
            actor_user_id=request.actor_user_id,
            app_id=request.app,
            task_kind=request.task_kind,
            capability=request.capability,
            provider=provider,
        ),
        tuple(request.input_texts),
    )


def _external_capability_masking_result(
    *,
    request: AiExternalCapabilityRequest,
    settings: Settings,
    db: Session | None,
    safety: ExternalPayloadSafetyDecision,
    security_decision: AiSecurityPolicyDecision | None,
    external_transfer_blockers: tuple[str, ...],
    external_transfer_exception: AiSecurityExternalTransferExceptionDecision,
) -> ExternalPayloadMaskingResult | None:
    custom_block_term_count = (
        security_decision.custom_block_term_count if security_decision is not None else 0
    )
    if security_decision is not None and security_decision.effect == "mask_and_send":
        return evaluate_external_payload_masking(
            tuple(request.input_texts),
            safety_decision=safety,
            custom_block_term_count=custom_block_term_count,
            settings=settings,
        )
    if POLICY_BLOCK_EXTERNAL_BLOCKER in external_transfer_blockers:
        return None
    if db is None or not external_transfer_blockers or external_transfer_exception.allowed:
        return None
    action = ai_security_external_app_action_for_blockers(
        db,
        request.app,
        external_transfer_blockers,
    )
    if action != "mask_and_send":
        return None
    return evaluate_external_payload_masking(
        tuple(request.input_texts),
        safety_decision=safety,
        custom_block_term_count=custom_block_term_count,
        settings=settings,
    )


def _merge_tuple_values(*groups: tuple[str, ...]) -> tuple[str, ...]:
    merged: list[str] = []
    for group in groups:
        for value in group:
            if value not in merged:
                merged.append(value)
    return tuple(sorted(merged))


def _default_provider(capability: str, settings: Settings) -> str:
    if "search" in capability:
        return settings.ai_default_external_search_provider
    return settings.ai_default_external_llm_provider


def _egress_capability(capability: str) -> ExternalCapability:
    if "search" in capability:
        return "search"
    if "quality" in capability or "review" in capability:
        return "quality_review"
    if "plan" in capability or "manager" in capability or "brief" in capability:
        return "planning"
    return "reasoning"


def _sanitized_texts_for_capability(capability: str, texts: Sequence[str]) -> tuple[str, ...]:
    return tuple(
        _sanitized_text_for_capability(
            capability,
            build_external_egress_sanitization(text or ""),
        )
        for text in texts
    )


def _sanitized_text_for_capability(capability: str, sanitization: Any) -> str:
    if "search" in capability:
        return sanitization.sanitized_query
    return sanitization.sanitized_prompt


def _redacted_metadata(metadata: Mapping[str, Any]) -> dict[str, Any]:
    return {
        str(key): _redacted_value(value) for key, value in metadata.items() if value is not None
    }


def _redacted_value(value: Any) -> Any:
    if isinstance(value, str):
        return value if len(value) <= 256 else f"{value[:253]}..."
    if isinstance(value, bool | int | float):
        return value
    if isinstance(value, Sequence) and not isinstance(value, (str, bytes, bytearray)):
        return [_redacted_value(item) for item in list(value)[:20]]
    if isinstance(value, Mapping):
        return {str(key): _redacted_value(item) for key, item in list(value.items())[:20]}
    return str(value)


def _elapsed_ms(started_at: float) -> int:
    return int((time.perf_counter() - started_at) * 1000)


def _error_summary(error: BaseException) -> str:
    if isinstance(error, asyncio.CancelledError):
        return "CancelledError"
    message = str(error).strip()
    if message:
        return f"{type(error).__name__}: {message[:500]}"
    return type(error).__name__


__all__ = [
    "AiExternalCapabilityDecision",
    "AiExternalCapabilityExecution",
    "AiExternalCapabilityPolicyViolation",
    "AiExternalCapabilityRequest",
    "begin_external_capability",
    "decide_external_capability",
    "execute_external_capability",
    "execute_external_capability_async",
]
