"""remove_access_groups

Revision ID: d2f3a4b5c6d7
Revises: c6a0b7d8e9f1
Create Date: 2026-05-07 00:00:00.000000

"""

from typing import Sequence, Union

from alembic import op
import sqlalchemy as sa


revision: str = "d2f3a4b5c6d7"
down_revision: Union[str, Sequence[str], None] = "c6a0b7d8e9f1"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


UUID_SQL = """
concat(
    substr(md5(random()::text || clock_timestamp()::text), 1, 8), '-',
    substr(md5(random()::text || clock_timestamp()::text), 1, 4), '-',
    substr(md5(random()::text || clock_timestamp()::text), 1, 4), '-',
    substr(md5(random()::text || clock_timestamp()::text), 1, 4), '-',
    substr(md5(random()::text || clock_timestamp()::text), 1, 12)
)
"""

PLATFORM_ADMIN_ROLE_ALIASES_SQL = """
(
    'platform_admin',
    'platform-admin',
    'org_admin',
    'org-admin',
    'people_admin',
    'people-admin',
    'workspace_admin',
    'workspace-admin',
    'audit_viewer',
    'audit-viewer'
)
"""

PLATFORM_ADMIN_LEGACY_SLUGS_SQL = """
(
    'platform-admin',
    'org-admin',
    'people-admin',
    'workspace-admin',
    'audit-viewer'
)
"""

PLATFORM_ADMIN_PERMISSION_VALUES_SQL = """
(
    'admin.access',
    'user.read',
    'user.write',
    'group.read',
    'group.write',
    'org_unit.read',
    'org_unit.write',
    'workspace.read',
    'workspace.write',
    'team.read',
    'team.write',
    'audit.read',
    'session.revoke'
)
"""


def upgrade() -> None:
    op.execute(
        f"""
        WITH group_platform_admin_users AS (
            SELECT DISTINCT uag.user_id
            FROM user_access_groups AS uag
            JOIN access_groups AS ag ON ag.id = uag.group_id
            WHERE ag.active IS TRUE
              AND (
                  lower(ag.slug) IN {PLATFORM_ADMIN_LEGACY_SLUGS_SQL}
                  OR EXISTS (
                      SELECT 1
                      FROM group_system_roles AS gsr
                      WHERE gsr.group_id = ag.id
                        AND lower(gsr.role) IN {PLATFORM_ADMIN_ROLE_ALIASES_SQL}
                  )
                  OR EXISTS (
                      SELECT 1
                      FROM jsonb_array_elements_text(
                          CASE
                              WHEN jsonb_typeof(coalesce(ag.permissions, '[]'::json)::jsonb) = 'array'
                              THEN coalesce(ag.permissions, '[]'::json)::jsonb
                              ELSE '[]'::jsonb
                          END
                      ) AS permission(value)
                      WHERE lower(permission.value) IN {PLATFORM_ADMIN_PERMISSION_VALUES_SQL}
                  )
              )
        )
        INSERT INTO user_system_roles (id, user_id, role, created_at)
        SELECT {UUID_SQL}, user_id, 'platform_admin', now()
        FROM group_platform_admin_users AS grants
        WHERE NOT EXISTS (
            SELECT 1
            FROM user_system_roles AS usr
            WHERE usr.user_id = grants.user_id
              AND lower(usr.role) IN {PLATFORM_ADMIN_ROLE_ALIASES_SQL}
        )
          AND NOT EXISTS (
              SELECT 1
              FROM user_system_roles AS usr
              WHERE usr.user_id = grants.user_id
                AND usr.role = 'platform_admin'
          )
        """
    )
    op.execute(
        f"""
        WITH group_workspace_roles AS (
            SELECT
                wgb.workspace_id,
                uag.user_id,
                CASE
                    WHEN bool_or(lower(wgb.role) IN ('admin', 'owner')) THEN 'admin'
                    ELSE 'member'
                END AS role
            FROM workspace_group_bindings AS wgb
            JOIN access_groups AS ag ON ag.id = wgb.group_id
            JOIN user_access_groups AS uag ON uag.group_id = ag.id
            WHERE ag.active IS TRUE
            GROUP BY wgb.workspace_id, uag.user_id
        )
        INSERT INTO workspace_user_bindings (id, workspace_id, user_id, role, created_at)
        SELECT {UUID_SQL}, gwr.workspace_id, gwr.user_id, gwr.role, now()
        FROM group_workspace_roles AS gwr
        WHERE NOT EXISTS (
            SELECT 1
            FROM workspace_user_bindings AS wub
            WHERE wub.workspace_id = gwr.workspace_id
              AND wub.user_id = gwr.user_id
        )
        """
    )
    op.execute(
        """
        WITH group_workspace_roles AS (
            SELECT
                wgb.workspace_id,
                uag.user_id,
                CASE
                    WHEN bool_or(lower(wgb.role) IN ('admin', 'owner')) THEN 'admin'
                    ELSE 'member'
                END AS role
            FROM workspace_group_bindings AS wgb
            JOIN access_groups AS ag ON ag.id = wgb.group_id
            JOIN user_access_groups AS uag ON uag.group_id = ag.id
            WHERE ag.active IS TRUE
            GROUP BY wgb.workspace_id, uag.user_id
        )
        UPDATE workspace_user_bindings AS wub
        SET role = 'admin'
        FROM group_workspace_roles AS gwr
        WHERE wub.workspace_id = gwr.workspace_id
          AND wub.user_id = gwr.user_id
          AND gwr.role = 'admin'
          AND wub.role <> 'admin'
        """
    )

    op.drop_table("workspace_group_bindings")
    op.drop_table("group_system_roles")
    op.drop_table("user_access_groups")
    op.drop_table("access_groups")


def downgrade() -> None:
    op.create_table(
        "access_groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("name", sa.String(length=120), nullable=False),
        sa.Column("slug", sa.String(length=80), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("group_kind", sa.String(length=24), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=True),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("slug"),
    )
    op.create_index(op.f("ix_access_groups_active"), "access_groups", ["active"], unique=False)
    op.create_index(op.f("ix_access_groups_group_kind"), "access_groups", ["group_kind"], unique=False)
    op.create_index(op.f("ix_access_groups_name"), "access_groups", ["name"], unique=False)
    op.create_index(op.f("ix_access_groups_slug"), "access_groups", ["slug"], unique=True)

    op.create_table(
        "user_access_groups",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("user_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["access_groups.id"]),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("user_id", "group_id", name="uq_user_access_group"),
    )
    op.create_index(op.f("ix_user_access_groups_group_id"), "user_access_groups", ["group_id"], unique=False)
    op.create_index(op.f("ix_user_access_groups_user_id"), "user_access_groups", ["user_id"], unique=False)

    op.create_table(
        "group_system_roles",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=40), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["access_groups.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("group_id", "role", name="uq_group_system_role"),
    )
    op.create_index(op.f("ix_group_system_roles_group_id"), "group_system_roles", ["group_id"], unique=False)
    op.create_index(op.f("ix_group_system_roles_role"), "group_system_roles", ["role"], unique=False)

    op.create_table(
        "workspace_group_bindings",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("workspace_id", sa.String(length=36), nullable=False),
        sa.Column("group_id", sa.String(length=36), nullable=False),
        sa.Column("role", sa.String(length=24), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["group_id"], ["access_groups.id"]),
        sa.ForeignKeyConstraint(["workspace_id"], ["workspaces.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("workspace_id", "group_id", name="uq_workspace_group"),
    )
    op.create_index(op.f("ix_workspace_group_bindings_group_id"), "workspace_group_bindings", ["group_id"], unique=False)
    op.create_index(op.f("ix_workspace_group_bindings_role"), "workspace_group_bindings", ["role"], unique=False)
    op.create_index(op.f("ix_workspace_group_bindings_workspace_id"), "workspace_group_bindings", ["workspace_id"], unique=False)
