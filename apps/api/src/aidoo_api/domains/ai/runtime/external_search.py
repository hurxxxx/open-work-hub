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
ExternalSearchExecutionStatus = Literal["disabled", "skipped", "completed"]
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
    execution_provider: Literal["mock"] = "mock"
    status: ExternalSearchExecutionStatus
    provider: str | None = None
    disabled_reason: ExternalSearchExecutionDisabledReason | None = None
    query_digest: str | None = None
    result_count: int = 0
    source_kinds: list[str] = Field(default_factory=list)
    raw_output_persisted: bool = False


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
    return ExternalSearchExecutionResult(
        status="completed",
        provider=request.provider,
        query_digest=_query_digest(request.query),
        result_count=2,
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
        "result_count": result.result_count,
        "source_kinds": list(result.source_kinds),
        "raw_output_persisted": result.raw_output_persisted,
    }


def _query_digest(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


__all__ = [
    "EXTERNAL_SEARCH_ADAPTER_ID",
    "ExternalSearchDisabledReason",
    "ExternalSearchExecutionDisabledReason",
    "ExternalSearchExecutionResult",
    "ExternalSearchExecutionStatus",
    "ExternalSearchRequest",
    "ExternalSearchStatus",
    "build_external_search_request",
    "execute_mock_external_search",
    "summarize_external_search_execution",
    "summarize_external_search_request",
]
