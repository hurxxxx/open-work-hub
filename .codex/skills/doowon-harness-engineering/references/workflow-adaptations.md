# Workflow Adaptations

This repository borrows a few ideas from gstack and adapts them to a harness-first workflow.

## Adopted patterns

- A named work sequence instead of ad-hoc prompting:
  - `explore -> select scenario -> lock contracts -> implement -> review/eval -> document -> release-gate -> retro/learn`
- Explicit document synchronization after meaningful changes.
- Separate habits for:
  - durable learnings
  - task checkpoints
  - retros
- A discoverable command/role registry instead of hidden prompts.

## Not adopted

- The full "virtual team of dozens of roles" model.
- gstack's telemetry, local daemons, or persistent browser runtime.
- gstack's generated multi-host skill toolchain.

## Repository equivalents

- Role/command catalog:
  - `docs/agents/agent-tooling-registry.md`
- Workflow:
  - `docs/ops/sprint-workflow.md`
- Learnings/checkpoints:
  - `docs/ops/learnings-and-checkpoints.md`
- Doc sync:
  - `.claude/commands/document-release.md`
