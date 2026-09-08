from __future__ import annotations

import pytest

from open_work_hub_api.domains.auth.roles import (
    SYSTEM_PLATFORM_ADMIN,
    _sorted_system_roles,
    normalize_system_role,
)
from open_work_hub_api.domains.pms.roles import _higher_team_role, team_role_allows


def test_unknown_current_role_returns_false() -> None:
    assert team_role_allows("unknown", "viewer") is False


def test_unknown_minimum_role_raises() -> None:
    with pytest.raises(ValueError, match="Unknown team role: superuser"):
        team_role_allows("owner", "superuser")


def test_team_role_rank_order() -> None:
    assert team_role_allows("owner", "admin")
    assert team_role_allows("admin", "member")
    assert team_role_allows("member", "viewer")
    assert not team_role_allows("viewer", "member")
    assert not team_role_allows("admin", "owner")


def test_only_canonical_platform_role_grants_authority() -> None:
    assert normalize_system_role("platform_admin") == SYSTEM_PLATFORM_ADMIN
    assert normalize_system_role("platform-admin") is None


def test_legacy_narrow_system_roles_never_grant_platform_admin() -> None:
    for role in (
        "workspace_admin",
        "workspace-admin",
        "audit_viewer",
        "audit-viewer",
    ):
        assert normalize_system_role(role) is None


def test_sorted_system_roles_are_deterministic() -> None:
    assert _sorted_system_roles({"z_custom", SYSTEM_PLATFORM_ADMIN, "a_custom"}) == [
        SYSTEM_PLATFORM_ADMIN,
        "a_custom",
        "z_custom",
    ]


def test_higher_team_role_merges_by_rank_and_ignores_unknowns() -> None:
    assert _higher_team_role("member", "owner") == "owner"
    assert _higher_team_role("admin", "member") == "admin"
    assert _higher_team_role(None, "viewer") == "viewer"
    assert _higher_team_role("unknown", "viewer") == "viewer"
    assert _higher_team_role("member", "unknown") == "member"
