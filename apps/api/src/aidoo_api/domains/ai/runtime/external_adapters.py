from __future__ import annotations

from dataclasses import dataclass
import hashlib
from typing import Any
from typing import Protocol

from aidoo_api.domains.ai.runtime.external_planner import (
    EXTERNAL_PLANNER_ADAPTER_ID,
    ExternalPlannerExecutionResult,
    ExternalPlannerRequest,
    MockExternalPlannerAdapter,
)
from aidoo_api.domains.ai.runtime.external_search import (
    EXTERNAL_SEARCH_ADAPTER_ID,
    ExternalSearchExecutionResult,
    ExternalSearchRequest,
    MockExternalSearchAdapter,
)


class ExternalPlannerExecutionAdapter(Protocol):
    adapter_id: str
    execution_provider: str

    def execute(self, request: ExternalPlannerRequest) -> ExternalPlannerExecutionResult:
        """Execute an external planner request and return a trace-safe summary result."""


class ExternalSearchExecutionAdapter(Protocol):
    adapter_id: str
    execution_provider: str

    def execute(self, request: ExternalSearchRequest) -> ExternalSearchExecutionResult:
        """Execute an external search request and return a normalized, trace-safe result."""


@dataclass(frozen=True)
class DisabledExternalPlannerAdapter:
    execution_provider: str
    adapter_id: str = EXTERNAL_PLANNER_ADAPTER_ID

    def execute(self, request: ExternalPlannerRequest) -> ExternalPlannerExecutionResult:
        return ExternalPlannerExecutionResult(
            status="disabled",
            execution_provider=self.execution_provider,
            provider=request.provider,
            disabled_reason="execution_flag_disabled",
        )


@dataclass(frozen=True)
class UnavailableExternalPlannerAdapter:
    execution_provider: str
    adapter_id: str = EXTERNAL_PLANNER_ADAPTER_ID

    def execute(self, request: ExternalPlannerRequest) -> ExternalPlannerExecutionResult:
        return ExternalPlannerExecutionResult(
            status="failed",
            execution_provider=self.execution_provider,
            provider=request.provider,
            error_class="adapter_not_implemented",
        )


@dataclass(frozen=True)
class DisabledExternalSearchAdapter:
    execution_provider: str
    adapter_id: str = EXTERNAL_SEARCH_ADAPTER_ID

    def execute(self, request: ExternalSearchRequest) -> ExternalSearchExecutionResult:
        return ExternalSearchExecutionResult(
            status="disabled",
            execution_provider=self.execution_provider,
            provider=request.provider,
            disabled_reason="execution_flag_disabled",
        )


@dataclass(frozen=True)
class UnavailableExternalSearchAdapter:
    execution_provider: str
    adapter_id: str = EXTERNAL_SEARCH_ADAPTER_ID

    def execute(self, request: ExternalSearchRequest) -> ExternalSearchExecutionResult:
        query_digest = _query_digest(request.query) if request.query else None
        return ExternalSearchExecutionResult(
            status="failed",
            execution_provider=self.execution_provider,
            provider=request.provider,
            query_digest=query_digest,
            cache_key=_cache_key(
                execution_provider=self.execution_provider,
                provider=request.provider,
                query_digest=query_digest,
            )
            if query_digest
            else None,
            error_class="adapter_not_implemented",
        )


def select_external_planner_execution_adapter(
    settings: Any,
    *,
    execution_enabled: bool,
) -> ExternalPlannerExecutionAdapter:
    adapter_name = _adapter_name(
        getattr(settings, "ai_external_planner_execution_adapter", "mock")
    )
    if not execution_enabled:
        return DisabledExternalPlannerAdapter(execution_provider=adapter_name)
    if adapter_name == "mock":
        return MockExternalPlannerAdapter(execution_enabled=True)
    return UnavailableExternalPlannerAdapter(execution_provider=adapter_name)


def select_external_search_execution_adapter(
    settings: Any,
    *,
    execution_enabled: bool,
) -> ExternalSearchExecutionAdapter:
    adapter_name = _adapter_name(
        getattr(settings, "ai_external_search_execution_adapter", "mock")
    )
    if not execution_enabled:
        return DisabledExternalSearchAdapter(execution_provider=adapter_name)
    if adapter_name == "mock":
        return MockExternalSearchAdapter(execution_enabled=True)
    return UnavailableExternalSearchAdapter(execution_provider=adapter_name)


def _adapter_name(value: Any) -> str:
    name = str(value or "mock").strip().lower()
    return name or "mock"


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


__all__ = [
    "DisabledExternalPlannerAdapter",
    "DisabledExternalSearchAdapter",
    "ExternalPlannerExecutionAdapter",
    "ExternalSearchExecutionAdapter",
    "UnavailableExternalPlannerAdapter",
    "UnavailableExternalSearchAdapter",
    "select_external_planner_execution_adapter",
    "select_external_search_execution_adapter",
]
