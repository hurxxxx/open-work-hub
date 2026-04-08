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

## 🟢 Phase 7: Tier 4 — Advanced (5개)

### 7-1. 폴더 계층
- [ ] **BE**: `pms_folders` 모델 (space_id, name, sort_order)
- [ ] **BE**: `pms_projects.folder_id` FK 추가
- [ ] **FE**: 사이드바에 Folder 토글 + Folder 내 프로젝트 그룹핑

### 7-2. 역할/권한 관리
- [ ] **BE**: `pms_project_members.role`을 viewer/editor/admin으로 확장
- [ ] **BE**: 엔드포인트별 권한 체크 미들웨어
- [ ] **FE**: 멤버 관리에서 역할 변경 UI

### 7-3. 자동화 규칙
- [ ] **BE**: `pms_automations` 모델 (project_id, trigger, condition, action)
- [ ] **BE**: 이슈 변경 시 자동화 규칙 평가/실행
- [ ] **FE**: 자동화 규칙 빌더 UI (When → If → Then)

### 7-4. Goals/OKR
- [ ] **BE**: `pms_goals` 모델 (workspace_id, name, target, progress, linked issues)
- [ ] **BE**: Goal ↔ Issue 연결 + 자동 진행률 계산
- [ ] **FE**: Goals 뷰 (목표 목록 + 진행률 바 + 연결된 태스크)

### 7-5. Docs
- [ ] **BE**: `pms_docs` 모델 (project_id, title, content_blocks)
- [ ] **BE**: Doc CRUD 엔드포인트
- [ ] **FE**: Docs 뷰 (BlockNote 에디터 재사용) + 사이드바 연결
