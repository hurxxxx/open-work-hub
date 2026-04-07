# Admin API Contract

## 목적

- auth/admin foundation 의 현재 REST 계약을 고정한다.
- 웹 앱과 향후 외부 운영 도구가 같은 API를 사용하도록 한다.

## Auth API

- `GET /api/v1/auth/bootstrap-status`
  - 첫 관리자 bootstrap 필요 여부 반환
- `POST /api/v1/auth/setup`
  - 첫 관리자 생성
  - 성공 시 session token 과 확장된 user payload 반환
- `POST /api/v1/auth/login`
  - local ID/PW 로그인
- `GET /api/v1/auth/me`
  - 현재 사용자 정보
  - `workspace_roles`, `group_slugs`, `permissions`, `visible_features`, `must_change_password`, `is_admin(compat)` 포함
- `POST /api/v1/auth/logout`
  - 현재 세션 revoke
- `POST /api/v1/auth/change-password`
  - `current_password`, `new_password`
- `PATCH /api/v1/auth/preferences`
  - `display_name`, `full_name`, `job_title`, `theme_preference`
- `GET /api/v1/auth/sessions`
  - 현재 사용자 세션 목록
- `POST /api/v1/auth/sessions/{session_id}/revoke`
  - 특정 사용자 세션 종료

## Admin API

### Users

- `GET /api/v1/admin/users`
- `GET /api/v1/admin/users/{user_id}`
- `POST /api/v1/admin/users`
- `PATCH /api/v1/admin/users/{user_id}`
- `POST /api/v1/admin/users/{user_id}/reset-password`

### Org Units

- `GET /api/v1/admin/org-units`
- `POST /api/v1/admin/org-units`
- `PATCH /api/v1/admin/org-units/{org_unit_id}`

### Groups

- `GET /api/v1/admin/groups`
- `POST /api/v1/admin/groups`
- `PATCH /api/v1/admin/groups/{group_id}`
- `PUT /api/v1/admin/groups/{group_id}/members`

### Workspaces

- `GET /api/v1/admin/workspaces`
- `POST /api/v1/admin/workspaces`
- `PATCH /api/v1/admin/workspaces/{workspace_id}`
- `GET /api/v1/admin/workspaces/{workspace_id}/bindings`
- `PUT /api/v1/admin/workspaces/{workspace_id}/bindings`

### Teams

- `GET /api/v1/admin/teams`
- `POST /api/v1/admin/workspaces/{workspace_id}/teams`
- `PATCH /api/v1/admin/teams/{team_id}`
- `GET /api/v1/admin/teams/{team_id}/members`
- `PUT /api/v1/admin/teams/{team_id}/members`

### Feature Policies

- `GET /api/v1/admin/feature-policies`
- `PUT /api/v1/admin/feature-policies`

### Audit

- `GET /api/v1/admin/audit-logs`

## 권한 기준

- 읽기/쓰기 권한은 permission 코드로 나눈다.
- 주요 코드
  - `admin.access`
  - `user.read`, `user.write`
  - `group.read`, `group.write`
  - `org_unit.read`, `org_unit.write`
  - `workspace.read`, `workspace.write`
  - `team.read`, `team.write`
  - `feature_policy.read`, `feature_policy.write`
  - `audit.read`
  - `session.revoke`

## 호환 필드

- `AuthUser.is_admin` 은 당분간 유지한다.
- 내부 계산은 `platform-admin` 과 `admin.access` 중심으로 이동한다.
- 기존 PMS 소비처는 이 호환 필드를 계속 사용할 수 있다.
