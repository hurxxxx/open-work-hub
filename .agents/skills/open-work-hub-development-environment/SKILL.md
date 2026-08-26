---
name: open-work-hub-development-environment
description: Set up and operate the Open Work Hub local Node/Python/Docker Compose development environment. Use when onboarding, installing dependencies, starting or stopping local services, checking local ports, or choosing the minimal/full dev stack. Do not use for production infrastructure or application deployment.
---

# Development Environment

## Contract

- Local stack: Node 22+, pnpm 10.33.0, Python 3.12 + `uv`, Docker Compose.
- Env prefix: `OPEN_WORK_HUB_*`; copy `.env.example` to ignored `.env`; never print secrets.
- Full infra: `ops/compose/open-work-hub-dev.infra.yml`.
- Minimal infra: PostgreSQL + Redis; disables storage/AI/search/video/RAG startup deps.
- Defaults: Web `127.0.0.1:4200`, API `127.0.0.1:8001`.
- No shared-server, internal-network, OS-specific, native-DB-only, or fixed-checkout assumptions.

## Commands

```bash
cp .env.example .env
pnpm install --frozen-lockfile
pnpm dev:infra:up
pnpm dev
pnpm dev:minimal
pnpm dev:login-smoke
pnpm e2e:install
pnpm dev:login-browser-smoke
./dev.sh --status
./dev.sh --restart
./dev.sh --stop
```

## Checks

- Env semantics: `pnpm check:env-contract`.
- Runtime paths: `pnpm check:path-hardcoding`.
- Migration drift: inspect; do not stamp/delete to bypass.
- Production operations belong to `open-work-hub-production-operations`.
