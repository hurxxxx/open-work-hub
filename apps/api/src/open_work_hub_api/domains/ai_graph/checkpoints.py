from __future__ import annotations

from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, contextmanager

from langgraph.checkpoint.postgres import PostgresSaver
from langgraph.checkpoint.postgres.aio import AsyncPostgresSaver

from open_work_hub_api.core.settings import get_settings


def normalize_checkpoint_dsn(dsn: str) -> str:
    """Convert a SQLAlchemy psycopg URL into the libpq URL used by psycopg."""

    if dsn.startswith("postgresql+psycopg://"):
        return "postgresql://" + dsn.removeprefix("postgresql+psycopg://")
    if dsn.startswith("postgres+psycopg://"):
        return "postgresql://" + dsn.removeprefix("postgres+psycopg://")
    return dsn


def _resolved_dsn(dsn: str | None) -> str:
    return normalize_checkpoint_dsn(dsn or get_settings().postgres_dsn)


@contextmanager
def postgres_checkpointer(
    dsn: str | None = None,
) -> Iterator[PostgresSaver]:
    """Open the production checkpointer without implicitly mutating schema."""

    with PostgresSaver.from_conn_string(_resolved_dsn(dsn)) as checkpointer:
        yield checkpointer


@asynccontextmanager
async def async_postgres_checkpointer(
    dsn: str | None = None,
) -> AsyncIterator[AsyncPostgresSaver]:
    """Open the async production checkpointer without implicitly mutating schema."""

    async with AsyncPostgresSaver.from_conn_string(_resolved_dsn(dsn)) as checkpointer:
        yield checkpointer


def setup_postgres_checkpoint_schema(dsn: str | None = None) -> None:
    """Explicit one-time setup for package-owned LangGraph checkpoint tables."""

    with postgres_checkpointer(dsn) as checkpointer:
        checkpointer.setup()


async def setup_async_postgres_checkpoint_schema(dsn: str | None = None) -> None:
    """Async variant of the explicit package schema setup."""

    async with async_postgres_checkpointer(dsn) as checkpointer:
        await checkpointer.setup()
