---
name: open-work-hub-agent-work-intake
description: Convert Open Work Hub plans, bugs, and feature requests into consistent GitHub Issues, PRDs, triage outcomes, and implementation-ready briefs. Use when creating or refining work for multiple maintainers or autonomous agents. Do not use for implementing an already-scoped issue.
---

# Open Work Hub Agent Work Intake

## Rules

- GitHub Issues are the repository work-tracking source of truth.
- Follow `docs/agents/issue-tracker.md` and `docs/agents/triage-labels.md`; verify live labels before changing them.
- Implementation-ready work needs observable acceptance criteria and current-state evidence with no hidden product, security, data, or architecture decisions.
- Use the current GitHub default labels (`bug`, `enhancement`, `documentation`, `question`, and closure labels). Do not invent workflow-state labels; readiness is recorded as a completed brief/checklist.
- Put durable decisions in the owning document linked from `docs/README.md` or in root `adr/`; do not leave them only in chat or issue comments.
- Creating, commenting on, labeling, closing, or reopening an issue is an external mutation and requires explicit user scope.

## Workflow

1. Read `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, and `docs/agents/domain.md`.
2. Inspect the current code, tests, owner documentation, and relevant ADRs.
3. Classify unresolved decision work as HITL and independently implementable work as AFK.
4. Write acceptance criteria around observable behavior and affected repository checks.
5. Draft first; use `gh issue create` or `gh issue edit` only when publication or mutation was explicitly requested.
