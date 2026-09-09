# AI Gateway

Generative model calls use registered workloads and the common execution gateway. App code never chooses provider SDK or external HTTP endpoint.

Approval replay, graph execution, and artifact state are owned by [AI Execution](execution.md).

## Contract

- Workload registers ID, owner, routes, capability, output cap, audit/tracing, external-data policy.
- Admin selects active provider/model and workload route.
- No local/external automatic fallback.
- External transfer passes classification, masking, approval policy, and audit.
- Tool execution checks the current user/execution principal, owning-app admission, descriptor discoverability, and
  source ACL; write tools also require approval.
- Audit records actor, app, workload, provider/model, token usage, trace ID.
- Agent runtime uses `AgentRuntimeAdapter`, separate from one-shot chat adapter.
- Runtime choice is a workload override.

## Local Runtime

- Endpoint: `OPEN_WORK_HUB_LLM_LOCAL_BASE_URL`.
- Profile: `OPEN_WORK_HUB_LLM_LOCAL_PROVIDER`.
- Model selection lives in Admin model catalog/routing, not env or app code.
- Docker Model Runner profile uses OpenAI-compatible API.
- Dev default: `http://127.0.0.1:12434/engines/v1`.
- Use `scripts/dev-local-qwen.sh` for model install/status/smoke.
- Qwen `reasoning_effort=none` maps to `chat_template_kwargs.enable_thinking=false`.
- `LlmCompletionResult` exposes provider-neutral `tool_calls`; apps do not inspect provider raw responses.
