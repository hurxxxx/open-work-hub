---
description: Prepare the regression checklist for a scenario or changed surface.
argument-hint: [scenario-id-or-change]
disable-model-invocation: true
allowed-tools: Read Grep Glob Bash
---

Prepare a regression checklist for:

$ARGUMENTS

Steps:
1. Read `docs/harness/eval-regression-spec.md`.
2. Read the matching scenario document.
3. Identify which datasets must run: `golden`, `adversarial`, `shadow`, `drift`.
4. List the metrics and thresholds that gate release.
5. If there is no executable harness yet, output the checklist and missing automation gaps.

Return:

```text
scenario_id:
dataset_plan:
gate_metrics:
must_run_now:
missing_automation:
```
