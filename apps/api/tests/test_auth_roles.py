from __future__ import annotations

import pytest

from open_work_hub_api.domains.auth.roles import (
    SYSTEM_PLATFORM_ADMIN,
    _higher_team_role,
    _higher_workspace_role,
    _sorted_system_roles,
    is_valid_workspace_role,
    normalize_system_role,
    normalize_workspace_role,
    team_role_allows,
    workspace_role_allows,
)


def test_workspace_role_aliases_collapse_to_supported_roles() -> None:
    assert normalize_workspace_role("viewer") == "member"
    assert normalize_workspace_role("owner") == "admin"
    assert is_valid_workspace_role("viewer")
    assert is_valid_workspace_role("owner")


def test_unknown_current_role_returns_false() -> None:
    assert workspace_role_allows("unknown", "member") is False
    assert team_role_allows("unknown", "viewer") is False


def test_unknown_minimum_role_raises() -> None:
    with pytest.raises(ValueError, match="Unknown workspace role: superuser"):
        workspace_role_allows("admin", "superuser")

    with pytest.raises(ValueError, match="Unknown team role: superuser"):
        team_role_allows("owner", "superuser")


def test_team_role_rank_order() -> None:
    assert team_role_allows("owner", "admin")
    assert team_role_allows("admin", "member")
    assert team_role_allows("member", "viewer")
    assert not team_role_allows("viewer", "member")
    assert not team_role_allows("admin", "owner")


def test_system_role_aliases_collapse_legacy_names_to_platform_admin() -> None:
    for role in (
        "platform_admin",
        "platform-admin",
        "workspace_admin",
        "workspace-admin",
        "audit_viewer",
        "audit-viewer",
    ):
        assert normalize_system_role(role) == SYSTEM_PLATFORM_ADMIN


def test_sorted_system_roles_are_deterministic() -> None:
    assert _sorted_system_roles({"z_custom", SYSTEM_PLATFORM_ADMIN, "a_custom"}) == [
        SYSTEM_PLATFORM_ADMIN,
        "a_custom",
        "z_custom",
    ]


def test_higher_workspace_role_merges_aliases_and_unknowns() -> None:
    assert _higher_workspace_role("member", "admin") == "admin"
    assert _higher_workspace_role("owner", "member") == "admin"
    assert _higher_workspace_role(None, "viewer") == "member"
    assert _higher_workspace_role("unknown", "viewer") == "member"
    assert _higher_workspace_role("member", "unknown") == "member"


def test_higher_team_role_merges_by_rank_and_ignores_unknowns() -> None:
    assert _higher_team_role("member", "owner") == "owner"
    assert _higher_team_role("admin", "member") == "admin"
    assert _higher_team_role(None, "viewer") == "viewer"
    assert _higher_team_role("unknown", "viewer") == "viewer"
    assert _higher_team_role("member", "unknown") == "member"
