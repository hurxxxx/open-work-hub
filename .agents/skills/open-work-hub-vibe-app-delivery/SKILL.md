---
name: open-work-hub-vibe-app-delivery
description: Deliver new or ported Open Work Hub apps and changes that cross protected app identity, API/data, worker, file/network, or AI extension contracts. Use when creating or porting an app or when an existing app lacks required platform scaffold. Do not use for copy, translation, app-local UI, focused tests, or routine fixes inside an existing scaffold.
---

# App Delivery

Start with code/tests and `docs/domains/app-platform/README.md`.

## Route

- Existing scaffold + app-local behavior: normal implementation.
- Missing/changed protected scaffold: make enablement explicit before app-local work.

Protected scaffold: identity/registration, entitlement/bootstrap, shell/API composition, OpenAPI/client, RBAC/data scope, worker runtime, file/network service, AI workload/capability.

## Enablement Brief

```text
- outcome:
- app/feature id and owner:
- missing protected extension points:
- data scope:
- roles/write ops:
- API/OpenAPI/worker/file/network/AI needs:
- app-owned paths after enablement:
- activation owner/default-disabled behavior:
- acceptance/negative tests:
```

## Invariants

- Server enforces entitlement/RBAC.
- Authoritative state uses DB/object storage with transactions, retention, retry/idempotency, cleanup.
- Files/URLs validate type, size, redirects, TLS, SSRF, active content, cleanup.
- Generative AI uses registered workloads/common execution; app never selects provider/model/pool/fallback.
- Worker task is complete only when deployed bootstrap/routing discovers it.
- Migrations build from current head and preserve supported rows/workflows.
- Search/retrieval uses source ACL, partition/projection lifecycle, backfill/cutover/rollback evidence.

Use [Vibe Harness](../../../docs/agents/vibe-coding-harness.md). MR templates apply only when publication is requested.
