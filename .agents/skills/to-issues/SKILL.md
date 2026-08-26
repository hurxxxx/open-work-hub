---
name: to-issues
description: Break a plan, spec, or PRD into independently-grabbable issues on the project issue tracker using tracer-bullet vertical slices. Use when user wants to convert a plan into issues, create implementation tickets, or break down work into issues.
---

# To Issues

Use GitLab Issues. Draft first; publish with `glab issue create` only when requested.

## Process

1. Use conversation context and referenced issue/spec. Fetch full issue/comments if an issue ref is given.
2. Inspect repo only as needed for current behavior/terms.
3. Break into vertical tracer slices.
4. Mark each slice HITL or AFK.
5. Ask user to approve granularity/dependencies/classification before publishing.
6. Publish blockers first when requested.

## Slice Fields

- title
- type: HITL/AFK
- blocked by
- user stories covered
- what to build: observable end-to-end behavior
- acceptance criteria
- validation
- labels: `bug` for defects, `needs-triage` for unresolved decisions, `ready-for-agent` only with complete brief

Do not close/modify parent issue.
