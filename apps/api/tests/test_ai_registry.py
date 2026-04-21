from __future__ import annotations

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.registry import get_ai_capability_registry, reset_ai_capability_registry


def _reset_settings_and_registry() -> None:
    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    reset_ai_capability_registry()


def test_mcp_bridge_disabled_by_default(monkeypatch) -> None:
    for env_name in (
        "AIDOO_AI_MCP_BRIDGE_ENABLED",
        "DOOWON_AIDOO_AI_MCP_BRIDGE_ENABLED",
        "DOOWON_API_AIDOO_AI_MCP_BRIDGE_ENABLED",
    ):
        monkeypatch.delenv(env_name, raising=False)

    _reset_settings_and_registry()
    try:
        assert get_settings().ai_mcp_bridge_enabled is False
    finally:
        _reset_settings_and_registry()


def test_ai_write_tools_disabled_by_default(monkeypatch) -> None:
    for env_name in (
        "AIDOO_AI_WRITE_TOOLS_ENABLED",
        "DOOWON_AIDOO_AI_WRITE_TOOLS_ENABLED",
        "DOOWON_API_AIDOO_AI_WRITE_TOOLS_ENABLED",
    ):
        monkeypatch.delenv(env_name, raising=False)

    _reset_settings_and_registry()
    try:
        assert get_settings().ai_write_tools_enabled is False
    finally:
        _reset_settings_and_registry()


def test_openai_tool_specs_export_registered_read_tools() -> None:
    _reset_settings_and_registry()
    registry = get_ai_capability_registry()

    specs = registry.openai_tool_specs()

    assert len(specs) == 12
    assert [spec["function"]["name"] for spec in specs] == sorted(registry.tools.keys())
    for spec in specs:
        function = spec["function"]
        assert spec["type"] == "function"
        assert isinstance(function["description"], str)
        assert function["parameters"]["type"] == "object"
        assert "strict" not in function


def test_legacy_openai_tool_specs_preserve_registered_parameter_shapes() -> None:
    _reset_settings_and_registry()
    registry = get_ai_capability_registry()

    specs_by_name = {
        spec["function"]["name"]: spec["function"]["parameters"]
        for spec in registry.openai_tool_specs()
    }

    for name, definition in registry.tools.items():
        if definition.args_model is None:
            expected = {
                "type": "object",
                "properties": {},
                "additionalProperties": True,
            }
        else:
            expected = definition.args_model.model_json_schema()
        assert specs_by_name[name] == expected


def test_registry_compiles_mcp_and_openai_schemas_for_all_tools() -> None:
    _reset_settings_and_registry()
    registry = get_ai_capability_registry()

    compiled = registry.compiled_schemas()

    assert set(compiled.keys()) == set(registry.tools.keys())
    planner_schema = compiled["planner.list_events"]
    mcp_input = planner_schema.mcp_input_schema
    strict_input = planner_schema.openai_strict_input_schema

    assert mcp_input["type"] == "object"
    assert "from" not in mcp_input["required"]
    assert strict_input["type"] == "object"
    assert strict_input["additionalProperties"] is False
    assert {"from", "to"} <= set(strict_input["required"])
    assert strict_input["properties"]["from"]["type"] == ["string", "null"]


def test_pms_write_anchors_are_hidden_when_write_tools_disabled() -> None:
    _reset_settings_and_registry()
    registry = get_ai_capability_registry()

    assert registry.resolve_preview_builder("pms.issue_create_preview") is not None
    assert registry.resolve_preview_builder("pms.issue_update_preview") is not None
    assert registry.resolve_preview_builder("pms.issue_comment_preview") is not None
    assert "pms.create_issue" not in registry.tools
    assert "pms.update_issue" not in registry.tools
    assert "pms.add_comment" not in registry.tools


def test_pms_write_tools_register_when_enabled(monkeypatch) -> None:
    monkeypatch.setenv("AIDOO_AI_WRITE_TOOLS_ENABLED", "1")
    _reset_settings_and_registry()
    try:
        registry = get_ai_capability_registry()

        assert get_settings().ai_write_tools_enabled is True
        assert {
            "pms.create_issue",
            "pms.update_issue",
            "pms.add_comment",
            "meeting.create_meeting",
            "planner.create_event",
            "docs.create_page",
        } <= set(registry.tools)

        default_specs = {spec["function"]["name"] for spec in registry.openai_tool_specs()}
        full_specs = {
            spec["function"]["name"]
            for spec in registry.openai_tool_specs(include_approval_required=True)
        }
        assert "pms.create_issue" not in default_specs
        assert {
            "pms.create_issue",
            "pms.update_issue",
            "pms.add_comment",
            "meeting.create_meeting",
            "planner.create_event",
            "docs.create_page",
        } <= full_specs
    finally:
        monkeypatch.delenv("AIDOO_AI_WRITE_TOOLS_ENABLED", raising=False)
        _reset_settings_and_registry()
