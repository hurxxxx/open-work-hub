from __future__ import annotations

import pytest
from pydantic import BaseModel, ConfigDict

from open_alm_api.core.principal import personal_user_principal
from open_alm_api.domains.ai.registry import (
    AiCapabilityRegistry,
    WorkspaceContext,
    WorkspaceEntitlementView,
    get_ai_capability_registry,
    reset_ai_capability_registry,
)
from open_alm_api.domains.legacy_issues import (
    register_ai_capabilities as register_legacy_issue_ai_capabilities,
)
from open_alm_api.domains.legacy_issues.task_kinds import (
    LEGACY_ISSUE_ANALYSIS_PLAN_TASK_KIND,
    LEGACY_ISSUE_ANALYSIS_PLAN_WORKLOAD_ID,
    LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_TASK_KIND,
    LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_WORKLOAD_ID,
    LEGACY_ISSUE_INTENT_ROUTER_TASK_KIND,
    LEGACY_ISSUE_INTENT_ROUTER_WORKLOAD_ID,
)


def test_all_registered_capabilities_compile_successfully() -> None:
    reset_ai_capability_registry()
    registry = get_ai_capability_registry()

    compiled = registry.compile_capabilities()

    assert compiled
    assert set(compiled.keys()) == set(registry.tools.keys())


def test_legacy_issue_analysis_workloads_register_independently() -> None:
    registry = AiCapabilityRegistry()
    register_legacy_issue_ai_capabilities(registry)

    expected = {
        LEGACY_ISSUE_ANALYSIS_PLAN_WORKLOAD_ID: LEGACY_ISSUE_ANALYSIS_PLAN_TASK_KIND,
        LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_WORKLOAD_ID: (
            LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_TASK_KIND
        ),
        LEGACY_ISSUE_INTENT_ROUTER_WORKLOAD_ID: LEGACY_ISSUE_INTENT_ROUTER_TASK_KIND,
    }
    assert {"legacy_issues.conversation_answer", "legacy_issues.attachment_vision"}.issubset(
        registry.llm_workloads
    )
    for workload_id, task_kind in expected.items():
        workload = registry.resolve_llm_workload(workload_id)

        assert workload.task_kind == task_kind
        assert workload.owner_domain == "legacy-issues"
        assert workload.app_ids == ("legacy-issues",)
        assert workload.default_route == "local"
        assert workload.execution_kind == "chat"
        assert workload.allowed_routes == ("local", "external")
        assert workload.required_capabilities == ("chat",)
        assert workload.external_data is True
        expected_max_tokens = (
            1_024 if workload_id == LEGACY_ISSUE_INTENT_ROUTER_WORKLOAD_ID else 8_192
        )
        assert workload.local_max_output_tokens == expected_max_tokens
        assert workload.external_max_output_tokens == expected_max_tokens


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
        workspace_app_id="chatbot",
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
        workspace_app_id="chatbot",
    )

    with pytest.raises(ValueError, match="Duplicate AI tool registration"):
        registry.register_tool(
            name="custom.read_item",
            description="Read item again",
            owner_domain="custom",
            args_model=Args,
            handler=lambda db, workspace, principal, user, arguments: {"ok": True},
            discoverability_predicate_id="custom.enabled",
            workspace_app_id="chatbot",
        )


def test_registry_accepts_plugin_workspace_app_without_core_catalog_entry() -> None:
    registry = AiCapabilityRegistry()

    registry.register_tool(
        name="plugin.read_item",
        description="Read plugin item",
        owner_domain="plugin",
        workspace_app_id="plugin.app",
        handler=lambda db, workspace, principal, user, arguments: {"ok": True},
    )

    descriptor = registry.descriptors["plugin.read_item"]
    predicate = registry.resolve_discoverability_predicate(descriptor.discoverability_predicate_id)

    assert descriptor.workspace_app_id == "plugin.app"
    assert descriptor.discoverability_predicate_id == "plugin.app.enabled"
    assert predicate is not None
    assert predicate(
        None,
        WorkspaceContext(workspace_id="ws-1", workspace_slug="ws", display_name="Workspace"),
        WorkspaceEntitlementView(enabled_app_ids=frozenset({"plugin.app"})),
    )
    assert not predicate(
        None,
        WorkspaceContext(workspace_id="ws-1", workspace_slug="ws", display_name="Workspace"),
        WorkspaceEntitlementView(enabled_app_ids=frozenset({"other.app"})),
    )


def test_platform_app_predicate_uses_platform_availability() -> None:
    reset_ai_capability_registry()
    registry = get_ai_capability_registry()
    predicate = registry.resolve_discoverability_predicate("mail.enabled")

    assert predicate is not None
    assert predicate(
        personal_user_principal(user_id="user-1", source="test"),
        WorkspaceContext(
            workspace_id="ws-1",
            workspace_slug="ws",
            display_name="Workspace",
        ),
        WorkspaceEntitlementView(
            enabled_app_ids=frozenset(),
            platform_enabled_app_ids=frozenset({"mail"}),
        ),
    )
    assert not predicate(
        personal_user_principal(user_id="user-1", source="test"),
        WorkspaceContext(
            workspace_id="ws-1",
            workspace_slug="ws",
            display_name="Workspace",
        ),
        WorkspaceEntitlementView(
            enabled_app_ids=frozenset({"mail"}),
            platform_enabled_app_ids=frozenset(),
        ),
    )


def test_personal_user_principal_has_no_workspace_scope() -> None:
    principal = personal_user_principal(
        user_id="user-1",
        source="test.personal",
        session_id="session-1",
    )

    assert principal.scope == "personal"
    assert principal.workspace_id is None
    assert principal.principal_id == "user-1"
    assert principal.as_payload()["scope"] == "personal"


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


def test_registry_rejects_write_tool_without_approval_gate() -> None:
    registry = AiCapabilityRegistry()
    registry.register_discoverability_predicate(
        predicate_id="custom.enabled",
        predicate=lambda principal, workspace, entitlements: True,
    )

    with pytest.raises(ValueError, match="must set approval_required=True"):
        registry.register_tool(
            name="custom.write_without_approval",
            description="Unsafe write item",
            owner_domain="custom",
            mode="write",
            handler=lambda db, workspace, principal, user, arguments: {"ok": True},
            discoverability_predicate_id="custom.enabled",
            workspace_app_id="chatbot",
        )


def test_registry_rejects_approval_tool_with_unknown_preview_builder() -> None:
    registry = AiCapabilityRegistry()
    registry.register_discoverability_predicate(
        predicate_id="custom.enabled",
        predicate=lambda principal, workspace, entitlements: True,
    )

    with pytest.raises(ValueError, match="Unknown preview builder"):
        registry.register_tool(
            name="custom.write_without_preview_builder",
            description="Unsafe write item",
            owner_domain="custom",
            mode="write",
            approval_required=True,
            handler=lambda db, workspace, principal, user, arguments: {"ok": True},
            discoverability_predicate_id="custom.enabled",
            preview_builder_id="custom.missing_preview",
            workspace_app_id="chatbot",
        )
