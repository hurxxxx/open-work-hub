---
name: open-work-hub-development-environment
description: Set up and operate the Open Work Hub local Node/Python/Docker Compose development environment. Use when onboarding, installing dependencies, starting or stopping local services, checking local ports, or choosing the minimal/full dev stack. Do not use for production infrastructure or application deployment.
---

# Open Work Hub Development Environment

## Local Model

- The supported repository workflow is local: Node.js 22+, pnpm 10.33.0, Python 3.12 with `uv`, and Docker Compose.
- Runtime settings use `OPEN_WORK_HUB_*`. Copy `.env.example` to ignored `.env`; never commit or display its secret values.
- The full dev stack uses the Docker services described in `ops/compose/open-work-hub-dev.infra.yml`.
- `dev:minimal` starts PostgreSQL and Redis only and disables storage, AI, search, video, and RAG startup dependencies.
- The web defaults to `http://127.0.0.1:4200`; the API defaults to `http://127.0.0.1:8001` with docs at `/docs`.
- Do not carry forward shared-server, OS-specific, internal-network, native-database-only, or fixed absolute-checkout assumptions.

## First Setup

```bash
cp .env.example .env
pnpm install --frozen-lockfile
pnpm dev:infra:up
pnpm dev
```

For authentication and core UI work:

```bash
pnpm dev:minimal
pnpm dev:login-smoke
```

Install Chromium once before the browser login smoke:

```bash
pnpm e2e:install
pnpm dev:login-browser-smoke
```

## Operations

```bash
./dev.sh --status
pnpm infra:dev:status
pnpm dev:infra:minimal:status
./dev.sh --restart
./dev.sh --stop
pnpm dev:infra:down
```

Use `pnpm dev:infra:minimal:down` to stop only minimal containers. Inspect `./dev.sh --help` before selecting web-only, API-only, worker, or no-infra modes.

## Verification and Safety

- Run `pnpm check:env-contract` after changing env semantics and `pnpm check:path-hardcoding` after changing runtime paths.
- `dev.sh` performs an Alembic preflight when auto-migration is enabled. Do not stamp or delete database objects to bypass drift. Inspect migration history and data before any repair.
- Do not run production Compose commands from a normal checkout. Production infrastructure is owned by `open-work-hub-production-operations`.
