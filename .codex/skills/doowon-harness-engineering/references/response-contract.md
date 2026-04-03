# Response Contract

For substantial task results in this repository, prefer this structure:

```text
scenario_id: <one scenario key>
changed surfaces: <prompt/workflow/retrieval/guardrail/trace/export/docs/adapters/code>
tests/evals: <offline evals, online eval implications, required regressions>
open risks: <remaining ambiguity, missing automation, gate blockers>
```

## Required notes

- State assumptions explicitly if the scenario mapping was not obvious.
- If docs changed, mention which adapter files should be checked for alignment.
- If service behavior changed, mention trace/span and release-gate impact.
