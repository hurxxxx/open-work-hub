from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import Base and all model modules so Base.metadata is fully populated.
from open_work_hub_api.core.db import Base
from open_work_hub_api.core.model_registry import import_all_models
from open_work_hub_api.core.settings import get_settings
import_all_models()

config = context.config

if config.config_file_name is not None:
    fileConfig(config.config_file_name)

# Resolve the DSN from app settings unless an override was passed in
# programmatically (e.g. tests). Allows operators to run alembic without
# duplicating the connection string in alembic.ini.
if not config.get_main_option("sqlalchemy.url", "").startswith(
    ("postgresql://", "postgresql+psycopg://")
):
    config.set_main_option("sqlalchemy.url", get_settings().postgres_dsn)

target_metadata = Base.metadata

_MANUALLY_MANAGED_INDEXES = {
    "ix_audit_logs_action_created",
    "ix_audit_logs_actor_created",
    "ix_audit_logs_created_at",
}


def include_object(object_, name: str | None, type_: str, reflected: bool, compare_to) -> bool:
    del compare_to
    if type_ == "index" and name in _MANUALLY_MANAGED_INDEXES:
        return False
    return True


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
        include_object=include_object,
    )

    with context.begin_transaction():
        context.run_migrations()


def run_migrations_online() -> None:
    connectable = engine_from_config(
        config.get_section(config.config_ini_section, {}),
        prefix="sqlalchemy.",
        poolclass=pool.NullPool,
    )

    with connectable.connect() as connection:
        context.configure(
            connection=connection,
            target_metadata=target_metadata,
            compare_type=True,
            compare_server_default=True,
            include_object=include_object,
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
