---
description: Map a request to the correct harness scenario and list the required source-of-truth docs.
argument-hint: [request-or-change]
disable-model-invocation: true
allowed-tools: Read Grep Glob
---

Normalize the request below into this repository's harness workflow.

Request:
$ARGUMENTS

Steps:
1. Read `docs/agents/agent-operating-standard.md`.
2. Read the scenario docs under `docs/harness/scenarios/`.
3. Choose exactly one `scenario_id`.
4. List the must-read documents for this task.
5. List the optional supporting docs only if the task truly needs them.
6. List which scenario or domain docs should not be loaded by default.
7. List the expected artifacts.
8. List the required regressions and release-gate checks.

Return in this format:

```text
scenario_id:
must_read_docs:
optional_support_docs:
do_not_load_by_default:
expected_artifacts:
required_regressions:
open_risks:
```
