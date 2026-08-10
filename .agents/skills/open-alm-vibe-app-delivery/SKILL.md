---
name: open-alm-vibe-app-delivery
description: Deliver new or ported Open ALM domain apps and changes that cross protected app identity, API/data, worker, file/network, or AI extension boundaries. Use when creating or porting an app, or when an existing app needs missing protected scaffold. Do not use for copy, translation, app-local UI, focused tests, or routine bug fixes inside an existing scaffold.
---

# Open ALM Vibe App Delivery

## Route The Work

Start with current code/tests and
`docs/domains/app-platform/README.md`. Load only the references for surfaces the
change actually reaches.

- Existing scaffold + app-local behavior: use the normal implementation workflow.
  This skill, Core Enablement, exact lane, and Draft state are not prerequisites.
- Missing or changed protected scaffold: stop app-local implementation and produce
  the Core Enablement brief below.

Protected scaffold includes app/feature identity and registration, entitlement/bootstrap,
shell/API composition, generated OpenAPI/client, shared RBAC/data scope, worker
bootstrap/runtime, file/network platform services, and AI workload/capability extension
points.

An app change must not weaken CI, agent policy, checker/exclusion, CODEOWNERS, auth,
generated contracts, or platform registries to make itself pass.

## Core Enablement Brief

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

The core maintainer uses
`.gitlab/merge_request_templates/Core_Enablement.md`. The scaffold must be
independently deployable and hidden/disabled until the named activation change is
ready. Do not inflate an App Sandbox lane into a Core Platform lane.

## Contract Map

For a complex delivery, record only applicable rows in the MR evidence:

| Surface | Contract |
| --- | --- |
| Identity | app/feature id, owner, route, entitlement, existing scaffold |
| Data/auth | scope, authoritative store, transaction/concurrency, retention, read/write roles |
| API/UI | request/response/error, workspace prefix, generated client, i18n/accessibility |
| File/network | parser/type, counted limits, redirect/TLS/active content, cleanup |
| AI | workload id, server app id, route/budget, audit/approval, external-data policy |
| Worker/runtime | import/registration, queue/beat, retry/idempotency, dependencies |
| Migration | current head, metadata, existing-row compatibility, upgrade/rollback |
| Search/retrieval | owner, source ACL, partition, projection fence, lifecycle, backfill/cutover |

Unknown product, permission, retention, destructive, or external-data decisions require
an owner decision; do not infer them.

## Load References By Surface

- App registration/API prefix: `docs/domains/app-platform/README.md`
- Validation depth: `docs/agents/vibe-coding-harness.md`
- AI/LLM: ADR 0002, ADR 0005, then `open-alm-mcp-capability-governance`
- Search/RAG: `docs/domains/retrieval/README.md` and ADR 0009
- UI: `docs/agents/ui-components.md` and product UI principles

Do not load every reference. A linked skill is added only when its own trigger matches
the requested work.

## Invariants

- Enforce entitlement and RBAC on the server.
- Keep shared/authoritative state in the approved DB/object-store contract.
- Use transactions and cover rollback, retry idempotency, concurrency, and cleanup
  order for writes and destructive operations.
- Validate files by observed type/parser behavior and enforce counted limits before
  whole-body reads, decompression, decode, workbook load, or JSON materialization.
- Revalidate external URLs after redirects, block private/link-local/metadata targets,
  keep TLS verification, and serve active content safely.
- Route generative AI through registered workloads and the common execution interface.
  Apps do not select provider/model/pool, call providers directly, or add cross-route
  fallback.
- A queued worker operation is complete only when deployed bootstrap and routing can
  discover it.
- Build migrations from current target head, register model metadata, and preserve
  supported data/workflows.

## Evidence And Delivery

Select affected checks from `docs/agents/vibe-coding-harness.md`; do not run unrelated
full suites. `pnpm ci:harness` alone is not app evidence.

Publish a feature MR through:

```bash
pnpm mr:publish -- --title "<title>" --description-file /tmp/open-alm-mr.md
```

The publisher checks target, clean state, merge result, diff, and lane metadata.
Feature MR CI runs Codex review only; full non-Codex validation runs on the
`dev → main` release MR. Do not substitute direct `glab mr create`, GitLab UI/API,
manual lane, push pipeline, or immediate auto-merge.

Lane is required only when the diff reaches app delivery or another protected
integration boundary. Draft/Ready alone is not a validation or merge condition.
Review evidence is bound to the latest source SHA and target merge result.
