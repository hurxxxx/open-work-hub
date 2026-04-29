from __future__ import annotations

import hashlib
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from aidoo_api.domains.ai.runtime.external_egress import ExternalEgressDecision


EXTERNAL_SEARCH_ADAPTER_ID = "external_search_v0"

ExternalSearchStatus = Literal["disabled", "ready"]
ExternalSearchDisabledReason = Literal[
    "capability_mismatch",
    "egress_denied",
    "sanitized_empty",
]
ExternalSearchExecutionStatus = Literal["disabled", "skipped", "completed", "failed"]
ExternalSearchExecutionDisabledReason = Literal[
    "execution_flag_disabled",
    "request_not_ready",
]


class ExternalSearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_id: Literal["external_search_v0"] = EXTERNAL_SEARCH_ADAPTER_ID
    status: ExternalSearchStatus
    provider: str | None = None
    disabled_reason: ExternalSearchDisabledReason | None = None
    egress_reason: str | None = None
    query: str = ""


class ExternalSearchExecutionResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    adapter_id: Literal["external_search_v0"] = EXTERNAL_SEARCH_ADAPTER_ID
    execution_provider: str = "mock"
    status: ExternalSearchExecutionStatus
    provider: str | None = None
    disabled_reason: ExternalSearchExecutionDisabledReason | None = None
    query_digest: str | None = None
    cache_key: str | None = None
    cache_hit: bool = False
    result_count: int = 0
    result_refs: list[str] = Field(default_factory=list)
    source_kinds: list[str] = Field(default_factory=list)
    latency_ms: int = 0
    retry_count: int = 0
    error_class: str | None = None
    estimated_cost_microunits: int = 0
    raw_output_persisted: bool = False


class MockExternalSearchAdapter:
    adapter_id = EXTERNAL_SEARCH_ADAPTER_ID
    execution_provider = "mock"

    def __init__(
        self,
        *,
        execution_enabled: bool,
        force_error_class: str | None = None,
    ) -> None:
        self._execution_enabled = execution_enabled
        self._force_error_class = force_error_class

    def execute(self, request: ExternalSearchRequest) -> ExternalSearchExecutionResult:
        return execute_mock_external_search(
            request,
            execution_enabled=self._execution_enabled,
            force_error_class=self._force_error_class,
        )


def build_external_search_request(
    *,
    egress_decision: ExternalEgressDecision,
) -> ExternalSearchRequest:
    if egress_decision.capability != "search":
        return ExternalSearchRequest(
            status="disabled",
            provider=egress_decision.provider,
            disabled_reason="capability_mismatch",
            egress_reason=egress_decision.reason,
        )
    if not egress_decision.allow_external:
        return ExternalSearchRequest(
            status="disabled",
            provider=egress_decision.provider,
            disabled_reason="egress_denied",
            egress_reason=egress_decision.reason,
        )
    sanitized_query = egress_decision.sanitized_query.strip()
    if not sanitized_query:
        return ExternalSearchRequest(
            status="disabled",
            provider=egress_decision.provider,
            disabled_reason="sanitized_empty",
            egress_reason=egress_decision.reason,
        )
    return ExternalSearchRequest(
        status="ready",
        provider=egress_decision.provider,
        egress_reason=egress_decision.reason,
        query=sanitized_query,
    )


def summarize_external_search_request(
    request: ExternalSearchRequest,
) -> dict[str, object]:
    return {
        "adapter_id": request.adapter_id,
        "status": request.status,
        "provider": request.provider,
        "disabled_reason": request.disabled_reason,
        "egress_reason": request.egress_reason,
        "query_present": bool(request.query),
    }


def execute_mock_external_search(
    request: ExternalSearchRequest,
    *,
    execution_enabled: bool,
    force_error_class: str | None = None,
) -> ExternalSearchExecutionResult:
    if not execution_enabled:
        return ExternalSearchExecutionResult(
            status="disabled",
            provider=request.provider,
            disabled_reason="execution_flag_disabled",
        )
    if request.status != "ready":
        return ExternalSearchExecutionResult(
            status="skipped",
            provider=request.provider,
            disabled_reason="request_not_ready",
        )
    query_digest = _query_digest(request.query)
    if force_error_class:
        return ExternalSearchExecutionResult(
            status="failed",
            provider=request.provider,
            query_digest=query_digest,
            cache_key=_cache_key(
                provider=request.provider,
                query_digest=query_digest,
            ),
            error_class=force_error_class,
        )
    result_refs = _mock_result_refs(query_digest=query_digest, result_count=2)
    return ExternalSearchExecutionResult(
        status="completed",
        provider=request.provider,
        query_digest=query_digest,
        cache_key=_cache_key(
            provider=request.provider,
            query_digest=query_digest,
        ),
        cache_hit=False,
        result_count=len(result_refs),
        result_refs=result_refs,
        source_kinds=["public_web_mock"],
        raw_output_persisted=False,
    )


def summarize_external_search_execution(
    result: ExternalSearchExecutionResult,
) -> dict[str, object]:
    return {
        "adapter_id": result.adapter_id,
        "execution_provider": result.execution_provider,
        "status": result.status,
        "provider": result.provider,
        "disabled_reason": result.disabled_reason,
        "query_digest": result.query_digest,
        "cache_key": result.cache_key,
        "cache_hit": result.cache_hit,
        "result_count": result.result_count,
        "result_refs": list(result.result_refs),
        "source_kinds": list(result.source_kinds),
        "latency_ms": result.latency_ms,
        "retry_count": result.retry_count,
        "error_class": result.error_class,
        "estimated_cost_microunits": result.estimated_cost_microunits,
        "raw_output_persisted": result.raw_output_persisted,
    }


def _query_digest(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def _cache_key(*, provider: str | None, query_digest: str) -> str:
    provider_key = provider or "unknown"
    return f"{EXTERNAL_SEARCH_ADAPTER_ID}:mock:{provider_key}:{query_digest}"


def _mock_result_refs(*, query_digest: str, result_count: int) -> list[str]:
    return [
        f"mock://external-search/{query_digest}/result-{index}"
        for index in range(1, result_count + 1)
    ]


__all__ = [
    "EXTERNAL_SEARCH_ADAPTER_ID",
    "ExternalSearchDisabledReason",
    "ExternalSearchExecutionDisabledReason",
    "ExternalSearchExecutionResult",
    "ExternalSearchExecutionStatus",
    "ExternalSearchRequest",
    "ExternalSearchStatus",
    "MockExternalSearchAdapter",
    "build_external_search_request",
    "execute_mock_external_search",
    "summarize_external_search_execution",
    "summarize_external_search_request",
]
