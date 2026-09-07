from __future__ import annotations

from sqlalchemy import Column, MetaData, String, Table, create_engine, select

from open_work_hub_api.domains.source_access.access_scope import AccessScopeRules


def _member_rules() -> AccessScopeRules:
    return AccessScopeRules(
        workspace_id="workspace-1",
        workspace_role="member",
        user_id="user-1",
        team_ids=("team-1",),
    )


def test_access_scope_rules_admin_preserves_workspace_and_scope_boundaries() -> None:
    rules = AccessScopeRules(
        workspace_id="workspace-1",
        workspace_role="admin",
        user_id="user-1",
        team_ids=("team-1",),
    )

    assert rules.can_access("workspace", "other-workspace") is False
    assert rules.can_access("team", None) is False
    assert rules.can_access("team", "other-workspace-team") is False
    assert rules.can_access("unknown", "scope-1") is False
    assert rules.can_access("workspace", "workspace-1") is True
    assert rules.can_access("team", "team-1") is True
    assert rules.can_access("user", "other-user") is True
    assert rules.can_access("user", None) is False


def test_access_scope_rules_without_workspace_role_blocks_all_scopes() -> None:
    rules = AccessScopeRules(
        workspace_id="workspace-1",
        workspace_role=None,
        user_id="user-1",
        team_ids=("team-1",),
    )

    assert rules.can_access("workspace", "workspace-1") is False
    assert rules.can_access("team", "team-1") is False
    assert rules.can_access("user", "user-1") is False


def test_access_scope_rules_workspace_scope_matches_workspace_or_null_id() -> None:
    rules = _member_rules()

    assert rules.can_access("workspace", "workspace-1") is True
    assert rules.can_access("workspace", None) is True
    assert rules.can_access("workspace", "workspace-2") is False


def test_access_scope_rules_team_scope_matches_accessible_teams() -> None:
    rules = _member_rules()

    assert rules.can_access("team", "team-1") is True
    assert rules.can_access("team", "team-2") is False
    assert rules.can_access("team", None) is False


def test_access_scope_rules_user_scope_matches_current_user() -> None:
    rules = _member_rules()

    assert rules.can_access("user", "user-1") is True
    assert rules.can_access("user", "user-2") is False
    assert rules.can_access(None, "user-1") is False


def test_access_scope_rules_predicate_matches_member_accessible_rows() -> None:
    rules = _member_rules()

    assert _matching_predicate_labels(rules) == [
        "team",
        "user",
        "workspace-id",
        "workspace-null",
    ]


def test_access_scope_rules_predicate_handles_admin_and_no_workspace_role() -> None:
    admin_rules = AccessScopeRules(
        workspace_id="workspace-1",
        workspace_role="admin",
        user_id="user-1",
        team_ids=("team-1",),
    )
    blocked_rules = AccessScopeRules(
        workspace_id="workspace-1",
        workspace_role=None,
        user_id="user-1",
        team_ids=("team-1",),
    )

    assert _matching_predicate_labels(admin_rules) == [
        "team",
        "user",
        "workspace-id",
        "workspace-null",
    ]
    assert _matching_predicate_labels(blocked_rules) == []


def _matching_predicate_labels(rules: AccessScopeRules) -> list[str]:
    metadata = MetaData()
    scope_rows = Table(
        "scope_rows",
        metadata,
        Column("label", String, primary_key=True),
        Column("scope_kind", String, nullable=True),
        Column("scope_id", String, nullable=True),
    )
    engine = create_engine("sqlite:///:memory:")
    metadata.create_all(engine)
    with engine.begin() as connection:
        connection.execute(
            scope_rows.insert(),
            [
                {
                    "label": "workspace-id",
                    "scope_kind": "workspace",
                    "scope_id": "workspace-1",
                },
                {
                    "label": "workspace-null",
                    "scope_kind": "workspace",
                    "scope_id": None,
                },
                {"label": "team", "scope_kind": "team", "scope_id": "team-1"},
                {"label": "user", "scope_kind": "user", "scope_id": "user-1"},
                {"label": "unknown", "scope_kind": "unknown", "scope_id": "scope-1"},
            ],
        )
        return list(
            connection.scalars(
                select(scope_rows.c.label)
                .where(rules.predicate(scope_rows.c.scope_kind, scope_rows.c.scope_id))
                .order_by(scope_rows.c.label)
            )
        )
