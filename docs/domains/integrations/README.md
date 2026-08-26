# 플랫폼 API 키와 외부 연계 계약

이 도메인은 회사 내부 또는 승인된 외부 시스템이 Open Work Hub의 제한된 company-level
projection을 읽는 경계를 소유한다. 현재 제공하는 기능은 조직·임직원 디렉터리의 읽기 전용
연계이며 사용자 세션, 관리자 API, workspace API를 대신하는 범용 서비스 계정이 아니다.

핵심 결정과 보안 근거는
[ADR 0010](../../../adr/0010-platform-api-key-directory-integration.md)에 기록한다.

## 자격 증명 경계

- 키 형식은 `owh_pk_` 접두사를 가진 opaque bearer token이다.
- 외부 endpoint는 일반 사용자 access token을 거부하고, 일반 API도 플랫폼 API 키를 사용자
  세션으로 인정하지 않는다.
- 서버는 인증용 SHA-256 hash, 목록용 prefix, 관리자 재표시용 암호문만 저장한다.
- 암호화에는 전용
  `OPEN_WORK_HUB_PLATFORM_API_KEY_ENCRYPTION_KEY`를 사용한다. 값이 없으면 키 발급·재표시는
  fail closed지만 기존 hash 기반 인증은 계속 동작한다.
- 폐기 시 암호문을 즉시 비우고 hash row는 감사·재사용 방지를 위해 보존한다. 폐기된 키는
  다시 활성화하거나 재표시할 수 없다.
- 키 원문, Authorization header와 암호문은 API 응답 목록, 로그, 감사 payload에 넣지 않는다.
  발급·재표시 응답과 인증 실패 응답에는 `private, no-store`를 적용한다.

관리자가 키를 재표시할 수 있는 것은 현재 승인된 제품 요구사항이다. 따라서 전용 암호화 키의
접근 통제가 키 데이터베이스 접근 통제만큼 중요하다. 재표시 작업은 항상 감사한다.

## Scope와 endpoint

| Scope               | Method and path                                         | Projection                            |
| ------------------- | ------------------------------------------------------- | ------------------------------------- |
| `organization:read` | `GET /api/v1/integrations/directory/organization-units` | 조직 계층과 활성 상태                 |
| `people:read`       | `GET /api/v1/integrations/directory/people`             | 사용자 식별·프로필·주 소속 메타데이터 |

Scope registry는 코드의 고정 allowlist이며 임의 문자열 scope를 발급할 수 없다. 각 route는
OpenAPI의 `x-open-work-hub-platform-api-scopes` extension으로 요구 scope를 선언한다. 관리자
목록 API는 이 OpenAPI 계약에서 scope별 operation과 Swagger/ReDoc 링크를 파생한다. 문서 목록을
별도 하드코딩하지 않는다.

모든 외부 목록은 `page`와 최대 200인 `page_size`를 받으며 기본적으로 활성 항목만 반환한다.
응답은 요청 시점의 현재 상태 projection이다. 페이지 사이의 snapshot consistency, delta token,
tombstone, webhook과 exactly-once 전달은 현재 제공하지 않는다. 장기 동기화 consumer는 전체
재조정이 가능해야 한다.

## 관리자 수명주기

| 기능              | API                                                | 권한                      |
| ----------------- | -------------------------------------------------- | ------------------------- |
| 목록과 scope 문서 | `GET /api/v1/admin/platform-api-keys`              | `platform_api_key.read`   |
| 발급              | `POST /api/v1/admin/platform-api-keys`             | `platform_api_key.write`  |
| 재표시            | `POST /api/v1/admin/platform-api-keys/{id}/reveal` | `platform_api_key.reveal` |
| 폐기              | `POST /api/v1/admin/platform-api-keys/{id}/revoke` | `platform_api_key.write`  |

현재 `platform_admin`만 이 권한들을 가진다. 관리 UI는 `/admin/api-integrations`에 있으며 원문을
브라우저 저장소에 쓰지 않고 dialog를 닫을 때 component state에서 제거한다.

## 감사와 운영

- 발급, 목록, 재표시, 폐기와 성공한 외부 read는 actor 또는 API key ID, scope가 아닌 결과 수,
  paging 정보만 포함해 감사한다.
- 키 hash와 prefix로 원문을 복원할 수 없다. 재표시는 암호문을 통해서만 수행한다.
- 암호화 root를 변경하면 기존 키 인증은 계속 가능하지만 기존 암호문 재표시는 불가능해진다.
  회전 시 새 root로 새 키를 발급해 consumer를 전환한 뒤 이전 키를 폐기한다.
- 외부 쓰기, SCIM provisioning, inbound webhook, customer-defined scope, IP allowlist와 키별 rate
  limit는 현재 non-goal이다. 추가 시 별도 위협 모델과 rollout gate가 필요하다.

## 검증

- API, scope, 저장·폐기·감사 계약:
  `apps/api/tests/test_organization_integrations.py`
- OpenAPI/generated client: `pnpm generate:api-client`, `pnpm check:api-contract`
- Migration graph: `pnpm check:alembic-graph`, `pnpm test:alembic-graph`
