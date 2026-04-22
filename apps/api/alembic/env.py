from __future__ import annotations

from logging.config import fileConfig

from sqlalchemy import engine_from_config, pool

from alembic import context

# Import Base and all model modules so Base.metadata is fully populated.
from aidoo_api.core.db import Base
from aidoo_api.core.settings import get_settings
from aidoo_api.domains.ai import approvals as ai_approvals  # noqa: F401
from aidoo_api.domains.ai import models as ai_models  # noqa: F401
from aidoo_api.domains.auth import models as auth_models  # noqa: F401
from aidoo_api.domains.conversations import models as conversations_models  # noqa: F401
from aidoo_api.domains.docs import models as docs_models  # noqa: F401
from aidoo_api.domains.media import models as media_models  # noqa: F401
from aidoo_api.domains.meeting import models as meeting_models  # noqa: F401
from aidoo_api.domains.planner import models as planner_models  # noqa: F401
from aidoo_api.domains.pms import models as pms_models  # noqa: F401
from aidoo_api.domains.rag import models as rag_models  # noqa: F401

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


def run_migrations_offline() -> None:
    url = config.get_main_option("sqlalchemy.url")
    context.configure(
        url=url,
        target_metadata=target_metadata,
        literal_binds=True,
        dialect_opts={"paramstyle": "named"},
        compare_type=True,
        compare_server_default=True,
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
        )

        with context.begin_transaction():
            context.run_migrations()


if context.is_offline_mode():
    run_migrations_offline()
else:
    run_migrations_online()
