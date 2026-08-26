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
| UI/time/feedback          | `docs/agents/ui-components.md`, `docs/product/ui-design-principles.md`                                                     |
| AI/MCP/LLM                | `adr/0002-mcp-capability-platform.md`, `adr/0005-registered-llm-workload.md`, `docs/domains/ai/write-policy.md`            |
| Retrieval/RAG             | `docs/domains/retrieval/README.md`, `docs/domains/rag/README.md`, `adr/0009-retrieval-partition-projection-generations.md` |
| Runtime/deploy            | `README.md`, `docs/domains/release/README.md`, relevant operations skill                                                   |

## Git

- GitLab `origin` is the site canonical remote. GitHub `upstream` is source-only.
- Do not push site changes to GitHub or manage them with GitHub PRs.
- Site integration branch: `dev`. Production branch: protected `main`.
- Feature flow: feature branch -> GitLab MR to `dev`. Release flow: `dev` -> GitLab MR to `main`.
- No commit, push, MR, merge, branch switch, or destructive cleanup unless requested.
- Keep upstream core updates and site custom patches in separate commits.
- Do not weaken tests, checkers, CI, agent policy, exclusions, auth, or guardrails to pass a feature.

## Platform

- Use existing composition roots, registries, manifests, public APIs, generated contracts, and migrations.
- Web app surfaces stay under `apps/web/src/app-modules/<appId>/`; expose only manifest, public API, or bootstrap DTO.
- FastAPI routers are assembled by `open_work_hub_api.api_registry`.
- API contract changes require generated client regeneration when `pnpm check:api-contract` demands it.
- New DB schema changes require Alembic migration.
- User-facing copy keeps `ko-KR` and `en-US` aligned.
- Shared/auditable state lives in PostgreSQL/object storage, not UI hiding, local storage, `/tmp`, process memory, or JSON load-modify-write.
- Server enforces auth, workspace, entitlement, app visibility, resource ACL, and AI write approval fail-closed.
- External file/URL input needs size/type/scheme/host/timeout/SSRF/cleanup boundaries and failure tests.
- Generative LLM calls use registered `RegisteredLlmWorkload` plus common execution interface. App code never selects provider/model/pool/credential or direct SDK/HTTP.
- Retrieval partition is candidate scope, not authorization. Apply source ACL, stable identity, versioned projection/outbox, and ADR 0009 cutover rules.

## Validation

- Pick checks by changed surface. Start focused; widen only for shared, migration, external, or uncertain blast radius.
- Feature MR CI owns Codex review. `dev -> main` release MR owns non-Codex validation.
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
cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/<file>.py -q
cd apps/worker && uv run --python 3.12 --group dev python -m pytest tests/<file>.py -q
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
