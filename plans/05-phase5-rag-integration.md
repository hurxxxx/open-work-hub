# Phase 5 — Internal Retrieval Orchestration + Remote Retrieval Infrastructure

## Context
Phase 5의 목표는 Docs / Meeting / PMS / Planner 전도메인 데이터를 검색 가능한 retrieval platform으로 묶고, 그 결과를 REST, AI tool, `/tool/search` UI까지 일관된 계약으로 노출하는 것이다.

이번 Phase에서 바뀌는 가장 큰 판단은 다음이다.

- **별도 RAG 서버를 제품 경계로 두지 않는다.**
- Doowon API/worker가 retrieval orchestration 코드의 정본이 된다.
- 원격으로 둘 것은 "플랫폼 전체"가 아니라 **Qdrant / embedding / OCR / optional rerank 같은 infra capability** 다.

이렇게 두는 이유는 Phase 5의 핵심 리스크가 검색 품질보다 **ACL 정합성, approval/runtime 정합성, 장애 추적성** 이기 때문이다. 별도 RAG 플랫폼을 제품 경계로 세우면, ACL projection / query-time grant 해석 / grounded answer / audit/trace 연결이 분산돼 오히려 초기에 불안정해진다.

이미 Phase 4에서 AI capability / MCP registry / approval / scoped conversation / event envelope / audit contract가 정리되어 있다. Phase 5는 그 계약을 흔들지 않고, retrieval 계층을 이 내부 LLM runtime에 자연스럽게 연결하는 단계다.

이 계획은 기존 "external RAG server + HTTP client" 가정에서 수정된 실제 실행 플랜이다.

## External Reference Patterns
아래는 2026-04 기준 공식 자료에서 확인한 유사 패턴과, 이 계획에서의 채택 방식이다.

- Qdrant는 다수 tenant를 위해 "수많은 collection"보다 **embedding model별 단일 collection + payload 기반 partitioning** 을 권장한다.
  - 채택: Phase 5 baseline은 `workspace_id` / `resource_type` / visibility metadata payload partitioning이다. workspace마다 collection을 따로 만들지 않는다.
  - 참고: https://qdrant.tech/documentation/manage-data/multitenancy/
- Qdrant는 filterable search에서 **payload index** 를 early 생성하는 것이 중요하고, dense + sparse + rerank 구성을 공식적으로 지원한다.
  - 채택: Phase 5 baseline retrieval은 dense-only가 아니라 **hybrid retrieval(dense + sparse)** 이고, precision 문제가 있으면 optional rerank를 붙인다.
  - 참고: https://qdrant.tech/documentation/manage-data/indexing/
  - 참고: https://qdrant.tech/documentation/advanced-tutorials/reranking-hybrid-search/
- Azure AI Search의 security trimming 문서는 metadata filter가 **문서 권한을 "시뮬레이션"** 하는 것이지, 실제 인증/인가를 대체하지 않는다고 명시한다.
  - 채택: Qdrant metadata pre-filter는 성능 최적화 수단으로만 본다. **실제 ACL 경계는 Doowon access helper post-filter** 다.
  - 참고: https://learn.microsoft.com/en-us/azure/search/search-security-trimming-for-azure-search
- OpenTelemetry는 GenAI span / event / metric semantic convention을 별도로 정의하고 있다.
  - 채택: retrieval / embedding / rerank / grounded answer / tool call을 trace 하나로 묶고, `llm_call` / `llm_tool_call` audit와 correlation한다.
  - 참고: https://opentelemetry.io/docs/specs/semconv/gen-ai/
- LangGraph는 human-in-the-loop를 위해 checkpoint persistence를 정본으로 둔다. OpenAI도 장시간 reasoning에 background execution을 분리한다.
  - 채택: Doowon은 이미 Phase 4의 snapshot/approval runtime을 갖고 있으므로, Phase 5에서 별도 agent server/runtime을 도입하지 않는다. 장시간 synthesis가 필요하면 Phase 6 `LlmJob` 경로로 보내고, Phase 5 query 자체는 sync path를 유지한다.
  - 참고: https://docs.langchain.com/oss/python/langgraph/persistence
  - 참고: https://developers.openai.com/api/docs/guides/background
- OpenAI Responses는 structured JSON output과 tool state를 정교하게 다룬다.
  - 채택: grounded answer는 자연어 blob이 아니라 **schema-validated citation DTO** 로 먼저 만들고, 그 위에 renderer를 얹는다. provider native structured output이 있으면 활용하고, 없으면 internal schema validation으로 강제한다.
  - 참고: https://platform.openai.com/docs/api-reference/responses/compacted-object

## Architecture / Principles
- Doowon은 retrieval control plane이자 ACL 진실원이다.
  - resource payload 정규화
  - chunking 계획
  - visibility projection 생성
  - requester access context 생성
  - provider orchestration
  - 결과 후처리 및 hit 재검증
  - grounded answer synthesis
  - audit / trace correlation
- 원격 의존성은 monolithic "RAG 서버"가 아니라 capability별 provider adapter로 둔다.
  - `QdrantClient`
  - `EmbeddingClient`
  - `OcrClient`
  - `AsrClient` (필요 시)
  - `RerankClient` (optional)
- `core/rag_client.py` 같은 단일 HTTP client를 Phase 5의 주 abstraction으로 두지 않는다.
  - 대신 `domains/rag/` 내부 service + provider port 구조를 사용한다.
  - 외부 monolithic retrieval service가 필요해지면 나중에 `ExternalRagAdapter` 를 같은 port에 끼운다.
- provider SDK/HTTP 상세는 `domains/rag/providers/` 안에만 가둔다.
  - router / AI tool handler / application service는 provider port + DTO만 의존한다.
  - provider별 payload, auth header, SDK 타입이 상위 레이어로 새지 않게 한다.
- ingest와 query는 경로를 명확히 분리한다.
  - `ingest / delete / visibility_update / backfill / reindex` 는 queue + worker
  - `query / grounded-answer` 는 sync request path
- query sync path는 timeout / retry / circuit-breaker / degraded fallback을 가진다.
  - query를 worker에 넣어 UX를 깨뜨리지 않는다.
  - timeout budget을 넘기면 grounded answer를 포기하고 search-only degrade가 가능해야 한다.
- projection에는 "grant exists" 사실만 싣고, grant 만료/활성 판정은 query 시점 requester access context에서만 해석한다.
- raw share token은 외부 infra로 보내지 않는다.
  - 내부에서만 검증하고, 외부에는 `link_share_ref` 같은 파생 ref만 싣는다.
- **pre-filter는 optimization, post-filter는 enforcement** 로 명시한다.
  - Qdrant metadata filter는 검색량 축소와 latency 최적화 수단이다.
  - Doowon access helper 재검증이 실제 ACL 경계다.
  - projection이 stale일 수 있다는 가정이 항상 우선한다.
- retrieval baseline은 dense-only가 아니라 hybrid로 잡는다.
  - dense semantic retrieval
  - sparse keyword retrieval
  - optional rerank / late-interaction
- collection 전략은 "workspace별 collection"이 아니라 "embedding model/revision별 collection + payload partitioning" 이다.
  - collection 내부 vector schema는 dense + sparse named vector를 함께 둔다. query는 두 named vector를 병행 사용하는 hybrid retrieval을 baseline으로 삼는다.
  - coarse partition key는 최소 `workspace_id`
  - 추가 payload는 `resource_type`, `source_kind`, owner/share/grant refs, visibility summary
  - 특정 대형 workspace가 커지면 Qdrant tiered multitenancy/dedicated shard는 후속 운영 결정으로 남긴다.
- Qdrant payload index는 query hot path에 쓰는 필드만 대상으로 early 생성한다.
  - `workspace_id`
  - `resource_type`
  - `source_kind`
  - access-context filter에 실제로 쓰는 high-selectivity visibility field
- 기존 Phase 4 AI 계약은 유지한다.
  - `AiCapabilityDescriptor`
  - `LlmTaskContext`
  - `/ai/chat/stream`, `/ai/chat/resume`
  - `/ai/conversations`
  - approval state machine
- observability는 audit-only가 아니라 trace-first로 설계한다.
  - API request, outbox enqueue, worker sync, provider call, grounded-answer span을 한 trace로 연결한다.
  - 비동기 경계는 W3C `traceparent` 또는 동등한 trace context를 job payload로 전달한다.
  - audit row는 사후 감사/정책 기록이고, runtime causality 추적은 trace가 담당한다.
- retrieval tool은 read-only다.
  - approval/write flow를 retrieval에 섞지 않는다.
  - `rag.query` 자체가 side effect를 만들지 않는다.
- retrieval tool 노출은 turn/step/context-aware로 좁힌다.
  - 모든 AI turn에 `rag.query` / `rag.list_sources` 를 항상 노출하지 않는다.
  - `/tool/search`, search-oriented intent, 검색 보강이 필요한 대화 turn에서만 active tool subset에 포함한다.
  - provider가 native active-tools 제어를 지원하지 않아도 서버가 tool spec을 필터링한다.
- grounded answer는 Doowon 내부 LLM runtime이 만든다.
  - `task_kind = "rag_grounded_answer"`
  - Phase 4 policy routing / PII gate / audit를 그대로 탄다
  - retrieval 결과는 LLM prompt context이자 audit-linked artifact다
- grounded answer는 schema-validated contract를 가진다.
  - 예: `answer_text`, `citations`, `unsupported_claims`, `sources_used`
  - provider가 strict structured output을 지원하면 그걸 사용한다
  - 아니면 tool-call/fallback + server-side validation으로 동일 contract를 강제한다
- Phase 5는 별도 agent runtime / LangGraph server / hosted RAG platform을 도입하지 않는다.
  - LangChain / LlamaIndex / LangGraph는 필요하면 library 단위로만 쓴다
  - ACL / conversation persistence / approval / audit의 진실원은 Doowon 내부 구현이다

## 구현 단계

### 5A — Foundation: Contracts + Projection + Provider Ports + Sync
목표는 Doowon 내부에 retrieval orchestration의 정본 경계를 만들고, 원격 infra와 안전하게 동기화/호출할 기반을 만드는 것이다. 이 단계에서는 UI를 건드리지 않고, contract / sync correctness / observability를 먼저 닫는다.

구현:
- 5A 내부 실행 순서
  1. 공통 DTO / provider port / sync contract / trace schema 먼저 고정
  2. Docs 도메인으로 vertical slice(E2E ingest + query + ACL 검증) 먼저 통과
  3. 동일 패턴을 Meeting / PMS / Planner에 복제
- 신규 모듈 추가
  - `apps/api/src/aidoo_api/domains/rag/contracts.py`
  - `apps/api/src/aidoo_api/domains/rag/service.py` — projection build + chunking/ingest orchestration
  - `apps/api/src/aidoo_api/domains/rag/query_service.py` — sync retrieval + grounded-answer orchestration
  - `apps/api/src/aidoo_api/domains/rag/projection.py`
  - `apps/api/src/aidoo_api/domains/rag/providers/`
  - `apps/worker/src/aidoo_worker/tasks/rag_sync.py`
- provider port 정의
  - `VectorIndexClient`
  - `EmbeddingClient`
  - `OcrClient`
  - `AsrClient`
  - `RerankClient`
- provider 구현 경계
  - concrete SDK/HTTP client는 `domains/rag/providers/` 아래 구현체로만 둔다
  - `service.py`, `query_service.py`, REST router, AI tool handler는 port interface와 DTO만 import한다
- settings 추가
  - `AIDOO_RAG_ENABLED`
  - `AIDOO_RAG_UI_ENABLED`
  - `AIDOO_RAG_QUERY_TIMEOUT_MS`
  - `AIDOO_RAG_GROUNDED_ANSWER_TIMEOUT_MS`
  - `AIDOO_QDRANT_URL`
  - `AIDOO_QDRANT_API_KEY`
  - `AIDOO_QDRANT_COLLECTION_PREFIX`
  - `AIDOO_EMBEDDING_PROVIDER`
  - `AIDOO_OCR_PROVIDER`
  - `AIDOO_RERANK_PROVIDER`
- projection layer 추가
  - Docs: owner, direct share, link share ref, meeting grant, workspace/container context
  - Meeting: metadata, summary, transcript, insights, participant visibility
  - PMS: issue, description, comments, label/list/milestone context, issue access grant
  - Planner: title, description, location, time, owner/public visibility
- sync outbox/job 추가
  - resource-granular sync row: `rag_sync_jobs`
  - cascade visibility recompute producer row: `rag_visibility_recompute_jobs`
  - `rag_sync_jobs`: `lane`, `resource_type`, `resource_id`, `workspace_id`, `operation`, `content_checksum`, `visibility_checksum`, `trace_context`, `status`, `attempts`, `last_error`, `next_retry_at`
  - `rag_sync_jobs.lane`은 최소 `realtime | backfill`
  - `rag_sync_jobs.operation`은 최소 `upsert | delete | visibility_update`를 포함한다
  - `rag_visibility_recompute_jobs`: `scope_type`, `scope_id`, `workspace_id`, `trace_context`, `cursor`, `status`, `attempts`, `last_error`, `next_retry_at`
- write/change path는 provider를 직접 호출하지 않고 sync job만 enqueue
- sync enqueue는 도메인 write와 같은 DB 트랜잭션에서 커밋되는 transactional outbox를 전제로 한다
- outbox는 enqueue 시점의 trace context를 함께 저장해 worker span이 원 요청 trace에 이어 붙도록 한다
- pending outbox는 best-effort dedupe를 적용한다
  - 같은 resource/lane의 pending sync job은 새 row를 늘리지 않고 `delete > upsert > visibility_update` 우선순위로 병합한다
  - 같은 scope의 pending visibility recompute job은 cursor를 merge하고 새 row를 늘리지 않는다
- enqueue 대상은 content 변경뿐 아니라 ACL-only 변경 경로도 포함한다
  - link share revoke/rotate
  - doc-meeting grant 변경
  - meeting participant 변경
  - issue grant 변경
  - planner private/public 토글
- workspace membership churn 같은 query-time principal 변화는 기본적으로 per-resource enqueue 대상이 아니다
- projection payload 자체가 바뀌는 cascade ACL 변경은 per-resource fan-out 대신 별도 bulk visibility recompute lane으로 처리한다
- worker가 job을 소비해 extraction / chunking / embedding / vector upsert / delete 를 수행한다
- binary 처리 원칙
  - raw binary 자체를 vector store에 저장하지 않는다
  - Doowon은 signed URL 또는 storage ref를 통해 OCR/ASR provider를 호출하고, 추출 텍스트를 정규화해 chunking한다
  - Meeting transcript는 우선 기존 Phase 4 pipeline 산출물을 재사용하고, 외부 ASR은 future binary source용 capability로 남긴다
- collection bootstrap 원칙
  - embedding model/revision별 collection 생성
  - dense + sparse named vector schema를 collection 생성 시점에 함께 고정
  - hot filter field payload index를 ingest 전에 생성
  - strict mode / index completeness 검증을 bootstrap 단계에서 체크
- 초기 대량 적재(backfill/reindex)는 chunked/throttled 전용 lane으로 처리하고, 일반 write sync queue와 분리한다
  - backfill worker는 작은 batch를 순차 drain하고 job 사이에 throttle을 걸어 realtime lane과 자원 경합을 낮춘다
- worker queue는 최소 다음 3개 lane으로 분리한다
  - `rag_sync_realtime`
  - `rag_sync_backfill`
  - `rag_visibility_recompute`
- delete는 인덱스 hard-delete를 기본으로 한다
  - tombstone이 필요하면 Doowon 내부 sync 상태 추적용으로만 사용한다
- 5A observability를 선행 구축한다
  - `rag_sync_queue_depth`
  - `rag_sync_job_lag_ms`
  - `rag_ingest_latency_ms`
  - `qdrant_query_latency_ms`
  - `embedding_latency_ms`
  - `ocr_latency_ms`
  - `rerank_latency_ms`
  - `grounded_answer_latency_ms`
  - provider별 error rate / timeout count
- OpenTelemetry tracer/meter bootstrap을 API와 worker 양쪽에 깐다
  - request -> outbox enqueue -> rag_sync worker -> provider call span linkage를 검증 가능하게 만든다
  - provider adapter는 최소 `workspace_id`, `resource_type`, `source_kind`, `operation`, `provider_name` 수준의 span attribute를 공통 부여한다
- threshold는 이 단계에서 hard-code 하지 않는다
  - 먼저 metric / trace를 까고, 운영 데이터가 쌓인 뒤 SLO / alert threshold를 확정한다

주의:
- ACL truth는 도메인 service/access helper에서 읽고, projection에만 옮긴다
- 도메인 ACL 로직을 별도 규칙으로 재작성하지 않는다
- projection/visibility payload는 query acceleration을 위한 cache이지 최종 권한 판정기가 아니다

#### 5A 착수 체크리스트
5A는 한 번에 끝내는 큰 PR이 아니라 아래 6개 구현 단위로 나눠 진행한다. 각 단위는 독립 merge 가능해야 하고, 다음 단계를 막는 계약만 먼저 고정한다.

1. `5A-1 Skeleton + Settings + Fake Providers`
   - `domains/rag/` 패키지, `contracts.py`, `projection.py`, `providers/base.py`, `providers/fake.py`, `service.py`, `query_service.py` 스캐폴드를 만든다.
   - `AIDOO_RAG_*` settings와 feature flag 기본값을 추가한다.
   - provider SDK가 없어도 테스트 가능한 fake provider를 먼저 둔다.
   - 완료 기준: feature flag off 상태에서 앱 import/boot가 깨지지 않고, 상위 레이어가 provider port만 참조한다.
2. `5A-2 Persistence + Transactional Outbox + Queue Routing`
   - `rag_sync_jobs`, `rag_visibility_recompute_jobs` 모델과 alembic migration을 추가한다.
   - enqueue helper를 만들어 도메인 write 트랜잭션 안에서 job row를 기록한다.
   - Celery route에 `rag_sync_realtime`, `rag_sync_backfill`, `rag_visibility_recompute` queue를 추가한다.
   - 완료 기준: provider 호출 없이도 resource sync job / cascade recompute job이 DB와 queue에 정확히 기록된다.
3. `5A-3 OpenTelemetry Bootstrap + Trace Propagation`
   - API `app.py`와 worker `celery_app.py`에 tracer/meter bootstrap을 추가한다.
   - enqueue 시 현재 trace context를 serialize하고, worker가 이를 복원해 child span으로 이어 붙이게 만든다.
   - 공통 span attribute helper를 두어 `workspace_id`, `resource_type`, `source_kind`, `operation`, `provider_name`를 일관되게 기록한다.
   - 완료 기준: 테스트에서 request span -> outbox enqueue -> worker span linkage를 같은 trace ID로 검증할 수 있다.
4. `5A-4 Docs Vertical Slice`
   - Docs projection builder와 ACL-only mutation enqueue hook을 먼저 완성한다.
   - collection bootstrap, payload index bootstrap, chunking, embedding, vector upsert/delete의 첫 vertical slice를 Docs로 닫는다.
   - `sync_projection()`은 현재 chunk set을 upsert한 뒤 tail stale chunk를 prune해서, 본문 축소나 chunk 경계 변경 후에도 orphan vector가 남지 않게 한다.
   - 내부 `query_service.py`를 이용해 REST/UI 없이도 ingest -> query -> post-filter가 도는 smoke path를 만든다.
   - query path는 post-filter가 켜질 때 retrieval top-k를 oversample해서, 접근 불가 hit가 상단을 점유해도 접근 가능한 hit를 복구할 수 있게 한다.
   - 완료 기준: Docs direct share / link share / meeting grant / revoke / expiry 시나리오가 fake provider와 실제 adapter smoke 양쪽에서 통과한다.
5. `5A-5 Meeting / PMS / Planner Parity`
   - Meeting, PMS, Planner projection builder와 enqueue hook을 같은 패턴으로 확장한다.
   - Meeting projection은 meeting row 자체만이 아니라 최신 recording의 summary/transcript를 포함하고, 참가자 변경/recording 파이프라인 갱신이 같은 sync contract로 이어져야 한다.
   - workspace/container/grant 변경이 projection payload를 바꾸는 경우 `rag_visibility_recompute_jobs` producer를 연결한다.
   - 완료 기준: 네 도메인 모두 resource sync contract를 공유하고, cascade ACL 변경이 realtime lane을 압도하지 않는다.
6. `5A-6 Hardening + Readiness Gate`
   - retry / idempotency / dedupe / collection readiness check를 정리한다.
   - worker failure는 `next_retry_at` + bounded Celery retry로 다시 올리고, max-attempts 초과 poison message는 terminal dead-letter 상태로 격리한다.
   - provider import-boundary test, metric/trace smoke test, worker queue routing test를 닫는다.
   - 5B로 넘어가기 전 "Docs-first vertical slice + 전도메인 projection enqueue + trace propagation" 세 조건을 exit gate로 건다.

### 5B — Product Surface: Workspace RAG API + AI Capability + Grounded Answer
목표는 retrieval 결과를 제품 surface로 노출하는 것이다. 이 단계에서 REST와 AI tool contract를 먼저 고정하고, grounded answer 생성/검증/감사 경계를 Phase 4 runtime과 연결한다.

구현:
- workspace-scoped REST 추가
  - `POST /api/v1/workspaces/{slug}/rag/query`
  - `GET /api/v1/workspaces/{slug}/rag/sources`
  - `POST /api/v1/workspaces/{slug}/rag/reindex` 는 admin/internal only
- AI capability 등록
  - `rag.query`
  - `rag.list_sources`
- 등록 원칙
  - `register_ai_capabilities(registry)` 경로만 사용한다
  - REST DTO와 AI DTO를 섞지 않는다
  - read tool이므로 `approval_required=False`
- `rag.list_sources`는 access-context-aware로 동작하며 요청자가 조회 가능한 `source_kind` / domain-level source 목록만 반환한다
  - 개별 리소스 나열 API로 쓰지 않고, UI filter seed 용도로 제한한다
- REST와 AI tool은 같은 retrieval service를 호출한다
- AI runtime은 turn/step 단위 active tool subset을 구성한다
  - retrieval intent가 없는 일반 대화 turn에는 `rag.query` / `rag.list_sources` 를 숨긴다
  - `/tool/search` 진입, 명시적 검색 요청, planner/docs/meeting/pms 검색 보강 turn에서만 retrieval tool을 노출한다
  - provider가 native active tool selection을 지원하지 않아도 Doowon이 tool spec 목록을 서버에서 줄여서 전달한다
- query flow 고정
  1. Doowon이 requester access context 구성
  2. query text를 dense / sparse retrieval input으로 변환
  3. Qdrant에 workspace / source / visibility metadata pre-filter를 포함해 query 수행
  4. 필요 시 rerank stage 수행
  5. retrieval service가 반환 hit를 access helper로 재검증하고 접근 불가 hit를 제거
  6. `answer_mode=grounded-answer` 이면 Doowon 내부 LLM runtime이 filtered hit만으로 grounded answer 생성
- query path는 sync로 유지하되 resilience를 명시한다
  - provider timeout
  - bounded retry
  - circuit-breaker
  - grounded-answer만 실패하면 search-only degrade
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
- grounded answer contract는 별도 DTO로 강제
  - `text`
  - `citations`
  - `unsupported_claims`
  - `sources_used`
- grounded answer runtime 규칙
  - `rag_grounded_answer`용 LLM policy seed 추가
  - pool routing 및 external policy일 때 PII gate 적용 여부 명시
  - grounded answer는 retrieval hit 바깥의 사실을 새로운 근거 없이 단정하지 못한다
  - citation span이 없는 claim은 기본적으로 최종 answer text에서 제거하고, `unsupported_claims`에는 debug/audit 용도로만 남긴다
- AI chat path와의 연계 원칙
  - `rag.query` tool 결과는 REST와 동일한 contract를 반환한다
  - 별도 외부 agent memory/runtime을 추가하지 않는다
  - conversation state / approval / resume 정본은 Phase 4 snapshot/runtime 그대로 유지한다
  - retrieval 관련 `trace_id`는 conversation turn meta / audit와 연결 가능해야 한다
- audit / trace 연계
  - retrieval `trace_id`를 `llm_call` / `llm_tool_call` payload와 연결
  - provider span, query span, grounded-answer span을 같은 trace로 묶는다
  - OpenTelemetry GenAI semantic convention 채택 범위를 문서화한다
  - span attribute에는 최소 `conversation_id`, `agent_run_id`, `tool_name`, `workspace_id`, `answer_mode`, `provider_name`를 포함한다
- 기존 `/api/v1/search/documents` 는 legacy/demo surface로 유지한다
  - 새 surface와 연결하지 않는다

주의:
- retrieval tool은 read-only로 유지한다
- Phase 4 approval/write flow를 retrieval에 섞지 않는다
- query rewrite / multi-hop agentic retrieval loop는 baseline 범위에 넣지 않는다
  - 필요하면 feature flag로 후속 실험한다

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
  - grounded-answer failure 시 search-only degraded state
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
- ACL-only mutation이 `visibility_update` job enqueue되는지 검증
- `content_checksum` / `visibility_checksum` idempotency 분리 검증
- sync job enqueue / idempotency / retry tests
- `rag_visibility_recompute_jobs` producer / cursor / fan-out tests
- transactional outbox -> worker `trace_context` propagation tests
- Celery queue routing tests (`realtime`, `backfill`, `bulk visibility`)
- backfill lane chunk/throttle 및 일반 sync lane 격리 검증
- delete hard-delete 동작 검증
- provider adapter contract tests
- provider SDK import boundary tests
- collection bootstrap / payload index / strict-mode readiness tests
- extraction / chunking / embedding serialization tests
- Docs vertical slice ingest/query smoke tests
- metric / trace emission smoke tests

5B:
- fake provider contract tests
- workspace ACL no-leak tests
- expired grant exclusion tests
- pre-filter hit가 남아도 post-filter에서 제거되는 defense-in-depth test
- hybrid retrieval + optional rerank path tests
- query timeout / retry / circuit-breaker tests
- `rag.list_sources` access-context-aware visibility tests
- `rag.query` AI tool tests
- turn/step-level retrieval tool exposure narrowing tests
- grounded answer synthesis tests with mocked local LLM
- grounded answer schema validation / citation-only answer tests
- `rag_grounded_answer` policy seed / PII gate 적용 tests
- retrieval `trace_id`와 audit event 연계 tests
- request span -> tool call span -> grounded answer span linkage tests
- legacy `/search/documents` unchanged regression

5C:
- `/tool/search` route render
- search-only / grounded-answer mode tests
- cross-domain hit rendering
- citations / source badges
- source filters
- degraded error state
- AI tool result renderer regression
- Playwright
  - 접근 가능한 Docs hit 노출
  - 접근 불가 Docs hit 비노출
  - meeting transcript hit 노출
  - PMS private issue 비노출
  - grounded answer + citation render

### 단계별 E2E 전략
- `5A`는 브라우저 E2E보다 service/integration test를 우선한다
  - 대상: projection builder, transactional outbox, worker queue routing, provider smoke, post-filter
  - 이유: 이 단계의 핵심 불변식은 UI보다 `ACL projection + state transition + async fan-out` 이기 때문이다
- `5A-4` 종료 시점에는 Docs vertical slice 기준으로 `ingest -> sync worker -> query_service -> post-filter` service-level E2E를 닫는다
- `5A-5` 종료 시점에는 Meeting / PMS / Planner의 cross-domain integration test를 닫는다
  - 대상: ACL-only mutation이 `rag_sync_jobs` / `rag_visibility_recompute_jobs`로 정확히 fan-out 되는지
- `5B`에서는 workspace-scoped REST와 AI capability가 붙는 즉시 API-level E2E를 추가한다
  - 대상: `POST /rag/query`, `GET /rag/sources`, pre-filter + post-filter, grounded-answer degrade
- `5C`에서 `/tool/search` UI가 붙으면 browser E2E를 본격화한다
  - 대상: 검색 입력, source filter, citation click, 접근 불가 hit 비노출, grounded-answer 실패 시 search-only degrade, workspace switch isolation
- 브라우저 E2E는 `agent-browser` 기준으로 수행하고, 결과는 관련 작업 문서나 루트 작업 기록에 간단히 남긴다

### 수동 검증
- 같은 질의를 REST, AI tool, `/tool/search` 세 surface에서 호출했을 때 hit set과 citation 구조가 실질적으로 일치하는지 확인
- 만료된 grant 이후 다음 query부터 결과에서 즉시 빠지는지 확인
- grounded answer가 citation 없는 claim을 내지 않는지 spot check
- provider 장애 시
  - REST는 explicit unavailable/error 또는 search-only degrade
  - AI는 tool error 후 fallback assistant 응답
  - UI는 graceful empty/error/degraded state
- 운영 대시보드에서 최소 다음 metric이 보이는지 확인
  - retrieval latency
  - queue depth / lag
  - provider error rate
  - grounded-answer latency
  - Qdrant latency

## 결정 로그
확정:
- Phase 5는 단일 계획 파일로 관리하되, 구현은 5A / 5B / 5C로 분할한다
- Phase 5의 retrieval orchestration 코드는 Doowon 내부(API/worker)에 둔다
- Qdrant / embedding / OCR / optional rerank는 원격 infra/provider로 둔다
- monolithic external RAG server는 Phase 5 baseline에서 채택하지 않는다
- `core/rag_client.py` 단일 HTTP client 대신 `domains/rag/` service + provider port 구조를 사용한다
- provider SDK/HTTP 상세는 `domains/rag/providers/` 내부에만 두고 상위 레이어는 port + DTO만 의존한다
- resource-granular sync와 cascade visibility recompute는 `rag_sync_jobs` / `rag_visibility_recompute_jobs`로 분리한다
- ingest / delete / visibility_update / backfill 은 queue + worker 경로를 사용한다
- query / grounded-answer 는 sync request path를 유지한다
- pre-filter는 성능 최적화이고, post-filter(access helper 재검증)가 primary enforcement다
- projection에는 grant 존재 사실을 저장하고, grant 만료/활성 판정은 query 시점 access context에서 수행한다
- raw share token은 외부로 보내지 않고 `link_share_ref` 만 보낸다
- collection 전략은 workspace별 분리보다 embedding model/revision별 collection + payload partitioning을 기본으로 한다
- retrieval baseline은 hybrid(dense + sparse)로 잡고 optional rerank를 허용한다
- grounded answer는 Doowon LLM이 생성하며 `rag_grounded_answer` task kind로 Phase 4 policy/audit/runtime과 연결한다
- grounded answer는 schema-validated citation contract를 사용한다
- observability는 OpenTelemetry 기반 trace-first로 두고, audit는 보조 correlation record로 유지한다
- retrieval tool은 turn/step/context-aware active subset으로 노출한다
- metric / trace를 먼저 구축하고, threshold/SLO는 운영 데이터가 쌓인 뒤 고정한다
- LangChain / LlamaIndex / LangGraph는 필요 시 library 단위로만 사용하고, 제품 런타임/ACL 진실원으로 채택하지 않는다
- 기존 `/api/v1/search/documents` 는 legacy/demo로 유지한다
- 기존 Phase 4 approval/conversation contract는 유지한다

후속 결정:
- embedding / rerank provider의 1차 선택
- binary OCR provider별 signed URL / retry 전략
- Qdrant strict mode / payload index 세부 필드 셋
- 특정 대형 workspace에 dedicated shard를 적용할지 여부
- Phase 6 `LlmJob` 와 grounded-answer background escalation 연결 여부

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
- provider 일부 장애 시
  - search-only degrade 또는 explicit unavailable을 우선하고, ACL 경계는 절대 완화하지 않는다
- 모든 단계에서 Phase 4 approval/chat/conversation surface는 회귀 없이 유지되어야 한다

## Assumptions
- Phase 5는 전도메인 범위로 진행한다
- Docs-first가 아니라 공통 contract / provider port / observability를 먼저 만든다
- 구현 순서는 반드시 `5A -> 5B -> 5C`
- write -> sync -> index 사이에는 eventual consistency lag가 존재하며, 신규/변경 리소스가 즉시 검색되지 않을 수 있다
- 단, query 시점 access context + Doowon post-filter를 통해 만료/회수된 권한은 다음 query부터 결과에서 제외되어야 한다
- retrieval precision 향상 실험은 허용하지만, ACL 경계 / audit / trace / answer contract를 우회하는 실험은 허용하지 않는다
- 이 파일 하나만 active plan으로 두고, 완료 후 planning log로 이관한다
