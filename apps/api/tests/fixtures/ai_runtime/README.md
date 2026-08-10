# AI Runtime Evaluation Gates

These fixtures are synthetic seed cases for runtime evaluation checks. They are
intentionally small and deterministic. They must not call an LLM, network
provider, or workspace data source during tests.

Only fixtures that feed active runtime tests live here. Historical sample
fixtures should stay out of the local suite unless they drive executable
behavior.

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

These gates are evaluation targets only. The graph manager is not enabled by
these fixtures.
