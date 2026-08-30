# Open Work Hub

Modular ALM platform: workspaces, tasks, docs, meetings, files, search, and AI-assisted workflows.

## Layout

- `apps/web`: React/Vite app
- `apps/api`: FastAPI app and Alembic migrations
- `apps/worker`: Celery workers
- `packages`: shared contracts/UI/core-web
- `ops`: Compose and deployment assets

## Requirements

- Node.js 22+
- pnpm 10.33.0
- Python 3.12 + `uv`
- Docker Compose

## Dev

```bash
cp .env.example .env
pnpm install --frozen-lockfile
pnpm dev:infra:up
pnpm dev
```

- Web default: `http://127.0.0.1:4200`
- API default: `http://127.0.0.1:8001`
- Runtime env prefix: `OPEN_WORK_HUB_*`

Minimal auth/UI stack:

```bash
pnpm dev:minimal
pnpm dev:login-smoke
pnpm e2e:install
pnpm dev:login-browser-smoke
```

Full-stack public-domain user acceptance uses the current development data and real dependencies.
Keep the first command running, then execute the preflight in another terminal before opening
isolated `agent-browser` sessions:

```bash
./dev.sh --with-worker --restart
OPEN_WORK_HUB_UAT_BASE_URL=https://your-public-dev-domain.example pnpm uat:preflight
```

The repeatable personas, state restoration rules, and expected evidence are owned by
[Core Platform User Acceptance](./docs/product/core-platform-user-acceptance.md).

Seed account: `administrator` / `open-work-hub-dev-only`. Dev/minimal settings are rejected by preview/prod.

## Checks

```bash
pnpm check:project-version
pnpm check:path-hardcoding
pnpm check:python-source-integrity
pnpm check:skills
pnpm nx run-many -t typecheck --all
```

## Agent Rules

Coding agents must read [AGENTS.md](./AGENTS.md). Docs index: [docs/README.md](./docs/README.md).

## Security

Never commit `.env`, credentials, production data, customer documents, or generated backups. Keep safe placeholders in `.env.example`.
