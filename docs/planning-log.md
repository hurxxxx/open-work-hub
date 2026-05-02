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

## 2026-05-02 · 다국어 지원 및 하드코드 메시지 정리

- **요약**: API/Web 다국어 기반을 정리하고 사용자 노출 validation/error/UI 메시지를 `ko-KR`/`en-US` 리소스로 전환했다. Web i18n 가드는 `packages/ui`까지 검사하도록 확장했고, 최종 하드코드 UI 메시지 검색은 0건이다.
- **PR/커밋**: 0b0e546, 59c82aa, 10a4795, 44686a8, c3ce2d9, eb3f9f2, dad54ea, 377dcd6, 6f195fc, 9013918, 9267494
- **영향 파일**: `apps/api/src/aidoo_api/core/i18n.py`, `apps/api/src/aidoo_api/domains/`, `apps/web/src/platform/i18n/`, `apps/web/src/app-modules/`, `packages/ui/src/`, `scripts/check-*-i18n-*`
- **남은 후속 작업**: 다국어 작업은 종료. 신규 UI/API 메시지는 `pnpm check:i18n`을 필수 가드로 유지.

## 2026-05-02 · 사용자 시간대 기본값 + 모바일 워크플로우 정리

- **요약**: 사용자 프로필에 `time_zone` 설정을 추가하고 기본 표시 기준을 `Asia/Seoul`로 고정했다. PMS/Meeting 모바일 표면은 3단 가로 분할 대신 단일 흐름으로 재배치했고, 모바일 셸은 `앱 전환` 드로어와 현재 앱 내부 메뉴 드로어를 분리했다.
- **PR/커밋**: eb3f0c9, 1e0630e, 6920752
- **영향 파일**: `apps/api/src/aidoo_api/domains/auth/`, `apps/web/src/platform/time/`, `apps/web/src/platform/auth/settings-pages.tsx`, `apps/web/src/app/shell/AppContent.tsx`, `apps/web/src/components/layout/AppBar.tsx`, `apps/web/src/app-modules/{pms,meeting}/`
- **남은 후속 작업**: 모바일 셸/업무 화면의 Playwright 실기기형 visual regression을 별도 E2E로 보강.

## 2026-04-26 · 통합검색 결과 미리보기 UX 적용

- **요약**: `/tool/search` 결과 클릭을 즉시 라우팅에서 선택/미리보기로 전환하고, 명시적 `열기` 액션과 `selected_type`/`selected_id` URL 상태를 추가했다. Vitest, typecheck, Playwright 검색 E2E 8건 통과.
- **PR/커밋**: 미커밋
- **영향 파일**: `apps/web/src/components/views/RagSearchView.tsx`, `apps/web/e2e/rag-search.spec.ts`, `apps/web/src/components/views/RagSearchView.spec.tsx`
- **남은 후속 작업**: 없음.

## 2026-04-26 · Learning Course — 아이디어에서 출시까지(서비스 개발 여정)

- **요약**: 신규 학습 코스 `service-launch-journey` 7파트 28레슨을 신설. 한 사람이 서비스 하나를 처음 떠올린 순간부터 출시·운영·수익화까지 따라가는 여정 컨셉으로, 기존 `vibe-coding-foundations`(개념·기술 카탈로그형)과 상호 보완 관계로 분리. manifest.spec.ts 8/8 통과.
- **PR/커밋**: 미커밋
- **영향 파일**: `learning/service-launch-journey/`(28편), `apps/web/src/domains/learning/manifest.ts`
- **남은 후속 작업**: 출시 후 사용자 피드백 기반으로 톤·분량 미세 조정. 각 레슨 "한 셜 더" 섹션의 외부 자료 링크 보강.

## 2026-04-25 · OpenSearch 증분 색인 worker 상시 구동 재검증

- **요약**: API + Celery worker + Redis + OpenSearch를 실제로 띄운 상태에서 Docs/Meeting/PMS/Planner 증분 색인 ACL/CRUD/delete 시나리오를 재실행했다. 검증 중 PMS issue create job이 `pending attempts=0`으로 남는 savepoint 조기 publish 버그를 발견해 search/RAG outbox listener를 최상위 transaction commit/rollback에만 반응하도록 수정했고, 재검증 및 UI smoke까지 통과했다.
- **PR/커밋**: 미커밋
- **영향 파일**: `apps/api/src/aidoo_api/domains/search/outbox.py`, `apps/api/src/aidoo_api/domains/rag/outbox.py`, `apps/api/tests/test_search_index_outbox.py`, `apps/api/tests/test_rag_outbox.py`, 로컬 `.env`
- **남은 후속 작업**: `.env.example`과 compose/local port 정책을 정리할지 결정.

## 2026-04-25 · OpenSearch 증분 색인 확장 ACL/CRUD E2E 검증

- **요약**: `agent-browser`로 admin/member/same-workspace outsider/hq-member 세션을 분리해 Docs, Meeting, PMS, Planner 검색 ACL/CRUD 전이 52건을 검증했다. user share, link share 비노출, teamspace membership add/remove, meeting attendee add/remove 및 attached doc/issue grant, PMS direct grant/revoke/comment/list rename/archive/delete, planner public/private/update/delete, workspace boundary를 확인했고 실패 0건이다. 검증 중 발견한 Docs teamspace projection 누락과 meeting delete FK 500도 수정했다.
- **PR/커밋**: 미커밋
- **영향 파일**: `apps/api/src/aidoo_api/domains/search/projections.py`, `apps/api/src/aidoo_api/domains/meeting/service.py`, `apps/api/tests/test_search_index_hooks.py`
- **남은 후속 작업**: 운영과 동일한 worker 상시 구동 구성에서 동일 시나리오를 재실행.

## 2026-04-25 · OpenSearch 증분 색인 agent-browser E2E 검증

- **요약**: `agent-browser`로 `delivery-hub-admin`/`delivery-hub-member` 실제 세션을 열어 문서 ACL 및 CRUD 증분 색인을 검증했다. member는 share grant 전 0건, grant 후 1건, revoke 후 0건으로 확인했고, admin은 title update 후 새 제목 1건/기존 제목 0건, delete 후 0건을 확인했다. 백엔드 로그를 함께 확인해 Redis 기동 후 E2E 구간의 `ERROR`/`Traceback`/500 로그가 없음을 확인했다.
- **PR/커밋**: 미커밋
- **영향 파일**: `apps/api/src/aidoo_api/domains/search/`, `apps/api/src/aidoo_api/domains/pms/`
- **남은 후속 작업**: 실제 worker 상시 구동 환경에서 동일 grant/revoke smoke를 반복 확인.

## 2026-04-25 · OpenSearch 통합검색 ACL grant/revoke 검증

- **요약**: `delivery-hub-admin`/`delivery-hub-member` 계정으로 실제 검색 API를 호출해 임시 문서/회의/PMS/일정 ACL을 검증했다. 문서 user share, 회의 attendee, PMS issue direct grant, 일정 public/private 전환 모두 권한 부여 후 검색 노출, revoke 후 미노출로 확인했고 cleanup 후 잔여 검색 결과도 0건임을 확인했다.
- **PR/커밋**: 9db6436, 59f59d6
- **영향 파일**: `apps/api/src/aidoo_api/domains/search/`
- **남은 후속 작업**: 요청 시 workspace 전체 rebuild를 CRUD/outbox 기반 증분 색인으로 전환하면서 권한 변경 이벤트가 색인 ACL 필드 갱신을 트리거하도록 보강.

## 2026-04-25 · OpenSearch 통합검색 UI E2E 검증

- **요약**: `agent-browser`로 실제 `/tool/search?workspace=hq` 화면을 검증했다. `hq-admin`은 `복슬` 검색에서 private 문서 1건과 `<mark>` 하이라이트를 확인했고 결과 클릭이 `/w/hq/docs/4d9c30e3-bacd-4607-811a-ab0a31d90142` deep link로 이동했다. 별도 세션의 `hq-member`는 같은 검색에서 0건으로 ACL 필터링됨을 확인했다. 추가로 `delivery-hub-member`로 샘플 데이터 검색을 수행해 `예산 리스크`, `품질 감사`, `온보딩`, `재고 부족`, `계약 갱신` 쿼리가 문서/회의/PMS/일정 결과와 facet count를 실제 UI에 렌더링하는 것을 확인했다.
- **PR/커밋**: 9db6436, 59f59d6
- **영향 파일**: `apps/api/src/aidoo_api/domains/search/`, `apps/web/src/components/views/RagSearchView.tsx`
- **남은 후속 작업**: 검색 요청 시 workspace 전체 rebuild를 CRUD/outbox 기반 증분 색인으로 전환.

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
