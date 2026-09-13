"""Unify organization metadata and group principals without replacing group grants.

Revision ID: group_sources_20260912
Revises: company_20260908
"""

from alembic import op
import sqlalchemy as sa

revision = "group_sources_20260912"
down_revision = "company_20260908"
branch_labels = None
depends_on = None


def _drop_foreign_keys(table: str, column: str) -> None:
    for fk in sa.inspect(op.get_bind()).get_foreign_keys(table):
        if fk["constrained_columns"] == [column]:
            op.drop_constraint(fk["name"], table, type_="foreignkey")


def upgrade() -> None:
    op.add_column("groups", sa.Column("source", sa.String(24), nullable=True))
    for name, length in (("slug", 80), ("unit_type", 40), ("source_reference", 120)):
        op.add_column("groups", sa.Column(name, sa.String(length), nullable=True))
    op.add_column("groups", sa.Column("parent_id", sa.String(36), nullable=True))
    op.add_column("groups", sa.Column("head_user_id", sa.String(36), nullable=True))
    # Cover valid old directories created before their group was materialized.
    op.execute(
        sa.text("""
        INSERT INTO groups (id, kind, organization_unit_id, name, description, active, created_at, updated_at)
        SELECT gen_random_uuid()::text, 'organization', o.id, '', '', true, o.created_at, o.updated_at
        FROM organization_units o WHERE NOT EXISTS (
            SELECT 1 FROM groups g WHERE g.organization_unit_id = o.id
        )
    """)
    )
    op.execute(sa.text("UPDATE groups SET source = 'local' WHERE kind = 'manual'"))
    op.execute(
        sa.text("""
        UPDATE groups g SET source = 'hr', source_reference = o.id, name = o.name,
            slug = o.slug, unit_type = o.unit_type, head_user_id = o.head_user_id,
            active = g.active AND o.active, created_at = LEAST(g.created_at, o.created_at),
            updated_at = GREATEST(g.updated_at, o.updated_at),
            parent_id = (SELECT p.id FROM groups p WHERE p.organization_unit_id = o.parent_id)
        FROM organization_units o WHERE g.organization_unit_id = o.id
    """)
    )
    _drop_foreign_keys("users", "primary_organization_unit_id")
    op.execute(
        sa.text("""
        UPDATE users u SET primary_organization_unit_id = g.id
        FROM groups g WHERE u.primary_organization_unit_id = g.organization_unit_id
    """)
    )
    op.create_foreign_key(
        "fk_users_primary_group",
        "users",
        "groups",
        ["primary_organization_unit_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.drop_constraint("ck_groups_origin", "groups", type_="check")
    _drop_foreign_keys("groups", "organization_unit_id")
    op.drop_column("groups", "organization_unit_id")
    op.drop_column("groups", "kind")
    op.drop_table("organization_units")
    op.alter_column("groups", "source", nullable=False)
    op.create_check_constraint("ck_groups_source", "groups", "source IN ('hr', 'local')")
    op.create_check_constraint("ck_groups_name", "groups", "length(trim(name)) > 0")
    op.create_check_constraint(
        "ck_groups_hr_metadata",
        "groups",
        "source != 'hr' OR (slug IS NOT NULL AND unit_type IS NOT NULL)",
    )
    op.create_unique_constraint("uq_groups_slug", "groups", ["slug"])
    op.create_unique_constraint(
        "uq_groups_source_reference", "groups", ["source", "source_reference"]
    )
    op.create_foreign_key(
        "fk_groups_parent", "groups", "groups", ["parent_id"], ["id"], ondelete="SET NULL"
    )
    op.create_foreign_key(
        "fk_group_head_user", "groups", "users", ["head_user_id"], ["id"], ondelete="SET NULL"
    )
    for column in ("source", "name", "parent_id", "head_user_id"):
        op.create_index(f"ix_groups_{column}", "groups", [column])


def downgrade() -> None:
    # Reconstruct the prior directory while preserving every group ID and grant.
    op.create_table(
        "organization_units",
        sa.Column("id", sa.String(36), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("slug", sa.String(80), nullable=False),
        sa.Column("unit_type", sa.String(40), nullable=False),
        sa.Column("parent_id", sa.String(36), nullable=True),
        sa.Column("head_user_id", sa.String(36), nullable=True),
        sa.Column("active", sa.Boolean(), nullable=False),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.CheckConstraint("length(trim(name)) > 0", name="ck_organization_units_name"),
        sa.CheckConstraint("length(trim(unit_type)) > 0", name="ck_organization_units_type"),
        sa.ForeignKeyConstraint(["parent_id"], ["organization_units.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["head_user_id"],
            ["users.id"],
            name="fk_organization_unit_head_user",
            ondelete="SET NULL",
        ),
    )
    op.add_column("groups", sa.Column("organization_unit_id", sa.String(36), nullable=True))
    op.add_column("groups", sa.Column("kind", sa.String(24), nullable=True))
    # Imported reference keys are arbitrary; only restore the original UUID-sized IDs.
    op.execute(
        sa.text("""
        UPDATE groups SET kind = CASE WHEN source = 'hr' THEN 'organization' ELSE 'manual' END,
            organization_unit_id = CASE WHEN source = 'hr' THEN
                CASE WHEN source_reference IS NOT NULL AND length(source_reference) <= 36
                     THEN source_reference ELSE id END ELSE NULL END
    """)
    )
    op.execute(
        sa.text("""
        INSERT INTO organization_units (id, name, slug, unit_type, parent_id, head_user_id, active, created_at, updated_at)
        SELECT g.organization_unit_id, g.name, g.slug, g.unit_type, p.organization_unit_id,
               g.head_user_id, g.active, g.created_at, g.updated_at
        FROM groups g LEFT JOIN groups p ON p.id = g.parent_id WHERE g.source = 'hr'
    """)
    )
    _drop_foreign_keys("users", "primary_organization_unit_id")
    op.execute(
        sa.text("""
        UPDATE users u SET primary_organization_unit_id = g.organization_unit_id
        FROM groups g WHERE u.primary_organization_unit_id = g.id
    """)
    )
    op.create_foreign_key(
        "users_primary_organization_unit_id_fkey",
        "users",
        "organization_units",
        ["primary_organization_unit_id"],
        ["id"],
        ondelete="SET NULL",
    )
    op.create_foreign_key(
        "groups_organization_unit_id_fkey",
        "groups",
        "organization_units",
        ["organization_unit_id"],
        ["id"],
        ondelete="CASCADE",
    )
    op.create_unique_constraint(
        "groups_organization_unit_id_key", "groups", ["organization_unit_id"]
    )
    op.alter_column("groups", "kind", nullable=False)
    op.create_check_constraint(
        "ck_groups_origin",
        "groups",
        "(kind = 'organization' AND organization_unit_id IS NOT NULL) OR "
        "(kind = 'manual' AND organization_unit_id IS NULL AND length(trim(name)) > 0)",
    )
    for column in ("active", "head_user_id", "name", "parent_id", "unit_type", "slug"):
        op.create_index(
            f"ix_organization_units_{column}",
            "organization_units",
            [column],
            unique=column == "slug",
        )
    for name in ("ck_groups_source", "ck_groups_name", "ck_groups_hr_metadata"):
        op.drop_constraint(name, "groups", type_="check")
    op.drop_constraint("uq_groups_source_reference", "groups", type_="unique")
    op.drop_constraint("uq_groups_slug", "groups", type_="unique")
    for column in ("parent_id", "head_user_id"):
        _drop_foreign_keys("groups", column)
    for column in ("source", "name", "parent_id", "head_user_id"):
        op.drop_index(f"ix_groups_{column}", table_name="groups")
    for column in ("source", "source_reference", "slug", "unit_type", "parent_id", "head_user_id"):
        op.drop_column("groups", column)
