# AI Runtime Evaluation Gates

These fixtures are synthetic seed cases for runtime evaluation checks. They are
intentionally small and deterministic. They must not call an LLM, network
provider, or company data source during tests.

Fixtures should stay here only while they feed an executable runtime evaluation. The sanitizer
fixture is consumed by external-egress tests. `routing_cases.json` is currently a reserved
evaluation corpus, not a CI gate; do not treat its expectations as enforced until a deterministic
evaluator consumes it.

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
