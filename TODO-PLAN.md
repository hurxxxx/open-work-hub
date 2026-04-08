# PMS 구현 계획

## 완료된 기능 (Tier 1 + Tier 2)

Tier 1 Core(태스크 CRUD, 상태/우선순위, 담당자, 5개 뷰, 필터/검색, 서브태스크, 코멘트, 마일스톤)
+ Tier 2 Productivity(라벨, 체크리스트, 첨부파일, 시간추적, 일괄작업, 활동로그, 대시보드) 완료.
상세 이력은 git log 참조: `ebb9cd8` ~ `745afe8`

---

## 🔴 Phase 5: 필수 보완 (2개)

### 5-1. 계층 구조 — Space > Project > Task
- [ ] **BE**: `pms_projects.team_id` FK 추가 (nullable), 스키마/필터/직렬화 수정
- [ ] **FE**: `pms-api.ts`에 team_id 타입 + 필터 파라미터
- [ ] **FE**: `SubSidebar.tsx` — Space별 프로젝트 그룹핑, +/... 메뉴
- [ ] **FE**: `CreateProjectModal.tsx` — teamId prop, 폼 리셋
- [ ] **FE**: `CreateSpaceModal.tsx` — 폼 리셋

### 5-2. 알림 UI
- [ ] **FE**: 헤더에 벨 아이콘 + unread count 뱃지
- [ ] **FE**: 알림 드롭다운 (목록, 읽음 처리, 전체 읽음)
- [ ] **FE**: 알림 클릭 시 해당 이슈로 이동

---

## 🟡 Phase 6: Tier 3 — Professional (8개)

### 6-1. 프로젝트별 커스텀 상태
- [ ] **BE**: `pms_project_statuses` 모델 (project_id, name, color, category, sort_order)
- [ ] **BE**: Issue 상태를 enum → FK로 전환 (또는 string + 프로젝트별 허용 목록)
- [ ] **FE**: 프로젝트 설정에서 상태 관리 UI (추가/수정/삭제/재정렬)
- [ ] **FE**: 보드/리스트 등 모든 뷰에서 커스텀 상태 반영

### 6-2. 반복 태스크
- [ ] **BE**: Issue에 `recurrence_rule` 필드 (cron 또는 rrule 형식)
- [ ] **BE**: 반복 생성 로직 (스케줄러 또는 API 호출 시 체크)
- [ ] **FE**: 태스크 상세에서 반복 설정 UI (매일/매주/매월/커스텀)

### 6-3. 태스크 템플릿
- [ ] **BE**: `pms_task_templates` 모델 (project_id, name, default fields, checklist items)
- [ ] **BE**: 템플릿 CRUD 엔드포인트 + 템플릿에서 이슈 생성
- [ ] **FE**: 템플릿 관리 UI + NewTaskModal에서 템플릿 선택

### 6-4. @멘션
- [ ] **BE**: 코멘트 body에서 `@user_id` 파싱 → 알림 생성
- [ ] **FE**: 코멘트 에디터에 멘션 자동완성 (팀원 목록)

### 6-5. 태스크 의존성 시각화
- [ ] **FE**: 간트 차트에서 의존성 화살표 렌더링
- [ ] **FE**: 태스크 상세에서 의존성 추가/삭제 UI (이미 API 있음)

### 6-6. 커스텀 필드
- [ ] **BE**: `pms_custom_fields` 모델 (project_id, name, type: text/number/date/select)
- [ ] **BE**: `pms_custom_field_values` 모델 (issue_id, field_id, value)
- [ ] **BE**: CRUD 엔드포인트 + 이슈 직렬화에 포함
- [ ] **FE**: 프로젝트 설정에서 필드 관리 + 태스크 상세에서 값 입력

### 6-7. 다중 담당자
- [ ] **BE**: `pms_issue_assignees` junction 테이블 (issue_id, user_id)
- [ ] **BE**: 기존 `assignee_id` → 다중 관계로 마이그레이션
- [ ] **FE**: 태스크 상세/필터에서 다중 담당자 선택

### 6-8. 내보내기
- [ ] **BE**: `GET /projects/{id}/export?format=csv` 엔드포인트
- [ ] **FE**: 프로젝트 메뉴에 "Export CSV" 버튼

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
