# AIDOO PMS 구현 계획

## 목표

- AIDOO 안에 실제로 운영 가능한 경량 PMS를 구축한다.
- 초기 버전은 현대적인 프로젝트 관리 도구의 핵심 기능만 먼저 구현한다.
- AI 보조 기능은 넣지 않는다.
- 대신 REST API를 표준화해 웹, 향후 CLI, 향후 챗봇이 같은 PMS API를 사용하도록 설계한다.

## 제품 방향

- 일상 작업 UX는 `Linear`처럼 빠르게 간다.
- 프로젝트 진행률, 마일스톤, 대시보드 요약은 `Jira / Azure DevOps`처럼 본다.
- 간트는 지금 넣지 않되, `OpenProject`식 planning view를 나중에 추가할 수 있도록 일정 데이터 구조를 먼저 깐다.

## 1차 범위

- `Project`
- `Project member`
- `Milestone`
- `Issue`
- `Comment`
- `Activity log`
- `Dependency`
- `Dashboard`
- `Board`
- `List`

제외:

- Wiki / 문서관리
- AI preview, triage, 요약 생성
- CLI 구현
- 간트 UI
- 제조업 전용 확장 엔터티

## 구현 원칙

- AIDOO 단일 테넌트 구조로 시작한다.
- PMS는 공통 identity 계층의 `workspace` 아래에 놓는다. 기본 workspace key 는 `pms` 다.
- 협업 경계는 장기적으로 `Workspace > Team > Project` 로 정렬한다.
- 현재 PMS REST API는 기존 `project membership(owner/member)` 과 공존한다.
- 전역 관리자 호환 필드는 유지하되, 장기적으로는 `platform-admin` 과 permission 기반으로 수렴한다.
- 챗봇이 PMS를 조작하게 되더라도 별도 백도어를 만들지 않고 공식 PMS REST API만 사용한다.

## 데이터 모델

### 핵심 엔터티

- `pms_projects`
- `pms_project_members`
- `pms_milestones`
- `pms_labels`
- `pms_issues`
- `pms_issue_labels`
- `pms_issue_comments`
- `pms_issue_activity_logs`
- `pms_schedule_dependencies`

### 프로젝트

- `key`
- `name`
- `description`
- `status`
- `archived`
- `created_by_id`
- 장기 확장: `workspace_id`, `team_id`

### 프로젝트 멤버

- `project_id`
- `user_id`
- `role`

역할:

- `owner`
- `member`

### 마일스톤

- `title`
- `description`
- `status`
- `start_date`
- `due_date`
- `sort_order`

### 이슈

- `issue_number`
- `title`
- `description`
- `status`
- `priority`
- `assignee_id`
- `reporter_id`
- `milestone_id`
- `start_date`
- `due_date`
- `board_position`
- `archived`

### 의존성

- `project_id`
- `predecessor_kind`
- `predecessor_id`
- `successor_kind`
- `successor_id`
- `relation_type`

초기에는 `issue -> issue`의 `blocks`만 사용한다.

## 진행률 규칙

- 수동 진행률은 두지 않는다.
- 상태 기반 자동 계산만 사용한다.

가중치:

- `backlog = 0`
- `todo = 0`
- `in_progress = 0.5`
- `done = 1`
- `canceled = 분모 제외`

롤업:

- 프로젝트 진행률 = 프로젝트 내 비취소 이슈 평균
- 마일스톤 진행률 = 연결된 비취소 이슈 평균

## REST API 규약

기본 prefix:

- `/api/v1/pms`

### 프로젝트

- `GET /projects`
- `POST /projects`
- `GET /projects/{project_id}`
- `PATCH /projects/{project_id}`

### 멤버

- `GET /projects/{project_id}/members`
- `POST /projects/{project_id}/members`

### 마일스톤

- `GET /projects/{project_id}/milestones`
- `POST /projects/{project_id}/milestones`
- `PATCH /milestones/{milestone_id}`

### 이슈

- `GET /projects/{project_id}/issues`
- `POST /projects/{project_id}/issues`
- `GET /issues/{issue_id}`
- `PATCH /issues/{issue_id}`

### 댓글과 활동 로그

- `POST /issues/{issue_id}/comments`
- `GET /issues/{issue_id}/activity-logs`

### 의존성

- `POST /dependencies`
- `DELETE /dependencies/{dependency_id}`

### 대시보드

- `GET /dashboard/summary`

### 목록 응답 표준

모든 목록 응답은 아래를 따른다.

- `items`
- `total`
- `page`
- `page_size`

### 목록 쿼리 표준

- `page`
- `page_size`
- `sort_by`
- `sort_dir`
- `q`
- 도메인별 필터: `status`, `priority`, `assignee_id`, `label_id`, `milestone_id`, `archived`

## 웹 구현 계획

### 1차 화면

- PMS Home Dashboard
- Project creation
- Project summary cards
- Project detail board
- Project detail list
- Issue detail drawer
- Mobile issue detail panel
- Milestone panel
- Member panel

### 상호작용

- 보드는 드래그 앤 드롭으로 상태를 바꾼다.
- 상태 이동 시 `status + board_position`을 같이 저장한다.
- 리스트와 보드는 같은 이슈 데이터를 공유한다.
- 이슈 상세에서 상태, 우선순위, 담당자, 마일스톤을 변경할 수 있다.
- 댓글과 활동 로그는 이슈 상세에서 본다.

### 모바일

- 데스크톱은 넓은 테이블/보드와 보조 drawer를 유지할 수 있다.
- 모바일은 가로 3단 분할을 사용하지 않는다. 목록, 필터, 상세를 하나의 주 흐름으로 접고 필요한 보조 정보만 drawer 또는 전체 폭 패널로 연다.
- 모바일 PMS 목록은 카드 중심(`TaskIssueCard`)으로 스캔 가능해야 하며, 필터는 압축된 바/시트/섹션으로 노출한다.
- 모바일 이슈 상세는 전체 폭 상세 패널로 열고, 설명/활동/첨부/관련 자료는 탭 또는 세로 섹션으로 정리한다.
- 모바일 셸에서 햄버거는 앱/워크스페이스 전환만 담당한다. PMS 내부 메뉴는 상단 앱 제목에서 별도 드로어로 연다.

## 테스트 기준

### API

- 프로젝트 생성
- 프로젝트 멤버 권한
- 마일스톤 생성
- 이슈 생성
- 상태 변경
- 댓글 추가
- 활동 로그 자동 기록
- 대시보드 집계
- 의존성 생성과 삭제

### 웹

- `/pms` 라우트 렌더링
- PMS 대시보드 기본 표시
- 프로젝트 요약 카드 렌더링
- 프로젝트 상세 보드/리스트 렌더링
- 모바일 상세 분기 가드

## 현재 구현 상태

이미 반영된 표면:

- 백엔드 PMS 도메인 모델 추가
- PMS REST API 추가
- API 앱 라우터 연결
- `/pms` 실제 작업면 연결
- 프로젝트/마일스톤/이슈/댓글/활동 로그 UI 연결
- 보드 드래그 이동
- 모바일 PMS 카드 목록, 필터 접힘, 상세 전체 폭 패널
- 모바일 앱 전환 드로어와 앱 내부 메뉴 드로어 분리
- 프로젝트/마일스톤/이슈/대시보드 테스트 추가
- 공통 auth/admin foundation 과 함께 workspace/team/group 문서 기준 추가

## 2차 확장 포인트

- 간트 / 타임라인 view
- 저장된 필터
- 릴리즈 / iteration 개념
- CLI 표면 구현
- 챗봇 툴 호출을 위한 PMS API action layer
- 제조업 전용 타입
  - `risk`
  - `decision`
  - `change request`
  - `approval stage`
  - `linked documents`
