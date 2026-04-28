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
  - 2026-04-15 `pms_task_lists.sort_order` 추가, 이후 2026-04-20 canonical docs reset로 space docs 정렬은 `docs_doc_containers.sort_order` 로 이관 (migration `e1f2a3b4c5d6`)
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
- [x] `/w/:workspaceSlug/<app>` 기반 workspace shell 수동 QA
  - 2026-04-17 Playwright MCP 로 `hq-admin` + `innovation-lab-admin` 시드 계정 스윕 완료
  - 검증 통과: `/w/hq/{home,ai,pms,docs,planner,meeting}` 전 경로 0 콘솔 에러, `/w/innovation-lab/{home,meeting,settings}` 동일 패턴 확인, WorkspaceSwitcher 가 사용자 멤버십 워크스페이스만 노출, AppBar 크로스 앱 네비게이션 시 워크스페이스 컨텍스트 유지, 바깥 워크스페이스 직접 URL (`/w/delivery-hub/pms`) → AccessDeniedView, 존재하지 않는 slug (`/w/does-not-exist/home` + bare `/w/does-not-exist`) → AccessDeniedView, bare `/w/:slug` → `/w/:slug/home` 리다이렉트
  - 발견 사항 후속 처리 (2026-04-17):
    - **Platform Admin dead-end (해결 확인)**: 실제로는 이미 `resolveRootEntryPath` ([workspace-utils.ts:179-190](apps/web/src/domains/workspaces/workspace-utils.ts#L179-L190)) 가 워크스페이스 없는 admin 을 `/admin/general` 로 리다이렉트하도록 구현되어 있음. QA 에서 `/w/hq/home` 직접 URL 진입만 테스트해서 WorkspaceGate 차단을 dead-end 로 오해한 것. Playwright 로 Platform Admin HOME 클릭 플로 재확인 → `/` → `/admin/general` 정상 리다이렉트. 별도 수정 불필요
    - **AppBar 알림 폴링 403 노이즈 (수정)**: `getUnreadNotificationCount(token, workspaceSlug?)` 시그니처로 slug 파라미터 추가 ([pms-api.ts:950-961](apps/web/src/domains/pms/pms-api.ts#L950-L961)). AppBar useEffect 가 `shellWorkspaceSlug` 를 명시적으로 전달하고 null 이면 폴링 자체 스킵 ([AppBar.tsx:88-117](apps/web/src/components/layout/AppBar.tsx#L88-L117)). 효과: URL 이 접근 권한 없는 워크스페이스여도 폴링은 사용자가 속한 shell 워크스페이스로 발사 → 403 사라짐. Platform Admin (워크스페이스 0개) 는 폴링 자체 스킵. AppBar.spec.tsx 어서션 하나 업데이트. 회귀 검증: typecheck 0건, vitest 8 passed (AppBar spec), Playwright 로 innovation-lab-admin 이 `/w/hq/home` 및 `/w/delivery-hub/pms` 진입 시 콘솔 에러 0건 확인
  - 회귀: `pnpm nx typecheck web` 0건 (cache), vitest 70 passed + PlannerView 1건 기존 실패 (쓴 변경 무관), pytest 130 passed
- [x] web typecheck 잔재 7건 정리 (2026-04-14 확인, 이미 해결된 상태)
- [x] meeting `datetime.utcnow()` deprecation warning 제거 (2026-04-14 확인, 전 도메인 `_utcnow()` / `utcnow_naive()` 헬퍼로 이미 전환 완료)
- [x] Home을 워크스페이스 스코프로 전환 (`/w/:slug/home`)
  - 2026-04-17 `WorkspaceAppId` 유니온에 `home` 추가, `WORKSPACE_APP_PATH_PATTERN` 확장, `app-shell.ts` 가 `/w/:slug/home` 을 `activeAppId='home'` 으로 매핑
  - `/` → `resolveShellWorkspaceSlug` 기반 `/w/{last}/home` 리다이렉트, bare `/w/:slug` → `/w/:slug/home`, WorkspaceGate 에서 멤버십 체크
  - 신규 `apps/web/src/components/views/WorkspaceHomeView/WorkspaceHomeView.tsx` — Greeting + 한국 공휴일 배너, Quick Actions (새 회의 / 새 태스크 / 새 Doc), 오늘의 회의 (`listMeetings scope=upcoming` 필터링), 내 태스크 (신규 `listAssignedIssues`), 최근 Docs (`listRecentPages`)
  - 신규 백엔드 엔드포인트 `GET /api/v1/pms/issues/assigned?limit=10` — `_accessible_task_lists_query` 기반 워크스페이스 스코프, 본인 assignee 이면서 non-archived + non-closed, due_date ASC → updated_at DESC 정렬
  - MeetingView 가 `?create=1` 쿼리 파라미터로 create 모달 자동 오픈 + URL 정리 (replace)
  - SubSidebar 는 `activeAppId === 'home'` 에서 `return null` 로 접힘
  - 기존 `HomeView.tsx` 삭제, `/tool/pms-tasks-assigned` 는 그대로 유지
  - 검증: `pnpm nx typecheck web` 0건, pytest 130 passed (신규 2건 포함), dev E2E (playwright, delivery-hub-admin): `/` → `/w/delivery-hub/home`, Quick Actions "새 회의" → 모달 자동 오픈 + URL 정리, AppBar HOME 왕복 시 워크스페이스 컨텍스트 유지, bare `/w/:slug` → home, `/w/hq/home` (미접근) → AccessDeniedView, 콘솔 에러 0건
  - 설계 문서: [docs/planning/workspace-home-plan.md](docs/planning/workspace-home-plan.md)

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
- [x] dev E2E 스모크 (hq-admin 시드, playwright)
  - `/w/hq/pms` → CreateTaskListModal → List 생성 → NewTaskModal 태스크 생성, `/tool/pms-tasks-assigned`, `/w/hq/meeting`, `/w/hq/docs/:docId` 콘솔 에러 0건 (2026-04-14)
