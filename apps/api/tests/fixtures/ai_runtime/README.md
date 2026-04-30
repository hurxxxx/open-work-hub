# AI Runtime Phase 0 Gates

These fixtures are synthetic seed cases for Phase 6 Evidence Runtime PR 1.
They are intentionally small and deterministic. They must not call an LLM,
network provider, or workspace data source during tests.

`external_execution_summary_cases.json` also stays deterministic: it exercises
only local mock external planner/search adapters and records safe summary
metadata, not raw prompts, raw queries, or raw provider output.

## Launch SLO Metrics

- concurrent active users
- p95 TTFT
- p95 report latency
- approval wait time

## Structured Output Hard Gate

Before graph runtime rollout, local model profile and the selected serving stack
must be measured for:

- `ExecutionGraph` schema success rate
- tool-call stability
- malformed output rate

These gates are benchmark targets only in Phase 0-A. The graph manager is not
enabled by these fixtures.
