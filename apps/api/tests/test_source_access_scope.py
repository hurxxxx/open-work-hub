from __future__ import annotations

import pytest
from sqlalchemy import Column, MetaData, String, Table, create_engine, select

from open_work_hub_api.domains.source_access.access_scope import AccessScopeRules


_SCOPE_CASES = [
    ("company", None, True),
    ("company", "invented-container", False),
    ("group", "group-1", True),
    ("group", "group-2", False),
    ("group", None, False),
    ("team", "space-1", True),
    ("team", "space-2", False),
    ("team", None, False),
    ("user", "user-1", True),
    ("user", "user-2", False),
    ("user", None, False),
    ("workspace", None, False),
    ("workspace", "retired", False),
    (None, "user-1", False),
    ("unknown", "group-1", False),
]


@pytest.mark.parametrize("platform_admin", [False, True])
@pytest.mark.parametrize("active", [False, True])
@pytest.mark.parametrize("scope_kind,scope_id,granted", _SCOPE_CASES)
def test_source_scope_preserves_group_space_and_personal_boundaries(
    platform_admin: bool, active: bool, scope_kind: str | None, scope_id: str | None, granted: bool
) -> None:
    rules = AccessScopeRules(
        user_id="user-1",
        active=active,
        platform_admin=platform_admin,
        team_ids=("space-1",),
        group_ids=("group-1",),
    )
    assert rules.can_access(scope_kind, scope_id) is (active and granted)


@pytest.mark.parametrize("platform_admin", [False, True])
@pytest.mark.parametrize("active", [False, True])
def test_sql_scope_projection_matches_the_same_fail_closed_matrix(
    platform_admin: bool, active: bool
) -> None:
    rules = AccessScopeRules(
        user_id="user-1",
        active=active,
        platform_admin=platform_admin,
        team_ids=("space-1",),
        group_ids=("group-1",),
    )
    metadata = MetaData()
    scope_rows = Table(
        "scope_rows",
        metadata,
        Column("label", String, primary_key=True),
        Column("scope_kind", String, nullable=True),
        Column("scope_id", String, nullable=True),
    )
    engine = create_engine("sqlite://")
    try:
        metadata.create_all(engine)
        with engine.begin() as connection:
            connection.execute(
                scope_rows.insert(),
                [
                    {"label": str(index), "scope_kind": kind, "scope_id": identity}
                    for index, (kind, identity, _allowed) in enumerate(_SCOPE_CASES)
                ],
            )
            actual = set(
                connection.scalars(
                    select(scope_rows.c.label).where(
                        rules.predicate(scope_rows.c.scope_kind, scope_rows.c.scope_id)
                    )
                )
            )
        expected = {
            str(index)
            for index, (_kind, _identity, allowed) in enumerate(_SCOPE_CASES)
            if active and allowed
        }
        assert actual == expected
    finally:
        engine.dispose()


def test_live_scope_policy_rejects_temporary_password_until_change_is_complete() -> None:
    from sqlalchemy.orm import Session
    from company_admission_fixture import company_authority_tables, seed_company_app_access
    from open_work_hub_api.core.db import Base
    from open_work_hub_api.domains.auth.models import User
    from open_work_hub_api.domains.pms.space_models import Team, TeamMember, SpaceGroupBinding
    from open_work_hub_api.domains.source_access.access_scope import AccessScopePolicy

    engine = create_engine("sqlite://")
    try:
        Base.metadata.create_all(
            engine,
            tables=[
                *company_authority_tables(),
                Team.__table__,
                TeamMember.__table__,
                SpaceGroupBinding.__table__,
            ],
        )
        with Session(engine) as db:
            seed_company_app_access(db)
            user = User(
                id="user-1",
                login_id="scope-user",
                email="scope@example.test",
                full_name="Scope User",
                password_hash="test",
                must_change_password=True,
            )
            db.add(user)
            db.commit()
            policy = AccessScopePolicy(db=db, user_id=user.id)
            assert policy.can_access("company", None) is False
            assert policy.can_access("user", user.id) is False
            user.must_change_password = False
            db.commit()
            assert policy.can_access("company", None) is True
            assert policy.can_access("user", user.id) is True
            user.login_blocked = True
            db.commit()
            assert policy.can_access("company", None) is False
            assert policy.can_access("user", user.id) is False
    finally:
        engine.dispose()
