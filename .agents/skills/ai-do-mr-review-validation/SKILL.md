---
name: ai-do-mr-review-validation
description: Review AI-DO GitLab merge requests for mergeability and project contract risk. Use when the user explicitly asks to review an MR, decide whether it can merge, or address existing MR review findings. Do not use for ordinary implementation, local code reading, or a pre-commit self-review.
---

# AI-DO MR Review Validation

## Goal

Treat an MR as a contract change proposal. Prove it preserves existing behavior,
uses the platform/framework extension points correctly, and is safe to merge.

## Start

1. Read root `agents.md` and any domain/app ADRs or docs touched by the MR.
2. Inspect MR metadata: target/source branches, pipeline, mergeability, conflicts,
   blocking discussions, labels, and latest source SHA. Require a lane only when the
   target-approved classifier says the diff reaches app delivery, protected platform,
   migration/generated/shared runtime, or mixed integration. Draft/Ready and a missing
   lane on a low-risk profile are not blockers.
3. Compare against the target branch, not only the source branch working tree.
4. On `/projects/ai-do/dev`, keep the checkout on `dev`. Add the worktree skill only
   when changing the MR source branch or performing branch/worktree operations.

## Review Lens

Lead with bugs and merge blockers. Order findings by severity and cite files/lines.

- Contract: API schemas, OpenAPI output, route paths, generated clients, database
  migrations, env variables, persisted data, i18n keys, and public TypeScript types.
- Platform: app manifests, workspace API prefixes, FastAPI router composition,
  platform extension registries, LLM task budgets, AI capability registration,
  approval gates, audit/tracing, and discoverability predicates.
- Framework: React state ownership, hooks, accessibility, stable keys, app-module
  boundaries, generated artifacts, import boundaries, and test seams.
- Security: no secrets in code, docs, logs, prompts, fixtures, or review comments.
- Delivery boundary: a vibe-coded App Sandbox MR must stay inside a pre-existing
  core scaffold. Missing app registration, entitlement, API composition, generated
  contract, shared RBAC/data scope, worker bootstrap, or AI extension points require
  a separate core-enablement brief/MR, not self-escalation in the feature MR.
- File upload/preview security: server-side validation must not trust filename or
  client MIME alone; active formats must be sandboxed, sanitized, or served as
  attachment rather than same-origin inline content.
- Resource limits: user-supplied or upstream-fetched files, archives, crawl batches,
  and AI/tool payloads need explicit per-item and/or total caps; large binary batches
  should stream or persist incrementally instead of accumulating whole runs in memory.
  Limits must apply before whole-body reads, decompression, image/workbook decoding,
  or JSON materialization and must count missing-length or chunked input.
- UX: changed workflows remain reachable, translated, responsive, and keyboard usable.
- Data lifecycle: authoritative/shared state uses the approved database/object-store
  boundary with transactions, concurrency control, retention, safe cleanup order,
  compatibility, and rollback; process locks, `/tmp`, and JSON load-modify-write are
  not shared persistence.
- Runtime reachability: workers import/register each task in deployed bootstrap,
  queue/beat routing is covered, frozen dependencies are present, and executable/path
  discovery works on production Linux.

## Refactor Rules

Refactor only when it removes a merge risk, restores a contract, or makes the MR use
the intended platform seam. Keep unrelated cleanup out of the MR.

- Preserve public contracts by default. If a contract must change, make it explicit in
  the MR evidence, update callers, regenerate generated files, and add compatibility
  or migration tests.
- Prefer existing registries, adapters, manifests, generated clients, domain services,
  and shared helpers over local bypasses.
- Do not work around platform validation with service-local constants or duplicate
  wiring; fix the registry/profile/manifest contract instead.
- Reject feature changes that weaken CI, agent rules, checkers, exclusions, or
  CODEOWNERS to make themselves pass. Route genuine harness changes separately.
- Keep domain modules independent of API composition roots.
- Keep web app screens, routes, app APIs, and sidebar entries inside their app module
  unless the app public root or manifest intentionally exposes them.
- Add or adjust tests at the interface where callers depend on the behavior.

## Verification Matrix

Feature MR CI provides Codex review rather than affected validation jobs. Use local
evidence already supplied by the author when needed; full non-Codex verification is
owned by the `dev → main` release pipeline:

- API/domain/router/LLM change:
  `pnpm check:python-source-integrity`, then
  `cd apps/api && uv run --python 3.12 --group dev python -m pytest <targeted-tests> -q`
- Platform registries, LLM tasks, providers, adapters, search, RAG, or AI tools:
  `cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/test_platform_adapter_registries.py -q`
- OpenAPI or API request/response change:
  `pnpm check:api-contract`
- Settings or environment variable contract change:
  `pnpm check:env-contract`
- API architecture/import/i18n change:
  `pnpm check:api-architecture`
- Worker task, queue, beat, or scheduler change:
  run the affected worker tests, including task bootstrap/registration coverage.
- Migration change: run `pnpm check:alembic-graph`, then single-head, upgrade, and
  drift validation in the API environment; verify model metadata registration.
- Web route/view/app-module/API client change:
  `pnpm nx typecheck web && pnpm check:web-architecture`
- Workspace API prefix or app API policy change:
  `pnpm nx test web src/platform/api/workspace-api-path-policy.spec.ts`
- Cross-app, shell, navigation, or critical user workflow change:
  run the relevant browser/E2E smoke and capture the outcome.
- File/network feature: test disguised and malformed input, per-item and aggregate
  resource caps, decompression/pixel/body limits as applicable, safe download/inline
  behavior, redirect-aware SSRF blocking, TLS verification, and failure cleanup.
- AI feature: verify gateway/task registration, server-selected `app_id`, local and
  external budgets, audit/tracing, approval, and user-visible external-data policy.

## Merge Decision

Say an MR is merge-ready only when:

- latest source SHA is reviewed and validated,
- pipeline diff base and source SHA match the recorded MR evidence; source changes
  invalidate affected checks/review, while target movement alone does not require
  source-branch ancestry and only requires affected checks when the merged surface
  changes,
- target-branch merge simulation or GitLab mergeability is clean,
- required discussions are resolved,
- the latest feature MR Codex gate is green,
- affected contract/platform/framework checks passed,
- remaining risks are named clearly.

For domain app work, require the completed
`.gitlab/merge_request_templates/Vibe_Domain_App.md` evidence. A green
`pnpm ci:harness` alone is never sufficient because it does not replace affected
API, contract, web, worker, migration, or browser checks.
