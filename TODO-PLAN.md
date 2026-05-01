# PMS 안정화 + 협업 워크스페이스 재구조화 현황

## 현재 상태

- PMS IA 재설계와 PR1 meeting 후속 안정화는 main 에 반영됨
- 현재 모델은 **협업 workspace + enabled apps + team(space) membership** 조합
- 실제 앱 경로는 `/w/:workspaceSlug/<app>` 기준이며, Admin Console 과 Workspace Settings 가 같은 workspace 상세 패널을 공유
- 검증 기준 (2026-04-11): backend `75 passed`, Alembic head `2d4f6c9ab1ef`, drift 0, web typecheck 는 기존 오류 7건

## 최근 작업 기록

- 2026-05-01 Phase 2 legacy API 제거 + live smoke 강화: workspace context가 필요한 legacy global API mount(`ai`, `documents`, `plm`, `drafts`, `ocr`, `wiki_pms`, `pms`, `meeting`, `calendar`, `planner`)를 제거하고 OpenAPI/types/tests를 workspace-scoped API 기준으로 갱신했다. docs shared-link는 의도된 public route만 `/api/v1/docs/*` 로 보존했고, PMS deprecated list-member/project alias는 계약에서 제거했다. import-linter contract는 domain -> app/main/api_registry 역참조 금지를 추가했다. Web은 주요 app/platform API 타입을 OpenAPI generated schema 기반으로 확장했고, Learning markdown과 AI artifact panel을 lazy split해 route chunk를 줄였다. 신규 `pnpm nx e2e-live-smoke web` 은 실제 local API + dev-login으로 `/w/hq/{home,ai,pms,docs,planner,meeting,learning,settings}`, `/tool/search?workspace=hq`, `/admin/workspaces`, legacy NotFound를 검증한다. 로컬 OpenSearch index 미준비 시 `/search/query` 503은 shell smoke에서 명시적으로 허용한다. 브라우저 검증: `pnpm nx e2e-shell web` 4 passed, `pnpm nx e2e-live-smoke web` 3 passed.
- 2026-05-01 Phase 2 API boundary 후속 마무리: web app/platform API facade 전반을 `apiFetchJson` 기반 공통 JSON client로 맞춰 인증 header/error normalization 중복을 줄였고, `platform/api/types.ts` 에 OpenAPI operation response/request helper type을 추가했다. workspace 검색/RAG E2E 스텁을 보강해 `/tool/search?workspace=hq` smoke가 실제 API 401/로그아웃 흐름에 의존하지 않도록 했으며, `auth.workspace_router` 도 import-linter protected router 목록에 포함했다. route module은 `React.lazy` + `app/shell/lazy-route.tsx` 로 앱별 chunk를 분리하고 `/tool/*` wrapper도 app module public element만 사용하도록 정리했다. `package.json` 의 Nx wrapper는 `env -u NO_COLOR nx` 로 바꿔 FORCE_COLOR/NO_COLOR 경고를 없앴고, Vite chunk warning도 lazy split 이후 기준값에 맞춰 사라졌다. 브라우저 검증: Playwright `pnpm nx e2e-shell web` 4 passed (`/w/hq/{home,ai,pms,docs,planner,meeting,learning,settings}`, `/tool/search`, disabled app, legacy NotFound, admin routes). 전체 검증: `pnpm ci:web` 통과, `pnpm ci:api` 통과 (`663 passed`, `1 skipped`, warnings 3), `git diff --check` 통과.
- 2026-05-01 Phase 2 contract-first API boundary 1차 구현: FastAPI `create_app(initialize_runtime=False)` 경로와 `aidoo_api.api_registry` composition root 를 추가해 OpenAPI export 시 DB/MinIO/LLM 초기화를 건너뛰고 router mount 를 중앙화했다. `scripts/generate-openapi-client.mjs`, `openapi-typescript`, `openapi-fetch`, `apps/web/src/platform/api/openapi.generated.d.ts`, `platform/api/client.ts` 를 추가했고 `generate:api-client`, `check:api-contract`, `check:api-architecture`, `ci:api`, `ci:contract`, `ci:web` 스크립트를 연결했다. web `domains/*` API 진입점은 앱 전용 `app-modules/<appId>/api` 또는 cross-cutting `platform/*` 로 이동했고, 앱 API 공유는 `<appId>/public-api` 로 제한했다. 백엔드는 media reusable helper 를 `media.service` 로 옮기고 docs/pms service 의 router 역참조를 제거했으며, `import-linter` protected contract 로 domain service/module 의 router import 를 차단했다. 후속으로 AI tool/RAG/LLM 테스트 double 과 환경 오염에 취약한 settings 테스트를 정리해 전체 API suite 까지 통과시켰다. 검증: `pnpm generate:api-client`, `pnpm check:api-contract`, `pnpm check:api-architecture`, `pnpm nx typecheck api`, `pnpm nx lint api`, `pnpm nx test api` 663 passed / 1 skipped, `pnpm nx typecheck web`, `pnpm check:web-architecture`, `pnpm nx lint web`, `pnpm nx test web` 41 files / 292 tests, `pnpm nx build web`, `pnpm nx e2e-shell web` 4 passed.
- 2026-05-01 web app boundary 경계 강화 마무리: Planner 전용 `MeetingPreviewModal` 을 `app-modules/planner/views/calendar/` 로 이동해 shared calendar 잔여 결합을 줄였고, shell registry 단위 테스트에 app path/nav owner/sidebar registry 불변식을 추가했다. `WorkspaceGate` 단위 테스트로 enabled app/member 차단 조건을 고정하고, Playwright `e2e-shell` target + `apps/web/e2e/app-boundary-smoke.spec.ts` 를 추가해 `/w/hq/{home,ai,pms,docs,planner,meeting,learning,settings}`, `/tool/search`, disabled app 차단, legacy top-level NotFound, `/admin/{general,workspaces}` 를 실제 브라우저에서 검증한다. `ci:web` 에 architecture/lint/test/build/e2e-shell 을 연결했고, `agents.md` 에 web app boundary 작업 규칙을 추가했다. 검증: `pnpm nx test web -- src/app/shell/app-registry.spec.ts src/app/shell/gates.spec.tsx src/app-modules/planner/views/PlannerView.spec.tsx`, `pnpm nx typecheck web`, `pnpm exec tsc --noEmit -p apps/web/tsconfig.e2e.json`, `pnpm nx architecture web`, `pnpm nx e2e-shell web`, `pnpm ci:web` 통과. `lint` 기존 warning 57, build chunk warning, jsdom `window.scrollTo` noise 는 기존 상태로 남아 있다.
- 2026-04-30 web app boundary 후속 완결: `components/views` 에 남아 있던 AI/Docs/Home/Learning/Meeting/Planner view 를 각 `app-modules/<appId>/views/` 로 이동하고, shell 전용 placeholder/tool view 만 `app/shell/tool-views/` 로 분리했다. `SubSidebar.tsx` 는 `app-sidebar-registry` 기반 delegator 로 축소하고 앱별 sidebar create action/category/extras 는 각 app module public API(`aiSidebarConfig`, `pmsSidebarConfig`, `docsSidebarConfig`, `plannerSidebarConfig`, `meetingSidebarConfig`, `learningSidebarConfig`) 로 노출했다. `components/views/**` import 금지를 ESLint/check script 에 추가했고, web `architecture` Nx target 과 root `ci:web` 스크립트를 추가했다. 검증: `pnpm nx architecture web`, `pnpm nx typecheck web`, `pnpm ci:web` 통과 (`lint` 기존 warning 57, `test` 40 files / 286 tests, `build` 기존 chunk warning 유지). `agent-browser` 실제 브라우저 스모크로 hq-admin 기준 `/w/hq/{home,ai,pms,docs,planner,meeting,learning,settings}`, `/tool/{search,chatbot,docs-all,pms-tasks-assigned,planner-calendar,meeting-upcoming}`, legacy `/meeting|/docs|/pms|/planner|/ai` NotFound 를 확인했고, platform-admin 기준 `/admin/general`, `/admin/workspaces` 렌더링을 확인했다. 모든 경로 final URL + accessibility snapshot + page error + console 확인 결과 신규 에러 없음.
- 2026-04-30 web app boundary 후속 강화: `dependency-cruiser` + `knip` 도입, `check:web-architecture` 스크립트 추가. `dependency-cruiser` 는 app-module private entry(`routes/sidebar/views/...`) 외부 import 와 web circular dependency 를 차단하고, `knip:web` 은 web unused file/unresolved import 를 점검한다. 이 과정에서 드러난 순환 2종도 제거했다: auth provider/login screen 은 `auth-context.ts` 로 context/useAuth 를 분리했고, AI view/composer 는 shell registry 직접 import 를 끊고 AI manifest nav items 를 route 에서 주입하도록 바꿨다. shell registry/route registry 도 app module root public API 만 import 하도록 정리했다. 검증: `pnpm check:web-architecture`, `pnpm nx lint web`(기존 warning 57), `pnpm nx test web`(40 files, 288 tests), `pnpm nx build web` 통과. build chunk size warning 과 jsdom `window.scrollTo` noise 는 기존 상태로 남아 있다.
- 2026-04-30 실제 브라우저 전체 shell E2E 스모크: 로컬 web `127.0.0.1:4200` + api `127.0.0.1:8000` 재사용, `agent-browser` 로 36개 라우트 순회 완료. 검증 범위: `/`, `/w/hq`, `/w/hq/{home,ai,pms,docs,planner,meeting,learning,settings}`, PMS 하위 `/assigned|/today|/personal`, Learning course/lesson 4개, `/tool/{search,chatbot,docs-all,pms-tasks-assigned,planner-calendar,meeting-upcoming,drafting}`, seed PMS space detail, `/admin/{general,people,workspaces,security,audit}`, legacy `/meeting|/docs|/pms|/planner|/ai` NotFound. 모든 경로 final URL + accessibility snapshot + page error + console error 확인 결과 PASS 36 / FAIL 0. seed 데이터상 docs detail, meeting detail, PMS list/issue detail 은 대상 ID가 없어 스킵했다. PMS overview 의 Recharts container size warning 2건은 기존 warning 으로 남아 있다.
- 2026-04-30 AI-friendly PMS view module 이동: `components/views/PMSView/*` 전체를 `app-modules/pms/views/` 로 이동하고, PMS routes/sidebar 는 내부 상대 import 를 사용하도록 정리했다. shell 의 `ToolViewWrapper` 는 `@/src/app-modules/pms` public export (`PMSView`) 만 import 한다. ESLint boundary 에 `app-modules/*/views/**` 직접 import 금지를 추가했고, `pnpm check:web-boundaries` 로 alias/상대 경로 기반 cross-app internal import 를 잡는 경량 검사를 추가했다. `pnpm nx lint web`, `pnpm nx test web`, `pnpm nx build web`, `pnpm check:web-boundaries` 통과. `agent-browser` 로 `/w/hq/pms` 와 `/tool/pms-tasks-assigned` 렌더링 및 page error 0건을 확인했다. 콘솔은 기존 PMS chart size warning 2건만 남았다.
- 2026-04-30 AI-friendly PMS sidebar orchestration 분리: `SubSidebar.tsx` 에 남아 있던 PMS fetch/state/mutation/modal orchestration 을 `app-modules/pms/sidebar/PmsSidebarSpaces.tsx` 로 이동하고, shell 은 `PmsSidebarSpaces` public export 만 통해 렌더링하도록 축소했다. `pnpm nx lint web`, `pnpm nx test web`, `pnpm nx build web` 통과. `agent-browser` clean session 으로 `/w/hq/pms` 렌더링, Spaces/Team Space/Personal 노출, page error 0건을 확인했다. 콘솔은 기존 PMS chart size warning 2건만 남았다.
- 2026-04-30 AI-friendly PMS sidebar tree 분리: PMS Space/List/Folder/Doc 트리 렌더러와 DnD popover/helper를 `app-modules/pms/sidebar/SpaceTree.tsx` 로 이동하고, `SubSidebar.tsx` 는 PMS 데이터 orchestration + 공통 shell 위주로 축소했다. `pnpm nx lint web`, `pnpm nx test web`, `pnpm nx build web` 통과. `agent-browser` 로 `/w/hq/pms` sidebar 의 Spaces/Team Space/Personal 렌더링을 확인했다.
- 2026-04-30 AI-friendly sidebar boundary refactor 2차 적용: AI 최근 대화, Docs Favorites/Recent Pages, Learning 목차를 각 `app-modules/{ai,docs,learning}/sidebar.tsx` 로 분리하고 PMS `SpaceOrderEditorModal` 을 `app-modules/pms/sidebar/` 로 이동했다. `agent-browser` smoke 로 `/w/hq/{ai,docs,learning,pms}` 렌더링과 앱별 sidebar 항목 노출을 확인했고, page error 0건이었다.
- 2026-04-30 AI-friendly web app boundary refactor 1차 적용: `apps/web/src/app/` shell, `apps/web/src/app-modules/*` manifests/routes, registry 기반 AppBar/SubSidebar/route composition 으로 이동. `agent-browser` smoke 로 `hq-admin` 기준 `/w/hq/{home,ai,pms,docs,planner,meeting,learning}`, `/tool/search`, legacy `/meeting|/docs|/pms|/planner|/ai` NotFound 를 확인했고, `platform-admin` 기준 `/admin/general` 렌더링도 확인했다. 브라우저 page error 0건, 콘솔은 Vite/React dev 안내와 PMS chart size warning 2건만 확인.

## 다음 세션 핸드오프 (2026-05-01)

### 기준 상태

- 최신 반영 커밋: `f9ff885 refactor API boundaries and remove legacy mounts`
- 브랜치/원격: `main` -> `origin/main` 푸시 완료
- 현재 리팩토링 상태:
  - web app boundary refactor 완료: 앱별 `app-modules/*` 구조, shell registry, sidebar delegator, public API/import boundary 적용
  - Phase 2 contract-first API boundary 완료: FastAPI app factory, OpenAPI codegen, platform API client, app/platform facade 분리, import-linter API boundary 적용
  - legacy workspace API cleanup 완료: workspace context가 필요한 global API mount 제거, `/api/v1/workspaces/{workspace_slug}/...` 기준으로 API/tests/frontend 호출 정리
  - public docs shared-link route만 intentional non-workspace API로 유지
  - PMS deprecated list-member/project alias 제거
  - live smoke target 추가: `pnpm nx e2e-live-smoke web`

### 마지막 검증 결과

- `pnpm generate:api-client` 통과
- `pnpm check:api-contract` 통과
- `pnpm check:web-architecture` 통과
- `pnpm check:api-architecture` 통과
- `pnpm nx lint api` 통과
- `pnpm nx typecheck api` 통과
- `pnpm nx test api` 통과: `664 passed`, `1 skipped`
- `pnpm nx typecheck web` 통과
- `pnpm nx lint web` 통과
- `pnpm nx test web` 통과: `294 passed`
- `pnpm nx build web` 통과, Vite chunk warning 없음
- `pnpm nx e2e-shell web` 통과: `4 passed`
- `pnpm nx e2e-live-smoke web` 통과: `3 passed`
- `pnpm ci:all` 통과
- `git diff --check` 통과

### 다음 권장 작업 순서

1. GitHub Actions 원격 CI 확인
   - 방금 `main`에 푸시된 `f9ff885`가 원격 CI에서도 로컬과 같은 결과인지 먼저 확인한다.
   - 실패가 있으면 새 기능 작업보다 CI 수정이 우선이다.
   - 특히 로컬과 원격의 API seed, OpenSearch, browser dependency 차이를 먼저 본다.

2. CI workflow 고정
   - GitHub Actions에 최소 게이트를 명시한다.
   - 권장 필수 게이트: `pnpm ci:all`, `pnpm check:api-contract`, `pnpm check:web-architecture`, `pnpm check:api-architecture`
   - `pnpm nx e2e-shell web`은 PR/main 필수 smoke로 유지한다.
   - `pnpm nx e2e-live-smoke web`은 local API/seed/OpenSearch 상태 의존성이 있으므로 처음에는 manual 또는 nightly workflow로 분리하는 편이 안전하다.

3. OpenAPI 계약 품질 개선
   - FastAPI route의 `operation_id`, request/response schema, error schema를 정리한다.
   - generated type 이름이 안정적으로 나오도록 중복/익명 schema를 줄인다.
   - frontend facade에서 남은 hand-written API 타입을 더 줄이고, UI-only view model과 server contract type의 경계를 명확히 한다.
   - raw `fetch`는 SSE stream, blob/download, direct media playback처럼 JSON client가 맞지 않는 경우에만 남긴다.

4. Backend domain boundary v3
   - 현재는 router 역참조, app/main/api_registry 역참조, legacy mount를 끊은 상태다.
   - 다음은 cross-domain service 직접 호출을 줄이는 단계다.
   - 필요한 협업은 domain service끼리 직접 물리는 대신 application service 또는 명확한 read model/helper 경계로 올린다.
   - import-linter contract를 확장할 때는 기존 테스트 double/seed 흐름이 깨지지 않는지 함께 본다.

5. 실제 UX 회귀 검증 강화
   - Playwright smoke는 shell routing 중심이다. 다음 세션에서는 실제 사용자 플로우를 `agent-browser`로 한 단계 더 깊게 확인한다.
   - 우선순위:
     - docs 생성/편집/shared-link 접근
     - meeting 생성/녹음/전사/문서 연결
     - PMS task 생성/이동/담당자 변경
     - AI chat stream 및 artifact panel
     - `/tool/search?workspace=hq` 검색 결과와 OpenSearch 준비 상태
   - 브라우저 기반 점검을 수행하면 이 파일의 최근 작업 기록에 final URL, accessibility snapshot, console/page error 결과를 남긴다.

6. 성능/번들 후속
   - AIView와 LearningCourseView chunk는 크게 줄었다.
   - main chunk는 아직 큰 편이므로 다음 후보는 shell-level provider, editor dependency, admin/settings route split이다.
   - 단, chunk split은 behavior 안정화 이후에 작게 진행한다.

### 주의할 점

- DB schema migration은 이번 리팩토링 범위에 없었다. API surface cleanup만 수행했다.
- 숨은 legacy 클라이언트가 `/api/v1/{ai,pms,docs,meeting,planner,...}` global path를 호출하면 실패하는 것이 의도된 상태다.
- docs shared-link처럼 의도적으로 workspace가 없는 public route는 `/api/v1/docs/*`에 남아 있다.
- local OpenSearch index가 준비되지 않은 환경에서는 `/api/v1/workspaces/hq/search/query`가 `503`을 낼 수 있다. live smoke에서는 shell routing 회귀와 구분하기 위해 이 경우만 명시적으로 허용한다.
- 새 에이전트 지시 파일(`AGENTS.md`, `CLAUDE.md`, `.codex/`, `.claude/`)은 만들지 않는다. 활성 규칙은 루트 `agents.md`만 사용한다.

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
- [x] 실제 브라우저 Phase 3 smoke (2026-05-01, agent-browser)
  - `Aidoo HQ Admin`: `/w/hq/{home,ai,pms,docs,planner,meeting,learning,settings}`, `/tool/search?workspace=hq`, legacy `/meeting` NotFound 확인, 콘솔/페이지 오류 0건
  - `Platform Admin`: `/admin/workspaces` 관리자 화면 렌더 확인, 콘솔/페이지 오류 0건
- [x] Phase 3 API facade 타입 경계 강화 (2026-05-01)
  - `auth`, `workspaces`, `meeting`, `pms` facade의 주요 request/response 타입을 `openapi.generated.d.ts` schema alias 기반으로 전환
  - 검증: `pnpm ci:web` 통과 (OpenAPI drift check, web architecture, typecheck, lint, test, build, e2e-shell)
