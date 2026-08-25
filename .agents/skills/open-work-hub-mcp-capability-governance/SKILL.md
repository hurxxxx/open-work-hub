---
name: open-work-hub-mcp-capability-governance
description: Govern Open Work Hub product MCP/AI capabilities and registered LLM workloads against ADRs 0002 and 0005. Use when adding or changing product AI tools, MCP manifests, LLM execution, approval/discoverability, audit/tracing, or write-capability rollout. Do not use for coding-agent review automation unless it changes a product AI capability.
---

# Open Work Hub MCP Capability Governance

## Capability Contract

- Read root ADR 0002 for product AI capabilities and ADR 0005 for generative LLM workloads.
- Register capabilities through `register_ai_capabilities(registry)` and `AiCapabilityRegistry`; use AI-specific DTOs rather than human REST request models.
- Write tools require approval gates and discoverability predicates. Test both discovery filtering and execution-time authorization.
- Every generative call declares a stable, feature-specific `RegisteredLlmWorkload` and executes through the common `execute_llm`/`stream_llm` interface.
- A workload is one independently configurable execution function. Split stages when route, model, or output-token cap can differ.
- Callers use server-selected constant `workload_id` and `app_id`; user input must not select workload, provider, model, pool, endpoint, or credential.
- Declare local/external output caps, audit/tracing behavior, and external-data behavior on the descriptor. Do not create service-local budget maps or direct provider calls.
- The workload route override is the only admin source of local/external selection. A security block fails the request and never silently reroutes.
- Unknown workloads, missing adapters, and unsupported routes fail closed.
- Search/planner quality fixes belong in generic operators, schemas, prompts, scoring, and evaluation fixtures—not question-specific branches or hardcoded synonym rewrites.

## Required Evidence

After registry, provider, adapter, search, RAG, or workload changes, run the focused relevant tests:

```bash
cd apps/api
uv run --python 3.12 --group dev python -m pytest \
  tests/test_platform_adapter_registries.py \
  tests/test_ai_gateway_direct_call_guard.py \
  tests/test_ai_capability_compile.py -q
```

Also prove hidden tools are blocked at execution, write exposure requires approval, unknown identities fail closed, and audit/tracing does not retain secrets or unnecessary sensitive payloads.
