---
name: open-work-hub-agent-work-intake
description: Convert Open Work Hub plans, bugs, and feature requests into consistent GitLab Issues, PRDs, triage outcomes, and implementation-ready briefs. Use when creating or refining work for multiple maintainers or autonomous agents. Do not use for implementing an already-scoped issue.
---

# Work Intake

- Tracker: GitLab `gitlab.1punicorn.com/lumejs/open-work-hub`.
- Read `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, `docs/agents/domain.md`.
- Live labels: `bug`, `needs-triage`, `ready-for-agent`.
- Ready work requires observable acceptance criteria, current evidence, and no hidden product/security/data/architecture decision.
- Durable decisions go in owner docs or root `adr/`.
- External issue mutations require explicit scope.

Workflow: inspect code/tests/docs -> classify HITL/AFK -> draft criteria/checks -> publish with `glab` only when requested.
