# 앱 플랫폼 등록 계약

이 문서는 Open ALM 앱의 identity, 등록, 조합, launcher 노출과 tenant/workspace 접근 게이트의
현재 정본이다. 앱 구현 구조와 검증 깊이는
[바이브 코딩 하네스](../../agents/vibe-coding-harness.md)를 함께 따른다.

## 핵심 모델

앱 등록은 다음 세 단계로만 구성한다.

1. **앱 소유 descriptor/manifest**가 identity와 계약을 선언한다.
2. **플랫폼 composition root**가 descriptor/registration 객체를 명시적으로 import해 조합한다.
3. **registry compiler**가 bootstrap, nav, route, launcher, background work, 검색/가이드용
   projection을 만들고 중복·소유권 불일치를 fail-fast로 거부한다.

composition root의 명시적인 객체 목록은 의도된 구조다. 앱을 추가할 때 이 목록을 수정한다.
반면 플랫폼 코드에 앱 ID 문자열만 다시 나열한 `Set`, allowlist, 분기, 별도 section 목록을
두어서는 안 된다. 이런 목록은 manifest와 쉽게 어긋나며 registry compiler를 우회한다.

앱 ID 문자열은 app-owned backend catalog와 frontend manifest에서 각 런타임의 identity로
선언한다. 같은 앱 안의 route/nav 소유권 필드가 그 ID를 참조할 수는 있지만, shell·auth·검색
같은 플랫폼 소비자는 문자열을 재선언하지 않고 등록 객체나 컴파일된 projection을 사용한다.

## Tenant와 앱 scope

Open ALM의 최상위 tenant는 회사이며, 현재는 회사별 배포·데이터베이스·설정 묶음으로 암묵적으로
식별한다. Workspace는 회사 tenant 아래의 부서·팀·프로젝트 협업 범위다. 전체 범위 계약은
[ADR 0007](../../../adr/0007-company-tenant-workspace-scope.md)을 따른다.

App availability(`platform` 또는 `workspace`), resource ownership(`company`, `personal`,
`workspace`, `hybrid`), route context(global 또는 workspace)와 execution principal은 서로 다른
계약이다. `platform` 앱이라는 사실만으로 company resource라고 판단하거나, principal이
`personal`이라는 이유로 모든 데이터가 personal resource라고 판단하지 않는다.

Workspace 앱의 canonical route에는 `/w/:workspaceSlug/...`를 사용한다. slug는 대상 workspace를
찾는 locator이며 권한 증거가 아니다. 서버는 membership, RBAC, resource ACL과 entitlement를
실행 시점에 검사한다. Global 앱은 canonical route에서 workspace slug를 생략하지만 인증과
platform visibility hard gate를 그대로 적용한다.

Launcher category, 정렬과 개인 pin은 표시 구성일 뿐 앱 접근 권한을 부여하지 않는다. 사용자·조직·
팀별 audience targeting은 현재 app-platform 계약에 포함하지 않으며 별도 결정이 필요하다.

## Backend 등록

앱을 소유한 API domain은 `apps/api/src/open_alm_api/domains/<domain>/app_catalog.py`에서
불변 `WorkspaceAppRegistration`을 내보낸다.

```python
MY_APP = WorkspaceAppRegistration(
    app_id="my-app",
    title="My App",
    route_base="/my-app",
    icon_key="box",
    # 미완성 scaffold는 아래 기본값을 유지한다.
    enabled_by_default=False,
    visible_by_default=False,
    launcher_category=False,
)
```

앱 등록은 데이터 소유권과 별개로 availability scope를 선언한다.

- `availability_scope="workspace"`: workspace bootstrap과 workspace entitlement가 활성화를 결정한다.
- `availability_scope="platform"`: `/api/v1/apps/bootstrap`과 platform visibility가 활성화를 결정한다.

Frontend manifest의 `resourceScope`는 데이터 소유권을 나타낸다. 현재 값은 `workspace`,
`company`, `personal`, `hybrid`이며, `personal`은 인증 사용자 본인 소유 데이터를 뜻한다.
따라서 platform availability인 Community는 company resource이고, Mail·Planner는 personal
resource다. availability scope와 resource scope를 같은 개념으로 취급하지 않는다.

Core Enablement 단계에서 이 객체를
`apps/api/src/open_alm_api/domains/auth/workspace_apps.py`의 조합 tuple에 import한다.
`compile_workspace_app_registry()`는 다음 값을 검증하고 파생한다.

- kebab-case app/nav ID와 workspace route base
- app ID, route base, nav ID의 전역 중복
- nav가 가리키는 `link_app_id`의 존재 여부
- fixed/category/default-pin launcher 정책의 일관성
- app identity가 주입된 nav catalog
- `WORKSPACE_APP_CATALOG`, `WORKSPACE_APP_IDS`, fixed/default-pin projection

bootstrap, entitlement, 접근 게이트, 관리자 앱 목록은 이 컴파일된 catalog를 소비한다.
도메인 router의 앱 접근 검사도 app-owned registration의 `app_id`를 사용한다. auth/core에
도메인 앱 ID 상수나 별도 allowlist를 추가하지 않는다.

`launcher_section`, `launcher_sections`, `parent_app_id`, `feature_app_id` 같은 과거 호환 필드는
runtime 등록이나 bootstrap DTO에 다시 추가하지 않는다. workspace entitlement는 현재
`visibility_override` 계약을 따르며 제거된 `enabled` 호환 필드를 복원하지 않는다. 과거 데이터
이관에만 필요한 ID 매핑은 해당 Alembic migration 안에 한정한다.

## Launcher category와 앱 등록의 구분

`WorkspaceAppRegistration.launcher_category`는 특정 `ai`, `collaboration`, `business` 섹션의
이름이 아니다. 관리자가 편집하는 category에 배치할 수 있는 앱인지 나타내는 eligibility
flag다. `launcher_fixed`와 `launcher_pinned_by_default`도 앱 자체의 launcher 정책만 선언한다.

실제 category의 제목, 아이콘, 순서, 앱 배치 순서는 DB의 `platform_app_bar_categories`와
연결 테이블이 소유한다. API는 entitlement와 feature flag를 적용한 뒤 이를 bootstrap의
`app_bar_categories`로 투영한다. 따라서 다음을 구분한다.

- 앱을 등록하거나 활성화하는 일: app catalog, composition, entitlement/bootstrap 계약
- launcher 표시 그룹을 편집하는 일: 관리자 DB category와 그 layout
- 앱 내부 sidebar의 `nav_items.category`: 해당 앱 안의 도구 표시 그룹

DB category에 앱 ID를 넣는 것만으로 미등록 앱이 생기거나 접근 권한이 부여되지는 않는다.
반대로 플랫폼에 하드코딩된 `ai`/`collaboration`/`business` section을 만들어 DB category를
대체하지 않는다.

`launcher_personal_tools=True`는 platform availability이면서 personal resource인 앱을
고정 `개인 도구` 런처에 넣는다. 이 앱은 `launcher_category=False`여야 하며 DB category,
즐겨찾기 pin, 앱바 편집 대상에 포함되지 않는다. 활성화된 personal tool이 하나도 없으면
고정 런처도 표시하지 않는다. Mail과 Planner가 이 계약을 사용한다.

Global bootstrap은 인증 사용자에게 선택된 workspace 없이도 다음을 제공한다.

- `GET /api/v1/apps/bootstrap`
- 활성 platform app과 일반 global category projection
- 활성 personal tool 목록
- `scope="personal"`, `workspace_id=null`인 caller principal

workspace bootstrap은 workspace availability 앱만 소유한다. Global route/API/worker/AI tool은
UI 노출과 별개로 platform visibility를 실행 시점에 다시 검사해야 한다.

### 현재 global 앱 승격 적용

뉴스·리포트(`news`)는 이 계약을 처음 적용한 platform 앱이다. Canonical route는 `/news`이며,
기존 `/w/:workspaceSlug/news`는 query와 hash를 보존해 canonical route로 이동하는 호환 alias다.
회사 공용 피드와 사용자별 스크랩을 함께 다루므로 frontend `resourceScope`는 `hybrid`다.

News visibility는 global bootstrap에서 제공하고, UI route뿐 아니라 News·Industry Report API,
관리자 수동 batch, API dispatch와 worker 실행 직전에도 같은 platform hard gate를 적용한다. 기존
AI curation workload identity인 `news_curate`는 유지한다.

사내 관리팀 Q&A(`qa-assistant`)도 platform availability 앱이다. Canonical route는
`/qa-assistant`이고 데이터와 RAG corpus는 계속 company scope를 사용한다. 인증 사용자는 활성화된
Q&A를 조회·질문할 수 있고, 문서 및 동기화 mutation은 기존 관리자 권한을 유지한다. `/api/v1/qna`,
관리자 수동 batch, API dispatch와 worker의 외부 provider 호출 직전에 같은 platform hard gate를
적용한다.

웹 검색, 논문·기술동향, 규격·법규 모니터링 등 나머지 AI 앱은 이번 승격 범위에 포함하지 않는다.
이 앱들은 별도 결정 전까지 현재 availability와 route 계약을 유지한다.

관리 UI는 `/admin/apps/platform`에서 platform 앱과 개인 도구를 관리하고,
`/admin/apps/workspace`에서 workspace 앱을 관리한다. Workspace 앱 화면의 `앱 기본 설정` 탭은
모든 workspace가 상속하는 platform visibility 기본값을, `워크스페이스 앱 설정` 탭은 선택한
workspace의 visibility override를 다룬다. `/admin/apps/app-bar`는 category layout만 관리한다.

## Frontend 등록

Frontend identity와 계약은 `apps/web/src/app-modules/<moduleId>/`가 소유한다.

App Bar 항목과 자체 shell을 소유하는 상위 앱은 `AppModuleManifest`와 app-local module
registration을 내보낸다. `apps/web/src/app/shell/app-module-manifests.ts`의
`DEFAULT_APP_MODULES`는 이 registration 객체를 조합한다.

상위 앱 아래에 노출되는 독립 도구는 `FeatureModuleManifest`를 사용한다.

1. app-local `manifest.ts`에서 `defineFeatureModule()`로 `moduleId`와 contract를 선언한다.
2. nav/tool/route/background work가 있으면 `defineFeatureModuleRegistration()`으로 manifest와
   함께 묶는다.
3. 소유 상위 앱의 composition root(예: Business의 `businessFeatureModules`)에 registration을
   추가한다.
4. shell의 `DEFAULT_FEATURE_MODULES`가 상위 composition을 포함한 입력을 조합하고,
   `app-registry.ts`가 전체 feature registry를 컴파일한다.

Feature registration의 shell nav와 background work source에는 app ID를 다시 적지 않는다.
`compileFeatureModuleRegistry()`가 `manifest.moduleId`를 nav, canonical workspace route,
tool route와 background work source에 주입한다. App module의 core registry도 background work
source 입력에서 `appId`를 받지 않고 `manifest.appBarItem.id`를 주입한다. 호출자가 `appId`를
명시하거나 manifest와 다른 소유자를 선언하면 부팅 시 오류로 처리한다.

다음 값은 registry의 **파생 projection**이다. 앱 추가를 위해 ID 목록처럼 직접 편집하지 않는다.

- `DEFAULT_APP_MODULE_MANIFESTS`
- `DEFAULT_FEATURE_MODULE_MANIFESTS`
- `WORKSPACE_AI_TOOL_APP_IDS`
- background work/feature-guide source 목록
- nav, App Bar item, route와 tool-view registry

AI 도구 여부는 `manifest.surfaces.aiToolEntry`에서 선언한다. Workspace keyword search는
Frontend manifest가 아니라 Backend의 app-owned `SearchEntityAdapter`가 정본이다.

### Workspace keyword search 참여

검색에 참여하지 않는 앱은 아무 등록도 하지 않는다. 참여하는 앱은 다음 계약을 모두 지킨다.

1. `domains/<domain>/search_projection.py`에 canonical `owner_app` registration, `entity_type`,
   `resource_type`, locale에 등록된 `label_key`, fallback `label`, workspace/single-document
   loader와 create/update/delete별 `SearchIndexLifecycleHooks`를 가진
   `SearchEntityAdapter` 상수를 둔다.
2. `domains/search/default_entity_adapters.py`의 명시적 composition root에 상수를 추가한다.
   런타임 파일 스캔, Frontend source flag, app ID allowlist는 만들지 않는다.
3. resource type의 Source ACL Adapter와 keyword ACL branch, create/update/delete index hook,
   projection/ACL/disabled-app/empty-index/missing-index 테스트를 함께 둔다. Loader와 hook
   callable은 owner app domain 아래에 있어야 하며 ACL clause field는 실제 OpenSearch mapping에
   존재해야 한다.
4. Workspace bootstrap의 `keyword_search.entity_types`가 활성 앱에 허용된 entity를 투영한다.
   App Bar, route gate, 검색 filter는 이 배열만 소비한다.
5. 배포 전에 등록된 전체 entity를 백필한다. 앱 비활성화는 index를 삭제하지 않으며,
   재활성화는 기존 index를 재사용한다.

`SearchEntityAdapter` 선언을 다른 파일에 두거나 저수준 descriptor/projection registry를 앱에서
직접 호출하면 하네스가 실패한다. Search projection/hook/registration 변경은 Core Platform lane과
workspace keyword search MR 증거가 필요하다.

검색 Core Enablement 검증은 `test_platform_adapter_registries.py`,
`test_workspace_keyword_search_registry.py`, `test_search_index_hooks.py`,
`test_search_opensearch_client.py`, `test_workspace_bootstrap.py`와 `pnpm check:api-contract`,
`pnpm check:i18n`을 필수로 포함한다. CRUD integration은 실제 operation 직후에 search processing
assertion helper를 일치하는 `entity_type`과
`lifecycle_operation=<create|update|delete>` 인자로 호출한다. App-platform guard는 composition
누락, 실행 가능한 lifecycle assertion 누락, 지원 locale의 `apps.ai.search` 아래 `label_key`
누락·중복을 실패시킨다.

## 새 앱 추가 체크리스트

Core Enablement가 다음 scaffold를 먼저 준비한다.

- Backend `app_catalog.py` registration과 `workspace_apps.py` composition
- server-side entitlement/access gate, bootstrap projection, icon/i18n 계약
- app/feature manifest와 app-local registration, `DEFAULT_APP_MODULES` 또는
  `DEFAULT_FEATURE_MODULES`로 이어지는 composition
- workspace API prefix, OpenAPI/generated client, RBAC/data scope, worker/AI extension point
- registry의 duplicate/unknown-owner/identity-injection negative test
- keyword search 참여 여부와 `none — reason` 또는 owner/entity/resource/projection/hook/test/ACL/
  backfill/rollback 증거

미완성 scaffold는 `enabled_by_default=False`, `visible_by_default=False`로 독립 배포 가능하게
둔다. 필요한 protected scaffold가 없다면 App Sandbox 작업을 멈추고 core-enablement brief를
작성한다. App Sandbox는 준비된 app-owned 경계 안의 UI, service, migration과 focused test만
구현한다.

앱을 실제 노출할 때는 다음을 함께 확인한다.

- API catalog와 Web manifest가 같은 canonical kebab-case ID와 의도한 route 계약을 쓰는가
- workspace entitlement, platform visibility와 관리자 category layout이 의도대로 투영되는가
- feature flag가 있는 앱의 bootstrap과 server-side gate가 같은 결정을 내리는가
- route/nav/tool/background work가 registry에서 한 소유자에만 등록되는가
- AI/guide 목록이 하드코딩 ID가 아니라 manifest surface에서 파생되는가
- Workspace keyword search가 Backend registry와 bootstrap에서 파생되고 Frontend source flag가 없는가

## 검증

최소 정적·단위 검증은 다음과 같다.

```bash
pnpm check:app-platform-guardrails
pnpm check:web-architecture
pnpm nx typecheck web
pnpm check:api-architecture
cd apps/api && uv run --frozen --python 3.12 --group dev python -m pytest \
  tests/test_workspace_app_registry.py \
  tests/test_workspace_bootstrap.py \
  tests/test_workspace_app_api_gate.py \
  tests/test_admin_workspaces.py -q
```

Frontend registry를 변경했다면 `apps/web/src/app/shell/app-registry.spec.ts`,
`apps/web/src/app/shell/feature-module-registry.spec.ts`와
`packages/core-web/src/app-registry.spec.ts`를 포함한 affected Web test를 실행한다. 실제 노출
변경은 브라우저에서 launcher category, pin, canonical route, disabled/unauthorized gate와 콘솔
오류가 없는지도 확인한다.
