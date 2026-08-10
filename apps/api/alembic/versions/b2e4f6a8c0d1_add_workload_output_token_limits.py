"""add workload output token limits and split legacy batch settings

Revision ID: b2e4f6a8c0d1
Revises: e7a1c3d5f9b2
Create Date: 2026-07-11 10:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

import sqlalchemy as sa
from alembic import op


revision: str = "b2e4f6a8c0d1"
down_revision: str | Sequence[str] | None = "e7a1c3d5f9b2"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


NEW_WORKLOAD_IDS = (
    "spec_compare.extract",
    "spec_compare.compare",
    "spec_compare.report",
    "patent_automation.invoice_extract",
)
NEW_TASK_KINDS = (
    "spec_compare_extract",
    "spec_compare_compare",
    "spec_compare_report",
    "patent_invoice_extract",
)


def upgrade() -> None:
    op.add_column(
        "ai_model_route_overrides",
        sa.Column("local_max_output_tokens", sa.Integer(), nullable=True),
    )
    op.add_column(
        "ai_model_route_overrides",
        sa.Column("external_max_output_tokens", sa.Integer(), nullable=True),
    )
    op.create_check_constraint(
        "ck_ai_model_route_overrides_local_max_output_tokens",
        "ai_model_route_overrides",
        "local_max_output_tokens IS NULL OR "
        "(local_max_output_tokens BETWEEN 1024 AND 65536 "
        "AND local_max_output_tokens % 1024 = 0)",
    )
    op.create_check_constraint(
        "ck_ai_model_route_overrides_external_max_output_tokens",
        "ai_model_route_overrides",
        "external_max_output_tokens IS NULL OR "
        "(external_max_output_tokens BETWEEN 1024 AND 65536 "
        "AND external_max_output_tokens % 1024 = 0)",
    )

    bind = op.get_bind()
    metadata = sa.MetaData()
    route_overrides = sa.Table("ai_model_route_overrides", metadata, autoload_with=bind)
    llm_policies = sa.Table("llm_policies", metadata, autoload_with=bind)
    policy_rules = sa.Table("ai_security_policy_rules", metadata, autoload_with=bind)
    transfer_exceptions = sa.Table(
        "ai_security_external_transfer_exceptions",
        metadata,
        autoload_with=bind,
    )

    _clone_route_override(bind, route_overrides)
    _clone_llm_policy(bind, llm_policies)
    _expand_security_task_scopes(bind, policy_rules)
    _expand_security_task_scopes(bind, transfer_exceptions)


def downgrade() -> None:
    # The legacy batch scope is deliberately not recreated: after upgrade the
    # four feature-specific settings can diverge and cannot be merged without
    # silently discarding administrator choices.
    op.drop_constraint(
        "ck_ai_model_route_overrides_external_max_output_tokens",
        "ai_model_route_overrides",
        type_="check",
    )
    op.drop_constraint(
        "ck_ai_model_route_overrides_local_max_output_tokens",
        "ai_model_route_overrides",
        type_="check",
    )
    op.drop_column("ai_model_route_overrides", "external_max_output_tokens")
    op.drop_column("ai_model_route_overrides", "local_max_output_tokens")


def _clone_route_override(bind: sa.Connection, table: sa.Table) -> None:
    legacy = bind.execute(
        sa.select(table).where(table.c.workload_id == "batch_generation")
    ).mappings().one_or_none()
    if legacy is None:
        return
    existing = set(
        bind.execute(
            sa.select(table.c.workload_id).where(table.c.workload_id.in_(NEW_WORKLOAD_IDS))
        ).scalars()
    )
    for workload_id in NEW_WORKLOAD_IDS:
        if workload_id in existing:
            continue
        values = dict(legacy)
        values.update(id=str(uuid4()), workload_id=workload_id)
        bind.execute(sa.insert(table).values(**values))
    bind.execute(sa.delete(table).where(table.c.workload_id == "batch_generation"))


def _clone_llm_policy(bind: sa.Connection, table: sa.Table) -> None:
    legacy = bind.execute(
        sa.select(table).where(table.c.task_kind == "batch_generation")
    ).mappings().one_or_none()
    if legacy is None:
        return
    existing = set(
        bind.execute(
            sa.select(table.c.task_kind).where(table.c.task_kind.in_(NEW_TASK_KINDS))
        ).scalars()
    )
    for task_kind in NEW_TASK_KINDS:
        if task_kind in existing:
            continue
        values = dict(legacy)
        values.update(id=str(uuid4()), task_kind=task_kind)
        bind.execute(sa.insert(table).values(**values))
    bind.execute(sa.delete(table).where(table.c.task_kind == "batch_generation"))


def _expand_security_task_scopes(bind: sa.Connection, table: sa.Table) -> None:
    rows = bind.execute(
        sa.select(table.c.id, table.c.task_kind, table.c.task_kinds_json)
    ).mappings()
    for row in rows:
        raw_task_kinds = row["task_kinds_json"]
        task_kinds = (
            [str(value) for value in raw_task_kinds if isinstance(value, str)]
            if isinstance(raw_task_kinds, list)
            else []
        )
        scalar_is_legacy = row["task_kind"] == "batch_generation"
        list_has_legacy = "batch_generation" in task_kinds
        if not scalar_is_legacy and not list_has_legacy:
            continue
        expanded = [value for value in task_kinds if value != "batch_generation"]
        if scalar_is_legacy or list_has_legacy:
            expanded.extend(NEW_TASK_KINDS)
        normalized = list(dict.fromkeys(expanded))
        bind.execute(
            sa.update(table)
            .where(table.c.id == row["id"])
            .values(
                task_kind=normalized[0] if len(normalized) == 1 else None,
                task_kinds_json=normalized,
            )
        )
