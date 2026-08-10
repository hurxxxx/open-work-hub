---
name: ai-do-runtime-separation-audit
description: Audit AI-DO prod/dev runtime separation across env files, ports, services, containers, and health endpoints. Use when the user requests a separation audit or a change actually alters prod/dev runtime identity, ports, units, compose topology, or health routing. Do not use automatically for every env or deploy-script edit.
---

# AI-DO Runtime Separation Audit

This skill audits runtime separation. Add `ai-do-env-management` only when the
task also changes or synchronizes `.env` or GitLab Secure Files.

## Workflow

1. Run redacted checks only:
   ```bash
   pnpm check:env-contract
   pnpm check:runtime-separation
   pnpm check:path-hardcoding
   ```
2. On the server, with prod/dev services running, run:
   ```bash
   pnpm check:runtime-separation:live
   ```
3. Confirm prod health reports `environment=production` and `instance_id=prod-api`.
4. Confirm dev health reports `environment=development` on dev ports only.
5. Confirm prod bootstrap never exposes dev-login.
6. Do not print `.env` values; report key names, expected profiles, and redacted status only.

## Expected Shape

- Prod checkout: `/projects/ai-do/prod`, branch `main`, production env, `ai-do-prod-*` units.
- Dev checkout: `/projects/ai-do/dev`, branch `dev`, `AI_DO_ENV_PROFILE=dev`, development env, `ai-do-dev-*` infra.
- No preview VM harness, no unapproved app/infra port collision, and no dev nginx upstream to port `8000`.
- Shared dependencies are allowed only when an owner runbook defines the boundary. Current explicit shared services are the native PostgreSQL listener on `127.0.0.1:5432` with separate databases and `ai-do-privacy-filter.service` on `127.0.0.1:18081`.
