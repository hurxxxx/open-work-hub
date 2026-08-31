---
name: open-work-hub-production-operations
description: Operate Open Work Hub's guarded production infrastructure and application runtime from the dedicated checkout named `prod`. Use when explicitly checking, deploying, starting, stopping, restarting, smoking, or rolling back production. Do not use for local development or release promotion.
---

# Production Operations

## Boundary

- Owns infra operations through `ops/compose/open-work-hub-prod.infra.yml` and `scripts/infra-stack.sh`.
- Owns app operations through `ops/app/Dockerfile`, `ops/compose/open-work-hub-prod.app.yml`, and `scripts/prod-app.sh`.
- Production checkout basename must be `prod`.
- Production source is GitLab `origin/main`; this skill does not authorize changing it.
- `prod` checkout is a command guard. Do not force `prod` into container/volume/service names when a shared site-named instance can isolate data by database, bucket, index, collection, Redis namespace, or queue group.
- Add separate environment-named instances only for lifecycle, security, capacity, or blast-radius isolation.
- Never run dev commands from prod checkout.
- Do not bypass `scripts/prod-app.sh` with direct app Compose commands; its source, env, migration, revision, smoke, and restoration gates are part of the deploy contract.
- Never print `.env`; use env skill if env changes are scoped.
- App rollback restores the previous image only. It does not reverse migrations.

## Preflight

```bash
test "$(basename "$PWD")" = prod
git branch --show-current
git status --short
pnpm check:env-contract
pnpm infra:prod:status
pnpm app:prod:status
```

Read-only when production inspection is in scope: `pnpm infra:prod:status`, `pnpm app:prod:status`, `pnpm app:prod:smoke`.

Mutating commands require the exact action to be requested: `pnpm infra:prod:up`, `pnpm infra:prod:down`, `pnpm app:prod:deploy`, `pnpm app:prod:rollback`, or `pnpm app:prod:up`. A deploy includes image build, migration, runtime replacement, and local/public smoke; do not split or skip those gates.
