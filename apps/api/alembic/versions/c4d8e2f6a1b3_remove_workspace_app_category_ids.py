"""remove_workspace_app_category_ids

Revision ID: c4d8e2f6a1b3
Revises: b3d7f1a9c2e4
Create Date: 2026-07-09 12:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from typing import Any

import sqlalchemy as sa
from alembic import op


revision: str = "c4d8e2f6a1b3"
down_revision: str | Sequence[str] | None = "b3d7f1a9c2e4"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


STALE_CATEGORY_APP_IDS = frozenset({"ai", "collaboration", "business"})
LEGACY_SECTION_CHILD_APP_IDS = {
    "collaboration": (
        "pms",
        "docs",
        "files",
        "mail",
        "meeting",
        "planner",
        "whiteboard",
        "diagrams",
        "recording",
        "community",
        "video-chat",
    ),
    "business": (
        "plm",
        "learning",
        "news",
        "drafting",
        "document-translate",
        "spec-compare",
        "fmea-compare",
        "imds-minerals",
        "image-wizard",
        "email-assistant",
        "ppt-assistant",
        "retrieval-search",
        "law-search",
        "patent-compose",
        "patent-analysis",
        "patent-report",
        "patent-automation",
        "meal-invoice-ocr",
        "data-viz",
        "legacy-issues",
    ),
    "ai": (
        "chatbot",
        "qa-assistant",
        "web-search",
        "research-trends",
        "standards-monitor",
    ),
}
DEFAULT_APP_BAR_PINNED_APP_IDS = (
    "pms",
    "docs",
    "whiteboard",
    "qa-assistant",
)
LEGACY_DEFAULT_APP_BAR_PINNED_APP_IDS = (
    ("ai", "business"),
    ("ai", "collaboration", "business"),
)
DEFAULT_APP_BAR_FIXED_APP_IDS = frozenset({"home"})
MAX_APP_BAR_PINNED_APP_IDS = 8
KNOWN_APP_BAR_APP_IDS = frozenset(
    {
        "pms",
        "docs",
        "files",
        "mail",
        "meeting",
        "planner",
        "whiteboard",
        "diagrams",
        "recording",
        "community",
        "video-chat",
        "plm",
        "learning",
        "news",
        "drafting",
        "document-translate",
        "spec-compare",
        "fmea-compare",
        "imds-minerals",
        "image-wizard",
        "email-assistant",
        "ppt-assistant",
        "retrieval-search",
        "law-search",
        "patent-compose",
        "patent-analysis",
        "patent-report",
        "patent-automation",
        "meal-invoice-ocr",
        "data-viz",
        "legacy-issues",
        "chatbot",
        "qa-assistant",
        "web-search",
        "research-trends",
        "standards-monitor",
    }
)


def _normalize_pinned_app_ids(value: Any) -> list[str] | None:
    if not isinstance(value, list):
        return None
    raw_app_ids = tuple(
        item
        for item in value
        if isinstance(item, str) and item not in DEFAULT_APP_BAR_FIXED_APP_IDS
    )
    if raw_app_ids in LEGACY_DEFAULT_APP_BAR_PINNED_APP_IDS:
        return list(DEFAULT_APP_BAR_PINNED_APP_IDS)

    normalized: list[str] = []
    for item in value:
        if (
            not isinstance(item, str)
            or item in DEFAULT_APP_BAR_FIXED_APP_IDS
            or item in STALE_CATEGORY_APP_IDS
            or item not in KNOWN_APP_BAR_APP_IDS
        ):
            continue
        if item not in normalized:
            normalized.append(item)
            if len(normalized) >= MAX_APP_BAR_PINNED_APP_IDS:
                break
    return normalized


def _normalize_app_bar_layout(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, dict):
        return None
    pinned_app_ids = _normalize_pinned_app_ids(value.get("pinned_app_ids"))
    if pinned_app_ids is None:
        return None
    next_value = dict(value)
    next_value["pinned_app_ids"] = pinned_app_ids
    return next_value


def _cleanup_user_app_bar_layouts() -> None:
    bind = op.get_bind()
    users = sa.table(
        "users",
        sa.column("id", sa.String(length=36)),
        sa.column("app_bar_layout", sa.JSON()),
    )
    rows = bind.execute(
        sa.select(users.c.id, users.c.app_bar_layout).where(users.c.app_bar_layout.is_not(None))
    ).all()
    for user_id, app_bar_layout in rows:
        normalized_layout = _normalize_app_bar_layout(app_bar_layout)
        if normalized_layout is None or normalized_layout == app_bar_layout:
            continue
        bind.execute(
            users.update().where(users.c.id == user_id).values(app_bar_layout=normalized_layout)
        )


def _materialize_parent_visibility() -> None:
    """Preserve parent visibility policy on the retired section's children.

    Platform restrictions remain platform restrictions so they also apply to
    future workspaces. Workspace overrides are copied only when they changed
    the parent's effective value: a false override restricts every child, while
    a true override over a false platform parent preserves each child's prior
    effective value.
    """

    bind = op.get_bind()
    legacy_section_values = ",\n                ".join(
        f"('{parent_app_id}', '{child_app_id}')"
        for parent_app_id, child_app_ids in LEGACY_SECTION_CHILD_APP_IDS.items()
        for child_app_id in child_app_ids
    )
    bind.execute(
        sa.text(
            f"""
            WITH legacy_sections(parent_app_id, child_app_id) AS (
                VALUES
                {legacy_section_values}
            ),
            parent_platform_visibility AS (
                SELECT
                    parent_app_id,
                    COALESCE(platform_visibility.visible, true) AS visible
                FROM (
                    SELECT DISTINCT parent_app_id
                    FROM legacy_sections
                ) AS parents
                LEFT JOIN platform_app_visibility AS platform_visibility
                    ON platform_visibility.app_id = parents.parent_app_id
            ),
            workspace_child_overrides AS (
                SELECT
                    parent_entitlement.workspace_id,
                    legacy_sections.child_app_id,
                    CASE
                        WHEN parent_entitlement.visibility_override IS FALSE
                            THEN false
                        ELSE COALESCE(
                            child_entitlement.visibility_override,
                            child_platform_visibility.visible,
                            true
                        )
                    END AS visibility_override
                FROM workspace_app_entitlements AS parent_entitlement
                JOIN legacy_sections
                    ON legacy_sections.parent_app_id = parent_entitlement.app_id
                JOIN parent_platform_visibility
                    ON parent_platform_visibility.parent_app_id =
                       legacy_sections.parent_app_id
                LEFT JOIN workspace_app_entitlements AS child_entitlement
                    ON child_entitlement.workspace_id = parent_entitlement.workspace_id
                   AND child_entitlement.app_id = legacy_sections.child_app_id
                LEFT JOIN platform_app_visibility AS child_platform_visibility
                    ON child_platform_visibility.app_id = legacy_sections.child_app_id
                WHERE parent_entitlement.visibility_override IS FALSE
                   OR (
                        parent_entitlement.visibility_override IS TRUE
                    AND parent_platform_visibility.visible IS FALSE
                   )
            )
            INSERT INTO workspace_app_entitlements (
                id,
                workspace_id,
                app_id,
                enabled,
                visibility_override,
                created_at,
                updated_at
            )
            SELECT
                'mig-' || md5(workspace_id || ':' || child_app_id),
                workspace_id,
                child_app_id,
                true,
                visibility_override,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM workspace_child_overrides
            ON CONFLICT (workspace_id, app_id)
            DO UPDATE SET
                visibility_override = EXCLUDED.visibility_override,
                updated_at = EXCLUDED.updated_at
            """
        )
    )
    bind.execute(
        sa.text(
            f"""
            WITH legacy_sections(parent_app_id, child_app_id) AS (
                VALUES
                {legacy_section_values}
            ),
            restricted_children AS (
                SELECT legacy_sections.child_app_id
                FROM legacy_sections
                JOIN platform_app_visibility AS parent_platform_visibility
                    ON parent_platform_visibility.app_id =
                       legacy_sections.parent_app_id
                WHERE parent_platform_visibility.visible IS FALSE
            )
            INSERT INTO platform_app_visibility (
                id,
                app_id,
                visible,
                created_at,
                updated_at
            )
            SELECT
                'mig-' || md5('platform:' || child_app_id),
                child_app_id,
                false,
                CURRENT_TIMESTAMP,
                CURRENT_TIMESTAMP
            FROM restricted_children
            ON CONFLICT (app_id)
            DO UPDATE SET
                visible = false,
                updated_at = EXCLUDED.updated_at
            """
        )
    )


def upgrade() -> None:
    bind = op.get_bind()
    stale_app_ids = tuple(sorted(STALE_CATEGORY_APP_IDS))
    _materialize_parent_visibility()
    bind.execute(
        sa.text("DELETE FROM platform_app_bar_category_apps WHERE app_id IN :app_ids").bindparams(
            sa.bindparam("app_ids", expanding=True)
        ),
        {"app_ids": stale_app_ids},
    )
    bind.execute(
        sa.text("DELETE FROM platform_app_visibility WHERE app_id IN :app_ids").bindparams(
            sa.bindparam("app_ids", expanding=True)
        ),
        {"app_ids": stale_app_ids},
    )
    bind.execute(
        sa.text("DELETE FROM workspace_app_entitlements WHERE app_id IN :app_ids").bindparams(
            sa.bindparam("app_ids", expanding=True)
        ),
        {"app_ids": stale_app_ids},
    )
    _cleanup_user_app_bar_layouts()


def downgrade() -> None:
    pass
