# ADR 0012: 공통 플랫폼 API 키와 외부 REST 연계

- Status: Accepted
- Date: 2026-07-29

## Context

AI-DO의 기존 Bearer token은 로그인한 사용자의 `AuthSession`을 나타낸다. 외부 시스템이
통합 인사정보 같은 회사 범위 데이터를 주기적으로 읽을 때 사람의 로그인 세션을 재사용하면
세션 만료, 사용자 권한, 감사 주체가 기계 연계와 섞인다.

첫 외부 연계 대상은 통합 인사정보이지만, 도메인마다 서로 다른 키 저장소와 인증 형식을
추가하면 발급·회수·감사 정책이 분산된다. 반대로 하나의 만능 키가 기존 사용자 API 전체에
접근하게 하면 최소 권한과 도메인별 공개 계약을 지킬 수 없다.

관리자는 발급한 키를 연계 시스템에 다시 전달해야 할 수 있다. 발급 순간에만 원문을
보여주는 방식으로는 운영 인수인계가 어렵기 때문에, 로그인한 platform admin이 기존 키를
다시 볼 수 있는 통제된 복호화 경로가 필요하다.

## Decision

### 공통 키 저장소와 scope registry를 둔다

- 플랫폼 API 키는 회사 tenant 전체의 기계 호출자다. 현재 tenant는 배포·DB 경계로
  식별하므로 키 row에 `workspace_id`를 넣지 않는다.
- 키 형식은 AI-DO가 발급한 opaque `aido_pk_...` 문자열이다.
- DB에는 검증용 SHA-256 hash, 목록 표시용 prefix, 활성 키의 재조회용 암호문, 이름, scope
  집합, 생성·폐기 주체와 시각, 최근 사용 시각을 저장한다.
- 원문 키와 관리자 비밀번호는 로그·감사 payload·일반 목록 응답에 저장하거나 반환하지
  않는다.
- 키 scope는 서버 registry가 소유한다. 이번에 활성화하는 첫 scope는 `hr:read`다.
  이후 외부 REST interface는 같은 키 저장소를 사용하되 자신의 scope를 명시적으로
  요구한다.
- 플랫폼 API 키는 opt-in한 `/api/v1/integrations/*` endpoint에서만 인정한다. 기존 사용자
  세션 API, 관리자 API 또는 workspace API의 권한을 자동으로 얻지 않는다.

### 관리자 발급·조회·폐기를 제공한다

- `platform_admin`만 키 목록 조회, 발급, 원문 재조회와 폐기를 수행한다.
- 새 키 원문은 발급 응답에서 표시할 수 있다.
- 기존 키 원문 재조회는 현재 로그인한 사용자의 platform admin 권한을 서버에서 다시
  확인한 뒤에만 허용한다. 별도 비밀번호 재인증은 요구하지 않는다.
- 재조회 가능한 원문은 서버 credential encryption root로 암호화해 저장한다. 암호화 설정이
  없거나 암호문을 복호화할 수 없으면 발급·재조회는 fail-closed한다.
- 목록은 prefix만 반환한다. 폐기한 키는 이력으로 남기고 다시 활성화하거나 원문을
  재조회하지 않으며 재조회용 암호문도 폐기 시 제거한다. 교체는 새 키 발급 후 기존 키 폐기로
  수행한다.
- 발급·원문 조회·폐기는 actor와 key ID를 감사하되 원문, password, 이름처럼 운영상 불필요한
  secret 값을 감사 payload에 넣지 않는다.

### 외부 REST API는 별도 계약으로 공개한다

- 외부 연계 API는 `/api/v1/integrations` 아래에 둔다.
- 각 endpoint는 필요한 API key scope를 선언하고, 누락·유효하지 않음·폐기됨은 `401`,
  scope 부족은 `403`으로 처리한다.
- 요청·응답 Pydantic model이 OpenAPI 정본이다. 전체 스펙은 FastAPI의 `/openapi.json`,
  Swagger UI는 `/docs`, ReDoc은 `/redoc`에서 자동 생성한다.
- 저장소의 generated TypeScript 계약도 같은 OpenAPI에서 재생성하고 CI drift 검사를
  통과해야 한다.
- 도메인별 연계 문서는 허용 field, 기준 projection, pagination/snapshot, 오류와 예제를
  별도로 소유한다. Raw snapshot payload와 내부 decision/control ID를 외부 DTO에 그대로
  노출하지 않는다.
- 개인정보 조회 audit는 API key ID, endpoint/basis, version 또는 snapshot ID, page와
  반환 건수, 성공 여부와 안정적인 오류 code만 기록한다. 호출자가 보낸 잘못된 snapshot
  원문과 검색어, 이름, 사번, 이메일 같은 row 값은 감사 payload에 기록하지 않는다.
- 키 관리 응답과 개인정보 연계 응답은 성공·도메인 오류 모두 cache 저장을 금지한다.

## Consequences

- 외부 시스템은 사람 세션 없이 장기 연계할 수 있고, 관리자는 한 화면에서 키를 발급·회수할
  수 있다.
- 새 REST interface는 인증 저장소를 다시 만들지 않고 scope와 공개 DTO만 추가한다.
- 키 원문 재조회가 가능하므로 관리자 session 보호, 조회 감사, 암호화 root의 보호와 회전
  계획이 필수다. 검증 hash와 암호문은 목적이 다르며 둘 중 하나를 다른 하나의 대체물로
  사용하지 않는다.
- 현재 구현은 key expiry, IP allowlist, quota와 자동 rotation을 포함하지 않는다. 필요하면
  공통 control plane에 추가하고 각 도메인에 중복 구현하지 않는다.
- `CallerPrincipal` 전체 통합은 후속 과제다. 이번 외부 read endpoint는 API key context를
  직접 감사하며 기존 user/workspace principal 계약을 변경하지 않는다.

## Related contracts

- [ADR 0001](0001-ai-platform-extensibility.md)
- [ADR 0011](0011-unified-hr-master.md)
- [외부 REST 연계 계약](../docs/domains/api-integrations/README.md)
- [통합 인사 REST API](../docs/domains/hr/rest-api.md)
