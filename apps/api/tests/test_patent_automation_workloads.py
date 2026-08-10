from __future__ import annotations

from types import SimpleNamespace

from ai_do_api.domains.ai.registry import AiCapabilityRegistry
from ai_do_api.domains.patent_automation import (
    PATENT_AUTOMATION_APP_ID,
    PATENT_INVOICE_EXTRACT_TASK_KIND,
    PATENT_INVOICE_EXTRACT_WORKLOAD_ID,
    register_ai_capabilities,
)
from ai_do_api.domains.patent_automation import llm_extract


def test_registers_patent_invoice_extraction_workload() -> None:
    registry = AiCapabilityRegistry()

    register_ai_capabilities(registry)

    workload = registry.llm_workloads[PATENT_INVOICE_EXTRACT_WORKLOAD_ID]
    assert workload.task_kind == PATENT_INVOICE_EXTRACT_TASK_KIND
    assert workload.app_ids == (PATENT_AUTOMATION_APP_ID,)
    assert workload.default_route == "local"
    assert workload.allowed_routes == ("local", "external")
    assert workload.allowed_providers == ()
    assert workload.external_data is True


def test_invoice_extraction_executes_patent_workload(monkeypatch) -> None:
    captured: dict[str, object] = {}

    def fake_execute(workload_id, context, _db, **kwargs):
        captured.update(workload_id=workload_id, context=context, kwargs=kwargs)
        return SimpleNamespace(
            completion=SimpleNamespace(
                text=(
                    '{"domain":"국내","vendor":"한라","invoice_no":"INV-1",'
                    '"items":[]}'
                )
            )
        )

    monkeypatch.setattr(llm_extract, "execute_llm", fake_execute)

    result = llm_extract.extract_invoice_json(
        object(),
        workspace_id="workspace-1",
        actor_user_id="user-1",
        page_text="특허 비용 청구서 INV-1",
        domain_hint="국내",
    )

    assert result["invoice_no"] == "INV-1"
    assert captured["workload_id"] == PATENT_INVOICE_EXTRACT_WORKLOAD_ID
    assert captured["context"].app_id == PATENT_AUTOMATION_APP_ID
