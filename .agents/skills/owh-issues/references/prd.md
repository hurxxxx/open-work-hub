# To PRD

Synthesize current conversation and repo context. Ask only for consequential missing decisions; otherwise preserve open questions in the draft. Draft first; publish GitLab issue only when requested.

## Process

1. Inspect repo for current behavior, owner terms, relevant ADRs.
2. List unresolved product/testing decisions; use `needs-triage` if published.
3. Prefer deep modules with small interfaces when describing implementation.
4. Add `ready-for-agent` only when no unresolved decisions remain.

## PRD Fields

- Problem Statement
- Solution
- User Stories
- Implementation Decisions
- Testing Decisions
- Out of Scope
- Further Notes

Avoid brittle file paths/snippets unless an exploratory implementation produced decision-rich state/schema/interface detail.
