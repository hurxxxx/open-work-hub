# LLM-Friendly Development

## Defaults

- Few entrypoints, clear ownership, predictable names: `router.py`, `application.py`, `service.py`, `schemas.py`, `registry.py`.
- Thin abstractions. Add registry/adapter/plugin loader only for real runtime variation.
- Match code names to domain terms. Avoid local aliases and pass-through modules.
- Preserve compatibility routes/contracts until explicitly retired.
- [ADR 0012](../../adr/0012-company-app-access-without-workspaces.md) and [App Platform](../domains/app-platform/README.md) own current company, app admission, and execution scope. Superseded ADR sections are not implementation requirements.
- Expose complex behavior as descriptors, profiles, degraded reasons, and source IDs.
- No branch for one prompt, keyword, field, user, customer, or fixture.

## Shape

- Backend domain: `apps/api/src/open_work_hub_api/domains/<domain>/`.
- Frontend app: `apps/web/src/app-modules/<moduleId>/`.
- Composition roots assemble registrations; no copied app ID allowlists in shell/auth/search.
- Router owns HTTP/SSE envelope, dependencies, response models, localized errors.
- Application/service owns orchestration, ACL/business rules, DB transactions, search/LLM/projection calls.
- REST, AI tool, and worker paths share domain service behavior when semantics match.

## Generative LLM

- Register every generative call as a stable namespaced `RegisteredLlmWorkload`.
- Register from `register_ai_capabilities(registry)`.
- Workload unit = independently configurable function/stage.
- Call only `execute_llm` or `stream_llm`.
- Caller supplies constant `workload_id`, app/actor, declared personal/company execution context,
  and input/messages. No global container ID is attached to company execution.
- Caller never selects provider, model, pool, endpoint, credential, retry/fallback, or route by user input.
- Providers and agent runtimes are approved adapters behind the common interface.
- Output caps default to local 32K and external 64K unless descriptor/admin route is stricter.
- External transfer security allow/mask/block/audit never reroutes.
- Unknown workload, missing adapter, unsupported route, or security block fails closed.
- Embedding/rerank/OCR/ASR use Inference Gateway, not LLM workload contracts.

Owners: [AI Domain](../domains/ai/README.md) and [AI Execution](../domains/ai/execution.md).
[ADR 0002](../../adr/0002-mcp-capability-platform.md) and
[ADR 0005](../../adr/0005-registered-llm-workload.md) retain capability/workload contracts under ADR 0012.

## MCP/AI Tools

- Capability source: `AiCapabilityDescriptor`.
- MCP manifest, OpenAI strict schema, and derived OpenAPI are generated from descriptors.
- Use AI-specific Pydantic DTOs, not human REST request models.
- Discovery checks app availability/discoverability. Invoke repeats discoverability and source ACL.
- Write tools require feature flag, preview, explicit approval, execution ACL, and audit.

## Retrieval/RAG

- New callers use Retrieval surfaces; `/rag` wrappers stay compatibility-only.
- Active caller-facing backend channels: Qdrant `generic_rag`, OpenSearch `keyword`; resource
  participation is listed separately in the RAG source matrix.
- Do not compare raw scores across backends.
- Company keyword search is declared by backend `SearchEntityAdapter`, not frontend flags/app allowlists.
- `retrieval_partition_id` is candidate scope, not ACL.
- Evidence, summaries, external LLM payloads, and citations pass source-owned final ACL.
- Projection identity/version/cutover: ADR 0009.

Owners: [Retrieval](../domains/retrieval/README.md), [RAG](../domains/rag/README.md),
and [Source Access](../domains/source-access/README.md).
[ADR 0004](../../adr/0004-retrieval-rag-boundary-policy.md) and
[ADR 0009](../../adr/0009-retrieval-partition-projection-generations.md) retain backend/projection
safety contracts under ADR 0012.

## Avoid

- inheritance framework around all backends
- registry/plugin loader without runtime extension
- router/service/worker direct calls to provider SDK, low-level LLM gateway, RAG query, retry, rerank
- deep imports across app modules
- app ID lists in shell/auth/search outside composition output
- generated artifacts edited by hand
- docs/code using different names without explaining the difference

## Validation

- New AI capability: registry compile, duplicate guard, MCP schema/discovery, direct invoke, hidden-tool blocked tests.
- New LLM workload: duplicate/budget/adapter/default-route tests and direct-call guard.
- New app API: router registration, server app gate, `pnpm check:api-contract`.
- Docs updates: verify paths, commands, and owner links against current tree.
- Check selection: [Vibe Harness](vibe-coding-harness.md).
