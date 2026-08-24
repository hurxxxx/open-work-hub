# ADR 0005: Registered LLM Workload and Common Execution Interface

- Status: Accepted
- Date: 2026-07-10

## Context

Open Work Hub의 생성형 LLM 호출은 도메인 gateway, provider SDK, worker, agent runtime에
퍼져 있었다. 이 구조에서는 관리자가 호출 목록을 알기 위해 매번 코드를
재조사해야 하고, 새 앱이 provider/model, 보안, 예산, audit 계약을 부분적으로만
적용할 수 있다.

기존 `AiCapabilityRegistry`와 도메인별 `register_ai_capabilities(registry)` 훅은 AI 기능의
명시적인 발견 경계를 이미 제공한다. 새로운 자동 스캔 레지스트리나 호출부 DB
목록을 다시 만드는 것보다 이 확장점을 생성형 LLM workload의 정본으로 삼는
구조가 필요하다.

## Decision

### 1. `RegisteredLlmWorkload` is the canonical discovery contract

- 새 앱과 기존 기능의 모든 생성형 LLM 호출은 `AiCapabilityRegistry` 안의
  `RegisteredLlmWorkload`로 명시적으로 등록한다.
- 도메인은 `register_ai_capabilities(registry)`에서 `register_llm_workload(...)`를
  호출한다. 파일 스캔, app-local registry, 독립 plugin loader를 추가하지 않는다.
- `workload_id`는 `mail.summarize`, `meeting.summary`처럼 namespaced되고 배포 후에도
  유지되는 서버 상수다. 사용자 입력으로 선택하지 않는다.
- workload는 앱 이름이나 범용 처리 종류가 아니라 관리자가 route, model, output
  budget을 독립 변경해야 하는 실제 실행 기능 단위다. 한 앱의 여러
  LLM 단계는 별도 workload로 등록하고, 여러 앱이 같은 workload를 공유하는 것은
  실행·모델·예산 의미가 완전히 같은 기능일 때만 허용한다.
- legacy `task_kind`는 예산·audit 호환을 위해 유지할 수 있지만 신규 관리·발견의
  정본 key는 `workload_id`다.

### 2. Execution uses one common Interface

- 도메인 service와 worker는 `execute_llm(...)` 또는 `stream_llm(...)`만 호출한다.
- 호출자는 서버가 확정한 `workload_id`, `app_id`, actor/workspace context와
  input/messages만 제공한다. provider, model, pool, endpoint, credential은 선택하지 않는다.
- 공통 실행 Module은 registry descriptor와 관리자 override로 route/provider/model/output
  budget을 한 번만 결정한다. 선택 route가 external일 때만 AI security가 payload를
  allow/mask/block/audit하고 그 판정으로 다른 route를 선택하지 않는다.
- 보안이 외부 전송을 block하면 호출은 실패한다. local로 자동 전환하거나 보안 규칙이
  local route를 external로 승격하지 않는다.
- 미등록 workload, 준비되지 않은 route, 부적합 Adapter/model은 fail-closed다.
  provider 오류를 이유로 local/external 간 자동 fallback하지 않는다.

### 3. Provider implementations are Adapters

- 등록된 local/external LLM Provider Module 구현은 공통 실행 Interface 뒤의
  승인된 Adapter로 격리한다. 지원 provider 목록을 관리자 API나 DB CHECK에 다시
  하드코딩하지 않는다.
- 기존 외부 LLM의 provider-native tool, stream, trace, result 동작은 삭제하지 않고
  해당 Adapter 내부에 보존한다. 마이그레이션은 실행 소유권을 Adapter 뒤로
  옮기는 것이지 외부 기능을 제거하는 것이 아니다.
- 앱, router, domain service, app worker에서 provider SDK·HTTP, `core.llm`, 저수준
  gateway를 직접 호출하지 않는다.
- 신규 실행 종류나 Adapter가 필요하면 기능 코드에서 우회하지 말고 Core
  Enablement로 먼저 추가한다.
- `execution_kind='agent'` workload는 one-shot `LlmExecutionAdapter`와 별도의
  `AgentRuntimeAdapter`를 등록한다. 관리자는 workload가 허용한 runtime adapter 중 하나를
  route/provider/model과 함께 선택한다. agent runtime도 gateway 보안·audit·credential 경계를
  거치며 provider SDK나 secret을 앱 코드에서 직접 선택하지 않는다.
- embedding, rerank, OCR, ASR은 이 ADR의 생성형 LLM workload 범위가 아니며
  각 Inference Gateway 계약을 따른다.

### 4. Admin settings project the registry

- 관리자 API/UI는 workload 목록을 하드코딩하지 않고 registry snapshot과 DB route
  override를 합성한다.
- 새 workload는 별도 DB seed 없이 등록 즉시 기본 route로 노출된다.
- DB는 provider/model 설정과 registry 기본값과 다른 workload override만 소유한다.
  제거된 workload의 override는 실행하지 않고 orphan으로 관리한다.
- 관리자는 workload별로 local/external route와 승인 모델을 선택한다. 일반
  workload의 registry 기본값은 local이다.
- 관리자는 workload별 local/external 최대 출력 토큰을 함께 관리한다. 플랫폼
  기본값은 local 32K, external 64K이며 호출부가 더 작은 출력을 요청하면 그 값을
  사용한다. 앱 코드는 관리자 상한을 넘길 수 없다.
- workload route override가 local/external 선택의 유일한 관리자 정본이다.
  `task_kind -> local_only/external` 같은 별도 정책 저장소를 추가하지 않는다.
- 관리자 화면의 책임은 다음 제어면으로 분리한다.
  - **LLM Providers**: provider 활성화, 기본/override endpoint, API key, 기본 모델과 서버측 모델 discovery
  - **Model Catalog**: discovery inventory 중 서비스 사용 모델과 capability 승인
  - **LLM Routing**: 앱/실제 기능 workload별 local/external, provider/model, 출력 상한
  - **AI Security**: 이미 external로 선택된 payload의 allow/mask/block/audit와 예외
- 관리자 정보 구조에서는 LLM Providers, 모델 catalog, LLM Routing을 `LLM 관리`
  section에 두고 AI Security에는 외부 전송 보안 기능만 둔다. 감사 이벤트 탐색기는
  전역 `감사 로그`를 단일 Interface로 사용하며 AI Security는 필터된 deep link로 연결한다.
- 일반 OCR, embedding, rerank, vector/keyword index는 LLM Routing에 노출하지 않는다.
  Vision LLM을 쓰는 문서 추출 workload는 registry·공통 실행·audit 계약은 유지하되
  `management_surface='document_processing'`으로 분류한다. 관리자는 별도 `문서 처리 현황`
  section에서 현재 환경변수, API runtime health, workload readiness를 읽기 전용으로 확인한다.
  이 projection은 별도 DB 설정이나 두 번째 route source를 만들지 않으며 Worker health를
  API process readiness로 가장하지 않는다.
- API key 원문은 응답이나 화면에 반환하지 않는다. 빈 key 입력은 기존 secret을
  유지하고, 명시적인 교체 또는 제거 동작에서만 변경한다.
- discovery로 새로 확인한 모델은 자동 승인하거나 route에 노출하지 않는다. 관리자가
  catalog에서 승인한 모델만 route 선택 대상이며, discovery 실패나 inventory 누락은
  기존 승인과 route를 자동 변경하지 않는다.

### 5. AI security protects external transfer without routing

- AI security는 선택 route가 external일 때만 외부로 나갈 payload를 검사한다.
- 보안 효과는 inherit, block_external, mask_and_send, audit_only로 제한한다.
- soft blocker를 허용하려면 사유와 만료일이 있는 외부 전송 예외를 사용한다.
- hard blocker는 예외로 우회할 수 없다.
- local route는 외부 전송 검사를 받지 않지만 workload 등록, 모델 준비 상태, 토큰
  상한, audit/usage 계약은 동일하게 적용한다.

### 6. Web search workload is external-only

- Web Search는 안정적인 workload로 등록하고 기존 Anthropic native `web_search` tool
  구현을 승인된 external Adapter로 사용한다.
- 이 workload는 local route를 제공하지 않으며 관리자는 승인된 외부 provider/model만
  선택한다. 외부 검색 실패 시 local route로 자동 fallback하지 않는다.

### 7. Future additions are enforced by code contracts

새 LLM workload는 다음을 하나의 변경으로 제공한다.

1. 안정적인 namespaced `workload_id`와 domain registration
2. local/external 양쪽 최대 출력 토큰 예산(기본 local 32K/external 64K)
3. 공통 execution Interface 호출
4. audit/tracing과 외부 데이터 전송 정책
5. registry bootstrap·duplicate·Adapter/default-route 검증
6. provider/core LLM direct-call guard 테스트

Registry bootstrap과 계약 테스트가 이 체크리스트를 검증한다. 예외는 호출부에
추가하지 않고 공통 실행 정책에서 명시적으로 검토한다.

## Consequences

### Positive

- 관리자 설정이 실제 호출 발견 계약과 자동으로 맞춰진다.
- 새 앱이 기존 보안, 예산, audit, provider/model 정책을 기본으로 상속한다.
- Provider 변경과 정책 해석이 호출부에 퍼지지 않는다.

### Negative

- 간단한 LLM 호출도 descriptor, 양쪽 예산, 검증을 함께 추가해야 한다.
- 기존 direct provider 호출은 provider-native 구현을 보존한 채 Adapter와 공통
  Interface 뒤로 실행 소유권을 옮기는 마이그레이션이 필요하다.

## Follow-up

- Legacy `register_llm_task(...)`는 호환 workload를 materialize하되 신규 코드는
  `register_llm_workload(...)`를 사용한다.
- 기존 Web Search 외부 구현을 workload Adapter 안에 보존한 뒤
  direct-call guard를 필수 CI로 고정한다.
- Provider-native Adapter도 provider/model/output cap을 환경 변수에서 다시 고르지
  않고 등록 workload의 resolved route를 사용한다.
- AI Gateway 소유 문서와 관리자 설정 계약은 registry 스키마가 변경될 때 함께
  갱신한다.
