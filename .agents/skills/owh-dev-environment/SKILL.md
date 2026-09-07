---
name: owh-dev-environment
description: Use when setting up dependencies or operating the local dev stack. Covers minimal/full services and local smoke checks; excludes production operations and env-contract changes.
---

# Development Environment

## Contract

- Local stack: Node + pnpm, Python + `uv`, Docker Compose.
- Read versions from root `package.json` and Python project files. Initialize ignored `.env` only if absent; preserve existing values.
- Full infra: `ops/compose/open-work-hub-dev.infra.yml`.
- Minimal infra: PostgreSQL + Redis; disables storage/AI/search/video/RAG startup deps.
- Defaults: Web `127.0.0.1:4200`, API `127.0.0.1:8001`.
- No shared-server, internal-network, OS-specific, native-DB-only, or fixed-checkout assumptions.

## Commands

```bash
bash .agents/skills/owh-env-contracts/scripts/local-env-files.sh status --source .env.example --target .env
# Only for requested setup and status=missing_target:
bash .agents/skills/owh-env-contracts/scripts/local-env-files.sh install --source .env.example --target .env
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
- Production operations belong to `owh-production`.
