# PMS 기본 기능 완성 — API 연결 + 서브태스크 + 첨부파일 + 라벨 CRUD + 알림

## Context

PMSView는 MOCK_TASKS로 돌아가고, 실제 API 연결이 안 된 상태다. ClickUp "기본" 수준까지 올리려면 mock 제거 외에 서브태스크, 첨부파일, 라벨 관리, 알림이 필요하다.

**이미 완성된 것:** 백엔드 PMS API 17개 엔드포인트, API 클라이언트(`pms-api.ts`), 블록 에디터 컴포넌트
**미사용 코드:** `pms-home.tsx`, `pms-workspace.tsx` (API 연결 검증됨, 라우팅에 미통합)
**새로 필요:** MinIO 파일 업로드 인프라, 서브태스크 모델, 라벨 CRUD, 인앱 알림

---

## 구현 순서

### Phase 1: PMSView → 실제 API 연결 (mock 제거) ✅ 완료

PMSView.tsx에서 `useAuth()` → `token` 획득, `listPmsProjects` / `listProjectIssues` 호출. 하위 뷰를 `PmsIssue[]`로 전환.

**1-1. PMSView.tsx 데이터 계층 전환** ✅
- `MOCK_TASKS`, `Task` import 제거
- `useAuth()` 에서 token 획득
- 프로젝트 목록 + 선택된 프로젝트 이슈 로드
- 로딩/에러 상태 추가
- `PmsIssue[]`를 하위 뷰에 전달

**1-2. 코어 뷰 타입 전환 (ListView, BoardView, TableView)** ✅
- Props: `Task[]` → `PmsIssue[]`
- 필드 매핑: `name→title`, `status→status/status_label`, `assignee→assignee_name`, `dueDate→due_date`(ISO), `comments→comments_count`, `tags→labels.map(l=>l.name)`
- BoardView 드래그: `updateIssue()` 호출하여 상태+board_position 변경

**1-3. TaskDetail 실제 연결** ✅
- Props: `Task` → `PmsIssue`
- `getIssueDetail()` 호출 → 댓글/활동로그 로드
- 설명 저장: `updateIssue(token, id, { description_blocks })`
- 댓글 작성: `createIssueComment()`
- 상태/우선순위/담당자 변경 인라인 편집
- ClickUp 스타일 풀사이즈 모달 + 2컬럼 레이아웃 (좌: 콘텐츠, 우: Activity)

**1-4. NewTaskModal 실제 생성** ✅
- 폼 상태: title, status, priority, assignee_id, due_date, description_blocks
- 제출: `createProjectIssue()` → 목록 갱신 콜백

**1-5. OverviewView 대시보드 연결** ✅
- `getPmsDashboardSummary()` 호출
- 상태별/우선순위별 카운트, 프로젝트 진행률, 최근 활동

**1-6. 필터/개인 뷰 (AssignedToMeView, TodayOverdueView, CalendarView, GanttView)** ✅
- AssignedToMe: 현재 사용자 ID로 필터
- TodayOverdue: ISO due_date 기준 필터
- Calendar: ISO date 파싱
- Gantt: start_date/due_date 기반 바 렌더

---

### Phase 2: 서브태스크 ✅ 완료

이슈 간 부모-자식 관계 추가.

**백엔드:** ✅
- `pms_issues` 테이블에 `parent_id` 컬럼 추가 (self-referencing FK, nullable)
- `IssueCreateRequest`, `IssueUpdateRequest`에 `parent_id` 필드 추가
- `IssueListItem` 응답에 `parent_id`, `subtask_count` 추가
- 이슈 상세에서 subtasks 목록 포함
- `DELETE /issues/{issue_id}` 엔드포인트 추가

**프론트엔드:** ✅
- TaskDetail에 서브태스크 목록 섹션 추가
- 서브태스크 인라인 생성 (제목만 입력)
- 서브태스크 ··· 컨텍스트 메뉴: Unlink / Archive / Delete

---

### Phase 3: 라벨 CRUD ✅ 완료

현재 프로젝트 생성 시 기본 3개만 자동 생성됨. 관리 API 필요.

**백엔드:** ✅
- `GET /projects/{project_id}/labels` — 라벨 목록
- `POST /projects/{project_id}/labels` — 라벨 생성
- `PATCH /labels/{label_id}` — 라벨 수정 (이름, 색상)
- `DELETE /labels/{label_id}` — 라벨 삭제

**프론트엔드:** ✅
- TaskDetail 라벨 피커 (드롭다운으로 토글 선택)
- ProjectSettingsPanel 슬라이드오버에서 라벨 생성/수정/삭제 + 색상 피커

---

### Phase 4: 첨부파일 (MinIO) ✅ 완료

이슈/댓글에 파일 첨부. MinIO를 오브젝트 스토리지로 사용.

**인프라 설정:**
- `.env` MinIO 설정 완료: `minio.lumejs.com`
- `Settings` 클래스에 MinIO 필드 추가
- MinIO 클라이언트 유틸리티 (`core/storage.py`)
- 버킷 자동 생성 (init_db 또는 startup)

**백엔드:**
- `pms_attachments` 테이블: id, issue_id (nullable), comment_id (nullable), filename, content_type, size_bytes, storage_key, uploaded_by_id, created_at
- `POST /issues/{issue_id}/attachments` — presigned URL 발급 또는 직접 업로드
- `GET /attachments/{attachment_id}` — presigned download URL 반환
- `DELETE /attachments/{attachment_id}` — 삭제

**프론트엔드:**
- TaskDetail에 첨부파일 목록/업로드 영역
- 드래그앤드롭 + 클릭 업로드
- 파일 미리보기 (이미지는 썸네일, 나머지는 아이콘+이름)
- 댓글 작성 시 파일 첨부

**수정 파일:**
- `apps/api/src/aidoo_api/core/settings.py` — MinIO 설정 필드
- `apps/api/src/aidoo_api/core/storage.py` — 신규: MinIO 클라이언트
- `apps/api/src/aidoo_api/domains/pms/models.py` — Attachment 모델
- `apps/api/src/aidoo_api/domains/pms/router.py` — 첨부파일 엔드포인트
- `apps/web/src/domains/pms/pms-api.ts` — 업로드/다운로드 함수
- `apps/web/src/components/views/PMSView/TaskDetail.tsx` — 첨부파일 UI

**pip 의존성 추가:** `minio` 패키지

---

### Phase 5: 인앱 알림 ✅ 완료

이슈 변경 시 관련자에게 알림.

**백엔드:**
- `notifications` 테이블: id, user_id, type, title, body, reference_type, reference_id, read, created_at
- 알림 생성 트리거: 이슈 담당자 변경, 멘션, 댓글 추가, 상태 변경
- `GET /notifications` — 내 알림 목록 (페이지네이션)
- `PATCH /notifications/{id}/read` — 읽음 처리
- `PATCH /notifications/read-all` — 전체 읽음
- `GET /notifications/unread-count` — 미읽 개수

**프론트엔드:**
- 상단바에 알림 벨 아이콘 + 미읽 카운트 뱃지
- 알림 드롭다운 패널 (최근 알림 목록)
- 클릭 시 해당 이슈로 이동

**수정 파일:**
- `apps/api/src/aidoo_api/domains/pms/models.py` — Notification 모델 (또는 별도 notifications 도메인)
- `apps/api/src/aidoo_api/domains/pms/router.py` — 알림 엔드포인트
- `apps/web/src/components/layout/` — 알림 벨 UI

---

### Phase 6: 정리 ✅ 완료

- `MOCK_TASKS`, `Task` 타입, `mockData.ts` PMS 관련 mock 제거
- `pms-home.tsx`, `pms-workspace.tsx` — PMSView에 통합됐으므로 삭제
- `types.ts` — Task 타입 전용, 미사용으로 삭제
- `constants.ts`에서 `pms-home` nav item 제거
- 미사용 import 정리

---

## 검증 방법

1. 로그인 → `/pms` → 실제 프로젝트 목록 표시
2. 프로젝트 선택 → List/Board/Table에 실제 이슈 렌더
3. 이슈 클릭 → TaskDetail에서 댓글/활동로그/서브태스크/첨부파일 표시
4. "Create Task" → 실제 생성 → 목록 즉시 반영
5. Board 드래그 → 상태 API 저장 → 새로고침 후 유지
6. 파일 첨부 → MinIO 업로드 → 다운로드 링크 동작
7. 이슈 변경 → 담당자에게 알림 생성 → 벨 아이콘에 카운트
8. `grep -r "MOCK_TASKS" apps/web/` → 0건
