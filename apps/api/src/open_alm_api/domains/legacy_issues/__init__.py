"""Legacy issue dataset CRUD endpoints for core business apps."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from open_alm_api.domains.ai.registry import AiCapabilityRegistry


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    from open_alm_api.domains.legacy_issues.task_kinds import (
        LEGACY_ISSUE_ASSISTANT_TASK_KIND,
        LEGACY_ISSUE_ATTACHMENT_SUMMARY_TASK_KIND,
        LEGACY_ISSUE_ATTACHMENT_VISION_TASK_KIND,
        LEGACY_ISSUE_ANALYSIS_PLAN_TASK_KIND,
        LEGACY_ISSUE_ANALYSIS_PLAN_WORKLOAD_ID,
        LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_TASK_KIND,
        LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_WORKLOAD_ID,
        LEGACY_ISSUE_ANSWER_DRAFT_TASK_KIND,
        LEGACY_ISSUE_ANSWER_DRAFT_WORKLOAD_ID,
        LEGACY_ISSUE_CONVERSATION_ANSWER_TASK_KIND,
        LEGACY_ISSUE_CONVERSATION_ANSWER_WORKLOAD_ID,
        LEGACY_ISSUE_CHECKLIST_ANALYST_TASK_KIND,
        LEGACY_ISSUE_CHECKLIST_ANALYST_WORKLOAD_ID,
        LEGACY_ISSUE_EVIDENCE_ANALYST_TASK_KIND,
        LEGACY_ISSUE_EVIDENCE_ANALYST_WORKLOAD_ID,
        LEGACY_ISSUE_GROUNDING_REVIEW_TASK_KIND,
        LEGACY_ISSUE_GROUNDING_REVIEW_WORKLOAD_ID,
        LEGACY_ISSUE_INTENT_ROUTER_TASK_KIND,
        LEGACY_ISSUE_INTENT_ROUTER_WORKLOAD_ID,
        LEGACY_ISSUE_QUANTITATIVE_ANALYST_TASK_KIND,
        LEGACY_ISSUE_QUANTITATIVE_ANALYST_WORKLOAD_ID,
        LEGACY_ISSUE_REPORT_CORRECTION_TASK_KIND,
        LEGACY_ISSUE_REPORT_CORRECTION_WORKLOAD_ID,
        LEGACY_ISSUE_REPORT_DRAFT_TASK_KIND,
        LEGACY_ISSUE_REPORT_DRAFT_WORKLOAD_ID,
        LEGACY_ISSUE_REPORT_FINALIZE_TASK_KIND,
        LEGACY_ISSUE_REPORT_FINALIZE_WORKLOAD_ID,
        LEGACY_ISSUE_REPORT_TEMPLATE_TASK_KIND,
        LEGACY_ISSUE_REPORT_TEMPLATE_WORKLOAD_ID,
        LEGACY_ISSUE_REQUEST_INTERPRET_TASK_KIND,
        LEGACY_ISSUE_REQUEST_INTERPRET_WORKLOAD_ID,
        LEGACY_ISSUE_SQL_AGENT_TASK_KIND,
        LEGACY_ISSUE_SQL_AGENT_WORKLOAD_ID,
    )

    registry.register_llm_task(
        task_kind=LEGACY_ISSUE_ASSISTANT_TASK_KIND,
        default_policy="local_only",
        description="Read-only assistant for legacy issue records and revisions.",
        app_ids=("legacy-issues",),
    )
    registry.register_llm_task(
        task_kind=LEGACY_ISSUE_ATTACHMENT_SUMMARY_TASK_KIND,
        default_policy="local_only",
        description="Detailed local AI summary for indexed legacy issue attachments.",
        app_ids=("legacy-issues",),
    )
    registry.register_llm_workload(
        workload_id=LEGACY_ISSUE_CONVERSATION_ANSWER_WORKLOAD_ID,
        task_kind=LEGACY_ISSUE_CONVERSATION_ANSWER_TASK_KIND,
        owner_domain="legacy-issues",
        app_id="legacy-issues",
        description="Interactive answers grounded in legacy issue records.",
        default_route="local",
        execution_kind="chat",
        allowed_routes=("local", "external"),
        required_capabilities=("chat",),
        model_roles=("default",),
        label_key=(
            "admin.console.aiSecurity.modelSettings.workloadCatalog."
            "legacyIssueConversationAnswer.label"
        ),
        description_key=(
            "admin.console.aiSecurity.modelSettings.workloadCatalog."
            "legacyIssueConversationAnswer.description"
        ),
        external_data=True,
        local_max_output_tokens=8_192,
        external_max_output_tokens=8_192,
    )
    registry.register_llm_workload(
        workload_id=LEGACY_ISSUE_INTENT_ROUTER_WORKLOAD_ID,
        task_kind=LEGACY_ISSUE_INTENT_ROUTER_TASK_KIND,
        owner_domain="legacy-issues",
        app_id="legacy-issues",
        description="Routes legacy issue chat requests to scoped analysis modes.",
        default_route="local",
        execution_kind="chat",
        allowed_routes=("local", "external"),
        required_capabilities=("chat",),
        model_roles=("default",),
        external_data=True,
        local_max_output_tokens=1_024,
        external_max_output_tokens=1_024,
    )
    registry.register_llm_workload(
        workload_id=LEGACY_ISSUE_ANALYSIS_PLAN_WORKLOAD_ID,
        task_kind=LEGACY_ISSUE_ANALYSIS_PLAN_TASK_KIND,
        owner_domain="legacy-issues",
        app_id="legacy-issues",
        description="Plans schema-validated queries for legacy issue analysis.",
        default_route="local",
        execution_kind="chat",
        allowed_routes=("local", "external"),
        required_capabilities=("chat",),
        model_roles=("default",),
        external_data=True,
        local_max_output_tokens=8_192,
        external_max_output_tokens=8_192,
    )
    registry.register_llm_workload(
        workload_id=LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_WORKLOAD_ID,
        task_kind=LEGACY_ISSUE_ANALYSIS_SQL_FALLBACK_TASK_KIND,
        owner_domain="legacy-issues",
        app_id="legacy-issues",
        description="Generates guarded SQL for unsupported legacy issue analysis requests.",
        default_route="local",
        execution_kind="chat",
        allowed_routes=("local", "external"),
        required_capabilities=("chat",),
        model_roles=("default",),
        external_data=True,
        local_max_output_tokens=8_192,
        external_max_output_tokens=8_192,
    )
    graph_workloads = (
        (
            LEGACY_ISSUE_REQUEST_INTERPRET_WORKLOAD_ID,
            LEGACY_ISSUE_REQUEST_INTERPRET_TASK_KIND,
            "Interprets legacy issue questions into a compact analysis request.",
            2_048,
        ),
        (
            LEGACY_ISSUE_SQL_AGENT_WORKLOAD_ID,
            LEGACY_ISSUE_SQL_AGENT_TASK_KIND,
            "Selects and runs bounded read-only analysis tools for legacy issues.",
            4_096,
        ),
        (
            LEGACY_ISSUE_REPORT_TEMPLATE_WORKLOAD_ID,
            LEGACY_ISSUE_REPORT_TEMPLATE_TASK_KIND,
            "Designs a question-appropriate evidence-grounded report outline.",
            4_096,
        ),
        (
            LEGACY_ISSUE_QUANTITATIVE_ANALYST_WORKLOAD_ID,
            LEGACY_ISSUE_QUANTITATIVE_ANALYST_TASK_KIND,
            "Interprets only captured structured query results.",
            4_096,
        ),
        (
            LEGACY_ISSUE_EVIDENCE_ANALYST_WORKLOAD_ID,
            LEGACY_ISSUE_EVIDENCE_ANALYST_TASK_KIND,
            "Synthesizes retrieved legacy issue cases with source citations.",
            4_096,
        ),
        (
            LEGACY_ISSUE_CHECKLIST_ANALYST_WORKLOAD_ID,
            LEGACY_ISSUE_CHECKLIST_ANALYST_TASK_KIND,
            "Summarizes captured vehicle checklist evidence and coverage.",
            4_096,
        ),
        (
            LEGACY_ISSUE_REPORT_DRAFT_WORKLOAD_ID,
            LEGACY_ISSUE_REPORT_DRAFT_TASK_KIND,
            "Writes a dynamic Markdown report from the approved outline and evidence.",
            8_192,
        ),
        (
            LEGACY_ISSUE_GROUNDING_REVIEW_WORKLOAD_ID,
            LEGACY_ISSUE_GROUNDING_REVIEW_TASK_KIND,
            "Reviews report claims against captured sources and returns compact JSON.",
            4_096,
        ),
        (
            LEGACY_ISSUE_REPORT_FINALIZE_WORKLOAD_ID,
            LEGACY_ISSUE_REPORT_FINALIZE_TASK_KIND,
            "Finalizes a grounded report without internal processing commentary.",
            8_192,
        ),
        (
            LEGACY_ISSUE_REPORT_CORRECTION_WORKLOAD_ID,
            LEGACY_ISSUE_REPORT_CORRECTION_TASK_KIND,
            "Corrects one report after deterministic validation failure.",
            8_192,
        ),
        (
            LEGACY_ISSUE_ANSWER_DRAFT_WORKLOAD_ID,
            LEGACY_ISSUE_ANSWER_DRAFT_TASK_KIND,
            "Writes a concise grounded answer when a full report was not requested.",
            4_096,
        ),
    )
    for workload_id, task_kind, description, max_output_tokens in graph_workloads:
        registry.register_llm_workload(
            workload_id=workload_id,
            task_kind=task_kind,
            owner_domain="legacy-issues",
            app_id="legacy-issues",
            description=description,
            default_route="local",
            execution_kind="agent" if workload_id == LEGACY_ISSUE_SQL_AGENT_WORKLOAD_ID else "chat",
            allowed_routes=("local", "external"),
            required_capabilities=("chat",),
            model_roles=("default",),
            external_data=True,
            local_max_output_tokens=max_output_tokens,
            external_max_output_tokens=max_output_tokens,
        )
    registry.register_llm_workload(
        workload_id="legacy_issues.attachment_vision",
        task_kind=LEGACY_ISSUE_ATTACHMENT_VISION_TASK_KIND,
        owner_domain="legacy-issues",
        app_id="legacy-issues",
        description="Local vision extraction for indexed legacy issue attachments.",
        default_route="local",
        allowed_routes=("local",),
        required_capabilities=("vision",),
        label_key=(
            "admin.console.aiSecurity.modelSettings.workloadCatalog.legacyAttachmentVision.label"
        ),
        description_key=(
            "admin.console.aiSecurity.modelSettings.workloadCatalog."
            "legacyAttachmentVision.description"
        ),
        external_data=False,
        management_surface="document_processing",
    )


__all__ = ["register_ai_capabilities"]
