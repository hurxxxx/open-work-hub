# Open Work Hub Agent Rules

## Scope And Context

- `AGENTS.md` is canonical; `CLAUDE.md` and `.github/copilot-instructions.md` are tool bridges.
- Start from the requested outcome and acceptance evidence. Make the smallest complete change and preserve unrelated dirty work.
- Select context in this order: user request -> current diff/code/tests -> closest `AGENTS.md` for every touched path -> exactly matching project skill -> necessary owner doc or accepted root ADR.
- For mixed-path work, read each applicable scoped `AGENTS.md`; do not preload unrelated apps, old plans, raw logs, or whole doc trees.
- Use a project skill only when named or its trigger directly matches. Mentioning another skill does not load it.
- Outside paths are read-only unless explicitly scoped. Resolve exact targets before destructive work.
- Never expose secrets, tokens, `.env` values, production/customer data, raw prompts, or sensitive logs.
- Use typed `OPEN_WORK_HUB_*` settings; never commit `.env`.
- Do not hardcode behavior for one prompt, keyword, field, user, customer, or fixture.

## Git And Delivery

- GitLab `origin` is canonical; GitHub `upstream` is source-only. Never send site changes through GitHub PRs.
- The checkout root contains `dev`, `prod`, and `worktrees/<feature>`; `prod` is reserved for `main` production operations.
- Work in clean `dev` by default. Create a feature branch/worktree under `../worktrees/<slug>` only when the latest request asks for branch, worktree, or MR isolation.
- If `dev` has unrelated dirty work, use a temporary detached `../worktrees/<slug>` from `origin/dev`, integrate only the task diff, then remove it.
- `dev` is the persistent integration branch. Keep it protected and never remove it as the source branch of a `dev -> main` release MR.
- Protected `main` is production. A `dev -> main` MR, merge, production-checkout update, and deploy each require explicit current authorization.
- Commit, push, MR mutation, merge, deploy, and unrelated or force cleanup require explicit current authorization. An authorized MR delivery includes removing only its clean local worktree and verified-merged local branch.
- Leave finished work as an uncommitted diff by default. Keep upstream core updates and site patches in separate commits when commits are requested.
- Never weaken tests, checkers, CI, agent policy, exclusions, auth, or guardrails to make a change pass.

## Platform Boundaries

- Use existing composition roots, registries, manifests, public APIs, generated contracts, and migrations.
- For third-party libraries and external tools, prefer the pinned version's documented configuration, public APIs, extension points, and official headless/lifecycle features. Before adding a wrapper, monkey patch, compatibility shim, or duplicated lifecycle/state logic, verify that the official surface cannot meet the requirement. Keep any necessary adapter narrow, version-pinned, fail-closed, tested, and documented with the specific upstream gap; remove it when an official capability replaces it.
- Shared/auditable state belongs in PostgreSQL or object storage, not UI hiding, browser storage, `/tmp`, process memory, or JSON load-modify-write.
- Server enforcement owns auth, workspace/execution context, runtime app availability, resource ACL, and fail-closed AI write approval.
- External file/URL input needs size, type, scheme, host, redirect, timeout, SSRF, cleanup, and failure boundaries.
- Generative calls use registered workloads and the common execution interface; app code never chooses provider, model, pool, credential, or fallback.
- Retrieval partitions narrow candidates, never authorization; apply source ACL and versioned projection/cutover contracts.

## Validation And Handoff

- Start with focused behavior/contract checks; widen for shared, migration, external, or uncertain blast radius.
- Use `docs/agents/vibe-coding-harness.md` to select checks. CI files and tests own exact job routing.
- MR-only review and release checks apply only to explicitly requested MR/release work.
- Report files changed, commands run, results, skipped checks, and residual risk.

## Documentation And Skills

- Keep one owner per fact and link to it. Do not create parallel current-truth trees, nested ADRs, progress dumps, or raw QA artifacts.
- Keep skills single-purpose and on-demand: concise trigger, boundaries, invariants, workflow, and only necessary resources.

## Parallel Work

- Parallelize independent reads when useful; never delegate secrets, external mutations, destructive work, or overlapping writes.
- The main agent owns scope, integration, edits, validation, and final reporting.
