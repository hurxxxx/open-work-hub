"""Specification comparison domain and LLM workload registrations."""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_do_api.domains.ai.registry import AiCapabilityRegistry


SPEC_COMPARE_APP_ID = "spec-compare"
SPEC_COMPARE_EXTRACT_WORKLOAD_ID = "spec_compare.extract"
SPEC_COMPARE_EXTRACT_TASK_KIND = "spec_compare_extract"
SPEC_COMPARE_COMPARE_WORKLOAD_ID = "spec_compare.compare"
SPEC_COMPARE_COMPARE_TASK_KIND = "spec_compare_compare"
SPEC_COMPARE_REPORT_WORKLOAD_ID = "spec_compare.report"
SPEC_COMPARE_REPORT_TASK_KIND = "spec_compare_report"


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registrations = (
        (
            SPEC_COMPARE_EXTRACT_WORKLOAD_ID,
            SPEC_COMPARE_EXTRACT_TASK_KIND,
            "Extract structured specification facts from source documents.",
            "specCompareExtract",
        ),
        (
            SPEC_COMPARE_COMPARE_WORKLOAD_ID,
            SPEC_COMPARE_COMPARE_TASK_KIND,
            "Compare and align specification candidates between two documents.",
            "specCompareCompare",
        ),
        (
            SPEC_COMPARE_REPORT_WORKLOAD_ID,
            SPEC_COMPARE_REPORT_TASK_KIND,
            "Generate an analysis summary for a specification comparison report.",
            "specCompareReport",
        ),
    )
    for workload_id, task_kind, description, catalog_key in registrations:
        registry.register_llm_workload(
            workload_id=workload_id,
            task_kind=task_kind,
            owner_domain="spec-compare",
            app_id=SPEC_COMPARE_APP_ID,
            description=description,
            default_route="local",
            execution_kind="chat",
            allowed_routes=("local", "external"),
            required_capabilities=("chat",),
            model_roles=("default",),
            label_key=(
                "admin.console.aiSecurity.modelSettings.workloadCatalog."
                f"{catalog_key}.label"
            ),
            description_key=(
                "admin.console.aiSecurity.modelSettings.workloadCatalog."
                f"{catalog_key}.description"
            ),
            external_data=True,
        )


__all__ = [
    "SPEC_COMPARE_APP_ID",
    "SPEC_COMPARE_COMPARE_TASK_KIND",
    "SPEC_COMPARE_COMPARE_WORKLOAD_ID",
    "SPEC_COMPARE_EXTRACT_TASK_KIND",
    "SPEC_COMPARE_EXTRACT_WORKLOAD_ID",
    "SPEC_COMPARE_REPORT_TASK_KIND",
    "SPEC_COMPARE_REPORT_WORKLOAD_ID",
    "register_ai_capabilities",
]
