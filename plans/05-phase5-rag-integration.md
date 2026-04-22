# Phase 5 — External RAG Integration (Retrieval-Only, Cross-Domain)

## Context
Phase 5는 별도 RAG 서버와의 HTTP 연동을 통해 Doowon 전도메인 데이터를 검색 가능하게 만들고, 그 결과를 REST, AI tool, `/tool/search` UI까지 일관된 계약으로 노출하는 단계다.

이번 Phase는 Docs 전용 ACL projection 실험이 아니라, Docs / Meeting / PMS / Planner를 모두 포괄하는 retrieval platform을 만드는 일로 본다. 다만 범위가 크기 때문에 한 번에 구현하지 않고, 단일 계획 파일 안에서 5A / 5B / 5C 세 마일스톤으로 쪼개어 실행한다.

이미 Phase 4에서 AI capability / MCP registry / approval / scoped conversation / event envelope 계약이 크게 정리되었으므로, Phase 5는 그 계약을 다시 흔들지 않는다. 바뀌는 것은 retrieval 계층과 search 결과 contract다.

이 계획은 현재 로드맵의 `05-phase5-rag-acl-projection.md` placeholder를 대체하는 실제 실행 플랜이다.

## Architecture / Principles
- RAG 서버는 별도 서버이며 Doowon과는 HTTP로만 통신한다.
- RAG 서버는 retrieval pipeline을 전담한다.
  - chunking
  - binary extraction / OCR / ASR
  - embedding
  - Qdrant indexing
  - retrieval / rerank
- Doowon은 retrieval orchestrator이자 ACL 진실원이다.
  - resource payload 정규화
  - visibility projection 생성
  - requester access context 생성
  - 결과 후처리
  - grounded answer가 필요한 경우 Doowon LLM 호출
- raw share token은 외부 RAG 서버로 보내지 않는다.
  - 내부에서만 검증하고, 외부에는 파생 `link_share_ref` 같은 안전한 ref만 보낸다.
- 기존 Phase 4 AI 계약은 유지한다.
  - `AiCapabilityDescriptor`
  - `LlmTaskContext`
  - `/ai/chat/stream`, `/ai/chat/resume`
  - `/ai/conversations`
  - approval state machine
- 기존 `/api/v1/search/documents`는 Phase 5 동안 legacy/demo surface로 유지한다.
  - 새 RAG surface와 섞지 않는다.
- Phase 5는 retrieval-only external RAG 전제다.
  - grounded answer는 RAG 서버가 아니라 Doowon의 LLM이 생성한다.

## 구현 단계

### 5A — Foundation: Sync + ACL Projection + RAG Client
목표는 Doowon 데이터와 외부 RAG 서버를 안전하게 동기화할 기반을 만드는 것이다. 이 단계에서는 UI를 건드리지 않고 ingest/delete, ACL projection, sync queue를 먼저 닫는다.

구현:
- settings 추가
  - `AIDOO_RAG_ENABLED`
  - `AIDOO_RAG_BASE_URL`
  - `AIDOO_RAG_API_KEY`
  - `AIDOO_RAG_TIMEOUT_MS`
  - `AIDOO_RAG_UI_ENABLED`
- `core/rag_client.py` 추가
  - HTTP client
  - typed DTO
  - timeout / retry / trace id
- projection layer 추가
  - Docs: owner, direct share, link share ref, meeting grant, workspace/container context
  - Meeting: metadata, summary, transcript, insights, participant visibility
  - PMS: issue, description, comments, label/list/milestone context, issue access grant
  - Planner: title, description, location, time, owner/public visibility
- sync outbox/job 추가
  - 예: `rag_sync_jobs`
  - `resource_type`, `resource_id`, `workspace_id`, `operation`, `checksum`, `status`, `attempts`, `last_error`, `next_retry_at`
- write/change path는 RAG 서버를 직접 호출하지 않고 sync job만 enqueue
- worker가 job을 소비해 ingest/delete 호출
- binary는 Doowon이 직접 처리하지 않음
  - 텍스트는 raw text/content payload 전송
  - 바이너리는 signed URL 또는 storage ref + mime metadata 전송
- 5A 완료 시점에는 검색 호출보다 index sync correctness를 우선 검증한다

주의:
- ACL truth는 도메인 service/access helper에서 읽고, projection에만 옮긴다
- 도메인 ACL 로직을 별도 규칙으로 재작성하지 않는다

### 5B — Product Surface: Workspace RAG API + AI Capability
목표는 retrieval 결과를 제품 surface로 노출하는 것이다. 이 단계에서 REST와 AI tool contract를 먼저 고정하고, grounded answer 생성 위치도 Doowon 쪽으로 확정한다.

구현:
- workspace-scoped REST 추가
  - `POST /api/v1/workspaces/{slug}/rag/query`
  - `GET /api/v1/workspaces/{slug}/rag/sources`
  - `POST /api/v1/workspaces/{slug}/rag/reindex` 는 admin/internal only
- AI capability 등록
  - `rag.query`
  - `rag.list_sources`
- REST와 AI tool은 같은 retrieval service를 호출
- query flow 고정
  1. Doowon이 requester access context 구성
  2. RAG 서버에 query + access context + filters 전송
  3. RAG 서버가 hits/citations/source metadata 반환
  4. `answer_mode=grounded-answer`이면 Doowon이 own LLM으로 grounded answer 생성
- retrieval result 공통 계약 정의
  - request
    - `query`
    - `answer_mode: search-only | grounded-answer`
    - `source_kinds`
    - `filters`
    - `top_k`
    - `include_binary_hits`
  - response
    - `query`
    - `answer_mode`
    - `hits`
    - `grounded_answer | null`
    - `sources_used`
    - `query_profile`
    - `trace_id`
    - `latency_ms`
- hit 공통 shape 통일
  - `source_kind`
  - `resource_type`
  - `resource_id`
  - `workspace_id`
  - `title`
  - `summary`
  - `score`
  - `citation`
  - `page_or_span`
  - `owner_label`
  - `acl_summary`
  - `origin_ref`
- grounded answer LLM 호출용 task kind 추가
  - `rag_grounded_answer`
- 기존 `/api/v1/search/documents`는 유지하되 새 surface와 연결하지 않음

주의:
- retrieval tool은 read-only로 유지
- Phase 4 approval/write flow를 retrieval에 섞지 않는다

### 5C — UI: `/tool/search` 실연결
목표는 orphan 상태인 검색 UI를 실제 제품 surface로 승격하는 것이다. 이 단계에서만 `/tool/search`를 실사용 가능한 화면으로 만든다.

구현:
- 현재 `SearchWorkbench`를 실제 route consumer로 연결
- `/tool/search`는 placeholder `ToolView` 대신 real workbench를 렌더
- UI 모드
  - search-only result list
  - grounded answer + citations
  - source/domain filters
- 결과 렌더
  - Docs / Meeting / PMS / Planner source badge
  - citation / origin link / summary / score
- AI tool result renderer도 같은 retrieval contract를 사용
- dedicated search UI와 AI tool은 같은 REST/service contract를 재사용
- 기존 approval/scoped conversation UX는 그대로 유지

주의:
- UI 단계에서 retrieval contract를 다시 정의하지 않는다
- UI는 5B contract 소비자일 뿐이다

## Verification

### 자동화 테스트
5A:
- Docs direct share / link share / meeting grant / revoke / expiry projection tests
- Meeting participant/non-participant visibility tests
- PMS issue grant visibility tests
- Planner private/public visibility tests
- sync job enqueue/idempotency/retry tests
- binary ingest request serialization tests

5B:
- fake RAG server contract tests
- workspace ACL no-leak tests
- expired grant exclusion tests
- `rag.query` AI tool tests
- grounded answer synthesis tests with mocked local LLM
- legacy `/search/documents` unchanged regression

5C:
- `/tool/search` route render
- search-only / grounded-answer mode tests
- cross-domain hit rendering
- citations/source badges
- source filters
- AI tool result renderer regression
- Playwright
  - 접근 가능한 Docs hit 노출
  - 접근 불가 Docs hit 비노출
  - meeting transcript hit 노출
  - PMS private issue 비노출
  - grounded answer + citation render

### 수동 검증
- 같은 질의를 REST, AI tool, `/tool/search` 세 surface에서 호출했을 때 hit set과 citation 구조가 실질적으로 일치하는지 확인
- 만료된 grant 이후 다음 query부터 결과에서 즉시 빠지는지 확인
- RAG 서버 장애 시
  - REST는 explicit unavailable/error response
  - AI는 tool error 후 fallback assistant 응답
  - UI는 graceful empty/error state

## 결정 로그
확정:
- Phase 5는 단일 계획 파일로 관리하되, 구현은 5A/5B/5C로 분할한다
- RAG 서버는 external retrieval-only server
- Qdrant / extraction / embedding / rerank는 RAG 서버가 담당
- Doowon은 ACL, query shaping, sync orchestration, 결과 후처리 담당
- grounded answer는 Doowon LLM이 생성
- 기존 `/api/v1/search/documents`는 legacy/demo로 유지
- 기존 Phase 4 AI approval/conversation contract는 유지
- `scope_ref`와 approval UX는 Phase 5에서 재설계하지 않음

후속 결정:
- RAG 서버 OpenAPI 문서의 정확한 field naming
- binary ingest 시 signed URL 만료/재시도 전략
- reindex 운영 정책과 admin surface 노출 수준

## 롤백 계획
- feature flag 기본값은 off
  - `AIDOO_RAG_ENABLED=false`
  - `AIDOO_RAG_UI_ENABLED=false`
- 5A 실패 시
  - sync enqueue만 중단하고 기존 도메인 write path는 유지
- 5B 실패 시
  - `/rag/*` route와 AI capability 노출만 비활성화
  - 기존 `/search/documents`와 기존 AI flow는 그대로 유지
- 5C 실패 시
  - `/tool/search`만 기존 placeholder로 되돌리고 backend surface는 유지 가능
- 모든 단계에서 Phase 4 approval/chat/conversation surface는 회귀 없이 유지되어야 한다

## Assumptions
- Phase 5는 전도메인 범위로 진행한다
- Docs-first가 아니라 공통 projection/contract를 먼저 만든다
- 구현 순서는 반드시 `5A -> 5B -> 5C`
- 비차단 리팩터링은 포함하지 않는다
- 이 파일 하나만 active plan으로 두고, 완료 후 planning log로 이관한다
