# ADR 0002: MCP-First AI Capability Platform Contracts

- Status: Accepted
- Date: 2026-04-20

## Context

Open ALM AI capability registry는 단순 `OpenAI function` 목록에서 **MCP-first capability platform** 으로 전환됐다. 현재 구현은 다음 구조를 전제로 한다.

- 내부 정본 계약은 `AiCapabilityDescriptor`
- AI-facing 1차 산출물은 MCP manifest
- OpenAI function schema와 derived OpenAPI는 MCP/descriptor에서 파생
- discovery는 capability가 속한 앱의 availability scope에 맞춰 platform 또는 workspace
  entitlement로 필터링
- execution은 tool invoke 시점에 discoverability와 도메인 ACL을 다시 검증

이 계약을 코드에만 남겨두면 다음 문제가 다시 생긴다.

- 새 앱이 ad-hoc tool registration이나 router 특례로 추가된다.
- AI tool input이 인간용 REST DTO와 섞여 UI 전용 필드가 새어 들어간다.
- discovery와 execution의 보안 경계가 분리되지 않는다.
- 새 capability 추가 시 어떤 테스트와 문서가 같이 바뀌어야 하는지 일관성이 깨진다.

## Decision

### 1. Canonical contract는 `AiCapabilityDescriptor` 로 고정한다

- `domains/ai/registry.py` 의 `AiCapabilityDescriptor` 가 내부 capability 정본이다.
- MCP manifest는 descriptor에서 컴파일되는 AI-facing 아티팩트다.
- OpenAI strict function schema와 derived OpenAPI export는 파생물이다.
- legacy `openai_tool_specs()` 경로는 호환성 레이어로만 유지한다. 새 capability 규칙의 정본으로 사용하지 않는다.

### 2. Capability 등록 경로는 도메인 소유 + registry 경로로 제한한다

- 각 도메인은 `register_ai_capabilities(registry)` 훅으로 capability를 등록한다.
- 새 tool은 `AiCapabilityRegistry.register_tool(...)` 로만 추가한다.
- router 또는 agent에서 ad-hoc tool name/spec를 하드코딩하지 않는다.
- `domains/ai/*` 는 공통 runtime / compilation / transport만 소유한다.

### 3. Capability authoring 규칙을 고정한다

- tool input은 **AI 전용 Pydantic DTO** 로 정의한다.
- 인간용 REST request model을 그대로 재사용하지 않는다.
- tool handler는 router 코드를 재사용하지 않고 **application service** 를 호출한다.
- read capability는 `mode="read"` 를 기본으로 한다.
- write capability는 `approval_required=True` 를 기본으로 하며, 이 경우 반드시 `preview_builder_id` 를 함께 등록한다.
- 모든 capability는 `discoverability_predicate_id` 를 가져야 한다.
- 중복 tool/predicate/preview/service handler 등록은 `ValueError` 로 즉시 실패해야 한다.

### 4. Discovery와 execution은 별도 게이트를 가진다

- `AiMcpClient.list_tools()` 는 principal과 app availability scope에 맞는 entitlement 및
  discoverability predicate로 tool 목록을 필터링한다.
- `tool_service.execute_tool()` 는 실제 invoke 시점에 같은 discoverability predicate를 다시 평가한다.
- discovery에서 숨겨진 tool은 execution에서도 차단되어야 한다.
- execution 단계의 최종 권한 판정은 기존 domain ACL helper/service가 담당한다.

즉, 보안 모델은 다음 순서를 따른다.

1. `tools/list` 에서 hide
2. `execute_tool` 에서 discoverability 재검증
3. 도메인 service/ACL 에서 최종 `403/404`

### 5. Schema 규칙을 고정한다

- MCP canonical schema는 JSON Schema 2020-12 subset으로 정규화한다.
- 허용:
  - local `$ref` inline
  - object / array / enum / scalar
  - nullable union
- 금지:
  - `allOf`
  - `not`
  - `patternProperties`
  - conditional keywords
  - external `$ref`
  - non-nullable complex union
- OpenAI bridge는 strict schema를 파생 생성한다.
- legacy `openai_tool_specs()` 는 기존 shape 호환을 유지한다.

### 6. Builtin discoverability source를 고정한다

- coarse app-level predicate는 `domains/auth/workspace_apps.py` 의 컴파일된 app catalog를
  기준으로 생성한다.
- `availability_scope="workspace"` 앱은 현재 workspace entitlement를 사용한다.
- `availability_scope="platform"` 앱은 선택된 workspace와 무관하게 platform visibility를
  사용하며, personal principal(`workspace_id=None`)에서도 같은 hard gate를 적용한다.
- app 목록을 AI registry 내부에 별도 하드코딩하지 않는다.
- fine-grained write predicate는 해당 write capability가 실제로 도입되는 시점에 추가한다.

### 7. Write capability rollout 경계를 고정한다

- Read capability parity, MCP bridge, inspection/export는 현재 계약에 포함한다.
- Write DTO, preview builder, handler 코드는 둘 수 있지만 discovery 노출은 분리한다.
- executable write tool은 `OPEN_ALM_AI_WRITE_TOOLS_ENABLED=true` 일 때에만 discovery 대상이 된다.
- write capability는 코드 존재와 discovery 노출을 분리해서 rollout 한다.

### 8. 필수 테스트를 고정한다

새 capability 추가 또는 플랫폼 규칙 변경 PR은 최소한 다음 중 관련 항목을 함께 갱신해야 한다.

- registry compile test
- duplicate registration guard test
- legacy schema compatibility test
- MCP manifest / derived OpenAPI filtering test
- direct tool invoke test
- hidden tool blocked test
- chat stream 또는 agent loop regression test

capability contract를 바꾸는 PR은 **문서 + 테스트 + 코드** 를 같은 PR에서 함께 갱신한다.

## Consequences

### Positive

- 새 앱을 붙일 때 capability 등록 방식이 흔들리지 않는다.
- AI tool input과 인간용 REST input의 책임이 분리된다.
- MCP manifest, execution runtime, approval flow를 같은 계약 위에서 확장할 수 있다.
- discoverability 누락이나 등록 충돌을 더 빨리 잡을 수 있다.

### Negative

- 단순 read tool도 registry/DTO/predicate/service 규칙을 따라야 하므로 초기 작성 비용이 조금 늘어난다.
- capability 계약 변경 시 문서와 테스트를 함께 고쳐야 해서 PR 면적이 넓어진다.

## Non-Goals

- 이 ADR은 remote MCP transport의 wire-level OAuth 구현 자체를 다루지 않는다.
- `resources/*`, `prompts/*` 실행 활성화 시점은 별도 결정으로 남긴다.
- approval persistence 세부 상태머신은 runtime approval service와 해당 테스트가 정본이다.

## Follow-up

- 새 앱 추가 시 이 ADR의 규칙을 먼저 확인하고 capability를 추가한다.
- capability platform 구현 상태가 바뀌면 관련 current/domain 문서와 하네스 검증 기준을 이 ADR과 같이 정합성 있게 갱신한다.
- write capability를 실제로 활성화할 때 fine-grained discoverability predicate와 approval persistence 기준을 함께 확정한다.
- write capability 추가 시 `OPEN_ALM_AI_WRITE_TOOLS_ENABLED` off/on 양쪽 discovery test를 함께 유지한다.
