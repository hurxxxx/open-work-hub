# Phase 1 — Foundation (LLM Request Context + Pool Routing)

## Context

### 왜 지금 하는가
- 현재 LLM 계층은 `primary(local) -> fallback(external)` 자동 폴백 구조다.
- 이 구조는 로컬 풀이 죽었을 때 민감한 업무 텍스트가 외부로 조용히 넘어갈 수 있어 보안 정책과 충돌한다.
- 이후 Phase 2~5는 모두 "누가, 어느 워크스페이스에서, 어떤 정책으로" LLM을 호출했는지 공통 컨텍스트가 필요하다. 지금 이 foundation이 없으면 이후 Phase에서 actor/workspace/system-job 정체성을 다시 설계하게 된다.

### 현재 코드 기준 사실
- `/api/v1/ai/*`는 완전 무방비가 아니다. `app.include_router(ai_router, ...)` 단계에서 이미 `require_current_user` + workspace membership dependency 뒤에 mount되어 있다.
- 반면 LLM 호출 자체는 여전히 `core/llm.py`의 `primary/fallback` 개념에 묶여 있고, `apps/api/src/aidoo_api/domains/ai/router.py`와 `apps/worker/src/aidoo_worker/tasks/meeting.py`가 low-level client를 직접 호출한다.
- 워커 요약 태스크는 `primary.ready`면 로컬, 아니면 fallback으로 넘어간다. 이 부분이 현재 가장 명시적인 크로스풀 폴백이다.

### 목표
- `LlmTaskContext`를 도입해 모든 LLM 요청에 `source`, `actor_user_id`, `workspace_id`, `task_kind`를 강제한다.
- 로컬/외부 풀을 완전히 독립시키고, `task_kind` 기반 정책으로만 풀을 선택한다.
- PII hit 시 외부 정책이라도 로컬로 강제한다.
- 모든 LLM 호출을 audit log에 남긴다.
- `/readyz`는 시스템 readiness로 유지하고, `/api/v1/ai/health`를 제품/API health endpoint로 추가한다.

### 범위
- API `ai` 도메인
- 워커의 meeting summarize 호출
- 설정/환경변수/헬스체크
- 정책 테이블 + seed + audit

### 비범위
- 스트리밍
- tool calling
- 관리자 UI
- RAG
- ASR provider 교체

### 예상 작업 기간
- 구현 + 테스트 + 문서 반영까지 `1.5~2.5일`

## Architecture/Principles

### 핵심 원칙
1. 풀 선택은 fallback이 아니라 policy resolution 결과여야 한다.
2. LLM 호출은 모두 `LlmTaskContext`를 받아야 한다.
3. low-level `get_llm_client(pool)`는 내부 구현 세부사항이고, 호출부는 정책/audit wrapper를 통해서만 접근한다.
4. policy row가 없으면 fail-open이 아니라 `local_only`로 본다.
5. raw request 텍스트는 audit payload에 저장하지 않는다. PII hit 여부/패턴 종류/토큰 수 같은 요약만 남긴다.

### 새 개념

#### `LlmPoolName`
- `"local" | "external"`

#### `LlmPolicyMode`
- `"local_only" | "external"`

#### `LlmTaskContext`
- `source: str`
- `actor_user_id: str | None`
- `workspace_id: str`
- `task_kind: str`

`LlmTaskContext`는 **호출 정체성(identity)** 만 가진다. policy는 여기 넣지 않고 routing 결과인 `PolicyDecision`이 가진다.

#### `source` vs `task_kind`
- `source`는 호출 경로 식별자다. 예: `api.chat`, `worker.meeting.summarize`
- `task_kind`는 정책 조회 키인 업무 종류다. 예: `chatbot`, `meeting_summary`, `batch_generation`
- 같은 업무라도 호출 경로가 다를 수 있다.
  - 예: `source=api.chat`, `task_kind=chatbot`
  - 예: `source=api.stream`, `task_kind=chatbot`

#### `PolicyDecision`
- `policy: LlmPolicyMode`
- `chosen_pool: LlmPoolName`
- `pii_hits: list[str]`
- `forced_local: bool`
- `reason: str`

### 설정 구조

현재:
- `DOOWON_LLM_*`
- `DOOWON_LLM_FALLBACK_*`

P1 목표:
- `DOOWON_LLM_LOCAL_*`
- `DOOWON_LLM_EXTERNAL_*`

호환성:
- 기존 `DOOWON_LLM_*` / `DOOWON_LLM_FALLBACK_*`는 **deprecated alias**로 유지하되, **제거 시점은 Phase 3 kickoff** 로 고정한다.
- `.env.example`와 `apps/api/README.md`는 새 이름 기준으로 업데이트한다.
- `long_generation_timeout`은 **pool별 분리**로 확정한다.
  - `DOOWON_LLM_LOCAL_LONG_GENERATION_TIMEOUT_SECONDS`
  - `DOOWON_LLM_EXTERNAL_LONG_GENERATION_TIMEOUT_SECONDS`
- 일반 `request_timeout`은 공통 필드로 유지한다. health check / models.list / 짧은 control-plane 호출은 같은 예산을 쓴다.

### 헬스체크 계약

#### `/readyz`
- 인증 없음
- 시스템 readiness endpoint 유지
- local/external 풀 상태를 둘 다 노출
- `llm_required=false`면 degraded를 readiness failure로 취급하지 않음

#### `/api/v1/ai/health`
- 기존 AI router 보호 체인 뒤에 mount
- 현재 사용자/workspace 기준 제품용 상태 확인 endpoint
- 웹 UI는 장기적으로 이 endpoint를 canonical로 사용

#### `/api/v1/ai/llm-health`
- P1에서는 backward-compatible alias로 유지
- 내부 구현은 `/ai/health`와 같은 서비스 함수를 사용

## 구현 단계

### 1. 설정/환경변수 재구조

수정 파일:
- `apps/api/src/aidoo_api/core/settings.py`
- `.env.example`
- `apps/api/README.md`
- 필요 시 `apps/worker/src/aidoo_worker/settings.py`

작업:
- local/external 풀 설정 필드를 분리한다.
- 예시:
  - `llm_local_provider`
  - `llm_local_base_url`
  - `llm_local_api_key`
  - `llm_local_default_model`
  - `llm_local_canonical_model`
  - `llm_external_provider`
  - `llm_external_base_url`
  - `llm_external_api_key`
  - `llm_external_default_model`
  - `llm_external_http_referer`
  - `llm_external_title`
- `long generation timeout`은 pool별로 분리한다.
  - `llm_local_long_generation_timeout_seconds`
  - `llm_external_long_generation_timeout_seconds`
- 일반 `request timeout`은 공통 필드 유지:
  - `llm_request_timeout_seconds`
- 기존 env 이름은 `AliasChoices(...)`로 한 Phase 호환 유지한다.

완료 기준:
- 새 env 이름만으로 앱이 기동한다.
- 기존 env 이름으로도 테스트 환경이 깨지지 않는다.

### 2. 정책 테이블 + seed + 서비스

수정 파일:
- `apps/api/src/aidoo_api/domains/ai/models.py` 신규
- `apps/api/src/aidoo_api/domains/ai/policy_service.py` 신규
- `apps/api/alembic/versions/<new_revision>_add_llm_policies.py`
- `apps/api/src/aidoo_api/domains/auth/access.py` 또는 동등한 seed entrypoint

스키마 초안:
- `id`
- `task_kind` unique
- `policy_mode` (`local_only` | `external`)
- `description`
- `created_at`
- `updated_at`

초기 seed:
- `chatbot -> local_only`
- `meeting_summary -> local_only`
- `batch_generation -> local_only`

정책 해석 규칙:
- row가 없으면 `local_only`
- workspace/role override는 P1 범위 밖
- **health check는 policy lookup 대상이 아니다.** `models.list()` 기반 pool health는 local/external 각각 직접 체크한다.

seed 주입 방식:
- **Alembic은 스키마만 담당**한다. data migration으로 정책 row를 넣지 않는다.
- 초기 정책 row는 기존 repo 패턴에 맞춰 `ensure_seed_data()` 경로에서 `ensure_llm_policy_seed_data()` 같은 helper로 **idempotent insert-if-missing** 처리한다.
- 관리자가 수정한 policy row는 seed가 덮어쓰지 않는다.

완료 기준:
- Alembic upgrade/downgrade 통과
- `resolve_policy(task_kind)`가 deterministic하게 동작

### 3. `core/llm.py` 재작성

수정 파일:
- `apps/api/src/aidoo_api/core/llm.py`
- `apps/api/src/aidoo_api/core/pii.py` 신규

목표 구조:
- `LlmTaskContext`
- `PolicyDecision`
- `LlmPoolConfig`
- `LlmPoolHealth`
- `get_llm_pool_config(pool)`
- `get_llm_client(pool)`
- `check_llm_pool_health(pool)`
- `check_llm_pools_health()`
- `resolve_policy(...)`
- `choose_pool(context, text_inputs, db)`
- `complete_chat(context, db, *, messages, temperature, max_tokens, reasoning_effort, timeout_seconds: float | None = None, ...)`

행동 규칙:
1. caller가 `LlmTaskContext` 없이 `complete_chat(...)`를 호출할 수 없어야 한다.
2. `choose_pool(...)`는 policy + PII만 보고 local/external 중 하나만 반환한다.
3. local 실패 시 external 재시도는 없다.
4. external 정책에서 PII hit 시 local로 강제하고 `forced_local=True`를 기록한다.
5. health는 local/external 각각 독립적으로 계산한다.
6. `complete_chat(...)`는 기본적으로 **선택된 pool의 long_generation_timeout**을 사용하고, `timeout_seconds`는 예외적인 호출부만 override할 수 있게 한다.

PII 범위:
- 정규식 기반 최소셋
- 주민등록번호 패턴
- 이메일
- 휴대전화/전화번호
- 카드번호처럼 오탐이 큰 패턴은 P1에 넣을지 구현 전 최종 확정

완료 기준:
- core 레벨에서 더 이상 `primary/fallback` 개념을 public API로 쓰지 않는다.
- 호출부는 모두 pool name이 아니라 `LlmTaskContext`를 넘긴다.

### 4. AI router 전환

수정 파일:
- `apps/api/src/aidoo_api/domains/ai/router.py`
- 필요 시 `apps/api/src/aidoo_api/domains/ai/schemas.py` 신규

작업:
- 현재 chat route가 직접 health 체크와 fallback을 수행하는 로직 제거
- 현재 `ai/router.py`의 direct completion 호출에 남아 있는 route-local long timeout 지정도 제거하고, **pool별 long_generation_timeout 선택을 `complete_chat(...)` wrapper로 일원화**한다.
- route 내부 또는 전용 builder helper에서:
  - `current_user`는 app-level dependency 체인으로 이미 보장된 상태를 전제로 사용
  - `workspace_id`는 **추가 route-level `Depends(require_current_workspace)`를 강제하지 않고**, app-level dependency가 바인딩한 `request.state.current_workspace` 또는 `get_current_workspace(db)`에서 읽어 `LlmTaskContext(source="api.chat", actor_user_id=current_user.id, workspace_id=<bound workspace id>, task_kind="chatbot")` 생성
  - `complete_chat(...)` 호출
- `/ai/health` 추가
- `/ai/llm-health`는 alias로 유지하되 동일 health 서비스 사용
- app-level dependency 체인은 그대로 유지하고, 이 사실을 테스트로 고정

중요:
- `app.py`의 AI router mount dependency를 약하게 바꾸지 않는다.
- route 함수에 `require_current_user` / `require_current_workspace`를 중복 주입할지 여부는 구현 시 결정하되, app-level dependency를 canonical source로 유지한다.

완료 기준:
- `/api/v1/ai/chat`는 정책 기반 한 번만 시도한다.
- `/api/v1/ai/health`와 `/api/v1/ai/llm-health` 응답 shape가 일관된다.

### 5. 워커 meeting summarize 전환

수정 파일:
- `apps/worker/src/aidoo_worker/tasks/meeting.py`

작업:
- 현재 `primary.ready ? local : fallback` 로직 삭제
- recording에서 `meeting.workspace_id`를 읽어 `LlmTaskContext(source="worker.meeting.summarize", actor_user_id=None, workspace_id=recording.meeting.workspace_id, task_kind="meeting_summary")` 생성
- 같은 `complete_chat(...)` wrapper를 사용
- local_only 정책에서 local pool이 unavailable이면 retry/fail 처리만 하고 external로 보내지 않는다

완료 기준:
- meeting summarize는 policy 위반 없는 호출만 한다.
- worker audit에도 `source=worker.meeting.summarize`, `actor_user_id=null`, `workspace_id=<meeting.workspace_id>`가 남는다.

### 6. Audit 통합

수정 파일:
- `apps/api/src/aidoo_api/domains/ai/audit.py` 신규 또는 `core/llm.py` 내부 helper
- 필요 시 `apps/api/src/aidoo_api/domains/auth/access.py` 호출부 래퍼

기록 규칙:
- action: `llm_call`
- entity_kind: `llm_task`
- entity_id: 없음 또는 request/job id
- payload:
  - `source`
  - `actor_user_id`
  - `workspace_id`
  - `task_kind`
  - `policy`
  - `chosen_pool`
  - `forced_local`
  - `pii_hits`
  - `model`
  - `status`
  - `latency_ms`
  - `usage`

주의:
- 원문 prompt/content는 저장하지 않는다.

### 7. Health/readiness 정리

수정 파일:
- `apps/api/src/aidoo_api/app.py`
- `apps/api/src/aidoo_api/domains/ai/router.py`
- `apps/api/tests/test_health.py`

작업:
- startup readiness와 `/readyz`가 새 health API를 사용하도록 정리
- 응답은 `local`/`external` 각각의 status를 포함
- `/readyz`는 system endpoint로 유지
- `/api/v1/ai/health`는 protected endpoint로 추가
- **shape 영향 점검**:
  - `app.state.llm_health`는 현재 `app.py`에서만 write되고 별도 reader는 없는 상태를 먼저 grep으로 확인한다.
  - 반면 웹 UI는 `/api/v1/ai/llm-health` 응답의 `primary/fallback/active_backend` shape를 소비하므로, endpoint 응답은 P1에서 바로 깨지지 않게 alias/adapter를 둔다.
  - 즉, in-process state shape 변경은 자유도가 높지만 wire response shape 변경은 별도 마이그레이션 전략이 필요하다.

### 8. 문서/샘플/후속 준비

수정 파일:
- `.env.example`
- `apps/api/README.md`
- 필요 시 `plans/00-ai-platform-roadmap.md`의 결정 완료 표 보정

작업:
- 새 env 이름 문서화
- `task_kind` seed와 기본 정책 설명
- `/ai/health` vs `/readyz` 용도 구분 문서화

## Verification

### 단위 테스트

대상 파일:
- `apps/api/tests/test_llm.py` **재작성**
- `apps/api/tests/test_health.py`
- `apps/api/tests/test_meeting_recordings.py`
- 필요 시 `apps/api/tests/test_ai_routes.py` 신규

주의:
- 기존 `test_llm.py`의 primary/fallback 중심 7개 케이스는 새 local/external + policy API와 모델이 충돌하므로, **부분 수정이 아니라 전면 재작성**을 전제로 한다.
- 기존 fallback 강제/자동 전환 가정 테스트는 폐기하고, policy resolution / pool selection / no-cross-pool fallback 테스트로 교체한다.

시나리오:
1. settings가 새 local/external env 이름을 읽는다.
2. deprecated env alias도 한 Phase 동안 읽힌다.
3. policy row가 없으면 `local_only`로 해석된다.
4. `external` 정책 + PII 없음 => external pool 선택
5. `external` 정책 + PII hit => local pool 강제
6. `local_only` 정책 + local 실패 => external 재시도 없음
7. `/readyz`는 unauthenticated로 접근 가능
8. `/api/v1/ai/health`와 `/api/v1/ai/chat`는 unauthenticated 401
9. legacy `/api/v1/ai/*` 경로에서는 "접근 가능한 workspace가 하나도 없는 사용자"가 403
10. slug 경로 `/api/v1/workspaces/{slug}/ai/*`에서는 해당 workspace membership이 없으면 403
11. worker meeting summarize는 local unavailable 시 retry/fail하지만 external 호출은 하지 않음
12. audit payload에 `source/actor_user_id/workspace_id/task_kind/policy/chosen_pool`이 남는다

### 마이그레이션 검증
- `uv run pytest tests/test_alembic_migrations.py`
- `uv run alembic upgrade head`
- `uv run alembic downgrade -1`
- `uv run alembic upgrade head`

### 수동 검증
1. 로컬 pool 정상, policy=`local_only`에서 `/api/v1/ai/chat` 호출 → local 응답.
2. 로컬 pool 비정상, policy=`local_only`에서 `/api/v1/ai/chat` 호출 → 503, external 호출 흔적 없음.
3. policy=`external` 임시 row로 바꾸고 일반 텍스트 요청 → external 응답.
4. 같은 policy에서 주민등록번호 포함 텍스트 요청 → local 강제, audit에 `forced_local=true`.
5. meeting recording summarize 수동 실행 → local로만 요약 수행.
6. `/readyz`와 `/api/v1/ai/health` 응답이 각기 기대한 인증/상태 계약을 만족.
7. `/api/v1/ai/llm-health`가 기존 프론트 소비 필드(`primary`, `fallback`, `active_backend`)를 유지하는지 확인.

## 결정 로그

### 이번 Phase에서 확정
- `LlmTaskContext`는 모든 LLM 진입점의 공통 입력이다.
- `LlmTaskContext`는 identity만 담고, policy는 `PolicyDecision`이 가진다.
- `task_kind`는 업무 종류(`chatbot`, `meeting_summary`, `batch_generation`)이고, `source`와 분리한다.
- 기본 정책은 fail-open이 아니라 `local_only`다.
- health check는 policy 대상이 아니며 seed row를 두지 않는다.
- `/api/v1/ai/llm-health`는 P1에서 제거하지 않고 `/api/v1/ai/health`의 backward-compatible alias로 유지한다.
- 기존 AI route 보호는 app-level dependency 체인을 canonical로 본다.
- long generation timeout은 pool별 분리, request timeout은 공통 유지로 확정한다.
- 장기 호출 timeout은 `complete_chat(...)` wrapper가 **선택된 pool의 long_generation_timeout**을 기본값으로 사용하고, 호출부 `timeout_seconds` override는 예외 경로에만 허용한다.
- raw prompt/content는 audit에 저장하지 않는다.
- deprecated env alias 제거 시점은 **Phase 3 kickoff** 로 고정한다.
- LLM policy seed는 Alembic data migration이 아니라 기존 `ensure_seed_data()` 경로의 idempotent insert-if-missing 방식으로 넣는다.
- audit `usage`는 `{prompt_tokens, completion_tokens, total_tokens}` 고정 shape로 저장한다.

### 구현 중 열어둘 결정
- PII 정규식 최소셋 최종 확정
- `entity_id`는 nullable 유지하되, API는 request id(`X-Request-ID`), worker는 Celery task id를 우선 후보로 쓸지 구현 시 확정
- `/api/v1/ai/llm-health` 제거 시점 (P2 이후 검토)

## 롤백 계획

### 코드 롤백
- `core/llm.py`, `domains/ai/router.py`, `worker/tasks/meeting.py` 변경을 git revert한다.
- `/api/v1/ai/health` 추가만 제거하고 `/ai/llm-health` 기존 계약은 유지한다.

### DB 롤백
- Alembic down migration으로 `llm_policies` 테이블 제거
- 정책 테이블 제거 전에는 앱이 row 없음 => `local_only`로 동작하도록 구현해 migration order 의존성을 낮춘다

### 설정 롤백
- deprecated env alias를 유지하므로 `.env`를 즉시 되돌리지 않아도 앱 기동은 유지된다
- README/.env.example는 후행 정리 가능

### 운영 롤백 기준
- local pool 장애 시 chat/meeting summarize가 광범위하게 503을 내고 운영상 감당이 안 되는 경우
- audit volume이 과도해 DB 부하가 큰 경우
- policy resolve 오작동으로 정상적인 local_only 요청이 막히는 경우

### 롤백 후 상태
- 원복 시 다시 크로스풀 폴백 위험이 생긴다
- 따라서 운영 롤백은 임시 대응으로만 사용하고, 원인 수정 후 Phase 1을 재적용한다
