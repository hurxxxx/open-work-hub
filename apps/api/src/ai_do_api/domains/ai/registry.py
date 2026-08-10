from __future__ import annotations

from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from ai_do_api.domains.ai.schema_compile import compile_input_schemas
from ai_do_api.domains.auth.access import (
    resolve_platform_enabled_app_ids,
    resolve_workspace_enabled_app_ids,
)
from ai_do_api.domains.auth.workspace_apps import iter_workspace_app_catalog

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ai_do_api.core.principal import CallerPrincipal
    from ai_do_api.domains.ai.internal_agent_contracts import LocalAgentTask
    from ai_do_api.domains.auth.models import User, Workspace


ToolMode = Literal["read", "write"]
ApprovalPolicy = Literal["none", "required"]
OutputProjection = Literal["summary", "resource_ids", "full"]
CapabilityKind = Literal["tool", "resource", "prompt"]
LlmRoute = Literal["local", "external"]
LlmPolicyMode = Literal["local_only", "external"]
LlmExecutionKind = Literal["chat", "agent", "image_supervisor", "image_generation"]
LlmManagementSurface = Literal["llm_routing", "document_processing"]

DEFAULT_LOCAL_MAX_OUTPUT_TOKENS = 32_768
DEFAULT_EXTERNAL_MAX_OUTPUT_TOKENS = 65_536
MIN_MAX_OUTPUT_TOKENS = 1_024
MAX_MAX_OUTPUT_TOKENS = 65_536

ToolHandler = Callable[
    ["Session", "Workspace", "CallerPrincipal", "User", Mapping[str, Any]],
    Any,
]
GatewayArgumentBuilder = Callable[["LocalAgentTask"], Mapping[str, Any]]
DiscoverabilityPredicate = Callable[
    ["CallerPrincipal", "WorkspaceContext", "WorkspaceEntitlementView"],
    bool,
]
PreviewBuilder = Callable[
    ["CallerPrincipal", "WorkspaceContext", BaseModel | Mapping[str, Any]],
    "ApprovalPreview",
]
ToolArgsModel = type[BaseModel]


def _normalize_registration_values(values: Iterable[str]) -> tuple[str, ...]:
    return tuple(
        dict.fromkeys(str(value).strip().lower() for value in values if str(value).strip())
    )


@dataclass(frozen=True)
class PreviewField:
    label: str
    value: str


@dataclass(frozen=True)
class ApprovalPreview:
    title: str
    summary: str
    fields: tuple[PreviewField, ...] = ()


@dataclass(frozen=True)
class WorkspaceContext:
    workspace_id: str
    workspace_slug: str
    display_name: str


@dataclass(frozen=True)
class WorkspaceEntitlementView:
    enabled_app_ids: frozenset[str]
    platform_enabled_app_ids: frozenset[str] = frozenset()
    # Reserved for future fine-grained capability rollout. Current discovery
    # uses app-level enablement and keeps this view additive.
    capability_flags: frozenset[str] = frozenset()

    @property
    def effective_enabled_app_ids(self) -> frozenset[str]:
        return self.enabled_app_ids | self.platform_enabled_app_ids


@dataclass(frozen=True)
class RegisteredLlmTask:
    task_kind: str
    default_policy: "LlmPolicyMode"
    description: str
    app_ids: tuple[str, ...]


@dataclass(frozen=True)
class RegisteredLlmWorkload:
    """Stable platform contract for one administratively routable LLM workload.

    ``task_kind`` remains the generation-budget and audit compatibility key. New
    callers must address the registry by ``workload_id`` so multiple app-owned
    workloads can evolve independently without leaking provider/model choices
    into domain code.
    """

    workload_id: str
    task_kind: str
    owner_domain: str
    app_ids: tuple[str, ...]
    description: str
    default_route: LlmRoute = "local"
    execution_kind: LlmExecutionKind = "chat"
    allowed_routes: tuple[LlmRoute, ...] = ("local", "external")
    allowed_providers: tuple[str, ...] = ()
    required_capabilities: tuple[str, ...] = ("chat",)
    model_roles: tuple[str, ...] = ("default",)
    label_key: str = ""
    description_key: str = ""
    external_data: bool = False
    local_max_output_tokens: int = DEFAULT_LOCAL_MAX_OUTPUT_TOKENS
    external_max_output_tokens: int = DEFAULT_EXTERNAL_MAX_OUTPUT_TOKENS
    management_surface: LlmManagementSurface = "llm_routing"

    @property
    def app_id(self) -> str:
        """Primary app id for single-app consumers; ``app_ids`` is authoritative."""

        return self.app_ids[0]

    @property
    def default_policy(self) -> "LlmPolicyMode":
        return "local_only" if self.default_route == "local" else "external"

    @property
    def allowed_pools(self) -> tuple[LlmRoute, ...]:
        """Compatibility alias for runtime code that calls routes pools."""

        return self.allowed_routes


@dataclass(frozen=True)
class GatewayToolAdapter:
    agent_id: str
    tool_name: str
    build_arguments: GatewayArgumentBuilder
    passthrough_keys: frozenset[str] = frozenset()
    priority: int = 100


@dataclass(frozen=True)
class AiCapabilityDescriptor:
    name: str
    kind: CapabilityKind
    mode: ToolMode
    description: str
    ai_input_model: ToolArgsModel | None
    approval_policy: ApprovalPolicy
    discoverability_predicate_id: str
    preview_builder_id: str | None
    output_projection: OutputProjection
    service_handler_id: str
    # Workspace AppBar app_id this capability belongs to (e.g. "pms",
    # "meeting", "chatbot"). Tool name prefix is *not* authoritative — RAG tools
    # are named ``rag.*`` but live under the ``ai`` app, and future bridges
    # may register tools whose name namespace differs from their app id.
    workspace_app_id: str

    @property
    def app_id(self) -> str:
        # Backwards-compatible alias for callers that historically read the
        # name-prefix-derived id. Prefer ``workspace_app_id`` for new code.
        return self.workspace_app_id


@dataclass(frozen=True)
class ToolAnnotations:
    title: str
    readOnlyHint: bool
    destructiveHint: bool
    idempotentHint: bool
    openWorldHint: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "title": self.title,
            "readOnlyHint": self.readOnlyHint,
            "destructiveHint": self.destructiveHint,
            "idempotentHint": self.idempotentHint,
            "openWorldHint": self.openWorldHint,
        }


@dataclass(frozen=True)
class CompiledToolSchemas:
    mcp_input_schema: Mapping[str, Any]
    strict_input_schema: Mapping[str, Any]
    annotations: ToolAnnotations

    def mcp_tool_definition(
        self,
        *,
        descriptor: AiCapabilityDescriptor,
        include_meta: bool = False,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "name": descriptor.name,
            "description": descriptor.description,
            "inputSchema": dict(self.mcp_input_schema),
            "annotations": self.annotations.as_dict(),
        }
        if include_meta:
            payload["_meta"] = {
                "com.doowon/ai": {
                    "approval_policy": descriptor.approval_policy,
                    "discoverability_predicate_id": descriptor.discoverability_predicate_id,
                    "output_projection": descriptor.output_projection,
                    "preview_builder_id": descriptor.preview_builder_id,
                }
            }
        return payload

    def openai_function_spec(
        self,
        *,
        descriptor: AiCapabilityDescriptor,
    ) -> dict[str, Any]:
        return {
            "type": "function",
            "function": {
                "name": descriptor.name,
                "description": descriptor.description,
                "strict": True,
                "parameters": dict(self.strict_input_schema),
            },
        }


@dataclass(frozen=True)
class RegisteredToolDefinition:
    name: str
    description: str
    owner_domain: str
    approval_required: bool = False
    handler: ToolHandler | None = None
    args_model: ToolArgsModel | None = None
    descriptor: AiCapabilityDescriptor | None = None
    compiled_schemas: CompiledToolSchemas | None = None

    def validate_arguments(self, arguments: Mapping[str, Any]) -> BaseModel | None:
        if self.args_model is None:
            return None
        return self.args_model.model_validate(dict(arguments))

    def openai_function_spec(self) -> dict[str, Any]:
        parameters_schema: dict[str, Any]
        if self.args_model is None:
            parameters_schema = {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }
        else:
            parameters_schema = self.args_model.model_json_schema()
        return {
            "type": "function",
            "function": {
                "name": self.name,
                "description": self.description,
                "parameters": parameters_schema,
            },
        }


@dataclass(frozen=True)
class ResolvedToolRegistrationPolicy:
    service_handler_id: str
    discoverability_predicate_id: str
    approval_policy: ApprovalPolicy
    workspace_app_id: str


def _resolve_tool_registration_policy(
    *,
    name: str,
    owner_domain: str,
    mode: ToolMode,
    approval_required: bool,
    discoverability_predicate_id: str | None,
    preview_builder_id: str | None,
    service_handler_id: str | None,
    workspace_app_id: str | None,
    known_discoverability_predicate_ids: set[str],
    known_preview_builder_ids: set[str],
) -> ResolvedToolRegistrationPolicy:
    resolved_service_handler_id = service_handler_id or name
    resolved_workspace_app_id = (workspace_app_id or owner_domain).strip()
    if not resolved_workspace_app_id:
        raise ValueError(f"Tool {name} must declare a workspace_app_id or owner_domain")
    predicate_id = discoverability_predicate_id or f"{resolved_workspace_app_id}.enabled"
    if (
        discoverability_predicate_id is not None
        and predicate_id not in known_discoverability_predicate_ids
    ):
        raise ValueError(f"Unknown discoverability predicate: {predicate_id} for tool {name}")
    if mode == "write" and not approval_required:
        raise ValueError(f"Write AI tool {name} must set approval_required=True")
    approval_policy: ApprovalPolicy = "required" if approval_required else "none"
    if approval_policy == "required" and not preview_builder_id:
        raise ValueError(f"Approval-required tool {name} must declare preview_builder_id")
    if preview_builder_id is not None and preview_builder_id not in known_preview_builder_ids:
        raise ValueError(f"Unknown preview builder: {preview_builder_id} for tool {name}")

    return ResolvedToolRegistrationPolicy(
        service_handler_id=resolved_service_handler_id,
        discoverability_predicate_id=predicate_id,
        approval_policy=approval_policy,
        workspace_app_id=resolved_workspace_app_id,
    )


@dataclass
class AiCapabilityRegistry:
    llm_tasks: dict[str, RegisteredLlmTask] = field(default_factory=dict)
    llm_workloads: dict[str, RegisteredLlmWorkload] = field(default_factory=dict)
    tools: dict[str, RegisteredToolDefinition] = field(default_factory=dict)
    descriptors: dict[str, AiCapabilityDescriptor] = field(default_factory=dict)
    gateway_tool_adapters: dict[tuple[str, str], GatewayToolAdapter] = field(default_factory=dict)
    _service_handlers: dict[str, ToolHandler] = field(default_factory=dict)
    _discoverability_predicates: dict[str, DiscoverabilityPredicate] = field(default_factory=dict)
    _preview_builders: dict[str, PreviewBuilder] = field(default_factory=dict)
    _compiled_schemas: Mapping[str, CompiledToolSchemas] = field(
        default_factory=dict,
        init=False,
        repr=False,
    )

    def register_llm_task(
        self,
        *,
        task_kind: str,
        default_policy: "LlmPolicyMode",
        description: str,
        app_ids: tuple[str, ...] | list[str],
    ) -> None:
        if task_kind in self.llm_tasks:
            raise ValueError(f"Duplicate LLM task registration: {task_kind}")
        normalized_app_ids = tuple(
            dict.fromkeys(app_id.strip().lower() for app_id in app_ids if app_id and app_id.strip())
        )
        if not normalized_app_ids:
            raise ValueError(f"LLM task {task_kind} must declare at least one app_id")
        task = RegisteredLlmTask(
            task_kind=task_kind,
            default_policy=default_policy,
            description=description,
            app_ids=normalized_app_ids,
        )
        # Preserve the historical task registry while projecting every legacy
        # task into the canonical workload registry. The deterministic id keeps
        # existing task_kind-based callers and persisted settings addressable.
        self.register_llm_workload(
            workload_id=task_kind,
            task_kind=task_kind,
            owner_domain=normalized_app_ids[0],
            app_ids=normalized_app_ids,
            description=description,
            default_route="local" if default_policy == "local_only" else "external",
            execution_kind="chat",
            allowed_routes=("local", "external"),
            required_capabilities=("chat",),
            model_roles=("default",),
        )
        self.llm_tasks[task_kind] = task

    def register_llm_workload(
        self,
        *,
        workload_id: str,
        task_kind: str,
        owner_domain: str,
        description: str,
        app_id: str | None = None,
        app_ids: tuple[str, ...] | list[str] = (),
        default_route: LlmRoute = "local",
        execution_kind: LlmExecutionKind = "chat",
        allowed_routes: tuple[LlmRoute, ...] | list[LlmRoute] = ("local", "external"),
        allowed_providers: tuple[str, ...] | list[str] = (),
        required_capabilities: tuple[str, ...] | list[str] = ("chat",),
        model_roles: tuple[str, ...] | list[str] = ("default",),
        label_key: str = "",
        description_key: str = "",
        external_data: bool = False,
        local_max_output_tokens: int = DEFAULT_LOCAL_MAX_OUTPUT_TOKENS,
        external_max_output_tokens: int = DEFAULT_EXTERNAL_MAX_OUTPUT_TOKENS,
        management_surface: LlmManagementSurface = "llm_routing",
    ) -> None:
        normalized_workload_id = workload_id.strip().lower()
        normalized_task_kind = task_kind.strip().lower().replace("-", "_")
        normalized_owner = owner_domain.strip().lower()
        if not normalized_workload_id:
            raise ValueError("LLM workload_id is required")
        if normalized_workload_id in self.llm_workloads:
            raise ValueError(f"Duplicate LLM workload registration: {normalized_workload_id}")
        if not normalized_task_kind:
            raise ValueError(f"LLM workload {normalized_workload_id} must declare task_kind")
        if not normalized_owner:
            raise ValueError(f"LLM workload {normalized_workload_id} must declare owner_domain")
        if default_route not in ("local", "external"):
            raise ValueError(f"LLM workload {normalized_workload_id} has invalid default route")
        if execution_kind not in (
            "chat",
            "agent",
            "image_supervisor",
            "image_generation",
        ):
            raise ValueError(f"LLM workload {normalized_workload_id} has invalid execution_kind")
        if management_surface not in ("llm_routing", "document_processing"):
            raise ValueError(
                f"LLM workload {normalized_workload_id} has invalid management_surface"
            )

        all_app_ids: list[str] = []
        if app_id is not None:
            all_app_ids.append(app_id)
        all_app_ids.extend(app_ids)
        normalized_app_ids = tuple(
            dict.fromkeys(value.strip().lower() for value in all_app_ids if value and value.strip())
        )
        if not normalized_app_ids:
            raise ValueError(
                f"LLM workload {normalized_workload_id} must declare at least one app_id"
            )

        normalized_routes = tuple(dict.fromkeys(allowed_routes))
        if not normalized_routes:
            raise ValueError(f"LLM workload {normalized_workload_id} must allow at least one route")
        if any(route not in ("local", "external") for route in normalized_routes):
            raise ValueError(f"LLM workload {normalized_workload_id} has an invalid allowed route")
        if default_route not in normalized_routes:
            raise ValueError(f"LLM workload {normalized_workload_id} default route must be allowed")
        for route, max_output_tokens in (
            ("local", local_max_output_tokens),
            ("external", external_max_output_tokens),
        ):
            if not MIN_MAX_OUTPUT_TOKENS <= max_output_tokens <= MAX_MAX_OUTPUT_TOKENS:
                raise ValueError(
                    f"LLM workload {normalized_workload_id} {route} max output tokens "
                    f"must be between {MIN_MAX_OUTPUT_TOKENS} and {MAX_MAX_OUTPUT_TOKENS}"
                )
            if max_output_tokens % 1_024 != 0:
                raise ValueError(
                    f"LLM workload {normalized_workload_id} {route} max output tokens "
                    "must use 1024-token increments"
                )
        normalized_model_roles = _normalize_registration_values(model_roles)
        if not normalized_model_roles:
            raise ValueError(
                f"LLM workload {normalized_workload_id} must declare at least one model role"
            )
        normalized_capabilities = _normalize_registration_values(required_capabilities)
        if not normalized_capabilities:
            raise ValueError(
                f"LLM workload {normalized_workload_id} must declare model capabilities"
            )

        conflicting = [
            registered.workload_id
            for registered in self.llm_workloads.values()
            if registered.task_kind == normalized_task_kind
            and set(registered.app_ids).intersection(normalized_app_ids)
        ]
        if conflicting:
            raise ValueError(
                "Duplicate LLM workload app/task registration: "
                f"{normalized_workload_id} conflicts with {sorted(conflicting)}"
            )

        self.llm_workloads[normalized_workload_id] = RegisteredLlmWorkload(
            workload_id=normalized_workload_id,
            task_kind=normalized_task_kind,
            owner_domain=normalized_owner,
            app_ids=normalized_app_ids,
            description=description.strip(),
            default_route=default_route,
            execution_kind=execution_kind,
            allowed_routes=normalized_routes,
            allowed_providers=_normalize_registration_values(allowed_providers),
            required_capabilities=normalized_capabilities,
            model_roles=normalized_model_roles,
            label_key=label_key.strip(),
            description_key=description_key.strip(),
            external_data=external_data,
            local_max_output_tokens=local_max_output_tokens,
            external_max_output_tokens=external_max_output_tokens,
            management_surface=management_surface,
        )
        existing_task = self.llm_tasks.get(normalized_task_kind)
        if existing_task is None:
            self.llm_tasks[normalized_task_kind] = RegisteredLlmTask(
                task_kind=normalized_task_kind,
                default_policy=("local_only" if default_route == "local" else "external"),
                description=description.strip(),
                app_ids=normalized_app_ids,
            )
        else:
            self.llm_tasks[normalized_task_kind] = RegisteredLlmTask(
                task_kind=existing_task.task_kind,
                default_policy=(
                    "local_only"
                    if existing_task.default_policy == "local_only" or default_route == "local"
                    else "external"
                ),
                description=existing_task.description,
                app_ids=tuple(dict.fromkeys((*existing_task.app_ids, *normalized_app_ids))),
            )

    def get_llm_workload(self, workload_id: str) -> RegisteredLlmWorkload | None:
        return self.llm_workloads.get(workload_id.strip().lower())

    def resolve_llm_workload(self, workload_id: str) -> RegisteredLlmWorkload:
        workload = self.get_llm_workload(workload_id)
        if workload is None:
            raise LookupError(f"Unknown LLM workload: {workload_id}")
        return workload

    def resolve_llm_workload_for_task(
        self,
        *,
        app_id: str,
        task_kind: str,
    ) -> RegisteredLlmWorkload | None:
        normalized_app_id = app_id.strip().lower()
        normalized_task_kind = task_kind.strip().lower().replace("-", "_")
        matches = [
            workload
            for workload in self.llm_workloads.values()
            if workload.task_kind == normalized_task_kind and normalized_app_id in workload.app_ids
        ]
        if not matches:
            return None
        if len(matches) > 1:
            raise ValueError(
                "Ambiguous LLM workload registration for "
                f"{normalized_app_id}/{normalized_task_kind}"
            )
        return matches[0]

    def register_service_handler(
        self,
        *,
        service_handler_id: str,
        handler: ToolHandler,
    ) -> None:
        if service_handler_id in self._service_handlers:
            raise ValueError(f"Duplicate service handler registration: {service_handler_id}")
        self._service_handlers[service_handler_id] = handler

    def register_discoverability_predicate(
        self,
        *,
        predicate_id: str,
        predicate: DiscoverabilityPredicate,
    ) -> None:
        if predicate_id in self._discoverability_predicates:
            raise ValueError(f"Duplicate discoverability predicate registration: {predicate_id}")
        self._discoverability_predicates[predicate_id] = predicate

    def register_preview_builder(
        self,
        *,
        preview_builder_id: str,
        builder: PreviewBuilder,
    ) -> None:
        if preview_builder_id in self._preview_builders:
            raise ValueError(f"Duplicate preview builder registration: {preview_builder_id}")
        self._preview_builders[preview_builder_id] = builder

    def register_gateway_tool_adapter(
        self,
        *,
        agent_id: str,
        tool_name: str,
        build_arguments: GatewayArgumentBuilder,
        passthrough_keys: Iterable[str] = (),
        priority: int = 100,
    ) -> None:
        if not agent_id.strip():
            raise ValueError(f"Gateway tool adapter for {tool_name} must declare agent_id")
        if tool_name not in self.tools:
            raise ValueError(f"Gateway tool adapter targets an unregistered AI tool: {tool_name}")
        key = (agent_id, tool_name)
        if key in self.gateway_tool_adapters:
            raise ValueError(
                f"Duplicate gateway tool adapter registration: {agent_id} -> {tool_name}"
            )
        self.gateway_tool_adapters[key] = GatewayToolAdapter(
            agent_id=agent_id,
            tool_name=tool_name,
            build_arguments=build_arguments,
            passthrough_keys=frozenset(
                str(value).strip() for value in passthrough_keys if str(value).strip()
            ),
            priority=priority,
        )

    def gateway_adapters_for_agent(self, agent_id: str) -> tuple[GatewayToolAdapter, ...]:
        return tuple(
            sorted(
                (
                    adapter
                    for (
                        registered_agent_id,
                        _tool_name,
                    ), adapter in self.gateway_tool_adapters.items()
                    if registered_agent_id == agent_id
                ),
                key=lambda adapter: (adapter.priority, adapter.tool_name),
            )
        )

    def get_gateway_tool_adapter(
        self,
        *,
        agent_id: str,
        tool_name: str,
    ) -> GatewayToolAdapter | None:
        return self.gateway_tool_adapters.get((agent_id, tool_name))

    def register_tool(
        self,
        *,
        name: str,
        description: str,
        owner_domain: str,
        approval_required: bool = False,
        handler: ToolHandler | None = None,
        args_model: ToolArgsModel | None = None,
        mode: ToolMode = "read",
        discoverability_predicate_id: str | None = None,
        preview_builder_id: str | None = None,
        output_projection: OutputProjection = "full",
        service_handler_id: str | None = None,
        workspace_app_id: str | None = None,
    ) -> None:
        if name in self.tools or name in self.descriptors:
            raise ValueError(f"Duplicate AI tool registration: {name}")
        policy = _resolve_tool_registration_policy(
            name=name,
            owner_domain=owner_domain,
            mode=mode,
            approval_required=approval_required,
            discoverability_predicate_id=discoverability_predicate_id,
            preview_builder_id=preview_builder_id,
            service_handler_id=service_handler_id,
            workspace_app_id=workspace_app_id,
            known_discoverability_predicate_ids=set(self._discoverability_predicates),
            known_preview_builder_ids=set(self._preview_builders),
        )
        if handler is not None:
            self.register_service_handler(
                service_handler_id=policy.service_handler_id,
                handler=handler,
            )
        if policy.discoverability_predicate_id not in self._discoverability_predicates:
            self.register_discoverability_predicate(
                predicate_id=policy.discoverability_predicate_id,
                predicate=_app_enabled_predicate(policy.workspace_app_id),
            )
        descriptor = AiCapabilityDescriptor(
            name=name,
            kind="tool",
            mode=mode,
            description=description,
            ai_input_model=args_model,
            approval_policy=policy.approval_policy,
            discoverability_predicate_id=policy.discoverability_predicate_id,
            preview_builder_id=preview_builder_id,
            output_projection=output_projection,
            service_handler_id=policy.service_handler_id,
            workspace_app_id=policy.workspace_app_id,
        )
        self.descriptors[name] = descriptor
        self.tools[name] = RegisteredToolDefinition(
            name=name,
            description=description,
            owner_domain=owner_domain,
            approval_required=approval_required,
            handler=handler,
            args_model=args_model,
            descriptor=descriptor,
        )

    def compile_capabilities(self) -> Mapping[str, CompiledToolSchemas]:
        compiled: dict[str, CompiledToolSchemas] = {}
        updated_tools: dict[str, RegisteredToolDefinition] = {}
        for tool_name, descriptor in sorted(self.descriptors.items()):
            compiled_tool = _compile_tool_descriptor(descriptor)
            compiled[tool_name] = compiled_tool
            tool = self.tools[tool_name]
            updated_tools[tool_name] = RegisteredToolDefinition(
                name=tool.name,
                description=tool.description,
                owner_domain=tool.owner_domain,
                approval_required=tool.approval_required,
                handler=tool.handler,
                args_model=tool.args_model,
                descriptor=tool.descriptor,
                compiled_schemas=compiled_tool,
            )
        self.tools = updated_tools
        self._compiled_schemas = MappingProxyType(compiled)
        return self._compiled_schemas

    def compiled_schemas(self) -> Mapping[str, CompiledToolSchemas]:
        return self._compiled_schemas

    def get_descriptor(self, tool_name: str) -> AiCapabilityDescriptor | None:
        return self.descriptors.get(tool_name)

    def get_compiled_schemas(self, tool_name: str) -> CompiledToolSchemas | None:
        return self._compiled_schemas.get(tool_name)

    def resolve_service_handler(self, service_handler_id: str) -> ToolHandler | None:
        return self._service_handlers.get(service_handler_id)

    def resolve_discoverability_predicate(
        self,
        predicate_id: str,
    ) -> DiscoverabilityPredicate | None:
        return self._discoverability_predicates.get(predicate_id)

    def resolve_preview_builder(self, preview_builder_id: str) -> PreviewBuilder | None:
        return self._preview_builders.get(preview_builder_id)

    def openai_tool_specs(
        self,
        *,
        include_approval_required: bool = False,
    ) -> list[dict[str, Any]]:
        definitions = [
            definition
            for definition in self.tools.values()
            if include_approval_required or not definition.approval_required
        ]
        return [
            definition.openai_function_spec()
            for definition in sorted(definitions, key=lambda item: item.name)
        ]


def build_workspace_context(workspace: "Workspace") -> WorkspaceContext:
    return WorkspaceContext(
        workspace_id=workspace.id,
        workspace_slug=workspace.key,
        display_name=workspace.name,
    )


def resolve_workspace_entitlement_view(
    db: "Session",
    *,
    workspace: "Workspace",
) -> WorkspaceEntitlementView:
    return WorkspaceEntitlementView(
        enabled_app_ids=frozenset(resolve_workspace_enabled_app_ids(db, workspace.id)),
        platform_enabled_app_ids=frozenset(resolve_platform_enabled_app_ids(db)),
        capability_flags=frozenset(),
    )


def _register_builtin_predicates(registry: AiCapabilityRegistry) -> None:
    for app in iter_workspace_app_catalog():
        app_id = app.app_id
        registry.register_discoverability_predicate(
            predicate_id=f"{app_id}.enabled",
            predicate=_app_enabled_predicate(
                app_id,
                availability_scope=app.availability_scope,
            ),
        )


def _app_enabled_predicate(
    app_id: str,
    *,
    availability_scope: Literal["platform", "workspace"] = "workspace",
) -> DiscoverabilityPredicate:
    def _predicate(
        principal: "CallerPrincipal",
        workspace: WorkspaceContext,
        entitlements: WorkspaceEntitlementView,
    ) -> bool:
        if availability_scope == "platform":
            return app_id in entitlements.platform_enabled_app_ids
        return app_id in entitlements.enabled_app_ids

    return _predicate


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
    _register_builtin_predicates(registry)
    for module_name in (
        "ai_do_api.domains.ai",
        "ai_do_api.domains.docs",
        "ai_do_api.domains.files",
        "ai_do_api.domains.legacy_issues",
        "ai_do_api.domains.mail",
        "ai_do_api.domains.meal_invoice_ocr",
        "ai_do_api.domains.meeting",
        "ai_do_api.domains.planner",
        "ai_do_api.domains.pms",
        "ai_do_api.domains.ppt_generator",
        "ai_do_api.domains.spec_compare",
        "ai_do_api.domains.patent_automation",
        "ai_do_api.domains.patent_prior_art",
        "ai_do_api.domains.retrieval",
        "ai_do_api.domains.rag",
        "ai_do_api.domains.web_search",
    ):
        _register_domain(registry, module_name)
    registry.compile_capabilities()
    return registry


def initialize_ai_capability_registry() -> AiCapabilityRegistry:
    registry = get_ai_capability_registry()
    return registry


def reset_ai_capability_registry() -> None:
    cache_clear = getattr(get_ai_capability_registry, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()


def resolve_llm_workload(workload_id: str) -> RegisteredLlmWorkload:
    """Resolve a registered workload or fail closed for an unknown id."""

    return get_ai_capability_registry().resolve_llm_workload(workload_id)


def resolve_llm_workload_for_task(
    *,
    app_id: str,
    task_kind: str,
) -> RegisteredLlmWorkload | None:
    """Compatibility lookup for callers being migrated from ``task_kind``."""

    return get_ai_capability_registry().resolve_llm_workload_for_task(
        app_id=app_id,
        task_kind=task_kind,
    )


def get_chatbot_capable_app_ids() -> tuple[str, ...]:
    """Workspace app ids that currently expose at least one chatbot tool.

    Used by the workspace bootstrap response so the chat scope picker stays
    data-driven: registering a new domain via ``register_ai_capabilities``
    automatically surfaces it in the picker without any frontend change.
    """
    registry = get_ai_capability_registry()
    seen: dict[str, None] = {}
    for descriptor in registry.descriptors.values():
        if descriptor.kind != "tool":
            continue
        seen.setdefault(descriptor.workspace_app_id, None)
    return tuple(seen.keys())


def _compile_tool_descriptor(descriptor: AiCapabilityDescriptor) -> CompiledToolSchemas:
    annotations = ToolAnnotations(
        title=descriptor.name,
        readOnlyHint=descriptor.mode == "read",
        destructiveHint=descriptor.mode == "write",
        idempotentHint=descriptor.mode == "read",
        openWorldHint=False,
    )
    mcp_schema, strict_schema = compile_input_schemas(descriptor.ai_input_model)
    return CompiledToolSchemas(
        mcp_input_schema=MappingProxyType(mcp_schema),
        strict_input_schema=MappingProxyType(strict_schema),
        annotations=annotations,
    )
