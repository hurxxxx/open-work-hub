from __future__ import annotations

from dataclasses import dataclass
from typing import Any
from typing import Callable
from typing import Protocol
from typing import TypeVar

from ai_do_api.domains.ai.runtime.external_capability import (
    failed_external_execution_result,
)
from ai_do_api.domains.ai.runtime.external_planner import (
    EXTERNAL_PLANNER_ADAPTER_ID,
    ExternalPlannerExecutionResult,
    ExternalPlannerRequest,
    MockExternalPlannerAdapter,
)
from ai_do_api.domains.ai.runtime.external_search import (
    EXTERNAL_SEARCH_ADAPTER_ID,
    ExternalSearchExecutionResult,
    ExternalSearchRequest,
    MockExternalSearchAdapter,
    build_external_search_trace_identity,
)


AdapterT = TypeVar("AdapterT")
ResultT = TypeVar("ResultT")
PlannerAdapterFactory = Callable[[], "ExternalPlannerExecutionAdapter"]
SearchAdapterFactory = Callable[[], "ExternalSearchExecutionAdapter"]

_planner_adapter_factories: dict[str, PlannerAdapterFactory] = {}
_search_adapter_factories: dict[str, SearchAdapterFactory] = {}
_defaults_registered = False


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
        return _disabled_external_execution_result(
            ExternalPlannerExecutionResult,
            execution_provider=self.execution_provider,
            provider=request.provider,
        )


@dataclass(frozen=True)
class UnavailableExternalPlannerAdapter:
    execution_provider: str
    adapter_id: str = EXTERNAL_PLANNER_ADAPTER_ID

    def execute(self, request: ExternalPlannerRequest) -> ExternalPlannerExecutionResult:
        return _unavailable_external_execution_result(
            ExternalPlannerExecutionResult,
            execution_provider=self.execution_provider,
            provider=request.provider,
        )


@dataclass(frozen=True)
class DisabledExternalSearchAdapter:
    execution_provider: str
    adapter_id: str = EXTERNAL_SEARCH_ADAPTER_ID

    def execute(self, request: ExternalSearchRequest) -> ExternalSearchExecutionResult:
        return _disabled_external_execution_result(
            ExternalSearchExecutionResult,
            execution_provider=self.execution_provider,
            provider=request.provider,
        )


@dataclass(frozen=True)
class UnavailableExternalSearchAdapter:
    execution_provider: str
    adapter_id: str = EXTERNAL_SEARCH_ADAPTER_ID

    def execute(self, request: ExternalSearchRequest) -> ExternalSearchExecutionResult:
        return _unavailable_external_execution_result(
            ExternalSearchExecutionResult,
            execution_provider=self.execution_provider,
            provider=request.provider,
            extra_fields=_unavailable_external_search_trace_fields(
                request=request,
                execution_provider=self.execution_provider,
            ),
        )


def select_external_planner_execution_adapter(
    settings: Any,
    *,
    execution_enabled: bool,
) -> ExternalPlannerExecutionAdapter:
    ensure_default_external_execution_adapters_registered()
    return _select_external_execution_adapter(
        settings,
        setting_name="ai_external_planner_execution_adapter",
        execution_enabled=execution_enabled,
        disabled_factory=DisabledExternalPlannerAdapter,
        adapter_factories=_planner_adapter_factories,
        unavailable_factory=UnavailableExternalPlannerAdapter,
    )


def select_external_search_execution_adapter(
    settings: Any,
    *,
    execution_enabled: bool,
) -> ExternalSearchExecutionAdapter:
    ensure_default_external_execution_adapters_registered()
    return _select_external_execution_adapter(
        settings,
        setting_name="ai_external_search_execution_adapter",
        execution_enabled=execution_enabled,
        disabled_factory=DisabledExternalSearchAdapter,
        adapter_factories=_search_adapter_factories,
        unavailable_factory=UnavailableExternalSearchAdapter,
    )


def supported_external_planner_execution_adapters() -> tuple[str, ...]:
    ensure_default_external_execution_adapters_registered()
    return tuple(sorted(_planner_adapter_factories))


def supported_external_search_execution_adapters() -> tuple[str, ...]:
    ensure_default_external_execution_adapters_registered()
    return tuple(sorted(_search_adapter_factories))


def ensure_default_external_execution_adapters_registered() -> None:
    global _defaults_registered
    if _defaults_registered:
        return
    register_external_planner_execution_adapter(
        "mock",
        lambda: MockExternalPlannerAdapter(execution_enabled=True),
    )
    register_external_search_execution_adapter(
        "mock",
        lambda: MockExternalSearchAdapter(execution_enabled=True),
    )
    register_external_search_execution_adapter(
        "kipris",
        lambda: UnavailableExternalSearchAdapter("kipris"),
    )
    _defaults_registered = True


def register_external_planner_execution_adapter(
    name: str,
    factory: PlannerAdapterFactory,
) -> None:
    _register_external_execution_adapter(_planner_adapter_factories, name, factory)


def register_external_search_execution_adapter(
    name: str,
    factory: SearchAdapterFactory,
) -> None:
    _register_external_execution_adapter(_search_adapter_factories, name, factory)


def reset_external_execution_adapters() -> None:
    global _defaults_registered
    _planner_adapter_factories.clear()
    _search_adapter_factories.clear()
    _defaults_registered = False


def normalize_external_execution_adapter_name(value: Any) -> str:
    return _adapter_name(value)


def _select_external_execution_adapter(
    settings: Any,
    *,
    setting_name: str,
    execution_enabled: bool,
    disabled_factory: Callable[[str], AdapterT],
    adapter_factories: dict[str, Callable[[], AdapterT]],
    unavailable_factory: Callable[[str], AdapterT],
) -> AdapterT:
    adapter_name = _adapter_name(getattr(settings, setting_name, "mock"))
    if not execution_enabled:
        return disabled_factory(adapter_name)
    adapter_factory = adapter_factories.get(adapter_name)
    if adapter_factory is not None:
        return adapter_factory()
    return unavailable_factory(adapter_name)


def _register_external_execution_adapter(
    factories: dict[str, Callable[[], AdapterT]],
    name: str,
    factory: Callable[[], AdapterT],
) -> None:
    adapter_name = _adapter_name(name)
    if adapter_name in factories:
        raise ValueError(f"external execution adapter already registered: {adapter_name}")
    factories[adapter_name] = factory


def _disabled_external_execution_result(
    result_factory: Callable[..., ResultT],
    *,
    execution_provider: str,
    provider: str | None,
) -> ResultT:
    return result_factory(
        status="disabled",
        execution_provider=execution_provider,
        provider=provider,
        disabled_reason="execution_flag_disabled",
    )


def _unavailable_external_execution_result(
    result_factory: Callable[..., ResultT],
    *,
    execution_provider: str,
    provider: str | None,
    extra_fields: dict[str, Any] | None = None,
) -> ResultT:
    return failed_external_execution_result(
        result_factory,
        provider=provider,
        error_class="adapter_not_implemented",
        extra_fields={
            "execution_provider": execution_provider,
            **(extra_fields or {}),
        },
    )


def _unavailable_external_search_trace_fields(
    *,
    request: ExternalSearchRequest,
    execution_provider: str,
) -> dict[str, str]:
    if not request.query:
        return {}
    trace_identity = build_external_search_trace_identity(
        query=request.query,
        execution_provider=execution_provider,
        provider=request.provider,
    )
    return {
        "query_digest": trace_identity.query_digest,
        "cache_key": trace_identity.cache_key,
    }


def _adapter_name(value: Any) -> str:
    name = str(value or "mock").strip().lower()
    return name or "mock"


__all__ = [
    "DisabledExternalPlannerAdapter",
    "DisabledExternalSearchAdapter",
    "ExternalPlannerExecutionAdapter",
    "ExternalSearchExecutionAdapter",
    "UnavailableExternalPlannerAdapter",
    "UnavailableExternalSearchAdapter",
    "ensure_default_external_execution_adapters_registered",
    "normalize_external_execution_adapter_name",
    "register_external_planner_execution_adapter",
    "register_external_search_execution_adapter",
    "reset_external_execution_adapters",
    "select_external_planner_execution_adapter",
    "select_external_search_execution_adapter",
    "supported_external_planner_execution_adapters",
    "supported_external_search_execution_adapters",
]
