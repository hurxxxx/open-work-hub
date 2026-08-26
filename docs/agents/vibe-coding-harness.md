# Vibe Coding Harness

Pick validation by changed surface. Current code/tests plus owner docs are source; CI scripts/tests own exact automation behavior.

## Context

1. Inspect request, working tree/diff, current code, and tests.
2. Select touched surfaces below.
3. Read only matching owner docs/ADRs.
4. Verify referenced paths/scripts exist before citing them.

## Protected Surfaces

Separate app-local work from platform enablement when touching:

- app/feature identity, manifest, entitlement, bootstrap
- shell route/nav, protected API composition, OpenAPI/generated client
- shared RBAC/data/table, worker runtime
- file/network platform pipeline
- AI capability/workload route/budget/audit/approval
- migration, CI, agent policy, checker, architecture guardrail

No app-local bypass, checker exclusion, or local allowlist for missing platform scaffold.

## Contract Map

Record only applicable rows in MR evidence.

| Surface | Must state |
| --- | --- |
| Identity/route | app/feature ID, owner, route context, availability, entitlement |
| Data/auth | scope, authoritative store, transactions, retention, read/write roles |
| API/UI | request/response/error, workspace prefix, OpenAPI/client, i18n, a11y, time/stale state |
| File/network | type/size/decompression, redirect/TLS/active content, cleanup |
| AI | workload ID, route/budget, audit/approval, external-data policy |
| Worker/runtime | import/registration, queue/beat, retry/idempotency |
| Migration | target head, model metadata, existing-row compatibility, rollback |
| Search/retrieval | owner, ACL, partition, projection/outbox, backfill/cutover/rollback |

## Router

| Change | Owner | Minimum checks |
| --- | --- | --- |
| Docs/skills/policy | current file owner | `git diff --check`; `pnpm check:skills` if skills/policy |
| Translation | i18n catalog | `pnpm check:i18n` |
| Env/runtime | env settings/compose/scripts | `pnpm check:env-contract`, `pnpm check:path-hardcoding` |
| Web app-local | app module/UI owner | `pnpm check:web-architecture`, `pnpm nx typecheck web`, focused Vitest |
| API/domain | domain router/service/tests | `pnpm check:api-architecture`, focused pytest |
| OpenAPI/generated | API contract | `pnpm check:api-contract`; generate client when required |
| Worker | worker task owner | focused worker pytest, registration check |
| Migration/model | Alembic/model owner | `pnpm check:alembic-graph`, migration test |
| File/network | parser/service/security tests | malformed/oversized/redirect/failure-cleanup tests |
| AI capability | AI registry/ADR 0002/0005 | registry/direct-call/invoke/ACL tests |
| Search/RAG | Retrieval/RAG/ADR 0009 | ACL/projection/source/quality tests |

Focused commands:

```bash
pnpm --dir apps/web exec vitest run <path>
cd apps/api && uv run --python 3.12 --group dev python -m pytest <path> -q
cd apps/worker && uv run --python 3.12 --group dev python -m pytest <path> -q
```

Use `pnpm ci:app-api-contracts`, `pnpm ci:app-web-contracts`, or `pnpm ci:all` only when the changed surface justifies broad validation.

## MR Flow

- Feature MR target: GitLab `dev`; same user outcome stays in one MR.
- Release MR target: `main` from `dev`; non-Codex validation lives there.
- Codex feature MR job checks only review/freshness/merge/evidence gates.
- Source change requires affected evidence refresh. Target change requires rechecking merged surface when it changes.
- Future publisher/CI gates are not evidence until implemented.
- Use `open-work-hub-mr-review-validation` only when review/merge decision is requested.

## Stop

- old plans/other repos treated as current source
- platform/security/AI/retrieval boundary bypass
- feature diff weakens policy/checker/CI/test to pass itself
- secrets, production data, destructive migration, or large deletion without scope
