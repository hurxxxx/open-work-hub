from __future__ import annotations

import hashlib
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

from open_work_hub_api.domains.ai.runtime.external_capability import (
    ExternalCapabilityDisabledReason,
    ExternalCapabilityExecutionDisabledReason,
    ExternalCapabilityExecutionStatus,
    ExternalCapabilityRequestStatus,
    RedactedSummaryField,
    blocked_external_execution_result,
    decide_external_capability_request,
    external_execution_summary_projection,
    external_request_fields_from_decision,
    external_request_summary_projection,
    failed_external_execution_result,
    gate_mock_external_execution,
)
from open_work_hub_api.domains.ai.runtime.external_egress import ExternalEgressDecision
from open_work_hub_api.domains.ai.runtime.summary_fields import (
    summary_int,
    summary_string,
    summary_string_list,
)

EXTERNAL_SEARCH_ADAPTER_ID = "external_search_v0"

ExternalSearchStatus = ExternalCapabilityRequestStatus
ExternalSearchDisabledReason = ExternalCapabilityDisabledReason
ExternalSearchExecutionStatus = ExternalCapabilityExecutionStatus
ExternalSearchExecutionDisabledReason = ExternalCapabilityExecutionDisabledReason


@dataclass(frozen=True)
class ExternalSearchTraceIdentity:
    query_digest: str
    cache_key: str


@dataclass(frozen=True)
class ExternalSearchExecutionSummaryView:
    status: str | None
    adapter_id: str | None
    execution_provider: str | None
    provider: str | None
    query_digest: str | None
    source_kinds: tuple[str, ...]
    result_count: int
    result_refs: tuple[str, ...]

    @classmethod
    def from_summary(
        cls,
        summary: Mapping[str, object] | None,
    ) -> ExternalSearchExecutionSummaryView:
        return cls(
            status=summary_string(summary, "status"),
            adapter_id=summary_string(summary, "adapter_id"),
            execution_provider=summary_string(summary, "execution_provider"),
            provider=summary_string(summary, "provider"),
            query_digest=summary_string(summary, "query_digest"),
            source_kinds=tuple(summary_string_list(summary, "source_kinds")),
            result_count=summary_int(summary, "result_count"),
            result_refs=tuple(summary_string_list(summary, "result_refs")),
        )

    @property
    def used(self) -> bool:
        return self.status == "completed" and self.result_count > 0

    @property
    def sanitized_query_ref(self) -> str | None:
        if not self.used or not self.query_digest:
            return None
        return f"sha256:{self.query_digest}"

    @property
    def source_kind(self) -> str:
        return self.source_kinds[0] if self.source_kinds else "external_web"

    def result_refs_or_fallback(self) -> tuple[str, ...]:
        if not self.used:
            return ()
        if self.result_refs:
            return self.result_refs
        query_ref = self.sanitized_query_ref
        if not query_ref:
            return ()
        fallback_count = max(self.result_count, 1)
        return tuple(
            f"external-search:{query_ref}:result-{index}" for index in range(1, fallback_count + 1)
        )


_SEARCH_REQUEST_SUMMARY_PROJECTION = external_request_summary_projection(
    (RedactedSummaryField("query_present", source_attr="query", codec="presence"),)
)
_SEARCH_EXECUTION_SUMMARY_PROJECTION = external_execution_summary_projection(
    (
        RedactedSummaryField("query_digest"),
        RedactedSummaryField("cache_key"),
        RedactedSummaryField("cache_hit"),
        RedactedSummaryField("result_count"),
        RedactedSummaryField("result_refs", codec="list"),
        RedactedSummaryField("source_kinds", codec="list"),
    )
)


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
    decision = decide_external_capability_request(
        egress_decision=egress_decision,
        expected_capability="search",
        sanitized_payload=egress_decision.sanitized_query,
    )
    if decision.status == "disabled":
        return ExternalSearchRequest(**external_request_fields_from_decision(decision))
    return ExternalSearchRequest(
        **external_request_fields_from_decision(decision),
        query=decision.sanitized_payload,
    )


def summarize_external_search_request(
    request: ExternalSearchRequest,
) -> dict[str, object]:
    return _SEARCH_REQUEST_SUMMARY_PROJECTION.build(request)


def execute_mock_external_search(
    request: ExternalSearchRequest,
    *,
    execution_enabled: bool,
    force_error_class: str | None = None,
) -> ExternalSearchExecutionResult:
    gate = gate_mock_external_execution(
        execution_enabled=execution_enabled,
        request_status=request.status,
    )
    if not gate.should_execute:
        return blocked_external_execution_result(
            ExternalSearchExecutionResult,
            gate=gate,
            provider=request.provider,
        )
    trace_identity = build_external_search_trace_identity(
        query=request.query,
        provider=request.provider,
    )
    if force_error_class:
        return failed_external_execution_result(
            ExternalSearchExecutionResult,
            provider=request.provider,
            error_class=force_error_class,
            extra_fields={
                "query_digest": trace_identity.query_digest,
                "cache_key": trace_identity.cache_key,
            },
        )
    result_refs = _mock_result_refs(
        query_digest=trace_identity.query_digest,
        result_count=2,
    )
    return ExternalSearchExecutionResult(
        status="completed",
        provider=request.provider,
        query_digest=trace_identity.query_digest,
        cache_key=trace_identity.cache_key,
        cache_hit=False,
        result_count=len(result_refs),
        result_refs=result_refs,
        source_kinds=["public_web_mock"],
        raw_output_persisted=False,
    )


def summarize_external_search_execution(
    result: ExternalSearchExecutionResult,
) -> dict[str, object]:
    return _SEARCH_EXECUTION_SUMMARY_PROJECTION.build(result)


def build_external_search_trace_identity(
    *,
    query: str,
    provider: str | None,
    execution_provider: str = "mock",
) -> ExternalSearchTraceIdentity:
    query_digest = _query_digest(query)
    return ExternalSearchTraceIdentity(
        query_digest=query_digest,
        cache_key=_cache_key(
            execution_provider=execution_provider,
            provider=provider,
            query_digest=query_digest,
        ),
    )


def _query_digest(query: str) -> str:
    return hashlib.sha256(query.encode("utf-8")).hexdigest()[:16]


def _cache_key(
    *,
    execution_provider: str,
    provider: str | None,
    query_digest: str,
) -> str:
    provider_key = provider or "unknown"
    return f"{EXTERNAL_SEARCH_ADAPTER_ID}:{execution_provider}:{provider_key}:{query_digest}"


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
    "ExternalSearchExecutionSummaryView",
    "ExternalSearchExecutionStatus",
    "ExternalSearchRequest",
    "ExternalSearchStatus",
    "ExternalSearchTraceIdentity",
    "MockExternalSearchAdapter",
    "build_external_search_request",
    "build_external_search_trace_identity",
    "execute_mock_external_search",
    "summarize_external_search_execution",
    "summarize_external_search_request",
]
