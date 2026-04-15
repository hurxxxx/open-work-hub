# PMS 안정화 + 협업 워크스페이스 재구조화 현황

## 현재 상태

- PMS IA 재설계와 PR1 meeting 후속 안정화는 main 에 반영됨
- 현재 모델은 **협업 workspace + enabled apps + team(space) membership** 조합
- 실제 앱 경로는 `/w/:workspaceSlug/<app>` 기준이며, Admin Console 과 Workspace Settings 가 같은 workspace 상세 패널을 공유
- 검증 기준 (2026-04-11): backend `75 passed`, Alembic head `2d4f6c9ab1ef`, drift 0, web typecheck 는 기존 오류 7건

## 구현 완료

### Stage 1 안정화
- [x] `viewer` 쓰기 차단
  - 이슈 수정/삭제
  - 코멘트 작성
  - 의존성 추가
  - 첨부 업로드/삭제
  - 체크리스트 생성/수정/삭제/정렬
  - 시간기록 생성/수정/삭제
  - 다중 담당자 변경
- [x] 폴더 CRUD 권한 하드닝
  - Space owner/admin 또는 global admin만 생성/수정/삭제 가능
- [x] Docs 미디어 sync 시그니처 수정
  - project docs create/update/delete 경로 정상화
- [x] nullable issue 필드 explicit `null` clear 지원
  - `assignee_id`
  - `milestone_id`
  - `start_date`
  - `due_date`
  - `recurrence_rule`
  - `parent_id`
- [x] 다중 담당자 API에 프로젝트 멤버십 검증 추가
- [x] 커스텀 상태 slug 불변 처리
  - 생성 시에만 slug 생성
  - 이름 변경 시 기존 이슈 status 값 유지
- [x] 설정 패널에 멤버 역할 변경/멤버 제거 UI 연결

### Stage 2 IA 재설계
- [x] 사용자 라우팅을 `List` 중심으로 전환
  - 메인 경로: `/tool/pms-list-{id}`
  - 레거시 `/tool/pms-project-{id}` → 동일 ID list route redirect
- [x] `Team`을 PMS `Space`로 사용
  - 기본 `Team Space` 자동 보장
  - 기존 `team_id = null` 리스트는 기본 Space로 이관
- [x] 사이드바를 `Space > Folder > List + Docs` 구조로 전환
- [x] `Team Docs` 탭 제거
- [x] Space Docs 실구현
  - 경로: `/tool/pms-space-{space_id}-docs`
  - doc collection + hierarchical page CRUD
  - 실제 BlockEditor 연결
- [x] list-named API alias 추가
  - `/api/v1/pms/lists`
  - `/api/v1/pms/lists/{id}/...`
  - `/api/v1/pms/spaces/{space_id}/lists`
- [x] 프론트 API 레이어를 `lists`/`space docs` 계약으로 전환
- [x] Space 삭제를 휴지통 정책으로 전환
  - `Team.trashed_at` 기반 soft delete
  - 삭제된 Space의 lists/folders/space docs 비노출 처리
  - 기본 `Team Space` 재요청 시 untrash 재사용

### Stage 3 협업 워크스페이스 재구조화
- [x] `workspace_enabled_apps` 테이블 + `docs_native_docs.workspace_id` 마이그레이션
- [x] 5개 workspace seed 체계 확정
  - `hq`
  - `innovation-lab`
  - `knowledge-base`
  - `planning-desk`
  - `delivery-hub`
- [x] 앱 shell 을 `/w/:workspaceSlug/{ai|pms|docs|planner|meeting}` 경로로 통일
- [x] AppBar/SubSidebar/workspace-utils 가 현재 workspace slug + enabled apps 기준으로 라우팅
- [x] Workspace role 단순화
  - `member`
  - `admin`
- [x] System role 단순화
  - 사실상 `platform_admin` 중심
- [x] 로그인 화면에서 seed accounts 바로 로그인 노출
- [x] `WorkspaceDetailPanel` 공용화
  - Admin Console
  - Workspace Settings (`/w/:workspaceSlug/settings`)
- [x] Workspace member management UX 확장
  - bulk add picker
  - candidate search
  - paginated drawer
  - near-fullscreen fixed modal

## 제거된 기능

- [x] Automations — 코드·DB 스키마·프론트 API 전체 제거 (불필요)
- [x] Goals / OKR — 코드·DB 스키마·프론트 API 전체 제거 (불필요)

## 호환용 유지

- [x] 내부 저장 구조의 `pms_projects` 테이블 이름
  - 물리 테이블은 유지
  - 사용자 계약과 UI에서는 `List`로 노출
- [x] legacy `/projects` API
  - 기존 클라이언트 호환용 alias로 유지
- [x] project-scoped docs API
  - 기존 데이터 호환용으로 유지
  - 신규 PMS UI는 Space Docs 사용

## 후속 개선 후보

- [x] issue payload의 `project_id` 등 내부 필드명을 `list_id` 계열로 정리
  - 2026-04-14 PMS router.py 전면 리네임: path param, 내부 헬퍼 인자, ORM 속성 접근, 레거시 `/projects/...` 데코레이터 placeholder 까지 `list_id` 로 통일
  - 응답 Pydantic 모델 5종 (`MilestoneItem`, `TaskTemplateItem`, `CustomFieldItem`, `IssueListItem`, `DashboardProjectItem`) 은 `AliasChoices("list_id", "project_id")` 로 입력 호환 유지, 출력은 `list_id`
  - `Issue.list_id` / `Label.list_id` / `ProjectStatus.list_id` 사용처를 `auth/access.py`, `meeting/service.py`, `media/router.py` 에서 정정
  - Dashboard summary 쿼리파라미터를 `list_id` 로 전환, 백엔드는 `project_id` dual-accept
  - 호환용 유지: `pms_projects` 테이블, `Project` ORM 클래스, `project_id = synonym("list_id")`, `/api/v1/pms/projects/...` URL
- [x] Folder 정렬/이동 UI 추가
- [x] Space 권한을 프로젝트 fallback 없이 완전한 Space ACL로 정리
  - 2026-04-11 PR1 라운드 7 에서 `ProjectMember` 좀비 테이블 완전 제거
  - `list_project_members` / `add_project_member` 라우터는 호환용 alias 로 유지하되 응답/요청 모델을 `SpaceMemberItem` 으로 교체
  - `meeting.ensure_issue_readable` 가 `_ensure_space_access` + `resolve_team_role` 패턴으로 재작성
  - SpaceMembersModal (Linear 스타일) 신규 — 사이드바 우클릭 / CreateSpaceModal 생성 시점에서 진입
  - Alembic 마이그레이션 `6b21fc0a74c8_drop_pms_project_members` 로 테이블 DROP, 원격 dev DB 적용 완료
  - 관련 commit: `98a4700`, `742672c`, `06bd0a1`, `8d2f297`
- [x] PMS 사이드바 List + Space Doc DnD (sibling reorder + cross-folder move)
  - 2026-04-15 `pms_task_lists.sort_order` + `pms_space_docs.sort_order` 추가 (migration `7a3c2b9f11e8`, `updated_at DESC` 기반 backfill)
  - Serializer + `PATCH /api/v1/pms/lists/{id}` 가 `sort_order` 와 `folder_id` 동시 업데이트, `sort_by=sort_order` 쿼리 파라미터로 사이드바 stable 정렬
  - 프론트 공용 유틸 [apps/web/src/domains/pms/pms-sidebar-reorder.ts](apps/web/src/domains/pms/pms-sidebar-reorder.ts) — flat list 버전 (sibling + cross-parent move) + 9 vitest 단위
  - `SubSidebar.tsx`: `SortableListLink` 컴포넌트 + space 단위 `DndContext` + optimistic 업데이트 + WIP 권한 게이팅 (canCreateSpaceContent / canManageSpace) 그대로 보존
  - `groupedSpaces` 정렬을 `localeCompare` 에서 `(sort_order, name)` 으로 교체해 드래그 직후 UI 가 즉시 반영되도록 수정
  - 백엔드 regression 2건: `test_task_list_patch_sort_order_and_cross_folder_move`, `test_space_doc_collection_patch_sort_order`
  - E2E (hq-admin, playwright): DnD Alpha 를 folder-내 재정렬 → 새 sort_order 2000 적용, 이후 키보드 DnD 로 다른 folder 의 List 위에 드롭 → `folder_id` 바뀌고 양쪽 부모 sort_order 재번호 확인 (folder A: [Bravo:0, Charlie:1000, List:2000], folder B: [List:0, Alpha:1000])
  - 루트 List/Doc 렌더 구조 개편: `rootItems` (이름순 mixed) → `rootListsOrdered` (sort_order) + `rootDocsOrdered` (sort_order) 두 블록으로 분리. Folder block 이후 하드코딩 순서 (folder → root lists → root docs)
  - Space Doc 사이드바 DnD 추가: `SortableDocLink` 컴포넌트 (rename/menu UX 보존), `handleReorderDoc` optimistic + 롤백, `updateSpaceDoc({ sort_order })` 호출. E2E: Doc Alpha → Doc Charlie 뒤로 이동 확인 (sort_order 4000)
  - 크로스-종류 드롭 차단: `onDragEnd` 가 `active.data.kind === over.data.kind` 체크, 불일치 시 skip
  - 후속: Folder DnD (현재 arrow 메뉴 유지) — 같은 유틸로 추가 가능. Space 최상위 순서는 여전히 글로벌 vs per-user 결정 필요해 범위 외.
- [x] Space Docs 페이지 이동/드래그 정렬 UX 개선
  - 2026-04-15 `@dnd-kit/core` + `sortable` + `utilities` 도입, `DocsView` 트리를 `DocsPageTreeNode` + `DndContext` 로 재작성
  - 순수 유틸 `apps/web/src/domains/docs/docs-page-reorder.ts` (sibling 재번호, 부모 이동, cycle 방지) + 14개 vitest 단위 테스트
  - 기존 `PATCH /api/v1/docs/pages/{id}` 계약 그대로 재사용, optimistic 업데이트 + 실패 시 스냅샷 롤백
  - 백엔드 regression 2건 추가: `test_native_doc_page_patch_reorders_and_moves_parent`, `test_native_doc_page_patch_rejects_cycle` (pytest 101 passed)
  - E2E 확인 (hq-admin seed, playwright): 키보드 DnD 로 Alpha → [Root, Bravo, Charlie, Alpha] 재정렬 확인, 새로고침 후 순서 유지, 부모 이동 + cycle 거부(409) 확인
- [x] Admin Console / Workspace Settings 공용 workspace 멤버 관리 UI 추가
- [ ] `/w/:workspaceSlug/<app>` 기반 workspace shell 수동 QA
- [x] web typecheck 잔재 7건 정리 (2026-04-14 확인, 이미 해결된 상태)
- [x] meeting `datetime.utcnow()` deprecation warning 제거 (2026-04-14 확인, 전 도메인 `_utcnow()` / `utcnow_naive()` 헬퍼로 이미 전환 완료)
- [ ] Home을 워크스페이스 스코프로 전환 (`/w/:slug/home`)
  - 현재 `/`의 전역 HomeView는 더미 데이터이고 앱바 HOME 진입 시 워크스페이스 컨텍스트가 증발함
  - Notion "Jump back in" + Linear "My Issues" + ClickUp Agenda 패턴 차용: Greeting, Quick actions, 오늘 일정, 내 태스크, 최근 작업 5개 위젯
  - 기존 워크스페이스 스코프 엔드포인트(`meeting/meetings?scope=upcoming`, `pms/docs-hub/recent-pages`, PMS assigned issues)만 재사용 — 신규 API 없음
  - `WorkspaceAppId` 유니온에 `'home'` 추가, SubSidebar는 빈 필터 결과에서 접힘, `/` → `/w/{last}/home` 리다이렉트
  - 세부 설계: [docs/planning/workspace-home-plan.md](docs/planning/workspace-home-plan.md)

## 검증

- [x] `cd apps/api && uv run --python 3.12 --group dev pytest`
  - 99 passed, 1 warning (2026-04-14, 리네임 regression 테스트 포함) — 이전 세션의 `test_docs_hub::test_internal_shared_links_require_auth_and_honor_read_vs_edit` 회귀는 `deb4eef feat(docs): harden realtime collaboration stack` 이후 복구 확인
- [x] `cd apps/api && uv run --python 3.12 --group dev alembic current`
  - `3e4983704c82 (head)` (2026-04-14, `rename_pms_list_to_task_list` 적용 후)
- [x] `cd apps/api && uv run --python 3.12 --group dev alembic check`
  - drift 0
- [x] `pnpm nx typecheck web`
  - 에러 0건 (2026-04-14)
- [x] `cd apps/web && pnpm exec vitest run`
  - 8 files, 35 passed (2026-04-14)
- [x] prod-like E2E 스모크 (hq-admin 시드, playwright)
  - `/w/hq/pms` → CreateTaskListModal → List 생성 → NewTaskModal 태스크 생성, `/tool/pms-tasks-assigned`, `/w/hq/meeting`, `/w/hq/docs/:docId` 콘솔 에러 0건 (2026-04-14)
