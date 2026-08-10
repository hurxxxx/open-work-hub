# Open ALM

Open ALM is a modular application lifecycle management platform. It brings planning,
workspaces, tasks, documents, meetings, files, search, and AI-assisted workflows into
one extensible product.

## Architecture

- `apps/web`: React and Vite web application
- `apps/api`: FastAPI application and database migrations
- `apps/worker`: background jobs and asynchronous workflows
- `apps/ops`: operational APIs and administration tools
- `packages`: shared contracts, UI components, and web platform code
- `ops`: container and deployment definitions

The default development stack uses PostgreSQL, Redis, MinIO, OpenSearch, and Qdrant.
Optional AI and media services can be enabled through environment settings.

## Requirements

- Node.js 22 or later
- pnpm 10.33.0
- Python 3.12 and `uv`
- Docker with Compose

## Local development

```bash
cp .env.example .env
pnpm install --frozen-lockfile
pnpm dev:infra:up
pnpm dev
```

The web application listens on `http://127.0.0.1:4200` by default. Runtime settings
use the `OPEN_ALM_*` prefix; adjust `.env` for services that are not running locally.

Useful checks:

```bash
pnpm check:project-version
pnpm check:path-hardcoding
pnpm check:python-source-integrity
pnpm nx run-many -t typecheck --all
```

See [`docs/README.md`](./docs/README.md) for architecture and domain documentation.

## Security

Never commit `.env`, credentials, production data, customer documents, or generated
backups. Keep only safe placeholders in `.env.example` and report security issues
privately to the repository owner.

## Status

Open ALM is being generalized from an internal application into an independent ALM
project. Interfaces and deployment contracts may change while this work is in progress.
