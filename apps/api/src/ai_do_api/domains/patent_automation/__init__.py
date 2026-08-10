"""Patent work automation domain.

Turns the patent team's Excel-based 특허현황관리 workbook into a managed
database (config-driven flexible schema, mirroring ``legacy_issues``), tracks
each patent's lifecycle/progress timeline, and generates the monthly cost
summary spreadsheets (산업재산권 지출 비용 요약 / 해외출원특허 지출 비용 요약)
from uploaded PDF invoices via the LLM gateway + document extraction.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from ai_do_api.domains.ai.registry import AiCapabilityRegistry


PATENT_AUTOMATION_APP_ID = "patent-automation"
PATENT_INVOICE_EXTRACT_WORKLOAD_ID = "patent_automation.invoice_extract"
PATENT_INVOICE_EXTRACT_TASK_KIND = "patent_invoice_extract"


def register_ai_capabilities(registry: AiCapabilityRegistry) -> None:
    registry.register_llm_workload(
        workload_id=PATENT_INVOICE_EXTRACT_WORKLOAD_ID,
        task_kind=PATENT_INVOICE_EXTRACT_TASK_KIND,
        owner_domain="patent-automation",
        app_id=PATENT_AUTOMATION_APP_ID,
        description="Extract structured patent cost items from invoice text.",
        default_route="local",
        execution_kind="chat",
        allowed_routes=("local", "external"),
        required_capabilities=("chat",),
        model_roles=("default",),
        label_key=(
            "admin.console.aiSecurity.modelSettings.workloadCatalog."
            "patentInvoiceExtract.label"
        ),
        description_key=(
            "admin.console.aiSecurity.modelSettings.workloadCatalog."
            "patentInvoiceExtract.description"
        ),
        external_data=True,
    )


__all__ = [
    "PATENT_AUTOMATION_APP_ID",
    "PATENT_INVOICE_EXTRACT_TASK_KIND",
    "PATENT_INVOICE_EXTRACT_WORKLOAD_ID",
    "register_ai_capabilities",
]
