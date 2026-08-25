---
name: open-work-hub-vibe-app-delivery
description: Deliver new or ported Open Work Hub apps and changes that cross protected app identity, API/data, worker, file/network, or AI extension contracts. Use when creating or porting an app or when an existing app lacks required platform scaffold. Do not use for copy, translation, app-local UI, focused tests, or routine fixes inside an existing scaffold.
---

# Open Work Hub App Delivery

Start with current code/tests and `docs/domains/app-platform/README.md`. Load only references for surfaces the change actually reaches.

## Route the Work

- Existing scaffold plus app-local behavior: use the normal implementation workflow.
- Missing or changed protected scaffold: make the missing extension points explicit before app-local implementation.

Protected scaffold includes app identity/registration, entitlement/bootstrap, shell and API composition, generated OpenAPI/client, shared RBAC/data scope, worker runtime, file/network services, and AI workload/capability extension points. Never weaken checks, auth, generated contracts, or registries to force a feature through.

## Enablement Brief

```text
Core-enablement brief
- User outcome:
- App/feature id and owner:
- Missing protected extension points:
- Workspace/company/global data scope:
- Roles and write operations:
- API/OpenAPI, worker, file, network, or AI needs:
- Proposed app-owned paths after enablement:
- Activation owner and default-disabled behavior:
- Acceptance and negative tests:
```

Unknown product, permission, retention, destructive, or external-data decisions require an owner decision; do not infer them.

## Contract Map

For a complex delivery, record applicable surfaces: identity; data/auth; API/UI; files/network; AI workload/route/budget/audit; worker registration/routing; migration compatibility; and search/retrieval ACL/projection lifecycle.

## References by Surface

- Registration/API prefix: `docs/domains/app-platform/README.md`
- Validation depth: `docs/agents/vibe-coding-harness.md`
- UI reuse: `docs/agents/ui-components.md`
- AI/LLM: ADR 0002, ADR 0005, then `open-work-hub-mcp-capability-governance`
- Search/RAG: `docs/domains/retrieval/README.md`, `docs/domains/rag/README.md`, and ADR 0009

## Invariants

- Enforce entitlement and RBAC on the server.
- Keep authoritative state in approved database/object-storage contracts with transactions, concurrency, retention, retry/idempotency, and safe cleanup.
- Validate observed file type and counted limits before whole-body read, decompression, decode, workbook load, or JSON materialization.
- Revalidate external URLs after redirects, block private/link-local/metadata targets, preserve TLS verification, and serve active content safely.
- Route generative AI through registered workloads and the common execution interface; apps do not select provider/model/pool or add fallback.
- A worker task is complete only when deployed bootstrap and routing can discover it.
- Build migrations from the current head, register model metadata, and preserve supported data/workflows.

Select affected checks from `docs/agents/vibe-coding-harness.md`. Creating a branch, commit, push, or GitHub PR remains separately authorized; no repository-specific publisher or lane is required.
