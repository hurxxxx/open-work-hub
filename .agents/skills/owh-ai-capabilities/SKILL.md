---
name: owh-ai-capabilities
description: Use when changing product AI tools, MCP manifests, or registered LLM execution, approval, discovery, and audit. Excludes coding-agent CI automation and ordinary app UI.
---

# MCP Capability Governance

- Start with [App Platform](../../../docs/domains/app-platform/README.md) and [ADR 0012](../../../adr/0012-company-app-access-without-workspaces.md) for current authorization. Read ADR 0002 for capabilities and ADR 0005 for LLM workloads; their former scope requirements are superseded.
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
