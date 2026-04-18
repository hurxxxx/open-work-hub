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

## 2026-04-18 · Phase 2 — Agent Event Envelope + SSE Streaming

- **요약**: `AgentEventEnvelope`(P2 발행 5종 + P3/P4 예약 5종) 계약 확정, provider-agnostic `LlmStreamAdapter`(mlx-lm/OpenRouter) + `AsyncOpenAI` 기반 `complete_chat_stream`, `/api/v1/ai/chat/stream` SSE 라우트(legacy + workspace slug 이중 마운트), `useChatStream` 훅 + ChatThread/MessageBubble/ThinkingPanel 추출, P3/P4 플레이스홀더 컴포넌트, hidden `aidoo.ai.streamEnabled` 플래그로 sync fallback 유지.
- **PR/커밋**: c30b818
- **영향 파일**: `apps/api/src/aidoo_api/core/{llm.py,llm_adapters.py}`, `apps/api/src/aidoo_api/domains/ai/{events.py,events_schema.md,router.py,audit.py}`, `apps/api/tests/{test_ai_events.py,test_ai_stream.py,test_llm_adapters.py,fixtures/envelope_schema.json}`, `apps/web/src/domains/ai/{agent-events.ts,sse-parser.ts,useChatStream.ts,ai-api.ts}`, `apps/web/src/components/views/{AIView.tsx,chat/}`, `DESIGN.md`
- **남은 후속 작업**: P3 킥오프 시 Phase 1 deprecated env alias 제거·`/api/v1/ai/llm-health` 제거 결정, `done.audit_id` 노출 정책(P6 운영 UI에서 확정), `first_token_ms` 측정 여부, 수동 스모크 4종(local 정상·mid-stream abort·provider outage·hidden flag off) 실기기 검증.

## 2026-04-18 · Phase 1 — LLM Pool Routing Foundation

- **요약**: local/external 풀 완전 분리, `LlmTaskContext` + `LlmPolicy` 도입, PII 기반 강제 local, 감사 로그 독립 세션 커밋, `/readyz`는 effective readiness, `/ai/health`는 raw pool 상태로 분리, 워커 summarize도 정책 경로로 통합.
- **PR/커밋**: fe23cff
- **영향 파일**: `apps/api/src/aidoo_api/core/llm.py`, `apps/api/src/aidoo_api/core/pii.py`, `apps/api/src/aidoo_api/domains/ai/`, `apps/api/alembic/versions/c7a2f1e8b3d4_add_llm_policies.py`, `apps/worker/src/aidoo_worker/`, `apps/web/src/domains/ai/`
- **남은 후속 작업**: deprecated env alias 제거(Phase 3 kickoff), `/api/v1/ai/llm-health` 제거 시점 재검토(P2 이후)
