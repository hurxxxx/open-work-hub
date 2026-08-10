---
name: ai-do-production-operations
description: "Operate the AI-DO production checkout safely: render/start/restart/status/smoke, run migrations deliberately, and validate rollback readiness. Use when deploying, restarting, checking, or rolling back production on /projects/ai-do/prod."
---

# AI-DO Production Operations

## Rules

- Run production commands only from `/projects/ai-do/prod`.
- Never use `dev.sh`, `dev:*`, or dev infra commands in the prod checkout.
- Before restart or deploy, verify branch `main`, clean working tree, and production env profile.
- Do not promote by direct `git push origin main`; `main` is protected and production must deploy the merged `origin/main` result from a GitLab MR.
- Do not print secrets from `.env`.
- If production `.env` keys or values are also in scope, add
  `ai-do-env-management` and update the `.env.production` GitLab Secure File
  before restart.
- Production PostgreSQL is native on the server, not Docker. Do not start PostgreSQL containers in production. Required extensions such as `pgvector` must be installed/enabled on the native database before migration; do not change the feature plan to a fallback backend because the extension is missing.

## Workflow

```bash
git -C /projects/ai-do/prod branch --show-current
git -C /projects/ai-do/prod status --short
cd /projects/ai-do/prod
git fetch origin main dev
git pull --ff-only origin main
pnpm check:env-contract
pnpm check:runtime-separation
pnpm check:runtime-separation:live
pnpm prod:deploy -- --dry-run
pnpm prod:deploy
```

`pnpm prod:deploy` is the standard release entrypoint. It validates the checkout and Alembic graph, installs locked dependencies, backs up PostgreSQL, builds web, migrates, verifies the database head, restarts units, runs smoke, executes configured release gates, and runs final smoke. Follow [production deployment layout](../../../docs/domains/release/production-deployment-layout.md) for its fail-closed gate configuration and stop conditions.

## Failure Handling

- If prod health is not `environment=production`, stop and fix env before any further deploy.
- If dev-login appears in prod bootstrap, stop and disable `AI_DO_API_ALLOW_DEV_ADMIN_LOGIN`.
- If deploy smoke fails, let the script's retrying smoke finish before inspecting units and logs.
- For rollback, revert the change on `dev`, promote the revert through a GitLab MR to `main`, update the prod checkout to the resulting `origin/main`, and run `pnpm prod:deploy` again. Do not deploy a detached or arbitrary historical checkout.
