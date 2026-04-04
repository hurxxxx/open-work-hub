---
description: Check documentation staleness and update repository source-of-truth docs and adapters after a change.
argument-hint: [changed-surface-or-branch]
disable-model-invocation: true
allowed-tools: Read Grep Glob Write Edit
---

Synchronize documentation for:

$ARGUMENTS

Steps:
1. Read `docs/agents/agent-operating-standard.md`.
2. Read `docs/agents/agent-tooling-registry.md`.
3. Read `docs/ops/sprint-workflow.md`.
4. Identify which source-of-truth docs or structured assets are stale after the change.
5. Check `docs/harness/manifests/*`, `docs/harness/prompt-bundles/*`, `docs/harness/evals/*`, `docs/agents/manifests/*`.
6. Identify which adapter files are stale: `agents.md`, `CLAUDE.md`, `.claude/rules/*`, `.claude/commands/*`, `.codex/skills/doowon-harness-engineering/*`.
7. Update the source-of-truth docs first, then update adapters only if needed.
8. Summarize which docs changed and which docs should still be reviewed by a human.

Return:

```text
scenario_id:
source_of_truth_docs_updated:
adapter_files_updated:
docs_still_to_review:
open_risks:
```
