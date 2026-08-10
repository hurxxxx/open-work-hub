---
name: open-alm-agent-work-intake
description: Convert Open ALM plans, bugs, and feature requests into GitLab Issues with consistent PRD, triage, and ready-for-agent briefs. Use when creating or refining work for multiple maintainers or AFK agents.
---

# Open ALM Agent Work Intake

## Rules

- GitLab Issues are the work-tracking source of truth.
- Use only the triage labels documented in `docs/agents/triage-labels.md`: optional `bug`, plus exactly one open-issue state when triage has started (`needs-triage` or `ready-for-agent`).
- Ready-for-agent issues need enough context for an AFK agent to implement without hidden decisions.
- Put durable domain decisions in the owning document under `docs/current`, `docs/domains`, or `docs/apps`, or in root `adr/`; do not leave them only in chat or issue comments.

## Workflow

1. Read `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`, and `docs/agents/domain.md`.
2. Classify the work as AFK or HITL.
3. Write acceptance criteria around observable behavior and harness checks.
4. Link relevant ADRs and current docs.
5. Use GitLab issue comments with clear AI-generated triage disclosure where applicable.
