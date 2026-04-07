# User And Group Admin Runbook

## 목적

- 운영자가 local account 기반 identity 기능을 관리하는 절차를 정리한다.

## 첫 관리자 생성

1. `/api/v1/auth/bootstrap-status` 가 `requires_setup: true` 인지 확인한다.
2. 웹 로그인 화면에서 첫 관리자 계정을 만든다.
3. 생성된 계정은 `platform-admin` 그룹과 관리자 호환 권한을 가진다.

## 사용자 생성

1. `관리 콘솔 > 사용자`
2. 이메일, 성명, 표시 이름, 기본 OrgUnit, 기본 그룹 입력
3. 생성 후 반환된 임시 비밀번호를 전달
4. 사용자는 첫 로그인 후 비밀번호를 변경해야 한다

## 비밀번호 재발급

1. `관리 콘솔 > 사용자`
2. 대상 사용자에서 `비밀번호 초기화`
3. 새 임시 비밀번호를 전달

## 그룹 운영

- `AccessGroup` 은 tenant 전역 권한 그룹이다.
- 권한 코드 묶음을 그룹에 넣고, 사용자를 그룹에 배정한다.
- workspace 접근은 group 자체만으로 열리지 않고 workspace binding이 추가로 필요하다.

## Workspace binding

- 사용자 또는 그룹을 특정 workspace에 연결한다.
- role 기본값은 `member`
- 관리자/운영팀은 필요한 workspace에만 binding 한다.

## Team 운영

- team 은 한 workspace 전용이다.
- cross-functional 사용자 구성이 가능하다.
- 서로 다른 OrgUnit 사용자도 같은 team 에 속할 수 있다.

## 세션 운영

- 사용자는 `보안 설정` 에서 본인 세션을 종료할 수 있다.
- 관리자는 비밀번호 초기화와 상태 변경으로 계정 접근을 통제한다.

## 감사로그 확인

- 사용자 생성
- 비밀번호 재설정
- 그룹 변경
- workspace binding 변경
- feature policy 변경
- 로그인/로그아웃

위 동작은 `관리 콘솔 > 감사로그` 에 기록된다.

## 로컬 PostgreSQL 개발 환경

```bash
docker compose -f compose.postgres.yml up -d
```

- 기본 계정은 `aidoo_db / aidoo_db`
- 기본 DB 이름은 `doowon_ai_portal`
- 실제 개발 DSN 이 루트 `.env` 에 있으면 그 값을 사용한다.
