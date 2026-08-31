# ADR 0005: Registered LLM Workload and Common Execution Interface

- Status: Accepted
- Date: 2026-07-10

## Decision

- Every generative LLM call registers `RegisteredLlmWorkload` in `AiCapabilityRegistry`.
- Domain hook: `register_ai_capabilities(registry)`.
- `workload_id` is a stable namespaced server constant.
- Workload unit = independently configurable execution function/stage.
- Legacy `task_kind` may remain for budget/audit compatibility; `workload_id` is discovery key.
- Domain service/worker calls only `execute_llm(...)` or `stream_llm(...)`.
- Caller passes workload, app, actor, execution context, and input. Workspace is present only for a
  workspace execution context. Caller never chooses provider/model/pool/endpoint/credential.
- Common execution resolves route/provider/model/output cap once from descriptor plus admin override.
- External security allow/mask/block/audit never reroutes. Block fails closed.
- Provider implementations are approved adapters behind the common interface.
- `execution_kind="agent"` uses `AgentRuntimeAdapter`, separate from one-shot `LlmExecutionAdapter`.
- Embedding/rerank/OCR/ASR are outside this ADR and use Inference Gateway.

## Admin Surfaces

- Admin projects registry snapshot plus DB overrides; no hardcoded workload list.
- New workload appears with default route without DB seed.
- DB stores provider/model settings and workload overrides only.
- Workload route override is the only local/external selection source.
- Output cap defaults: local 32K, external 64K.
- Approved model catalog controls route choices; discovery never auto-approves models.
- API responses/UI never return API key plaintext.
- Management groups: LLM Providers, Model Catalog, LLM Routing, AI Security, Audit Logs.
- Document-processing vision workloads keep registry/audit but use `management_surface="document_processing"`.
- Web Search is external-only; no local fallback.

## Required Change Unit

- stable `workload_id`
- local/external output caps
- common execution call
- audit/tracing and external-data policy
- registry/bootstrap/duplicate/adapter/default-route tests
- provider/core direct-call guard test

## Do Not

- Add app-local workload registry, file scan, direct SDK/HTTP call, or route fallback.
- Let AI Security choose a different route.
- Store task-kind local/external policy outside workload routing.
