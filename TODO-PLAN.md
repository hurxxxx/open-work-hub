# PMS 구현 계획

## 완료된 기능 (Tier 1 + Tier 2)

Tier 1 Core(태스크 CRUD, 상태/우선순위, 담당자, 5개 뷰, 필터/검색, 서브태스크, 코멘트, 마일스톤)
+ Tier 2 Productivity(라벨, 체크리스트, 첨부파일, 시간추적, 일괄작업, 활동로그, 대시보드) 완료.
상세 이력은 git log 참조: `ebb9cd8` ~ `745afe8`

---

## ~~Phase 5: 필수 보완~~ ✅ 완료

계층 구조(team_id FK, SubSidebar Space 그룹핑) + 알림 UI(벨 아이콘, 드롭다운, 이슈 이동) 모두 구현 완료.

---

## ~~Phase 6: Tier 3 — Professional~~ ✅ 완료 (8/8)

### 6-1. 프로젝트별 커스텀 상태 ✅
- [x] **BE**: `pms_project_statuses` 모델 (project_id, slug, name, color, category, sort_order)
- [x] **BE**: Issue 상태를 string으로 전환 + 프로젝트별 상태 자동 시드
- [x] **BE**: CRUD 엔드포인트 (GET/POST/PATCH/DELETE)
- [x] **FE**: 프로젝트 설정에서 상태 관리 UI (추가/수정/삭제)
- [x] **FE**: 모든 뷰(List/Board/Table/TaskDetail/Filter/Bulk/NewTask)에서 커스텀 상태 반영

### 6-2. 반복 태스크 ✅
- [x] **BE**: Issue에 `recurrence_rule` 필드 (daily/weekly/biweekly/monthly)
- [x] **BE**: 생성/수정 API에서 recurrence_rule 지원
- [x] **FE**: 태스크 상세에서 반복 설정 UI (None/Daily/Weekly/Biweekly/Monthly)

### 6-3. 태스크 템플릿 ✅
- [x] **BE**: `pms_task_templates` 모델 + CRUD 엔드포인트
- [x] **FE**: `listTaskTemplates`/`createTaskTemplate`/`deleteTaskTemplate` API
- [x] **FE**: NewTaskModal에서 Templates 버튼 → 템플릿 선택 적용

### 6-4. @멘션 ✅
- [x] **BE**: 코멘트 생성 시 body에서 `@{uuid}` 파싱 + body_blocks에서 mention 노드 추출 → 알림 생성
- [x] **FE**: 코멘트 입력에 `@` 드롭다운 (팀원 자동완성) → `@{user_id}` 삽입

### 6-5. 태스크 의존성 시각화 ✅
- [x] **FE**: pms-api.ts에 createDependency/deleteDependency 함수 추가
- [x] **FE**: TaskDetail에 Dependencies 섹션 (표시 + 삭제)

### 6-6. 커스텀 필드 ✅
- [x] **BE**: `pms_custom_fields` + `pms_custom_field_values` 모델
- [x] **BE**: CRUD 엔드포인트 (GET/POST/DELETE fields, GET/PUT values)
- [x] **FE**: `listCustomFields`/`createCustomField`/`deleteCustomField`/`listIssueCustomFieldValues`/`setIssueCustomFieldValue` API

### 6-7. 다중 담당자 ✅
- [x] **BE**: `pms_issue_assignees` junction 테이블 + `IssueAssignee` 모델
- [x] **BE**: Issue에 `assignee_ids`/`assignee_names` 직렬화 추가
- [x] **BE**: `PUT /issues/{id}/assignees` 엔드포인트
- [x] **FE**: `setIssueAssignees` API + `PmsIssue` 인터페이스에 `assignee_ids`/`assignee_names` 추가

### 6-8. 내보내기 ✅
- [x] **BE**: `GET /projects/{id}/export?format=csv` 엔드포인트
- [x] **FE**: 프로젝트 헤더에 Download 버튼 (CSV 다운로드)

---

## ~~Phase 7: Tier 4 — Advanced~~ ✅ 완료 (5/5)

### 7-1. 폴더 계층 ✅
- [x] **BE**: `Folder` 모델 + `pms_projects.folder_id` FK
- [x] **BE**: Folder CRUD 엔드포인트 (GET/POST/PATCH/DELETE)
- [x] **FE**: `listFolders`/`createFolder`/`updateFolder`/`deleteFolder` API

### 7-2. 역할/권한 관리 ✅
- [x] **BE**: role을 owner/admin/editor/viewer/member으로 확장
- [x] **BE**: `_ensure_project_editor` 미들웨어 + owner/admin 분리
- [x] **BE**: 역할 변경 PATCH + 멤버 제거 DELETE 엔드포인트
- [x] **FE**: `updateMemberRole`/`removeProjectMember` API

### 7-3. 자동화 규칙 ✅
- [x] **BE**: `Automation` 모델 (trigger/condition/action JSON)
- [x] **BE**: CRUD 엔드포인트 (GET/POST/PATCH/DELETE)
- [x] **FE**: `listAutomations`/`createAutomation`/`updateAutomation`/`deleteAutomation` API

### 7-4. Goals/OKR ✅
- [x] **BE**: `Goal` + `GoalLink` 모델 (progress, linked issues)
- [x] **BE**: Goal CRUD + Issue link/unlink 엔드포인트
- [x] **FE**: Goals 전체 API (`listGoals`/`createGoal`/`updateGoal`/`deleteGoal`/`linkIssueToGoal`/`unlinkIssueFromGoal`)

### 7-5. Docs ✅
- [x] **BE**: `Doc` 모델 (project_id, title, content_blocks, created_by)
- [x] **BE**: Doc CRUD 엔드포인트 (GET list/single, POST, PATCH, DELETE)
- [x] **FE**: `listDocs`/`createDoc`/`getDoc`/`updateDoc`/`deleteDoc` API
