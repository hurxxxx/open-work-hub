---
paths:
  - "docs/harness/**/*"
  - "apps/ops/**/*"
  - "packages/api/documents/**/*"
  - "packages/api/search/**/*"
  - "packages/api/plm/**/*"
  - "packages/api/drafts/**/*"
---

# Service Harness Rules

- 모든 LLM 경로는 먼저 `scenario_id` 에 매핑한다.
- Prompt 변경만 단독으로 하지 말고 대응 `EvalCase` 와 release gate 영향을 함께 갱신한다.
- `documents-rag`, `plm-query`, `draft-generation`, `ocr-pipeline`, `wiki-pms` 중 하나를 반드시 고른다.
- citation 없는 응답은 실패다.
- online eval 은 비동기지만 ACL, unsafe SQL, catastrophic OCR 은 동기 가드레일로 차단한다.
