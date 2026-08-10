"""remove retired document assistant apps

Revision ID: 8b1f3c2d4e5a
Revises: 3efcf1ed36c3
Create Date: 2026-08-10 18:30:00.000000

The upgrade removes active configuration and app-owned data for the retired
document translation, drafting, and specification comparison apps. Audit and
usage history remains intact. Downgrade recreates the specification comparison
schema, but deleted rows and configuration cannot be restored.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql


revision: str = "8b1f3c2d4e5a"
down_revision: str | Sequence[str] | None = "3efcf1ed36c3"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RETIRED_APP_IDS = ("document-translate", "drafting", "spec-compare")
RETIRED_TASK_KINDS = (
    "document_translate",
    "draft_assist",
    "spec_compare_extract",
    "spec_compare_compare",
    "spec_compare_report",
)
RETIRED_WORKLOAD_IDS = (
    "document_translate",
    "draft_assist",
    "spec_compare.extract",
    "spec_compare.compare",
    "spec_compare.report",
)


def _delete_by_app_id(table_name: str) -> None:
    table = sa.table(table_name, sa.column("app_id", sa.String(length=64)))
    op.get_bind().execute(sa.delete(table).where(table.c.app_id.in_(RETIRED_APP_IDS)))


def _clean_user_app_bar_layouts() -> None:
    users = sa.table(
        "users",
        sa.column("id", sa.String(length=36)),
        sa.column("app_bar_layout", sa.JSON()),
    )
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.select(users.c.id, users.c.app_bar_layout).where(users.c.app_bar_layout.is_not(None))
        )
        .mappings()
        .all()
    )
    retired = set(RETIRED_APP_IDS)
    for row in rows:
        layout = row["app_bar_layout"]
        if not isinstance(layout, dict):
            continue
        pinned_app_ids = layout.get("pinned_app_ids")
        if not isinstance(pinned_app_ids, list):
            continue
        filtered = [app_id for app_id in pinned_app_ids if app_id not in retired]
        if filtered == pinned_app_ids:
            continue
        next_layout = dict(layout)
        next_layout["pinned_app_ids"] = filtered
        connection.execute(
            sa.update(users).where(users.c.id == row["id"]).values(app_bar_layout=next_layout)
        )


def _clean_external_app_actions() -> None:
    settings = sa.table(
        "ai_security_data_protection_settings",
        sa.column("id", sa.String(length=36)),
        sa.column("external_app_actions_json", sa.JSON()),
    )
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.select(settings.c.id, settings.c.external_app_actions_json).where(
                settings.c.external_app_actions_json.is_not(None)
            )
        )
        .mappings()
        .all()
    )
    retired = set(RETIRED_APP_IDS)
    for row in rows:
        actions = row["external_app_actions_json"]
        if not isinstance(actions, dict) or retired.isdisjoint(actions):
            continue
        filtered = {key: value for key, value in actions.items() if key not in retired}
        connection.execute(
            sa.update(settings)
            .where(settings.c.id == row["id"])
            .values(external_app_actions_json=filtered)
        )


def _clean_ai_security_scopes(table_name: str) -> None:
    scopes = sa.table(
        table_name,
        sa.column("id", sa.String(length=36)),
        sa.column("app_id", sa.String(length=64)),
        sa.column("task_kind", sa.String(length=128)),
        sa.column("task_kinds_json", sa.JSON()),
    )
    connection = op.get_bind()
    rows = (
        connection.execute(
            sa.select(
                scopes.c.id,
                scopes.c.app_id,
                scopes.c.task_kind,
                scopes.c.task_kinds_json,
            )
        )
        .mappings()
        .all()
    )
    retired_apps = set(RETIRED_APP_IDS)
    retired_tasks = set(RETIRED_TASK_KINDS)

    for row in rows:
        if row["app_id"] in retired_apps:
            connection.execute(sa.delete(scopes).where(scopes.c.id == row["id"]))
            continue

        raw_task_kinds = row["task_kinds_json"]
        if isinstance(raw_task_kinds, list):
            normalized = [item for item in raw_task_kinds if isinstance(item, str)]
            filtered = [item for item in normalized if item not in retired_tasks]
            if filtered != normalized:
                if not filtered:
                    connection.execute(sa.delete(scopes).where(scopes.c.id == row["id"]))
                else:
                    legacy_task_kind = filtered[0] if len(filtered) == 1 else None
                    connection.execute(
                        sa.update(scopes)
                        .where(scopes.c.id == row["id"])
                        .values(
                            task_kind=legacy_task_kind,
                            task_kinds_json=filtered,
                        )
                    )
                continue

        if row["task_kind"] in retired_tasks:
            connection.execute(sa.delete(scopes).where(scopes.c.id == row["id"]))


def upgrade() -> None:
    """Remove retired app configuration, app-owned data, and tables."""
    for table_name in (
        "platform_app_bar_category_apps",
        "workspace_app_entitlements",
        "platform_app_visibility",
        "ai_artifacts",
        "ai_graph_runs",
        "ai_index_generations",
    ):
        _delete_by_app_id(table_name)

    _clean_user_app_bar_layouts()
    _clean_external_app_actions()
    _clean_ai_security_scopes("ai_security_policy_rules")
    _clean_ai_security_scopes("ai_security_external_transfer_exceptions")

    route_overrides = sa.table(
        "ai_model_route_overrides",
        sa.column("workload_id", sa.String(length=160)),
    )
    op.get_bind().execute(
        sa.delete(route_overrides).where(route_overrides.c.workload_id.in_(RETIRED_WORKLOAD_IDS))
    )

    op.drop_table("spec_compare_spec_items")
    op.drop_table("spec_compare_jobs")


def downgrade() -> None:
    """Recreate empty specification comparison tables."""
    op.create_table(
        "spec_compare_jobs",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("title", sa.String(length=200), nullable=False),
        sa.Column(
            "status",
            sa.String(length=24),
            server_default=sa.text("'queued'"),
            nullable=False,
        ),
        sa.Column(
            "progress",
            sa.Integer(),
            server_default=sa.text("0"),
            nullable=False,
        ),
        sa.Column("status_message", sa.String(length=300), nullable=False),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("base_file_name", sa.String(length=512), nullable=False),
        sa.Column("base_mime_type", sa.String(length=160), nullable=False),
        sa.Column("base_size_bytes", sa.Integer(), nullable=False),
        sa.Column("base_storage_key", sa.String(length=1024), nullable=False),
        sa.Column("target_file_name", sa.String(length=512), nullable=False),
        sa.Column("target_mime_type", sa.String(length=160), nullable=False),
        sa.Column("target_size_bytes", sa.Integer(), nullable=False),
        sa.Column("target_storage_key", sa.String(length=1024), nullable=False),
        sa.Column("result_json_storage_key", sa.String(length=1024), nullable=True),
        sa.Column(
            "report_markdown_storage_key",
            sa.String(length=1024),
            nullable=True,
        ),
        sa.Column(
            "result_summary",
            postgresql.JSONB(astext_type=sa.Text()).with_variant(sa.JSON(), "sqlite"),
            nullable=True,
        ),
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "status IN ('queued','running','succeeded','failed','cancelled')",
            name="ck_spec_compare_jobs_status",
        ),
        sa.CheckConstraint(
            "progress >= 0 AND progress <= 100",
            name="ck_spec_compare_jobs_progress",
        ),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_spec_compare_jobs_owner_id"),
        "spec_compare_jobs",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_compare_jobs_status"),
        "spec_compare_jobs",
        ["status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_spec_compare_jobs_workspace_id"),
        "spec_compare_jobs",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_spec_compare_jobs_workspace_owner_created",
        "spec_compare_jobs",
        ["workspace_id", "owner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_spec_compare_jobs_workspace_status_created",
        "spec_compare_jobs",
        ["workspace_id", "status", "created_at"],
        unique=False,
    )

    op.create_table(
        "spec_compare_spec_items",
        sa.Column("id", sa.String(length=140), nullable=False),
        sa.Column("job_id", sa.String(length=36), nullable=False),
        sa.Column("document_role", sa.String(length=16), nullable=False),
        sa.Column("item_id", sa.String(length=100), nullable=False),
        sa.Column("normalized_key", sa.String(length=300), nullable=False),
        sa.Column("category", sa.String(length=300), nullable=False),
        sa.Column("item_name", sa.String(length=300), nullable=False),
        sa.Column("value", sa.Text(), nullable=False),
        sa.Column("unit", sa.String(length=80), nullable=False),
        sa.Column("condition", sa.String(length=500), nullable=False),
        sa.Column("evidence_id", sa.String(length=160), nullable=False),
        sa.Column("locator_label", sa.String(length=160), nullable=False),
        sa.Column("section_path", sa.String(length=300), nullable=False),
        sa.Column("source_text", sa.Text(), nullable=False),
        sa.Column("confidence", sa.Float(), nullable=False),
        sa.Column("extraction_method", sa.String(length=80), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "document_role IN ('base','target')",
            name="ck_spec_compare_spec_items_document_role",
        ),
        sa.ForeignKeyConstraint(
            ["job_id"],
            ["spec_compare_jobs.id"],
            ondelete="CASCADE",
        ),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint(
            "job_id",
            "document_role",
            "item_id",
            name="uq_spec_compare_spec_items_job_role_item",
        ),
    )
    op.create_index(
        "ix_spec_compare_spec_items_job_role",
        "spec_compare_spec_items",
        ["job_id", "document_role"],
        unique=False,
    )
    op.create_index(
        "ix_spec_compare_spec_items_normalized_key",
        "spec_compare_spec_items",
        ["normalized_key"],
        unique=False,
    )
