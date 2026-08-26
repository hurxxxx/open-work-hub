# 조직 디렉터리 계약

조직 디렉터리는 현재 회사 배포 전체에서 공유하는 조직 계층과 사용자 프로필 메타데이터를
소유한다. 회사 tenant와 workspace의 범위는 [ADR 0007](../../../adr/0007-company-tenant-workspace-scope.md)을
따르며, 조직 단위는 workspace나 별도 tenant가 아니다.

## 현재 모델

- `organization_units`는 `name`, 고유 `slug`, 자유 형식 `unit_type`, 선택적인 `parent_id`,
  `active`와 생성·수정 시각을 저장한다.
- `users.primary_organization_unit_id`는 사용자의 주 소속 하나만 가리킨다.
- `users.employee_code`와 `users.job_title`은 회사 디렉터리 프로필 메타데이터다.
- 계층은 임의 깊이를 허용하지만 자기 자신 또는 자손을 부모로 지정하는 순환은 거부한다.
- 비활성 조직 단위는 과거 사용자 소속과 계층을 보존하지만 새 사용자에게 배정할 수 없다.

주 소속, 사번, 직책은 현재 권한 증거가 아니다. 조직 단위는 system role, workspace membership,
resource ACL, app entitlement를 부여하거나 대체하지 않는다. 조직 기반 RBAC가 필요하면 별도 정책,
서버 실행 게이트, migration과 ADR을 먼저 추가한다.

## 관리 API와 UI

| 기능                        | API                                           | 권한                 |
| --------------------------- | --------------------------------------------- | -------------------- |
| 조직 목록                   | `GET /api/v1/admin/organization-units`        | `organization.read`  |
| 조직 생성                   | `POST /api/v1/admin/organization-units`       | `organization.write` |
| 조직 수정·비활성화          | `PATCH /api/v1/admin/organization-units/{id}` | `organization.write` |
| 사용자 메타데이터 생성·수정 | 기존 `/api/v1/admin/users`                    | 기존 `user.write`    |
| 사용자 조직 필터            | `GET /api/v1/admin/users`의 조직 query        | 기존 `user.read`     |

관리 UI의 `/admin/organization`은 삭제 대신 비활성화를 제공한다. `/admin/people`은 주 소속,
사번과 직책을 편집하고 정확한 조직, 하위 조직 포함, 미소속 사용자 필터를 제공한다. 검색은 이름,
로그인 ID, 이메일과 함께 사번, 직책, 조직 이름을 포함한다.

## 외부 projection

외부 시스템은 조직 관리 API가 아니라 범위 제한 플랫폼 API를 사용한다.
`organization:read` scope의
`GET /api/v1/integrations/directory/organization-units`가 현재 상태를 페이지 단위로 반환한다.
자격 증명과 동기화 의미는 [Integrations](../integrations/README.md)가 소유한다.

## 변경 규칙

- 계층과 사용자 소속의 authoritative source는 PostgreSQL이다.
- 조직 삭제 API를 추가하기 전에 사용자 참조, 자손 처리, 외부 동기화 tombstone과 감사 보존
  정책을 결정한다.
- `unit_type`을 권한 분기나 고정 enum으로 사용하지 않는다. 제품 정책이 생기면 migration과 API
  호환 계약을 함께 설계한다.
- 사용자 응답의 `primary_organization_unit`은 편의를 위한 projection이며 canonical reference는
  `users.primary_organization_unit_id`다.
- API schema 변경 후 OpenAPI TypeScript를 다시 생성하고 한/영 관리자 UI 문구를 함께 갱신한다.

## 검증

- API 통합 계약: `apps/api/tests/test_organization_integrations.py`
- 계층 UI projection: `apps/web/src/platform/admin/admin-organization-section.spec.ts`
- 사용자 필터 controller: `apps/web/src/platform/admin/useAdminPeopleDirectoryController.spec.ts`
- Schema migration: `a7c4e9f2b6d1_add_organization_and_platform_integrations.py`
