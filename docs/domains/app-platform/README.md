# App Platform Contract

## Model

1. App-owned descriptor/manifest declares identity and contract.
2. Platform composition root imports registration objects explicitly.
3. Registry compiler derives bootstrap, nav, routes, launcher, background work, search/guide projections and rejects duplicates/owner mismatch.

Do not add app ID string allowlists, section lists, or platform branches outside registry output.

## Scope

- Top tenant = company deployment/database/settings bundle. See [ADR 0007](../../../adr/0007-company-tenant-workspace-scope.md).
- Workspace = collaboration/data/access scope below company.
- `availability_scope`: `workspace` or `platform`.
- `resourceScope`: `workspace`, `company`, `personal`, `hybrid`.
- Route context and execution principal are separate from availability/resource ownership.
- Workspace route uses `/w/:workspaceSlug/...`; slug is locator, not auth.
- Server rechecks membership, RBAC, resource ACL, entitlement, and platform visibility at execution.
- Launcher categories/pins are display only.

## Backend Registration

- Domain exports immutable `WorkspaceAppRegistration` from `domains/<domain>/app_catalog.py`.
- Add it to `domains/auth/workspace_apps.py` composition tuple.
- `compile_workspace_app_registry()` validates ID/route/nav uniqueness, owner links, launcher policy, and derived projections.
- Bootstrap, entitlement, admin app list, router gates, and fixed/default-pin projections consume compiled catalog.
- Removed legacy fields stay removed: `launcher_section`, `launcher_sections`, `parent_app_id`, `feature_app_id`, entitlement `enabled`.
- Migration-only ID mappings stay inside Alembic migrations.

## Launcher

- `launcher_category` = eligible for DB-managed launcher category, not a named section.
- DB owns category title/icon/order/app placement.
- `launcher_fixed` and `launcher_pinned_by_default` describe app launcher policy only.
- `launcher_personal_tools=True` is for platform + personal apps in fixed personal tools launcher. It requires `launcher_category=False`.
- Empty personal tools launcher is hidden.
- Admin screens:
  - `/admin/apps/platform`: platform apps and personal tools
  - `/admin/apps/workspace`: workspace apps
  - `/admin/apps/app-bar`: category layout only

## Frontend Registration

- App identity lives in `apps/web/src/app-modules/<moduleId>/`.
- Top-level app exports `AppModuleManifest` and app-local registration.
- Child tool exports `FeatureModuleManifest`/registration from its own module.
- Parent composition root includes child registration; shell registry compiles all app/feature projections.
- Caller does not pass app ID into nav/background inputs; compiler injects owner from manifest and rejects mismatch.
- Derived projections are not edited as ID lists: manifests, AI tool app IDs, guide sources, nav, routes, App Bar, tool views.
- AI tool entry is declared by `manifest.surfaces.aiToolEntry`.
- Workspace keyword search is backend-owned, not frontend manifest-owned.

## Workspace Keyword Search

Participating app must provide:

- app-owned `SearchEntityAdapter` in domain `search_projection.py`
- `owner_app`, `entity_type`, `resource_type`, locale `label_key`, fallback `label`
- workspace/single-document loader and create/update/delete lifecycle hooks
- explicit composition in `domains/search/default_entity_adapters.py`
- Source ACL adapter, keyword ACL branch, hook tests, projection/ACL/disabled/empty/missing-index tests
- bootstrap projection through `keyword_search.entity_types`
- backfill plan before production exposure

Do not use runtime scans, frontend flags, app ID allowlists, or direct low-level registry calls.

## New App Checklist

- backend app catalog and composition
- server entitlement/access gate, bootstrap, icon/i18n
- frontend manifest/registration and shell composition
- workspace API prefix, OpenAPI/generated client, RBAC/data scope
- worker/AI extension points if used
- duplicate/unknown-owner/identity-injection negative tests
- keyword search: `none - reason` or adapter/ACL/projection/hook/backfill/rollback evidence
- incomplete scaffold defaults: `enabled_by_default=False`, `visible_by_default=False`

## Remove App Checklist

- backend catalog/router/gates/AI/worker registrations
- frontend manifest/route/API/help/i18n/tests
- entitlements, visibility, launcher category, pins, app tables
- workload route overrides and AI security scoped to removed app/task
- regenerated OpenAPI/client
- preserve audit/usage history unless retention policy says delete

## Checks

```bash
pnpm check:web-architecture
pnpm nx typecheck web
pnpm check:api-architecture
pnpm check:api-contract
pnpm check:i18n
cd apps/api && uv run --frozen --python 3.12 --group dev python -m pytest tests/test_workspace_app_registry.py tests/test_workspace_bootstrap.py tests/test_admin_workspaces.py -q
```

Frontend registry changes also run affected app-registry specs. Exposure changes need browser check for launcher, route, disabled/unauthorized gate, and console errors.
