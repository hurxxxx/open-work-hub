from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from aidoo_api.domains.ai.registry import (
    AiCapabilityRegistry,
    get_ai_capability_registry,
    reset_ai_capability_registry,
)


def test_all_registered_capabilities_compile_successfully() -> None:
    reset_ai_capability_registry()
    registry = get_ai_capability_registry()

    compiled = registry.compile_capabilities()

    assert compiled
    assert set(compiled.keys()) == set(registry.tools.keys())


def test_compile_rejects_non_nullable_union_schema() -> None:
    class UnsupportedArgs(BaseModel):
        model_config = ConfigDict(extra="forbid")
        value: str | int

    registry = AiCapabilityRegistry()
    registry.register_discoverability_predicate(
        predicate_id="custom.enabled",
        predicate=lambda principal, workspace, entitlements: True,
    )
    registry.register_tool(
        name="custom.union_tool",
        description="Unsupported union tool",
        owner_domain="custom",
        args_model=UnsupportedArgs,
        handler=lambda db, workspace, principal, user, arguments: {"ok": True},
        discoverability_predicate_id="custom.enabled",
    )

    with pytest.raises(ValueError, match="nullable unions"):
        registry.compile_capabilities()


def test_registry_rejects_duplicate_tool_registration() -> None:
    class Args(BaseModel):
        model_config = ConfigDict(extra="forbid")

    registry = AiCapabilityRegistry()
    registry.register_discoverability_predicate(
        predicate_id="custom.enabled",
        predicate=lambda principal, workspace, entitlements: True,
    )
    registry.register_tool(
        name="custom.read_item",
        description="Read item",
        owner_domain="custom",
        args_model=Args,
        handler=lambda db, workspace, principal, user, arguments: {"ok": True},
        discoverability_predicate_id="custom.enabled",
    )

    with pytest.raises(ValueError, match="Duplicate AI tool registration"):
        registry.register_tool(
            name="custom.read_item",
            description="Read item again",
            owner_domain="custom",
            args_model=Args,
            handler=lambda db, workspace, principal, user, arguments: {"ok": True},
            discoverability_predicate_id="custom.enabled",
        )


def test_registry_rejects_duplicate_predicate_and_preview_registration() -> None:
    registry = AiCapabilityRegistry()

    def predicate(principal, workspace, entitlements):
        return True

    def preview(principal, workspace, parsed_args):
        return None

    registry.register_discoverability_predicate(
        predicate_id="custom.enabled",
        predicate=predicate,
    )
    registry.register_preview_builder(
        preview_builder_id="custom.preview",
        builder=preview,
    )

    with pytest.raises(ValueError, match="Duplicate discoverability predicate registration"):
        registry.register_discoverability_predicate(
            predicate_id="custom.enabled",
            predicate=predicate,
        )
    with pytest.raises(ValueError, match="Duplicate preview builder registration"):
        registry.register_preview_builder(
            preview_builder_id="custom.preview",
            builder=preview,
        )
