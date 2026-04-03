---
description: Capture a durable project learning that will save time in future sessions.
argument-hint: [insight-or-workstream]
disable-model-invocation: true
allowed-tools: Read Write Edit Grep Glob
---

Review whether this work produced a durable learning:

$ARGUMENTS

Steps:
1. Read `docs/ops/learnings-and-checkpoints.md`.
2. Read `docs/ops/project-learnings.md`.
3. Only keep insights that are non-obvious, reusable, and likely to save time later.
4. Append a concise entry to `docs/ops/project-learnings.md` if warranted.
5. If no durable learning exists, say so explicitly and do not add filler.

Return:

```text
scenario_id:
learning_added:
insight:
evidence:
impact:
```
