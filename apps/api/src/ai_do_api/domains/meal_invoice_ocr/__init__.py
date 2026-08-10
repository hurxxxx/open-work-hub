from __future__ import annotations

from typing import TYPE_CHECKING

# 식당 거래명세표 OCR 업무 앱. 사용자가 명세표(PDF/이미지)를 올리면 관리자가 선택한 local Vision 모델로
# 표를 추출해 편집 가능한 그리드로 돌려주고, 편집 결과를 엑셀로 내보낸다.
# 사용자 주도 앱 UI 흐름이라 MCP 도구(AI capability, ADR 0002)로는 노출하지 않는다(patent-prior-art 와 동일).
# 단, 비전 OCR 은 플랫폼 LLM task 로 등록해 토큰 예산·정책·감사(llm_call)를 적용받는다.
APP_ID = "meal-invoice-ocr"

if TYPE_CHECKING:
    from ai_do_api.domains.ai.registry import AiCapabilityRegistry


def register_ai_capabilities(registry: "AiCapabilityRegistry") -> None:
    """플랫폼 LLM task registry 에 명세표 OCR task 를 등록한다(도구/capability 노출은 없음).

    이렇게 해야 OCR 비전 호출이 플랫폼 gateway 경로(정책·토큰 예산·llm_call 감사)를 탄다.
    """
    from ai_do_api.domains.meal_invoice_ocr.task_kinds import (
        MEAL_INVOICE_OCR_RESCAN_TASK_KIND,
        MEAL_INVOICE_OCR_RESCAN_WORKLOAD_ID,
        MEAL_INVOICE_OCR_TASK_KIND,
        MEAL_INVOICE_OCR_WORKLOAD_ID,
    )

    # 두 JSON 응답 모두 25행 표를 담을 수 있게 넉넉히 잡되, route/model/cap/audit identity 는
    # 기능별로 분리한다. 두 workload 모두 외부 egress 없는 로컬 비전 모델만 허용한다.
    registrations = (
        (
            MEAL_INVOICE_OCR_WORKLOAD_ID,
            MEAL_INVOICE_OCR_TASK_KIND,
            "Vision OCR of restaurant delivery invoices (image to structured rows).",
        ),
        (
            MEAL_INVOICE_OCR_RESCAN_WORKLOAD_ID,
            MEAL_INVOICE_OCR_RESCAN_TASK_KIND,
            "Focused reread of invoice row bands for names, origins, and units.",
        ),
    )
    for workload_id, task_kind, description in registrations:
        registry.register_llm_workload(
            workload_id=workload_id,
            task_kind=task_kind,
            owner_domain="meal-invoice-ocr",
            app_id=APP_ID,
            description=description,
            default_route="local",
            allowed_routes=("local",),
            required_capabilities=("vision",),
            management_surface="document_processing",
            external_data=False,
            local_max_output_tokens=4096,
            external_max_output_tokens=4096,
        )


__all__ = ["APP_ID", "register_ai_capabilities"]
