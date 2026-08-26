---
name: open-work-hub-mcp-capability-governance
description: Govern Open Work Hub product MCP/AI capabilities and registered LLM workloads against ADRs 0002 and 0005. Use when adding or changing product AI tools, MCP manifests, LLM execution, approval/discoverability, audit/tracing, or write-capability rollout. Do not use for coding-agent review automation unless it changes a product AI capability.
---

# MCP Capability Governance

- Read ADR 0002 for capabilities and ADR 0005 for LLM workloads.
- Register through `register_ai_capabilities(registry)` and `AiCapabilityRegistry`.
- Use AI-specific DTOs, not REST request models.
- Write tools require approval, discoverability predicate, execution ACL, audit.
- Every generative call uses stable `RegisteredLlmWorkload` and `execute_llm`/`stream_llm`.
- Workload is independently configurable function/stage. Split route/model/output-cap differences.
- Caller never selects workload/provider/model/pool/endpoint/credential from user input.
- Descriptor declares output caps, audit/tracing, external-data behavior.
- Route override is only local/external selector; security block fails closed.
- Quality fixes use generic operators/schemas/prompts/scoring/evals, not question-specific branches.

```bash
cd apps/api
uv run --python 3.12 --group dev python -m pytest tests/test_platform_adapter_registries.py tests/test_ai_gateway_direct_call_guard.py tests/test_ai_capability_compile.py -q
```
