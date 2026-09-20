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
def test_file_revision_migration_preserves_current_bytes_without_inventing_a_run(postgres_dsn, monkeypatch):
    from datetime import timedelta
    from open_work_hub_api.domains.auth.models import utcnow_naive
    from open_work_hub_api.domains.hermes.models import (
        HermesFileObject,
        HermesFileRevision,
        HermesSessionFile,
    )
    from test_hermes_runtime import seed, session_for
    from test_hermes_runtime import admit_runtime_apps
    from open_work_hub_api.domains.hermes import file_router

    config = _migration_config(postgres_dsn)
    command.upgrade(config, "hermes_runtime_20260912")
    engine = sa.create_engine(postgres_dsn)
    try:
        with Session(engine) as db:
            user, binding = seed(db)
            admit_runtime_apps(db, user.id)
            session = session_for(db, binding)
            expires = utcnow_naive() + timedelta(days=10)
            db.add(HermesFileObject(object_key="migration-snapshot", expires_at=expires))
            db.add(
                HermesSessionFile(
                    id="legacy-file",
                    session_id=session.id,
                    user_id=binding.user_id,
                    relative_path="legacy.txt",
                    size_bytes=3,
                    sha256="abc",
                    object_key="migration-snapshot",
                    media_type="text/plain",
                    expires_at=expires,
                )
            )
            earlier = utcnow_naive() - timedelta(days=2)
            later = earlier + timedelta(days=1)
            for name, modified in (("index.html", earlier), ("app.js", later)):
                db.add(HermesFileObject(object_key=name, expires_at=expires))
                db.add(HermesSessionFile(
                    id=name, session_id=session.id, user_id=binding.user_id,
                    relative_path=name, size_bytes=3, sha256="abc", object_key=name,
                    media_type="text/html" if name.endswith("html") else "text/javascript",
                    expires_at=expires, updated_at=modified,
                ))
            user_id = user.id
            db.commit()
        command.upgrade(config, "hermes_file_versions_20260914")
        published = utcnow_naive() + timedelta(hours=1)
        with Session(engine) as db:
            anchor = db.get(HermesFileRevision, "index.html")
            db.add(HermesFileObject(object_key="subsequent", expires_at=expires))
            db.add(HermesFileRevision(
                id="subsequent", file_id=anchor.file_id, session_id=anchor.session_id,
                user_id=anchor.user_id, relative_path=anchor.relative_path, size_bytes=3,
                sha256="new", object_key="subsequent", media_type=anchor.media_type,
                expires_at=expires, created_at=published,
            ))
            db.commit()
        command.upgrade(config, "head")
        with Session(engine) as db:
            revision = db.get(HermesFileRevision, "legacy-file")
            assert revision.file_id == "legacy-file"
            assert revision.object_key == "migration-snapshot"
            assert revision.run_id is None
            assert revision.expires_at == expires
            anchor = db.get(HermesFileRevision, "index.html")
            dependency = db.get(HermesFileRevision, "app.js")
            assert anchor.created_at == dependency.created_at == revision.created_at
            assert db.get(HermesSessionFile, "index.html").updated_at == earlier
            assert db.get(HermesSessionFile, "app.js").updated_at == later
            assert db.get(HermesFileRevision, "subsequent").created_at == published
            monkeypatch.setattr(file_router, "read_file", lambda row: row.object_key.encode())
            result = file_router.preview_file_asset(anchor.id, path="app.js", db=db, user=db.get(User, user_id))
            assert result.body == b"app.js"
        import_all_models()
        with engine.connect() as connection:
            assert compare_metadata(MigrationContext.configure(connection), Base.metadata) == []
    finally:
        engine.dispose()


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
        with pytest.raises(RuntimeError, match="paired database/configuration restore"):
            command.downgrade(config, "group_sources_20260912")
    finally:
        engine.dispose()
