from __future__ import annotations

from dataclasses import replace
import importlib
from types import SimpleNamespace

import pytest

import open_work_hub_api.platform_extensions as platform_extensions
from open_work_hub_api.domains.ai.registry import (
    get_ai_capability_registry,
    reset_ai_capability_registry,
)
from open_work_hub_api.core import llm as llm_core
from open_work_hub_api.core.app_registry import AppCatalogItem, AppRegistration
from open_work_hub_api.core.asr_backend_registry import reset_asr_backends
from open_work_hub_api.core.settings import Settings, get_settings
from open_work_hub_api.core.llm_provider_registry import (
    ExternalLlmProviderDescriptor,
    ensure_default_external_llm_providers_registered,
    external_llm_provider_ids,
    register_external_llm_provider,
    reset_external_llm_providers,
)
from open_work_hub_api.core.platform_retirements import KNOWLEDGE_SOURCE_REGISTRY_RETIRED
from open_work_hub_api.core.llm_execution_adapters import (
    ensure_default_llm_execution_adapters_registered,
    llm_execution_adapter_keys,
    reset_llm_execution_adapters,
    supports_tool_calling,
)
from open_work_hub_api.core.llm_pool_config_registry import (
    LlmPoolConfigValues,
    ensure_default_llm_pool_config_resolvers_registered,
    llm_pool_config_resolver_keys,
    register_llm_pool_config_resolver,
    reset_llm_pool_config_resolvers,
)
from open_work_hub_api.core.llm_model_profiles import (
    LlmGenerationProfile,
    build_chat_payload,
    ensure_default_llm_generation_profiles_registered,
    llm_generation_profile_keys,
    register_llm_generation_profile,
    reset_llm_generation_profiles,
    resolve_reasoning_effort,
    select_llm_generation_profile,
)
from open_work_hub_api.domains.ai.runtime.external_adapters import (
    register_external_planner_execution_adapter,
    register_external_search_execution_adapter,
    reset_external_execution_adapters,
    select_external_planner_execution_adapter,
    select_external_search_execution_adapter,
    supported_external_planner_execution_adapters,
    supported_external_search_execution_adapters,
)
from open_work_hub_api.domains.ai.runtime.external_planner import ExternalPlannerExecutionResult
from open_work_hub_api.domains.ai.runtime.external_search import ExternalSearchExecutionResult
from open_work_hub_api.domains.conversations.default_scope_adapters import (
    ensure_conversation_scope_adapters_registered,
)
from open_work_hub_api.domains.conversations.scope_registry import (
    get_conversation_scope_adapter,
    reset_conversation_scope_adapters,
)
from open_work_hub_api.domains.docs.app_catalog import DOCS_APP
from open_work_hub_api.domains.docs import search_projection as docs_search_projection
from open_work_hub_api.domains.docs.search_projection import DOCS_KEYWORD_SEARCH_ADAPTER
from open_work_hub_api.domains.docs.source_access import NativeDocSourceAccessAdapter
from open_work_hub_api.domains.files import search_projection as file_search_projection
from open_work_hub_api.domains.files.retrieval_contract import (
    files_retrieval_active_for_environment,
)
from open_work_hub_api.domains.meeting.app_catalog import MEETING_APP
from open_work_hub_api.domains.planner.app_catalog import PLANNER_APP
from open_work_hub_api.domains.pms.app_catalog import PMS_APP
from open_work_hub_api.domains.rag.default_source_adapters import (
    ensure_rag_source_adapters_registered,
    resolve_rag_resource_types_for_source_kinds,
)
from open_work_hub_api.domains.rag.source_adapter_registry import (
    RagResourceAdapter,
    RagSourceAdapter,
    RagVisibilityScopeAdapter,
    get_rag_source_adapter,
    get_rag_resource_adapter,
    register_rag_source_adapter,
    register_rag_resource_adapter,
    register_rag_visibility_scope_adapter,
    reset_rag_source_adapters,
)
from open_work_hub_api.domains.retrieval.partition_adapter_ids import (
    FILES_RETRIEVAL_PARTITION_ADAPTER_ID,
)
from open_work_hub_api.domains.retrieval.partition_adapter_registry import (
    register_retrieval_partition_adapter,
    reset_retrieval_partition_adapters,
)
from open_work_hub_api.domains.search.default_entity_adapters import (
    ensure_search_entity_descriptors_registered,
)
from open_work_hub_api.domains.search.default_index_hook_adapters import (
    ensure_search_index_hooks_registered,
)
from open_work_hub_api.domains.search.backend_factory import reset_keyword_search_backends
from open_work_hub_api.domains.search.default_projection_adapters import (
    ensure_search_projection_adapters_registered,
)
from open_work_hub_api.domains.search.entity_adapter_registry import (
    SearchEntityAdapter,
    SearchIndexLifecycleHooks,
    get_search_entity_adapter,
    register_search_entity_adapter,
    reset_search_entity_adapters,
    resolve_keyword_search_scope,
    search_date_filter_fields,
    search_people_roles,
    search_sort_fields,
)
from open_work_hub_api.domains.search.entity_registry import (
    SearchEntityDescriptor,
    label_for_search_entity,
    register_search_entity_descriptor,
    reset_search_entity_descriptors,
)
from open_work_hub_api.domains.search import hooks as search_hooks
from open_work_hub_api.domains.search.hook_registry import (
    get_search_index_hook_registration,
    has_search_index_hook,
    register_search_index_hook,
    reset_search_index_hooks,
)
from open_work_hub_api.domains.search.projection_registry import (
    FunctionSearchProjectionAdapter,
    get_search_projection_adapter,
    register_search_projection_adapter,
    reset_search_projection_adapters,
)
from open_work_hub_api.domains.search.resource_mapping import resource_type_for_search_entity
from open_work_hub_api.domains.search.schemas import SearchEntityType
from open_work_hub_api.domains.source_access.policy import SourceAclPolicy
from open_work_hub_api.domains.source_access.default_adapters import (
    ensure_builtin_source_access_adapters_registered,
)
from open_work_hub_api.domains.source_access.targets import (
    TargetAccessProjection,
    TargetRef,
    target_access_allowed,
    ensure_builtin_target_access_adapters_registered,
    get_target_access_adapter,
    has_target_access_adapter,
    register_target_access_adapter,
    reset_target_access_adapters,
)
from open_work_hub_api.domains.source_access.registry import (
    get_source_access_adapter,
    has_source_access_adapter,
    register_source_access_adapter,
    reset_source_access_adapters,
)
from open_work_hub_api.domains.source_access.resource_types import (
    FILE_MANAGER_FILE_RESOURCE_TYPE,
    NATIVE_DOC_RESOURCE_TYPE,
)
from open_work_hub_api.platform_extensions import (
    PlatformExtensionBootstrapError,
    initialize_platform_extensions,
    validate_platform_extension_registries,
)


def _reset_platform_registries() -> None:
    reset_ai_capability_registry()
    reset_asr_backends()
    reset_external_execution_adapters()
    reset_external_llm_providers()
    reset_llm_pool_config_resolvers()
    reset_llm_execution_adapters()
    reset_llm_generation_profiles()
    reset_conversation_scope_adapters()
    reset_rag_source_adapters()
    reset_retrieval_partition_adapters()
    reset_keyword_search_backends()
    reset_search_entity_adapters()
    reset_search_entity_descriptors()
    reset_search_index_hooks()
    reset_search_projection_adapters()
    reset_target_access_adapters()
    reset_source_access_adapters()


def _test_settings(**overrides) -> Settings:
    return Settings(
        OPEN_WORK_HUB_POSTGRES_DSN=(
            "postgresql+psycopg://open_work_hub_test:open_work_hub_test@127.0.0.1:5432/open_work_hub_test"
        ),
        **overrides,
    )


def test_platform_extension_bootstrap_registers_core_adapters_after_reset() -> None:
    _reset_platform_registries()
    try:
        snapshot = initialize_platform_extensions()

        assert "docs.list_hub" in snapshot.ai_tool_names
        assert "cohere" in snapshot.asr_backend_names
        assert "inference_gateway" in snapshot.asr_backend_names
        assert "qwen_asr" in snapshot.asr_backend_names
        assert "whisper" in snapshot.asr_backend_names
        assert "mock" in snapshot.ai_external_planner_execution_adapter_names
        assert "mock" in snapshot.ai_external_search_execution_adapter_names
        assert "pms" in snapshot.target_access_app_ids
        assert "docs" not in snapshot.target_access_app_ids
        assert "pms" in snapshot.target_access_app_ids
        assert "files" in snapshot.conversation_scope_refs
        assert "meeting" in snapshot.conversation_scope_refs
        assert "opensearch" in snapshot.keyword_search_backend_names
        assert "external:anthropic" in snapshot.llm_execution_adapter_keys
        assert "external:gemini" in snapshot.llm_execution_adapter_keys
        assert "external:openai" in snapshot.llm_execution_adapter_keys
        assert "external:*" in snapshot.llm_execution_adapter_keys
        assert "local:*" in snapshot.llm_execution_adapter_keys
        assert "anthropic" in snapshot.llm_external_provider_ids
        assert "gemini" in snapshot.llm_external_provider_ids
        assert "openai" in snapshot.llm_external_provider_ids
        assert "external:anthropic" in snapshot.llm_generation_profile_keys
        assert "external:gemini" in snapshot.llm_generation_profile_keys
        assert "external:openai" in snapshot.llm_generation_profile_keys
        assert "external:*" in snapshot.llm_generation_profile_keys
        assert "local:docker-model-runner" in snapshot.llm_generation_profile_keys
        assert "local:vllm" in snapshot.llm_generation_profile_keys
        assert "local:*" in snapshot.llm_generation_profile_keys
        assert "external:anthropic" in snapshot.llm_pool_config_resolver_keys
        assert "external:gemini" in snapshot.llm_pool_config_resolver_keys
        assert "external:openai" in snapshot.llm_pool_config_resolver_keys
        assert "local:*" in snapshot.llm_pool_config_resolver_keys
        assert "inference_gateway" in snapshot.rag_embedding_provider_names
        assert "inference_gateway" in snapshot.rag_ocr_provider_names
        assert "inference_gateway" in snapshot.rag_rerank_provider_names
        assert "fake" in snapshot.rag_vector_index_provider_names
        assert NATIVE_DOC_RESOURCE_TYPE in snapshot.rag_resource_types
        assert FILE_MANAGER_FILE_RESOURCE_TYPE in snapshot.rag_resource_types
        assert "manual" in snapshot.rag_source_kinds
        assert "meeting" in snapshot.rag_visibility_scope_types
        assert "pms_label" in snapshot.rag_visibility_scope_types
        expected_retrieval_partition_adapter_ids = (
            "docs",
            "files",
            "meeting",
            "planner",
            "pms",
        )
        assert snapshot.retrieval_partition_adapter_ids == expected_retrieval_partition_adapter_ids
        assert SearchEntityType.DOC.value in snapshot.search_entity_adapter_types
        assert SearchEntityType.FILE.value in snapshot.search_entity_adapter_types
        assert SearchEntityType.DOC.value in snapshot.search_entity_types
        expected_source_access_resource_types = (
            "docs_native_doc",
            "file_manager_file",
            "meeting",
            "planner_event",
            "pms_task",
        )
        assert snapshot.source_access_resource_types == expected_source_access_resource_types
        assert has_search_index_hook("docs.enqueue_doc_search_index")
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_requires_retrieval_partition_registry() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        reset_retrieval_partition_adapters()

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="retrieval partition adapter registry is empty",
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_non_normalized_partition_policy_metadata(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        registered = platform_extensions.retrieval_partition_adapters()
        docs_adapter = next(adapter for adapter in registered if adapter.adapter_id == "docs")
        invalid_docs_adapter = SimpleNamespace(
            adapter_id=docs_adapter.adapter_id,
            source_namespace=docs_adapter.source_namespace,
            resource_types=docs_adapter.resource_types,
            allowed_candidate_scopes=(" company",),
            allowed_transitions=("publish_company ",),
            transition_mode=docs_adapter.transition_mode,
            bind_resource_partition=docs_adapter.bind_resource_partition,
        )
        monkeypatch.setattr(
            platform_extensions,
            "retrieval_partition_adapters",
            lambda: tuple(
                invalid_docs_adapter if adapter.adapter_id == "docs" else adapter
                for adapter in registered
            ),
        )

        with pytest.raises(PlatformExtensionBootstrapError) as exc_info:
            validate_platform_extension_registries(settings=_test_settings())

        message = str(exc_info.value)
        assert "retrieval partition adapter candidate scopes are not normalized: docs" in message
        assert "retrieval partition adapter transitions are not normalized: docs" in message
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_search_partition_resource_drift(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_platform_registries()
    try:
        monkeypatch.setattr(
            docs_search_projection,
            "DOCS_KEYWORD_SEARCH_ADAPTER",
            replace(
                DOCS_KEYWORD_SEARCH_ADAPTER,
                partition_adapter_id=FILES_RETRIEVAL_PARTITION_ADAPTER_ID,
            ),
        )

        with pytest.raises(PlatformExtensionBootstrapError) as exc_info:
            initialize_platform_extensions(settings=_test_settings())

        message = str(exc_info.value)
        assert (
            "retrieval partition adapter does not claim resource: "
            "search:doc/docs_native_doc -> files"
        ) in message
        assert "retrieval partition adapter mismatch for resource docs_native_doc" in message
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_rag_partition_adapter_mismatch() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        native_doc_adapter = get_rag_resource_adapter(NATIVE_DOC_RESOURCE_TYPE)
        assert native_doc_adapter is not None
        reset_rag_source_adapters()
        register_rag_resource_adapter(
            replace(
                native_doc_adapter,
                partition_adapter_id=FILES_RETRIEVAL_PARTITION_ADAPTER_ID,
            )
        )
        ensure_rag_source_adapters_registered()

        with pytest.raises(PlatformExtensionBootstrapError) as exc_info:
            validate_platform_extension_registries(settings=_test_settings())

        message = str(exc_info.value)
        assert (
            "retrieval partition adapter does not claim resource: "
            "rag:docs_native_doc/docs_native_doc -> files"
        ) in message
        assert "retrieval partition adapter mismatch for resource docs_native_doc" in message
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_source_access_partition_mismatch() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())

        class MismatchedNativeDocSourceAccessAdapter(NativeDocSourceAccessAdapter):
            partition_adapter_id = FILES_RETRIEVAL_PARTITION_ADAPTER_ID

        reset_source_access_adapters()
        register_source_access_adapter(MismatchedNativeDocSourceAccessAdapter())
        ensure_builtin_source_access_adapters_registered()

        with pytest.raises(PlatformExtensionBootstrapError) as exc_info:
            validate_platform_extension_registries(settings=_test_settings())

        message = str(exc_info.value)
        assert (
            "retrieval partition adapter does not claim resource: "
            "source_access:docs_native_doc/docs_native_doc -> files"
        ) in message
        assert "retrieval partition adapter mismatch for resource docs_native_doc" in message
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_requires_partition_resource_source_access() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        reset_source_access_adapters()

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match=(
                "retrieval partition adapter resources without source access adapters: "
                ".*docs_native_doc"
            ),
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_half_registered_search_entity() -> None:
    _reset_platform_registries()
    try:
        register_search_projection_adapter(
            FunctionSearchProjectionAdapter(
                entity_types=("plugin_record",),
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="search projection adapters without entity descriptors: plugin_record",
        ):
            validate_platform_extension_registries()
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_provider_without_runtime_adapter() -> None:
    _reset_platform_registries()
    try:
        register_external_llm_provider(ExternalLlmProviderDescriptor("plugin"))

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="external LLM providers without execution adapters: plugin",
        ):
            validate_platform_extension_registries()
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_llm_provider_without_execution_contracts() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_external_llm_provider(ExternalLlmProviderDescriptor("plugin"))
        register_llm_pool_config_resolver(
            pool="external",
            provider="plugin",
            resolver=lambda settings: LlmPoolConfigValues(
                provider="plugin",
                base_url="https://plugin.example/v1",
                api_key="plugin-key",
                default_model="plugin-default",
                canonical_model="plugin-canonical",
                long_generation_timeout_seconds=(
                    settings.llm_external_long_generation_timeout_seconds
                ),
                enabled=True,
            ),
        )

        with pytest.raises(PlatformExtensionBootstrapError) as excinfo:
            validate_platform_extension_registries(settings=_test_settings())

        message = str(excinfo.value)
        assert "external LLM providers without execution adapters: plugin" in message
        assert "external LLM providers without generation profiles: plugin" in message
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_gateway_tool_registry_drift(
    monkeypatch,
) -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        monkeypatch.setattr(
            platform_extensions,
            "default_gateway_tools_by_agent",
            lambda: {
                "domain.docs": ("docs.list_hub", "plugin.missing_builder"),
                "domain.unknown": ("docs.list_hub",),
            },
        )

        with pytest.raises(PlatformExtensionBootstrapError) as excinfo:
            validate_platform_extension_registries(settings=_test_settings())

        message = str(excinfo.value)
        assert "default gateway tools registered for unknown AI agent(s): domain.unknown" in message
        assert "default gateway tools without argument builders: plugin.missing_builder" in message
        assert (
            "default gateway tools missing from AI capability registry: "
            "plugin.missing_builder" in message
        )
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_keeps_disabled_rag_gateway_tools_registered(
    monkeypatch,
) -> None:
    _reset_platform_registries()
    get_settings.cache_clear()
    monkeypatch.setenv("OPEN_WORK_HUB_RAG_ENABLED", "0")
    try:
        snapshot = initialize_platform_extensions(
            settings=_test_settings(OPEN_WORK_HUB_RAG_ENABLED=False),
        )

        assert "rag.query" in snapshot.ai_tool_names
    finally:
        _reset_platform_registries()
        get_settings.cache_clear()


def test_platform_extension_validation_rejects_unregistered_asr_backend() -> None:
    _reset_platform_registries()
    try:
        settings = _test_settings(OPEN_WORK_HUB_API_ASR_BACKEND="plugin_asr")

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="configured ASR backend is not registered: plugin_asr",
        ):
            initialize_platform_extensions(settings=settings)
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_enabled_external_execution_adapter_without_support() -> (
    None
):
    _reset_platform_registries()
    try:
        planner_settings = _test_settings(
            OPEN_WORK_HUB_AI_EXTERNAL_PLANNER_EXECUTION_ENABLED=True,
            OPEN_WORK_HUB_AI_EXTERNAL_PLANNER_EXECUTION_ADAPTER="vendor-planner",
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match=(
                "configured AI external planner execution adapter is not registered: vendor-planner"
            ),
        ):
            initialize_platform_extensions(settings=planner_settings)

        search_settings = _test_settings(
            OPEN_WORK_HUB_AI_EXTERNAL_SEARCH_EXECUTION_ENABLED=True,
            OPEN_WORK_HUB_AI_EXTERNAL_SEARCH_EXECUTION_ADAPTER="vendor-search",
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match=(
                "configured AI external search execution adapter is not registered: vendor-search"
            ),
        ):
            initialize_platform_extensions(settings=search_settings)
    finally:
        _reset_platform_registries()


def test_external_execution_adapter_registries_support_extension_factories() -> None:
    _reset_platform_registries()
    try:

        class VendorPlannerAdapter:
            adapter_id = "external_planner_v0"
            execution_provider = "vendor-planner"

            def execute(self, request):
                return ExternalPlannerExecutionResult(
                    status="completed",
                    execution_provider=self.execution_provider,
                    provider=request.provider,
                    planned_agent_ids=["docs.writer"],
                )

        class VendorSearchAdapter:
            adapter_id = "external_search_v0"
            execution_provider = "vendor-search"

            def execute(self, request):
                return ExternalSearchExecutionResult(
                    status="completed",
                    execution_provider=self.execution_provider,
                    provider=request.provider,
                    result_count=1,
                )

        register_external_planner_execution_adapter(
            "vendor-planner",
            VendorPlannerAdapter,
        )
        register_external_search_execution_adapter(
            "vendor-search",
            VendorSearchAdapter,
        )

        assert "vendor-planner" in supported_external_planner_execution_adapters()
        assert "vendor-search" in supported_external_search_execution_adapters()

        planner = select_external_planner_execution_adapter(
            SimpleNamespace(ai_external_planner_execution_adapter="vendor-planner"),
            execution_enabled=True,
        )
        search = select_external_search_execution_adapter(
            SimpleNamespace(ai_external_search_execution_adapter="vendor-search"),
            execution_enabled=True,
        )

        assert planner.execution_provider == "vendor-planner"
        assert search.execution_provider == "vendor-search"
    finally:
        _reset_platform_registries()


def test_platform_validation_accepts_search_only_external_provider_adapter() -> None:
    _reset_platform_registries()
    try:

        class VendorSearchAdapter:
            adapter_id = "external_search_v0"
            execution_provider = "vendor-search"

            def execute(self, request):
                return ExternalSearchExecutionResult(
                    status="completed",
                    execution_provider=self.execution_provider,
                    provider=request.provider,
                    result_count=1,
                )

        register_external_search_execution_adapter(
            "vendor-search",
            VendorSearchAdapter,
        )
        settings = _test_settings(
            OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS="vendor-search",
            OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER="openai",
            OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER="vendor-search",
            OPEN_WORK_HUB_AI_EXTERNAL_SEARCH_ENABLED=True,
            OPEN_WORK_HUB_AI_EXTERNAL_SEARCH_EXECUTION_ENABLED=True,
            OPEN_WORK_HUB_AI_EXTERNAL_SEARCH_EXECUTION_ADAPTER="vendor-search",
        )

        snapshot = initialize_platform_extensions(settings=settings)

        assert "vendor-search" in snapshot.ai_external_search_execution_adapter_names
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_rag_source_without_resource_adapter() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_rag_source_adapter(
            RagSourceAdapter(
                source_kind="plugin",
                resource_type="plugin_resource",
                app_id="plugin",
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="RAG source adapters without resource adapters: plugin_resource",
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_queryable_rag_resource_without_listed_source() -> (
    None
):
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_rag_resource_adapter(
            RagResourceAdapter(
                resource_type="plugin_resource",
                app_id="plugin",
                include_in_default_query=True,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match=("RAG query/reindex adapter lacks listed source adapter: plugin_resource"),
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_queryable_rag_resource_without_app_id() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_rag_source_adapter(
            RagSourceAdapter(
                source_kind="plugin_source",
                resource_type="plugin_resource",
                app_id="plugin",
                include_in_source_listing=True,
            )
        )
        register_rag_resource_adapter(
            RagResourceAdapter(
                resource_type="plugin_resource",
                include_in_default_query=True,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="RAG query/reindex adapter must declare app_id: plugin_resource",
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_reindex_app_id_mismatch() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_rag_source_adapter(
            RagSourceAdapter(
                source_kind="plugin_source",
                resource_type="plugin_resource",
                app_id="plugin",
                include_in_source_listing=True,
            )
        )
        register_rag_resource_adapter(
            RagResourceAdapter(
                resource_type="plugin_resource",
                app_id="other_plugin",
                load_projection=lambda db, resource_id, rag_service: None,
                company_resource_ids=lambda db,: [],
                include_in_reindex=True,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match=(
                "RAG query/reindex adapter app_id does not match listed source "
                "adapter: plugin_resource"
            ),
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_rag_visibility_scope_without_resource_adapter() -> (
    None
):
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_rag_visibility_scope_adapter(
            RagVisibilityScopeAdapter(
                scope_type="plugin_scope",
                resource_type="plugin_resource",
                resource_ids=lambda db, job: [],
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="RAG visibility adapters without resource adapters: plugin_resource",
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_enabled_unknown_rag_provider() -> None:
    _reset_platform_registries()
    try:
        settings = _test_settings(
            OPEN_WORK_HUB_RAG_ENABLED=True,
            OPEN_WORK_HUB_RAG_VECTOR_INDEX_PROVIDER="missing-vector",
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="configured RAG vector index provider is not registered: missing-vector",
        ):
            initialize_platform_extensions(settings=settings)
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_search_entity_without_manifest() -> None:
    _reset_platform_registries()
    try:
        register_search_entity_descriptor(
            SearchEntityDescriptor(
                entity_type="plugin_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
            )
        )
        register_search_projection_adapter(
            FunctionSearchProjectionAdapter(
                entity_types=("plugin_record",),
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="search entity descriptors without entity adapters: plugin_record",
        ):
            validate_platform_extension_registries()
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_search_entity_without_keyword_acl_branch() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_APP,
                entity_type="plugin_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="search entity descriptors without keyword ACL branches: plugin_record",
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_search_entity_without_index_hooks() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_APP,
                entity_type="plugin_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="plugin_record must declare index hooks for: create, update, delete",
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


@pytest.mark.parametrize("missing_operation", ["create", "update", "delete"])
def test_platform_extension_validation_requires_each_search_index_lifecycle_hook(
    missing_operation: str,
) -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        hook_name = "plugin.enqueue_record_search_index"
        register_search_index_hook(
            hook_name,
            lambda: None,
            owner_app=DOCS_APP,
            entity_type="plugin_record",
            operations=("create", "update", "delete"),
        )
        hooks_by_operation = {
            operation: () if operation == missing_operation else (hook_name,)
            for operation in ("create", "update", "delete")
        }
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_APP,
                entity_type="plugin_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
                index_hooks=SearchIndexLifecycleHooks(**hooks_by_operation),
            )
        )

        with pytest.raises(PlatformExtensionBootstrapError) as exc_info:
            validate_platform_extension_registries(settings=_test_settings())

        assert f"plugin_record must declare index hooks for: {missing_operation}" in str(
            exc_info.value
        )
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_cross_checks_search_index_hook_metadata() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_search_index_hook(
            "plugin.create_record",
            lambda: None,
            owner_app=MEETING_APP,
            entity_type="plugin_record",
            operations=("create",),
        )
        register_search_index_hook(
            "plugin.update_record",
            lambda: None,
            owner_app=DOCS_APP,
            entity_type="other_record",
            operations=("update",),
        )
        register_search_index_hook(
            "plugin.delete_record",
            lambda: None,
            owner_app=DOCS_APP,
            entity_type="plugin_record",
            operations=("update",),
        )
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_APP,
                entity_type="plugin_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
                index_hooks=SearchIndexLifecycleHooks(
                    create=("plugin.create_record",),
                    update=("plugin.update_record",),
                    delete=("plugin.delete_record",),
                ),
            )
        )

        with pytest.raises(PlatformExtensionBootstrapError) as exc_info:
            validate_platform_extension_registries(settings=_test_settings())

        message = str(exc_info.value)
        assert "index hooks owned by another app: plugin.create_record" in message
        assert "index hooks for another entity: plugin.update_record" in message
        assert "index hooks without lifecycle operation: plugin.delete_record (delete)" in message
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_search_contract_owned_by_another_domain() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())

        def secret_company_loader(
            db,
        ):
            del db
            return []

        def secret_document_loader(db, *, entity_type, entity_id):
            del db, entity_type, entity_id
            return None

        def secret_index_hook():
            return None

        secret_company_loader.__module__ = "open_work_hub_api.domains.secret.search_projection"
        secret_document_loader.__module__ = "open_work_hub_api.domains.secret.search_projection"
        secret_index_hook.__module__ = "open_work_hub_api.domains.secret.search_hooks"

        hook_name = "secret.enqueue_record"
        register_search_index_hook(
            hook_name,
            secret_index_hook,
            owner_app=DOCS_APP,
            entity_type="secret_record",
            operations=("create", "update", "delete"),
        )
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_APP,
                entity_type="secret_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Secret Record",
                label_key="ai.search.entitySecretRecord",
                company_loader=secret_company_loader,
                document_loader=secret_document_loader,
                index_hooks=SearchIndexLifecycleHooks(
                    create=(hook_name,),
                    update=(hook_name,),
                    delete=(hook_name,),
                ),
            )
        )

        with pytest.raises(PlatformExtensionBootstrapError) as exc_info:
            validate_platform_extension_registries(settings=_test_settings())

        message = str(exc_info.value)
        assert "secret_record loaders must belong to backend domain docs" in message
        assert "secret_record index hook callables must belong to their owner app domain" in message
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_accepts_explicit_backend_domain_different_from_app_id(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        owner_app = AppRegistration(
            app_id="quality-search",
            title="Quality Search",
            route_base="/apps/quality-search",
            icon_key="search",
            backend_domain="quality_records",
        )
        owner_catalog = AppCatalogItem(
            app_id=owner_app.app_id,
            title=owner_app.title,
            route_base=owner_app.route_base,
            icon_key=owner_app.icon_key,
        )

        def company_loader(
            db,
        ):
            del db
            return []

        def document_loader(db, *, entity_type, entity_id):
            del db, entity_type, entity_id
            return None

        def index_hook():
            return None

        company_loader.__module__ = "open_work_hub_api.domains.quality_records.search_projection"
        document_loader.__module__ = "open_work_hub_api.domains.quality_records.search_projection"
        index_hook.__module__ = "open_work_hub_api.domains.quality_records.search_hooks"

        class QualitySourceAccessAdapter:
            adapter_id = "quality_records"
            partition_adapter_id = adapter_id
            source_namespace = "quality_records"
            resource_types = ("quality_record",)
            allowed_candidate_scopes = ("company",)
            allowed_transitions: tuple[str, ...] = ()
            transition_mode = "generic"
            keyword_acl_entity_types = ("quality_record",)

            def bind_resource_partition(
                self,
                db,
                *,
                resource_type: str,
                resource_id: str,
            ):
                raise AssertionError(
                    "quality partition binding is not exercised by registry validation"
                )

            def can_read_resource(self, policy, *, resource_type: str, resource_id: str) -> bool:
                del policy, resource_type, resource_id
                return False

            def can_read_rag_resource(
                self,
                policy,
                *,
                resource_type: str,
                resource_id: str,
            ) -> bool:
                del policy, resource_type, resource_id
                return False

            def has_accessible_source(self, policy, *, resource_type: str) -> bool:
                del policy, resource_type
                return False

            def keyword_acl_branches(self, policy):
                return [
                    policy._keyword_entity_branch(
                        "quality_record",
                        [policy._keyword_acl_clause("owner_user_id", policy.user.id)],
                    )
                ]

        hook_name = "quality_records.enqueue_record"
        source_access_adapter = QualitySourceAccessAdapter()
        register_retrieval_partition_adapter(source_access_adapter)
        register_source_access_adapter(source_access_adapter)
        register_search_index_hook(
            hook_name,
            index_hook,
            owner_app=owner_app,
            entity_type="quality_record",
            operations=("create", "update", "delete"),
        )
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=owner_app,
                entity_type="quality_record",
                resource_type="quality_record",
                label="Quality Record",
                label_key="ai.search.entityQualityRecord",
                company_loader=company_loader,
                document_loader=document_loader,
                partition_adapter_id=source_access_adapter.partition_adapter_id,
                index_hooks=SearchIndexLifecycleHooks(
                    create=(hook_name,),
                    update=(hook_name,),
                    delete=(hook_name,),
                ),
            )
        )

        catalog_lookup = platform_extensions.get_app_catalog_item
        registration_lookup = platform_extensions.get_app_registration
        monkeypatch.setattr(
            platform_extensions,
            "get_app_catalog_item",
            lambda app_id: owner_catalog if app_id == owner_app.app_id else catalog_lookup(app_id),
        )
        monkeypatch.setattr(
            platform_extensions,
            "get_app_registration",
            lambda app_id: owner_app if app_id == owner_app.app_id else registration_lookup(app_id),
        )

        snapshot = validate_platform_extension_registries(settings=_test_settings())

        assert "quality_record" in snapshot.search_entity_types
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_requires_explicit_search_backend_domain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        owner_app = AppRegistration(
            app_id="quality-search",
            title="Quality Search",
            route_base="/apps/quality-search",
            icon_key="search",
        )
        owner_catalog = AppCatalogItem(
            app_id=owner_app.app_id,
            title=owner_app.title,
            route_base=owner_app.route_base,
            icon_key=owner_app.icon_key,
        )
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=owner_app,
                entity_type="quality_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Quality Record",
                label_key="ai.search.entityQualityRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        catalog_lookup = platform_extensions.get_app_catalog_item
        registration_lookup = platform_extensions.get_app_registration
        monkeypatch.setattr(
            platform_extensions,
            "get_app_catalog_item",
            lambda app_id: owner_catalog if app_id == owner_app.app_id else catalog_lookup(app_id),
        )
        monkeypatch.setattr(
            platform_extensions,
            "get_app_registration",
            lambda app_id: owner_app if app_id == owner_app.app_id else registration_lookup(app_id),
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="quality_record owner app must declare backend_domain: quality-search",
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_keyword_acl_branch_entity_drift() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())

        class PluginSourceAccessAdapter:
            resource_types = ("plugin_resource",)
            keyword_acl_entity_types = ("plugin_record",)

            def can_read_resource(
                self,
                policy,
                *,
                resource_type: str,
                resource_id: str,
            ) -> bool:
                del policy, resource_type, resource_id
                return False

            def can_read_rag_resource(
                self,
                policy,
                *,
                resource_type: str,
                resource_id: str,
            ) -> bool:
                del policy, resource_type, resource_id
                return False

            def has_accessible_source(self, policy, *, resource_type: str) -> bool:
                del policy, resource_type
                return False

            def keyword_acl_branches(self, policy):
                return [policy._keyword_entity_branch("other_record", [])]

        register_source_access_adapter(PluginSourceAccessAdapter())
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_APP,
                entity_type="plugin_record",
                resource_type="plugin_resource",
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match=("keyword ACL branches do not cover declared search entity types: plugin_record"),
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_unmapped_keyword_acl_field() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())

        class PluginSourceAccessAdapter:
            resource_types = ("plugin_resource",)
            keyword_acl_entity_types = ("plugin_record",)

            def can_read_resource(self, policy, *, resource_type: str, resource_id: str) -> bool:
                del policy, resource_type, resource_id
                return False

            def can_read_rag_resource(
                self,
                policy,
                *,
                resource_type: str,
                resource_id: str,
            ) -> bool:
                del policy, resource_type, resource_id
                return False

            def has_accessible_source(self, policy, *, resource_type: str) -> bool:
                del policy, resource_type
                return False

            def keyword_acl_branches(self, policy):
                return [
                    policy._keyword_entity_branch(
                        "plugin_record",
                        [policy._keyword_acl_clause("project_ids", "project-1")],
                    )
                ]

        register_source_access_adapter(PluginSourceAccessAdapter())
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_APP,
                entity_type="plugin_record",
                resource_type="plugin_resource",
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match=(
                "keyword ACL branches reference unmapped OpenSearch fields: "
                "plugin_record.project_ids"
            ),
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_checks_acl_fields_for_company_admin_and_member() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())

        class RoleSensitiveSourceAccessAdapter:
            resource_types = ("role_sensitive_resource",)
            keyword_acl_entity_types = ("role_sensitive_record",)

            def can_read_resource(self, policy, *, resource_type: str, resource_id: str) -> bool:
                del policy, resource_type, resource_id
                return False

            def can_read_rag_resource(
                self,
                policy,
                *,
                resource_type: str,
                resource_id: str,
            ) -> bool:
                del policy, resource_type, resource_id
                return False

            def has_accessible_source(self, policy, *, resource_type: str) -> bool:
                del policy, resource_type
                return False

            def keyword_acl_branches(self, policy):
                field = "admin_project_ids" if policy.is_platform_admin else "member_project_ids"
                return [
                    policy._keyword_entity_branch(
                        "role_sensitive_record",
                        [policy._keyword_acl_clause(field, "value")],
                    )
                ]

        register_source_access_adapter(RoleSensitiveSourceAccessAdapter())
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_APP,
                entity_type="role_sensitive_record",
                resource_type="role_sensitive_resource",
                label="Role Sensitive Record",
                label_key="ai.search.entityRoleSensitiveRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        with pytest.raises(PlatformExtensionBootstrapError) as exc_info:
            validate_platform_extension_registries(settings=_test_settings())

        message = str(exc_info.value)
        assert "role_sensitive_record.admin_project_ids" in message
        assert "role_sensitive_record.member_project_ids" in message
    finally:
        _reset_platform_registries()


def test_default_search_projection_adapters_reregister_after_reset() -> None:
    reset_search_projection_adapters()

    ensure_search_projection_adapters_registered()
    ensure_search_projection_adapters_registered()

    assert get_search_projection_adapter(SearchEntityType.DOC) is not None
    assert get_search_projection_adapter(SearchEntityType.PMS_TASK) is not None
    assert get_search_projection_adapter(SearchEntityType.MEETING) is not None
    assert get_search_projection_adapter(SearchEntityType.PLANNER_EVENT) is None


def test_company_keyword_search_scope_projects_only_enabled_owner_entities() -> None:
    _reset_platform_registries()
    try:
        scope = resolve_keyword_search_scope({"docs", "pms"})

        assert scope.entity_types == ("doc", "pms_task")
        assert scope.constrain_entity_types([]) == ("doc", "pms_task")
        assert scope.constrain_entity_types(["meeting", "doc", "unknown"]) == ("doc",)
    finally:
        _reset_platform_registries()


def test_files_keyword_search_adapter_can_activate_after_partition_generation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _reset_platform_registries()
    try:
        assert files_retrieval_active_for_environment(
            environment="development",
            env_profile="dev",
            rag_enabled=True,
            operator_enabled=True,
            partition_generation_ready=True,
        )
        monkeypatch.setattr(
            file_search_projection,
            "FILES_KEYWORD_SEARCH_ADAPTER",
            replace(
                file_search_projection.FILES_KEYWORD_SEARCH_ADAPTER,
                active=True,
            ),
        )
        ensure_search_entity_descriptors_registered()
        adapter = get_search_entity_adapter(SearchEntityType.FILE)

        assert adapter is not None
        assert adapter.active is True
        assert resolve_keyword_search_scope({"files"}).entity_types == ("file",)
    finally:
        _reset_platform_registries()


@pytest.mark.parametrize(
    ("owner_app", "message"),
    [
        (
            AppRegistration(
                app_id="missing-app",
                title="Missing App",
                route_base="/apps/missing-app",
                icon_key="missing",
            ),
            "references unknown owner app: missing-app",
        ),
        (
            PLANNER_APP,
            "owner app must declare backend_domain: planner",
        ),
    ],
)
def test_platform_extension_validation_rejects_invalid_search_entity_owner(
    owner_app: AppRegistration,
    message: str,
) -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=owner_app,
                entity_type="plugin_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        with pytest.raises(PlatformExtensionBootstrapError, match=message):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_platform_extension_validation_rejects_copied_owner_app_registration() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=replace(DOCS_APP),
                entity_type="plugin_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
            )
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="plugin_record must use its canonical owner app registration: docs",
        ):
            validate_platform_extension_registries(settings=_test_settings())
    finally:
        _reset_platform_registries()


def test_search_entity_adapter_registers_descriptor_and_projection_atomically() -> None:
    _reset_platform_registries()
    try:
        adapter = SearchEntityAdapter(
            owner_app=DOCS_APP,
            entity_type="plugin_record",
            resource_type=NATIVE_DOC_RESOURCE_TYPE,
            label="Plugin Record",
            label_key="ai.search.entityPluginRecord",
            company_loader=lambda db,: [{"entity_id": "company-doc"}],
            document_loader=lambda db, *, entity_type, entity_id: {
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )

        register_search_entity_adapter(adapter)

        assert get_search_entity_adapter("plugin_record") == adapter
        assert resource_type_for_search_entity("plugin_record") == NATIVE_DOC_RESOURCE_TYPE
        projection_adapter = get_search_projection_adapter("plugin_record")
        assert projection_adapter == adapter
        assert projection_adapter is not None
        assert projection_adapter.load_document(
            SimpleNamespace(),
            entity_type="plugin_record",
            entity_id="record-1",
        ) == {"entity_type": "plugin_record", "entity_id": "record-1"}
    finally:
        _reset_platform_registries()


def test_search_entity_adapter_requires_localized_label_key() -> None:
    _reset_platform_registries()
    try:
        with pytest.raises(
            ValueError,
            match="plugin_record must declare label_key",
        ):
            register_search_entity_adapter(
                SearchEntityAdapter(
                    owner_app=DOCS_APP,
                    entity_type="plugin_record",
                    resource_type=NATIVE_DOC_RESOURCE_TYPE,
                    label="Plugin Record",
                    label_key="",
                    company_loader=lambda db,: [],
                    document_loader=lambda db, *, entity_type, entity_id: None,
                )
            )
    finally:
        _reset_platform_registries()


def test_search_entity_adapter_exposes_extension_query_vocabulary() -> None:
    _reset_platform_registries()
    try:
        register_search_entity_adapter(
            SearchEntityAdapter(
                owner_app=DOCS_APP,
                entity_type="plugin_record",
                resource_type=NATIVE_DOC_RESOURCE_TYPE,
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
                company_loader=lambda db,: [],
                document_loader=lambda db, *, entity_type, entity_id: None,
                date_fields=("reviewed_at",),
                person_roles=("reviewer",),
                sort_fields=("reviewed_at",),
            )
        )

        assert "reviewed_at" in search_date_filter_fields()
        assert "reviewer" in search_people_roles()
        assert "reviewed_at" in search_sort_fields()
    finally:
        _reset_platform_registries()


def test_search_projection_registry_accepts_extension_entity_types() -> None:
    reset_search_projection_adapters()
    try:
        adapter = FunctionSearchProjectionAdapter(
            entity_types=("plugin_record",),
            company_loader=lambda db,: [],
            document_loader=lambda db, *, entity_type, entity_id: {
                "entity_type": entity_type,
                "entity_id": entity_id,
            },
        )

        register_search_projection_adapter(adapter)

        assert get_search_projection_adapter("plugin_record") is adapter
        assert get_search_projection_adapter(SearchEntityType.DOC) is None
    finally:
        reset_search_projection_adapters()


def test_search_entity_descriptors_accept_extension_entities() -> None:
    reset_search_entity_descriptors()
    try:
        register_search_entity_descriptor(
            SearchEntityDescriptor(
                entity_type="plugin_record",
                resource_type="plugin_resource",
                label="Plugin Record",
                label_key="ai.search.entityPluginRecord",
            )
        )
        ensure_search_entity_descriptors_registered()

        assert resource_type_for_search_entity("plugin_record") == "plugin_resource"
        assert label_for_search_entity("plugin_record") == "Plugin Record"
    finally:
        reset_search_entity_descriptors()


def test_default_search_index_hooks_reregister_after_reset() -> None:
    reset_search_index_hooks()

    ensure_search_index_hooks_registered()
    ensure_search_index_hooks_registered()

    assert has_search_index_hook("docs.enqueue_doc_search_index")
    registration = get_search_index_hook_registration("pms.enqueue_task_search_index")
    assert registration is not None
    assert registration.owner_app is PMS_APP
    assert registration.entity_type == SearchEntityType.PMS_TASK.value
    assert registration.operations == frozenset({"create", "update", "delete"})


def test_search_hook_facade_delegates_pms_task_enqueues_to_registry() -> None:
    reset_search_index_hooks()
    calls: list[tuple[str, object, str, str | tuple[str, ...], str | None]] = []

    def enqueue_task(db: object, *, task: SimpleNamespace, operation: str = "upsert") -> None:
        calls.append(("task", db, task.id, operation, None))

    def enqueue_task_by_id(db: object, *, task_id: str, operation: str = "upsert") -> None:
        calls.append(("task_by_id", db, task_id, operation, None))

    def recompute_label_tasks(
        db: object,
        *,
        label: SimpleNamespace,
        task_ids: list[str] | None = None,
        operation: str = "upsert",
    ) -> None:
        calls.append(("label", db, label.id, tuple(task_ids or ()), operation))

    try:
        register_search_index_hook(
            "pms.enqueue_task_search_index",
            enqueue_task,
            owner_app=PMS_APP,
            entity_type=SearchEntityType.PMS_TASK.value,
            operations=("create", "update", "delete"),
        )
        register_search_index_hook(
            "pms.enqueue_task_search_index_by_id",
            enqueue_task_by_id,
            owner_app=PMS_APP,
            entity_type=SearchEntityType.PMS_TASK.value,
            operations=("update",),
        )
        register_search_index_hook(
            "pms.enqueue_label_task_search_recompute",
            recompute_label_tasks,
            owner_app=PMS_APP,
            entity_type=SearchEntityType.PMS_TASK.value,
            operations=("update",),
        )

        db = object()
        search_hooks.enqueue_task_search_index(
            db, task=SimpleNamespace(id="task-1"), operation="delete"
        )
        search_hooks.enqueue_task_search_index_by_id(db, task_id="task-2", operation="upsert")
        search_hooks.enqueue_label_task_search_recompute(
            db,
            label=SimpleNamespace(id="label-1", list_id="list-1"),
            task_ids=["task-3", "task-4"],
            operation="upsert",
        )

        assert calls == [
            ("task", db, "task-1", "delete", None),
            ("task_by_id", db, "task-2", "upsert", None),
            ("label", db, "label-1", ("task-3", "task-4"), "upsert"),
        ]
    finally:
        reset_search_index_hooks()


def test_default_conversation_scope_adapters_reregister_after_reset() -> None:
    reset_conversation_scope_adapters()

    ensure_conversation_scope_adapters_registered()
    ensure_conversation_scope_adapters_registered()

    assert get_conversation_scope_adapter("files") is not None
    assert get_conversation_scope_adapter("meeting") is not None


def test_default_target_access_adapters_reregister_after_reset() -> None:
    reset_target_access_adapters()

    ensure_builtin_target_access_adapters_registered()
    ensure_builtin_target_access_adapters_registered()

    assert get_target_access_adapter("pms") is not None
    assert get_target_access_adapter("docs") is None
    assert get_target_access_adapter("pms") is not None


def test_target_access_import_does_not_register_default_adapters() -> None:
    reset_target_access_adapters()

    source_access_targets = importlib.import_module(
        "open_work_hub_api.domains.source_access.targets"
    )
    importlib.reload(source_access_targets)

    assert has_target_access_adapter("docs") is False
    assert has_target_access_adapter("pms") is False


def test_target_access_lookup_lazy_registers_default_adapters() -> None:
    reset_target_access_adapters()

    assert (
        target_access_allowed(
            db=SimpleNamespace(),
            user=SimpleNamespace(id="user-1"),
            ref=TargetRef(app="unknown", type="resource", id="resource-1"),
        )
        is False
    )
    assert has_target_access_adapter("pms")
    assert not has_target_access_adapter("docs")
    assert has_target_access_adapter("pms")


def test_default_external_llm_providers_reregister_after_reset() -> None:
    reset_external_llm_providers()

    ensure_default_external_llm_providers_registered()
    ensure_default_external_llm_providers_registered()

    assert external_llm_provider_ids(official_only=True) == (
        "anthropic",
        "gemini",
        "openai",
    )


def test_default_llm_pool_config_resolvers_reregister_after_reset() -> None:
    reset_llm_pool_config_resolvers()

    ensure_default_llm_pool_config_resolvers_registered()
    ensure_default_llm_pool_config_resolvers_registered()

    assert llm_pool_config_resolver_keys() == (
        "external:anthropic",
        "external:gemini",
        "external:openai",
        "local:*",
    )


def test_external_provider_descriptor_projects_default_pool_config() -> None:
    reset_external_llm_providers()
    reset_llm_pool_config_resolvers()
    try:
        register_external_llm_provider(
            ExternalLlmProviderDescriptor(
                "plugin",
                default_endpoint_url="https://plugin.example/v1",
                official=False,
                openai_compatible=True,
            )
        )
        settings = _test_settings(
            OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS="plugin",
        )

        config = llm_core.get_pool_config(
            "external",
            settings,
            external_provider="plugin",
        )

        assert config.provider == "plugin"
        assert config.base_url == "https://plugin.example/v1"
        assert config.api_key == ""
        assert config.default_model == ""
        assert config.canonical_model == ""
    finally:
        reset_external_llm_providers()
        reset_llm_pool_config_resolvers()


def test_configured_custom_llm_provider_requires_runtime_adapter() -> None:
    _reset_platform_registries()
    try:
        register_external_llm_provider(ExternalLlmProviderDescriptor("plugin", official=False))
        settings = _test_settings(
            OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS="plugin",
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match="configured external LLM providers without execution adapters: plugin",
        ):
            initialize_platform_extensions(settings=settings)
    finally:
        _reset_platform_registries()


def test_custom_llm_provider_settings_can_be_created_before_provider_registration() -> None:
    _reset_platform_registries()
    try:
        settings = _test_settings(
            OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS="plugin",
        )
        register_external_llm_provider(
            ExternalLlmProviderDescriptor(
                "plugin",
                official=False,
                openai_compatible=True,
            )
        )
        register_llm_pool_config_resolver(
            pool="external",
            provider="plugin",
            resolver=lambda settings: LlmPoolConfigValues(
                provider="plugin",
                base_url="https://plugin.example/v1",
                api_key="plugin-key",
                default_model="plugin-default",
                canonical_model="plugin-canonical",
                long_generation_timeout_seconds=(
                    settings.llm_external_long_generation_timeout_seconds
                ),
                enabled=True,
            ),
        )

        snapshot = initialize_platform_extensions(settings=settings)

        assert "external:plugin" in snapshot.llm_pool_config_resolver_keys
    finally:
        _reset_platform_registries()


def test_platform_validation_rejects_unknown_external_llm_provider_setting() -> None:
    _reset_platform_registries()
    try:
        settings = _test_settings(
            OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS="typo-provider",
        )

        with pytest.raises(PlatformExtensionBootstrapError) as excinfo:
            initialize_platform_extensions(settings=settings)

        message = str(excinfo.value)
        assert (
            "OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS contains unsupported external "
            "provider(s): typo-provider"
        ) in message
    finally:
        _reset_platform_registries()


def test_platform_validation_rejects_ai_external_llm_default_outside_allowlist() -> None:
    _reset_platform_registries()
    try:
        settings = _test_settings(
            OPEN_WORK_HUB_AI_EXTERNAL_LLM_ENABLED=True,
            OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS="anthropic",
            OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER="openai",
            OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER="anthropic",
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match=(
                "OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER must be listed in "
                "OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS: openai"
            ),
        ):
            initialize_platform_extensions(settings=settings)
    finally:
        _reset_platform_registries()


def test_platform_validation_rejects_unknown_ai_external_llm_default() -> None:
    _reset_platform_registries()
    try:
        settings = _test_settings(
            OPEN_WORK_HUB_AI_EXTERNAL_LLM_ENABLED=True,
            OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER="typo-provider",
        )

        with pytest.raises(
            PlatformExtensionBootstrapError,
            match=(
                "OPEN_WORK_HUB_AI_DEFAULT_EXTERNAL_LLM_PROVIDER contains unsupported "
                "external provider: typo-provider"
            ),
        ):
            initialize_platform_extensions(settings=settings)
    finally:
        _reset_platform_registries()


def test_configured_custom_llm_provider_requires_explicit_runtime_contract() -> None:
    _reset_platform_registries()
    try:
        register_external_llm_provider(ExternalLlmProviderDescriptor("plugin", official=False))
        register_llm_pool_config_resolver(
            pool="external",
            provider="plugin",
            resolver=lambda settings: LlmPoolConfigValues(
                provider="plugin",
                base_url="https://plugin.example/v1",
                api_key="plugin-key",
                default_model="plugin-default",
                canonical_model="plugin-canonical",
                long_generation_timeout_seconds=(
                    settings.llm_external_long_generation_timeout_seconds
                ),
                enabled=True,
            ),
        )
        settings = _test_settings(
            OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS="plugin",
        )

        with pytest.raises(PlatformExtensionBootstrapError) as exc_info:
            initialize_platform_extensions(settings=settings)

        message = str(exc_info.value)
        assert "configured external LLM providers without execution adapters: plugin" in message
        assert "configured external LLM providers without generation profiles: plugin" in message
    finally:
        _reset_platform_registries()


def test_openai_compatible_custom_llm_provider_can_use_default_runtime_contract() -> None:
    _reset_platform_registries()
    try:
        register_external_llm_provider(
            ExternalLlmProviderDescriptor(
                "plugin",
                official=False,
                openai_compatible=True,
            )
        )
        register_llm_pool_config_resolver(
            pool="external",
            provider="plugin",
            resolver=lambda settings: LlmPoolConfigValues(
                provider="plugin",
                base_url="https://plugin.example/v1",
                api_key="plugin-key",
                default_model="plugin-default",
                canonical_model="plugin-canonical",
                long_generation_timeout_seconds=(
                    settings.llm_external_long_generation_timeout_seconds
                ),
                enabled=True,
            ),
        )
        settings = _test_settings(
            OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS="plugin",
        )

        snapshot = initialize_platform_extensions(settings=settings)

        assert "external:*" in snapshot.llm_execution_adapter_keys
        assert "external:*" in snapshot.llm_generation_profile_keys
        assert "plugin" not in snapshot.llm_external_provider_ids
    finally:
        _reset_platform_registries()


def test_custom_llm_provider_runtime_fallback_requires_openai_compatibility() -> None:
    _reset_platform_registries()
    try:
        register_external_llm_provider(ExternalLlmProviderDescriptor("plugin", official=False))

        with pytest.raises(ValueError, match="no LLM execution adapter"):
            supports_tool_calling("external", "plugin")
        with pytest.raises(ValueError, match="no LLM generation profile"):
            resolve_reasoning_effort(
                "external",
                "plugin",
                reasoning_effort=None,
            )
    finally:
        _reset_platform_registries()

    _reset_platform_registries()
    try:
        register_external_llm_provider(
            ExternalLlmProviderDescriptor(
                "plugin",
                official=False,
                openai_compatible=True,
            )
        )

        assert supports_tool_calling("external", "plugin") is True
        assert (
            resolve_reasoning_effort(
                "external",
                "plugin",
                reasoning_effort=None,
            )
            == "medium"
        )
    finally:
        _reset_platform_registries()


def test_default_llm_execution_adapters_reregister_after_reset() -> None:
    reset_llm_execution_adapters()

    ensure_default_llm_execution_adapters_registered()
    ensure_default_llm_execution_adapters_registered()

    assert llm_execution_adapter_keys() == (
        "external:*",
        "external:anthropic",
        "external:gemini",
        "external:openai",
        "local:*",
    )
    assert supports_tool_calling("external", "openai") is True
    assert supports_tool_calling("external", "anthropic") is False
    assert supports_tool_calling("local", "vllm") is True


def test_default_llm_generation_profiles_reregister_after_reset() -> None:
    reset_llm_generation_profiles()

    ensure_default_llm_generation_profiles_registered()
    ensure_default_llm_generation_profiles_registered()

    assert llm_generation_profile_keys() == (
        "external:*",
        "external:anthropic",
        "external:gemini",
        "external:openai",
        "local:*",
        "local:docker-model-runner",
        "local:vllm",
        "local:vllm-openai",
    )
    assert resolve_reasoning_effort("external", "openai", reasoning_effort=None) == "medium"
    assert resolve_reasoning_effort("local", "docker-model-runner", reasoning_effort=None) == "none"
    assert resolve_reasoning_effort("local", "vllm", reasoning_effort=None) == "none"
    assert resolve_reasoning_effort("local", "vllm", reasoning_effort="high") == "high"

    docker_profile = select_llm_generation_profile("local", "docker-model-runner")
    assert docker_profile.extra_body("none") == {"chat_template_kwargs": {"enable_thinking": False}}


def test_web_search_workloads_register_as_external_only() -> None:
    _reset_platform_registries()
    try:
        initialize_platform_extensions(settings=_test_settings())
        registry = get_ai_capability_registry()

        for workload_id in ("web_search.answer",):
            workload = registry.resolve_llm_workload(workload_id)
            assert workload.default_route == "external"
            assert workload.allowed_routes == ("external",)
            assert workload.allowed_providers == ("anthropic",)

    finally:
        _reset_platform_registries()


def test_llm_generation_profiles_project_provider_payload_options() -> None:
    reset_llm_generation_profiles()
    try:
        local_execution = SimpleNamespace(
            config=SimpleNamespace(pool="local", provider="vllm"),
            chosen_model="local-model",
            resolved_max_tokens=9000,
            resolved_reasoning_effort="none",
        )
        local_large_output_execution = SimpleNamespace(
            config=SimpleNamespace(pool="local", provider="vllm"),
            chosen_model="local-model",
            resolved_max_tokens=24_576,
            resolved_reasoning_effort="none",
        )
        local_oversized_output_execution = SimpleNamespace(
            config=SimpleNamespace(pool="local", provider="vllm"),
            chosen_model="local-model",
            resolved_max_tokens=150_000,
            resolved_reasoning_effort="none",
        )
        external_execution = SimpleNamespace(
            config=SimpleNamespace(pool="external", provider="openai"),
            chosen_model="gpt-test",
            resolved_max_tokens=8192,
            resolved_reasoning_effort="medium",
        )

        local_payload = build_chat_payload(
            local_execution,
            messages=[{"role": "user", "content": "hi"}],
            temperature=None,
            extra_body=None,
        )
        local_large_output_payload = build_chat_payload(
            local_large_output_execution,
            messages=[{"role": "user", "content": "hi"}],
            temperature=None,
            extra_body=None,
        )
        local_oversized_output_payload = build_chat_payload(
            local_oversized_output_execution,
            messages=[{"role": "user", "content": "hi"}],
            temperature=None,
            extra_body=None,
        )
        external_payload = build_chat_payload(
            external_execution,
            messages=[{"role": "user", "content": "hi"}],
            temperature=None,
            extra_body=None,
        )

        assert local_payload["extra_body"] == {"chat_template_kwargs": {"enable_thinking": False}}
        assert local_large_output_payload["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": False}
        }
        assert local_oversized_output_payload["extra_body"] == {
            "chat_template_kwargs": {"enable_thinking": False}
        }
        assert external_payload["extra_body"] == {"reasoning_effort": "medium"}

        external_passthrough_payload = build_chat_payload(
            external_execution,
            messages=[{"role": "user", "content": "hi"}],
            temperature=None,
            extra_body={"truncate_prompt_tokens": 90000},
        )
        assert external_passthrough_payload["extra_body"] == {
            "reasoning_effort": "medium",
            "truncate_prompt_tokens": 90000,
        }
    finally:
        reset_llm_generation_profiles()


def test_llm_generation_profile_registry_accepts_extension_override() -> None:
    reset_llm_generation_profiles()
    try:
        register_llm_generation_profile(
            LlmGenerationProfile(
                profile_id="extension_local",
                pool="local",
                provider=None,
                default_reasoning_effort="low",
                extra_body_builder=lambda reasoning_effort: {
                    "extension_reasoning": reasoning_effort,
                },
            )
        )

        ensure_default_llm_generation_profiles_registered()

        assert (
            resolve_reasoning_effort(
                "local",
                "custom",
                reasoning_effort=None,
            )
            == "low"
        )
        payload = build_chat_payload(
            SimpleNamespace(
                config=SimpleNamespace(pool="local", provider="custom"),
                chosen_model="custom-model",
                resolved_max_tokens=123,
                resolved_reasoning_effort="low",
            ),
            messages=[{"role": "user", "content": "hi"}],
            temperature=None,
            extra_body=None,
        )
        assert payload["extra_body"] == {"extension_reasoning": "low"}
    finally:
        reset_llm_generation_profiles()


def test_default_target_access_adapters_allow_partial_app_override() -> None:
    class ExtensionDocsTargetAdapter:
        def label_for(self, *, db, ref) -> str | None:
            del db
            return "Extension Docs" if ref.type == "group_collection" else None

        def can_access(self, *, db, user, ref) -> bool:
            del (
                db,
                user,
            )
            return ref.type == "group_collection"

        def project_access(self, *, db, user, ref) -> TargetAccessProjection:
            del (
                db,
                user,
            )
            if ref.type != "group_collection":
                return TargetAccessProjection(False, False, False)
            return TargetAccessProjection(True, True, False)

    reset_target_access_adapters()
    try:
        adapter = ExtensionDocsTargetAdapter()
        register_target_access_adapter("docs", adapter)

        ensure_builtin_target_access_adapters_registered()

        assert get_target_access_adapter("docs") is adapter
        assert get_target_access_adapter("pms") is not None
    finally:
        reset_target_access_adapters()


def test_default_rag_source_adapters_reregister_after_reset() -> None:
    reset_rag_source_adapters()

    ensure_rag_source_adapters_registered()
    ensure_rag_source_adapters_registered()

    assert resolve_rag_resource_types_for_source_kinds(["manual"]) == ("docs_native_doc",)
    assert resolve_rag_resource_types_for_source_kinds(["unknown"]) == ()
    assert resolve_rag_resource_types_for_source_kinds(["unknown", "manual"]) == (
        "docs_native_doc",
    )
    assert "pms_task" not in resolve_rag_resource_types_for_source_kinds([])
    assert resolve_rag_resource_types_for_source_kinds(["pms_task"]) == ("pms_task",)
    native_doc_resource_adapter = get_rag_resource_adapter("docs_native_doc")
    assert native_doc_resource_adapter is not None
    assert native_doc_resource_adapter.app_id == DOCS_APP.app_id
    manual_source_adapter = get_rag_source_adapter("manual")
    assert manual_source_adapter is not None
    assert manual_source_adapter.app_id == DOCS_APP.app_id
    assert get_rag_resource_adapter("knowledge_source_document") is None


def test_rag_resource_registry_accepts_extension_projection_adapter() -> None:
    reset_rag_source_adapters()
    try:
        adapter = RagResourceAdapter(
            resource_type="plugin_resource",
            app_id="plugin",
            load_projection=lambda db, resource_id, rag_service: {
                "resource_id": resource_id,
            },
        )

        register_rag_resource_adapter(adapter)

        assert get_rag_resource_adapter("plugin_resource") is adapter
        assert get_rag_resource_adapter("missing") is None
    finally:
        reset_rag_source_adapters()


def test_default_rag_source_adapters_allow_partial_source_kind_override() -> None:
    reset_rag_source_adapters()
    try:
        adapter = RagSourceAdapter(
            source_kind="manual",
            resource_type="plugin_resource",
            app_id="plugin",
            label="Plugin Manual",
        )
        register_rag_source_adapter(adapter)

        ensure_rag_source_adapters_registered()

        assert get_rag_source_adapter("manual") is adapter
        assert get_rag_resource_adapter(NATIVE_DOC_RESOURCE_TYPE) is not None
    finally:
        reset_rag_source_adapters()


def test_default_source_access_adapters_reregister_after_reset() -> None:
    reset_source_access_adapters()
    policy = SourceAclPolicy(
        db=SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
    )

    assert policy.can_read_resource("unknown", "resource-1") is False
    assert has_source_access_adapter(NATIVE_DOC_RESOURCE_TYPE)


def test_source_access_policy_import_does_not_register_default_adapters() -> None:
    reset_source_access_adapters()

    source_access_policy = importlib.import_module("open_work_hub_api.domains.source_access.policy")
    importlib.reload(source_access_policy)

    assert has_source_access_adapter(NATIVE_DOC_RESOURCE_TYPE) is False

    policy = source_access_policy.SourceAclPolicy(
        db=SimpleNamespace(),
        user=SimpleNamespace(id="user-1"),
    )

    assert policy.can_read_resource("unknown", "resource-1") is False
    assert has_source_access_adapter(NATIVE_DOC_RESOURCE_TYPE)


def test_default_source_access_adapters_allow_partial_resource_override(monkeypatch) -> None:
    from open_work_hub_api.domains.source_access import policy as source_policy

    monkeypatch.setattr(source_policy, "can_use_app", lambda *args, **kwargs: True)

    class ExtensionNativeDocAccessAdapter:
        app_id = "docs"
        resource_types = (NATIVE_DOC_RESOURCE_TYPE,)
        keyword_acl_entity_types: tuple[str, ...] = ()

        def can_read_resource(self, policy, *, resource_type: str, resource_id: str) -> bool:
            del policy, resource_type
            return resource_id == "extension-doc"

        def can_read_rag_resource(self, policy, *, resource_type: str, resource_id: str) -> bool:
            del policy, resource_type, resource_id
            return False

        def has_accessible_source(self, policy, *, resource_type: str) -> bool:
            del policy, resource_type
            return True

        def keyword_acl_branches(self, policy):
            del policy
            return []

    reset_source_access_adapters()
    try:
        adapter = ExtensionNativeDocAccessAdapter()
        register_source_access_adapter(adapter)
        policy = SourceAclPolicy(
            db=SimpleNamespace(),
            user=SimpleNamespace(id="user-1"),
        )

        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, "extension-doc") is True
        monkeypatch.setattr(source_policy, "can_use_app", lambda *args, **kwargs: False)
        assert policy.can_read_resource(NATIVE_DOC_RESOURCE_TYPE, "extension-doc") is False
        assert get_source_access_adapter(NATIVE_DOC_RESOURCE_TYPE) is adapter
        assert has_source_access_adapter("knowledge_source_document") is not (
            KNOWLEDGE_SOURCE_REGISTRY_RETIRED
        )
    finally:
        reset_source_access_adapters()
