from __future__ import annotations

from dataclasses import dataclass
from types import SimpleNamespace
from typing import Any, Protocol

from open_work_hub_api.core.asr import ensure_default_asr_backends_registered
from open_work_hub_api.core.asr_backend_registry import (
    asr_backend_names,
    normalize_asr_backend_name,
)
from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import (
    get_ai_capability_registry,
    initialize_ai_capability_registry,
)
from open_work_hub_api.domains.ai.local_gateway_tool_catalog import (
    default_gateway_tools_by_agent,
    read_gateway_tool_builders,
)
from open_work_hub_api.domains.ai.runtime.external_adapters import (
    normalize_external_execution_adapter_name,
    supported_external_planner_execution_adapters,
    supported_external_search_execution_adapters,
)
from open_work_hub_api.domains.ai.runtime.agent_catalog import default_agent_definitions
from open_work_hub_api.core.llm_provider_registry import (
    ensure_default_external_llm_providers_registered,
    external_llm_provider_descriptor,
    external_llm_provider_ids,
    normalize_external_llm_provider_id,
)
from open_work_hub_api.core.llm_execution_adapters import (
    ensure_default_llm_execution_adapters_registered,
    llm_execution_adapter_keys,
)
from open_work_hub_api.core.llm_model_profiles import (
    ensure_default_llm_generation_profiles_registered,
    llm_generation_profile_keys,
)
from open_work_hub_api.core.llm_pool_config_registry import (
    ensure_default_llm_pool_config_resolvers_registered,
    llm_pool_config_resolver_keys,
)
from open_work_hub_api.domains.auth.workspace_apps import (
    get_workspace_app_catalog_item,
    get_workspace_app_registration,
)
from open_work_hub_api.domains.conversations.default_scope_adapters import (
    ensure_conversation_scope_adapters_registered,
)
from open_work_hub_api.domains.conversations.scope_registry import (
    conversation_scope_adapters,
    supported_conversation_scope_refs,
)
from open_work_hub_api.domains.rag.default_source_adapters import (
    ensure_rag_source_adapters_registered,
)
from open_work_hub_api.domains.rag.provider_factory import get_rag_provider_registry
from open_work_hub_api.domains.rag.source_adapter_registry import (
    listed_rag_source_adapters,
    rag_resource_adapters,
    rag_source_adapters,
    rag_visibility_scope_adapters,
)
from open_work_hub_api.domains.retrieval.default_partition_adapters import (
    ensure_retrieval_partition_adapters_registered,
)
from open_work_hub_api.domains.retrieval.partition_adapter_registry import (
    get_retrieval_partition_adapter,
    retrieval_partition_adapters,
)
from open_work_hub_api.domains.search.default_entity_adapters import (
    ensure_search_entity_adapters_registered,
)
from open_work_hub_api.domains.search.default_index_hook_adapters import (
    ensure_search_index_hooks_registered,
)
from open_work_hub_api.domains.search.backend_factory import (
    ensure_default_keyword_search_backends_registered,
    keyword_search_backend_names,
    normalize_keyword_search_backend_name,
)
from open_work_hub_api.domains.search.backend_contracts import (
    KeywordAclBranch,
    KeywordAclClause,
    keyword_acl_clause,
)
from open_work_hub_api.domains.search.entity_adapter_registry import search_entity_adapters
from open_work_hub_api.domains.search.entity_registry import search_entity_descriptors
from open_work_hub_api.domains.search.hook_registry import (
    get_search_index_hook_registration,
    search_index_hooks_registered,
)
from open_work_hub_api.domains.search.index_gateway import keyword_acl_query_field_names
from open_work_hub_api.domains.search.projection_registry import get_search_projection_adapters
from open_work_hub_api.domains.source_access.targets import (
    target_access_app_ids,
    ensure_builtin_target_access_adapters_registered,
)
from open_work_hub_api.domains.source_access.default_adapters import (
    ensure_builtin_source_access_adapters_registered,
)
from open_work_hub_api.domains.source_access.registry import get_source_access_adapters


class PlatformExtensionBootstrapError(RuntimeError):
    pass


class PlatformExtensionSettings(Protocol):
    ai_allowed_external_providers: str
    ai_default_external_llm_provider: str
    ai_default_external_search_provider: str
    ai_external_llm_enabled: bool
    ai_external_planner_execution_adapter: str
    ai_external_planner_execution_enabled: bool
    ai_external_planning_enabled: bool
    ai_external_quality_review_enabled: bool
    ai_external_reasoning_enabled: bool
    ai_external_search_execution_adapter: str
    ai_external_search_execution_enabled: bool
    asr_backend: str
    keyword_search_backend: str
    llm_external_allowed_providers: str
    rag_embedding_provider: str
    rag_enabled: bool
    rag_ocr_provider: str
    rag_rerank_provider: str
    rag_vector_index_provider: str


@dataclass(frozen=True)
class PlatformExtensionRegistrySnapshot:
    ai_tool_names: tuple[str, ...]
    asr_backend_names: tuple[str, ...]
    ai_external_planner_execution_adapter_names: tuple[str, ...]
    ai_external_search_execution_adapter_names: tuple[str, ...]
    target_access_app_ids: tuple[str, ...]
    conversation_scope_refs: tuple[str, ...]
    keyword_search_backend_names: tuple[str, ...]
    llm_execution_adapter_keys: tuple[str, ...]
    llm_external_provider_ids: tuple[str, ...]
    llm_generation_profile_keys: tuple[str, ...]
    llm_pool_config_resolver_keys: tuple[str, ...]
    rag_embedding_provider_names: tuple[str, ...]
    rag_ocr_provider_names: tuple[str, ...]
    rag_rerank_provider_names: tuple[str, ...]
    rag_resource_types: tuple[str, ...]
    rag_source_kinds: tuple[str, ...]
    rag_vector_index_provider_names: tuple[str, ...]
    rag_visibility_scope_types: tuple[str, ...]
    retrieval_partition_adapter_ids: tuple[str, ...]
    search_entity_adapter_types: tuple[str, ...]
    search_entity_types: tuple[str, ...]
    source_access_resource_types: tuple[str, ...]


def initialize_platform_extensions(
    settings: PlatformExtensionSettings | None = None,
) -> PlatformExtensionRegistrySnapshot:
    initialize_ai_capability_registry()
    ensure_default_asr_backends_registered()
    ensure_default_external_llm_providers_registered()
    ensure_default_llm_pool_config_resolvers_registered()
    ensure_default_llm_execution_adapters_registered()
    ensure_default_llm_generation_profiles_registered()
    ensure_retrieval_partition_adapters_registered()
    ensure_search_entity_adapters_registered()
    ensure_search_index_hooks_registered()
    ensure_builtin_target_access_adapters_registered()
    ensure_builtin_source_access_adapters_registered()
    ensure_conversation_scope_adapters_registered()
    ensure_default_keyword_search_backends_registered()
    ensure_rag_source_adapters_registered()
    return validate_platform_extension_registries(settings)


def validate_platform_extension_registries(
    settings: PlatformExtensionSettings | None = None,
) -> PlatformExtensionRegistrySnapshot:
    settings = settings or get_settings()
    snapshot = _registry_snapshot()
    problems = [
        *_validate_required_registries(snapshot),
        *_validate_ai_gateway_registry_contracts(snapshot, settings),
        *_validate_runtime_config_contracts(snapshot, settings),
        *_validate_external_provider_settings(settings),
        *_validate_llm_registry_contracts(snapshot, settings),
        *_validate_conversation_scope_registry_contracts(),
        *_validate_retrieval_partition_registry_contracts(),
        *_validate_search_registry_contracts(snapshot),
        *_validate_rag_registry_contracts(snapshot, settings),
    ]
    if problems:
        raise PlatformExtensionBootstrapError("; ".join(problems))
    return snapshot


def _registry_snapshot() -> PlatformExtensionRegistrySnapshot:
    registry = get_ai_capability_registry()
    rag_provider_registry = get_rag_provider_registry()
    source_access_resource_types = tuple(
        sorted(
            {
                resource_type
                for adapter in get_source_access_adapters()
                for resource_type in adapter.resource_types
            }
        )
    )
    return PlatformExtensionRegistrySnapshot(
        ai_tool_names=tuple(sorted(registry.tools)),
        asr_backend_names=asr_backend_names(),
        ai_external_planner_execution_adapter_names=(
            supported_external_planner_execution_adapters()
        ),
        ai_external_search_execution_adapter_names=(supported_external_search_execution_adapters()),
        target_access_app_ids=target_access_app_ids(),
        conversation_scope_refs=tuple(sorted(supported_conversation_scope_refs())),
        keyword_search_backend_names=keyword_search_backend_names(),
        llm_execution_adapter_keys=llm_execution_adapter_keys(),
        llm_external_provider_ids=external_llm_provider_ids(official_only=True),
        llm_generation_profile_keys=llm_generation_profile_keys(),
        llm_pool_config_resolver_keys=llm_pool_config_resolver_keys(),
        rag_embedding_provider_names=rag_provider_registry.embedding_provider_names(),
        rag_ocr_provider_names=rag_provider_registry.ocr_provider_names(),
        rag_rerank_provider_names=rag_provider_registry.rerank_provider_names(),
        rag_resource_types=tuple(
            sorted(adapter.resource_type for adapter in rag_resource_adapters())
        ),
        rag_source_kinds=tuple(sorted(adapter.source_kind for adapter in rag_source_adapters())),
        rag_vector_index_provider_names=rag_provider_registry.vector_index_provider_names(),
        rag_visibility_scope_types=tuple(
            sorted(adapter.scope_type for adapter in rag_visibility_scope_adapters())
        ),
        retrieval_partition_adapter_ids=tuple(
            sorted(adapter.adapter_id for adapter in retrieval_partition_adapters())
        ),
        search_entity_adapter_types=tuple(
            sorted(adapter.entity_type for adapter in search_entity_adapters())
        ),
        search_entity_types=tuple(
            sorted(descriptor.entity_type for descriptor in search_entity_descriptors())
        ),
        source_access_resource_types=source_access_resource_types,
    )


def _validate_required_registries(
    snapshot: PlatformExtensionRegistrySnapshot,
) -> list[str]:
    problems: list[str] = []
    required = {
        "AI capability registry": snapshot.ai_tool_names,
        "ASR backend registry": snapshot.asr_backend_names,
        "AI external planner execution adapter registry": (
            snapshot.ai_external_planner_execution_adapter_names
        ),
        "AI external search execution adapter registry": (
            snapshot.ai_external_search_execution_adapter_names
        ),
        "target access registry": snapshot.target_access_app_ids,
        "conversation scope registry": snapshot.conversation_scope_refs,
        "keyword search backend registry": snapshot.keyword_search_backend_names,
        "LLM execution adapter registry": snapshot.llm_execution_adapter_keys,
        "external LLM provider registry": snapshot.llm_external_provider_ids,
        "LLM generation profile registry": snapshot.llm_generation_profile_keys,
        "LLM pool config resolver registry": snapshot.llm_pool_config_resolver_keys,
        "RAG embedding provider registry": snapshot.rag_embedding_provider_names,
        "RAG OCR provider registry": snapshot.rag_ocr_provider_names,
        "RAG rerank provider registry": snapshot.rag_rerank_provider_names,
        "RAG resource registry": snapshot.rag_resource_types,
        "RAG source registry": snapshot.rag_source_kinds,
        "RAG vector index provider registry": snapshot.rag_vector_index_provider_names,
        "RAG visibility scope registry": snapshot.rag_visibility_scope_types,
        "retrieval partition adapter registry": snapshot.retrieval_partition_adapter_ids,
        "search entity adapter registry": snapshot.search_entity_adapter_types,
        "search entity registry": snapshot.search_entity_types,
        "source access registry": snapshot.source_access_resource_types,
    }
    for label, values in required.items():
        if not values:
            problems.append(f"{label} is empty")
    if not search_index_hooks_registered():
        problems.append("search index hook registry is empty")
    return problems


def _validate_conversation_scope_registry_contracts() -> list[str]:
    registry = get_ai_capability_registry()
    problems: list[str] = []
    for adapter in conversation_scope_adapters():
        experience = adapter.experience
        if get_workspace_app_catalog_item(experience.owner_app_id) is None:
            problems.append(
                "conversation scope owner app is not registered: "
                f"{adapter.scope_ref} -> {experience.owner_app_id}"
            )
        if experience.chat_workload_id is None:
            continue
        workload = registry.get_llm_workload(experience.chat_workload_id)
        if workload is None:
            problems.append(
                "conversation scope chat workload is not registered: "
                f"{adapter.scope_ref} -> {experience.chat_workload_id}"
            )
            continue
        if experience.owner_app_id not in workload.app_ids:
            problems.append(
                "conversation scope owner app is not allowed by chat workload: "
                f"{adapter.scope_ref} -> {experience.owner_app_id}/"
                f"{experience.chat_workload_id}"
            )
    return problems


def _validate_ai_gateway_registry_contracts(
    snapshot: PlatformExtensionRegistrySnapshot,
    settings: PlatformExtensionSettings,
) -> list[str]:
    problems: list[str] = []
    agent_ids = {definition.agent_id for definition in default_agent_definitions()}
    tool_names = set(snapshot.ai_tool_names)
    gateway_tool_builders = set(read_gateway_tool_builders())
    disabled_tool_names = _disabled_gateway_tool_names(settings)

    unknown_gateway_agents = sorted(set(default_gateway_tools_by_agent()) - agent_ids)
    if unknown_gateway_agents:
        problems.append(
            "default gateway tools registered for unknown AI agent(s): "
            + ", ".join(unknown_gateway_agents)
        )

    missing_tool_builders = sorted(
        {
            tool_name
            for tool_names_for_agent in default_gateway_tools_by_agent().values()
            for tool_name in tool_names_for_agent
            if tool_name not in gateway_tool_builders
        }
    )
    if missing_tool_builders:
        problems.append(
            "default gateway tools without argument builders: " + ", ".join(missing_tool_builders)
        )

    missing_registered_tools = sorted(
        {
            tool_name
            for tool_names_for_agent in default_gateway_tools_by_agent().values()
            for tool_name in tool_names_for_agent
            if tool_name not in disabled_tool_names and tool_name not in tool_names
        }
    )
    if missing_registered_tools:
        problems.append(
            "default gateway tools missing from AI capability registry: "
            + ", ".join(missing_registered_tools)
        )
    return problems


def _disabled_gateway_tool_names(
    settings: PlatformExtensionSettings,
) -> frozenset[str]:
    disabled_tool_names: set[str] = set()
    if not settings.rag_enabled:
        disabled_tool_names.update({"rag.query", "rag.list_sources"})
    return frozenset(disabled_tool_names)


def _validate_runtime_config_contracts(
    snapshot: PlatformExtensionRegistrySnapshot,
    settings: PlatformExtensionSettings,
) -> list[str]:
    problems: list[str] = []
    asr_backend = normalize_asr_backend_name(settings.asr_backend)
    if asr_backend not in set(snapshot.asr_backend_names):
        problems.append(f"configured ASR backend is not registered: {asr_backend}")
    if settings.ai_external_planner_execution_enabled:
        adapter_name = normalize_external_execution_adapter_name(
            settings.ai_external_planner_execution_adapter
        )
        if adapter_name not in set(snapshot.ai_external_planner_execution_adapter_names):
            problems.append(
                "configured AI external planner execution adapter is not "
                f"registered: {adapter_name}"
            )
    if settings.ai_external_search_execution_enabled:
        adapter_name = normalize_external_execution_adapter_name(
            settings.ai_external_search_execution_adapter
        )
        if adapter_name not in set(snapshot.ai_external_search_execution_adapter_names):
            problems.append(
                f"configured AI external search execution adapter is not registered: {adapter_name}"
            )
    keyword_search_backend = normalize_keyword_search_backend_name(settings.keyword_search_backend)
    if keyword_search_backend not in set(snapshot.keyword_search_backend_names):
        problems.append(
            f"configured keyword search backend is not registered: {keyword_search_backend}"
        )
    return problems


def _validate_external_provider_settings(
    settings: PlatformExtensionSettings,
) -> list[str]:
    problems: list[str] = []
    llm_allowed, llm_unknown = _normalize_provider_list(settings.llm_external_allowed_providers)
    if llm_unknown:
        problems.append(
            "OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS contains unsupported external "
            "provider(s): " + ", ".join(llm_unknown)
        )
    if not llm_allowed:
        problems.append(
            "OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS must include at least one "
            "supported external provider"
        )
    ai_allowed, ai_unknown = _normalize_ai_external_provider_list(
        settings.ai_allowed_external_providers
    )
    ai_default_llm = normalize_external_llm_provider_id(settings.ai_default_external_llm_provider)
    ai_default = _normalize_external_search_provider_id(
        settings.ai_default_external_search_provider
    )
    if ai_unknown:
        problems.append(
            "OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS contains unsupported external "
            "provider(s): " + ", ".join(ai_unknown)
        )
    if not ai_allowed:
        problems.append(
            "OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS must include at least one "
            "supported external provider"
        )
    if _ai_external_llm_provider_settings_required(settings):
        if ai_default_llm is None:
            problems.append(
                "OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER contains unsupported "
                f"external provider: {settings.ai_default_external_llm_provider}"
            )
        elif ai_allowed and ai_default_llm not in ai_allowed:
            problems.append(
                "OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER must be listed in "
                f"OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS: {ai_default_llm}"
            )
    if ai_default is None:
        problems.append(
            "OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER contains unsupported "
            f"external provider: {settings.ai_default_external_search_provider}"
        )
    elif ai_allowed and ai_default not in ai_allowed:
        problems.append(
            "OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER must be listed in "
            f"OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS: {ai_default}"
        )
    return problems


def _ai_external_llm_provider_settings_required(
    settings: PlatformExtensionSettings,
) -> bool:
    return (
        settings.ai_external_llm_enabled
        or settings.ai_external_planning_enabled
        or settings.ai_external_reasoning_enabled
        or settings.ai_external_quality_review_enabled
    )


def _normalize_provider_list(value: str) -> tuple[set[str], list[str]]:
    providers: set[str] = set()
    unknown: list[str] = []
    for raw_provider in str(value or "").split(","):
        provider = raw_provider.strip().lower()
        if not provider:
            continue
        normalized = normalize_external_llm_provider_id(provider)
        if normalized is None:
            unknown.append(provider)
            continue
        providers.add(normalized)
    return providers, unknown


def _normalize_ai_external_provider_list(value: str) -> tuple[set[str], list[str]]:
    providers: set[str] = set()
    unknown: list[str] = []
    for raw_provider in str(value or "").split(","):
        provider = raw_provider.strip().lower()
        if not provider:
            continue
        normalized = normalize_external_llm_provider_id(
            provider
        ) or _normalize_external_search_provider_id(provider)
        if normalized is None:
            unknown.append(provider)
            continue
        providers.add(normalized)
    return providers, unknown


def _normalize_external_search_provider_id(provider: str | None) -> str | None:
    llm_provider = normalize_external_llm_provider_id(provider)
    if llm_provider is not None:
        return llm_provider
    adapter_name = normalize_external_execution_adapter_name(provider)
    if adapter_name in set(supported_external_search_execution_adapters()):
        return adapter_name
    return None


def _validate_llm_registry_contracts(
    snapshot: PlatformExtensionRegistrySnapshot,
    settings: PlatformExtensionSettings,
) -> list[str]:
    config_provider_ids = {
        key.split(":", maxsplit=1)[1]
        for key in snapshot.llm_pool_config_resolver_keys
        if key.startswith("external:")
    }
    execution_provider_ids = {
        key.split(":", maxsplit=1)[1]
        for key in snapshot.llm_execution_adapter_keys
        if key.startswith("external:") and not key.endswith(":*")
    }
    profile_provider_ids = {
        key.split(":", maxsplit=1)[1]
        for key in snapshot.llm_generation_profile_keys
        if key.startswith("external:") and not key.endswith(":*")
    }
    official_provider_ids = set(snapshot.llm_external_provider_ids)
    configured_provider_ids = _configured_external_llm_provider_ids(settings)
    problems: list[str] = []
    missing_config = sorted(official_provider_ids - config_provider_ids)
    if missing_config:
        problems.append(
            "external LLM providers without pool config resolvers: " + ", ".join(missing_config)
        )
    missing_configured_config = sorted(configured_provider_ids - config_provider_ids)
    if missing_configured_config:
        problems.append(
            "configured external LLM providers without pool config resolvers: "
            + ", ".join(missing_configured_config)
        )
    missing_execution = sorted(official_provider_ids - execution_provider_ids)
    if missing_execution:
        problems.append(
            "external LLM providers without execution adapters: " + ", ".join(missing_execution)
        )
    fallback_execution_registered = "external:*" in snapshot.llm_execution_adapter_keys
    missing_configured_execution = sorted(
        provider_id
        for provider_id in configured_provider_ids - execution_provider_ids
        if not (
            fallback_execution_registered
            and _external_provider_allows_openai_compatible_fallback(provider_id)
        )
    )
    if missing_configured_execution:
        problems.append(
            "configured external LLM providers without execution adapters: "
            + ", ".join(missing_configured_execution)
        )
    missing_profile = sorted(official_provider_ids - profile_provider_ids)
    if missing_profile:
        problems.append(
            "external LLM providers without generation profiles: " + ", ".join(missing_profile)
        )
    fallback_profile_registered = "external:*" in snapshot.llm_generation_profile_keys
    missing_configured_profile = sorted(
        provider_id
        for provider_id in configured_provider_ids - profile_provider_ids
        if not (
            fallback_profile_registered
            and _external_provider_allows_openai_compatible_fallback(provider_id)
        )
    )
    if missing_configured_profile:
        problems.append(
            "configured external LLM providers without generation profiles: "
            + ", ".join(missing_configured_profile)
        )
    return problems


def _external_provider_allows_openai_compatible_fallback(provider_id: str) -> bool:
    descriptor = external_llm_provider_descriptor(provider_id)
    return bool(descriptor and descriptor.openai_compatible)


def _configured_external_llm_provider_ids(
    settings: PlatformExtensionSettings,
) -> set[str]:
    providers, _unknown = _normalize_provider_list(settings.llm_external_allowed_providers)
    return providers


def _validate_retrieval_partition_registry_contracts() -> list[str]:
    problems: list[str] = []
    supported_candidate_scopes = {"company", "workspace", "personal"}
    supported_transition_modes = {"generic", "source_owned"}
    for adapter in retrieval_partition_adapters():
        normalized_scopes = tuple(
            dict.fromkeys(
                str(scope).strip()
                for scope in adapter.allowed_candidate_scopes
                if str(scope).strip()
            )
        )
        if not normalized_scopes:
            problems.append(
                f"retrieval partition adapter must allow candidate scopes: {adapter.adapter_id}"
            )
        elif tuple(adapter.allowed_candidate_scopes) != normalized_scopes:
            problems.append(
                "retrieval partition adapter candidate scopes are not normalized: "
                f"{adapter.adapter_id}"
            )
        unknown_scopes = sorted(set(normalized_scopes) - supported_candidate_scopes)
        if unknown_scopes:
            problems.append(
                "retrieval partition adapter has unsupported candidate scopes: "
                f"{adapter.adapter_id} -> {', '.join(unknown_scopes)}"
            )
        normalized_transitions = tuple(
            dict.fromkeys(
                str(operation).strip()
                for operation in adapter.allowed_transitions
                if str(operation).strip()
            )
        )
        if tuple(adapter.allowed_transitions) != normalized_transitions:
            problems.append(
                f"retrieval partition adapter transitions are not normalized: {adapter.adapter_id}"
            )
        raw_transition_mode = getattr(adapter, "transition_mode", "")
        normalized_transition_mode = str(raw_transition_mode).strip()
        if not normalized_transition_mode:
            problems.append(
                f"retrieval partition adapter transition mode is missing: {adapter.adapter_id}"
            )
        elif raw_transition_mode != normalized_transition_mode:
            problems.append(
                "retrieval partition adapter transition mode is not normalized: "
                f"{adapter.adapter_id}"
            )
        elif normalized_transition_mode not in supported_transition_modes:
            problems.append(
                "retrieval partition adapter has unsupported transition mode: "
                f"{adapter.adapter_id} -> {normalized_transition_mode}"
            )

    source_access_by_resource_type = {
        resource_type: adapter
        for adapter in get_source_access_adapters()
        for resource_type in adapter.resource_types
    }
    partition_resource_types = {
        resource_type
        for adapter in retrieval_partition_adapters()
        for resource_type in adapter.resource_types
    }
    missing_source_access = sorted(partition_resource_types - set(source_access_by_resource_type))
    if missing_source_access:
        problems.append(
            "retrieval partition adapter resources without source access adapters: "
            + ", ".join(missing_source_access)
        )

    declarations_by_resource_type: dict[str, list[tuple[str, str]]] = {}

    def validate_reference(
        *,
        owner: str,
        resource_type: str,
        partition_adapter_id: str | None,
    ) -> None:
        normalized_resource_type = str(resource_type).strip()
        normalized_adapter_id = str(partition_adapter_id or "").strip()
        if not normalized_adapter_id:
            problems.append(
                "retrieval partition adapter reference is missing: "
                f"{owner} -> {normalized_resource_type}"
            )
            return
        declarations_by_resource_type.setdefault(normalized_resource_type, []).append(
            (owner, normalized_adapter_id)
        )
        partition_adapter = get_retrieval_partition_adapter(normalized_adapter_id)
        if partition_adapter is None:
            problems.append(
                "retrieval partition adapter reference is not registered: "
                f"{owner}/{normalized_resource_type} -> {normalized_adapter_id}"
            )
            return
        if normalized_resource_type not in partition_adapter.resource_types:
            problems.append(
                "retrieval partition adapter does not claim resource: "
                f"{owner}/{normalized_resource_type} -> {normalized_adapter_id}"
            )

    for adapter in search_entity_adapters():
        validate_reference(
            owner=f"search:{adapter.entity_type}",
            resource_type=adapter.resource_type,
            partition_adapter_id=adapter.partition_adapter_id,
        )
    for adapter in rag_resource_adapters():
        validate_reference(
            owner=f"rag:{adapter.resource_type}",
            resource_type=adapter.resource_type,
            partition_adapter_id=adapter.partition_adapter_id,
        )
    for adapter in get_source_access_adapters():
        for resource_type in adapter.resource_types:
            validate_reference(
                owner=f"source_access:{resource_type}",
                resource_type=resource_type,
                partition_adapter_id=getattr(adapter, "partition_adapter_id", None),
            )

    for resource_type, declarations in sorted(declarations_by_resource_type.items()):
        adapter_ids = {adapter_id for _owner, adapter_id in declarations}
        if len(adapter_ids) <= 1:
            continue
        details = ", ".join(f"{owner}={adapter_id}" for owner, adapter_id in sorted(declarations))
        problems.append(
            f"retrieval partition adapter mismatch for resource {resource_type}: {details}"
        )
    return problems


def _validate_search_registry_contracts(
    snapshot: PlatformExtensionRegistrySnapshot,
) -> list[str]:
    descriptor_entity_types = set(snapshot.search_entity_types)
    adapter_entity_types = set(snapshot.search_entity_adapter_types)
    projection_entity_types = {
        str(entity_type).strip()
        for adapter in get_search_projection_adapters()
        for entity_type in adapter.entity_types
        if str(entity_type).strip()
    }
    source_access_resource_types = set(snapshot.source_access_resource_types)
    source_access_adapters = get_source_access_adapters()
    descriptor_resource_types = {
        descriptor.resource_type
        for descriptor in search_entity_descriptors()
        if descriptor.resource_type.strip()
    }

    problems: list[str] = []
    for adapter in search_entity_adapters():
        owner = get_workspace_app_catalog_item(adapter.owner_app_id)
        owner_registration = get_workspace_app_registration(adapter.owner_app_id)
        if owner is None:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} references unknown owner app: {adapter.owner_app_id}"
            )
        elif owner.availability_scope != "workspace":
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} owner app must be workspace-available: "
                f"{adapter.owner_app_id}"
            )
        elif owner_registration is not adapter.owner_app:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} must use its canonical owner app registration: "
                f"{adapter.owner_app_id}"
            )
        backend_domain = adapter.owner_app.backend_domain
        if not backend_domain:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} owner app must declare backend_domain: "
                f"{adapter.owner_app_id}"
            )
        loader_domain_mismatches = (
            [
                f"{loader_name}={_callable_module_name(loader)}"
                for loader_name, loader in (
                    ("workspace_loader", adapter.workspace_loader),
                    ("document_loader", adapter.document_loader),
                )
                if not _callable_belongs_to_backend_domain(loader, backend_domain)
            ]
            if backend_domain
            else []
        )
        if loader_domain_mismatches:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} loaders must belong to backend domain "
                f"{backend_domain}: " + ", ".join(loader_domain_mismatches)
            )

        missing_lifecycle_operations = [
            operation
            for operation in ("create", "update", "delete")
            if not adapter.index_hooks.for_operation(operation)
        ]
        if missing_lifecycle_operations:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} must declare index hooks for: "
                + ", ".join(missing_lifecycle_operations)
            )

        missing_index_hooks: set[str] = set()
        owner_mismatched_hooks: set[str] = set()
        entity_mismatched_hooks: set[str] = set()
        operation_mismatched_hooks: set[str] = set()
        hook_domain_mismatches: set[str] = set()
        for operation in ("create", "update", "delete"):
            for hook_name in adapter.index_hooks.for_operation(operation):
                hook_registration = get_search_index_hook_registration(hook_name)
                if hook_registration is None:
                    missing_index_hooks.add(hook_name)
                    continue
                if hook_registration.owner_app is not adapter.owner_app:
                    owner_mismatched_hooks.add(hook_name)
                if hook_registration.entity_type != adapter.entity_type:
                    entity_mismatched_hooks.add(hook_name)
                if operation not in hook_registration.operations:
                    operation_mismatched_hooks.add(f"{hook_name} ({operation})")
                hook_backend_domain = hook_registration.owner_app.backend_domain
                if not hook_backend_domain or not _callable_belongs_to_backend_domain(
                    hook_registration.hook, hook_backend_domain
                ):
                    hook_domain_mismatches.add(
                        f"{hook_name}={_callable_module_name(hook_registration.hook)}"
                    )
        if missing_index_hooks:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} references unregistered index hooks: "
                + ", ".join(sorted(missing_index_hooks))
            )
        if owner_mismatched_hooks:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} references index hooks owned by another app: "
                + ", ".join(sorted(owner_mismatched_hooks))
            )
        if entity_mismatched_hooks:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} references index hooks for another entity: "
                + ", ".join(sorted(entity_mismatched_hooks))
            )
        if operation_mismatched_hooks:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} references index hooks without lifecycle operation: "
                + ", ".join(sorted(operation_mismatched_hooks))
            )
        if hook_domain_mismatches:
            problems.append(
                "workspace keyword search entity "
                f"{adapter.entity_type} index hook callables must belong to their owner app "
                "domain: " + ", ".join(sorted(hook_domain_mismatches))
            )

    missing_entity_adapter = sorted(descriptor_entity_types - adapter_entity_types)
    if missing_entity_adapter:
        problems.append(
            "search entity descriptors without entity adapters: "
            + ", ".join(missing_entity_adapter)
        )

    missing_projection = sorted(descriptor_entity_types - projection_entity_types)
    if missing_projection:
        problems.append(
            "search entity descriptors without projection adapters: "
            + ", ".join(missing_projection)
        )

    missing_descriptor = sorted(projection_entity_types - descriptor_entity_types)
    if missing_descriptor:
        problems.append(
            "search projection adapters without entity descriptors: "
            + ", ".join(missing_descriptor)
        )

    missing_acl = sorted(descriptor_resource_types - source_access_resource_types)
    if missing_acl:
        problems.append(
            "search entity descriptors without source access adapters: " + ", ".join(missing_acl)
        )
    missing_keyword_acl: list[str] = []
    invalid_keyword_acl: list[str] = []
    unmapped_keyword_acl_fields: set[tuple[str, str]] = set()
    keyword_mapping_fields = keyword_acl_query_field_names()
    keyword_acl_shapes_by_adapter: dict[int, _KeywordAclShape | str] = {}
    for descriptor in search_entity_descriptors():
        matching_adapters = [
            adapter
            for adapter in source_access_adapters
            if descriptor.resource_type in adapter.resource_types
            and descriptor.entity_type in getattr(adapter, "keyword_acl_entity_types", ())
        ]
        if not matching_adapters:
            missing_keyword_acl.append(descriptor.entity_type)
            continue
        shapes = [
            _keyword_acl_shape(adapter, cache=keyword_acl_shapes_by_adapter)
            for adapter in matching_adapters
        ]
        if not any(descriptor.entity_type in shape.entity_types for shape in shapes):
            invalid_keyword_acl.append(descriptor.entity_type)
        for shape in shapes:
            for field in shape.fields - keyword_mapping_fields:
                unmapped_keyword_acl_fields.add((descriptor.entity_type, field))

    missing_keyword_acl = sorted(missing_keyword_acl)
    if missing_keyword_acl:
        problems.append(
            "search entity descriptors without keyword ACL branches: "
            + ", ".join(missing_keyword_acl)
        )
    invalid_keyword_acl = sorted(invalid_keyword_acl)
    if invalid_keyword_acl:
        problems.append(
            "keyword ACL branches do not cover declared search entity types: "
            + ", ".join(invalid_keyword_acl)
        )
    if unmapped_keyword_acl_fields:
        problems.append(
            "keyword ACL branches reference unmapped OpenSearch fields: "
            + ", ".join(
                f"{entity_type}.{field}"
                for entity_type, field in sorted(unmapped_keyword_acl_fields)
            )
        )
    return problems


def _callable_belongs_to_backend_domain(value: Any, backend_domain: str) -> bool:
    module_name = _callable_module_name(value)
    domain_module = f"open_work_hub_api.domains.{backend_domain}"
    return module_name == domain_module or module_name.startswith(f"{domain_module}.")


def _callable_module_name(value: Any) -> str:
    return str(getattr(value, "__module__", "") or "<unknown>").strip()


class _KeywordAclShapePolicy:
    workspace = SimpleNamespace(id="__workspace__")
    user = SimpleNamespace(id="__user__")

    def __init__(self, workspace_role: str | None) -> None:
        self.workspace_role = workspace_role

    def _accessible_team_ids(self) -> list[str]:
        return ["__team__"]

    def _keyword_entity_branch(
        self,
        entity_type: str,
        clauses: list[KeywordAclClause],
    ) -> KeywordAclBranch:
        return KeywordAclBranch(entity_type=entity_type, clauses=tuple(clauses))

    def _keyword_acl_clause(
        self,
        field: str,
        value: str | list[str] | tuple[str, ...],
    ) -> KeywordAclClause:
        return keyword_acl_clause(field, value)


@dataclass(frozen=True)
class _KeywordAclShape:
    entity_types: frozenset[str] = frozenset()
    fields: frozenset[str] = frozenset()


def _keyword_acl_shape(
    adapter: Any,
    *,
    cache: dict[int, _KeywordAclShape | str],
) -> _KeywordAclShape:
    cache_key = id(adapter)
    cached = cache.get(cache_key)
    if isinstance(cached, _KeywordAclShape):
        return cached
    if isinstance(cached, str):
        return _KeywordAclShape()
    try:
        shape = _merge_keyword_acl_shapes(
            _keyword_acl_shape_from_value(
                adapter.keyword_acl_branches(_KeywordAclShapePolicy(workspace_role))
            )
            for workspace_role in (None, "member", "admin")
        )
    except Exception as exc:
        cache[cache_key] = str(exc)
        return _KeywordAclShape()
    cache[cache_key] = shape
    return shape


def _keyword_acl_shape_from_value(value: Any) -> _KeywordAclShape:
    if isinstance(value, list):
        return _merge_keyword_acl_shapes(_keyword_acl_shape_from_value(item) for item in value)
    if isinstance(value, tuple):
        return _merge_keyword_acl_shapes(_keyword_acl_shape_from_value(item) for item in value)
    if isinstance(value, KeywordAclBranch):
        return _KeywordAclShape(
            entity_types=frozenset({value.entity_type}),
            fields=frozenset(clause.field for clause in value.clauses),
        )
    if isinstance(value, KeywordAclClause):
        return _KeywordAclShape(fields=frozenset({value.field}))
    if not isinstance(value, dict):
        return _KeywordAclShape()

    entity_types: set[str] = set()
    fields: set[str] = set()
    term = value.get("term")
    if isinstance(term, dict):
        entity_type = term.get("entity_type")
        if isinstance(entity_type, str) and entity_type.strip():
            entity_types.add(entity_type.strip())
        fields.update(str(field).strip() for field in term if field != "entity_type")
    terms = value.get("terms")
    if isinstance(terms, dict):
        raw_entity_types = terms.get("entity_type")
        if isinstance(raw_entity_types, list):
            entity_types.update(
                item.strip() for item in raw_entity_types if isinstance(item, str) and item.strip()
            )
        fields.update(str(field).strip() for field in terms if field != "entity_type")

    bool_clause = value.get("bool")
    if isinstance(bool_clause, dict):
        for key in ("filter", "must", "must_not", "should"):
            child_shape = _keyword_acl_shape_from_value(bool_clause.get(key))
            entity_types.update(child_shape.entity_types)
            fields.update(child_shape.fields)
    return _KeywordAclShape(
        entity_types=frozenset(entity_types),
        fields=frozenset(field for field in fields if field),
    )


def _merge_keyword_acl_shapes(shapes: Any) -> _KeywordAclShape:
    entity_types: set[str] = set()
    fields: set[str] = set()
    for shape in shapes:
        entity_types.update(shape.entity_types)
        fields.update(shape.fields)
    return _KeywordAclShape(
        entity_types=frozenset(entity_types),
        fields=frozenset(fields),
    )


def _validate_rag_registry_contracts(
    snapshot: PlatformExtensionRegistrySnapshot,
    settings: PlatformExtensionSettings,
) -> list[str]:
    source_access_resource_types = {
        resource_type
        for adapter in get_source_access_adapters()
        for resource_type in adapter.resource_types
    }
    rag_resource_types = {adapter.resource_type for adapter in rag_resource_adapters()}
    rag_source_resource_types = {adapter.resource_type for adapter in rag_source_adapters()}
    rag_visibility_resource_types = {
        adapter.resource_type for adapter in rag_visibility_scope_adapters()
    }
    listed_source_resource_types = {
        adapter.resource_type for adapter in listed_rag_source_adapters()
    }
    listed_source_app_ids_by_resource_type: dict[str, set[str]] = {}
    for source_adapter in listed_rag_source_adapters():
        listed_source_app_ids_by_resource_type.setdefault(
            source_adapter.resource_type,
            set(),
        ).add(str(source_adapter.app_id or "").strip())
    problems: list[str] = []
    if settings.rag_enabled:
        configured_providers = (
            (
                "vector index",
                settings.rag_vector_index_provider,
                snapshot.rag_vector_index_provider_names,
            ),
            (
                "embedding",
                settings.rag_embedding_provider,
                snapshot.rag_embedding_provider_names,
            ),
            (
                "rerank",
                settings.rag_rerank_provider,
                snapshot.rag_rerank_provider_names,
            ),
            (
                "OCR",
                settings.rag_ocr_provider,
                snapshot.rag_ocr_provider_names,
            ),
        )
        for provider_kind, configured_provider, supported_providers in configured_providers:
            provider_name = str(configured_provider or "").strip()
            if provider_name not in set(supported_providers):
                problems.append(
                    f"configured RAG {provider_kind} provider is not registered: "
                    f"{provider_name or '<empty>'}"
                )

    missing_resource_adapter = sorted(rag_source_resource_types - rag_resource_types)
    if missing_resource_adapter:
        problems.append(
            "RAG source adapters without resource adapters: " + ", ".join(missing_resource_adapter)
        )
    missing_source_acl = sorted(rag_source_resource_types - source_access_resource_types)
    if missing_source_acl:
        problems.append(
            "RAG source adapters without source access adapters: " + ", ".join(missing_source_acl)
        )
    missing_visibility_resource_adapter = sorted(rag_visibility_resource_types - rag_resource_types)
    if missing_visibility_resource_adapter:
        problems.append(
            "RAG visibility adapters without resource adapters: "
            + ", ".join(missing_visibility_resource_adapter)
        )
    for adapter in rag_resource_adapters():
        if (
            adapter.load_projection is not None
            and adapter.resource_type not in source_access_resource_types
        ):
            problems.append(
                f"RAG resource adapter lacks source access adapter: {adapter.resource_type}"
            )
        if adapter.include_in_workspace_reindex:
            if adapter.workspace_resource_ids is None:
                problems.append(
                    f"RAG reindex adapter lacks workspace resource loader: {adapter.resource_type}"
                )
            if adapter.load_projection is None:
                problems.append(
                    f"RAG reindex adapter lacks projection loader: {adapter.resource_type}"
                )
        if (
            adapter.include_in_default_query or adapter.include_in_workspace_reindex
        ) and adapter.resource_type not in listed_source_resource_types:
            problems.append(
                f"RAG query/reindex adapter lacks listed source adapter: {adapter.resource_type}"
            )
        if adapter.include_in_default_query or adapter.include_in_workspace_reindex:
            app_id = str(adapter.app_id or "").strip()
            if not app_id:
                problems.append(
                    f"RAG query/reindex adapter must declare app_id: {adapter.resource_type}"
                )
                continue
            source_app_ids = {
                source_app_id
                for source_app_id in listed_source_app_ids_by_resource_type.get(
                    adapter.resource_type,
                    set(),
                )
                if source_app_id
            }
            if source_app_ids and app_id not in source_app_ids:
                problems.append(
                    "RAG query/reindex adapter app_id does not match listed source "
                    f"adapter: {adapter.resource_type} ({app_id} not in "
                    f"{', '.join(sorted(source_app_ids))})"
                )
    return problems


__all__ = [
    "PlatformExtensionBootstrapError",
    "PlatformExtensionSettings",
    "PlatformExtensionRegistrySnapshot",
    "initialize_platform_extensions",
    "validate_platform_extension_registries",
]
