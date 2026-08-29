# Open Work Hub Agent Rules

## Scope

- `AGENTS.md` is canonical. `CLAUDE.md` and `.github/copilot-instructions.md` are bridges.
- Make the smallest change that satisfies the user. Preserve unrelated dirty work.
- Outside paths are read-only unless explicitly scoped. Confirm exact target before destructive work.
- Never expose secrets, tokens, `.env` values, production/customer data, raw prompts, or sensitive logs.
- Use typed settings and `OPEN_WORK_HUB_*`; never commit `.env`.
- Do not hardcode behavior for one question, keyword, field, user, customer, or example.

## Context Routing

- Start with user request, current code, and tests. Read only owner docs/ADRs for the touched surface.
- Do not load unrelated apps, old plans, raw logs, or whole doc trees by inertia.
- Use a project skill only when its trigger matches or the user names it.

| Surface                   | Owner                                                                                                                      |
| ------------------------- | -------------------------------------------------------------------------------------------------------------------------- |
| Code shape/abstraction    | `docs/agents/llm-friendly-development.md`, `docs/agents/composable-abstractions.md`                                        |
| Validation/MR/Codex       | `docs/agents/vibe-coding-harness.md`, `docs/agents/local-codex-review.md`                                                  |
| Docs ownership            | `docs/agents/domain.md`                                                                                                    |
| GitLab issue triage       | `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md`                                                             |
| App identity/registration | `docs/domains/app-platform/README.md`                                                                                      |
| Indexed source auth       | `docs/domains/source-access/README.md`                                                                                    |
| Content delivery          | `docs/domains/content-access/README.md`                                                                                    |
| Global notifications      | `docs/domains/notifications/README.md`                                                                                     |
| Recording pipeline        | `docs/apps/recording/README.md`                                                                                            |
| UI/time/feedback          | `docs/agents/ui-components.md`, `docs/product/ui-design-principles.md`                                                     |
| AI/MCP/LLM                | `adr/0002-mcp-capability-platform.md`, `adr/0005-registered-llm-workload.md`, `docs/domains/ai/README.md`                  |
| Retrieval/RAG             | `docs/domains/retrieval/README.md`, `docs/domains/rag/README.md`, `adr/0009-retrieval-partition-projection-generations.md` |
| Runtime/deploy            | `README.md`, `docs/domains/release/README.md`, relevant operations skill                                                   |

## Git

- GitLab `origin` is the site canonical remote. GitHub `upstream` is source-only.
- Do not push site changes to GitHub or manage them with GitHub PRs.
- Work on `dev` unless the latest user request names another branch. Do not create a persistent branch, worktree, or MR for routine work.
- If the `dev` checkout has unrelated dirty work, preserve it and use a temporary detached worktree from `origin/dev`; remove it after handoff.
- Protected `main` is production. Creating or merging a `dev -> main` MR, updating `main` or the production checkout, and deploying each require an explicit latest-user request.
- No commit, push, MR mutation, merge, or destructive cleanup unless the latest user request explicitly asks for that operation.
- Finished work stays as an uncommitted diff by default; do not "helpfully" commit or push after implementation.
- Keep upstream core updates and site custom patches in separate commits.
- Do not weaken tests, checkers, CI, agent policy, exclusions, auth, or guardrails to pass a feature.

## Platform

- Use existing composition roots, registries, manifests, public APIs, generated contracts, and migrations.
- Runtime service names use site identity, not environment, when one physical instance can isolate data by DB/schema/bucket/index/collection/queue namespace. Create separate dev/prod instances only for incompatible lifecycle, security, capacity, or blast-radius needs.
- Web app surfaces stay under `apps/web/src/app-modules/<appId>/`; expose only manifest, public API, or bootstrap DTO.
- FastAPI routers are assembled by `open_work_hub_api.api_registry`.
- API contract changes require generated client regeneration when `pnpm check:api-contract` demands it.
- New DB schema changes require Alembic migration.
- User-facing copy keeps `ko-KR` and `en-US` aligned.
- Shared/auditable state lives in PostgreSQL/object storage, not UI hiding, local storage, `/tmp`, process memory, or JSON load-modify-write.
- Server enforces auth, declared execution context, runtime app availability, resource ACL, and AI
  write approval fail-closed.
- External file/URL input needs size/type/scheme/host/timeout/SSRF/cleanup boundaries and failure tests.
- Generative LLM calls use registered `RegisteredLlmWorkload` plus common execution interface. App code never selects provider/model/pool/credential or direct SDK/HTTP.
- Retrieval partition is candidate scope, not authorization. Apply the Source Access contract,
  stable identity, versioned projection/outbox, and ADR 0009 cutover rules.

## Validation

- Pick checks by changed surface. Start focused; widen only for shared, migration, external, or uncertain blast radius.
- MR-only review and release jobs apply only to explicitly requested MR work; the CI contract owns their exact routing.
- CI contract source: `.gitlab-ci.yml`, `ops/ci/ci-first.gitlab-ci.yml`, `scripts/check-gitlab-pipeline.mjs`.

| Change             | Baseline checks                                                                                   |
| ------------------ | ------------------------------------------------------------------------------------------------- |
| Docs/skills/policy | `git diff --check`, `pnpm check:skills`                                                           |
| GitLab CI/harness  | `pnpm check:gitlab-pipeline`, `pnpm ci:harness`                                                   |
| Web/UI/i18n        | focused Vitest, `pnpm check:web-architecture`, `pnpm nx typecheck web`                            |
| API/OpenAPI        | focused pytest, `pnpm check:api-architecture`, `pnpm check:api-contract`                          |
| DB migration       | `pnpm check:alembic-graph`, `pnpm test:alembic-graph`, optional `pnpm nx run api:test-migrations` |
| Worker             | focused worker pytest, `pnpm nx lint worker`                                                      |
| Env/runtime        | `pnpm check:env-contract`, `pnpm check:path-hardcoding`                                           |
| AI capability      | registry/invoke/ACL/direct-call tests plus ADR 0002/0005                                          |
| Browser flow       | `pnpm e2e:shell` or local login browser smoke                                                     |
| Release-scale risk | justified `pnpm ci:all`                                                                           |

API/worker focused tests:

```bash
(cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/<file>.py -q)
(cd apps/worker && uv run --python 3.12 --group dev python -m pytest tests/<file>.py -q)
```

Report commands run, results, skipped validation, and residual risk.

## Docs And Skills

- Keep docs AI-readable: commands, contracts, invariants, owner links. Remove narrative, history, and tutorial prose unless it prevents wrong implementation.
- One owner per fact. Link instead of copying decisions.
- No parallel current-truth trees, nested ADRs, progress dumps, raw QA artifacts, or duplicated tool rules.
- `SKILL.md` keeps trigger, scope, invariants, minimal workflow, resource routing. Move only necessary detail to linked references/scripts.

## Parallel Work

- Parallelize independent read/audit/log work when useful. Do not delegate secrets, external mutations, destructive work, or overlapping writes.
- Main agent owns scope, integration, edits, validation, and final report.
