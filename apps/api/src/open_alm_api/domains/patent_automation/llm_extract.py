"""LLM-based invoice extraction (primary for unknown vendors, fallback else).

Routes through the platform pool policy like the patent domain, reusing the
``parse_json_lenient`` repair helper. Robust to per-vendor format variation
because the model reads the page text and returns a fixed JSON shape.
"""

from __future__ import annotations

from typing import Any

from sqlalchemy.orm import Session

from open_alm_api.core.llm import LlmTaskContext
from open_alm_api.domains.ai.gateway import (
    LlmWorkloadContext,
    execute_llm,
)
from open_alm_api.domains.patent.llm import parse_json_lenient
from open_alm_api.domains.patent_automation import (
    PATENT_AUTOMATION_APP_ID,
    PATENT_INVOICE_EXTRACT_TASK_KIND,
    PATENT_INVOICE_EXTRACT_WORKLOAD_ID,
)

_TIMEOUT_SECONDS = 180.0

_SCHEMA_HINT = """다음 JSON 스키마로만 응답하세요(설명 금지):
{
  "domain": "국내" | "해외",
  "vendor": string,
  "invoice_no": string,
  "items": [
    {
      "app_no": string,            // 출원번호 (국내는 10-YYYY-NNNNNNN)
      "reg_no": string,            // 등록번호 (없으면 "")
      "title": string,             // 발명의 명칭
      "annuity_year": string,      // 연차 (연차료일 때, 예 "10년차")
      "supply_amount": number,     // 공급가액(원), 정수
      "vat": number,               // 부가세(원), 정수
      "gov_fee": number,           // 관납료(원), 정수 (없으면 0)
      "foreign_currency": string,  // 해외: "USD"|"EUR" (국내는 "")
      "foreign_amount": number,    // 해외 외화 금액 (없으면 0)
      "fx_rate": number,           // 해외 적용 환율 (없으면 0)
      "foreign_cost_krw": number,  // 해외비용 원화 (없으면 0)
      "remittance_fee": number,    // 송금수수료(원) (없으면 0)
      "agent_fee": number,         // 대리인/당소 수수료(원) (없으면 0)
      "line_total": number         // 청구금액/합계(원), 정수
    }
  ]
}
숫자는 콤마/원 표기를 제거한 정수 또는 숫자로만. 값이 없으면 0 또는 "".
"""


def extract_invoice_json(
    db: Session,
    *,
    workspace_id: str,
    actor_user_id: str | None,
    page_text: str,
    domain_hint: str,
) -> dict[str, Any]:
    context = LlmTaskContext(
        source="patent_automation",
        workspace_id=workspace_id,
        task_kind=PATENT_INVOICE_EXTRACT_TASK_KIND,
        app_id=PATENT_AUTOMATION_APP_ID,
        actor_user_id=actor_user_id,
        principal_kind="user",
        principal_id=actor_user_id,
    )
    prompt = (
        f"아래는 특허 비용 청구서({domain_hint})의 텍스트입니다. 청구 항목을 추출하세요.\n\n"
        f"{_SCHEMA_HINT}\n\n--- 청구서 텍스트 ---\n{page_text[:12000]}"
    )
    completion = execute_llm(
        PATENT_INVOICE_EXTRACT_WORKLOAD_ID,
        LlmWorkloadContext.from_task_context(context),
        db,
        messages=[{"role": "user", "content": prompt}],
        temperature=0.0,
        max_tokens=4096,
        reasoning_effort="none",
        timeout_seconds=_TIMEOUT_SECONDS,
    ).completion
    parsed = parse_json_lenient(completion.text.strip())
    return parsed if isinstance(parsed, dict) else {}
