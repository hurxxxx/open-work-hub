# ADR 0006: Platform Availability and Personal Global Apps

- Status: Accepted
- Date: 2026-07-16

## Decision

- `availability_scope` and `resource_scope` are separate.
- [ADR 0011](0011-app-first-workspace-context.md) is authoritative for current routes, launcher,
  runtime controls, and workspace choice. This ADR owns platform/personal resource semantics.
- Resource scopes: `workspace`, `company`, `personal`, `hybrid`.
- Community is `platform + company`.
- Mail and Planner are `platform + personal`.
- Company app control off hard-gates App Bar, route, REST, AI discovery/execution, background dispatch/claim/provider I/O.
- Disabled apps keep data; re-enable shows existing data.
- Mail and Planner use the static `personal_tools` launcher placement, not DB categories or pins.
- Personal data is owner-only. Cross-user access returns 404 without existence leak.
- Personal API routes remain `/api/v1/mail` and `/api/v1/planner`.
- Cross-workspace aggregations keep origin workspace and recheck membership, source-app availability,
  and resource ACL.
- DM user search uses tenant-wide directory.
- Planner busy blocks affect meeting availability without leaking title/location.

## Out Of Scope

- per-user app hiding
- workspace legacy routes for Mail/Planner
- audience targeting by user/team/org

## Related

- [ADR 0002](0002-mcp-capability-platform.md)
- [ADR 0005](0005-registered-llm-workload.md)
- [ADR 0011](0011-app-first-workspace-context.md) owns the route and runtime control contract.
