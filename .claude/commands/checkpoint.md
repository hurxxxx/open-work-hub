---
description: Capture a concise checkpoint for a large task, including completed surfaces, open risks, and the next action.
argument-hint: [workstream-or-task]
disable-model-invocation: true
allowed-tools: Read Write Edit Grep Glob
---

Create a checkpoint for:

$ARGUMENTS

Steps:
1. Read `docs/ops/learnings-and-checkpoints.md`.
2. Read `docs/ops/project-checkpoints.md`.
3. Summarize the current workstream in the checkpoint format from the docs.
4. Append a short new entry under `docs/ops/project-checkpoints.md`.
5. Keep the entry concise and durable.

Return:

```text
date:
workstream:
scenario_id:
completed:
open_risks:
next_action:
```
