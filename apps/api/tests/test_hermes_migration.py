from alembic import command
from alembic.autogenerate import compare_metadata
from alembic.migration import MigrationContext
import pytest
import sqlalchemy as sa
from sqlalchemy.orm import Session

from open_work_hub_api.core.db import Base
from open_work_hub_api.core.model_registry import import_all_models
from open_work_hub_api.domains.auth.models import CompanyAppControl, User
from open_work_hub_api.domains.auth.app_access_models import (
    AppAccessPolicy,
    AppUserGrant,
    AppGroupGrant,
)
from open_work_hub_api.domains.groups.models import Group
from test_alembic_migrations import _migration_config


@pytest.mark.migration
@pytest.mark.parametrize(
    "chat_enabled,chat_audience,terminal_enabled,terminal_audience,expected_audience,expected_users",
    [
        (True, "selected", True, "selected", "selected", {"chat", "terminal"}),
        (False, "all", True, "selected", "selected", {"terminal"}),
        (True, "selected", False, "all", "selected", {"chat"}),
        (True, "all", True, "selected", "all", {"chat", "terminal"}),
        (False, "selected", True, "all", "all", {"terminal"}),
        (False, "selected", False, "selected", "selected", {"chat"}),
    ],
)
def test_enabled_audience_union_and_schema(
    postgres_dsn,
    chat_enabled,
    chat_audience,
    terminal_enabled,
    terminal_audience,
    expected_audience,
    expected_users,
):
    config = _migration_config(postgres_dsn)
    command.upgrade(config, "group_sources_20260912")
    engine = sa.create_engine(postgres_dsn)
    try:
        with Session(engine) as db:
            for name in ("chat", "terminal"):
                db.add(
                    User(
                        id=name,
                        login_id=name,
                        email=f"{name}@example.test",
                        full_name=name,
                        password_hash="fixture",
                    )
                )
                db.add(Group(id=name, name=name, active=True))
            db.flush()
            for app, enabled, audience, user in (
                ("chatbot", chat_enabled, chat_audience, "chat"),
                ("hermes-terminal", terminal_enabled, terminal_audience, "terminal"),
            ):
                db.add(CompanyAppControl(app_id=app, enabled=enabled))
                db.flush()
                db.add(AppAccessPolicy(app_id=app, audience=audience))
                db.add(AppUserGrant(app_id=app, user_id=user))
                db.add(AppGroupGrant(app_id=app, group_id=user))
            db.commit()
        command.upgrade(config, "head")
        with Session(engine) as db:
            assert db.get(CompanyAppControl, "chatbot").enabled is (
                chat_enabled or terminal_enabled
            )
            assert db.get(CompanyAppControl, "hermes-terminal").enabled is False
            assert db.get(AppAccessPolicy, "chatbot").audience == expected_audience
            assert (
                set(
                    db.scalars(
                        sa.select(AppUserGrant.user_id).where(AppUserGrant.app_id == "chatbot")
                    )
                )
                == expected_users
            )
            assert (
                set(
                    db.scalars(
                        sa.select(AppGroupGrant.group_id).where(AppGroupGrant.app_id == "chatbot")
                    )
                )
                == expected_users
            )
        import_all_models()
        with engine.connect() as connection:
            differences = compare_metadata(MigrationContext.configure(connection), Base.metadata)
            assert differences == []
        with pytest.raises(RuntimeError, match="Archive policy-partitioned"):
            command.downgrade(config, "group_sources_20260912")
    finally:
        engine.dispose()
