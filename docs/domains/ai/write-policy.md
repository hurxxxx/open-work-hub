# AI Write Policy

Default AI behavior is read/search/summarize. Source-changing tools execute only with feature flag, preview, user approval, source ACL, and audit.

## Rules

- Write tools are hidden by default.
- First execution creates approval preview and stops before mutation.
- Only requesting user principal can approve/reject.
- Approved resume rechecks domain service ACL and business rules.
- Resume scope, frozen tool set, and snapshot lifecycle follow [AI Execution](execution.md).
- Approval row, tool audit, and resource IDs are linked.
- External provider input follows [AI Gateway](./gateway.md) security/transfer policy.

## Current Sources

| Source | Default AI | Write tool |
| --- | --- | --- |
| Mail | search/summary/translation/task extraction | none |
| Meeting | lookup/summary/action extraction | flag-gated create |
| PMS | lookup/summary/task candidates | flag-gated create/update/comment/delete |
| Files | lookup/summary candidates | none |
| Docs | search/summary/draft | none |
| Planner | lookup/summary/event candidates | flag-gated create/update/delete |

## Implementation

- `OPEN_WORK_HUB_AI_WRITE_TOOLS_ENABLED=false` hides write descriptors from registry/AI surface.
- Enabled descriptors use `mode="write"`, `approval_required=True`, valid `preview_builder_id`.
- Registry derives `approval_policy="required"`.
- Approval preview emits `approval_required`; mutation does not run.
- New write capability must include flag/discoverability, preview, approval, ACL, audit, failure, and idempotency tests.
