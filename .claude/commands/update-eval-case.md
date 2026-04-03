---
description: Update or propose eval cases when prompts, workflows, or guardrails change.
argument-hint: [scenario-id-or-changed-surface]
disable-model-invocation: true
allowed-tools: Read Grep Glob
---

Use the repository harness rules to update eval coverage for:

$ARGUMENTS

Steps:
1. Read `docs/agents/agent-operating-standard.md`.
2. Read `docs/harness/eval-regression-spec.md`.
3. Read the matching scenario document.
4. Identify which `EvalCase` examples are missing or stale.
5. Propose new cases for `golden`, `adversarial`, `shadow`, and `drift` as needed.

Return:

```text
scenario_id:
changed_surface:
required_new_cases:
cases_to_refresh:
release_gate_impact:
```
