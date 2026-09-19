from alembic import context
from sqlalchemy import create_engine, pool

from codex_console.config import Settings
from codex_console.models import Base

url = context.config.attributes.get("database_url") or Settings().database_url
engine = create_engine(url, poolclass=pool.NullPool, hide_parameters=True)
with engine.connect() as connection:
    context.configure(
        connection=connection,
        target_metadata=Base.metadata,
        version_table="console_alembic_version",
    )
    with context.begin_transaction():
        context.run_migrations()
