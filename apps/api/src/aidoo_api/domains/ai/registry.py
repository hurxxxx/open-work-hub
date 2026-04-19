from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from typing import TYPE_CHECKING, Any


if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from aidoo_api.core.principal import CallerPrincipal
    from aidoo_api.domains.ai.policy_service import LlmPolicyMode
    from aidoo_api.domains.auth.models import User, Workspace


ToolHandler = Callable[
    ["Session", "Workspace", "CallerPrincipal", "User", Mapping[str, Any]],
    Any,
]


@dataclass(frozen=True)
class RegisteredLlmTask:
    task_kind: str
    default_policy: "LlmPolicyMode"
    description: str


@dataclass(frozen=True)
class RegisteredToolDefinition:
    name: str
    description: str
    owner_domain: str
    approval_required: bool = False
    handler: ToolHandler | None = None


@dataclass
class AiCapabilityRegistry:
    llm_tasks: dict[str, RegisteredLlmTask] = field(default_factory=dict)
    tools: dict[str, RegisteredToolDefinition] = field(default_factory=dict)

    def register_llm_task(
        self,
        *,
        task_kind: str,
        default_policy: "LlmPolicyMode",
        description: str,
    ) -> None:
        self.llm_tasks[task_kind] = RegisteredLlmTask(
            task_kind=task_kind,
            default_policy=default_policy,
            description=description,
        )

    def register_tool(
        self,
        *,
        name: str,
        description: str,
        owner_domain: str,
        approval_required: bool = False,
        handler: ToolHandler | None = None,
    ) -> None:
        self.tools[name] = RegisteredToolDefinition(
            name=name,
            description=description,
            owner_domain=owner_domain,
            approval_required=approval_required,
            handler=handler,
        )


def _register_domain(
    registry: AiCapabilityRegistry,
    module_name: str,
) -> None:
    module = __import__(module_name, fromlist=["register_ai_capabilities"])
    register = getattr(module, "register_ai_capabilities", None)
    if callable(register):
        register(registry)


@lru_cache(maxsize=1)
def get_ai_capability_registry() -> AiCapabilityRegistry:
    registry = AiCapabilityRegistry()
    for module_name in (
        "aidoo_api.domains.ai",
        "aidoo_api.domains.docs",
        "aidoo_api.domains.meeting",
        "aidoo_api.domains.planner",
        "aidoo_api.domains.pms",
    ):
        _register_domain(registry, module_name)
    return registry


def initialize_ai_capability_registry() -> AiCapabilityRegistry:
    registry = get_ai_capability_registry()
    return registry


def reset_ai_capability_registry() -> None:
    cache_clear = getattr(get_ai_capability_registry, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
