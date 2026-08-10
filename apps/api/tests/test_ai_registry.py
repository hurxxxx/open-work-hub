from __future__ import annotations

import pytest

from open_work_hub_api.core.settings import get_settings
from open_work_hub_api.domains.ai.registry import (
    AiCapabilityRegistry,
    get_ai_capability_registry,
    reset_ai_capability_registry,
)


def _reset_settings_and_registry() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    reset_ai_capability_registry()


def test_openai_tool_specs_export_registered_read_tools() -> None:
    _reset_settings_and_registry()
    registry = get_ai_capability_registry()

    specs = registry.openai_tool_specs()

    tool_names = [spec["function"]["name"] for spec in specs]
    assert tool_names == sorted(registry.tools.keys())
    assert {"pms.search_tasks", "pms.get_task", "pms.list_task_lists"} <= set(tool_names)
    for spec in specs:
        function = spec["function"]
        assert spec["type"] == "function"
        assert isinstance(function["description"], str)
        assert function["parameters"]["type"] == "object"
        assert "strict" not in function


def test_gateway_tool_adapter_requires_registered_tool() -> None:
    registry = AiCapabilityRegistry()

    with pytest.raises(ValueError, match="unregistered AI tool"):
        registry.register_gateway_tool_adapter(
            agent_id="domain.example",
            tool_name="example.search",
            build_arguments=lambda _task: {},
        )


def test_legacy_llm_task_projects_to_deterministic_workload() -> None:
    registry = AiCapabilityRegistry()

    registry.register_llm_task(
        task_kind="example_summary",
        default_policy="local_only",
        description="Example summary",
        app_ids=("example", "example-reports"),
    )

    workload = registry.resolve_llm_workload("example_summary")
    assert workload.workload_id == "example_summary"
    assert workload.task_kind == "example_summary"
    assert workload.owner_domain == "example"
    assert workload.app_ids == ("example", "example-reports")
    assert workload.default_route == "local"
    assert workload.allowed_routes == ("local", "external")
    assert workload.local_max_output_tokens == 32_768
    assert workload.external_max_output_tokens == 65_536
    assert (
        registry.resolve_llm_workload_for_task(
            app_id="example-reports",
            task_kind="example_summary",
        )
        is workload
    )


def test_llm_workload_registration_fails_closed_and_rejects_duplicate_app_task() -> None:
    registry = AiCapabilityRegistry()
    registry.register_llm_workload(
        workload_id="example.summarize",
        task_kind="example_summary",
        owner_domain="example",
        app_id="example",
        description="Example summary",
    )

    with pytest.raises(LookupError, match="Unknown LLM workload"):
        registry.resolve_llm_workload("example.unknown")

    with pytest.raises(ValueError, match="Duplicate LLM workload app/task"):
        registry.register_llm_workload(
            workload_id="example.summarize-again",
            task_kind="example_summary",
            owner_domain="example",
            app_id="example",
            description="Duplicate example summary",
        )


def test_external_only_llm_workload_contract() -> None:
    registry = AiCapabilityRegistry()
    registry.register_llm_workload(
        workload_id="images.generate",
        task_kind="image_generation",
        owner_domain="images",
        app_id="images",
        description="Generate an image",
        default_route="external",
        execution_kind="image_generation",
        allowed_routes=("external",),
        allowed_providers=("openai",),
        required_capabilities=("image_generation",),
        model_roles=("generation",),
        external_data=True,
    )

    workload = registry.resolve_llm_workload("images.generate")
    assert workload.default_policy == "external"
    assert workload.allowed_pools == ("external",)
    assert workload.model_roles == ("generation",)


@pytest.mark.parametrize(
    ("local_max_output_tokens", "external_max_output_tokens"),
    [
        (1_023, 65_536),
        (32_768, 65_537),
        (1_500, 65_536),
    ],
)
def test_llm_workload_rejects_invalid_output_token_caps(
    local_max_output_tokens: int,
    external_max_output_tokens: int,
) -> None:
    registry = AiCapabilityRegistry()

    with pytest.raises(ValueError, match="max output tokens"):
        registry.register_llm_workload(
            workload_id="example.invalid-cap",
            task_kind="example_invalid_cap",
            owner_domain="example",
            app_id="example",
            description="Invalid cap",
            local_max_output_tokens=local_max_output_tokens,
            external_max_output_tokens=external_max_output_tokens,
        )


def test_pms_write_anchors_are_hidden_when_write_tools_disabled() -> None:
    _reset_settings_and_registry()
    registry = get_ai_capability_registry()

    assert registry.resolve_preview_builder("pms.task_create_preview") is not None
    assert registry.resolve_preview_builder("pms.task_update_preview") is not None
    assert registry.resolve_preview_builder("pms.task_comment_preview") is not None
    assert registry.resolve_preview_builder("pms.task_delete_preview") is not None
    assert "pms.create_task" not in registry.tools
    assert "pms.update_task" not in registry.tools
    assert "pms.add_comment" not in registry.tools
    assert "pms.delete_task" not in registry.tools


def test_pms_write_tools_register_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        registry = get_ai_capability_registry()

        assert get_settings().ai_write_tools_enabled is True
        assert {
            "pms.create_task",
            "pms.update_task",
            "pms.add_comment",
            "pms.delete_task",
            "meeting.create_meeting",
            "planner.create_event",
            "planner.update_event",
            "planner.delete_event",
        } <= set(registry.tools)
        assert "docs.create_page" not in registry.tools

        for tool_name in (
            "pms.create_task",
            "pms.update_task",
            "pms.add_comment",
            "pms.delete_task",
            "meeting.create_meeting",
            "planner.create_event",
            "planner.update_event",
            "planner.delete_event",
        ):
            descriptor = registry.get_descriptor(tool_name)
            assert descriptor is not None
            assert descriptor.mode == "write"
            assert descriptor.approval_policy == "required"
            assert descriptor.preview_builder_id is not None
            assert registry.resolve_preview_builder(descriptor.preview_builder_id) is not None
            assert (
                registry.resolve_discoverability_predicate(descriptor.discoverability_predicate_id)
                is not None
            )
            assert descriptor.output_projection == "resource_ids"

        default_specs = {spec["function"]["name"] for spec in registry.openai_tool_specs()}
        full_specs = {
            spec["function"]["name"]
            for spec in registry.openai_tool_specs(include_approval_required=True)
        }
        assert "pms.create_task" not in default_specs
        assert {
            "pms.create_task",
            "pms.update_task",
            "pms.add_comment",
            "pms.delete_task",
            "meeting.create_meeting",
            "planner.create_event",
            "planner.update_event",
            "planner.delete_event",
        } <= full_specs
        assert "docs.create_page" not in full_specs
    finally:
        monkeypatch.delenv("OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()
