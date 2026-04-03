---
paths:
  - "docs/harness/**/*"
  - "packages/testing/**/*"
  - "apps/ops/**/*"
---

# Eval Rules

- workflow version 이 바뀌면 최소 `golden` 과 `adversarial` 셋을 다시 본다.
- scorecard 는 시나리오별로 독립 계산한다.
- 기준선 대비 `3%p` 이상 하락은 회귀로 본다.
- 안전성 지표 실패는 `hold` 이다.
- 운영 실패 사례는 익일 eval 편입 후보로 큐잉한다.
