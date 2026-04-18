# Planning Log

완료된 실행 플랜의 요약 기록. 활성 플랜은 [`plans/`](../plans/) 디렉터리에 있다.

## 운영 규칙

- 플랜이 PR 머지로 완료되면 [`plans/`](../plans/)에서 해당 파일을 제거하고, **여기에 1개 엔트리 추가**.
- 세부 변경 내용은 GitHub PR/커밋에 있으니 이 로그는 **인덱스**로만 사용. 장황한 내용 금지.
- 엔트리 형식:

  ```markdown
  ## YYYY-MM-DD · 플랜 제목

  - **요약**: 1~2 문장.
  - **PR/커밋**: #123, abc1234
  - **영향 파일**: 주요 디렉터리/모듈
  - **남은 후속 작업**: (있다면)
  ```

- 최신 항목을 위로(descending).

---

## 엔트리

## 2026-04-18 · Phase 1 — LLM Pool Routing Foundation

- **요약**: local/external 풀 완전 분리, `LlmTaskContext` + `LlmPolicy` 도입, PII 기반 강제 local, 감사 로그 독립 세션 커밋, `/readyz`는 effective readiness, `/ai/health`는 raw pool 상태로 분리, 워커 summarize도 정책 경로로 통합.
- **PR/커밋**: fe23cff
- **영향 파일**: `apps/api/src/aidoo_api/core/llm.py`, `apps/api/src/aidoo_api/core/pii.py`, `apps/api/src/aidoo_api/domains/ai/`, `apps/api/alembic/versions/c7a2f1e8b3d4_add_llm_policies.py`, `apps/worker/src/aidoo_worker/`, `apps/web/src/domains/ai/`
- **남은 후속 작업**: deprecated env alias 제거(Phase 3 kickoff), `/api/v1/ai/llm-health` 제거 시점 재검토(P2 이후)
