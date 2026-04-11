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

- [ ] issue payload의 `project_id` 등 내부 필드명을 `list_id` 계열로 정리
- [x] Folder 정렬/이동 UI 추가
- [x] Space 권한을 프로젝트 fallback 없이 완전한 Space ACL로 정리
  - 2026-04-11 PR1 라운드 7 에서 `ProjectMember` 좀비 테이블 완전 제거
  - `list_project_members` / `add_project_member` 라우터는 호환용 alias 로 유지하되 응답/요청 모델을 `SpaceMemberItem` 으로 교체
  - `meeting.ensure_issue_readable` 가 `_ensure_space_access` + `resolve_team_role` 패턴으로 재작성
  - SpaceMembersModal (Linear 스타일) 신규 — 사이드바 우클릭 / CreateSpaceModal 생성 시점에서 진입
  - Alembic 마이그레이션 `6b21fc0a74c8_drop_pms_project_members` 로 테이블 DROP, 원격 dev DB 적용 완료
  - 관련 commit: `98a4700`, `742672c`, `06bd0a1`, `8d2f297`
- [ ] Space Docs 페이지 이동/드래그 정렬 UX 개선
- [x] Admin Console / Workspace Settings 공용 workspace 멤버 관리 UI 추가
- [ ] `/w/:workspaceSlug/<app>` 기반 workspace shell 수동 QA
- [ ] web typecheck 잔재 7건 정리
- [ ] meeting `datetime.utcnow()` deprecation warning 제거

## 검증

- [x] `cd apps/api && uv run --python 3.12 --group dev pytest`
  - 75 passed, 2 warnings (2026-04-11)
- [x] `cd apps/api && uv run --python 3.12 alembic current`
  - `2d4f6c9ab1ef (head)`
- [x] `cd apps/api && uv run --python 3.12 alembic check`
  - drift 0
- [ ] `pnpm nx typecheck web`
  - 기존 오류 7건 남아 있음
