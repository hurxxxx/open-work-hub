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

## 2026-04-24 · 러닝 개인 학습 노트 + 통합 sub-sidebar

- **요약**: 러닝 레슨에 per-user public/private 학습 노트를 추가했다. 본문은 Markdown + git 기반을 유지하고, 노트만 DB(`NativeDoc`/`NativeDocPage` 재사용, `source_kind`에 visibility 인코딩)로 저장한다. 관리자도 타인 private 노트는 조회 불가. 기존 좌측 TOC는 앱 sub-sidebar로 이관해 `SubSidebar.tsx`에 Learning 전용 렌더러를 추가(Docs Favorites 패턴 재사용), 콘텐츠 영역은 `[article][notes]`로 단순화.
- **PR/커밋**: 미커밋
- **영향 파일**: `apps/api/src/aidoo_api/domains/learning_notes/`, `apps/api/tests/test_learning_notes.py`, `apps/api/src/aidoo_api/app.py`, `apps/web/src/domains/learning-notes/`, `apps/web/src/components/views/learning-notes/`, `apps/web/src/components/views/LearningCourseView.tsx`, `apps/web/src/components/layout/SubSidebar.tsx`, `apps/web/src/domains/learning/manifest.ts`, `apps/web/src/domains/workspaces/workspace-utils.ts`, `apps/web/src/constants.ts`, `apps/web/src/app-shell.ts`, `learning/README.md`
- **남은 후속 작업**: `learning_note_editor` 전용 역할 도입(현재 관리자 특권 없음으로 v1 간소화), 노트 revision/history는 docs 공통 기능으로 추후 통합, manifest orphan 노트 정리용 staff 툴.

## 2026-04-24 · PostgreSQL 키워드 통합검색 실데이터 E2E 검증

- **요약**: `delivery-hub`에 검색검증 샘플 138건(문서 36, 회의 24, PMS 48, 일정 30)을 seed하고 실제 API/UI 검색을 검증했다. 빈 검색 total/facet 후보 제한 버그와 타입 필터 race를 발견해 수정했고, 실제 서버 Playwright 흐름으로 한국어 검색, facet, PMS 필터, empty state, deep link 이동을 확인했다.
- **PR/커밋**: 미커밋
- **영향 파일**: `apps/api/src/aidoo_api/seed_keyword_search_samples.py`, `apps/api/src/aidoo_api/domains/search/service.py`, `apps/web/src/components/views/RagSearchView.tsx`
- **남은 후속 작업**: 검색 read model refresh는 아직 요청 시 동기 rebuild 방식이므로 write hook/outbox 기반 증분 갱신으로 전환 필요.

## 2026-04-24 · RAG 통합검색 IA+UI V1 개선

- **요약**: `/tool/search`를 workspace 통합검색으로 인지되도록 AppBar 전역 진입, AI quick action 경로 정리, 검색 전 추천/최근 검색/source preview, 결과 유형 필터, 모바일 상세 필터, 503 복구 CTA를 반영했다. Playwright RAG 검색 E2E로 AI 진입, AppBar 진입, 모바일 source chips, timeout 복구를 검증했다.
- **PR/커밋**: 미커밋
- **영향 파일**: `apps/web/src/components/{layout,views}/`, `apps/web/src/domains/workspaces/workspace-utils.ts`, `apps/web/e2e/rag-search.spec.ts`
- **남은 후속 작업**: Cmd/Ctrl+K 전역 command palette와 live search API는 V2 범위로 유지한다.

## 2026-04-23 · Phase 5 — Internal Retrieval Orchestration + Remote Retrieval Infrastructure

- **요약**: `domains/rag/` 정본 위에 ACL projection + sync outbox/worker + Qdrant/provider adapter + workspace RAG REST/AI capability + `/tool/search` 실표면을 연결했다. Docs/Meeting/PMS/Planner 전도메인 hit/citation 계약, post-filter ACL 재검증, trace-first observability를 함께 정착시켰다.
- **PR/커밋**: 98663a5, 7be37e3, 6f6685e, e876cc7, 2bd82c0, 367b955, 8d8e29f, 3d4163d
- **영향 파일**: `apps/api/src/aidoo_api/domains/rag/`, `apps/api/src/aidoo_api/domains/{docs,meeting,pms,planner}/`, `apps/api/src/aidoo_api/core/{settings,telemetry}.py`, `apps/api/alembic/versions/{fa12bc34de56_add_rag_sync_jobs.py,c1d2e3f4a5b6_add_rag_pending_unique_indexes.py}`, `apps/worker/src/aidoo_worker/tasks/rag_sync.py`, `apps/web/src/domains/rag/`, `apps/web/src/components/views/RagSearchView.tsx`, `apps/web/src/App.tsx`
- **남은 후속 작업**: AI platform 트랙의 다음 단계는 Phase 6(`LlmJob` + Admin UI) 세부 플랜 작성이다. 운영 threshold/SLO와 provider 기본 선택은 운영 데이터가 쌓인 뒤 확정한다.

## 2026-04-22 · Phase 4 — Tool Calling (Write) + Meeting Intelligence

- **요약**: MCP-first capability bridge 위에 write tool 6종, approval halt/resume runtime, `AgentRunSnapshot`/`AiToolApproval`, meeting insight extraction/action proposal, meeting-scoped AI entry와 reload-safe approval recovery를 정착시켰다.
- **PR/커밋**: 다수 구현 커밋
- **영향 파일**: `apps/api/src/aidoo_api/domains/ai/`, `apps/api/src/aidoo_api/domains/{meeting,pms,planner,docs}/`, `apps/api/src/aidoo_api/domains/conversations/`, `apps/worker/src/aidoo_worker/tasks/meeting.py`, `apps/web/src/domains/ai/`, `apps/web/src/components/views/AIView.tsx`
- **남은 후속 작업**: Phase 5에서 retrieval tool과 grounded answer를 같은 approval/snapshot/runtime 위에 연결.

## 2026-04-18 · Phase 2 — Agent Event Envelope + SSE Streaming

- **요약**: `AgentEventEnvelope`(P2 발행 5종 + P3/P4 예약 5종) 계약 확정, provider-agnostic `LlmStreamAdapter`(mlx-lm/OpenRouter) + `AsyncOpenAI` 기반 `complete_chat_stream`, `/api/v1/ai/chat/stream` SSE 라우트(legacy + workspace slug 이중 마운트), `useChatStream` 훅 + ChatThread/MessageBubble/ThinkingPanel 추출, P3/P4 플레이스홀더 컴포넌트, hidden `aidoo.ai.streamEnabled` 플래그로 sync fallback 유지.
- **PR/커밋**: c30b818
- **영향 파일**: `apps/api/src/aidoo_api/core/{llm.py,llm_adapters.py}`, `apps/api/src/aidoo_api/domains/ai/{events.py,events_schema.md,router.py,audit.py}`, `apps/api/tests/{test_ai_events.py,test_ai_stream.py,test_llm_adapters.py,fixtures/envelope_schema.json}`, `apps/web/src/domains/ai/{agent-events.ts,sse-parser.ts,useChatStream.ts,ai-api.ts}`, `apps/web/src/components/views/{AIView.tsx,chat/}`, `DESIGN.md`
- **남은 후속 작업**: P3에서 `tool_call_*`/`approval_*` 이벤트 실제 발행과 placeholder 컴포넌트 실구현, `done.audit_id` 노출 정책(P6 운영 UI에서 확정), `first_token_ms` 측정 여부, 수동 스모크 4종(local 정상·mid-stream abort·provider outage·hidden flag off) 실기기 검증.

## 2026-04-18 · Phase 1 — LLM Pool Routing Foundation

- **요약**: local/external 풀 완전 분리, `LlmTaskContext` + `LlmPolicy` 도입, PII 기반 강제 local, 감사 로그 독립 세션 커밋, `/readyz`는 effective readiness, `/ai/health`는 raw pool 상태로 분리, 워커 summarize도 정책 경로로 통합.
- **PR/커밋**: fe23cff
- **영향 파일**: `apps/api/src/aidoo_api/core/llm.py`, `apps/api/src/aidoo_api/core/pii.py`, `apps/api/src/aidoo_api/domains/ai/`, `apps/api/alembic/versions/c7a2f1e8b3d4_add_llm_policies.py`, `apps/worker/src/aidoo_worker/`, `apps/web/src/domains/ai/`
- **남은 후속 작업**: 없음. Phase 3 착수 전 deprecated env alias와 legacy `/api/v1/ai/llm-health` 정리까지 반영 완료.
