# ADR 0001: AI Platform Extensibility Contracts

- Status: Accepted
- Date: 2026-04-18

## Context

Open ALM은 앞으로 AppBar에 여러 업무 앱이 늘어나고, AI는 각 앱을 지원하는 agent로 동작해야 한다. 동시에 백엔드는 특정 프론트 구현에 종속되지 않고 OpenAPI 기반의 AI hub로 확장 가능해야 한다.

지금 이 계약을 먼저 고정하지 않으면 다음 문제가 반복된다.

- 새 앱 추가 때마다 AI core와 프론트 shell을 같이 수정해야 한다.
- AI task/policy/tool 메타데이터가 중앙 파일에 하드코딩된다.
- router, worker, AI tool, 외부 API가 서로 다른 권한 경계와 DB 로직을 갖게 된다.
- 나중에 service account/API key를 추가할 때 `User` 전용 가정이 시스템 전체에 퍼져 있어 재작업 비용이 커진다.

## Decision

### 1. Workspace bootstrap을 앱 셸 진실원으로 채택한다

- `GET /api/v1/auth/me`는 identity-only 계약을 유지한다.
- `GET /api/v1/workspaces/{workspace_slug}/bootstrap`를 workspace별 앱 활성화와 nav 메타데이터의 단일 진실원으로 사용한다.
- 서버는 관리자 DB의 앱 표시 메타데이터, workspace별 entitlement, 그리고 코드에 존재하는 구현 capability 상태를 조합해 반환한다.
- 앱 표시명, 아이콘, 앱바 노출, 앱바 카테고리, 메뉴 배치, workspace별 활성화 여부는 관리자 DB가 정본이다.
- 실제 화면 컴포넌트와 route element 매핑, backend route, AI task, 권한 gate 같은 구현 capability는 코드 registry가 유지한다.
- 관리자 DB에 앱 row가 존재해도 대응 구현 capability가 없으면 bootstrap은 해당 앱을 노출하지 않거나 disabled로 반환해야 한다.

이 결정으로 새 앱 추가 시 운영자는 관리자 메뉴에서 표시/노출/배치를 관리하고,
개발자는 프론트 route/component registry와 백엔드 구현 capability만 추가하면 된다.

### 2. AI capability는 도메인이 소유한다

- 각 도메인은 선택적으로 `register_ai_capabilities(registry)` 훅을 노출한다.
- registry는 `task_kind`, `tool definitions`, `approval-required operations` 메타데이터를 수집한다.
- LLM policy seed, readiness, policy lookup은 registry 기반으로 동작한다.
- `domains/ai/*`는 공통 실행 파이프라인과 계약만 소유하고, 개별 도메인 capability 정의는 소유하지 않는다.
- 등록 대상 도메인은 bootstrap 코드에서 명시적으로 관리한다. 자동 파일 스캔은 도입하지 않는다.

이 결정으로 신규 도메인 추가 시 AI core 수정 면적을 최소화한다.

### 3. Application service layer를 단일 백엔드 경계로 고정한다

- router와 AI tool은 동일 service 함수를 호출해야 한다.
- 서비스 경계는 `workspace + principal + input`을 받아야 한다.
- raw SQL/ORM helper는 허용하되, 권한과 비즈니스 규칙은 서비스 경계 바깥으로 새지 않게 한다.
- 우선 대상은 `pms`, `meeting`, `docs`, `planner`다.

이 결정으로 ACL, audit, 외부 공개 API, AI tool 동작을 같은 백엔드 경계에서 검증할 수 있다.

### 4. CallerPrincipal을 공통 호출자 모델로 채택한다

- 공통 타입 `CallerPrincipal`을 도입한다.
- 최소 필드는 `kind`, `workspace_id`, `source`, `user_id?`, `service_account_id?`, `session_id?`다.
- human 호출은 `kind="user"`와 `actor_user_id`를 유지한다.
- non-user 호출은 `principal_kind`/`principal_id`를 audit와 LLM context에 함께 남긴다.
- 외부 소비자 기본 모델은 workspace-scoped `ServiceAccount + API Key`다.
- platform-wide client는 v1 범위에 넣지 않는다.

이 결정으로 user 호출, system worker, future service account 호출을 한 서비스 경계에서 처리할 수 있다.

## Consequences

### Positive

- workspace별 앱 노출과 chrome 구성이 프론트 하드코딩에서 분리된다.
- AI task/tool 확장이 도메인 단위로 이동한다.
- 정책 seed와 readiness가 registry 기반으로 일관된다.
- 미래의 API key/OAuth, webhook, quota를 추가해도 기존 user-flow를 크게 다시 뜯지 않는다.

### Negative

- 관리자 DB 카탈로그와 코드 capability registry 간 정합성 검증이 필요하다.
- 도메인 capability 등록 누락 시 bootstrap 또는 readiness에서 바로 드러나므로 등록 discipline이 필요하다.
- service layer 전환은 단계적 리팩토링이 필요하며, 단기적으로 router/service가 공존한다.

## Non-Goals

- 이번 결정은 service account/API key의 실제 발급/회전/폐기 구현을 포함하지 않는다.
- 서버가 프론트 컴포넌트를 동적으로 주입하는 구조는 도입하지 않는다.
- 관리자가 새 앱 row를 만든다고 route/component/backend 구현이 자동 생성되는 것은 아니다.
- 자동 import 스캔 기반 plugin architecture는 도입하지 않는다.

## Follow-up

- Read tool 대상 도메인의 service layer 추출을 계속 진행한다.
- Company-scoped external REST integration의 공통 API key 발급·scope·회수 정책은
  [ADR 0012](0012-platform-api-keys-and-rest-integrations.md)에서 구체화한다.
- `workspace_apps.py`를 실제 구현 capability registry와 관리자 DB catalog projection으로 분리한다.
