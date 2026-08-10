---
name: ai-do-mcp-capability-governance
description: Govern product MCP/AI capabilities and registered LLM workloads against ADRs 0002 and 0005. Use when adding or changing product AI tools, MCP manifests, LLM execution, approval/discoverability, audit/tracing, or write-capability rollout. Do not use for Codex CI/review harness behavior unless it changes a product AI capability.
---

# AI-DO MCP Capability Governance

## Rules

- ADR 0002 is the contract for AI capabilities.
- ADR 0005 is the contract for generative LLM workloads.
- Register capabilities through `register_ai_capabilities(registry)` and `AiCapabilityRegistry`.
- Use AI-specific DTOs; do not reuse human REST request models.
- Write tools require approval gates and discoverability predicates.
- Discovery filtering and execution-time authorization must both be tested.
- Every generative LLM call, whether it belongs to a new app or an existing feature,
  must declare a stable, app/feature-specific `RegisteredLlmWorkload` through
  `register_ai_capabilities(registry)` and execute through the common
  `execute_llm`/`stream_llm` Interface.
- A workload is one independently configurable execution function, not an app-wide or
  generic generation bucket. Split multi-stage apps whenever route, model, or output-token
  cap can differ. Multiple app ids may share a workload only when
  they expose the same execution and policy semantics.
- The caller must use a server-selected constant `workload_id` and `app_id`. It must not
  accept a workload id from user input or select provider, model, pool, endpoint, or
  credential.
- Every workload addition or identity change must declare its local and external output
  token caps on the `RegisteredLlmWorkload` descriptor, declare audit/tracing and
  external data behavior, and pass Adapter/capability validation. Do not create a second
  task/profile budget map or budget-registration hook.
- Default maximum output-token caps are 32K local and 64K external. Admin overrides are
  hard caps; a caller may request less but must never bypass or exceed them.
- The workload route override is the sole admin source of truth for local/external
  selection. Do not add a second task policy, security mode, caller hint, or app-local
  setting that selects another route.
- AI security evaluates only payloads whose resolved workload route is external. Its
  result is allow, mask, block, or audit; a block fails the request and must never silently
  reroute to local. Local calls still retain registry, readiness, cap, audit, and usage
  enforcement.
- Do not bypass a missing workload, Adapter, or budget with a service-local `max_tokens`,
  direct `core.llm`/gateway call, provider SDK/HTTP call, or local registry. Add the
  protected extension through Core Enablement first.
- Preserve existing external LLM implementations as approved provider Adapters. The
  common runtime and per-workload admin route choose local or external; migration moves
  SDK/HTTP ownership behind the Adapter and does not remove provider-native behavior.
- Web Search, Research Trends, and Standards Monitor are external-only workloads using
  the existing Anthropic native `web_search` Adapter. Do not add a local route or
  cross-route fallback on failure.
- AI search, RAG, planner, and report pipelines must not add question-specific,
  keyword-specific, vehicle-specific, field-specific, or case-specific branches.
  The LLM planner may select generic operators and schema-validated field keys; server
  code executes only reusable operators such as semantic search, full-text search,
  related-by-field, grouping, or aggregation.
- Reject bespoke tuning like `if question contains ...`, hardcoded synonym/suffix maps,
  per-question booleans, or result rewrites aimed at one prompt. Convert quality fixes
  into planner schema, prompt contract, generic scoring, and evaluation fixtures.

## Required Checks

- Registry compile and duplicate registration tests.
- Platform extension bootstrap / registry tests after LLM task, capability, provider,
  adapter, search, or RAG registry changes:
  `cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/test_platform_adapter_registries.py -q`.
- LLM workload and direct-call guard tests after any new app/feature LLM use:
  `cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/test_ai_gateway_direct_call_guard.py -q`.
- The registry test must prove each workload has a unique id, supported Adapter, local and
  external budgets, audit-safe metadata, and an executable default route. Unknown workload
  ids must fail closed.
- Hidden tool blocked at execution.
- Approval preview required before write capability exposure.
- Audit/tracing payloads do not include raw secrets or unnecessary sensitive data.
