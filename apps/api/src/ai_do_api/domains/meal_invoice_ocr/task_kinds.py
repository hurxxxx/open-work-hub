from __future__ import annotations

# 명세표 비전 OCR LLM workload/task 종류. 1차 전체 추출과 2차 확대 재판독은 프롬프트·출력
# 스키마가 다른 독립 기능이므로 관리자가 route/model/cap/audit 를 각각 제어할 수 있게 분리한다.
# 둘 다 로컬 vLLM(Qwen 비전)만 쓰므로 정책은 local_only.
MEAL_INVOICE_OCR_TASK_KIND = "meal_invoice_ocr_extract"
MEAL_INVOICE_OCR_RESCAN_TASK_KIND = "meal_invoice_ocr_rescan"

MEAL_INVOICE_OCR_WORKLOAD_ID = MEAL_INVOICE_OCR_TASK_KIND
MEAL_INVOICE_OCR_RESCAN_WORKLOAD_ID = MEAL_INVOICE_OCR_RESCAN_TASK_KIND
