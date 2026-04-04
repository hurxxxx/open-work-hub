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
2. If a file path or folder is known, resolve `domain_id` from `docs/agents/manifests/domain-rule-manifests/` first.
3. Read the matching `ScenarioManifest`.
4. Choose exactly one `scenario_id`.
5. List the must-read documents for this task.
6. List the optional supporting docs only if the task truly needs them.
7. List which scenario or domain docs should not be loaded by default.
8. List the expected artifacts.
9. List the required regressions and release-gate checks.

Return in this format:

```text
scenario_id:
resolved_domain:
must_read_docs:
optional_support_docs:
do_not_load_by_default:
expected_artifacts:
required_regressions:
open_risks:
```
