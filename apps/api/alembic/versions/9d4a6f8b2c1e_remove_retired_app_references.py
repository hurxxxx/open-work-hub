"""remove remaining retired app references

Revision ID: 9d4a6f8b2c1e
Revises: 8b1f3c2d4e5a
Create Date: 2026-08-10 21:30:00.000000

The upgrade removes executable configuration and cross-app links for every app
retired during the repository reset. Generic documents and whiteboards are kept
and reassigned to their native apps. Audit records, including AI interactions,
detected values, and usage events, remain intact. Deleted configuration and
links cannot be restored by downgrade.
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op
import sqlalchemy as sa


revision: str = "9d4a6f8b2c1e"
down_revision: str | Sequence[str] | None = "8b1f3c2d4e5a"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


# Canonical app IDs and historical domain aliases are intentionally confined to
# this migration. Runtime registries must not retain compatibility aliases.
RETIRED_APP_IDS = (
    "commute",
    "data-viz",
    "dataviz",
    "document-translate",
    "document_translate",
    "drafting",
    "drafts",
    "fmea-compare",
    "fmea_compare",
    "hr",
    "imds-minerals",
    "imds_minerals",
    "industry-report",
    "industry_report",
    "law-search",
    "lawsearch",
    "learning",
    "learning-notes",
    "learning_notes",
    "legacy-issues",
    "legacy_issues",
    "management-tasks",
    "management_tasks",
    "mcloudoc",
    "meal-invoice-ocr",
    "meal_invoice_ocr",
    "news",
    "patent",
    "patent-analysis",
    "patent-automation",
    "patent-compose",
    "patent-prior-art",
    "patent-report",
    "patent_automation",
    "patent_prior_art",
    "personal-attendance",
    "plm",
    "ppt-assistant",
    "ppt_generator",
    "qa-assistant",
    "qna",
    "spec-compare",
    "spec_compare",
)

RETIRED_TASK_KINDS = (
    "document_translate",
    "draft_assist",
    "fmea_compare",
    "legacy_issue_analysis_plan",
    "legacy_issue_analysis_sql_fallback",
    "legacy_issue_answer_draft",
    "legacy_issue_assistant",
    "legacy_issue_attachment_summary",
    "legacy_issue_attachment_vision",
    "legacy_issue_checklist_analyst",
    "legacy_issue_conversation_answer",
    "legacy_issue_evidence_analyst",
    "legacy_issue_grounding_review",
    "legacy_issue_intent_router",
    "legacy_issue_quantitative_analyst",
    "legacy_issue_report_correction",
    "legacy_issue_report_draft",
    "legacy_issue_report_finalize",
    "legacy_issue_report_template",
    "legacy_issue_request_interpret",
    "legacy_issue_sql_agent",
    "meal_invoice_ocr_extract",
    "meal_invoice_ocr_rescan",
    "news_curate",
    "patent_analysis",
    "patent_invoice_extract",
    "patent_prior_art_candidate_assessment",
    "patent_prior_art_search_plan",
    "ppt_design",
    "ppt_generate",
    "ppt_research",
    "spec_compare_compare",
    "spec_compare_extract",
    "spec_compare_report",
)

RETIRED_WORKLOAD_IDS = RETIRED_TASK_KINDS + (
    "legacy_issues.analysis_plan",
    "legacy_issues.analysis_sql_fallback",
    "legacy_issues.answer_draft",
    "legacy_issues.attachment_vision",
    "legacy_issues.checklist_analyst",
    "legacy_issues.conversation_answer",
    "legacy_issues.evidence_analyst",
    "legacy_issues.grounding_review",
    "legacy_issues.intent_router",
    "legacy_issues.quantitative_analyst",
    "legacy_issues.report_correction",
    "legacy_issues.report_draft",
    "legacy_issues.report_finalize",
    "legacy_issues.report_template",
    "legacy_issues.request_interpret",
    "legacy_issues.sql_agent",
    "patent_automation.invoice_extract",
    "patent_prior_art.candidate_assessment",
    "patent_prior_art.search_plan",
    "ppt.design",
    "ppt.research",
    "spec_compare.compare",
    "spec_compare.extract",
    "spec_compare.report",
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
    """Remove retired app configuration and live cross-app references."""
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
