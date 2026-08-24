"""Provider-neutral registry for autonomous agent runtimes.

Agent runtimes are intentionally separate from one-shot LLM execution adapters:
they own a bounded turn/tool loop, while workload routing and credentials remain
under the shared AI control plane.
"""

from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import TYPE_CHECKING, Any, Protocol

if TYPE_CHECKING:
    from open_work_hub_api.domains.ai.model_settings_service import ResolvedLlmWorkloadRoute


@dataclass(frozen=True)
class AgentRuntimeRequest:
    run_id: str
    workspace_id: str
    actor_user_id: str
    workload_id: str
    route: "ResolvedLlmWorkloadRoute"
    input_payload: Mapping[str, Any]
    progress: Callable[[str, int], None]
    cancelled: Callable[[], bool]


@dataclass(frozen=True)
class AgentRuntimeResult:
    output_payload: Mapping[str, Any]
    usage: Mapping[str, int] | None = None
    thread_id: str | None = None


class AgentRuntimeAdapter(Protocol):
    adapter_id: str
    display_name: str
    allowed_routes: tuple[str, ...]
    allowed_providers: tuple[str, ...]

    def run(self, request: AgentRuntimeRequest) -> AgentRuntimeResult: ...


_adapters: dict[str, AgentRuntimeAdapter] = {}


@dataclass(frozen=True)
class AgentRuntimeAdapterDescriptor:
    adapter_id: str
    display_name: str
    allowed_routes: tuple[str, ...]
    allowed_providers: tuple[str, ...]


def register_agent_runtime_adapter(adapter: AgentRuntimeAdapter) -> None:
    adapter_id = adapter.adapter_id.strip().lower()
    if not adapter_id:
        raise ValueError("Agent runtime adapter id is required")
    existing = _adapters.get(adapter_id)
    if existing is not None and existing is not adapter:
        raise ValueError(f"Agent runtime adapter already registered: {adapter_id}")
    _adapters[adapter_id] = adapter


def get_agent_runtime_adapter(adapter_id: str) -> AgentRuntimeAdapter:
    normalized = adapter_id.strip().lower()
    adapter = _adapters.get(normalized)
    if adapter is None:
        raise LookupError(f"Agent runtime adapter is not registered: {normalized}")
    return adapter


def get_agent_runtime_adapter_descriptor(
    adapter_id: str,
) -> AgentRuntimeAdapterDescriptor | None:
    adapter = _adapters.get(adapter_id.strip().lower())
    if adapter is None:
        return None
    return AgentRuntimeAdapterDescriptor(
        adapter_id=adapter.adapter_id,
        display_name=adapter.display_name,
        allowed_routes=tuple(adapter.allowed_routes),
        allowed_providers=tuple(adapter.allowed_providers),
    )


def agent_runtime_adapter_ids() -> tuple[str, ...]:
    return tuple(sorted(_adapters))


def reset_agent_runtime_adapters() -> None:
    _adapters.clear()


__all__ = [
    "AgentRuntimeAdapter",
    "AgentRuntimeAdapterDescriptor",
    "AgentRuntimeRequest",
    "AgentRuntimeResult",
    "agent_runtime_adapter_ids",
    "get_agent_runtime_adapter",
    "get_agent_runtime_adapter_descriptor",
    "register_agent_runtime_adapter",
    "reset_agent_runtime_adapters",
]
