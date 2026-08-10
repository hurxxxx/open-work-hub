"""remove undecided legacy issue compressor modules

Revision ID: c7f8e9d0a1b2
Revises: b3c4d5e6f7a9
Create Date: 2026-07-13 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "c7f8e9d0a1b2"
down_revision: str | Sequence[str] | None = "b3c4d5e6f7a9"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


COMPRESSOR_MODULE_KEYS = (
    "compressor-electric",
    "compressor-mechanical",
)
COMPRESSOR_REVISION_KEYS = tuple(
    f"legacy_issue.common-master.{module_key}"
    for module_key in COMPRESSOR_MODULE_KEYS
)


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    records = sa.Table("legacy_issue_records", metadata, autoload_with=bind)
    revisions = sa.Table(
        "legacy_issue_data_revisions",
        metadata,
        autoload_with=bind,
    )
    revision_events = sa.Table(
        "legacy_issue_data_revision_events",
        metadata,
        autoload_with=bind,
    )
    module_fields = sa.Table(
        "legacy_issue_module_fields",
        metadata,
        autoload_with=bind,
    )
    module_access_rules = sa.Table(
        "legacy_issue_module_access_rules",
        metadata,
        autoload_with=bind,
    )
    column_orders = sa.Table(
        "legacy_issue_column_orders",
        metadata,
        autoload_with=bind,
    )
    checklist_revisions = sa.Table(
        "legacy_issue_vehicle_checklist_revisions",
        metadata,
        autoload_with=bind,
    )

    record_count = bind.scalar(
        sa.select(sa.func.count())
        .select_from(records)
        .where(records.c.module_key.in_(COMPRESSOR_MODULE_KEYS))
    )
    if record_count:
        raise RuntimeError(
            "Refusing to remove legacy issue compressor modules because records "
            f"exist; export or reclassify them first (records={record_count})."
        )

    revision_ids = set(
        bind.execute(
            sa.select(revisions.c.id).where(
                revisions.c.dataset_key.in_(COMPRESSOR_REVISION_KEYS)
            )
        ).scalars()
    )
    if revision_ids:
        dependent_revision_count = bind.scalar(
            sa.select(sa.func.count())
            .select_from(revisions)
            .where(revisions.c.base_revision_id.in_(revision_ids))
        )
        checklist_reference_count = bind.scalar(
            sa.select(sa.func.count())
            .select_from(checklist_revisions)
            .where(checklist_revisions.c.source_master_revision_id.in_(revision_ids))
        )
        if dependent_revision_count or checklist_reference_count:
            raise RuntimeError(
                "Refusing to remove legacy issue compressor revisions while they "
                "are referenced by another revision or vehicle checklist."
            )

    for row in bind.execute(
        sa.select(
            checklist_revisions.c.id,
            checklist_revisions.c.definition_snapshot,
        )
    ).mappings():
        snapshot = dict(row["definition_snapshot"] or {})
        source_revisions = snapshot.get("source_module_revisions")
        if not isinstance(source_revisions, dict):
            continue
        cleaned_source_revisions = dict(source_revisions)
        for module_key in COMPRESSOR_MODULE_KEYS:
            cleaned_source_revisions.pop(module_key, None)
        if cleaned_source_revisions == source_revisions:
            continue
        snapshot["source_module_revisions"] = cleaned_source_revisions
        bind.execute(
            checklist_revisions.update()
            .where(checklist_revisions.c.id == row["id"])
            .values(definition_snapshot=snapshot)
        )

    bind.execute(
        sa.delete(module_access_rules).where(
            module_access_rules.c.module_key.in_(COMPRESSOR_MODULE_KEYS)
        )
    )
    bind.execute(
        sa.delete(module_fields).where(
            module_fields.c.module_key.in_(COMPRESSOR_MODULE_KEYS)
        )
    )
    bind.execute(
        sa.delete(column_orders).where(
            column_orders.c.view_key.in_(COMPRESSOR_MODULE_KEYS)
        )
    )
    if revision_ids:
        bind.execute(
            sa.delete(revision_events).where(
                revision_events.c.revision_id.in_(revision_ids)
            )
        )
        bind.execute(
            sa.delete(revisions).where(revisions.c.id.in_(revision_ids))
        )


def downgrade() -> None:
    raise RuntimeError(
        "c7f8e9d0a1b2 intentionally removes undecided compressor module state; "
        "restore from a database backup instead of recreating it implicitly."
    )
