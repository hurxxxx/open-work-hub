"""remove the retired image wizard

Revision ID: c8a1e4f7b2d9
Revises: b7f2d4a9c6e1
Create Date: 2026-08-11 10:00:00.000000

The upgrade removes executable configuration, app references, generated-image
records, and the image model control plane. Audit and usage history remain
intact. Downgrade restores empty tables only; deleted data and configuration
cannot be reconstructed.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c8a1e4f7b2d9"
down_revision: str | Sequence[str] | None = "b7f2d4a9c6e1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RETIRED_APP_IDS = ("image-wizard",)
RETIRED_TASK_KINDS = ("image_brief", "image_generation")
RETIRED_WORKLOAD_IDS = (
    "image-wizard.brief",
    "image-wizard.generate",
    "images.brief",
    "images.generate",
    *RETIRED_TASK_KINDS,
)


def _delete_matching(table_name: str, column_name: str, values: Sequence[str]) -> None:
    table = sa.table(table_name, sa.column(column_name, sa.String()))
    op.get_bind().execute(sa.delete(table).where(table.c[column_name].in_(values)))


def _update_matching(
    table_name: str,
    column_name: str,
    values: Sequence[str],
    replacement: str | None,
) -> None:
    table = sa.table(table_name, sa.column(column_name, sa.String()))
    op.get_bind().execute(
        sa.update(table).where(table.c[column_name].in_(values)).values({column_name: replacement})
    )


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
    rows = connection.execute(sa.select(scopes)).mappings().all()
    retired_apps = set(RETIRED_APP_IDS)
    retired_tasks = set(RETIRED_TASK_KINDS)

    for row in rows:
        if row["app_id"] in retired_apps:
            connection.execute(sa.delete(scopes).where(scopes.c.id == row["id"]))
            continue

        raw_task_kinds = row["task_kinds_json"]
        if isinstance(raw_task_kinds, list):
            filtered = [item for item in raw_task_kinds if item not in retired_tasks]
            if filtered != raw_task_kinds:
                if not filtered:
                    connection.execute(sa.delete(scopes).where(scopes.c.id == row["id"]))
                else:
                    connection.execute(
                        sa.update(scopes)
                        .where(scopes.c.id == row["id"])
                        .values(
                            task_kind=filtered[0] if len(filtered) == 1 else None,
                            task_kinds_json=filtered,
                        )
                    )
                continue

        if row["task_kind"] in retired_tasks:
            connection.execute(sa.delete(scopes).where(scopes.c.id == row["id"]))


def upgrade() -> None:
    """Remove image wizard data, settings, and live references."""
    for table_name in (
        "platform_app_bar_category_apps",
        "workspace_app_entitlements",
        "platform_app_visibility",
        "ai_artifacts",
        "ai_graph_runs",
        "ai_index_generations",
    ):
        _delete_matching(table_name, "app_id", RETIRED_APP_IDS)

    for table_name in ("docs_doc_targets", "recording_targets", "whiteboard_targets"):
        _delete_matching(table_name, "target_app", RETIRED_APP_IDS)

    _update_matching("docs_native_docs", "source_app", RETIRED_APP_IDS, "docs")
    _update_matching("whiteboards", "source_app", RETIRED_APP_IDS, "whiteboard")
    _update_matching("recording_staging", "initial_target_app", RETIRED_APP_IDS, None)

    _clean_user_app_bar_layouts()
    _clean_external_app_actions()
    _clean_ai_security_scopes("ai_security_policy_rules")
    _clean_ai_security_scopes("ai_security_external_transfer_exceptions")
    _delete_matching("ai_model_route_overrides", "workload_id", RETIRED_WORKLOAD_IDS)

    op.drop_table("image_model_profiles")
    op.drop_table("image_generations")
    op.drop_table("image_model_provider_configs")


def downgrade() -> None:
    """Restore empty image tables; deleted user data cannot be reconstructed."""
    op.create_table(
        "image_model_provider_configs",
        sa.Column("provider_id", sa.String(length=32), nullable=False),
        sa.Column("endpoint_url", sa.Text(), nullable=True),
        sa.Column("api_key_ciphertext", sa.Text(), nullable=True),
        sa.Column("supervisor_model_id", sa.String(length=160), nullable=True),
        sa.Column("generation_model_id", sa.String(length=160), nullable=True),
        sa.Column("enabled", sa.Boolean(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("provider_id"),
    )
    op.create_table(
        "image_generations",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("owner_id", sa.String(length=36), nullable=False),
        sa.Column("template_id", sa.String(length=80), nullable=True),
        sa.Column("is_template", sa.Boolean(), nullable=False),
        sa.Column("use_case", sa.String(length=64), nullable=False),
        sa.Column("use_case_other", sa.String(length=200), nullable=False),
        sa.Column("style", sa.JSON(), nullable=False),
        sa.Column("layout", sa.JSON(), nullable=False),
        sa.Column("details", sa.JSON(), nullable=False),
        sa.Column("context_refs", sa.JSON(), nullable=False),
        sa.Column("reference_image_keys", sa.JSON(), nullable=False),
        sa.Column("brief_versions", sa.JSON(), nullable=False),
        sa.Column("brief_status", sa.String(length=24), nullable=False),
        sa.Column("image_status", sa.String(length=24), nullable=False),
        sa.Column("image_storage_key", sa.String(length=512), nullable=True),
        sa.Column("image_model", sa.String(length=120), nullable=True),
        sa.Column("image_execution_profile", sa.JSON(), nullable=False),
        sa.Column("agent_trace_id", sa.String(length=120), nullable=True),
        sa.Column("failure_reason", sa.Text(), nullable=True),
        sa.Column("celery_task_id", sa.String(length=80), nullable=True),
        sa.Column("approved_at", sa.DateTime(), nullable=True),
        sa.Column("completed_at", sa.DateTime(), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.Column("trashed_at", sa.DateTime(), nullable=True),
        sa.ForeignKeyConstraint(["owner_id"], ["users.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_image_generations_brief_status"),
        "image_generations",
        ["brief_status"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_generations_image_status"),
        "image_generations",
        ["image_status"],
        unique=False,
    )
    op.create_index(
        "ix_image_generations_owner_created",
        "image_generations",
        ["owner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_generations_owner_id"),
        "image_generations",
        ["owner_id"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_generations_trashed_at"),
        "image_generations",
        ["trashed_at"],
        unique=False,
    )
    op.create_index(
        op.f("ix_image_generations_workspace_id"),
        "image_generations",
        ["workspace_id"],
        unique=False,
    )
    op.create_index(
        "ix_image_generations_workspace_image_status",
        "image_generations",
        ["workspace_id", "image_status"],
        unique=False,
    )
    op.create_index(
        "ix_image_generations_workspace_owner_created",
        "image_generations",
        ["workspace_id", "owner_id", "created_at"],
        unique=False,
    )
    op.create_index(
        "ix_image_generations_workspace_owner_template_created",
        "image_generations",
        ["workspace_id", "owner_id", "is_template", "created_at"],
        unique=False,
    )
    op.create_table(
        "image_model_profiles",
        sa.Column("profile_id", sa.String(length=32), nullable=False),
        sa.Column("active_provider_id", sa.String(length=32), nullable=True),
        sa.Column("brief_web_search_enabled", sa.Boolean(), nullable=False),
        sa.Column("generation_web_search_enabled", sa.Boolean(), nullable=False),
        sa.Column("max_iterations", sa.Integer(), nullable=False),
        sa.Column("version", sa.Integer(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint(
            "max_iterations BETWEEN 1 AND 20",
            name="ck_image_model_profiles_max_iterations",
        ),
        sa.ForeignKeyConstraint(
            ["active_provider_id"],
            ["image_model_provider_configs.provider_id"],
            ondelete="RESTRICT",
        ),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("profile_id"),
    )
