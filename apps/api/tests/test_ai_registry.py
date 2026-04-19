from __future__ import annotations

from aidoo_api.domains.ai.registry import get_ai_capability_registry, reset_ai_capability_registry


def test_openai_tool_specs_export_registered_read_tools() -> None:
    reset_ai_capability_registry()
    registry = get_ai_capability_registry()

    specs = registry.openai_tool_specs()

    assert len(specs) == 12
    assert [spec["function"]["name"] for spec in specs] == sorted(
        registry.tools.keys()
    )
    for spec in specs:
        function = spec["function"]
        assert spec["type"] == "function"
        assert isinstance(function["description"], str)
        assert function["parameters"]["type"] == "object"
