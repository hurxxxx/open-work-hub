from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from open_work_hub_api.core.principal import user_principal
from open_work_hub_api.domains.ai.registry import (
    AiCapabilityRegistry,
    AppEntitlementView,
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
        predicate=lambda principal, entitlements: True,
    )
    registry.register_tool(
        name="custom.union_tool",
        description="Unsupported union tool",
        owner_domain="custom",
        args_model=UnsupportedArgs,
        handler=lambda db, principal, user, arguments: {"ok": True},
        discoverability_predicate_id="custom.enabled",
        owner_app_id="chatbot",
    )

    with pytest.raises(ValueError, match="nullable unions"):
        registry.compile_capabilities()


def test_registry_rejects_duplicate_tool_registration() -> None:
    class Args(BaseModel):
        model_config = ConfigDict(extra="forbid")

    registry = AiCapabilityRegistry()
    registry.register_discoverability_predicate(
        predicate_id="custom.enabled",
        predicate=lambda principal, entitlements: True,
    )
    registry.register_tool(
        name="custom.read_item",
        description="Read item",
        owner_domain="custom",
        args_model=Args,
        handler=lambda db, principal, user, arguments: {"ok": True},
        discoverability_predicate_id="custom.enabled",
        owner_app_id="chatbot",
    )

    with pytest.raises(ValueError, match="Duplicate AI tool registration"):
        registry.register_tool(
            name="custom.read_item",
            description="Read item again",
            owner_domain="custom",
            args_model=Args,
            handler=lambda db, principal, user, arguments: {"ok": True},
            discoverability_predicate_id="custom.enabled",
            owner_app_id="chatbot",
        )


def test_registry_accepts_plugin_app_without_core_catalog_entry() -> None:
    registry = AiCapabilityRegistry()

    registry.register_tool(
        name="plugin.read_item",
        description="Read plugin item",
        owner_domain="plugin",
        owner_app_id="plugin.app",
        handler=lambda db, principal, user, arguments: {"ok": True},
    )

    descriptor = registry.descriptors["plugin.read_item"]
    predicate = registry.resolve_discoverability_predicate(descriptor.discoverability_predicate_id)

    assert descriptor.owner_app_id == "plugin.app"
    assert descriptor.discoverability_predicate_id == "plugin.app.enabled"
    assert predicate is not None
    assert predicate(
        user_principal(user_id="user-1", source="test"),
        AppEntitlementView(enabled_app_ids=frozenset({"plugin.app"})),
    )
    assert not predicate(
        user_principal(user_id="user-1", source="test"),
        AppEntitlementView(enabled_app_ids=frozenset({"other.app"})),
    )


def test_app_predicate_uses_current_entitlement() -> None:
    reset_ai_capability_registry()
    registry = get_ai_capability_registry()
    predicate = registry.resolve_discoverability_predicate("mail.enabled")

    assert predicate is not None
    assert predicate(
        user_principal(user_id="user-1", source="test"),
        AppEntitlementView(
            enabled_app_ids=frozenset({"mail"}),
        ),
    )
    assert not predicate(
        user_principal(user_id="user-1", source="test"),
        AppEntitlementView(
            enabled_app_ids=frozenset(),
        ),
    )


def test_user_principal_has_no_workspace_scope() -> None:
    principal = user_principal(
        user_id="user-1",
        source="test.personal",
        session_id="session-1",
    )

    assert principal.scope == "personal"
    assert "workspace_id" not in principal.as_payload()
    assert principal.principal_id == "user-1"
    assert principal.as_payload()["scope"] == "personal"


def test_registry_rejects_duplicate_predicate_and_preview_registration() -> None:
    registry = AiCapabilityRegistry()

    def predicate(principal, entitlements):
        return True

    def preview(principal, parsed_args):
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


def test_registry_rejects_write_tool_without_approval_gate() -> None:
    registry = AiCapabilityRegistry()
    registry.register_discoverability_predicate(
        predicate_id="custom.enabled",
        predicate=lambda principal, entitlements: True,
    )

    with pytest.raises(ValueError, match="must set approval_required=True"):
        registry.register_tool(
            name="custom.write_without_approval",
            description="Unsafe write item",
            owner_domain="custom",
            mode="write",
            handler=lambda db, principal, user, arguments: {"ok": True},
            discoverability_predicate_id="custom.enabled",
            owner_app_id="chatbot",
        )


def test_registry_rejects_approval_tool_with_unknown_preview_builder() -> None:
    registry = AiCapabilityRegistry()
    registry.register_discoverability_predicate(
        predicate_id="custom.enabled",
        predicate=lambda principal, entitlements: True,
    )

    with pytest.raises(ValueError, match="Unknown preview builder"):
        registry.register_tool(
            name="custom.write_without_preview_builder",
            description="Unsafe write item",
            owner_domain="custom",
            mode="write",
            approval_required=True,
            handler=lambda db, principal, user, arguments: {"ok": True},
            discoverability_predicate_id="custom.enabled",
            preview_builder_id="custom.missing_preview",
            owner_app_id="chatbot",
        )
