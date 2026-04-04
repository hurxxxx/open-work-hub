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
- Prompt 변경만 단독으로 하지 말고 대응 `ScenarioManifest`, `EvalSuite`, `TraceGradeSpec`, release gate 영향을 함께 갱신한다.
- `documents-rag`, `plm-query`, `draft-generation`, `ocr-pipeline`, `wiki-pms` 중 하나를 반드시 고른다.
- citation 없는 응답은 실패다.
- online eval 은 비동기지만 ACL, unsafe SQL, catastrophic OCR 은 동기 가드레일로 차단한다.
- 서비스 prompt 는 stage bundle 로 나누고, retrieval context 는 필요한 단계에만 전달한다.
