---
description: Run a lightweight retro for a completed workstream and identify repeatable patterns, bottlenecks, and next improvements.
argument-hint: [workstream-or-time-range]
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash
---

Run a retro for:

$ARGUMENTS

Steps:
1. Read `docs/ops/sprint-workflow.md`.
2. Read `docs/ops/learnings-and-checkpoints.md`.
3. Read `docs/ops/project-checkpoints.md` and `docs/ops/project-learnings.md`.
4. If useful, inspect recent git history or changed files.
5. Summarize what worked, what slowed us down, what should become a standard, and what should change next time.

Return:

```text
workstream:
worked_well:
friction:
standardize_next:
next_improvement:
```
