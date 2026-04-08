# PMS 구현 계획

## 이전 완료 (Phase 1~6)

PMSView 실제 API 연결, 서브태스크, 라벨 CRUD, 첨부파일(MinIO), 인앱 알림, mock 정리 모두 완료.
상세 이력은 git log 참조: `ebb9cd8` ~ `b180f5d`

---

## Tier 1: ClickUp 핵심 기능 추가 ✅ 완료

### Phase 1: Checklist (체크리스트) ✅

이슈 내부에 서브태스크보다 가벼운 체크리스트 항목 관리. 카드에 "3/5" 진행률 표시.

**Backend**
- [x] `ChecklistItem` 모델 (id, issue_id FK, text, completed, sort_order, created_at)
- [x] Issue에 `checklist_items` relationship 추가
- [x] 4개 엔드포인트: POST create, PATCH update, DELETE, PATCH reorder
- [x] `_serialize_issue()`에 `checklist_total`, `checklist_done` 추가
- [x] `IssueDetailResponse`에 `checklist_items` 추가

**Frontend**
- [x] `pms-api.ts`: PmsChecklistItem 타입 + CRUD 함수 3개
- [x] `TaskDetail.tsx`: Description~Subtasks 사이 Checklist 섹션
- [x] `ListView/BoardView/TableView`: checklist badge ("3/5")

---

### Phase 2: Advanced Filters (고급 필터 + 저장) ✅

다중 조건 필터 패널 + localStorage 프리셋 저장.

**Backend**
- [x] `list_issues`에 `due_date_from/to`, `start_date_from/to` 파라미터 추가

**Frontend**
- [x] `FilterBar.tsx` (신규): Status/Priority/Assignee/Label/Milestone/DateRange 드롭다운
- [x] 활성 필터 pill + Clear all + Save/Load filter (localStorage)
- [x] `PMSView.tsx`: searchQuery → FilterParams 교체, FilterBar 렌더링

---

### Phase 3: Bulk Operations (일괄 작업) ✅

다중 선택 → 일괄 상태/우선순위/담당자/라벨 변경, 삭제.

**Backend**
- [x] `PATCH /projects/{project_id}/issues/bulk` 엔드포인트

**Frontend**
- [x] `BulkActionBar.tsx` (신규): 하단 플로팅 바
- [x] `PMSView.tsx`: selectedIssueIds 상태
- [x] `ListView/TableView`: checkbox 컬럼, `BoardView`: hover checkbox

---

### Phase 4: Time Tracking (시간 추적) ✅

작업별 예상 시간 + 실제 투입 시간 기록.

**Backend**
- [x] `TimeEntry` 모델 + Issue에 `estimate_hours` 컬럼
- [x] `db.py` schema compat 업데이트
- [x] 3개 엔드포인트: POST create, PATCH update, DELETE

**Frontend**
- [x] `pms-api.ts`: PmsTimeEntry 타입 + CRUD 함수 3개
- [x] `TaskDetail.tsx`: Time Tracking 섹션 (예상/실제/진행률)
- [x] `ListView/BoardView/TableView`: time badge
