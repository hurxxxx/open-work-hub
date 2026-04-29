from __future__ import annotations

from types import SimpleNamespace

from aidoo_api.domains.ai.runtime.external_adapters import (
    select_external_planner_execution_adapter,
    select_external_search_execution_adapter,
)
from aidoo_api.domains.ai.runtime.external_planner import ExternalPlannerRequest
from aidoo_api.domains.ai.runtime.external_search import ExternalSearchRequest


def test_external_adapter_selection_defaults_to_mock() -> None:
    planner = select_external_planner_execution_adapter(
        SimpleNamespace(),
        execution_enabled=True,
    )
    search = select_external_search_execution_adapter(
        SimpleNamespace(),
        execution_enabled=True,
    )

    assert planner.adapter_id == "external_planner_v0"
    assert planner.execution_provider == "mock"
    assert search.adapter_id == "external_search_v0"
    assert search.execution_provider == "mock"


def test_external_adapter_selection_marks_unimplemented_adapter_failed() -> None:
    planner = select_external_planner_execution_adapter(
        SimpleNamespace(ai_external_planner_execution_adapter="openai"),
        execution_enabled=True,
    )
    search = select_external_search_execution_adapter(
        SimpleNamespace(ai_external_search_execution_adapter="anthropic"),
        execution_enabled=True,
    )

    planner_result = planner.execute(
        ExternalPlannerRequest(status="ready", provider="openai", messages=[])
    )
    search_result = search.execute(
        ExternalSearchRequest(
            status="ready",
            provider="anthropic",
            query="EU CE certification",
        )
    )

    assert planner.execution_provider == "openai"
    assert planner_result.status == "failed"
    assert planner_result.execution_provider == "openai"
    assert planner_result.error_class == "adapter_not_implemented"
    assert planner_result.raw_output_persisted is False

    assert search.execution_provider == "anthropic"
    assert search_result.status == "failed"
    assert search_result.execution_provider == "anthropic"
    assert search_result.error_class == "adapter_not_implemented"
    assert search_result.query_digest == "4a02ba5d13fa0cd7"
    assert search_result.cache_key == (
        "external_search_v0:anthropic:anthropic:4a02ba5d13fa0cd7"
    )
    assert search_result.result_refs == []
    assert search_result.raw_output_persisted is False


def test_external_adapter_selection_execution_flag_disables_selected_provider() -> None:
    planner = select_external_planner_execution_adapter(
        SimpleNamespace(ai_external_planner_execution_adapter="openai"),
        execution_enabled=False,
    )
    search = select_external_search_execution_adapter(
        SimpleNamespace(ai_external_search_execution_adapter="anthropic"),
        execution_enabled=False,
    )

    planner_result = planner.execute(
        ExternalPlannerRequest(status="ready", provider="openai", messages=[])
    )
    search_result = search.execute(
        ExternalSearchRequest(
            status="ready",
            provider="anthropic",
            query="EU CE certification",
        )
    )

    assert planner.execution_provider == "openai"
    assert planner_result.status == "disabled"
    assert planner_result.execution_provider == "openai"
    assert planner_result.disabled_reason == "execution_flag_disabled"
    assert planner_result.error_class is None
    assert planner_result.raw_output_persisted is False

    assert search.execution_provider == "anthropic"
    assert search_result.status == "disabled"
    assert search_result.execution_provider == "anthropic"
    assert search_result.disabled_reason == "execution_flag_disabled"
    assert search_result.error_class is None
    assert search_result.query_digest is None
    assert search_result.cache_key is None
    assert search_result.raw_output_persisted is False
