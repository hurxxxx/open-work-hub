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
3. Read the matching `EvalSuite` manifest and prompt bundle.
4. Read the matching scenario document.
5. Identify which dataset cases are missing or stale.
6. Propose new cases for `golden`, `adversarial`, `shadow`, and `drift` as needed.

Return:

```text
scenario_id:
changed_surface:
required_new_cases:
cases_to_refresh:
promptfoo_config:
release_gate_impact:
```
