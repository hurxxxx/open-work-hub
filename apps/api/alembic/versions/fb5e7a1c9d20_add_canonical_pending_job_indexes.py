"""Add canonical pending-job indexes for fenced retrieval events.

Revision ID: fb5e7a1c9d20
Revises: fa4d7b1c5e20
Create Date: 2026-07-22 22:00:00.000000
"""

from __future__ import annotations

from alembic import op
import sqlalchemy as sa


revision = "fb5e7a1c9d20"
down_revision = "fa4d7b1c5e20"
branch_labels = None
depends_on = None


_POSTGRESQL_LOCK_TIMEOUT = "5s"
_WORKSPACE_INDEX = "uq_rag_sync_jobs_pending_workspace_resource_lane"
_COMPANY_INDEX = "uq_rag_sync_jobs_pending_company_resource_lane"
_VERSIONED_INDEX = "uq_rag_sync_jobs_pending_versioned_resource_lane"
_SEARCH_FENCED_INDEX = "uq_search_index_jobs_pending_resource_fenced"
_CORPUS_INDEXES = (
    ("ix_file_manager_folders_corpus_id", "file_manager_folders"),
    ("ix_file_manager_files_corpus_id", "file_manager_files"),
)


def upgrade() -> None:
    if op.get_bind().dialect.name == "postgresql":
        _upgrade_postgresql()
        return
    _upgrade_transactional()


def downgrade() -> None:
    _assert_legacy_rag_uniqueness_can_be_restored()
    if op.get_bind().dialect.name == "postgresql":
        _downgrade_postgresql()
        return
    _downgrade_transactional()


def _upgrade_transactional() -> None:
    op.drop_index(
        _WORKSPACE_INDEX,
        table_name="rag_sync_jobs",
    )
    op.drop_index(
        _COMPANY_INDEX,
        table_name="rag_sync_jobs",
    )
    op.create_index(
        _WORKSPACE_INDEX,
        "rag_sync_jobs",
        ["scope_kind", "workspace_id", "lane", "resource_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'pending' AND workspace_id IS NOT NULL "
            "AND projection_version IS NULL"
        ),
        sqlite_where=sa.text(
            "status = 'pending' AND workspace_id IS NOT NULL "
            "AND projection_version IS NULL"
        ),
    )
    op.create_index(
        _COMPANY_INDEX,
        "rag_sync_jobs",
        ["scope_kind", "lane", "resource_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'pending' AND workspace_id IS NULL "
            "AND projection_version IS NULL"
        ),
        sqlite_where=sa.text(
            "status = 'pending' AND workspace_id IS NULL "
            "AND projection_version IS NULL"
        ),
    )
    op.create_index(
        _VERSIONED_INDEX,
        "rag_sync_jobs",
        ["lane", "resource_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'pending' AND projection_version IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "status = 'pending' AND projection_version IS NOT NULL"
        ),
    )
    op.create_index(
        _SEARCH_FENCED_INDEX,
        "search_index_jobs",
        ["resource_type", "entity_id"],
        unique=True,
        postgresql_where=sa.text(
            "status = 'pending' AND resource_type IS NOT NULL "
            "AND projection_version IS NOT NULL"
        ),
        sqlite_where=sa.text(
            "status = 'pending' AND resource_type IS NOT NULL "
            "AND projection_version IS NOT NULL"
        ),
    )


def _downgrade_transactional() -> None:
    op.drop_index(
        _SEARCH_FENCED_INDEX,
        table_name="search_index_jobs",
    )
    op.drop_index(
        _VERSIONED_INDEX,
        table_name="rag_sync_jobs",
    )
    op.drop_index(
        _COMPANY_INDEX,
        table_name="rag_sync_jobs",
    )
    op.drop_index(
        _WORKSPACE_INDEX,
        table_name="rag_sync_jobs",
    )
    op.create_index(
        _COMPANY_INDEX,
        "rag_sync_jobs",
        ["scope_kind", "lane", "resource_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND workspace_id IS NULL"),
        sqlite_where=sa.text("status = 'pending' AND workspace_id IS NULL"),
    )
    op.create_index(
        _WORKSPACE_INDEX,
        "rag_sync_jobs",
        ["scope_kind", "workspace_id", "lane", "resource_type", "resource_id"],
        unique=True,
        postgresql_where=sa.text("status = 'pending' AND workspace_id IS NOT NULL"),
        sqlite_where=sa.text("status = 'pending' AND workspace_id IS NOT NULL"),
    )


def _upgrade_postgresql() -> None:
    """Build every index on an existing table without blocking its writers."""
    with op.get_context().autocommit_block():
        _set_session_lock_timeout()
        try:
            for index_name, table_name in _CORPUS_INDEXES:
                _ensure_concurrent_index(
                    index_name,
                    f'CREATE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}" '
                    f'ON "{table_name}" ("corpus_id")',
                )

            # Establish protection for versioned/fenced jobs before narrowing
            # the legacy RAG predicates.
            _ensure_concurrent_index(
                _VERSIONED_INDEX,
                f'CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "{_VERSIONED_INDEX}" '
                'ON "rag_sync_jobs" ("lane", "resource_type", "resource_id") '
                "WHERE status = 'pending' AND projection_version IS NOT NULL",
            )
            _ensure_concurrent_index(
                _SEARCH_FENCED_INDEX,
                f'CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "{_SEARCH_FENCED_INDEX}" '
                'ON "search_index_jobs" ("resource_type", "entity_id") '
                "WHERE status = 'pending' AND resource_type IS NOT NULL "
                "AND projection_version IS NOT NULL",
            )
            _replace_rag_index_concurrently(
                _WORKSPACE_INDEX,
                workspace_scoped=True,
                include_projection_null=True,
            )
            _replace_rag_index_concurrently(
                _COMPANY_INDEX,
                workspace_scoped=False,
                include_projection_null=True,
            )
        finally:
            _reset_session_lock_timeout()


def _downgrade_postgresql() -> None:
    """Restore legacy uniqueness online, or fail before discarding any fence."""
    with op.get_context().autocommit_block():
        _set_session_lock_timeout()
        try:
            # Build the broader legacy indexes while both fenced indexes still
            # protect writes.  A concurrent build also detects a post-preflight
            # race and fails without removing the newer protection.
            _replace_rag_index_concurrently(
                _WORKSPACE_INDEX,
                workspace_scoped=True,
                include_projection_null=False,
            )
            _replace_rag_index_concurrently(
                _COMPANY_INDEX,
                workspace_scoped=False,
                include_projection_null=False,
            )
            _drop_concurrent_index(_SEARCH_FENCED_INDEX)
            _drop_concurrent_index(_VERSIONED_INDEX)
            for index_name, _table_name in reversed(_CORPUS_INDEXES):
                _drop_concurrent_index(index_name)
        finally:
            _reset_session_lock_timeout()


def _assert_legacy_rag_uniqueness_can_be_restored() -> None:
    duplicate = op.get_bind().execute(
        sa.text(
            """
            SELECT 1
            FROM rag_sync_jobs
            WHERE status = 'pending'
            GROUP BY scope_kind, workspace_id, lane, resource_type, resource_id
            HAVING count(*) > 1
            LIMIT 1
            """
        )
    ).first()
    if duplicate is not None:
        raise RuntimeError(
            "Cannot downgrade fb5e7a1c9d20 while legacy and fenced pending RAG "
            "jobs collide. Keep the expanded schema for application rollback, "
            "or drain/supersede the conflicting pending jobs before retrying."
        )


def _replace_rag_index_concurrently(
    canonical_name: str,
    *,
    workspace_scoped: bool,
    include_projection_null: bool,
) -> None:
    temporary_name = f"{canonical_name}__fb5e_tmp"
    canonical_state = _postgresql_index_state(canonical_name)
    temporary_state = _postgresql_index_state(temporary_name)

    if _predicate_matches(canonical_state, include_projection_null):
        if temporary_state[0]:
            _drop_concurrent_index(temporary_name)
        return

    if temporary_state[0] and not _is_valid_index(temporary_state):
        if not _is_valid_index(canonical_state):
            raise RuntimeError(
                f"Neither {canonical_name} nor {temporary_name} is a valid unique index; "
                "manual duplicate inspection is required before retrying."
            )
        _drop_concurrent_index(temporary_name)
        temporary_state = _postgresql_index_state(temporary_name)

    if not temporary_state[0]:
        if not _is_valid_index(canonical_state):
            raise RuntimeError(
                f"Cannot replace missing or invalid unique index {canonical_name} "
                "without risking an unprotected write window."
            )
        _ensure_concurrent_index(
            temporary_name,
            _rag_index_create_sql(
                temporary_name,
                workspace_scoped=workspace_scoped,
                include_projection_null=include_projection_null,
            ),
        )
        temporary_state = _postgresql_index_state(temporary_name)

    if not _is_valid_index(temporary_state):
        raise RuntimeError(f"Replacement index {temporary_name} is not valid and ready.")

    if canonical_state[0]:
        _drop_concurrent_index(canonical_name)
    op.execute(sa.text(f'ALTER INDEX "{temporary_name}" RENAME TO "{canonical_name}"'))

    replaced_state = _postgresql_index_state(canonical_name)
    if not _predicate_matches(replaced_state, include_projection_null):
        raise RuntimeError(f"Replacement index {canonical_name} was not installed correctly.")


def _rag_index_create_sql(
    index_name: str,
    *,
    workspace_scoped: bool,
    include_projection_null: bool,
) -> str:
    if workspace_scoped:
        columns = '"scope_kind", "workspace_id", "lane", "resource_type", "resource_id"'
        predicate = "status = 'pending' AND workspace_id IS NOT NULL"
    else:
        columns = '"scope_kind", "lane", "resource_type", "resource_id"'
        predicate = "status = 'pending' AND workspace_id IS NULL"
    if include_projection_null:
        predicate += " AND projection_version IS NULL"
    return (
        f'CREATE UNIQUE INDEX CONCURRENTLY IF NOT EXISTS "{index_name}" '
        f'ON "rag_sync_jobs" ({columns}) WHERE {predicate}'
    )


def _ensure_concurrent_index(index_name: str, create_sql: str) -> None:
    state = _postgresql_index_state(index_name)
    if _is_valid_index(state):
        return
    if state[0]:
        _drop_concurrent_index(index_name)
    op.execute(sa.text(create_sql))
    if not _is_valid_index(_postgresql_index_state(index_name)):
        raise RuntimeError(f"Concurrent index {index_name} is not valid and ready.")


def _drop_concurrent_index(index_name: str) -> None:
    op.execute(sa.text(f'DROP INDEX CONCURRENTLY IF EXISTS "{index_name}"'))


def _postgresql_index_state(index_name: str) -> tuple[bool, bool, bool, str | None]:
    row = op.get_bind().execute(
        sa.text(
            """
            SELECT indexes.indisvalid,
                   indexes.indisready,
                   pg_get_expr(indexes.indpred, indexes.indrelid) AS predicate
            FROM pg_catalog.pg_index AS indexes
            WHERE indexes.indexrelid = to_regclass(:index_name)
            """
        ),
        {"index_name": index_name},
    ).one_or_none()
    if row is None:
        return (False, False, False, None)
    return (True, bool(row.indisvalid), bool(row.indisready), row.predicate)


def _is_valid_index(state: tuple[bool, bool, bool, str | None]) -> bool:
    return state[0] and state[1] and state[2]


def _predicate_matches(
    state: tuple[bool, bool, bool, str | None],
    include_projection_null: bool,
) -> bool:
    if not _is_valid_index(state) or state[3] is None:
        return False
    has_projection_null = "PROJECTION_VERSION IS NULL" in state[3].upper()
    return has_projection_null is include_projection_null


def _set_session_lock_timeout() -> None:
    op.execute(sa.text(f"SET lock_timeout = '{_POSTGRESQL_LOCK_TIMEOUT}'"))


def _reset_session_lock_timeout() -> None:
    op.execute(sa.text("RESET lock_timeout"))
