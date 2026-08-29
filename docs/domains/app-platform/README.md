# App Platform Contract

## Source Of Truth

- [ADR 0011](../../../adr/0011-app-first-workspace-context.md) owns app-first workspace context and runtime control policy.
- `packages/contracts/app-contracts.json` owns executable leaf identity, route context, execution context, resource scope, and launcher placement.
- `packages/contracts/app-contracts.schema.json` validates the source contract.
- `scripts/generate-app-contracts.mjs` generates:
  - `packages/contracts/src/app-contracts.generated.ts`
  - `apps/api/src/open_work_hub_api/core/app_contracts_generated.py`
- Generated files are never hand-edited. Run `pnpm generate:app-contracts` after changing the source contract.

`ai`, `collaboration`, and `business` are display categories only. Do not register them as executable apps, route owners, API owners, runtime availability targets, or AI capability scopes.

## Route Contract

| Context          | Canonical form                               | Workspace bootstrap          |
| ---------------- | -------------------------------------------- | ---------------------------- |
| neutral launcher | `/`                                          | no                           |
| app entry        | `/apps/:appId`                               | no; resolves app-local entry |
| workspace        | `/apps/:appId/workspaces/:workspaceSlug/...` | yes                          |
| global/shared    | `/apps/:appId/...`                           | no                           |

- Use `buildAppHref` in TypeScript and `build_app_href` in Python for internal browser links.
- No legacy aliases, redirects, fallback parsing, or independently assembled browser paths.
- Route scope does not grant access. Server gates recheck membership, role, availability, resource ACL, and AI approval.
- API paths remain under `/api/v1`; they are not browser route aliases.

## Runtime Availability

The compiled leaf catalog provides metadata only. PostgreSQL controls execution and missing rows fail closed.

```text
company enabled
  ├─ platform app -> enabled
  └─ workspace app
       └─ workspace override when present
            otherwise workspace default
```

- `company_app_controls`: required company switch for every app.
- `workspace_app_defaults`: required fallback for workspace apps.
- `workspace_app_overrides`: optional workspace-specific enable/disable; delete the row to inherit.
- Static feature flags and required system roles remain additional gates.
- Catalog defaults, launcher placement, UI hiding, and local storage never authorize execution.
- Admin writes are audited through:
  - `GET/PATCH /api/v1/admin/apps/company-controls`
  - `GET/PATCH /api/v1/admin/apps/workspace-defaults`
  - `GET/PATCH /api/v1/admin/workspaces/{workspace_id}/app-overrides`

## Launch And Workspace Choice

- `GET /api/v1/apps/bootstrap` returns only executable apps for the current user.
- `global_route_app_ids` separately authorizes an app's global/shared routes when its company and role gates pass; it does not make the app launcher-visible without an executable context.
- Platform apps require company enablement and any role/feature gates.
- Workspace apps require at least one active membership where the app is enabled.
- `GET /api/v1/apps/{app_id}/eligible-workspaces` is the app-local chooser source.
- `PUT /api/v1/apps/{app_id}/workspace-preference` persists `(user_id, app_id) -> workspace_id` only after membership and availability checks.
- One eligible workspace auto-selects. Multiple eligible workspaces use an eligible saved preference or show the chooser.
- The global App Bar never stores or implies current workspace. Workspace selection renders in the current workspace app submenu.
- Launcher categories, fixed placement, personal tools, and pins affect presentation only.

## App Bar Presentation

- Static `launcher.placement` declares whether a leaf is fixed, a personal tool, or eligible for a
  company category. `launcher.pinned_by_default` supplies only the initial personal pin default.
- `platform_app_bar_categories` and `platform_app_bar_category_apps` own company category title,
  icon, order, and app membership. Admin manages them through `/api/v1/admin/app-bar-categories`;
  bootstrap filters every item through the current user's executable app catalog.
- `users.app_bar_layout.pinned_app_ids` owns at most eight personal pins. On reads, the server
  removes unknown, fixed, personal-tool, and duplicate IDs; a missing or malformed list falls back
  to compiled pinned defaults. Preference writes reject unknown IDs.
- Category assignment, pinning, ordering, and hiding never create an app identity or authorize a
  route, API, worker, search result, notification, or AI capability.

## Backend Registration

- A domain exports one immutable leaf registration from
  `apps/api/src/open_work_hub_api/domains/<domain>/app_catalog.py`.
- `apps/api/src/open_work_hub_api/domains/auth/workspace_apps.py` is the explicit composition root.
- `compile_workspace_app_registry()` rejects duplicate identity/routes/nav, invalid ownership, and inconsistent route metadata.
- Bootstrap, route/API gates, admin controls, AI discovery/execution, search, and background work consume compiled identity plus runtime availability.
- Executable app-owned user work rechecks availability after claiming the job and before resolving
  providers or mutating app data. A disabled job pauses or cancels according to that queue's
  terminal-state contract. Compensating cleanup may remove orphaned/expired storage after
  disablement but must not publish new user-visible app state.
- Migration-only app ID lists may exist inside Alembic migrations; runtime allowlists outside the registry are forbidden.

## Frontend Registration

- App code stays under `apps/web/src/app-modules/<appId>/`.
- Each leaf exports an `AppModuleManifest` and owns its routes, submenu, and extension registrations.
- An app with no submenu entries returns an empty navigation projection; the platform never invents a root item.
- Settings/admin is a shell-owned navigation surface, not an executable app identity or availability target.
- The shell composition root imports leaf registrations explicitly and derives route, App Bar, document title, mobile navigation, and background projections.
- A workspace app uses the route workspace slug as context. Global/shared routes must not call workspace bootstrap.
- User-facing copy keeps `ko-KR` and `en-US` catalogs aligned.

Cross-app authenticated byte delivery follows [Content Access](../content-access/README.md). Global
source events follow [Notifications](../notifications/README.md); notification rows never replace
source authorization.

## Workspace Keyword Search

Participating apps provide an app-owned `SearchEntityAdapter`, explicit composition in
`apps/api/src/open_work_hub_api/domains/search/default_entity_adapters.py`, lifecycle projection
hooks, source ACL, and disabled/empty/missing-index tests. Search results use the canonical generated
browser route and recheck source access. Retrieval partition is candidate scope, not authorization.

## Change Checklist

- update the source app contract and regenerate both language projections
- update backend leaf registration, route/API gate, admin/runtime availability, and focused tests
- update frontend manifest, app-first routes, submenu selector, launcher projection, and i18n
- update search, notification, share, worker, and AI links/capabilities owned by the app
- regenerate OpenAPI/client when the API contract changes
- add Alembic migration for persisted schema changes
- verify zero/missing-control, disabled, unauthorized, global/shared, one-workspace, multi-workspace, and stale-preference cases

## Checks

```bash
pnpm check:app-contracts
pnpm check:web-architecture
pnpm nx typecheck web
pnpm check:api-architecture
pnpm check:api-contract
pnpm check:i18n
pnpm check:alembic-graph
pnpm test:alembic-graph
(cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/test_app_routes.py tests/test_app_availability.py tests/test_apps_launch_catalog.py tests/test_workspace_app_registry.py tests/test_workspace_bootstrap.py tests/test_admin_workspaces.py -q)
```
