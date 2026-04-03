---
paths:
  - "apps/api/**/*"
  - "apps/worker/**/*"
  - "packages/api/**/*"
  - "scripts/**/*.py"
---

# Backend Rules

- 도메인별 `APIRouter`, 서비스, 모델, 마이그레이션 소유권을 섞지 않는다.
- 다른 도메인의 내부 ORM 모델이나 서비스에 직접 의존하지 않는다.
- 공용 계약은 `packages/contracts` 또는 `docs/harness` 계약에서 먼저 정의한다.
- LLM 호출 경로를 추가하거나 바꾸면 trace/span, eval, release gate 영향을 함께 기록한다.
- 읽기 전용이 아닌 PLM 경로, unsafe SQL, ACL 우회는 금지한다.
