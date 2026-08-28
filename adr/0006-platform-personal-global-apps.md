# ADR 0006: Platform Availability and Personal Global Apps

- Status: Accepted
- Date: 2026-07-16

## Decision

- `availability_scope` and `resourceScope` are separate.
- Workspace apps use workspace entitlement.
- Platform apps use company app control and global bootstrap.
- Resource scopes: `workspace`, `company`, `personal`, `hybrid`.
- Community is `platform + company`.
- Mail and Planner are `platform + personal`.
- Global shell uses `GET /api/v1/apps/bootstrap`.
- Workspace bootstrap and workspace app management exclude platform apps.
- Company app control off hard-gates App Bar, route, REST, AI discovery/execution, background dispatch/claim/provider I/O.
- Disabled apps keep data; re-enable shows existing data.
- Personal tools launcher is fixed/edit-disabled. Mail/Planner live there, not DB category/favorites.
- Personal data is owner-only. Cross-user access returns 404 without existence leak.
- Canonical personal browser routes: `/apps/mail`, `/apps/planner`. API routes remain `/api/v1/mail`, `/api/v1/planner`.
- Cross-workspace aggregations keep origin workspace and recheck membership/source entitlement/resource ACL.
- DM user search uses tenant-wide directory.
- Planner busy blocks affect meeting availability without leaking title/location.

## Out Of Scope

- per-user app hiding
- workspace legacy routes for Mail/Planner
- audience targeting by user/team/org

## Related

- [ADR 0002](0002-mcp-capability-platform.md)
- [ADR 0005](0005-registered-llm-workload.md)
- [ADR 0011](0011-app-first-workspace-context.md) replaces the route and runtime control contract.
