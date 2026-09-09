from __future__ import annotations

import pytest

from open_work_hub_api.domains.ai.registry import (
    AiCapabilityRegistry,
    get_ai_capability_registry,
    reset_ai_capability_registry,
)
from open_work_hub_api.domains.files import (
    FILES_APP_ID,
    FILES_GROUNDED_CHAT_TASK_KIND,
    FILES_GROUNDED_CHAT_WORKLOAD_ID,
    FILES_RAG_QUERY_REWRITE_TASK_KIND,
    FILES_RAG_QUERY_REWRITE_WORKLOAD_ID,
    register_ai_capabilities,
)


def test_files_registers_independent_llm_workload_descriptors() -> None:
    registry = AiCapabilityRegistry()

    register_ai_capabilities(registry)

    expected = {
        FILES_GROUNDED_CHAT_WORKLOAD_ID: (
            FILES_GROUNDED_CHAT_TASK_KIND,
            8_192,
        ),
        FILES_RAG_QUERY_REWRITE_WORKLOAD_ID: (
            FILES_RAG_QUERY_REWRITE_TASK_KIND,
            1_024,
        ),
    }
    assert set(registry.llm_workloads) == set(expected)
    for workload_id, (task_kind, max_output_tokens) in expected.items():
        workload = registry.resolve_llm_workload(workload_id)

        assert workload.task_kind == task_kind
        assert workload.owner_domain == FILES_APP_ID
        assert workload.app_ids == (FILES_APP_ID,)
        assert workload.default_route == "local"
        assert workload.execution_kind == "chat"
        assert workload.allowed_routes == ("local", "external")
        assert workload.allowed_providers == ()
        assert workload.required_capabilities == ("chat",)
        assert workload.model_roles == ("default",)
        assert workload.external_data is True
        assert workload.local_max_output_tokens == max_output_tokens
        assert workload.external_max_output_tokens == max_output_tokens
        assert (
            registry.resolve_llm_workload_for_task(
                app_id=FILES_APP_ID,
                task_kind=task_kind,
            )
            is workload
        )


def test_files_workloads_are_composed_into_canonical_registry() -> None:
    reset_ai_capability_registry()
    try:
        registry = get_ai_capability_registry()

        registry.compile_capabilities()

        assert (
            registry.resolve_llm_workload(FILES_GROUNDED_CHAT_WORKLOAD_ID).task_kind
            == FILES_GROUNDED_CHAT_TASK_KIND
        )
        assert (
            registry.resolve_llm_workload(FILES_RAG_QUERY_REWRITE_WORKLOAD_ID).task_kind
            == FILES_RAG_QUERY_REWRITE_TASK_KIND
        )
        with pytest.raises(LookupError, match="Unknown LLM workload"):
            registry.resolve_llm_workload("files.unknown")
    finally:
        reset_ai_capability_registry()
