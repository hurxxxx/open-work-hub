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
- 새 runtime 패키지와 additive DB table은 Phase 0-A에서 추가되었고, 현재는 shadow-write/inspection 용도로만 사용한다.

이 플랜은 기존 single-loop behavior를 canonical fallback으로 유지한다. `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false`가 기본값이며, Phase 0-A에서는 graph manager를 실제 실행하지 않는다.

## Current Execution State

이 섹션은 세션 handoff용이다. 구현 세션이 끝날 때마다 짧게 갱신한다.

- Current PR/stage: Phase 0-AH external provider adapter protocol after `2fa930d`.
- Last completed: Added first-class external planner/search execution adapter protocols and mock adapter implementations. Router egress wiring now executes through `MockExternalPlannerAdapter` and `MockExternalSearchAdapter` instead of calling mock functions directly, while the legacy helper functions remain available for focused tests. Protocol tests verify the mock adapters preserve adapter id, execution provider, and summary output shape. This creates the seam future OpenAI/Anthropic adapters can implement without changing routing metadata paths.
- In progress: None.
- Next exact task: Add adapter-selection helpers that choose mock vs future real external planner/search adapters from settings, while still defaulting to mock-only behavior until real providers are explicitly implemented.
- Files touched in Phase 0-AH: `apps/api/src/aidoo_api/domains/ai/router.py`, `apps/api/src/aidoo_api/domains/ai/runtime/__init__.py`, `apps/api/src/aidoo_api/domains/ai/runtime/external_adapters.py`, `apps/api/src/aidoo_api/domains/ai/runtime/external_planner.py`, `apps/api/src/aidoo_api/domains/ai/runtime/external_search.py`, `apps/api/tests/test_ai_runtime_external_planner.py`, `apps/api/tests/test_ai_runtime_external_search.py`, `plans/03-phase6-evidence-runtime-implementation.md`.
- Tests/checks run: `cd apps/api && uv run ruff check src/aidoo_api/domains/ai/router.py src/aidoo_api/domains/ai/runtime/__init__.py src/aidoo_api/domains/ai/runtime/external_adapters.py src/aidoo_api/domains/ai/runtime/external_planner.py src/aidoo_api/domains/ai/runtime/external_search.py tests/test_ai_runtime_external_planner.py tests/test_ai_runtime_external_search.py`; `cd apps/api && uv run pytest tests/test_ai_runtime_external_planner.py tests/test_ai_runtime_external_search.py tests/test_ai_runtime_eval_fixtures.py tests/test_ai_runtime_mock_e2e.py`; `scripts/phase6-mock-e2e.sh -q`.
- Known blockers: OpenAI/Anthropic-backed manager/search execution is still not enabled. The egress/planner/search contracts only decide, sanitize, and build request envelopes; they do not call external APIs. `graph_node_runner_v0` remains an in-process runner, not a durable workflow backend. Hidden node outputs are not persisted verbatim; only status/count/error summary is persisted. High-risk / approval-preview graphs are intentionally not supported by this adapter.

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

### 4. Runtime profile routing is shadow-only in Phase 0-A

`select_runtime_profile()`는 Phase 0-A에서 실행 분기를 바꾸지 않고 model metadata와 runtime shadow state에 기록하는 shadow classifier다. `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false`이면 graph behavior는 계속 비활성이다.

초기 rule priority는 `long_doc` signal을 먼저 보고, 그 다음 report/multi-app synthesis signal을 본 뒤, 마지막으로 write/external action signal을 본다. 따라서 "보고서/리포트/비교" 의도와 "초안" 같은 draft 표현이 함께 있는 경우에는 `grounded_report`로 분류하고, 명시적 write/create/update action만 있는 경우 `high_risk_action`으로 분류한다.

### 5. No external provider execution

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
- resume execution은 저장된 `resolved_tool_names`와 현재 entitlement/registry 결과의 교집합만 agent loop에 전달한다.
- wider scope 요청은 400 또는 approval-specific error로 차단한다.
- narrower scope가 승인된 tool을 제외하면 resume을 거부한다.
- re-halt는 같은 `AgentRun` 아래 새 invocation/checkpoint로 표현할 수 있게 trace/persistence helper를 둔다.

완료 조건:

- 기존 approval API 응답 shape는 유지된다.
- 기존 approval tests가 통과한다.
- omission, equal scope, narrower scope, wider scope 네 케이스가 테스트된다.
- resume 시 tool registry가 전체 entitlement로 넓어지지 않는다.
- runtime shadow-write 실패는 user-facing approval flow를 abort하지 않는다.

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
| resume tool surface | 저장된 `resolved_tool_names`와 현재 entitlement/registry 결과의 교집합만 허용 |
| review queue | backend 준비 전에는 구현하지 않음 |

## Known Follow-Ups Before Graph Manager Execution

- Manager candidate graph generation/validation is now wired to both metadata and the first graph-aware execution adapter. `AIDOO_AI_RUNTIME_GRAPH_ENABLED=true` plus `AIDOO_AI_RUNTIME_GRAPH_EXECUTION_ENABLED=true` is required before supported accepted graphs use the adapter.
- Accepted graph validation is still not sufficient by itself. Execution requires the separate execution gate and adapter support; unsupported graphs keep fallback metadata.
- Candidate graph summary is intentionally allowlisted to high-level fields only: intent, domains, risk, output kind, invocation agent ids, verifier flag, and approval-preview flag.
- Graph schedule summary remains `state=planned`, agent ids, invocation sequence, and dependency ids. `execution_enabled=true` currently means `graph_node_runner_v0` or another execution adapter was selected; it does not yet mean a durable workflow backend owns the run.
- Candidate graph trace events materialize for approval shadow runs and persisted non-approval graph-eligible fallback streams. `persist=false` streams still expose the summary only in SSE metadata because they intentionally do not create conversation/runtime records.
- Graph execution adapter trace events materialize for persisted adapter streams as `graph_execution_shadow`; `graph_node_runner_v0` records per-node status events, but raw node output remains ephemeral and is summarized only in terminal metadata.
- Long-running graph trace scheduler를 붙이기 전에 runtime retention helper를 실제 운영 job/admin trigger로 연결한다.
- Runtime metric은 counter skeleton만 있다. Operator-facing rollout 전 dashboard/alert threshold를 별도 정의한다.
- Phase 0-A에서 기존 table에 추가하는 `ai_tool_approvals` partial index는 의도된 tooling index 1건으로 기록한다. 이후 hot-table index 변경은 별도 concurrent migration으로 분리한다.
- 새 runtime status를 추가할 때 migration SQL, ORM partial index, runtime status constant의 live-status literal drift를 함께 점검한다.

## E2E Smoke Log

### 2026-04-29 Phase 0-R Graph Runtime Smoke

- Reused existing web dev server on `127.0.0.1:4200`.
- The previous `uvicorn --reload` process on `127.0.0.1:8000` was stale and did not respond; it was terminated and API was restarted with `DOOWON_API_AUTO_MIGRATE=1 pnpm nx dev api`.
- Local Postgres schema was empty, so startup applied Alembic migrations through `e7f8a9b0c1d2` and seeded the baseline records.
- Created the initial local admin with `POST /api/v1/auth/setup` as `admin@aidoo.local`; subsequent bootstrap status exposed the seeded dev-login accounts.
- API smoke:
  - `GET /api/v1/auth/bootstrap-status` returned 200 through both API direct and web proxy.
  - Authenticated `GET /api/v1/auth/me` returned 200 for `admin@aidoo.local`.
  - Authenticated `GET /api/v1/ai/health` returned 200 with `ready=false` because the local MLX server was not running and external OpenRouter credentials are not configured.
- Browser smoke with `agent-browser --session phase6-smoke`:
  - Opened `http://127.0.0.1:4200/`, quick-login as `Aidoo HQ Admin` succeeded, final URL `/w/hq/home`.
  - Navigated to `/w/hq/ai`; AI workspace shell and composer rendered.
  - Final URL: `http://127.0.0.1:4200/w/hq/ai`.
  - Accessibility snapshot exposed workspace navigation, AI side menu, routing status button, app context selector, routing selector, and disabled send button before text entry.
  - Console contained only Vite debug lines and the React DevTools info message; `agent-browser errors` returned no page errors.

### 2026-04-29 Phase 0-R MLX Local LLM Smoke

- Started MLX with `bash scripts/mlx-serve.sh`; server is listening on `127.0.0.1:8080` with `mlx-community/Qwen3.6-35B-A3B-4bit`.
- Fixed the local API dev command so `pnpm nx dev api` runs with `DOOWON_API_AUTO_MIGRATE=1`; this prevents reload/startup from calling seed data against an unmigrated empty DB and failing on missing `org_units`.
- `GET http://127.0.0.1:8080/v1/models` returned 200 and listed the configured MLX model.
- Authenticated `GET /api/v1/ai/health` returned 200 with `local.ready=true` and external pool still `not_configured`.
- Direct MLX chat completion with `max_tokens=512` returned assistant content `MLX smoke OK`. Lower `max_tokens` values can finish inside Qwen reasoning output before content is emitted.
- API sync chat through `/api/v1/workspaces/hq/ai/chat` with `backend_mode=local`, `max_tokens=512`, and `Say exactly: MLX smoke OK` returned 200:
  - `provider=mlx-lm`
  - `chosen_pool=local`
  - `policy=local_only`
  - `finish_reason=stop`
  - content `MLX smoke OK`
- Browser smoke with `agent-browser --session phase6-mlx-check`:
  - Quick-login as `Aidoo HQ Admin` succeeded and `/w/hq/ai` rendered.
  - The AI conversation list showed `Say exactly: MLX smoke OK`.
  - Opening the conversation rendered the persisted user turn, assistant content `MLX smoke OK`, and routing metadata `local 풀 · local_only · policy_local_only`.
  - Console contained only Vite debug lines and the React DevTools info message; `agent-browser errors` returned no page errors.

### 2026-04-28 Phase 0-A Hardening Smoke

- Reused local web/API servers on `127.0.0.1:4200` and `127.0.0.1:8000`.
- Started the local MLX server with `bash scripts/mlx-serve.sh` on `127.0.0.1:8080`; the reusable local session is `tmux attach -t doowon-mlx`.
- `agent-browser --session doowon-e2e` login through the form as `delivery-hub-admin@aidoo.local` succeeded; seed quick-login card click did not trigger login in automation.
- `/w/delivery-hub/home` and `/w/delivery-hub/ai` rendered without browser page errors or console errors.
- Authenticated AI health returned `ready=true` for the local `mlx-lm` pool after the MLX server was started.
- AI composer enabled send after text entry, created a conversation, streamed a local model response, and saved user plus assistant turns.
- The rendered UI contained the assistant response and local routing metadata: `local` pool, `local_only`, `policy_local_only`.

## Rollback Plan

- `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false`가 기본값이므로 graph behavior는 활성화되지 않는다.
- runtime shadow-write에 문제가 있으면 `AIDOO_AI_RUNTIME_SHADOW_WRITE_ENABLED=false`로 shadow-write helper를 비활성화하고 기존 `AgentRunSnapshot` read/write path를 유지한다.
- inspection endpoint에 문제가 있으면 route registration만 끄고 persistence는 유지한다.
- migration rollback은 새 runtime table을 제거하되 기존 `AgentRunSnapshot`과 `AiToolApproval` table은 변경하지 않는 방향으로 작성한다.
- resume scope guard에서 false reject가 발생하면 기존 approval tests와 audit trace로 원인을 확인하고, widen 허용 없이 scope comparison 로직만 수정한다.

## Assumptions

- `compose.dev.yml`의 현재 local modification은 unrelated이며 이 플랜 구현에서 건드리지 않는다.
- Phase 0-A는 code foundation이며 사용자-facing graph behavior를 켜지 않는다.
- `review_queue_required`는 이후 Phase 7/admin policy 또는 durable workflow backend가 생긴 뒤 활성화한다.
- External LLM/search DTO와 provider adapter는 Phase B/C 이후 별도 구현 플랜에서 다룬다.
- 구현 완료 후 commit/push는 사용자가 별도로 요청할 때만 수행한다.
