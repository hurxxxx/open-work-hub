---
name: open-work-hub-production-operations
description: Operate Open Work Hub's production Docker Compose infrastructure from a dedicated checkout named `prod`. Use when explicitly checking, starting, stopping, or restarting production infrastructure. Do not use for local development or full application deployment; this repository currently has no application deploy entrypoint.
---

# Production Operations

## Boundary

- Owns infra Compose only: `ops/compose/open-work-hub-prod.infra.yml`, `scripts/infra-stack.sh`.
- No full app build/migrate/restart/smoke/rollback command exists.
- Production checkout basename must be `prod`.
- Production source is GitLab `origin/main`; this skill does not authorize changing it.
- `prod` checkout is a command guard. Do not force `prod` into container/volume/service names when a shared site-named instance can isolate data by database, bucket, index, collection, Redis namespace, or queue group.
- Add separate environment-named instances only for lifecycle, security, capacity, or blast-radius isolation.
- Never run dev commands from prod checkout.
- Never print `.env`; use env skill if env changes are scoped.

## Preflight

```bash
test "$(basename "$PWD")" = prod
git branch --show-current
git status --short
pnpm check:env-contract
pnpm infra:prod:status
```

Allowed: `pnpm infra:prod:up`, `pnpm infra:prod:status`. `pnpm infra:prod:down` or service restart requires explicit exact request.
