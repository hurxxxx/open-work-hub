from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from functools import lru_cache
from types import MappingProxyType
from typing import TYPE_CHECKING, Any, Literal

from pydantic import BaseModel

from ai_do_api.domains.auth.access import resolve_workspace_enabled_app_ids
from ai_do_api.domains.auth.workspace_apps import WORKSPACE_APP_IDS

if TYPE_CHECKING:
    from sqlalchemy.orm import Session

    from ai_do_api.core.principal import CallerPrincipal
    from ai_do_api.domains.ai.policy_service import LlmPolicyMode
    from ai_do_api.domains.auth.models import User, Workspace


ToolMode = Literal["read", "write"]
ApprovalPolicy = Literal["none", "required"]
OutputProjection = Literal["summary", "resource_ids", "full"]
CapabilityKind = Literal["tool", "resource", "prompt"]

ToolHandler = Callable[
    ["Session", "Workspace", "CallerPrincipal", "User", Mapping[str, Any]],
    Any,
]
DiscoverabilityPredicate = Callable[
    ["CallerPrincipal", "WorkspaceContext", "WorkspaceEntitlementView"],
    bool,
]
PreviewBuilder = Callable[
    ["CallerPrincipal", "WorkspaceContext", BaseModel | Mapping[str, Any]],
    "ApprovalPreview",
]
ToolArgsModel = type[BaseModel]


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
    # Reserved for future fine-grained capability rollout. Phase 3.5 only
    # uses app-level enablement and keeps this view additive for Phase 4+.
    capability_flags: frozenset[str] = frozenset()


@dataclass(frozen=True)
class RegisteredLlmTask:
    task_kind: str
    default_policy: "LlmPolicyMode"
    description: str


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
    # "meeting", "ai"). Tool name prefix is *not* authoritative — RAG tools
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
    openai_strict_input_schema: Mapping[str, Any]
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
                "parameters": dict(self.openai_strict_input_schema),
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


@dataclass
class AiCapabilityRegistry:
    llm_tasks: dict[str, RegisteredLlmTask] = field(default_factory=dict)
    tools: dict[str, RegisteredToolDefinition] = field(default_factory=dict)
    descriptors: dict[str, AiCapabilityDescriptor] = field(default_factory=dict)
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
    ) -> None:
        if task_kind in self.llm_tasks:
            raise ValueError(f"Duplicate LLM task registration: {task_kind}")
        self.llm_tasks[task_kind] = RegisteredLlmTask(
            task_kind=task_kind,
            default_policy=default_policy,
            description=description,
        )

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
        resolved_service_handler_id = service_handler_id or name
        if handler is not None:
            self.register_service_handler(
                service_handler_id=resolved_service_handler_id,
                handler=handler,
            )

        predicate_id = discoverability_predicate_id or f"{owner_domain}.enabled"
        if predicate_id not in self._discoverability_predicates:
            raise ValueError(f"Unknown discoverability predicate: {predicate_id} for tool {name}")
        approval_policy: ApprovalPolicy = "required" if approval_required else "none"
        if approval_policy == "required" and not preview_builder_id:
            raise ValueError(f"Approval-required tool {name} must declare preview_builder_id")
        # Default to owner_domain so existing domains keep working without
        # touching their registration call. New tools that live under a
        # workspace app whose id differs from their owner domain can pass an
        # explicit value.
        resolved_workspace_app_id = workspace_app_id or owner_domain
        if resolved_workspace_app_id not in WORKSPACE_APP_IDS:
            raise ValueError(
                f"Tool {name} declares workspace_app_id={resolved_workspace_app_id!r} which is "
                f"not a registered workspace app. Known: {sorted(WORKSPACE_APP_IDS)}"
            )
        descriptor = AiCapabilityDescriptor(
            name=name,
            kind="tool",
            mode=mode,
            description=description,
            ai_input_model=args_model,
            approval_policy=approval_policy,
            discoverability_predicate_id=predicate_id,
            preview_builder_id=preview_builder_id,
            output_projection=output_projection,
            service_handler_id=resolved_service_handler_id,
            workspace_app_id=resolved_workspace_app_id,
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
        capability_flags=frozenset(),
    )


def _register_builtin_predicates(registry: AiCapabilityRegistry) -> None:
    for app_id in WORKSPACE_APP_IDS:
        registry.register_discoverability_predicate(
            predicate_id=f"{app_id}.enabled",
            predicate=_app_enabled_predicate(app_id),
        )
    registry.register_discoverability_predicate(
        predicate_id="pms.issue_write",
        # Phase 3.5 keeps write capability discovery at the coarse app-enabled
        # layer. Phase 4 write migration will replace this with finer ACL-aware
        # gating once `pms.create_issue` becomes executable.
        predicate=_app_enabled_predicate("pms"),
    )


def _app_enabled_predicate(app_id: str) -> DiscoverabilityPredicate:
    def _predicate(
        principal: "CallerPrincipal",
        workspace: WorkspaceContext,
        entitlements: WorkspaceEntitlementView,
    ) -> bool:
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
        "ai_do_api.domains.meeting",
        "ai_do_api.domains.planner",
        "ai_do_api.domains.pms",
        "ai_do_api.domains.rag",
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
    mcp_schema = _build_mcp_input_schema(descriptor.ai_input_model)
    openai_schema = _build_openai_strict_schema(mcp_schema)
    return CompiledToolSchemas(
        mcp_input_schema=MappingProxyType(mcp_schema),
        openai_strict_input_schema=MappingProxyType(openai_schema),
        annotations=annotations,
    )


def _build_mcp_input_schema(model: ToolArgsModel | None) -> dict[str, Any]:
    if model is None:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "type": "object",
            "properties": {},
            "required": [],
            "additionalProperties": False,
        }
    raw_schema = model.model_json_schema(by_alias=True, mode="validation")
    definitions = raw_schema.get("$defs", {})
    normalized = _normalize_schema(raw_schema, definitions=definitions)
    normalized["$schema"] = "https://json-schema.org/draft/2020-12/schema"
    return normalized


def _normalize_schema(
    schema: Mapping[str, Any],
    *,
    definitions: Mapping[str, Any],
) -> dict[str, Any]:
    if "$ref" in schema:
        return _normalize_ref(schema["$ref"], definitions=definitions)

    if "allOf" in schema or "not" in schema or "patternProperties" in schema:
        raise ValueError(f"Unsupported JSON schema construct: {sorted(schema.keys())}")
    if "if" in schema or "then" in schema or "else" in schema:
        raise ValueError("Conditional JSON schema constructs are not supported.")

    if "anyOf" in schema or "oneOf" in schema:
        branches = schema.get("anyOf") or schema.get("oneOf")
        if not isinstance(branches, list):
            raise ValueError("Union schema must be a list.")
        normalized = _normalize_nullable_union(branches, definitions=definitions)
        normalized.update(_copy_scalar_metadata(schema))
        return normalized

    schema_type = schema.get("type")
    if schema_type == "object":
        return _normalize_object_schema(schema, definitions=definitions)
    if schema_type == "array":
        return _normalize_array_schema(schema, definitions=definitions)
    if isinstance(schema_type, list):
        return _normalize_type_list_schema(schema)
    if schema_type in {"string", "number", "integer", "boolean", "null"}:
        return _normalize_scalar_schema(schema)
    if "enum" in schema:
        return _normalize_scalar_schema(schema)

    raise ValueError(f"Unsupported JSON schema node: {schema}")


def _normalize_ref(ref: Any, *, definitions: Mapping[str, Any]) -> dict[str, Any]:
    if not isinstance(ref, str) or not ref.startswith("#/$defs/"):
        raise ValueError(f"External JSON schema refs are not supported: {ref!r}")
    key = ref.split("/", 2)[-1]
    target = definitions.get(key)
    if not isinstance(target, Mapping):
        raise ValueError(f"Missing local JSON schema ref target: {ref!r}")
    return _normalize_schema(target, definitions=definitions)


def _normalize_nullable_union(
    branches: list[Any],
    *,
    definitions: Mapping[str, Any],
) -> dict[str, Any]:
    if len(branches) != 2:
        raise ValueError("Only nullable unions are supported.")
    normalized_branches = [
        _normalize_schema(branch, definitions=definitions)
        for branch in branches
        if isinstance(branch, Mapping)
    ]
    if len(normalized_branches) != 2:
        raise ValueError("Union branches must be JSON schema objects.")
    null_branch = next(
        (branch for branch in normalized_branches if branch.get("type") == "null"),
        None,
    )
    non_null_branch = next(
        (branch for branch in normalized_branches if branch.get("type") != "null"),
        None,
    )
    if null_branch is None or non_null_branch is None:
        raise ValueError("Only nullable unions are supported.")
    return _make_schema_nullable(non_null_branch)


def _normalize_object_schema(
    schema: Mapping[str, Any],
    *,
    definitions: Mapping[str, Any],
) -> dict[str, Any]:
    properties = schema.get("properties")
    if properties is not None and not isinstance(properties, Mapping):
        raise ValueError("Object schema properties must be a mapping.")
    normalized_properties: dict[str, Any] = {}
    for key in sorted((properties or {}).keys()):
        property_schema = properties[key]
        if not isinstance(property_schema, Mapping):
            raise ValueError(f"Object property {key!r} must be a schema mapping.")
        normalized_properties[key] = _normalize_schema(
            property_schema,
            definitions=definitions,
        )
    required = schema.get("required")
    required_values = []
    if required is not None:
        if not isinstance(required, list):
            raise ValueError("Object schema required must be a list.")
        required_values = [str(item) for item in required]
    return {
        "type": "object",
        "properties": normalized_properties,
        "required": required_values,
        "additionalProperties": False,
        **_copy_scalar_metadata(schema),
    }


def _normalize_array_schema(
    schema: Mapping[str, Any],
    *,
    definitions: Mapping[str, Any],
) -> dict[str, Any]:
    items = schema.get("items")
    if not isinstance(items, Mapping):
        raise ValueError("Array schema items must be a schema object.")
    normalized = {
        "type": "array",
        "items": _normalize_schema(items, definitions=definitions),
        **_copy_scalar_metadata(schema),
    }
    for key in ("minItems", "maxItems", "uniqueItems"):
        value = schema.get(key)
        if value is not None:
            normalized[key] = value
    return normalized


def _normalize_type_list_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    schema_type = schema.get("type")
    if not isinstance(schema_type, list):
        raise ValueError("Expected list-based schema type.")
    filtered_types = [str(item) for item in schema_type]
    supported = {"string", "number", "integer", "boolean", "array", "object", "null"}
    if not set(filtered_types) <= supported:
        raise ValueError(f"Unsupported union types: {filtered_types}")
    normalized = _normalize_scalar_schema({**schema, "type": filtered_types})
    if "object" in filtered_types:
        normalized["additionalProperties"] = False
        normalized.setdefault("properties", {})
        normalized.setdefault("required", [])
    return normalized


def _normalize_scalar_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    normalized: dict[str, Any] = {}
    schema_type = schema.get("type")
    if isinstance(schema_type, list):
        normalized["type"] = [str(item) for item in schema_type]
    elif schema_type is not None:
        normalized["type"] = _normalize_scalar_type(str(schema_type))
    if "enum" in schema:
        enum_values = schema.get("enum")
        if not isinstance(enum_values, list):
            raise ValueError("Enum schema values must be a list.")
        normalized["enum"] = list(enum_values)
    normalized.update(_copy_scalar_metadata(schema))
    for key in (
        "default",
        "minLength",
        "maxLength",
        "minimum",
        "maximum",
        "exclusiveMinimum",
        "exclusiveMaximum",
        "multipleOf",
        "minItems",
        "maxItems",
        "uniqueItems",
    ):
        value = schema.get(key)
        if value is not None:
            normalized[key] = value
    return normalized


def _normalize_scalar_type(schema_type: str) -> str:
    if schema_type not in {"string", "number", "integer", "boolean", "null"}:
        raise ValueError(f"Unsupported scalar JSON schema type: {schema_type}")
    return schema_type


def _copy_scalar_metadata(schema: Mapping[str, Any]) -> dict[str, Any]:
    metadata: dict[str, Any] = {}
    for key in ("title", "description"):
        value = schema.get(key)
        if isinstance(value, str) and value.strip():
            metadata[key] = value
    return metadata


def _build_openai_strict_schema(schema: Mapping[str, Any]) -> dict[str, Any]:
    if schema.get("type") == "object":
        properties = schema.get("properties", {})
        if not isinstance(properties, Mapping):
            raise ValueError("Strict schema object properties must be a mapping.")
        original_required = set(schema.get("required", []))
        strict_properties: dict[str, Any] = {}
        for key, value in properties.items():
            if not isinstance(value, Mapping):
                raise ValueError(f"Strict schema property {key!r} must be a mapping.")
            child = _build_openai_strict_schema(value)
            if key not in original_required:
                child = _make_schema_nullable(child)
            strict_properties[str(key)] = child
        strict_schema: dict[str, Any] = {
            "type": "object",
            "properties": strict_properties,
            "required": list(strict_properties.keys()),
            "additionalProperties": False,
        }
        strict_schema.update(_copy_scalar_metadata(schema))
        return strict_schema
    if schema.get("type") == "array":
        items = schema.get("items")
        if not isinstance(items, Mapping):
            raise ValueError("Strict schema array items must be a mapping.")
        normalized = {
            "type": "array",
            "items": _build_openai_strict_schema(items),
        }
        normalized.update(_copy_scalar_metadata(schema))
        for key in ("minItems", "maxItems", "uniqueItems"):
            value = schema.get(key)
            if value is not None:
                normalized[key] = value
        return normalized
    if "type" in schema:
        normalized = dict(schema)
        if normalized.get("type") == "object":
            normalized["additionalProperties"] = False
            normalized.setdefault("properties", {})
            normalized.setdefault("required", [])
        return normalized
    raise ValueError(f"Unsupported strict schema node: {schema}")


def _make_schema_nullable(schema: Mapping[str, Any]) -> dict[str, Any]:
    normalized = dict(schema)
    schema_type = normalized.get("type")
    if isinstance(schema_type, list):
        if "null" not in schema_type:
            normalized["type"] = [*schema_type, "null"]
        return normalized
    if isinstance(schema_type, str):
        if schema_type == "null":
            return normalized
        normalized["type"] = [schema_type, "null"]
        return normalized
    raise ValueError(f"Cannot make schema nullable without type: {schema}")
