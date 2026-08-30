# ADR 0011: App-First Workspace Context

- Status: Accepted
- Date: 2026-08-28

## Context

A global workspace selection made the entire shell appear workspace-scoped while company and personal apps continued to execute without that workspace. Co-locating both app kinds under the selected workspace created a false scope signal and made authorization, deep links, and navigation semantics diverge.

## Decision

- Executable leaf apps are the only app identities. `ai`, `collaboration`, and `business` are launcher display categories, never executable parents or authorization scopes.
- Canonical browser routes are app-first:
  - neutral launcher: `/`
  - app entry: `/apps/:appId`
  - workspace execution: `/apps/:appId/workspaces/:workspaceSlug/...`
  - global/shared execution: `/apps/:appId/...`
- No legacy browser route, redirect, alias, or inferred global workspace context is retained.
- The App Bar has no workspace selector. Workspace apps render the selector in their app-owned context surface, such as the app submenu or Home header. Platform apps and shared routes do not render or bootstrap workspace context.
- Shell app navigation preserves the route workspace only when the target is also a workspace app enabled in that workspace. This is a resolved link destination, not global workspace state.
- When the target workspace app is unavailable in the route workspace, navigation uses the target app entry resolution and previews its eligible saved or single-workspace destination. Platform apps never inherit route workspace context.
- A workspace slug is a locator, not authorization. The server rechecks active membership, role, app availability, resource ACL, and any AI approval at execution.
- App availability is fail-closed and evaluated in this order:
  1. company control must enable the app;
  2. a workspace app uses its workspace override when present, otherwise its workspace default;
  3. missing company control, workspace default, or required feature setting means disabled.
- Platform apps use only company control plus any system-role or feature requirement. They never consult workspace defaults or overrides.
- The launcher exposes only apps the user can execute: an enabled platform app, or a workspace app with at least one enabled workspace membership. Categories and pins are presentation only.
- Global/shared routes are admitted separately from launcher eligibility: company and role gates still apply, but workspace membership is not required and workspace bootstrap is forbidden.
- Workspace app entry resolution is app-local:
  - zero eligible workspaces: app is unavailable;
  - one eligible workspace: persist it as the app preference and enter it;
  - multiple eligible workspaces: use an eligible saved preference, otherwise show a chooser.
- The saved preference key is `(user_id, app_id)`. Changing workspace inside one app does not change another app.
- Implicit app-to-app continuity does not update a saved preference. Only an explicit chooser or in-app workspace selection updates the target app preference.
- In-app workspace selection enters the target workspace at the app root. Detail identifiers, query parameters, and fragments are not projected across workspace boundaries.
- Internal links, notifications, search/RAG origins, workers, and shares use the generated route contract; producers do not assemble browser paths independently.
- Queued/provider execution rechecks app availability after claim and before provider resolution or mutation. Disabled work pauses or cancels under the queue's explicit terminal-state contract.
- Settings/admin remains a shell-owned navigation surface rather than an executable app identity.

## Data And Control Ownership

- Static identity, route, execution, resource, and launcher metadata: `packages/contracts/app-contracts.json` and generated TypeScript/Python projections.
- Runtime company control: `company_app_controls`.
- Workspace fallback: `workspace_app_defaults`.
- Per-workspace exception: `workspace_app_overrides`; absence means inherit.
- Per-user app choice: `user_app_workspace_preferences`.
- Company App Bar categories/order: `platform_app_bar_categories` and
  `platform_app_bar_category_apps`.
- Per-user presentation pins: `users.app_bar_layout.pinned_app_ids`.
- PostgreSQL is authoritative. UI hiding, local storage, process state, and catalog defaults are not authorization inputs.

## Consequences

- Route context matches the app that owns it, so company/personal apps no longer appear to inherit a selected workspace.
- Workspace app navigation retains user orientation when the current scope is valid, while destination previews make fallback workspace changes explicit.
- App enablement changes apply consistently to launcher, route gates, APIs, search, AI, and background work.
- New app registration must declare one leaf identity and explicit route contexts before it can be composed.
- Removing the former global default workspace and legacy visibility/entitlement tables is an intentional breaking development-stage migration.

## Related

- [ADR 0002](0002-mcp-capability-platform.md)
- [ADR 0005](0005-registered-llm-workload.md)
- [ADR 0006](0006-platform-personal-global-apps.md)
- [ADR 0007](0007-company-tenant-workspace-scope.md)
