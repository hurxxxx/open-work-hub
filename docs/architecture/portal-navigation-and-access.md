# Portal Navigation And Access

## 기본 구조

- 좌측 AppBar는 workspace 중심 진입점이다.
- 기본 workspace
  - `Home`
  - `AI`
  - `PMS`
  - `Docs`
  - `Planner`
- `Admin` 은 top-level AppBar 아이콘으로 고정하지 않고 프로필 메뉴에서 진입한다.

## 프로필 메뉴

- 사용자 요약
  - 표시 이름
  - 이메일
  - OrgUnit
- 내 계정
- 보안 설정
- 테마
  - `system`
  - `light`
  - `dark`
- 관리 콘솔
  - 관련 read 권한이 있을 때만 노출
- 로그아웃

## 화면 노출 규칙

- workspace 노출은 `FeaturePolicy` 와 `workspace_roles` 로 결정한다.
- 현재 기본 feature code
  - `nav.ai`
  - `nav.docs`
  - `nav.pms`
  - `nav.planner`
  - `nav.admin`
- route에 직접 접근하더라도 필요한 feature/policy가 없으면 접근 거부 화면을 반환한다.

## 설정 화면

- `/settings/account`
  - 표시 이름
  - 성명
  - 직함
  - 테마
- `/settings/security`
  - 비밀번호 변경
  - 세션 목록
  - 세션 종료

## 관리자 화면

- `/admin/users`
- `/admin/groups`
- `/admin/workspaces`
- `/admin/teams`
- `/admin/feature-access`
- `/admin/audit`

각 화면은 `admin.access` 또는 해당 도메인의 read permission 이 있어야 한다.

## UX 원칙

- 기능 전환은 AppBar와 profile menu 두 축으로 나눈다.
- theme 토글과 account/security 진입은 profile context 안에 둔다.
- 관리자 기능은 일반 사용자 메뉴를 오염시키지 않도록 별도 섹션으로 묶는다.
