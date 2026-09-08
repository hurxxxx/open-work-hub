# API App

FastAPI composition layer for health, auth, app bootstrap, domains, AI Gateway, retrieval/search, OpenAPI, and Alembic migrations.

## Dev

```bash
./dev.sh --api-only
```

- Default API port: `8001`
- Runtime env contract: root `.env.example` plus ignored `.env`
- Do not commit secrets or operations data.
- Readiness: `curl http://127.0.0.1:8001/readyz`
- Authenticated AI health: `/api/v1/chatbot/health`
- Executable app routes require the current user, declared execution context, and owning-app
  company app admission before domain source ACL is evaluated. Core platform features retain
  their explicit account and source permissions. PMS spaces are app-owned resources; they never
  become a global execution context.
- App bootstrap, route, and availability ownership: [App Platform Contract](../../docs/domains/app-platform/README.md).
- Authenticated byte delivery: [Content Access](../../docs/domains/content-access/README.md).

## LLM

- Local and external pools are selected by registered workload plus admin override.
- No local-to-external automatic fallback.
- Local runtime contract: [AI Gateway](../../docs/domains/ai/gateway.md).
- vLLM/mlx endpoints must stay private; they do not provide app auth.
- External provider API keys are stored encrypted through Admin, not ordinary env variables.
- Env stores only `OPEN_WORK_HUB_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY` for credential encryption.
- Personal mlx-lm helper:

```bash
MLX_MODEL=org/local-model-id bash scripts/mlx-serve.sh
```

## Alembic

- Alembic owns schema. Do not reintroduce `Base.metadata.create_all()` or hand SQL compatibility lists.
- Baseline revision: `company_20260908` (`company users, groups and app-owned access schema`).
  Previous schemas and data are unsupported; upgrading an old product database is not a migration path.
  See the [release cutover procedure](../../docs/domains/release/README.md).

```bash
cd apps/api
uv run --python 3.12 alembic revision --autogenerate -m "change"
uv run --python 3.12 alembic upgrade head
uv run --python 3.12 alembic downgrade -1
```

Rules:

- Autogenerate only against intended dev DB from typed env.
- Review generated migration manually.
- Root `./dev.sh` upgrades the development DB to `head` before starting API processes by default,
  then disables per-process auto-migration. Set `OPEN_WORK_HUB_DEV_API_MIGRATION_PREFLIGHT=0` only
  when the caller explicitly owns migration ordering.
- Standalone `scripts/dev-api.sh` enables auto-migration only for the primary `8001` instance by
  default; secondary instances never race schema changes.
- Test workers migrate their isolated database once, capture the application-ready seed baseline,
  and reset data without dropping migration-owned schema.
- Staging/prod migrations are explicit pre-start operations.
- Do not `stamp`, `DROP`, or repair drift without approved plan.
- `pnpm check:alembic-graph` and `pnpm test:alembic-graph` validate the static revision graph;
  `pnpm nx run api:test-migrations` exercises the migration-marked suite. Autogenerate output still
  requires manual model/schema review; there is no automatic model-drift oracle.
