# Triage Labels

The live GitLab project uses three labels for issue triage:

| Role | GitLab label | Rule |
| --- | --- | --- |
| Defect marker | `bug` | Apply only when reported behavior is a confirmed or plausible defect. Feature work has no category label. |
| Needs decision | `needs-triage` | The issue still needs evidence, scope, or a maintainer decision. |
| Ready for AFK work | `ready-for-agent` | The issue has a complete, testable agent brief and no unresolved decision. |

An open issue must not carry both state labels. Moving an issue to one state removes the other. Reopened issues return to `needs-triage` until revalidated.

If information is missing or human judgment is still required, keep `needs-triage` and explain the outstanding question in a comment. For a duplicate or rejected request, record the reason in a comment, remove both state labels, and close the issue.

Repository lane and rewrite-approval labels are separate governance metadata, not triage states. Only the labels listed above belong to the triage contract.

Verify the live vocabulary before changing this contract:

```bash
glab label list --per-page 100
```
