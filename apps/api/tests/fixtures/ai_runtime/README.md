# AI Runtime Phase 0 Gates

These fixtures are synthetic seed cases for Phase 6 Evidence Runtime PR 1.
They are intentionally small and deterministic. They must not call an LLM,
network provider, or workspace data source during tests.

## Launch SLO Metrics

- concurrent active users
- p95 TTFT
- p95 report latency
- approval wait time

## Structured Output Hard Gate

Before graph runtime rollout, Qwen3.6-35B-A3B and the selected serving stack
must be measured for:

- `ExecutionGraph` schema success rate
- tool-call stability
- malformed output rate

These gates are benchmark targets only in Phase 0-A. The graph manager is not
enabled by these fixtures.
