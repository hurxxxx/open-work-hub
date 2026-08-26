# Triage Labels

| Label | Rule |
| --- | --- |
| `bug` | confirmed/plausible defect only |
| `needs-triage` | missing evidence, scope, or maintainer decision |
| `ready-for-agent` | complete testable brief; no unresolved decision |

- Feature/docs work has no category label by default.
- An open issue must not have both `needs-triage` and `ready-for-agent`.
- Reopened issues return to `needs-triage` until revalidated.
- Duplicate/rejected: comment reason, remove state labels, close only when authorized.
- Lane/rewrite-approval labels are governance metadata, not triage states.

Verify before changing:

```bash
glab label list --per-page 100
```
