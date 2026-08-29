# ADR 0007: Company Tenant And Workspace Scope

- Status: Accepted
- Date: 2026-07-20

## Decision

- Current deployment/database/settings bundle represents one company tenant.
- Company tenant is implicit deployment boundary, not a DB row.
- Do not add company slug to all URLs or `company_id` to all tables for current model.
- Active users belong to the company tenant.
- System role/platform admin controls tenant-level admin work.
- Workspace is a collaboration/access/data isolation scope below company, not tenant.
- App-first routes follow [ADR 0011](0011-app-first-workspace-context.md): workspace routes use `/apps/:appId/workspaces/:workspaceSlug/...`; global routes omit the workspace segment.
- Workspace slug is locator only. Server rechecks membership, RBAC, resource ACL, and app entitlement.
- Global route means no workspace selection required, not public access.

## Scope Matrix

| Dimension           | Values                                       |
| ------------------- | -------------------------------------------- |
| Tenant boundary     | company deployment                           |
| App availability    | `platform`, `workspace`                      |
| Resource ownership  | `company`, `personal`, `workspace`, `hybrid` |
| Route context       | global, workspace                            |
| Execution context   | `personal`, `company`, `workspace`           |

- Do not infer resource ownership from availability or principal.
- Company execution context means tenant-scoped app execution; it does not by itself widen resource ownership or source ACL.
- Company-resource reads default to authenticated tenant users when no narrower ACL exists.
- Company-resource writes default to platform admin when no narrower policy exists.
- Cross-workspace aggregation keeps origin workspace and rechecks source access.
- Launcher categories/pins are display only.

## Out Of Scope

- shared-database multi-tenancy
- converting all apps to global
- audience targeting
- workspace lifecycle/org policy

Shared-database multi-tenancy needs a new ADR.
