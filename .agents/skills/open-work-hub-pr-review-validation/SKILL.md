---
name: open-work-hub-pr-review-validation
description: Review an Open Work Hub GitHub pull request for mergeability, regressions, and project-contract risk. Use when the user explicitly asks to review a PR, decide whether it is safe to merge, or address existing PR findings. Do not use for ordinary implementation, local code reading, or an unrequested pre-commit self-review.
---

# Open Work Hub Pull Request Review Validation

Treat a PR as a contract-change proposal. Lead with concrete findings ordered by severity and cite files and lines.

## Establish the Review Target

1. Read `AGENTS.md`, current code/tests, affected owner documents, and relevant accepted ADRs.
2. Use `gh pr view <number> --json baseRefName,headRefName,headRefOid,mergeable,mergeStateStatus,statusCheckRollup` and `gh pr diff <number>` for current metadata and diff.
3. Compare against the PR base branch, not only the checked-out working tree. Record the reviewed head SHA.
4. Do not checkout, edit, comment, approve, merge, or push unless the user explicitly requested that mutation. Use a clean dedicated worktree if source-branch edits are in scope.

## Review Lens

- Contract: API schemas/routes, OpenAPI output, generated clients, migrations, env keys, persisted data, i18n, and public TypeScript types.
- Platform: app manifests, workspace API prefixes, router composition, registries, LLM workloads, approval gates, audit/tracing, and discoverability.
- Security: authorization is enforced server-side; no secret, unsafe upload/preview, SSRF, unbounded input, or sensitive prompt/log leakage.
- Architecture: app-module and import boundaries, existing extension points, state ownership, accessible UI, stable keys, and useful test seams.
- Data/runtime: transactions, concurrency, retention, cleanup, task registration, queue routing, locked dependencies, migration compatibility, and rollback.
- Delivery scope: do not weaken checkers, exclusions, auth, generated contracts, or platform registries merely to make the PR pass.

## Affected Validation

Choose focused checks from `docs/agents/vibe-coding-harness.md`:

- API/domain: `pnpm check:python-source-integrity` plus focused API pytest files.
- Registry/LLM/AI: focused `test_platform_adapter_registries.py`, `test_ai_gateway_direct_call_guard.py`, and capability tests.
- OpenAPI: `pnpm check:api-contract`.
- Env: `pnpm check:env-contract`.
- API architecture: `pnpm check:api-architecture`.
- Migration: `pnpm check:alembic-graph` plus focused upgrade/model tests.
- Web/app module: `pnpm check:web-architecture` and affected Nx typecheck/test targets.
- Shared contracts: `pnpm ci:contract` when the contract package or generated API surface changes.
- Critical user flow: the relevant Playwright/E2E or login smoke.

Do not claim a check passed unless it ran for the reviewed SHA or equivalent merge result.

## Merge Decision

A PR is merge-ready only when the latest head SHA was reviewed, mergeability is clean, required checks pass, contract/security findings are resolved, and remaining risk is named. A green generic harness never substitutes for affected API, web, worker, migration, or browser evidence.
