from __future__ import annotations

from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai.registry import get_ai_capability_registry, reset_ai_capability_registry


def test_mcp_bridge_disabled_by_default(monkeypatch) -> None:
    for env_name in (
        "AIDOO_AI_MCP_BRIDGE_ENABLED",
        "DOOWON_AIDOO_AI_MCP_BRIDGE_ENABLED",
        "DOOWON_API_AIDOO_AI_MCP_BRIDGE_ENABLED",
    ):
        monkeypatch.delenv(env_name, raising=False)

    cache_clear = getattr(get_settings, "cache_clear", None)
    if cache_clear is not None:
        cache_clear()
    try:
        assert get_settings().ai_mcp_bridge_enabled is False
    finally:
        if cache_clear is not None:
            cache_clear()


def test_openai_tool_specs_export_registered_read_tools() -> None:
    reset_ai_capability_registry()
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
    reset_ai_capability_registry()
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
    reset_ai_capability_registry()
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


def test_phase35_pms_create_issue_anchor_is_preview_only() -> None:
    reset_ai_capability_registry()
    registry = get_ai_capability_registry()

    assert registry.resolve_preview_builder("pms.issue_create_preview") is not None
    assert "pms.create_issue" not in registry.tools
    assert "pms.create_issue" not in registry.compiled_schemas()
