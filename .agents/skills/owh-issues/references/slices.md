# To Issues

Use GitLab Issues. Draft first; publish with `glab issue create` only when requested.

## Process

1. Use conversation context and referenced issue/spec. Fetch full issue/comments if an issue ref is given.
2. Inspect repo only as needed for current behavior/terms.
3. Break into vertical tracer slices.
4. Mark each slice HITL or AFK.
5. Resolve missing granularity/dependency/classification decisions; reuse existing decisions and publication authorization.
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
