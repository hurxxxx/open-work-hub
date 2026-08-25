---
name: open-work-hub-production-operations
description: Operate Open Work Hub's production Docker Compose infrastructure from a dedicated checkout named `prod`. Use when explicitly checking, starting, stopping, or restarting production infrastructure. Do not use for local development or full application deployment; this repository currently has no application deploy entrypoint.
---

# Open Work Hub Production Operations

## Current Boundary

- Production source currently owns infrastructure Compose only: `ops/compose/open-work-hub-prod.infra.yml` through `scripts/infra-stack.sh`.
- There is no repository command that builds, migrates, restarts, smokes, or rolls back the full application. Do not invent one or substitute a hand-assembled deployment.
- Production commands are refused unless the checkout basename is exactly `prod` (except an explicit one-off override intended for diagnostics).
- Never run `dev.sh` or development infra commands from the production checkout.
- Never print `.env` values. If env changes are separately in scope, also use `open-work-hub-env-management`.

## Read-Only Preflight

From the dedicated production checkout:

```bash
test "$(basename "$PWD")" = prod
git branch --show-current
git status --short
pnpm check:env-contract
pnpm infra:prod:status
```

Require branch `main`, a clean worktree before an operational change, an ignored production `.env`, and explicit confirmation of the intended infrastructure action.

## Authorized Infrastructure Actions

```bash
pnpm infra:prod:up
pnpm infra:prod:status
```

`pnpm infra:prod:down` stops and removes Compose containers and is destructive to availability; run it only when the user explicitly requests that exact action and the persistence/backup impact is understood. Use `bash scripts/infra-stack.sh prod restart <service>` only when the affected service is named and restart is explicitly authorized.

## Stop Conditions

Stop when the checkout is not named `prod`, branch/worktree state is unexpected, `.env` ownership is unclear, migration or application rollout is required, rollback is undefined, or the requested operation exceeds infrastructure Compose. Report that a deployment runbook/entrypoint is missing instead of improvising.
