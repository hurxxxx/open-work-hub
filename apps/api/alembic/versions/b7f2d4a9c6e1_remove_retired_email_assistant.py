"""remove retired email assistant references

Revision ID: b7f2d4a9c6e1
Revises: a2e6c8f1b3d5
Create Date: 2026-08-10 23:00:00.000000

The upgrade removes executable configuration and cross-app links for the
retired email assistant. Audit and usage history remain intact. Deleted
configuration and links cannot be reconstructed by downgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "b7f2d4a9c6e1"
down_revision: str | Sequence[str] | None = "a2e6c8f1b3d5"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


RETIRED_APP_IDS = ("email-assistant",)
RETIRED_TASK_KINDS = ("mail_compose", "writing_translate")
RETIRED_WORKLOAD_IDS = RETIRED_TASK_KINDS


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
    """Remove retired email assistant configuration and live references."""
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


def downgrade() -> None:
    """Retired configuration and cross-app links cannot be reconstructed."""
