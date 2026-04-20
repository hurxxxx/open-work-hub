# Phase 4 — Tool Calling (Write) + Meeting Intelligence

> **상위 문서**: [`00-ai-platform-roadmap.md` Phase 4 섹션](./00-ai-platform-roadmap.md#phase-4--tool-calling-write--meeting-intelligence)
> **선행 Phase**: 1 (foundation), 2 (envelope/streaming), 3 (read tools + service layer + agent loop) — 모두 머지 완료.
> **상태**: 작성 중. 리뷰/승인 후 실행.

---

## 1. Context

Phase 3에서 read-only 툴과 agent 루프가 붙었다. 현재 registry에 등록된 write 툴은 **0개**다. `tool_service.execute_tool`은 `approval_required=True`인 정의를 만나면 **409를 던지고 끝**이고 ([`tool_service.py:72`](../apps/api/src/aidoo_api/domains/ai/tool_service.py#L72)), agent 루프는 그 409를 받아 `agent_loop_blocked_tool_call` 에러로 턴을 종료한다 ([`agent.py:295-314`](../apps/api/src/aidoo_api/domains/ai/agent.py#L295-L314)). 프론트 `ApprovalModal.tsx`는 **null 반환 스텁**이고 `approval_resolved` 이벤트는 누구도 발행/소비하지 않는다.

Phase 4의 목표는 이 3축을 동시에 완성하는 것이다:

1. **Write 툴 6종 + 승인 게이트**: `pms.create_issue / update_issue / add_comment`, `meeting.create_meeting`, `planner.create_event`, `docs.create_page`. LLM이 바로 실행하지 못하고 반드시 사용자 승인 후에만 진행.
2. **회의 지능화**: 기존 `MeetingRecording.summary_text` 1개 필드를 넘어 **`MeetingInsight`** 테이블로 action / decision / followup_schedule 제안을 저장. 이 제안이 write 툴의 입력원이 된다.
3. **회의→챗 진입**: `Conversation.scope_ref`로 회의(또는 임의 리소스) 컨텍스트를 chat에 바인딩. "이 회의 액션 아이템을 이슈로 만들어줘" 류 플로우 완성.

### 현재 상태 스냅샷 (Phase 4 진입 시점)

- **Registry**: `pms`, `meeting`, `planner`, `docs`, `ai` 5개 도메인에서 `register_ai_capabilities` 로드. 모두 read 툴만 ([`registry.py:129-140`](../apps/api/src/aidoo_api/domains/ai/registry.py#L129-L140)).
- **Tool runtime**: 409 → `status="blocked"` → `approval_required` envelope 한 번만 emit하고 return ([`tool_runtime.py:127-137`](../apps/api/src/aidoo_api/domains/ai/tool_runtime.py#L127-L137)). 승인 상태 **영속화 없음**.
- **Agent loop**: pending tool call을 순회하다가([`agent.py:211`](../apps/api/src/aidoo_api/domains/ai/agent.py#L211)) blocked를 만나면 error + done(finish_reason=error)으로 **즉시 종료**하고 뒤에 남은 pending call은 버린다 ([`agent.py:295-314`](../apps/api/src/aidoo_api/domains/ai/agent.py#L295-L314)). **pause/resume 없음**.
- **Envelope**: `ApprovalRequiredData` / `ApprovalResolvedData` 스키마는 확정되어 있지만 ([`events.py:146-157`](../apps/api/src/aidoo_api/domains/ai/events.py#L146-L157)) **`call_id` 필드 없음** — approval과 특정 tool call을 연결할 키 부재. reject reason 필드도 없음. TS 타입도 마찬가지 ([`agent-events.ts:150-162`](../apps/web/src/domains/ai/agent-events.ts#L150-L162)).
- **PMS write 경로**: router에 ORM 직결, service 계층 write 메서드 **없음** ([`pms/service.py` grep 결과 — read 전용](../apps/api/src/aidoo_api/domains/pms/service.py)). Phase 3는 read만 추출했다.
- **Meeting / Planner / Docs write**: service 계층에 이미 존재 — `meeting_service.create_meeting` ([`meeting/service.py:762`](../apps/api/src/aidoo_api/domains/meeting/service.py#L762)), `planner_service.create_event` ([`planner/service.py:163`](../apps/api/src/aidoo_api/domains/planner/service.py#L163)), `docs_service.create_native_doc_for_user`.
- **ConversationTurn 저장 모델**: `role: user|assistant`만 허용 ([`conversations/models.py:88`](../apps/api/src/aidoo_api/domains/conversations/models.py#L88)). assistant turn의 `meta`에 `tool_calls` / `pending_approvals` / `artifacts`가 UI 렌더 용도로 들어가지만 ([`ai/router.py:1660-1674`](../apps/api/src/aidoo_api/domains/ai/router.py#L1660-L1674)) **OpenAI canonical transcript(assistant with `tool_calls[]` + 별도 `role:"tool"` message)는 아니다**. LLM 재실행에 필요한 정본 messages는 현재 DB에서 복원 불가.
- **Conversation**: `workspace_id`, `user_id`, `title` 만. **`scope_ref` 컬럼 없음**. 프론트는 `conversation_attached` envelope로 bind.
- **Worker meeting pipeline**: [`apps/worker/src/aidoo_worker/tasks/meeting.py`](../apps/worker/src/aidoo_worker/tasks/meeting.py)가 ASR → summary_text까지만 수행.
- **Audit**: `log_llm_tool_call` payload는 `status/resource_ids/args_summary` 포함, **approval_id 미포함**. Read vs write 구분 플래그도 없음.

### 목표

- write 툴은 "LLM이 제안 → 사용자가 승인 → 실행 → audit"의 단일 경로로만 성공한다. 우회 불가.
- 회의 녹취가 끝나면 summary + actions + decisions + followup 제안이 함께 저장되어, UI에서 한 번의 승인으로 실제 이슈·이벤트가 생성된다.
- "회의 컨텍스트 챗"에서 모델은 transcript 발췌를 system prompt로 받고, 위 write 툴들로 작업을 완결한다.

### 비목표 (Phase 4 범위 밖)

- ACL 우회 승인 (사용자가 승인해도 기존 ACL은 반드시 통과).
- 승인 위임 / 자동 승인 규칙 (Phase 6 정책 UI에서 재검토).
- MeetingInsight 수동 편집 UI (초기엔 accept/reject만).
- **한 halt에 여러 approval을 병렬 노출하는 UX** — Phase 4는 **halt당 approval 1건**이다. agent는 첫 blocked call에서 halt하고 뒤에 남은 pending call은 버린 뒤 모델이 다음 재개 턴에서 다시 계획하도록 한다 (상세 §2.2). "3 actions → 3 issues" 시나리오는 **client-orchestrated 순차 round-trip**으로 처리. 한 화면에서 N개를 동시에 승인 받는 UX는 Phase 4 polish 항목 또는 Phase 6 후보.
- Bulk multi-tool 트랜잭션 (여러 write를 한 atomic 블록으로). Phase 4는 **건별 승인**.
- 외부 푸시 알림 (Slack/이메일). Phase 6 운영 UI 후 검토.
- Artifact Canvas 연동 (Deferred Backlog).

---

## 2. Architecture / Principles

### 2.1 승인 게이트 원칙

1. **정의 시점 선언**: write 툴은 `registry.register_tool(..., approval_required=True)`로 등록. 이 플래그가 없으면 승인 없이 실행된다 — Phase 4에서 모든 신규 write 툴에 반드시 세팅.
2. **실행 시점 이중 차단**:
   - `tool_service.execute_tool`은 `approval_required=True` 툴을 **승인 토큰 없이 호출하면 차단**한다. 차단 시 tool call은 실행 흐름 대신 `AiToolApproval` 레코드로 persist된다.
   - 승인 토큰(= `approval_id` + decision)이 있을 때만 실제 handler까지 내려간다.
3. **ACL 독립**: 승인 여부는 "이 사용자가 이 행위를 원한다"의 확인일 뿐이다. 실제 리소스 변경 시점에는 도메인 ACL helper가 다시 돈다. 승인됐다고 write 권한이 생기진 않는다.
4. **Workspace 경계**: 승인 레코드는 `workspace_id` 필수. 다른 워크스페이스의 승인 ID로 resolve 시도 → 404.
5. **Principal 일치**: `AiToolApproval.requested_by_user_id`와 `resolved_by_user_id`가 원칙적으로 같아야 한다 (위임 정책은 Phase 6). 다르면 403.
6. **회계 감사**: 승인/거절/만료 모두 `AuditLog`에 남는다. 신규 action = `llm_tool_approval_resolved`.

### 2.2 Agent pause/resume 모델

현재 agent는 한 SSE 요청 = 한 턴이고 blocked를 만나면 즉시 종료한다. Phase 4는 "턴 안에서 blocked → 다음 SSE 요청에서 resume" 모델을 택하되, **halt는 첫 blocked call 한 건에서 발생**한다. 이유:

- 한 SSE 커넥션을 수 분간 hold하면 프록시 타임아웃 / 모바일 네트워크 이슈 / 승인 지연 시 비용 누수.
- client-driven resume이 frontend 상태 관리와 잘 맞음 (approve 버튼 → REST → 새 SSE).
- 승인이 하루 뒤에 나도 대화 맥락이 DB에 있으면 재개 가능.
- Phase 4 범위를 한 halt = 한 approval로 고정하면 replay 상태가 `{messages, blocked_call_id}` 둘로 단순해진다. 한 halt에 여러 approval을 모으는 설계는 별도 trade-off(envelope 버퍼링, 동시 resolve 타이밍, 부분 승인)를 몰고 오므로 Phase 4 이후로 미룬다.

#### 턴 경계 정의

| 턴 | 트리거 | 종료 조건 |
|---|---|---|
| **제안 턴** | `POST /ai/chat/stream` 일반 | 모델이 tool_calls를 보낸 경우 pending queue의 **첫 blocked call에서 halt** → `approval_required` envelope + `done{finish_reason:"awaiting_approval"}`. queue에 남은 다른 pending call은 **실행하지 않는다** (대응하는 assistant/tool canonical messages도 snapshot에 기록하지 않음). 모델이 다음 재개 턴에서 다시 계획한다. |
| **재개 턴** | `POST /ai/chat/resume` body `{conversation_id, approval_id, decision, reason?}` | snapshot을 불러와 canonical messages를 복원 → blocked_call_id 한 건 처리(승인이면 실제 handler 호출 + `tool_result`, 거절이면 툴 결과 자리에 거절 사유/decision 기록) → agent 루프 계속 → 모델이 또 blocked를 내면 동일 halt 사이클 반복. |

#### 2.2.1 Replay state — `AgentRunSnapshot`

**현재 저장의 한계**: `ConversationTurn`은 UI 렌더 전용이고 role이 user|assistant만이다 ([`conversations/models.py:88`](../apps/api/src/aidoo_api/domains/conversations/models.py#L88)). assistant turn의 `meta.tool_calls` / `meta.pending_approvals`는 ChatTurn UI 셰이프로, OpenAI canonical replay에 필요한 구조(`{role:"assistant", tool_calls:[{id,type,function}]}` + 짝이 되는 `{role:"tool", tool_call_id, content}` messages)를 재구성하지 못한다. 재구성 로직을 router에 끼워넣는 것도 가능하지만 assistant content가 UI용으로 가공(마크다운, PII 마스킹 등)되어 있어 LLM 입력으로 되돌리기 취약하다.

**결정**: 재실행에 필요한 canonical messages를 **별도 테이블에 raw 그대로** 남긴다. `ConversationTurn`은 UI persistence 그대로 둔다. 두 레이어의 책임이 다르므로 분리한다.

```
ai_agent_run_snapshots
  id                STRING(36) PK              -- = agent_run_id (per halt)
  conversation_id   FK conversations NOT NULL INDEX
  workspace_id      FK workspaces NOT NULL INDEX
  requested_by_user_id FK users NOT NULL
  parent_run_id     FK ai_agent_run_snapshots NULL INDEX
                                               -- 직전 halt 체인. 첫 halt는 NULL.
                                               -- 재halt 시 부모 = 방금 completed된 snapshot.
  status            STRING(16) NOT NULL DEFAULT 'awaiting_approval'
                    -- awaiting_approval | resumed | completed | abandoned
  messages_json     JSONB NOT NULL             -- OpenAI canonical message list
                                               -- (system / user / assistant(+tool_calls) / tool)
  blocked_call_id   STRING(80) NOT NULL        -- halt 원인 tool_call id
  model_meta        JSONB NULL                 -- {model, policy, chosen_pool, tool_choice_state, …}
  created_at        TIMESTAMP NOT NULL
  updated_at        TIMESTAMP NOT NULL
  INDEX (conversation_id, status, created_at)
  INDEX (workspace_id, status, created_at)
```

`parent_run_id`는 audit lineage 용도다. "이 최종 이슈가 어떤 halt 체인을 거쳤는지"를 한 쿼리로 복원할 수 있다. 첫 halt는 NULL이고 재halt는 직전 completed snapshot을 가리킨다.

`messages_json`은 agent가 그 halt까지 실제로 LLM에 전송한 (또는 전송할 예정이었던) 메시지 목록이다. halt 이전의 블록된 call 자체는 아직 `tool_call` assistant 메시지로는 기록되지 않는다 — 재개 턴에서 실행 결과와 짝지어 한 번에 append한다. 즉 snapshot은 **"재개 시 LLM에 먹일 canonical prefix"**를 정본으로 관리한다.

**AgentRunSnapshot vs AiToolApproval 관계**:
- **1 snapshot : 1 approval** (per-halt ledger). `agent_run_id == snapshot.id`. `AiToolApproval.agent_run_id` FK + `tool_call_id`는 해당 snapshot의 `blocked_call_id`와 같다.
- 한 halt에 approval 여러 건을 지원할 경우(future) `blocked_call_id` → `blocked_call_ids[]` + approval N:1로 전환. 지금 스키마는 칼럼 추가 + 이름 바꾸기만 하면 되게 둔다.

**Halt 체인 / Conversation 내 여러 snapshot**:
- 한 conversation은 재halt마다 **서로 다른 `agent_run_id`를 가진 snapshot row들의 chain**을 생성한다. lineage는 `parent_run_id` 컬럼(§B.2)으로 연결.
- "이 대화의 모든 halt 이력"은 `WHERE conversation_id=? ORDER BY created_at`으로 조회. 첫 halt의 snapshot만 `parent_run_id IS NULL`.

**`ConversationTurn`과의 관계**:
- **매 halt마다 `ConversationTurn.assistant` 1 row append**. meta에 그 halt의 `agent_run_id`, `pending_approvals=[{approval_id, call_id, tool, ...}]` 포함. 재halt면 그 halt의 approval 정보만 기록 (이전 halt 정보는 이전 ConversationTurn row에 이미 있음).
- **정상 stop 도달 시 `ConversationTurn.assistant` 최종 row append**. meta에 이 resume 단계에서 executed/rejected된 tool_calls 합본. pending_approvals는 비움.
- canonical replay는 snapshot 체인이 담당. UI reload는 ConversationTurn 시퀀스로 이전 halt 버블들까지 재구성 가능.

**`ConversationTurn.role` 확장 여부**: 확장하지 않는다. tool message를 별도 role로 노출하면 기존 UI 렌더 분기가 늘고, UI는 이미 assistant row의 `meta.tool_calls`로 표시한다. canonical replay는 snapshot이 담당.

#### 2.2.2 상태 전이 요약

```
제안 턴
  └ 정상 모델 응답(stop)          → ConversationTurn.assistant 1건 + snapshot 없음
  └ 첫 blocked tool call 감지      → AiToolApproval(pending) + AgentRunSnapshot(awaiting_approval)
                                     + ConversationTurn.assistant(meta.pending_approvals=[...])
                                     + done{finish_reason:"awaiting_approval"}

resolve API(REST)
  AiToolApproval.status = approved | rejected  (reason 선택)
  snapshot.status 변화 없음 (awaiting_approval)

재개 턴 진입
  snapshot FOR UPDATE lock
  snapshot.status awaiting_approval → resumed 로 전이 (중복 resume 차단 용도)

재개 턴 본문
  canonical messages 복원 후:
    approved: execute_tool(..., approved_call_id=approval_id) → tool_result envelope
              + assistant_tool_calls[blocked] + tool_message append
    rejected: 실행 skip, tool_message content에 거절 사유/decision 삽입
  (두 경우 모두 approval_resolved envelope emit)

재개 턴 종료
  agent loop 계속 진행:
    또 blocked 발생 → 현재 snapshot.status = completed 로 마감
                      + 새 AgentRunSnapshot(awaiting_approval) 생성
                      + 새 agent_run_id + 새 approval row 생성
                      + 새 approval_required envelope + done{awaiting_approval}
    정상 stop 도달 → snapshot.status = completed
                      + ConversationTurn.assistant 최종 row append
```

#### 2.2.3 동시성

- 한 `agent_run_id` (= 한 snapshot)는 동시에 resume 1회만 허용. `SELECT ... FOR UPDATE` on `ai_agent_run_snapshots`로 serialize. 두 번째 시도는 409 (진행 중) 또는 410 (이미 completed).
- snapshot.status=`completed|abandoned|resumed`로 resume 요청 → 410 gone. `resumed`는 "다른 프로세스가 현재 resume 중"이라 하여 409를 반환하고 끝나면 410으로 바뀌도록 FOR UPDATE로 연쇄 대기시킨다.
- **conversation 단위 mutual-exclusion**: 같은 `conversation_id`에 `awaiting_approval` 상태 snapshot이 존재하는 동안 `POST /ai/chat/stream`(새 사용자 turn)은 409로 차단한다. 프론트는 §G.3에서 이미 입력을 disable하므로 normal case에는 걸리지 않고, 레이스/악성 클라이언트 방어용.
- 반대로 stream이 먼저 새 turn을 시작해 halt 없이 끝나면 직전에 남은 `awaiting_approval` snapshot은 없어야 한다 — 만약 남아 있었다면 그 snapshot을 `abandoned`로 전이시키고 (관련 approval도 `expired`) 새 stream을 진행할지, 아니면 400으로 거절할지 결정이 필요 (§5.2 open).
- resume 중에 SSE 클라이언트가 끊어져도 서버는 루프를 계속 돈다 — 다음 halt 도달 시 직전 snapshot을 `completed`로 마감하고 새 `awaiting_approval` snapshot + approval을 생성하며 `ConversationTurn.assistant` row도 append한다. 클라이언트가 재접속하면 conversation reload에서 최신 pending approval 상태를 복원한다.

### 2.3 회의 지능화 데이터 모델

**결정**: `MeetingInsight`를 **별도 테이블**로 추가 (로드맵 open 결정 해소).

이유:
- insight 종류별 구조가 다르다 (action은 assignee/due_date, decision은 rationale, followup은 proposed_slot 배열).
- 여러 insight가 하나의 recording에서 배치 생성된다. JSON 배열을 컬럼에 박으면 승인 상태/FK 추적이 어려워진다.
- 승인 결과로 생성된 실제 리소스 ID (`accepted_as_kind`, `accepted_as_id`)를 추적해야 한다.
- 쿼리: "이 회의에서 나온 pending action 몇 개?" 가 O(1) 인덱스로 가능해야 한다.

JSON 컬럼은 insight별 `payload_json` 1개에만 사용한다 (구조적 diff 불필요 + provider별 다른 포맷 흡수).

### 2.4 `scope_ref` 설계

`Conversation.scope_ref TEXT NULL, scope_resource_id STRING NULL` 두 컬럼. 관례:

- `scope_ref` = `"meeting"` | `"pms_issue"` | `"docs_page"` | `null` (free chat)
- `scope_resource_id` = 위에 해당하는 resource PK

두 컬럼 분리 이유: 나중에 "이 회의 관련 모든 대화" 쿼리를 `WHERE scope_ref='meeting' AND scope_resource_id=?`로 바로 날릴 수 있다. 단일 문자열 `"meeting:<id>"` 방식은 파싱이 귀찮고 인덱스 타기 어렵다.

**ACL**: scope 리소스 접근 권한이 없으면 conversation 생성 거부. 권한이 나중에 빠지면 기존 conversation은 read-only 상태로 표시 (Phase 4에서는 정지만, UI는 diff 표시까지).

### 2.5 불변 (모든 write 툴 공통)

- 모든 write는 승인 게이트를 통과한다.
- 모든 write는 기존 도메인 ACL helper를 통과한다.
- 모든 write는 `llm_tool_call` audit + resource_ids 기록.
- 모든 write는 워크스페이스 외부 리소스를 건드릴 수 없다 (`LlmTaskContext.workspace_id` 강제).
- 툴 handler는 **deterministic + idempotent key 지원**: 같은 `approval_id`로 두 번 resolve해도 두 번 생성되면 안 된다.
- **halt당 approval 1건**. agent는 pending queue 첫 blocked에서 즉시 snapshot을 찍고 turn을 닫는다. 모델이 동시에 N개의 write를 제안하는 시나리오도 실제 집행은 순차 round-trip으로 처리한다.
- **Canonical replay = `AgentRunSnapshot.messages_json` 한 곳**. `ConversationTurn`은 UI 전용. 두 저장소의 내용이 상이해도 버그가 아니다 (UI는 마스킹/요약, replay는 raw).

---

## 3. 구현 단계

순서는 의존성 기준이다. 각 단계는 독립 커밋/PR로 분리 가능하되, 단계 간 동작하는 중간 상태를 유지한다.

### Step A — PMS write service 추출 (선행 리팩토링)

**목적**: Phase 3에서 read만 추출됐다. write 툴이 router ORM을 재호출할 수 없으니 먼저 service 경계로 끌어낸다.

**대상 파일**:
- [`apps/api/src/aidoo_api/domains/pms/service.py`](../apps/api/src/aidoo_api/domains/pms/service.py) — 신규 함수 추가:
  - `create_issue(db, *, workspace, actor, list_id, payload: IssueCreateRequest) -> Issue`
  - `update_issue(db, *, workspace, actor, issue_id, payload: IssueUpdateRequest) -> Issue`
  - `add_issue_comment(db, *, workspace, actor, issue_id, body: str) -> IssueComment`
- [`apps/api/src/aidoo_api/domains/pms/router.py`](../apps/api/src/aidoo_api/domains/pms/router.py) — 기존 route 바디를 service 호출로 슬림화 (line 2126 create_issue, 2228 update_issue, 2478 create_issue_comment).
- ACL helper(`_ensure_list_editor`, `_get_issue_for_user`)는 service로 함께 이동. router는 request/response 변환만 수행.

**행동 변화 없음**. 완료 기준: 기존 PMS 통합 테스트 그린.

### Step B — `AiToolApproval` + `AgentRunSnapshot` 모델, envelope 확장, resume endpoint 골격

**신규 파일**:
- `apps/api/src/aidoo_api/domains/ai/approvals.py` — 모델 + service (snapshot 포함)
- `apps/api/alembic/versions/<hash>_add_ai_tool_approvals_and_snapshots.py` — migration (두 테이블 한 파일)

#### B.1 `ai_tool_approvals`

```
ai_tool_approvals
  id              STRING(36) PK              -- = approval_id
  workspace_id    FK workspaces NOT NULL INDEX
  conversation_id FK conversations NOT NULL INDEX
  agent_run_id    STRING(36) NOT NULL INDEX  -- = AgentRunSnapshot.id
  tool_call_id    STRING(80) NOT NULL        -- LLM가 부여한 call id (envelope `call_id`와 동일)
  tool_name       STRING(80) NOT NULL
  arguments_json  TEXT NOT NULL
  resource_preview TEXT NULL
  status          STRING(16) NOT NULL DEFAULT 'pending'
                  -- pending|approved|rejected|expired|executed|failed
  requested_by_user_id FK users NOT NULL
  resolved_by_user_id  FK users NULL
  reject_reason   TEXT NULL                  -- Medium 피드백: 모달/API/envelope와 정합
  resolved_at     TIMESTAMP NULL
  expires_at      TIMESTAMP NOT NULL         -- default now()+24h
  execution_result_json TEXT NULL            -- 성공 시 resource_ids 포함
  error_message   TEXT NULL
  created_at      TIMESTAMP NOT NULL
  CHECK status IN ('pending','approved','rejected','expired','executed','failed')
  UNIQUE (agent_run_id, tool_call_id)        -- 재개 round-trip 마다 1:1
  INDEX (workspace_id, status)
  INDEX (conversation_id, status)
```

#### B.2 `ai_agent_run_snapshots`

§2.2.1에 정의한 스키마 그대로. 실제 migration에서는 `messages_json` / `model_meta`를 JSONB로 두고 Postgres GIN 인덱스는 **걸지 않는다** (쿼리 파턴이 PK 조회 위주).

#### B.3 Envelope 확장 — [`domains/ai/events.py`](../apps/api/src/aidoo_api/domains/ai/events.py) 및 [`agent-events.ts`](../apps/web/src/domains/ai/agent-events.ts)

기존 Phase 2 reserved 스키마를 확장한다:

```python
class ApprovalRequiredData(BaseModel):
    approval_id: str
    call_id: str                   # 신규 — tool_call 와 1:1 매칭
    tool: str
    resource_preview: str | None = None
    expires_at_ms: int             # 신규 — UI 타이머

class ApprovalResolvedData(BaseModel):
    approval_id: str
    call_id: str                   # 신규
    decision: Literal["approved", "rejected"]
    reason: str | None = None      # 신규 — Medium 피드백
```

TS 쪽 `PendingApproval` 인터페이스에도 `call_id`, `expires_at_ms`, `reason?` 추가. 기존 필드는 보존 (무해한 확장).

`done` envelope `meta`에 추가:

- `pending_approval_id: str | null`
- `pending_call_id: str | null`
- `finish_reason`: 기존 `stop | length | error | cancelled`에 **`awaiting_approval`** 추가 (P2 done 스키마에 string literal union 확장).

#### B.4 서비스 함수 (approvals.py)

- `create_pending_approval(db, *, ctx, tool_call_id, tool_name, arguments_json, resource_preview) -> AiToolApproval`
- `resolve_approval(db, *, approval_id, decision, reason, resolver_user) -> AiToolApproval` — 상태 전이 검증 (pending → approved/rejected). 이미 resolved면 409. 만료됐으면 lazy-expire 후 410.
- `expire_stale_approvals(db, older_than)` — cron hook (Phase 6 UI 전까지 기본 24h). 실행 시 관련 snapshot도 `abandoned`로 전이.
- `load_snapshot(db, *, agent_run_id, for_update: bool) -> AgentRunSnapshot` — `SELECT … FOR UPDATE` 옵션.
- `persist_snapshot_on_halt(db, *, ctx, messages_json, blocked_call_id, model_meta, parent_run_id=None) -> AgentRunSnapshot` — 첫 halt는 `parent_run_id=None`, 재halt는 직전 snapshot.id.
- `mark_snapshot_completed(db, snapshot) -> None` — 재halt 혹은 정상 종료 시 status 전이.
- `mark_snapshot_resumed(db, snapshot) -> None` — resume 진입 시 `awaiting_approval` → `resumed` 전이 (중복 resume 차단용).
- `abandon_stale_snapshot(db, snapshot, *, cause) -> None` — `awaiting_approval` → `abandoned` 전이 + 연관 approval `expired`.

#### B.5 신규 라우트

- `POST /api/v1/workspaces/{slug}/ai/approvals/{approval_id}/resolve` — REST. body `{decision: "approved"|"rejected", reason?: string}`. resolve만 수행 (실제 툴 실행은 resume SSE에서). 동일 approval_id 두 번 resolve → 409. 다른 user → 403. 만료 → 410.
- `POST /api/v1/workspaces/{slug}/ai/chat/resume` — SSE 스트리밍. body `{conversation_id, approval_id}`. 서버가:
  1. approval 상태 확인 (`approved` / `rejected` 모두 허용, `pending`이면 400).
  2. snapshot `FOR UPDATE` lock.
  3. canonical messages 복원 → agent 재개.
- 두 라우트 모두 **legacy `/api/v1/ai/...` + slug `/api/v1/workspaces/{slug}/ai/...` 이중 마운트** (Phase 1 entry contract).

이 단계 완료 시점엔 실제 write 툴이 아직 없으므로 resume이 의미 있는 tool을 실행하진 않는다. 다만 endpoint 계약, DB 스키마, envelope 확장은 전부 고정된다. Step C/D가 이 위에 올라탄다.

### Step C — tool_service / tool_runtime / agent 리팩토링 (canonical replay)

**[`tool_service.py`](../apps/api/src/aidoo_api/domains/ai/tool_service.py) 변경**:
- `execute_tool(..., approved_call_id: str | None = None)` 파라미터 추가.
- `approval_required=True` 툴 분기:
  - `approved_call_id`가 없으면 → 전용 예외 `ToolRequiresApproval(tool_call_id, tool_name, arguments_json, resource_preview)` 발생. HTTPException을 벗어나 agent 루프가 잡도록 한다. approval 레코드 자체는 **agent 루프가 halt 확정 시점에 한 번만 생성**한다 (tool_service 내부에서 즉시 만들면 halt 아닌 경로의 롤백이 어려워짐).
  - `approved_call_id`가 있으면 → approval row 조회, `status in {approved, rejected}` / workspace / user 검증, 통과 시:
    - `approved`: handler 호출 후 row를 `executed`로 전이.
    - `rejected`: handler를 호출하지 않고 `{"status":"rejected","reason":<reason>}` content를 돌려준다 (agent가 tool message로 주입).

**[`tool_runtime.py`](../apps/api/src/aidoo_api/domains/ai/tool_runtime.py) 변경**:
- `execute_tool_call` 시그니처에 `approved_call_id` 추가 + `ToolRequiresApproval` 분기.
- `iter_tool_call_events`:
  - blocked 시 **`approval_required` envelope의 payload에 `call_id` + `expires_at_ms` 포함** (Step B.3 스키마).
  - 재개 턴에서는 `approval_resolved` envelope를 먼저 emit한 다음 `tool_result`(approved) 또는 tool_result(status="rejected") 패턴으로 emit.
- 에러 envelope `agent_loop_blocked_tool_call` **제거** (halt는 에러 아님).

**[`agent.py`](../apps/api/src/aidoo_api/domains/ai/agent.py) 변경**:
- Line 211~314의 pending queue 루프 재작성:
  - queue 순회 중 `ToolRequiresApproval`이 발생하면 **그 call에서 halt**.
  - halt 직전 시점까지의 **OpenAI canonical message list**(system/user/prior assistant+tool pairs)를 집계해 `AgentRunSnapshot.messages_json`으로 persist. `blocked_call_id` 세팅, status=`awaiting_approval`.
  - blocked call 뒤에 남은 pending call은 **실행하지 않고** snapshot/canonical messages에 기록도 하지 않는다. 모델이 재개 턴에서 다시 계획하도록 둠.
  - `AiToolApproval` 레코드 생성 (approval service 경유).
  - `approval_required` envelope emit + `ConversationTurn.assistant`를 UI persistence rule로 저장 (meta에 `agent_run_id`, `pending_approvals=[{approval_id, call_id, tool, ...}]` 포함).
  - `done{finish_reason:"awaiting_approval", meta:{pending_approval_id, pending_call_id}}` emit 후 return.

- 신규 진입점 `resume_agent_run(db, *, conversation, approval_id, user, workspace) -> AsyncIterator[Envelope]`:
  1. `approvals.resolve_approval`가 이미 REST 호출로 수행됐는지 확인. `pending`이면 400.
  2. `load_snapshot(..., for_update=True)` — advisory lock + status `awaiting_approval` 확인 (아니면 410).
  3. `messages = snapshot.messages_json` 로드.
  4. `execute_tool_call(..., approved_call_id=approval_id)`:
     - approved → 실제 handler 수행 후 `tool_result` envelope emit. canonical messages에 `{role:"assistant", tool_calls:[{id:call_id,...}]}` + `{role:"tool", tool_call_id:call_id, content:<result>}` append.
     - rejected → `approval_resolved(decision=rejected, reason)` + `tool_result(status="rejected")` emit. canonical에도 동일 assistant/tool pair append (content는 rejected payload).
  5. snapshot status=`resumed`로 전이.
  6. agent 루프 main loop 계속 → 또 blocked가 나오면:
     - 현재 snapshot.status = `completed` 로 마감 + updated_at 갱신.
     - 새 `AgentRunSnapshot` 생성: 새 `agent_run_id`, `parent_run_id` = 방금 마감한 snapshot.id, `messages_json` = 현재 halt까지의 canonical prefix (rejected/approved tool pair 포함), status=`awaiting_approval`.
     - 새 `AiToolApproval` 생성.
     - 새 `approval_required` envelope + `done{awaiting_approval, meta:{pending_approval_id, pending_call_id, agent_run_id}}` emit 후 return.
     - 새 `ConversationTurn.assistant` row append (meta에 새 pending_approvals).
  7. 정상 stop 도달 시:
     - 현재 snapshot.status = `completed`.
     - `ConversationTurn.assistant` 최종 row를 append (UI 전용 meta, 이 resume 단계 tool_calls 합본).
     - `done{stop}` emit.

**finish_reason 확장**: `stop | length | error | cancelled | awaiting_approval`. done.meta에 `pending_approval_id`, `pending_call_id`, `agent_run_id` 포함.

**Canonical message 직렬화 규칙** (명세):
- `system`, `user`, `assistant(content)` — 그대로 저장.
- `assistant` with tool_calls — `{role:"assistant", content:null|string, tool_calls:[{id, type:"function", function:{name, arguments}}]}`.
- `tool` — `{role:"tool", tool_call_id, content}`. content는 `serialize_tool_result_for_llm` 결과와 동일 포맷 ([`tool_service.py`](../apps/api/src/aidoo_api/domains/ai/tool_service.py)).
- rejection tool message: `content = {"status":"rejected", "reason": reason|null}` JSON string.
- snapshot 저장 시 content는 UI 마스킹 **적용 전** 원본. 단, PII 정책상 external로 보내는 경우 별도 마스킹 파이프가 Phase 1 ruleset대로 동작 (이중 저장 아님).

### Step D — write 툴 6종 등록

각 도메인 `tools.py`에 handler + args model + `register_tool(..., approval_required=True)` 추가.

#### D.1 PMS 3종 — [`pms/tools.py`](../apps/api/src/aidoo_api/domains/pms/tools.py)

| Tool | Args (Pydantic) | Handler 위임 | Resource IDs |
|---|---|---|---|
| `pms.create_issue` | `list_id, title, body?, assignee_ids?, labels?, due_date?` | `pms_service.create_issue` | `[issue.id]` |
| `pms.update_issue` | `issue_id, title?, body?, status?, assignee_ids?, due_date?` | `pms_service.update_issue` | `[issue.id]` |
| `pms.add_comment` | `issue_id, body` | `pms_service.add_issue_comment` | `[comment.id, issue.id]` |

#### D.2 Meeting / Planner / Docs 각 1종

| Tool | Service | Args | Approval preview |
|---|---|---|---|
| `meeting.create_meeting` | `meeting_service.create_meeting` | `title, start_at, end_at, attendee_user_ids?, location?, description?` | title + start_at + 참석자 수 |
| `planner.create_event` | `planner_service.create_event` | `title, start_at, end_at, scope ("personal"/"team"), team_id?, description?` | title + start_at + scope |
| `docs.create_page` | `docs_service.create_native_doc_for_user` | `hub_id, title, content_markdown?, parent_id?` | title + hub 이름 |

**arguments validation**: 각 Pydantic 모델은 ISO8601 datetime parsing, naive/aware 변환, workspace scope 체크는 handler가 수행.

**resource_preview 생성**: 각 tool은 handler와 별개로 `preview_arguments(args) -> str` 옵션 함수 등록 가능. 없으면 args JSON 240자 truncate(기존 동작).

**idempotency**: 각 write handler는 `idempotency_key=approval_id`를 받도록 service 시그니처 확장. PMS issue는 이미 `new_id()`를 내부 생성하므로 handler가 approval_id를 PK로 바로 쓰면 이중 생성 방지 자연스럽게 됨. meeting/planner/docs도 동일 패턴.

### Step E — 회의 지능화: 모델 + 워커 + 툴

#### E.1 `MeetingInsight` 모델 + migration

```
meeting_insights
  id              STRING(36) PK
  meeting_id      FK meetings NOT NULL INDEX
  recording_id    FK meeting_recordings NULL
  workspace_id    FK workspaces NOT NULL INDEX
  insight_type    STRING(24) NOT NULL   -- action | decision | followup_schedule
  payload_json    JSONB NOT NULL        -- 아래 스키마별
  confidence      FLOAT NULL
  source_span     JSONB NULL            -- {start_ms, end_ms, quote}
  status          STRING(16) NOT NULL DEFAULT 'draft'   -- draft | accepted | rejected | superseded
  accepted_as_kind STRING(24) NULL      -- pms_issue | planner_event | docs_page
  accepted_as_id   STRING(36) NULL
  created_at      TIMESTAMP NOT NULL
  created_by_run_id STRING(36) NULL     -- agent_run_id
  INDEX (meeting_id, insight_type, status)
  INDEX (workspace_id, status)
```

**payload_json 구조** (타입별):
- `action`: `{title, description?, proposed_assignee_user_id?, proposed_due_date?, proposed_list_id?}`
- `decision`: `{statement, rationale?, decided_by_user_ids?[]}`
- `followup_schedule`: `{proposed_title, duration_minutes, proposed_slots: [{start_at, end_at}], attendee_user_ids?}`

#### E.2 워커 확장 — [`apps/worker/src/aidoo_worker/tasks/meeting.py`](../apps/worker/src/aidoo_worker/tasks/meeting.py)

summary 태스크 후 신규 태스크 체인:
- `extract_meeting_insights(recording_id)` — summary_text + transcript_text를 입력으로 세 가지 LLM 호출:
  - action items 추출 (`task_kind="meeting_insight_actions"`)
  - decisions 추출 (`task_kind="meeting_insight_decisions"`)
  - followup 후보 일정 (`task_kind="meeting_insight_followup"`)
- 각 LLM 응답을 `MeetingInsight` row로 persist. JSON 스키마 강제 검증 (Pydantic). 실패 시 해당 insight 타입만 skip + audit warning.

**LlmTaskContext**: `source="worker.meeting.extract_insights"`, `actor_user_id=None` (system-triggered), `workspace_id=recording.meeting.workspace_id`. 정책 seed는 `meeting_summary`와 동일하게 local_only.

**Chain**: `transcribe_recording → summarize_recording → extract_meeting_insights` (celery `chain()`). 실패 격리 — extract 실패가 summary 완료를 무효화하지 않음.

#### E.3 챗 툴 3종 — [`meeting/tools.py`](../apps/api/src/aidoo_api/domains/meeting/tools.py)

대화형 사용 (workspace_id 필수):

| Tool | 목적 | Approval |
|---|---|---|
| `meeting.extract_actions` | meeting_id → pending action insights 반환 + 필요 시 재추출 요청 | 재추출=no, 조회만=no (read) |
| `meeting.extract_decisions` | 동일 | read |
| `meeting.draft_followup_schedule` | meeting_id + 참석자 set → proposed_slots 반환 (기존 `meeting.find_availability` 재사용) | read |

**이 3개 자체는 read**. 실제 리소스 생성은 D의 write 툴 (`pms.create_issue` 등)에서 이뤄진다. 즉 회의 챗 플로우는:

> "어제 회의 액션 이슈로" → agent가 `meeting.extract_actions` (read, 자동 실행) → 반환된 action 3개 각각에 대해 `pms.create_issue` (write, 승인 필요) 3번 제안 → 사용자가 3번 승인 → agent가 각각 resume 턴으로 실행 → 완료.

#### E.4 MeetingInsight UI 연동

meeting detail view에 "AI 제안" 섹션 추가:
- pending action/decision/followup 리스트.
- 각 항목에 **"챗에서 진행"** 버튼 → `{scope_ref:"meeting", scope_resource_id:<meeting.id>}`로 conversation 생성 + 자동 prompt (`이 제안을 이슈로 만들어줘` 등) 주입. 실제 실행은 여전히 승인 게이트 통과.
- MeetingInsight 자체 accept/reject (챗 경유 없이) 버튼은 Phase 4 범위 밖 (UI만 read-only).

### Step F — `scope_ref` 도입

#### F.1 Conversation 스키마 migration

`Conversation` 테이블에 `scope_ref STRING(24) NULL`, `scope_resource_id STRING(36) NULL`. index `(workspace_id, scope_ref, scope_resource_id)`.

#### F.2 Conversation 생성 API

현재는 첫 chat stream 요청에서 암묵적으로 생성. Phase 4는 명시 생성도 허용:
- `POST /api/v1/workspaces/{slug}/ai/conversations` body `{scope_ref?, scope_resource_id?, title?}`.
- scope resource에 대한 ACL 검사 (meeting이면 `can_read_meeting`, pms issue면 `_get_issue_for_user`).

#### F.3 Agent system prompt에 scope 주입

`agent.py` build_system_prompt에 scope 블록 추가:
- meeting scope: 회의 제목 + 시작시각 + 참석자 + transcript의 **마지막 요약 또는 transcript 앞 4000자** 삽입.
- pms issue scope: 이슈 title/status/assignee/body.
- docs page scope: 문서 제목 + 헤딩 요약.

scope를 건드리는 write 툴(예: `pms.update_issue` with 다른 issue_id)은 agent 시스템 프롬프트에 명시적으로 "scope 밖 리소스는 명시 사용자 지시 없이 변경 금지" 문구 추가. 가드레일은 프롬프트 레벨 + tool handler 레벨 ACL 이중.

#### F.4 Meeting view → chat 진입

- [`apps/web/src/components/views/meeting`](../apps/web/src/components/views/meeting) 어딘가의 meeting detail → "AI로 처리" 버튼.
- click → `POST /ai/conversations` body `{scope_ref:"meeting", scope_resource_id:<meeting.id>}` → `AIView`로 라우트 + 빈 composer with hint "이 회의에서 할 일".

### Step G — 프론트 Approval 플로우

#### G.1 `ApprovalModal.tsx` 실구현

`apps/web/src/components/views/chat/ApprovalModal.tsx` (현재 null 반환 스텁) 재작성:
- props: `{approval: PendingApproval, onResolve: (decision) => Promise<void>, onClose: () => void}`.
- 표시:
  - tool name (icon + 한국어 라벨).
  - resource_preview 텍스트 (markdown safe-render).
  - **Full arguments JSON** 펼치기 (details 블록).
  - Approve / Reject 버튼. **Reject 시 optional reason textarea** (140자 제한, 빈값 허용). 입력한 값은 resolve API와 `approval_resolved` envelope `reason` 필드에 실린다 (§B.3, §B.5). 모델 입장에서 rejection tool message의 content에도 포함된다.
- 동작:
  - Approve → `POST /ai/approvals/{id}/resolve` body `{decision:"approved"}` → 성공 시 즉시 `POST /ai/chat/resume` body `{conversation_id, approval_id}` SSE 재연결.
  - Reject → `POST .../resolve` body `{decision:"rejected", reason?}` → resume 호출 (agent가 거절 결과로 루프 계속).
  - resume 스트림을 기존 `useChatStream` 상태에 합류.

#### G.2 `useChatStream` 훅 확장

- `pendingApprovals` state에 이미 자리 있음. `approval_required` event handler를 실제 modal trigger로. state 모양은 `{approval_id, call_id, tool, resource_preview, expires_at_ms, decision, reason}`로 확장 (§B.3 envelope과 정합).
- `done{finish_reason:"awaiting_approval"}` 수신 시 "응답을 기다리는 중" → 승인 UI 표출 상태로.
- `resumeWithApproval(approval_id, decision, reason?)` 메서드 추가: resolve API 호출 + SSE stream 연결.
- `approval_resolved` envelope 수신 시 해당 pendingApproval state를 resolved로 전이(모달 닫기 + ToolCallCard 상태 업데이트).

#### G.3 UI 폴리시

- Phase 4는 **halt당 approval 1건** (§2.2). 동시에 여러 modal을 띄우는 케이스는 발생하지 않는다. 그러나 "3개 연속 승인"은 일상이므로, 각 resume 응답에서 또 blocked가 나면 자동으로 다음 모달을 띄운다. UX는 사용자가 느끼기엔 큐지만 server 상태는 한 번에 하나만 pending.
- 대기 상태(`awaiting_approval` + 미해결 pendingApproval)에서 새 사용자 message 입력은 차단 + "현재 승인을 해결해야 다음 요청이 가능합니다" 안내. 입력창은 disabled, 대체 버튼 "요청 취소"는 REST `POST .../resolve` with rejected + reason="user cancelled"로 매핑.

### Step H — 감사 / 테스트 / 문서

#### H.1 Audit 확장

- `log_llm_tool_call`에 `approval_id` 필드 (nullable) 추가. write 툴 실행 시 필수.
- 신규 action `llm_tool_approval_resolved`: payload `{approval_id, tool_name, decision, resolver_user_id, elapsed_since_request_ms}`.
- MeetingInsight 생성도 `ai_meeting_insight_created` action으로 audit (workspace_id + meeting_id + insight_count per type).

#### H.2 테스트 (`apps/api/tests/` 확장)

**단위 / 통합**:
- `test_ai_approvals.py`:
  - pending → approved 전이 정상.
  - pending → rejected + reason(있음/없음) 전이 정상 + DB `reject_reason` 영속 확인.
  - approved 이중 resolve → 409.
  - 만료된 approval resolve → 410 gone + snapshot `abandoned` 동시 전이.
  - 다른 workspace approval_id → 404.
  - 다른 user resolve → 403.
  - envelope `approval_required.call_id`가 pending row `tool_call_id`와 일치.
- `test_ai_write_tools.py`:
  - 각 write 툴: approval 없이 실행 → `ToolRequiresApproval` 발생하되 **approval row는 아직 생성 안 됨** (agent halt 확정 시 생성).
  - agent halt까지 완주 → `AiToolApproval.pending` + `AgentRunSnapshot.awaiting_approval` 동시 persist 검증.
  - 승인 후 handler 실제 호출 + `resource_ids` audit + `approval_id` audit payload에 포함.
  - 승인 후 ACL 실패 (list에서 방금 제거된 멤버) → handler 쪽 403 + approval row `failed` + audit status=error.
  - idempotency: 같은 approval_id로 handler 호출 두 번 → 두 번째는 기존 결과 재활용 + row 이중 생성 없음.
- `test_agent_resume.py`:
  - halt 턴:
    - pending queue 첫 blocked에서 break. 뒤 pending call은 canonical messages와 snapshot 어느 쪽에도 기록되지 않음.
    - snapshot.messages_json이 OpenAI canonical 포맷(system/user/prior assistant-tool pairs)으로 persist.
    - `done{finish_reason:"awaiting_approval", meta:{pending_approval_id, pending_call_id, agent_run_id}}` emit.
    - UI용 `ConversationTurn.assistant`도 append되어 reload가 빈 bubble로 보이지 않음.
  - resume 턴 (approved):
    - snapshot FOR UPDATE lock.
    - handler 실행 → canonical messages에 assistant(tool_calls) + tool pair append.
    - `approval_resolved(decision=approved)` + `tool_result(ok)` envelope 순서 검증.
    - 진행 중인 resume과 동시에 같은 agent_run_id로 resume 재호출 → 409/410 (snapshot.status=resumed, FOR UPDATE 경합).
    - resume이 정상 종료되어 snapshot.status=completed가 된 뒤 동일 agent_run_id resume 재호출 → 410 gone.
  - resume 턴 (rejected with reason):
    - handler 호출되지 않음.
    - canonical tool message content에 `{"status":"rejected","reason":"..."}` JSON.
    - `approval_resolved(reason=...)` envelope에도 reason 포함.
  - **순차 다건 시나리오**:
    - 모델이 턴 1에서 action 3개를 요구 → 첫 번째만 blocked persist, 나머지 2개는 버림.
    - 승인 후 resume 중 agent가 또 blocked를 냄 → 직전 snapshot.status=`completed`, 새 snapshot이 `parent_run_id`=직전 id로 생성.
    - 반복. 최종적으로 3 issue가 모두 생성되고 각 생성마다 독립 `AiToolApproval` + `AgentRunSnapshot` row가 남는다.
    - Lineage 쿼리: 같은 `conversation_id`의 snapshot을 `parent_run_id` 체인으로 타고 올라가면 halt 3건이 순서대로 연결.
  - **Conversation 상호배제**:
    - `awaiting_approval` 스냅샷이 있는 conversation에 `POST /ai/chat/stream` → 409.
    - 해당 approval을 resolve + resume 정상 종료 후 동일 conversation에 stream → 200.
  - 동시성:
    - 같은 agent_run_id로 resume 동시 호출 2건 → 하나만 성공, 다른 하나 409.
- `test_ai_canonical_messages.py` (신규):
  - assistant(content+tool_calls) / tool message 직렬화/역직렬화 round-trip.
  - rejection tool content JSON schema 검증.
  - snapshot load → agent `messages` 변수로 그대로 공급해도 LLM이 tool_call_id mismatch 없이 소비하는지 provider adapter 계약 테스트.
- `test_meeting_insight_extractor.py`:
  - 더미 transcript → insights persist.
  - LLM JSON schema 위반 → 해당 type skip, audit warning.
  - celery chain 상에서 extract 실패가 summary 완료를 되돌리지 않음.
- `test_conversation_scope.py`:
  - meeting scope conversation 생성 + ACL 통과 + 두 컬럼(`scope_ref`, `scope_resource_id`) persist.
  - scope 리소스 권한 없는 user → 403.
  - system prompt에 scope 블록 주입 확인 (회의 제목/시작시각/transcript 발췌).

**프론트 (Playwright)** — `apps/web/tests/`에 케이스 추가:
- 승인 모달 띄우기, approve 후 tool_result 스트림 표시.
- reject 후 assistant가 거절 맥락으로 답변하는지.
- 여러 approval queue 동작.

**수동 스모크 체크리스트** (PR 본문 포함):
- 로컬 정책 write → approve → issue 실제 생성 확인.
- external-only 정책인 write 툴은 없음 (모두 local_only). 만약 향후 external이 필요하면 PII 가드 검토.
- 승인 24시간 만료 후 resume → 410.
- 회의 녹취 업로드 → summary + insights 3종 확인.
- meeting detail "AI로 처리" → scope chat 진입 + 자동 prompt.

#### H.3 문서

- [`DESIGN.md`](../DESIGN.md) approval modal 섹션 추가 (이미 P2 디자인 세션에서 커버 — 실구현 스펙만 반영).
- [`docs/planning-log.md`](../docs/planning-log.md) 엔트리는 **머지 후** 추가 (feedback 메모리: commit & push 승인 후에만).
- [`00-ai-platform-roadmap.md`](./00-ai-platform-roadmap.md) Phase 4 섹션 "결정 완료" 표 갱신 — MeetingInsight 스키마 결정, resume 모델, scope_ref 설계. 이 역시 **머지 완료 시점에 본 Phase 플랜 파일 제거와 함께**.

---

## 4. Verification

### 4.1 완료 조건 (roadmap과 정합)

- "어제 회의 액션 아이템 이슈로 만들어" 대화 1턴이 실제 PMS 이슈 다건 생성까지 도달. 각 이슈 승인 게이트 통과.
- 승인 없이 write 툴 실행 금지 — 자동화 테스트로 고정.
- ACL 실패 시 승인됐어도 리소스 변경 안 됨 — 자동화 테스트.
- 회의 녹취 업로드 → 몇 분 내에 action/decision/followup insights 생성. 0건이어도 에러 아님.
- meeting detail → chat scope 진입 → transcript 기반 답변 가능.
- 기존 read-only 툴 회귀 없음 (Phase 3 테스트 그린).

### 4.2 성능 / 운영

- `AiToolApproval` INDEX 미포함 쿼리 없음 (explain 확인).
- MeetingInsight 생성이 summary 완료 SLA를 2분 이상 늦추지 않음. 늦어지면 chain의 extract 단계만 별도 queue로 분리.
- resume 엔드포인트 동시성 — 같은 `agent_run_id`가 동시 두 번 resume 시도 → advisory lock 또는 row-level lock으로 한 쪽만 성공.

### 4.3 롤백 계획

Phase 4는 **4개 토글로 단계 롤백 가능**:
1. `AIDOO_AI_WRITE_TOOLS_ENABLED=false` — 각 write 툴 `register` 스킵. registry에 노출 안 됨 → LLM이 호출 불가. 기존 read 그대로.
2. `AIDOO_AI_APPROVAL_RESUME_ENABLED=false` — resume endpoint 404. 프론트는 fallback으로 "승인 후 새 대화 시작" 문구 표시.
3. `AIDOO_MEETING_INSIGHTS_ENABLED=false` — worker chain에서 extract 단계 skip.
4. `AIDOO_CONVERSATION_SCOPE_ENABLED=false` — conversation 생성 시 scope 인자 무시. 기존 free chat으로 fallback.

DB migration은 전진만. `AiToolApproval` / `MeetingInsight` 테이블과 `Conversation.scope_*` 컬럼은 롤백 시 남아도 무해.

---

## 5. 결정 로그

### 5.1 이번 플랜에서 확정

| 항목 | 결정 |
|---|---|
| **Replay state** | 신규 `AgentRunSnapshot` 테이블에 OpenAI canonical messages(`messages_json`) 보관. `ConversationTurn`은 UI 전용 persistence 유지 (역할 분리). |
| **Halt 범위** | **halt당 approval 1건**. agent는 첫 blocked에서 즉시 snapshot 찍고 종료. 뒤의 pending은 버리고 재개 턴에서 모델이 다시 계획. 동시 N-approval UX는 Phase 4 범위 밖. |
| **Envelope 확장** | `approval_required.call_id`, `approval_required.expires_at_ms`, `approval_resolved.reason` 추가. `done.finish_reason`에 `awaiting_approval` 추가. `done.meta`에 `pending_approval_id`/`pending_call_id`/`agent_run_id`. |
| **Reject reason 계약** | modal → resolve API(`reason?`) → DB `AiToolApproval.reject_reason` → envelope `approval_resolved.reason` → LLM 재개 턴 tool message `{status:"rejected",reason:"..."}`까지 한 계약으로 흐름. |
| **승인 상태 영속화** | `AiToolApproval` 테이블. `(agent_run_id, tool_call_id)` UNIQUE. Conversation에 embed 안 함. approval row 생성은 **agent halt 확정 시점**에 1회만 (tool_service 내부에서 선행 생성 금지). |
| **Agent pause/resume 모델** | 제안 턴 halt + snapshot persist → resolve REST → 별도 `/ai/chat/resume` SSE 턴. 단일 SSE hold 안 함. 같은 agent_run_id 동시 resume 금지(FOR UPDATE). |
| **Snapshot 수명주기** | 재halt마다 **새 `AgentRunSnapshot` row + 새 `agent_run_id`**를 만든다. 직전 snapshot은 `completed`로 마감하고 재사용하지 않는다. |
| **Snapshot lineage** | 새 snapshot의 `parent_run_id`가 직전 completed snapshot을 가리킨다 (첫 halt는 NULL). "이 이슈가 어떤 halt 체인으로 만들어졌나"를 단일 쿼리로 복원 가능. |
| **Conversation 단위 상호배제** | `awaiting_approval` snapshot이 살아있는 동안 같은 conversation에 새 stream turn을 열 수 없다(409). 프론트는 §G.3에서 입력 차단, 서버는 레이스 방어. |
| **MeetingInsight 스키마** | 별도 테이블 + `payload_json` 하이브리드. (로드맵 open 결정 해소) |
| **scope_ref 표현** | `scope_ref` + `scope_resource_id` **두 컬럼 쌍**. 문서 전체에서 `"meeting:<id>"` 단일 문자열 표현 금지. |
| **Idempotency** | handler는 `approval_id`를 idempotency key로 사용. 이중 실행 방지. |
| **Write 툴 정책** | 전부 `local_only`. external 정책 write는 Phase 4 범위 밖. |
| **회의 insight 3종** | action / decision / followup_schedule. 추출 실패는 타입별 격리. |
| **Approval UI** | modal 한 번에 한 건. resume 응답에서 또 blocked면 연쇄적으로 다음 모달 오픈. 사용자 입장에선 "3번 승인"이지만 server 상태는 항상 pending=1. |
| **회의 chat 진입점** | meeting detail view 버튼 + `{scope_ref:"meeting", scope_resource_id:<id>}`로 conversation 생성. |

### 5.2 Phase 4 실행 중 결정 필요

| 항목 | 기한 |
|---|---|
| `AgentRunSnapshot.messages_json` 저장 포맷을 "raw OpenAI message"로 둘지, provider-agnostic 중간 IR로 둘지 | Step C 초기 |
| reject reason 글자 수 제한 / i18n | Step G.1 구현 시 |
| MeetingInsight followup_schedule과 `meeting.find_availability` 데이터 중복 처리 | Step E.3 구현 시 |
| `scope_ref=pms_issue` / `scope_ref=docs_page` 지원 범위 (Phase 4에 meeting만 우선?) | Step F 킥오프 |
| write 툴 시스템 프롬프트 문구 (LLM이 쉽게 남용 않도록 "신중하게 제안" 유도) | Step D 리뷰 단계 |
| 만료 24h 값 조정 (정책 UI 없는 동안 상수) | Step B 구현 전 |
| 만료된 `awaiting_approval` snapshot을 새 stream 시작 시 `abandoned`로 강제 전이할지, 409로 거절할지 | Step C 구현 시 (§2.2.3 마지막 bullet) |

### 5.3 Phase 4 이후로 미룸

- 승인 위임 / 자동 승인 규칙 → Phase 6 policy UI와 함께.
- MeetingInsight manual 편집 UI → 제품 우선순위 재논의.
- Bulk atomic 승인 (여러 write 한 번 승인) → UX 검증 후 Phase 6 후보.
- **한 halt에 N개 approval 병렬 노출** — envelope에는 이미 `call_id`가 들어가 있으므로 스키마 breaking change 없이 확장 가능. `AgentRunSnapshot.blocked_call_id`를 `blocked_call_ids[]`로 확장, approvals 여러 건을 한 snapshot에 매다는 설계 전환만 필요.
- 승인 거절 사유 기반 모델 재학습 / 프롬프트 자동 조정 → 별도 트랙.

---

## 6. 예상 작업량 (참고용, 체크 없음)

| Step | 규모 |
|---|---|
| A. PMS write service 추출 | 1 day |
| B. Approval + AgentRunSnapshot 모델 + migration + envelope 확장 + endpoint 골격 | 1.5 days |
| C. tool_service / canonical replay / agent halt-persist / resume 구현 + 테스트 | 3 days |
| D. Write 툴 6종 등록 + handler 래핑 | 1.5 days |
| E. MeetingInsight + 워커 extract + 챗 read 툴 3종 | 2 days |
| F. Conversation scope_ref(두 컬럼) + meeting→chat UI | 1 day |
| G. ApprovalModal + reason 계약 + useChatStream 확장 + E2E | 1.5 days |
| H. Audit / 문서 / 수동 스모크 | 0.5 day |

총 **~12 working days** 가정. 병렬화 불가 요소: A → D, **B → C → G** 순서 체인 필수. Step C의 canonical replay 설계/테스트가 리스크 집중 포인트이므로 이 구간에서 2일 여유 확보. E, F는 D 이후 병렬 가능.

---

## 7. 킥오프 체크리스트

실행 착수 전:
- [ ] Phase 3 머지 요약을 [`docs/planning-log.md`](../docs/planning-log.md)에 기록 (현재 누락 상태).
- [ ] [`DESIGN.md`](../DESIGN.md)의 P4 컴포넌트 (ApprovalModal, meeting insight panel) 시안 확인.
- [ ] 로드맵 Phase 4 섹션의 "차후 결정 (Phase 킥오프 시)" 항목 중 `MeetingInsight 스키마` 본 플랜 결정으로 갱신 예고.
- [ ] 본 플랜을 사용자 리뷰 → 승인.

승인 후 Step A부터 순차 실행.
