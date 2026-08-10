"""unify LLM routing and external security policy

Revision ID: c3f5a7b9d1e2
Revises: b2e4f6a8c0d1
Create Date: 2026-07-11 00:00:00.000000

"""

from __future__ import annotations

from collections.abc import Sequence
from uuid import uuid4

from alembic import op
import sqlalchemy as sa


revision: str = "c3f5a7b9d1e2"
down_revision: str | Sequence[str] | None = "b2e4f6a8c0d1"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Frozen migration data. Runtime registry imports are deliberately forbidden in
# Alembic revisions because future registrations must not change old upgrades.
_TASK_WORKLOAD_ROUTES: dict[str, tuple[str, frozenset[str]]] = {
    "chatbot": ("chatbot", frozenset({"local", "external"})),
    "document_translate": ("document_translate", frozenset({"local", "external"})),
    "draft_assist": ("draft_assist", frozenset({"local", "external"})),
    "fmea_compare": ("fmea_compare", frozenset({"local", "external"})),
    "legacy_issue_assistant": (
        "legacy_issue_assistant",
        frozenset({"local", "external"}),
    ),
    "legacy_issue_attachment_summary": (
        "legacy_issue_attachment_summary",
        frozenset({"local", "external"}),
    ),
    "legacy_issue_attachment_vision": (
        "legacy_issues.attachment_vision",
        frozenset({"local"}),
    ),
    "mail_compose": ("mail_compose", frozenset({"local", "external"})),
    "mail_reply_draft": ("mail_reply_draft", frozenset({"local", "external"})),
    "mail_summarize": ("mail_summarize", frozenset({"local", "external"})),
    "mail_thread_brief": ("mail_thread_brief", frozenset({"local", "external"})),
    "meal_invoice_ocr_extract": (
        "meal_invoice_ocr_extract",
        frozenset({"local", "external"}),
    ),
    "meeting_insight_actions": (
        "meeting_insight_actions",
        frozenset({"local", "external"}),
    ),
    "meeting_insight_decisions": (
        "meeting_insight_decisions",
        frozenset({"local", "external"}),
    ),
    "meeting_insight_followup": (
        "meeting_insight_followup",
        frozenset({"local", "external"}),
    ),
    "meeting_summary": ("meeting_summary", frozenset({"local", "external"})),
    "news_curate": ("news_curate", frozenset({"local", "external"})),
    "patent_analysis": ("patent_analysis", frozenset({"local", "external"})),
    "patent_invoice_extract": (
        "patent_automation.invoice_extract",
        frozenset({"local", "external"}),
    ),
    "ppt_design": ("ppt.design", frozenset({"local", "external"})),
    "ppt_generate": ("ppt_generate", frozenset({"local", "external"})),
    "ppt_research": ("ppt.research", frozenset({"local", "external"})),
    "rag_grounded_answer": (
        "rag_grounded_answer",
        frozenset({"local", "external"}),
    ),
    "research_trends_answer": (
        "research_trends.answer",
        frozenset({"local", "external"}),
    ),
    "spec_compare_compare": (
        "spec_compare.compare",
        frozenset({"local", "external"}),
    ),
    "spec_compare_extract": (
        "spec_compare.extract",
        frozenset({"local", "external"}),
    ),
    "spec_compare_report": (
        "spec_compare.report",
        frozenset({"local", "external"}),
    ),
    "standards_monitor_answer": (
        "standards_monitor.answer",
        frozenset({"local", "external"}),
    ),
    "web_search_answer": ("web_search.answer", frozenset({"local", "external"})),
    "writing_translate": ("writing_translate", frozenset({"local", "external"})),
}


def upgrade() -> None:
    bind = op.get_bind()
    metadata = sa.MetaData()
    policies = sa.Table("llm_policies", metadata, autoload_with=bind)
    overrides = sa.Table("ai_model_route_overrides", metadata, autoload_with=bind)
    rules = sa.Table("ai_security_policy_rules", metadata, autoload_with=bind)
    settings = sa.Table(
        "ai_security_data_protection_settings",
        metadata,
        autoload_with=bind,
    )
    exceptions = sa.Table(
        "ai_security_external_transfer_exceptions",
        metadata,
        autoload_with=bind,
    )

    _migrate_task_routes(bind, policies, overrides)
    op.drop_constraint(
        "ck_ai_security_policy_rules_effect",
        "ai_security_policy_rules",
        type_="check",
    )
    _migrate_rule_effects(bind, rules)
    op.create_check_constraint(
        "ck_ai_security_policy_rules_effect",
        "ai_security_policy_rules",
        "effect IN ('inherit', 'block_external', 'mask_and_send', 'audit_only')",
    )
    _migrate_blocker_actions(bind, settings)
    _migrate_exception_blockers(
        bind, exceptions, old="policy_local_only", new="policy_block_external"
    )

    op.drop_index(op.f("ix_llm_policies_task_kind"), table_name="llm_policies")
    op.drop_table("llm_policies")


def downgrade() -> None:
    op.create_table(
        "llm_policies",
        sa.Column("id", sa.String(length=36), nullable=False),
        sa.Column("task_kind", sa.String(length=64), nullable=False),
        sa.Column("policy_mode", sa.String(length=32), nullable=False),
        sa.Column("description", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(length=36), nullable=True),
        sa.Column("created_at", sa.DateTime(), nullable=False),
        sa.Column("updated_at", sa.DateTime(), nullable=False),
        sa.ForeignKeyConstraint(["updated_by"], ["users.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index(
        op.f("ix_llm_policies_task_kind"),
        "llm_policies",
        ["task_kind"],
        unique=True,
    )

    bind = op.get_bind()
    metadata = sa.MetaData()
    policies = sa.Table("llm_policies", metadata, autoload_with=bind)
    overrides = sa.Table("ai_model_route_overrides", metadata, autoload_with=bind)
    rules = sa.Table("ai_security_policy_rules", metadata, autoload_with=bind)
    settings = sa.Table(
        "ai_security_data_protection_settings",
        metadata,
        autoload_with=bind,
    )
    exceptions = sa.Table(
        "ai_security_external_transfer_exceptions",
        metadata,
        autoload_with=bind,
    )

    _restore_task_policies(bind, policies, overrides)
    op.drop_constraint(
        "ck_ai_security_policy_rules_effect",
        "ai_security_policy_rules",
        type_="check",
    )
    bind.execute(
        sa.update(rules).where(rules.c.effect == "block_external").values(effect="local_only")
    )
    op.create_check_constraint(
        "ck_ai_security_policy_rules_effect",
        "ai_security_policy_rules",
        "effect IN ('inherit', 'local_only', 'mask_and_send', "
        "'external_allowed', 'deny', 'audit_only')",
    )
    _replace_json_values(bind, settings, settings.c.blocker_actions_json, "block", "local_only")
    _migrate_exception_blockers(
        bind, exceptions, old="policy_block_external", new="policy_local_only"
    )


def _migrate_task_routes(
    bind: sa.Connection,
    policies: sa.Table,
    overrides: sa.Table,
) -> None:
    existing = set(bind.execute(sa.select(overrides.c.workload_id)).scalars())
    rows = bind.execute(sa.select(policies)).mappings()
    for row in rows:
        mapping = _TASK_WORKLOAD_ROUTES.get(str(row["task_kind"]))
        route = "external" if row["policy_mode"] == "external" else "local"
        if mapping is None:
            continue
        workload_id, allowed_routes = mapping
        if workload_id in existing or route not in allowed_routes:
            continue
        bind.execute(
            sa.insert(overrides).values(
                id=str(uuid4()),
                workload_id=workload_id,
                route_mode=route,
                provider_id="anthropic" if route == "external" else "local",
                model_ids_json={},
                local_max_output_tokens=None,
                external_max_output_tokens=None,
                version=1,
                updated_by=row["updated_by"],
                created_at=row["created_at"],
                updated_at=row["updated_at"],
            )
        )
        existing.add(workload_id)


def _migrate_rule_effects(bind: sa.Connection, rules: sa.Table) -> None:
    bind.execute(
        sa.update(rules)
        .where(rules.c.effect.in_(("local_only", "deny")))
        .values(effect="block_external")
    )
    bind.execute(
        sa.update(rules)
        .where(rules.c.effect == "external_allowed")
        .values(effect="inherit", enabled=False)
    )


def _migrate_blocker_actions(
    bind: sa.Connection,
    settings: sa.Table,
) -> None:
    _replace_json_values(
        bind,
        settings,
        settings.c.blocker_actions_json,
        "local_only",
        "block",
    )


def _replace_json_values(
    bind: sa.Connection,
    table: sa.Table,
    column: sa.Column,
    old: str,
    new: str,
) -> None:
    for row in bind.execute(sa.select(table.c.id, column)).mappings():
        value = row[column.name]
        if not isinstance(value, dict):
            continue
        migrated = {key: new if item == old else item for key, item in value.items()}
        if migrated != value:
            bind.execute(
                sa.update(table).where(table.c.id == row["id"]).values({column.name: migrated})
            )


def _migrate_exception_blockers(
    bind: sa.Connection,
    exceptions: sa.Table,
    *,
    old: str,
    new: str,
) -> None:
    for row in bind.execute(
        sa.select(exceptions.c.id, exceptions.c.allowed_blocker_types_json)
    ).mappings():
        value = row["allowed_blocker_types_json"]
        if not isinstance(value, list) or old not in value:
            continue
        migrated = list(dict.fromkeys(new if item == old else item for item in value))
        bind.execute(
            sa.update(exceptions)
            .where(exceptions.c.id == row["id"])
            .values(allowed_blocker_types_json=migrated)
        )


def _restore_task_policies(
    bind: sa.Connection,
    policies: sa.Table,
    overrides: sa.Table,
) -> None:
    by_workload = {row["workload_id"]: row for row in bind.execute(sa.select(overrides)).mappings()}
    for task_kind, (workload_id, _allowed_routes) in _TASK_WORKLOAD_ROUTES.items():
        override = by_workload.get(workload_id)
        if override is None:
            continue
        bind.execute(
            sa.insert(policies).values(
                id=str(uuid4()),
                task_kind=task_kind,
                policy_mode=("external" if override["route_mode"] == "external" else "local_only"),
                description="Restored from AI model route override during downgrade.",
                updated_by=override["updated_by"],
                created_at=override["created_at"],
                updated_at=override["updated_at"],
            )
        )
