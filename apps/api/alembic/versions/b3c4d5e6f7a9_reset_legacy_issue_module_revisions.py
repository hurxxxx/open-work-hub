"""reset legacy issue revisions per module

Revision ID: b3c4d5e6f7a9
Revises: a2b3c4d5e6f8
Create Date: 2026-07-13 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime
import uuid

from alembic import op
import sqlalchemy as sa


revision: str = "b3c4d5e6f7a9"
down_revision: str | Sequence[str] | None = "a2b3c4d5e6f8"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


DATASET_KEY = "common-master"
LEGACY_REVISION_KEY = "legacy_issue.common-master"
MODULE_KEYS = (
    "aircon",
    "compressor-electric",
    "compressor-mechanical",
    "cooling-module",
    "electrical-control-hw",
    "electrical-control-sw",
    "electrical-mechanical",
    "interior",
)
DEPARTMENT_MODULE_KEYS = {
    "샤시(ACON)": "aircon",
    "컴프레서(전동)": "compressor-electric",
    "컴프레서(기계)": "compressor-mechanical",
    "의장(HVAC)": "interior",
    "쿨링모듈": "cooling-module",
    "전장(기구)": "electrical-mechanical",
    "전장(제어-HW)": "electrical-control-hw",
    "전장(제어-SW)": "electrical-control-sw",
}


def upgrade() -> None:
    op.create_index(
        "ix_legacy_issue_records_workspace_dataset_module_revision",
        "legacy_issue_records",
        ["workspace_id", "dataset_key", "module_key", "revision_id"],
    )
    bind = op.get_bind()
    metadata = sa.MetaData()
    revisions = sa.Table("legacy_issue_data_revisions", metadata, autoload_with=bind)
    records = sa.Table("legacy_issue_records", metadata, autoload_with=bind)
    attachments = sa.Table("legacy_issue_attachments", metadata, autoload_with=bind)
    chunks = sa.Table("legacy_issue_ai_chunks", metadata, autoload_with=bind)
    events = sa.Table("legacy_issue_data_revision_events", metadata, autoload_with=bind)
    history = sa.Table("legacy_issue_record_history", metadata, autoload_with=bind)
    checklist_revisions = sa.Table(
        "legacy_issue_vehicle_checklist_revisions",
        metadata,
        autoload_with=bind,
    )
    index_jobs = sa.Table(
        "legacy_issue_attachment_index_jobs",
        metadata,
        autoload_with=bind,
    )
    artifacts = sa.Table(
        "legacy_issue_attachment_artifacts",
        metadata,
        autoload_with=bind,
    )

    workspace_ids = sorted(
        set(
            bind.execute(
                sa.select(records.c.workspace_id).where(records.c.dataset_key == DATASET_KEY)
            ).scalars()
        )
        | set(
            bind.execute(
                sa.select(revisions.c.workspace_id).where(
                    revisions.c.dataset_key == LEGACY_REVISION_KEY
                )
            ).scalars()
        )
    )
    now = datetime.utcnow()
    new_revision_ids: set[str] = set()

    for workspace_id in workspace_ids:
        source_revision_id = bind.execute(
            sa.select(revisions.c.id)
            .where(
                revisions.c.workspace_id == workspace_id,
                revisions.c.dataset_key == LEGACY_REVISION_KEY,
                revisions.c.status == "published",
            )
            .order_by(
                revisions.c.revision_no.desc().nullslast(),
                revisions.c.published_at.desc().nullslast(),
                revisions.c.created_at.desc(),
            )
            .limit(1)
        ).scalar_one_or_none()
        current_rows = (
            list(
                bind.execute(
                    sa.select(
                        records.c.id,
                        records.c.module_key,
                        records.c.department,
                        records.c.field_values,
                        records.c.raw_fields,
                        records.c.search_text,
                    ).where(
                        records.c.workspace_id == workspace_id,
                        records.c.dataset_key == DATASET_KEY,
                        records.c.revision_id == source_revision_id,
                    )
                ).mappings()
            )
            if source_revision_id
            else []
        )
        normalized_rows: list[dict] = []
        for source_row in current_rows:
            row = dict(source_row)
            if row["module_key"] not in MODULE_KEYS:
                inferred_module_key = _infer_module_key(row)
                if inferred_module_key is not None:
                    row["module_key"] = inferred_module_key
                    bind.execute(
                        records.update()
                        .where(records.c.id == row["id"])
                        .values(module_key=inferred_module_key)
                    )
            normalized_rows.append(row)
        current_rows = normalized_rows
        invalid_rows = [
            row["id"]
            for row in current_rows
            if row["module_key"] not in MODULE_KEYS
        ]
        if invalid_rows:
            raise RuntimeError(
                "Legacy issue revision reset requires every current row to have a known "
                f"module_key; workspace={workspace_id}, invalid_rows={len(invalid_rows)}"
            )

        module_revision_ids = {
            module_key: str(uuid.uuid4()) for module_key in MODULE_KEYS
        }
        for module_key, revision_id in module_revision_ids.items():
            bind.execute(
                revisions.insert().values(
                    id=revision_id,
                    workspace_id=workspace_id,
                    dataset_key=f"{LEGACY_REVISION_KEY}.{module_key}",
                    revision_no=1,
                    status="published",
                    created_at=now,
                    updated_at=now,
                    published_at=now,
                )
            )
            new_revision_ids.add(revision_id)

        for row in current_rows:
            field_values = dict(row["field_values"] or {})
            field_values["introduced_revision_no"] = "1"
            bind.execute(
                records.update()
                .where(records.c.id == row["id"])
                .values(
                    revision_id=module_revision_ids[row["module_key"]],
                    introduced_revision_no=1,
                    field_values=field_values,
                    search_text=_reset_search_revision(row["search_text"]),
                )
            )

        current_record_ids = [row["id"] for row in current_rows]
        obsolete_records = sa.delete(records).where(
            records.c.workspace_id == workspace_id,
            records.c.dataset_key == DATASET_KEY,
        )
        if current_record_ids:
            obsolete_records = obsolete_records.where(
                records.c.id.not_in(current_record_ids)
            )
        bind.execute(obsolete_records)

        for module_key, revision_id in module_revision_ids.items():
            module_record_ids = sa.select(records.c.id).where(
                records.c.workspace_id == workspace_id,
                records.c.dataset_key == DATASET_KEY,
                records.c.module_key == module_key,
                records.c.revision_id == revision_id,
            )
            bind.execute(
                attachments.update()
                .where(attachments.c.record_id.in_(module_record_ids))
                .values(revision_id=revision_id)
            )
            bind.execute(
                chunks.update()
                .where(chunks.c.record_id.in_(module_record_ids))
                .values(revision_id=revision_id)
            )
            bind.execute(
                index_jobs.update()
                .where(index_jobs.c.attachment_id.in_(
                    sa.select(attachments.c.id).where(
                        attachments.c.record_id.in_(module_record_ids)
                    )
                ))
                .values(revision_id=revision_id)
            )
            bind.execute(
                artifacts.update()
                .where(artifacts.c.record_id.in_(module_record_ids))
                .values(revision_id=revision_id)
            )

    bind.execute(sa.delete(events))
    bind.execute(sa.delete(history).where(history.c.dataset_key == DATASET_KEY))
    bind.execute(revisions.update().values(base_revision_id=None))

    referenced_revision_ids = set(
        bind.execute(sa.select(checklist_revisions.c.source_master_revision_id)).scalars()
    )
    old_revision_ids = set(
        bind.execute(
            sa.select(revisions.c.id).where(
                revisions.c.dataset_key.like(f"{LEGACY_REVISION_KEY}%")
            )
        ).scalars()
    ) - new_revision_ids
    archived_revision_ids = old_revision_ids & referenced_revision_ids
    deletable_revision_ids = old_revision_ids - referenced_revision_ids
    if archived_revision_ids:
        for archived_id in archived_revision_ids:
            bind.execute(
                revisions.update()
                .where(revisions.c.id == archived_id)
                .values(
                    dataset_key=f"legacy_issue.archived.{archived_id}",
                    revision_no=None,
                    status="canceled",
                    updated_at=now,
                )
            )
    if deletable_revision_ids:
        bind.execute(
            sa.delete(revisions).where(revisions.c.id.in_(deletable_revision_ids))
        )

    for workspace_id in workspace_ids:
        bind.execute(
            revisions.insert().values(
                id=str(uuid.uuid4()),
                workspace_id=workspace_id,
                dataset_key=LEGACY_REVISION_KEY,
                revision_no=1,
                status="published",
                created_at=now,
                updated_at=now,
                published_at=now,
            )
        )


def downgrade() -> None:
    raise RuntimeError(
        "b3c4d5e6f7a9 is intentionally irreversible: it deletes legacy issue "
        "revision snapshots and edit history. Restore from a database backup instead."
    )


def _reset_search_revision(value: str | None) -> str | None:
    if not value:
        return value
    lines = value.splitlines()
    replaced = False
    for index, line in enumerate(lines):
        if line.startswith("리비전:") or line.startswith("Revision:"):
            label = line.split(":", 1)[0]
            lines[index] = f"{label}: 1"
            replaced = True
    if not replaced:
        lines.insert(0, "리비전: 1")
    return "\n".join(lines)


def _infer_module_key(row: dict) -> str | None:
    field_values = dict(row.get("field_values") or {})
    raw_fields = dict(row.get("raw_fields") or {})
    for label in (
        row.get("department"),
        field_values.get("department"),
        raw_fields.get("부서"),
    ):
        normalized = " ".join(str(label or "").split())
        if normalized in DEPARTMENT_MODULE_KEYS:
            return DEPARTMENT_MODULE_KEYS[normalized]
    return None
