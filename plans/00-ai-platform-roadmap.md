# Doowon AI Platform — 마스터 로드맵

> **이 문서의 성격**: 7개 Phase로 구성된 AI 플랫폼 구축의 **최상위 로드맵**이다.
> 각 Phase의 상세 실행 계획은 **해당 Phase 킥오프 시점에 개별 플랜 파일**로 작성한다.
> 본 문서는 방향·원칙·Phase 경계·공통 제약만 담는다.

---

## Context

프로젝트(aidoo-portal)의 AI 레이어를 인프라부터 제품 UX까지 새로 설계한다.

### 현재 상태
- 로컬 LLM: Ollama → **mlx-lm (Qwen3.6-35B-A3B-4bit)** 전환 완료. 프리필 3.1×, 생성 1.6× 개선.
- LLM 호출 계층: `primary(local) → fallback(external)` 자동 크로스풀 폴백 — **보안 정책 위반**.
- 업무 도메인 4개(PMS, Meeting, Planner, Docs) 이미 풍부한 엔드포인트(합계 90+). AI 기능은 회의록 자동 요약 1개뿐.
- 챗봇 UI: 동기식·비스트리밍·도구 호출 없음.

### 목표
- 정책 기반 풀 라우팅 + 워크스페이스 격리 기반 AI 플랫폼.
- agent + tool calling + RAG 기반 업무 챗봇.
- 회의·문서·일정·태스크 전체를 챗으로 조작 가능한 UX.
- 사내문서 RAG는 별도 서비스로 분리, 툴 호출로 연동.
- 전사는 초기 외부 API → 장기적으로 로컬.

### 업계 방향 참조
- **Atlassian Rovo**: Transcript Insights Reporter, Jira/Confluence agent
- **Microsoft 365 Copilot**: agentic workflow automation
- **Glean**: universal search + actions
공통 패턴: **agent + tool calling + RAG**. 본 플랜도 이 방향.

---

## 아키텍처 원칙 (모든 Phase 공통)

### 1. Pool 독립 (크로스풀 폴백 금지)
```
LOCAL POOL ────┐                    ┌──── EXTERNAL POOL
(mlx-lm)       │    ❌ 자동 폴백     │     (OpenRouter → Anthropic/OpenAI)
               │        금지         │
               └─────────────────────┘
        task_kind → DB policy → 한 쪽 풀 지정
```
- Task-level policy (DB), 관리자 편집 가능.
- LOCAL_ONLY 실패 → 503 + audit + 관리자 알람. 조용한 external fallback 금지.

### 2. Tool = ACL 경계
- LLM이 시킨 것이라도 실제 리소스 접근은 기존 `access.py` 검사 통과 필수.
- LLM은 ACL 우회 불가. 툴이 곧 보안 경계.

### 3. 모든 호출 감사
- `llm_call` (LLM 요청 단위) + `llm_tool_call` (도구 호출 단위) 분리 기록.
- 기존 `AuditLog` + `record_audit_log()` 재사용.

### 4. Workspace 스코프 강제 + LlmTaskContext
- 모든 LLM 요청은 **`LlmTaskContext`**(dataclass)를 구성해서 흘려보낸다:
  - `source`: 호출 경로 식별자 (아래 표 참조)
  - `actor_user_id`: UUID | None (source에 따라 결정, 아래 표 참조)
  - `workspace_id`: UUID (worker도 resource에서 유도)
  - `task_kind`: **업무 종류 식별자**. source와 분리한다.

#### source vs task_kind
| 개념 | 의미 | 예 |
|---|---|---|
| `source` | 어느 호출 경로에서 LLM이 불렸는지 | `api.chat`, `api.stream`, `worker.meeting.summarize` |
| `task_kind` | 어떤 업무 유형 정책을 적용할지 | `chatbot`, `meeting_summary`, `batch_generation` |

#### Source → actor 정책
| source | actor_user_id | workspace_id 유도 |
|---|---|---|
| `api.chat` | `current_user.id` (필수) | request dependency에서 바인딩된 workspace |
| `api.stream` (P2+) | `current_user.id` (필수) | 동일 |
| `api.jobs.submit` (P6) | `current_user.id` (필수) | 동일 |
| `worker.meeting.summarize` | `None` (system-triggered) | `recording.meeting.workspace_id` |
| `worker.llm_batch` (P6) | `job.created_by` (user-initiated) | `job.workspace_id` |
| 기타 worker | user-initiated면 id 보존, system-triggered면 None | 원본 리소스 FK |

- 모든 tool이 `LlmTaskContext.workspace_id`로 쿼리 제한. 크로스 워크스페이스 데이터 접근 원천 불가.
- 현재 `/ai/*` 보호는 **route 함수 내부가 아니라 `app.include_router(...)`의 app-level dependency 체인**에 걸려 있다 ([`app.py:93-110`](../apps/api/src/aidoo_api/app.py#L93-L110)). legacy 경로와 `/workspaces/{slug}` 경로로 **2중 mount**되어 있어 둘 다 회귀 대상.
- P1 목표는 "없는 인증 추가"가 아니라 이 보호 체인을 **LLM foundation 계약으로 명시**하고, 신규 `/ai/health`와 `/ai/chat/stream`(P2)·`/ai/jobs`(P6)까지 동일 체인을 회귀 테스트로 고정하는 것.
- **예외**: `/healthz`, `/readyz`는 system liveness probe로 무인증 허용 (LB health check 용도). 보호 체인은 `/ai/*`에만 적용. 회귀 테스트에서 `/readyz` 공개 유지를 검증.
- 현재 워커는 `primary.ready`면 local, 아니면 fallback — **자동 크로스풀 폴백**. P1에서 제거.

### 5. PII 기본 탐지
- `external` 정책 task에 한해 정규식 탐지. hit 시 LOCAL_ONLY 강제.
- 값 자체 마스킹은 현재 범위 밖 (차후 검토).

### 6. RAG는 외부 서비스 + Resource-level ACL Projection
- 별도 프로젝트, OpenAPI 계약.
- 본 프로젝트는 client + **문서 단위 visibility set 인제스트** + **요청 단위 principal_set 투영** 담당. 팀 ID 단일 필드 필터 금지 (Docs ACL = owner + direct_share + link_share + meeting_grant 복합).
- 단, **raw link-share token은 Doowon 경계를 벗어나지 않는다**. 외부 RAG 서비스에는 token 자체 대신 `link_share_ref`(예: 내부 share_id 또는 stable HMAC digest) 같은 파생 식별자만 전달한다.

## P3 Entry Contracts

Phase 3로 넘어가기 전에 아래 4개 계약을 먼저 고정한다. 목표는 새 앱, 새 AI capability, 외부 클라이언트 연계를 추가할 때 `domains/ai/*` 또는 특정 프론트 화면을 중심으로 다시 뜯지 않도록 만드는 것이다.

### 1. Workspace bootstrap = 앱 셸 진실원
- `/api/v1/auth/me`는 **identity-only** 계약을 유지한다. 사용자 신원, 시스템 역할, workspace 목록만 포함한다.
- 새 `GET /api/v1/workspaces/{workspace_slug}/bootstrap`가 workspace별 앱 노출, sidebar/nav 메타데이터, entitlement를 제공하는 단일 진실원이 된다.
- 프론트는 bootstrap 응답으로 AppBar/SubSidebar/route gating을 구성한다.
- 서버는 **메타데이터와 entitlement만** 결정한다. 실제 컴포넌트 매핑은 프론트 로컬 registry가 소유한다.
- 글로벌 앱 카탈로그는 코드 소유, workspace별 활성화 여부는 `WorkspaceAppEntitlement` DB 소유로 분리한다.
- 기존의 "workspace membership이면 모든 앱 허용" 규칙은 폐기한다.

### 2. 도메인 소유 AI capability 등록
- 각 도메인은 선택적으로 `register_ai_capabilities(registry)` 훅을 노출한다.
- AI registry는 최소 `task_kind`, `tool definitions`, `approval-required operations` 메타데이터를 수집한다.
- `task_kind` seed, readiness, policy lookup은 registry 기반으로 동작한다.
- 새 도메인 capability 추가 시 `domains/ai/*`를 직접 수정하지 않는다. 도메인 훅만 추가하고 registry bootstrap이 이를 합류시킨다.
- 자동 파일 스캔 기반 discovery는 도입하지 않는다. 등록 대상 도메인은 부트스트랩 코드에서 명시적으로 관리한다.

### 3. Application service layer를 단일 진입점으로 고정
- router와 AI tool은 같은 application service를 호출한다.
- 우선 대상 도메인은 `pms`, `meeting`, `docs`, `planner`다.
- 서비스 계층은 raw DB helper가 아니라 `workspace + principal + input`을 받는 application boundary로 둔다.
- 외부 API, 웹 프론트, AI tool, worker는 동일 서비스 경계를 재사용하는 것을 원칙으로 한다.

### 4. CallerPrincipal + external hub 호환성
- 공통 타입 `CallerPrincipal`을 도입한다.
- 최소 필드는 `kind(user|service_account|system)`, `workspace_id`, `user_id?`, `service_account_id?`, `session_id?`, `source`다.
- LLM context와 audit payload는 principal-aware로 유지한다.
- 외부 소비자 모델은 `workspace` 에 귀속된 `ServiceAccount` 를 기본으로 하고, 인증 수단은 API key 호환 경로와 OAuth 2.1 호환 경로를 모두 수용할 수 있게 설계한다.
- rate limit, webhook, 공개 문서 포털은 뒤 Phase로 미루되, 현재 구조가 이 요구를 막지 않도록 설계한다.

---

## Phase 로드맵

> 각 Phase는 독립 머지 가능하지만 **병렬 가능은 제한적**이다:
> - **P1 → 전부의 전제** (LlmTaskContext 없으면 다음 Phase들이 actor/workspace 재설계 필요).
> - **P2의 AgentEventEnvelope → P3·P4의 전제** (이벤트 계약 없이 tool/approval 렌더 불가).
> - **P3의 service layer → P4의 전제** (write 툴도 같은 service 쓰기).
> - **P5의 ACL Projection 설계 → P1 LlmTaskContext와 연결** (principal_set 주입점 공유).
> - **P6만 P2 이후 비교적 독립적** (UI 확장, 기존 감사 로그 활용).
>
> Phase 킥오프 시점에 `NN-phaseX-<slug>.md` 형식의 **상세 플랜 파일**을 [`plans/`](./) 디렉터리에 작성한다 (명명 규칙은 [`plans/README.md`](./README.md) 참조).

### Phase 1 — Foundation (LLM Request Context + Pool Routing)
**목표**: 풀 라우팅만이 아니라 **LLM 요청 아이덴티티(LlmTaskContext) + workspace 바인딩 + 감사 + 라우팅**을 묶은 진짜 foundation. 이 단계에서 빠지면 P3~P5에서 actor/workspace/system-job 정체성을 다시 뜯어야 한다.

**핵심 산출물**:
1. **LlmTaskContext dataclass** (`core/llm.py`) — source/actor_user_id/workspace_id/task_kind 필드. 모든 LLM 호출 진입점이 반드시 구성.
2. **AI route 보호 체인 명시화 + 회귀 고정**: `/ai/chat`과 `/ai/health`가 기존 app-level `require_current_user` + workspace membership dependency 뒤에만 mount되도록 고정. route/service 진입점에서 `LlmTaskContext` builder가 auth/workspace를 전제로 동작함을 문서화하고, 무인증 401 / 무워크스페이스 403 회귀 테스트 추가.
3. **워커 시스템-잡 정체성**: `worker/tasks/meeting.py`의 LLM 호출부를 `LlmTaskContext(source="worker.meeting.summarize", actor_user_id=None, workspace_id=recording.meeting.workspace_id, task_kind="meeting_summary")`로 전환. **자동 primary→fallback 로직 제거**.
4. **Settings 재구조** (`local_*` / `external_*` 분리).
5. **`LlmPolicy` DB 테이블** + 초기 seed + `resolve_policy()` 서비스.
6. **Routing 모듈 재작성** (`core/llm.py`): pool별 client + `choose_pool(task_kind, text_inputs, session)` → `(pool, PolicyDecision)`. **크로스풀 폴백 API 제거**.
7. **PII 탐지 모듈** (`core/pii.py`) — 정규식 기반. `external` 정책 task에만 적용, hit 시 `force_local_only`.
8. **Audit 통합** — `llm_call` action, payload에 LlmTaskContext + pool + model + status + pii_hits + tokens + latency.
9. **`/readyz` + `/api/v1/ai/health` + lifespan 전환** — 풀별 독립 상태. `/readyz`의 LLM 필드도 pool별 구조로. `app.py` startup health check도 `check_all_pools_health`/effective readiness 기준으로 정리. `/readyz`는 무인증 유지, `/ai/health`는 보호 체인 뒤.
10. **테스트**:
    - 크로스풀 폴백 금지 (API + worker 양쪽).
    - 워커 system-job `LlmTaskContext` 감사 검증 (actor_user_id=None, workspace_id는 resource에서 유도).
    - AI route 보호 체인 회귀: legacy 경로(`/api/v1/ai/chat`)와 slug 경로(`/api/v1/workspaces/{slug}/ai/chat`) **모두** 무인증 401 / 무워크스페이스 403.
    - `/readyz` 무인증 접근 유지 확인 (회귀 방지).
   - PII 강제: external 정책 task 입력에 주민번호 포함 → local 풀로 라우팅 + audit에 `pii_hits` 기록.

**완료 조건**: LOCAL_ONLY 작업이 절대 external 호출 안 함. 워커 호출도 동일 제약. PII hit 시 강제 local. 모든 호출 audit에 actor/workspace/source 포함. 기존 AI route 보호 체인이 회귀 없이 유지되고 신규 `/ai/health`도 동일 보호를 받음. 무인증 AI 호출은 401, workspace access 불가 시 403.

**상세 플랜 파일**: 완료 (fe23cff) — 요약은 [`docs/planning-log.md`](../docs/planning-log.md)

---

### Phase 2 — Agent Event Envelope + Streaming Chat UI
**목표**: 실시간 스트리밍만이 아니라 **agent-aware 이벤트 계약 설계 선행**. P3~P4에서 tool_call/approval 이벤트가 추가되어도 프론트 상태 모델 재작성이 불필요하도록.

**핵심 산출물**:
1. **AgentEventEnvelope 스펙 + 테스트** (첫 작업, 구현 전):
   - 이벤트 타입: `content_delta`, `reasoning_delta`, `tool_call_started`, `tool_call_args_delta`, `tool_result`, `approval_required`, `approval_resolved`, `usage`, `done`, `error`
   - 각 이벤트의 payload 스키마 확정 (Pydantic 모델).
   - 문서화 + 예제 JSON.
2. **SSE 엔드포인트**: `POST /ai/chat/stream` — Envelope 이벤트 중 **P2 구현 범위**(content_delta, reasoning_delta, usage, done, error)만 발행.
3. **의존성**: `sse-starlette`.
4. **`core/llm_adapters.py`**: provider-agnostic thinking/content delta 추출 (mlx-lm / OpenRouter / Anthropic).
5. **프론트**: `useChatStream()` 훅 + ChatThread / ThinkingPanel / MessageBubble 컴포넌트. Envelope 전체 이벤트 타입 모델링 (P3에서 tool/approval 추가 시 타입만 활성화).
6. **취소**: AbortController → 서버 disconnect → 모델 생성 중단.
7. **디자인 세션 선행**: `/design-consultation` 또는 디자이너 협업으로 DESIGN.md 산출 (P3 ToolCallCard / P4 ApprovalModal까지 커버).

**완료 조건**: Envelope 계약 확정(승인 가능한 스펙 문서). 토큰/thinking 실시간 스트리밍, 취소 동작, 기존 동기 `/chat` 회귀 없음. P3 작업 시 **Envelope 확장만** 필요하고 신규 이벤트 타입이나 프론트 상태 모델 재작성 불필요함을 리뷰로 검증.

**사전 작업**: 챗 UX 디자인 세션 (Envelope의 프론트 렌더 모델에도 영향).

**상세 플랜 파일**: 완료 (c30b818) — 요약은 [`docs/planning-log.md`](../docs/planning-log.md). 챗 뷰 디자인 기준은 [`DESIGN.md`](../DESIGN.md)에 고정.

---

### Phase 3 — Tool Service Layer + Tool Calling (Read)
**목표**: Agent 루프 + Read-only 툴. 단, **현재 도메인 로직이 거대한 router 함수에 박혀 있어서** 서비스 계층 추출이 선행되어야 재사용·테스트·ACL 일관성이 확보된다.

**핵심 산출물 (순서대로)**:
1. **Tool-facing service layer 추출** (첫 작업, 코드 이동):
   - `domains/pms/services/` — issue 검색/조회, space/list 조회, milestone/label/status 조회 등 router에서 분리.
   - `domains/meeting/services/` — meetings 조회, availability 계산 (현재 `meeting/router.py:466`에 있음) 분리.
   - `domains/planner/services/` — event 조회.
   - `domains/docs/services/` — hub/item/pages 조회 (아래 툴 네이밍 참조).
   - 기존 router는 service 호출로 얇아짐. 행동 변화 없음(리팩토링).
2. **Function-calling PoC** (두 번째 작업, 실험):
   - mlx-lm 서버가 OpenAI `tools` 파라미터 실제 수락하는지 측정.
   - 성공 시 정식 채택. 실패 시 JSON 프롬프트 fallback 파서 구현.
3. **TOOL_REGISTRY + 실행 파이프라인**: JSON Schema, permission precheck, AuthContext 주입, ACL 검사(기존 `access.py`), audit 기록.
4. **Read-only 툴 (현재 도메인 네이밍에 맞춤)**:
   - PMS: `pms.search_issues`, `pms.get_issue`, `pms.list_spaces`, `pms.list_task_lists`
   - Meeting: `meeting.list_meetings`, `meeting.get_meeting`, `meeting.list_recordings`, **`meeting.find_availability`** (planner 아님)
   - Planner: `planner.list_events`
   - Docs: **`docs.list_hub`**, **`docs.get_item`**, **`docs.list_pages`**, **`docs.read_page`** (list_docs/read_page 네이밍 폐기)
5. **Agent 루프** (최대 8턴, 루프 안전장치).
6. **프론트 ToolCallCard** (Phase 2 Envelope의 `tool_call_started` / `tool_result` 이벤트 렌더).

**완료 조건**: "내 오늘 할일", "어제 회의 요약", "다음 주 화요일 비어있는 시간" 등 read 기능이 채팅으로 동작. 워크스페이스 격리 검증 (다른 워크스페이스 리소스 접근 시 403). 서비스 계층 재사용으로 router-only 로직 중복 없음.

**결정 의존**: PoC 결과에 따라 tool 프로토콜 확정.

**상세 플랜 파일**: `03-phase3-services-tools-read.md`

---

### Phase 3.5 — MCP-First Capability Bridge
**목표**: AI capability 정본을 legacy OpenAI spec registry가 아니라 **MCP-shaped descriptor + InProc bridge** 로 고정한다. 이후 Phase 4의 write/approval/meeting 기능은 이 bridge 위 consumer slice로 쌓는다.

**핵심 산출물**:
- `AiCapabilityDescriptor` / MCP manifest compiler / `AiMcpClient`
- derived OpenAI function schema / derived OpenAPI export
- discoverability filtering + execute 시점 재검증
- legacy `openai_tool_specs()` 호환 유지
- inspection/debug manifest/openapi endpoint

**완료 조건**: read capability discovery 정본이 MCP bridge로 전환되고, 기존 read tool 이름/args shape 및 stream/agent loop 회귀가 유지된다.

**상세 플랜 파일**: 완료 — MCP bridge/canonical refactor 머지됨

---

### Phase 4 — Tool Calling (Write) + Meeting Intelligence
**목표**: 상태 변경 툴 + 승인 게이트 + 회의 지능화.

**핵심 산출물**:
- Write 툴: `pms.create_issue/update_issue/add_comment`, `meeting.create_meeting`, `planner.create_event`, `docs.create_page`
- ApprovalModal 플로우 (LLM proposal → 사용자 승인 → 실행)
- 회의 지능화:
  - `meeting.extract_actions` (전사 → 액션 아이템)
  - `meeting.extract_decisions`
  - `meeting.draft_followup_schedule`
  - `MeetingInsight` 저장 (별도 테이블 + `payload_json`)
- 회의 컨텍스트로 chat 진입 (scope_ref)

**전제**: tool discovery 정본은 MCP bridge다. write capability는 `AiCapabilityDescriptor` 로 등록하고, OpenAI function spec은 bridge 산출물로만 사용한다.

**완료 조건**: "어제 회의 액션 아이템 이슈로" 플로우 완성. ACL 통과 검증. 다건 작업을 순차 승인으로 완료 가능.

**전제**: 전사는 기존 `core/asr.py` 그대로. 로컬 whisper 전환은 별도 track.

**상세 플랜 파일**: `04-phase4-write-meeting.md`

---

### Phase 5 — RAG Integration (Resource-level ACL Projection)
**목표**: 내부 RAG 서비스 연동. 단, **팀 ID 전파로는 부족**하다. Docs의 실제 ACL = `owner` + `direct_share(user_id, access_level)` + `link_share(token, access_level)` + `meeting_grant(user_id, expires_at)` 복합이므로, 팀 소속만 넘기면 과차단 또는 과개방이 발생.

**핵심 산출물**:
1. **Resource-level ACL Projection 설계**:
   - **Ingest 시** (문서 단위): doowon이 `_resolve_native_doc_access` 계열 로직으로 해당 문서의 "열람 가능 principal 집합"을 미리 계산 → RAG 서비스에 함께 전송.
     - 예: `{document_id, chunks, visibility: {owners: [uid], direct_shares: [{uid, level}], link_share_refs: [{ref, level}], meeting_grants: [{uid, expires_at}], workspace_id}}`
   - **Query 시** (사용자 단위): doowon이 현재 요청자의 `principal_set` 구성 → RAG 서비스에 함께 전송.
     - 예: `{user_id, workspace_id, held_link_share_refs: [...], held_meeting_grants: [...], team_memberships: [...]}`
   - **raw token은 RAG로 보내지 않는다.** 사용자가 제시한 `share_token`은 doowon 내부에서만 검증하고, query 직전에 파생 `link_share_ref`로 치환한다.
   - RAG 서비스는 visibility와 principal_set의 **교집합 판정 로직**만 보유. 팀 기반 단일 필드 필터로 단순화 금지.
2. **OpenAPI 계약 문서** (`docs/rag-service-openapi.yaml`) — 위 ACL 스키마 포함.
3. **`core/rag_client.py`** httpx 비동기 클라이언트 + principal_set 빌더 (`domains/docs/access_grants.py` 로직 재사용).
4. **도구**: `rag.query`, `rag.list_sources`.
5. **Docs 훅**: 문서/페이지 생성·수정·삭제·공유 변경 이벤트 → Celery 태스크로 RAG 재인제스트. ACL 변경도 마찬가지 (visibility만 업데이트).
6. **서비스 장애 graceful degradation**: RAG 다운 시 "지식베이스 조회 불가" 메시지 + audit 기록. LLM이 툴 없이 답변 시도.

**완료 조건**: 사용자가 접근 권한 없는 문서의 chunk가 RAG 결과에 **한 건도** 섞이지 않음 (자동 테스트). meeting_grant 만료 후 접근 차단. 링크 공유 토큰으로 조회 시 해당 문서만 반환.

**전제**: RAG 서비스 자체 구현은 별도 프로젝트. 본 프로젝트는 client + 계약 + ingest 훅만.

**결정 의존**: ACL 체크를 RAG가 맡을지, client에서 필터링할지도 이 단계에 결정 (성능 vs 단순성).

**상세 플랜 파일**: `05-phase5-rag-acl-projection.md`

---

### Phase 6 — Batch LlmJob + Admin UI
**목표**: 장시간 배치 작업 + 관리자 정책 편집.

**핵심 산출물**:
- `LlmJob` 테이블 (pending/running/done/failed/cancelled, progress_pct, result_text/reasoning, usage)
- Worker task `llm_batch.py` (heartbeat 패턴, `task_time_limit=1800`)
- API: `POST/GET /ai/jobs`, `POST /ai/jobs/{id}/cancel`
- Admin UI 탭:
  - LLM Policy 관리 (task_kind × policy 편집)
  - Pool 상태 대시보드 (성공률, latency, 최근 에러)
  - Audit Log 필터 프리셋 (LLM 전용)

**완료 조건**: 30K 보고서 비동기 생성. 관리자가 DB 통해 정책 변경. 변경 즉시 라우팅 반영.

**상세 플랜 파일**: `06-phase6-batch-admin.md`

---

### Phase 7 — External Integration
**목표**: Doowon 백엔드를 first-party 프론트 전용이 아니라 **workspace-scoped AI hub**로 공개 가능한 상태까지 확장한다.

**핵심 산출물**:
- workspace 단위 `ServiceAccount` + external caller auth 설계/구현
- 1차 호환 경로는 API key, 장기 기본 경로는 OAuth 2.1 / external hub 호환 principal 매핑
- 외부 auth resolver → `CallerPrincipal(kind="service_account"|...)`
- route-family 기준 scope (`ai.invoke`부터 시작, 이후 domain read/write로 확장)
- 외부 소비자용 rate limit / quota
- webhook / async completion callback
- 외부 공개용 OpenAPI 보강 문서와 integration guide

**완료 조건**: first-party web 클라이언트와 동일 서비스 계층을 사용하면서도, 외부 시스템이 workspace-bound principal과 scope만으로 안전하게 AI/API를 호출할 수 있다.

**상세 플랜 파일**: `07-phase7-external-integration.md`

---

## 교차 관심사 (Cross-cutting)

### 워크스페이스 격리 + ACL
모든 Phase에서 지킬 불변.

| 레이어 | 적용 |
|---|---|
| `ChatThread` | `workspace_id` FK, `require_current_workspace` |
| LLM 요청 | AuthContext 주입, 시스템 프롬프트에 workspace_name |
| Tool 호출 | 기존 `access.py` 함수 호출로 ACL 검사 |
| RAG 쿼리 | workspace_id + user_id + principal_set (held_link_share_refs, held_meeting_grants, team_memberships) |
| Batch Job | `LlmJob.workspace_id`, 조회 시 필터 |
| Audit | workspace_id를 payload에 포함 |

### 감사 로그 구조
기존 `AuditLog` 테이블 재사용. 신규 action:
- `llm_call` — LLM 요청 단위. payload: {pool, model, policy, task_kind, status, pii_hits, tokens, latency_ms, workspace_id}
- `llm_tool_call` — 도구 호출 단위. payload: {tool_name, args_summary, status, resource_ids, error}

### 챗 히스토리 보존
**영구 보존** (TTL 없음). 사용자 명시 삭제 시 soft delete (`deleted_at`).

---

## 주요 디렉터리 맵

재사용(수정 없음):
- `domains/auth/models.py::AuditLog`
- `domains/auth/access.py::record_audit_log`
- `domains/auth/dependencies.py::require_permission, require_current_workspace`
- `domains/pms/access.py::_ensure_*`
- `domains/meeting/permissions.py`
- `domains/docs/access_grants.py`
- `worker/tasks/meeting.py::_heartbeat` 패턴
- `core/asr.py::ASRBackend` Protocol

Phase별 신규 영역:
- `apps/api/src/aidoo_api/core/pii.py`, `llm_adapters.py`, `rag_client.py`
- `apps/api/src/aidoo_api/domains/ai/` — models, tools, agent, policy_service, audit
- `apps/worker/src/aidoo_worker/tasks/llm_batch.py`
- `apps/web/src/domains/ai/` — 대거 개편
- `apps/web/src/domains/admin/` — LLM 탭 추가

---

## 의사결정 로그

### 결정 완료
| 항목 | 결정 |
|---|---|
| Pool 분리 방식 | LOCAL/EXTERNAL 완전 독립, 크로스 폴백 금지 |
| 정책 세분도 | Task-level only (Phase 1에선 workspace/role override 미지원) |
| 배치 스토리지 | 단일 `LlmJob` 테이블 (범용) |
| PII 탐지 | 기본 정규식 탐지 포함 (라우팅 결정 용도) |
| Phasing | P1→P6 점진, 일부 병렬 제한 (Phase 로드맵 주석 참조) |
| **P1 범위 확장** | 단순 라우팅이 아니라 **LlmTaskContext + 인증·워크스페이스 주입 + 감사 + 라우팅** 묶음 |
| **Phase 1 머지 완료 (2026-04-18, fe23cff)** | 세부 플랜 제거, 후속 요약은 [`docs/planning-log.md`](../docs/planning-log.md) 참조 |
| **P2 선행 작업** | 구현 전에 AgentEventEnvelope 계약 확정 (P3~P4 이벤트도 포함) |
| **P3 선행 작업** | PoC 전에 **도메인별 tool-facing service layer 추출** |
| **P5 ACL 모델** | 팀 기반 전파 ❌ → **Resource-level ACL projection** (ingest 시 visibility set + query 시 principal_set, raw link token 외부 전파 금지) |
| **Source→actor 매핑** | 원칙 4 표 참조. `/api.*` = user, `worker.meeting.*` = system(None), `worker.llm_batch` = job 제출자 |
| **AI route 보호 회귀** | legacy + slug 이중 mount 모두 커버. `/readyz`는 공개 유지. |
| 챗 UI 디자인 | Phase 2 킥오프 전 전용 디자인 세션 (P3/P4 컴포넌트까지 커버) |
| Tool calling 프로토콜 | Phase 3 두 번째 작업으로 mlx-lm function-calling PoC |
| **Phase 3.5 완료 (2026-04-20)** | MCP-shaped descriptor + InProc bridge를 capability 정본으로 채택. OpenAI function spec / OpenAPI는 파생 산출물로 유지. |
| **Phase 4 계획 결정** | `MeetingInsight` 는 별도 테이블 + `payload_json`, approval flow는 halt당 1건 순차 승인, scope conversation은 `scope_ref` + `scope_resource_id` 두 컬럼으로 간다. |
| 전사 프로바이더 | 기존 `core/asr.py` 설정 유지 |
| 챗 히스토리 | 영구 보존, soft delete |

### 차후 결정 (Phase 킥오프 시)
| 항목 | 결정 시점 |
|---|---|
| PII 값 자체 마스킹 | 법무 검토 후 (외부 풀 사용 업무 한정) |
| 장애 알람 채널 (Slack/이메일/Jira) | 인프라 구축 단계 |
| 비용/성능 모니터링 UI | Phase 6 확장 후보 |
| 외부 풀 프로바이더 확장 순서 (Anthropic/OpenAI) | 도입 필요 시점 |
| 로컬 whisper 전환 시점 | ASR 품질 측정 후 |
| Artifact Canvas 고도화 범위/우선순위 | Phase 4 이후 제품 하드닝 시 |

---

## Deferred Product Backlog — Artifact Canvas 고도화

현재 artifact 구현은 **type-aware renderer + live preview** 중심의 viewer 단계다. 향후 Claude Artifacts/Canvas 급의 작업 표면으로 고도화하려면 아래 태스크를 별도 트랙으로 잡는다.

### 킥오프 조건
- Phase 3의 read tool/service layer가 안정화되어 대화-도구-산출물의 책임 경계가 고정될 것.
- 가능하면 Phase 4의 write/approval 플로우 이후에 착수할 것. artifact 수정 제안과 승인 경계를 같은 UX 축에서 다뤄야 하기 때문.
- Docs 저장/공유와의 연결을 고려하므로 workspace-level 저장 전략이 먼저 정리되어야 함.

### P0 — 캔버스 최소 요건
1. **Artifact identity + version chain**
   - assistant turn 부속 payload가 아니라 “같은 artifact의 여러 revision”을 추적하는 모델로 승격.
   - version selector와 revision metadata(생성 시각, source turn, title 변경 이력) 제공.
   - follow-up prompt가 “새 artifact 추가”가 아니라 “선택 artifact의 새 버전 생성”으로 연결되게 조정.
2. **Active artifact targeting**
   - 다중 artifact가 있는 대화에서 “지금 어떤 artifact를 수정하는지” 명시적으로 선택.
   - 모델 전송 payload에도 selected artifact id / target revision 정보를 포함.
   - 여러 artifact가 공존할 때 후속 요청이 엉뚱한 artifact를 수정하지 않도록 방지.
3. **Canvas action bar**
   - 공통 액션: source 보기, 복사, 다운로드, 새 대화로 fork, Docs로 저장/승격.
   - 타입별 액션: HTML export, SVG download, Markdown/Code raw export.
   - 현재 단순 side panel을 “작업 표면”으로 바꾸는 최소 UI.
4. **Runtime error surface + fix loop**
   - HTML/interactive artifact의 iframe runtime error/console capture.
   - 캔버스 내부 오류 배너 + “이 오류로 다시 고쳐줘” 액션 제공.
   - 대화창에 오류 컨텍스트를 자동 주입하는 repair prompt 경로 마련.

### P1 — 재사용성과 워크스페이스 통합
1. **Artifact inventory**
   - conversation 종속 리스트가 아니라 workspace 차원의 “내 artifact / 최근 artifact” 진입점 제공.
   - 검색, 정렬, reopen, origin conversation 역추적 지원.
2. **Artifact → Docs 승격**
   - document/html/code artifact를 Docs 아이템 또는 페이지로 저장.
   - 저장 후 artifact와 docs 리소스 간 backlink 유지 여부 결정.
3. **Multi-artifact control surface**
   - 현재 URL query param 기반 단일 open 상태를 넘어, artifact switcher / overview 제공.
   - 선택된 artifact만 다음 수정 대상으로 쓰인다는 UI affordance 강화.

### P2 — 플랫폼화 후보
1. **Share / Customize**
   - 내부 공유 링크, 읽기 전용 보기, fork/customize 흐름.
   - 원본 artifact와 fork artifact의 lineage 추적.
2. **Publish / Embed**
   - 외부 공개가 필요할 때만 착수.
   - 허용 도메인, revoke/unpublish, 임베드 코드 정책 포함.
3. **AI-powered artifacts / MCP / persistent storage**
   - artifact 내부 AI 호출, 외부 툴 연동, 상태 저장은 별도 제품 결정 후 도입.
   - 보안/비용/감사 모델을 먼저 확정하지 않으면 금지.

### 검증 기준
- 다중 artifact 대화에서 사용자가 선택한 artifact만 후속 수정 대상으로 반영된다.
- 같은 artifact의 과거 버전과 최신 버전을 전환해도 내용과 메타데이터가 일관된다.
- HTML artifact 오류를 사용자가 캔버스 안에서 확인하고, repair prompt를 한 번에 재실행할 수 있다.
- 문서형 artifact를 Docs로 저장한 뒤 workspace 권한 체계 안에서 재사용할 수 있다.

---

## Phase 킥오프 프로토콜

각 Phase 시작 시 다음 단계를 따른다.

1. **세부 플랜 파일 생성**: 본 문서의 해당 Phase 섹션을 출발점으로 [`plans/`](./) 디렉터리에 `NN-phaseX-<slug>.md` 파일을 plan mode에서 새로 작성.
2. **현황 재탐색**: Phase가 의존하는 코드 영역 재스캔. 선행 Phase 이후 변경점 반영.
3. **열린 결정 해소**: 상단 "차후 결정" 표에서 해당 Phase에 해당하는 항목 먼저 확정.
4. **사전 작업 확인**: Phase 2의 디자인 세션처럼 사전 요구사항이 있으면 먼저 완료.
5. **테스트 계획 포함**: 세부 플랜에 검증 시나리오(단위 + 수동) 명시.
6. **실행 후 정리**:
   - 본 문서의 "결정 완료" / "결정 의존" 표 갱신.
   - Phase 세부 플랜 파일을 [`plans/`](./) 에서 제거.
   - [`docs/planning-log.md`](../docs/planning-log.md)에 요약 엔트리 추가 (PR/커밋 링크 포함).
   - 모든 Phase 완료 시 본 로드맵도 동일 절차로 로그 이관.

---

## 다음 단계

현재 다음 작업은 **Phase 3 (Tool Service Layer + Tool Calling Read) 세부 플랜**을 별도 파일(`plans/03-phase3-services-tools-read.md`)로 작성하는 것이다.

Phase 3 세부 플랜은 본 문서의 Phase 3 섹션을 확장해서:
- `domains/pms|meeting|planner|docs/services/` 추출 범위와 router slimming diff 확정
- mlx-lm `tools` 파라미터 수용 여부를 검증하는 function-calling PoC 절차와 성공/실패 분기 정의
- `TOOL_REGISTRY`/permission precheck/audit 파이프라인의 책임 경계 고정
- read-only 툴 스키마(`pms.search_issues`, `meeting.find_availability`, `docs.list_hub` 등)와 ACL 검증 포인트 명시
- Phase 2에서 고정한 `tool_call_*` envelope를 실제 발행으로 연결하는 서버/프론트 작업 순서 정리
- tool 실행 audit payload와 실패 코드 표준화
- 테스트 케이스 — 특히 read-only ACL 403, unknown tool/invalid args 방어, tool call envelope 순서 보존, function-calling PoC fallback 분기 검증
- 롤백 계획
- 예상 작업 기간

등을 포함한다.
