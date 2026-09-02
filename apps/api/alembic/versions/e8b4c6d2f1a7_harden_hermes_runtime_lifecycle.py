"""Harden Hermes runtime lifecycle and recovery state.

Revision ID: e8b4c6d2f1a7
Revises: d1f4a8c2e6b9
"""

from __future__ import annotations

from datetime import UTC, datetime

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision = "e8b4c6d2f1a7"
down_revision = "d1f4a8c2e6b9"
branch_labels = None
depends_on = None


HERMES_TERMINAL_APP_ID = "hermes-terminal"
HERMES_TERMINAL_CATEGORY_MAPPING_ID = "e8b4c6d2-f1a7-4f00-9000-000000000001"
HERMES_TERMINAL_FALLBACK_CATEGORY_ID = "e8b4c6d2-f1a7-4f00-9000-000000000002"


def _app_bar_tables() -> tuple[sa.TableClause, sa.TableClause]:
    categories = sa.table(
        "platform_app_bar_categories",
        sa.column("id", sa.String(length=36)),
        sa.column("key", sa.String(length=64)),
        sa.column("title", sa.String(length=120)),
        sa.column("icon_key", sa.String(length=64)),
        sa.column("position", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    category_apps = sa.table(
        "platform_app_bar_category_apps",
        sa.column("id", sa.String(length=36)),
        sa.column("category_id", sa.String(length=36)),
        sa.column("app_id", sa.String(length=64)),
        sa.column("position", sa.Integer()),
        sa.column("created_at", sa.DateTime()),
        sa.column("updated_at", sa.DateTime()),
    )
    return categories, category_apps


def _ensure_hermes_terminal_app_bar_mapping(bind: sa.Connection) -> None:
    """Place Hermes Terminal in the existing all-apps launcher exactly once."""

    categories, category_apps = _app_bar_tables()
    existing_mapping = bind.scalar(
        sa.select(category_apps.c.id)
        .where(category_apps.c.app_id == HERMES_TERMINAL_APP_ID)
        .limit(1)
    )
    if existing_mapping is not None:
        return

    preferred_category = sa.case(
        (
            sa.or_(
                sa.func.lower(categories.c.key).in_(("all-apps", "dev-all-apps")),
                sa.func.lower(categories.c.title) == "all apps",
                categories.c.title == "전체 앱",
            ),
            0,
        ),
        else_=1,
    )
    selected = bind.execute(
        sa.select(categories.c.id)
        .select_from(
            categories.outerjoin(
                category_apps,
                category_apps.c.category_id == categories.c.id,
            )
        )
        .group_by(
            categories.c.id,
            categories.c.key,
            categories.c.title,
            categories.c.position,
            categories.c.created_at,
        )
        .order_by(
            preferred_category.asc(),
            sa.func.count(category_apps.c.id).desc(),
            categories.c.position.asc(),
            categories.c.created_at.asc(),
            categories.c.id.asc(),
        )
        .limit(1)
    ).first()

    now = datetime.now(UTC).replace(tzinfo=None)
    if selected is None:
        category_id = HERMES_TERMINAL_FALLBACK_CATEGORY_ID
        bind.execute(
            categories.insert().values(
                id=category_id,
                key="all-apps",
                title="All Apps",
                icon_key="layout-grid",
                position=0,
                created_at=now,
                updated_at=now,
            )
        )
    else:
        category_id = str(selected.id)

    last_position = bind.scalar(
        sa.select(sa.func.max(category_apps.c.position)).where(
            category_apps.c.category_id == category_id
        )
    )
    bind.execute(
        category_apps.insert().values(
            id=HERMES_TERMINAL_CATEGORY_MAPPING_ID,
            category_id=category_id,
            app_id=HERMES_TERMINAL_APP_ID,
            position=(int(last_position) + 1) if last_position is not None else 0,
            created_at=now,
            updated_at=now,
        )
    )


def _remove_managed_hermes_terminal_app_bar_mapping(bind: sa.Connection) -> None:
    categories, category_apps = _app_bar_tables()
    bind.execute(
        category_apps.delete().where(category_apps.c.id == HERMES_TERMINAL_CATEGORY_MAPPING_ID)
    )
    fallback_has_apps = sa.exists(
        sa.select(category_apps.c.id).where(
            category_apps.c.category_id == HERMES_TERMINAL_FALLBACK_CATEGORY_ID
        )
    )
    bind.execute(
        categories.delete().where(
            categories.c.id == HERMES_TERMINAL_FALLBACK_CATEGORY_ID,
            ~fallback_has_apps,
        )
    )


def upgrade() -> None:
    op.add_column(
        "hermes_terminal_sessions",
        sa.Column("archive_claim_token", sa.String(length=64), nullable=True),
    )
    op.add_column(
        "hermes_terminal_sessions",
        sa.Column("archive_claim_expires_at", sa.DateTime(), nullable=True),
    )
    op.add_column(
        "hermes_terminal_sessions",
        sa.Column(
            "artifact_archived_bytes",
            sa.BigInteger(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "hermes_terminal_sessions",
        sa.Column(
            "artifact_omitted_count",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
    )
    op.add_column(
        "hermes_terminal_sessions",
        sa.Column(
            "workspace_retained",
            sa.Boolean(),
            server_default=sa.text("false"),
            nullable=False,
        ),
    )
    op.add_column(
        "hermes_terminal_sessions",
        sa.Column("quarantine_reason", sa.String(length=160), nullable=True),
    )
    op.create_index(
        "ix_hermes_terminal_sessions_archive_claim_expires_at",
        "hermes_terminal_sessions",
        ["archive_claim_expires_at"],
        unique=False,
    )

    op.add_column(
        "hermes_run_projections",
        sa.Column("client_request_id", sa.String(length=128), nullable=True),
    )
    op.add_column(
        "hermes_run_projections",
        sa.Column("request_sha256", sa.String(length=64), nullable=True),
    )
    op.create_index(
        "uq_hermes_run_projections_profile_client_request",
        "hermes_run_projections",
        ["profile_binding_id", "client_request_id"],
        unique=True,
        postgresql_where=sa.text("client_request_id IS NOT NULL"),
        sqlite_where=sa.text("client_request_id IS NOT NULL"),
    )

    op.add_column(
        "hermes_tool_approvals",
        sa.Column("expires_at", sa.DateTime(), nullable=True),
    )
    if op.get_bind().dialect.name == "sqlite":
        op.execute(
            "UPDATE hermes_tool_approvals "
            "SET expires_at = datetime(created_at, '+300 seconds') "
            "WHERE expires_at IS NULL"
        )
    else:
        op.execute(
            "UPDATE hermes_tool_approvals "
            "SET expires_at = created_at + INTERVAL '300 seconds' "
            "WHERE expires_at IS NULL"
        )
    with op.batch_alter_table("hermes_tool_approvals") as batch_op:
        batch_op.alter_column("expires_at", nullable=False)
    op.create_index(
        "ix_hermes_tool_approvals_status_expiry",
        "hermes_tool_approvals",
        ["status", "expires_at"],
        unique=False,
    )

    op.create_table(
        "hermes_maintenance_states",
        sa.Column("component", sa.String(length=64), nullable=False),
        sa.Column("last_started_at", sa.DateTime(), nullable=True),
        sa.Column("last_succeeded_at", sa.DateTime(), nullable=True),
        sa.Column("last_error_code", sa.String(length=160), nullable=True),
        sa.Column("run_scan_cursor", sa.String(length=36), nullable=True),
        sa.Column("job_scan_cursor", sa.String(length=36), nullable=True),
        sa.Column("lease_token", sa.String(length=64), nullable=True),
        sa.Column("lease_expires_at", sa.DateTime(), nullable=True),
        sa.Column(
            "counters",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            server_default=sa.text("'{}'"),
            nullable=False,
        ),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("component"),
    )
    _ensure_hermes_terminal_app_bar_mapping(op.get_bind())


def downgrade() -> None:
    _remove_managed_hermes_terminal_app_bar_mapping(op.get_bind())
    op.drop_table("hermes_maintenance_states")
    op.drop_index(
        "ix_hermes_tool_approvals_status_expiry",
        table_name="hermes_tool_approvals",
    )
    op.drop_column("hermes_tool_approvals", "expires_at")
    op.drop_index(
        "uq_hermes_run_projections_profile_client_request",
        table_name="hermes_run_projections",
        postgresql_where=sa.text("client_request_id IS NOT NULL"),
        sqlite_where=sa.text("client_request_id IS NOT NULL"),
    )
    op.drop_column("hermes_run_projections", "request_sha256")
    op.drop_column("hermes_run_projections", "client_request_id")
    op.drop_index(
        "ix_hermes_terminal_sessions_archive_claim_expires_at",
        table_name="hermes_terminal_sessions",
    )
    op.drop_column("hermes_terminal_sessions", "quarantine_reason")
    op.drop_column("hermes_terminal_sessions", "workspace_retained")
    op.drop_column("hermes_terminal_sessions", "artifact_omitted_count")
    op.drop_column("hermes_terminal_sessions", "artifact_archived_bytes")
    op.drop_column("hermes_terminal_sessions", "archive_claim_expires_at")
    op.drop_column("hermes_terminal_sessions", "archive_claim_token")
