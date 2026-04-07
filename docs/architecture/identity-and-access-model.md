# Identity And Access Model

## 목적

- 공통 사용자 인증과 관리자 기능의 기준 모델을 고정한다.
- 포털 협업 구조를 `Tenant > Workspace > Team > Project` 기준으로 설명한다.
- `OrgUnit` 과 `AccessGroup` 의 역할을 분리한다.

## 계층

- `Tenant`
  - 회사 전체 보안 경계
  - v1은 single-tenant
- `Workspace`
  - `AI`, `Docs`, `PMS`, `Planner`, `Admin` 같은 업무영역
- `Team`
  - 한 workspace 안의 협업 단위
  - 서로 다른 부서 사용자가 함께 참여할 수 있다
- `Project`
  - 실행 단위
  - PMS는 legacy project membership과 공존하며 점진적으로 team ownership으로 수렴한다

## 사용자 관련 엔터티

- `User`
  - 로그인 주체
  - `email`, `full_name`, `display_name`, `employee_code`, `job_title`, `status`, `must_change_password`, `theme_preference`, `last_login_at`
- `OrgUnit`
  - 전사 조직 메타데이터
  - HR/보고 체계/정책 필터 용도
  - 협업의 주 경계가 아니다
- `AccessGroup`
  - tenant 전역 접근 그룹
  - 권한 코드 묶음 소유
  - workspace 접근은 binding으로 별도 적용

## Binding 모델

- `WorkspaceUserBinding`
  - 특정 사용자를 특정 workspace에 직접 연결
- `WorkspaceGroupBinding`
  - 특정 그룹을 특정 workspace에 연결
- `TeamMember`
  - 팀 구성원 관계

## 권한 계산

1. 사용자 직접 속성에서 `is_admin` 호환 상태를 읽는다.
2. 사용자의 `AccessGroup.permissions` 를 합친다.
3. `platform-admin` 또는 `admin.access` 가 있으면 전체 관리자 권한으로 확장한다.
4. direct/group workspace binding 을 합쳐 workspace 역할을 계산한다.
5. `FeaturePolicy` 에 `required_permissions`, `allowed_workspace_keys`, `allowed_group_slugs` 를 적용해 화면 노출 여부를 판단한다.

## 기본 seed

- OrgUnit
  - `hq`
- AccessGroup
  - `platform-admin`
  - `people-admin`
  - `workspace-admin`
  - `audit-viewer`
- Workspace
  - `ai`
  - `docs`
  - `pms`
  - `planner`
  - `admin`

## 예시 시나리오

- 사용자 A는 `Engineering`, 사용자 B는 `Quality` OrgUnit 소속이다.
- 두 사용자는 모두 `PMS Workspace` 에 binding 된다.
- 두 사용자는 `Cross Functional Squad` 팀에 함께 속한다.
- 이 팀이 여러 project를 동시에 운영할 수 있다.
- 이때 OrgUnit은 보고 체계와 정책 필터에만 쓰이고, 실제 협업은 workspace/team/project에서 발생한다.

## 호환 정책

- 기존 `is_admin` 필드는 당분간 유지한다.
- PMS의 `owner/member` project membership도 유지한다.
- 새 관리자 기능은 permission 기반으로 추가하고, 기존 소비처는 호환 필드를 계속 받는다.

## 후속 확장

- multi-tenant
- SSO/OIDC
- LDAP/AD sync
- workspace별 세분 권한
- project의 강제 team ownership
