# Phase 6 Evidence Runtime Implementation Plan

> 문서 성격: `Evidence-First Hybrid Agent Runtime`의 Phase 0-A 구현 플랜.
> 기준 문서: [`02-evidence-first-agent-runtime.md`](./02-evidence-first-agent-runtime.md)
> 범위: Phase 0 gate + Phase A minimal runtime kernel. Graph manager, verifier, search/external provider, template writer 구현은 후속 플랜으로 넘긴다.

## Context

Phase 6 전체 목표는 기존 single-loop agent를 deterministic fast path, manager-controlled graph, evidence-first specialist runtime으로 확장하는 것이다. 다만 첫 구현에서 전체 hybrid surface를 한 번에 만들면 상태기계, approval migration, external egress policy, graph runtime이 동시에 흔들린다.

따라서 이 플랜의 목표는 **나중에 graph/search/verifier/external path를 얹을 수 있는 최소 실행 기반**을 먼저 고정하는 것이다.

현재 코드 기준:

- 기존 interactive chat 실행은 `domains/ai/agent.py` single-loop path가 담당한다.
- 기존 approval checkpoint는 `domains/ai/approvals.py::AgentRunSnapshot`과 `AiToolApproval`이 담당한다.
- 기존 AI route, SSE envelope, tool registry, MCP bridge, RAG tools는 유지한다.
- 새 runtime 패키지와 DB table은 아직 없다.

이 플랜은 기존 single-loop behavior를 canonical fallback으로 유지한다. `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false`가 기본값이며, Phase 0-A에서는 graph manager를 실제 실행하지 않는다.

## Current Execution State

이 섹션은 세션 handoff용이다. 구현 세션이 끝날 때마다 짧게 갱신한다.

- Current PR/stage: PR 1 complete, ready for PR 2.
- Last completed: Added Phase 0 eval/gate fixtures and fixture schema validation tests.
- In progress: None.
- Next exact task: PR 2 — add `apps/api/src/aidoo_api/domains/ai/runtime/` minimal contracts, registry validation helper, and trace sequence helper.
- Files touched in PR 1: `apps/api/tests/fixtures/ai_runtime/`, `apps/api/tests/test_ai_runtime_eval_fixtures.py`, `plans/03-phase6-evidence-runtime-implementation.md`.
- Tests/checks run: `cd apps/api && uv run --python 3.12 pytest tests/test_ai_runtime_eval_fixtures.py`; `git diff --check -- apps/api/tests/fixtures/ai_runtime apps/api/tests/test_ai_runtime_eval_fixtures.py`.
- Known blockers: None for PR 2. Later PR 3 must confirm Alembic head and runtime model import path before migration.
- Do not touch: unrelated local `compose.prod-like.yml` modification unless explicitly requested.

## Architecture / Principles

### 1. Minimal kernel first

첫 구현은 다음 최소 contract만 실제 코드로 고정한다.

- `AgentRun`
- `AgentInvocation`
- `AgentTraceEvent`
- minimal `ExecutionGraph`
- minimal `EvidencePacket`
- runtime/eval feature flag skeleton

External LLM/search DTO, provider adapter, verifier, writer, graph manager는 정본 설계에는 남기지만 Phase 0-A 구현 대상이 아니다.

### 2. Additive migration only

기존 `AgentRunSnapshot`을 즉시 제거하지 않는다. 새 runtime table은 additive로 추가하고, 기존 approval flow에서 shadow-write로 새 runtime record를 남긴다.

초기 read path는 기존 snapshot을 계속 사용할 수 있다. 새 runtime table은 inspection, invariant test, future cutover 준비에 사용한다.

### 3. State invariants before graph behavior

Phase A의 핵심 성공 기준은 graph execution이 아니라 상태 불변식이다.

- 한 conversation에는 live `AgentRun`이 하나만 있어야 한다.
- 한 `AgentRun`에는 pending approval이 하나만 있어야 한다.
- approval halt/resume은 동일 `AgentRun` 아래 새 `AgentInvocation`으로 표현 가능해야 한다.
- resume에서 tool surface가 넓어지면 안 된다.
- trace event ordering은 UUID가 아니라 per-run monotonic sequence여야 한다.

### 4. No external provider execution

Phase 0-A에서는 external provider를 호출하지 않는다. Feature flag와 config skeleton만 추가한다.

`review_queue_required`는 미래 contract로만 남긴다. Phase 0-A runtime은 review queue backend가 없으면 approval 또는 denial로 수렴하도록 이후 단계에서 구현한다.

## Implementation Stages

### PR 1 — Phase 0 Eval And Gate Skeleton

목표: runtime 구현 전 baseline/eval을 담을 위치와 schema를 고정한다.

변경:

- `apps/api/tests/fixtures/ai_runtime/` 디렉터리를 추가한다.
- seed fixture는 네 그룹으로 둔다.
  - `routing_cases.json`
  - `grounded_answer_cases.json`
  - `sanitizer_leakage_cases.json`
  - `approval_safe_drafting_cases.json`
- fixture loader/helper를 테스트 전용 모듈에 둔다. production runtime은 이 fixture에 의존하지 않는다.
- launch SLO 항목을 fixture metadata 또는 plan-adjacent markdown에 명시한다.
  - concurrent active users
  - p95 TTFT
  - p95 report latency
  - approval wait time
- Qwen structured output hard gate는 benchmark target으로만 기록한다.
  - `ExecutionGraph` schema success rate
  - tool-call stability
  - malformed output rate

완료 조건:

- fixture loader가 네 그룹을 모두 읽고 schema validation을 수행한다.
- fixture는 실제 고객명/제품명/주문번호를 포함하지 않는다.
- 테스트는 LLM/network 호출 없이 실행된다.

### PR 2 — Runtime Kernel Contracts

목표: runtime package와 최소 DTO를 추가한다.

변경:

- 새 패키지: `apps/api/src/aidoo_api/domains/ai/runtime/`
- 권장 모듈:
  - `contracts.py`: Pydantic/dataclass contract.
  - `registry_validation.py`: registry-validated string helper.
  - `trace.py`: monotonic trace sequence helper.
- `ExecutionGraph`는 closed enum을 쓰지 않는다.
  - `agent_id: str`
  - `intent: str`
  - `domains: list[str]`
  - `output_kind: str`
  - `risk: Literal["low", "medium", "high"]` 또는 기존 risk literal과 같은 값.
- `AgentInvocationSpec.agent_id`는 `AgentDefinitionResolver`나 runtime registry 결과에 있어야 valid다.
- minimal `EvidencePacket`은 internal evidence 중심으로 둔다.
  - query plan metadata.
  - evidence items.
  - coverage summary.
  - external-specific fields는 optional로 두되 Phase 0-A runtime에서는 생성하지 않는다.
- `AgentTraceEvent` contract는 `run_seq`, `invocation_seq`, `event_seq`를 포함한다.

완료 조건:

- invalid `agent_id`, `intent`, `domain`, `output_kind`를 registry validator가 거부한다.
- trace sequence helper가 같은 run 안에서 monotonic ordering을 보장한다.
- contract tests가 LLM/network 없이 통과한다.

### PR 3 — Runtime Persistence And Migration

목표: additive DB table과 SQLAlchemy model을 추가한다.

변경:

- Alembic migration으로 새 table을 추가한다.
  - `ai_agent_runs`
  - `ai_agent_invocations`
  - `ai_agent_trace_events`
- `alembic/env.py`와 test metadata import path에 runtime models를 포함한다.
- `AgentRun` status는 최소 다음 값을 가진다.
  - `pending`
  - `running`
  - `awaiting_approval`
  - `completed`
  - `failed`
  - `cancelled`
  - `abandoned`
- `AgentInvocation` status도 동일 계열을 사용하되 invocation 단위로 저장한다.
- `AgentTraceEvent`는 per-run ordering을 위해 정수 sequence를 저장한다.
- DB invariant:
  - live status에 해당하는 conversation당 run은 하나만 허용한다.
  - pending approval에 연결된 run은 하나의 pending approval만 허용하도록 기존 approval table 또는 runtime projection에 partial unique index를 추가한다.

권장 column 원칙:

- `workspace_id`, `conversation_id`, `requested_by_user_id`는 query와 audit에 필요한 FK/index를 가진다.
- `runtime_profile`, `model_profile_id`, `graph_enabled`, `fallback_reason`은 nullable metadata로 시작한다.
- payload는 JSONB로 둘 수 있지만 raw reasoning, tool secret, raw provider reasoning trace는 저장하지 않는다.

완료 조건:

- migration upgrade/downgrade가 안전하게 동작한다.
- model smoke test가 create/read를 검증한다.
- concurrent test가 live run/pending approval invariant를 검증한다.

### PR 4 — Snapshot Shadow-Write And Resume Scope Guard

목표: 기존 approval halt/resume flow를 깨지 않고 새 runtime record를 남기며, resume scope widening을 차단한다.

변경:

- 기존 `persist_snapshot_on_halt` 흐름에서 새 `AgentRun`/`AgentInvocation`을 shadow-write한다.
- 기존 `AgentRunSnapshot.model_meta` 또는 새 compat metadata에 다음을 저장한다.
  - resolved tool names.
  - resolved agent/app scope.
  - original `allowed_app_ids`.
  - blocked tool call id.
  - payload hash 또는 approval payload reference.
- `/chat/resume`에서 `allowed_app_ids`가 생략되면 원 halt scope를 그대로 사용한다.
- `/chat/resume`에서 `allowed_app_ids`가 전달되면 저장된 scope와 같거나 더 좁은 경우만 허용한다.
- wider scope 요청은 400 또는 approval-specific error로 차단한다.
- re-halt는 같은 `AgentRun` 아래 새 invocation/checkpoint로 표현할 수 있게 trace/persistence helper를 둔다.

완료 조건:

- 기존 approval API 응답 shape는 유지된다.
- 기존 approval tests가 통과한다.
- omission, equal scope, narrower scope, wider scope 네 케이스가 테스트된다.
- resume 시 tool registry가 전체 entitlement로 넓어지지 않는다.

### PR 5 — Trace And Inspection Endpoint

목표: runtime record를 운영자가 SQL 없이 확인할 수 있게 한다.

변경:

- runtime trace write helper를 추가한다.
- 기존 agent/approval flow에서 최소 trace event를 남긴다.
  - `run_created`
  - `invocation_started`
  - `approval_required`
  - `approval_resumed`
  - `invocation_completed`
  - `run_completed`
  - `run_failed`
- read-only inspection endpoint를 추가한다.
  - workspace-scoped `/api/v1/workspaces/{workspace_slug}/ai/runtime/runs/{run_id}`
  - 필요하면 list endpoint는 Phase A 후속으로 미룬다.
- endpoint는 기존 workspace auth dependency와 ACL boundary를 사용한다.
- 응답은 raw reasoning, tool secret, raw provider payload를 포함하지 않는다.

완료 조건:

- 같은 workspace 사용자는 run/invocation/trace summary를 조회할 수 있다.
- 다른 workspace 사용자는 조회할 수 없다.
- event ordering이 run 안에서 재현 가능하다.
- trace payload scrub test가 통과한다.

## Verification

### Targeted tests

Phase 0-A 구현 후 최소 다음을 실행한다.

```bash
cd apps/api
pytest tests/test_ai_approvals.py
pytest tests/test_ai_stream.py
pytest tests/test_ai_events.py
pytest tests/test_ai_conversations.py
```

### New tests

- `test_ai_runtime_contracts.py`
  - DTO validation.
  - registry-validated string rejection.
  - trace monotonicity.
- `test_ai_runtime_persistence.py`
  - `AgentRun` / `AgentInvocation` / `AgentTraceEvent` create/read.
  - live run invariant.
  - pending approval invariant.
- `test_ai_runtime_eval_fixtures.py`
  - fixture loader.
  - fixture schema validation.
  - no network/LLM dependency.
- approval regression additions.
  - resume without `allowed_app_ids` does not widen tools.
  - same scope resume works.
  - narrower scope resume works only when it does not invalidate the approved tool.
  - wider scope resume is rejected.
- inspection endpoint tests.
  - auth required.
  - workspace isolation.
  - payload omits raw reasoning/tool secrets.

### Static checks

```bash
git diff --check
cd apps/api && pytest tests/test_ai_runtime_contracts.py tests/test_ai_runtime_persistence.py tests/test_ai_runtime_eval_fixtures.py
```

## Decision Log

| 항목 | 결정 |
|---|---|
| 구현 범위 | Phase 0-A minimal kernel only |
| graph runtime | Phase 0-A에서는 실행하지 않음 |
| external provider | Phase 0-A에서는 호출하지 않음 |
| 기존 single-loop | canonical fallback으로 유지 |
| `AgentRunSnapshot` | 즉시 제거하지 않고 shadow-write/compat projection 사용 |
| `ExecutionGraph` value | closed enum이 아니라 registry-validated string |
| trace ordering | per-run monotonic sequence |
| resume scope | halt 시 저장한 scope와 같거나 더 좁은 경우만 허용 |
| review queue | backend 준비 전에는 구현하지 않음 |

## Rollback Plan

- `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false`가 기본값이므로 graph behavior는 활성화되지 않는다.
- runtime shadow-write에 문제가 있으면 shadow-write helper를 feature flag 뒤로 비활성화하고 기존 `AgentRunSnapshot` read/write path를 유지한다.
- inspection endpoint에 문제가 있으면 route registration만 끄고 persistence는 유지한다.
- migration rollback은 새 runtime table을 제거하되 기존 `AgentRunSnapshot`과 `AiToolApproval` table은 변경하지 않는 방향으로 작성한다.
- resume scope guard에서 false reject가 발생하면 기존 approval tests와 audit trace로 원인을 확인하고, widen 허용 없이 scope comparison 로직만 수정한다.

## Assumptions

- `compose.prod-like.yml`의 현재 local modification은 unrelated이며 이 플랜 구현에서 건드리지 않는다.
- Phase 0-A는 code foundation이며 사용자-facing graph behavior를 켜지 않는다.
- `review_queue_required`는 이후 Phase 7/admin policy 또는 durable workflow backend가 생긴 뒤 활성화한다.
- External LLM/search DTO와 provider adapter는 Phase B/C 이후 별도 구현 플랜에서 다룬다.
- 구현 완료 후 commit/push는 사용자가 별도로 요청할 때만 수행한다.
