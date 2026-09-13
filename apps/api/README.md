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

## Tests

| Command (repository root) | Evidence |
| --- | --- |
| `pnpm ci:api` | Architecture, lint, Python compilation, and default API regression tests, including authorization and request validation |
| `pnpm nx run api:test-slow` | Additional expensive/provider tests |
| `pnpm nx run api:test-migrations` | Real PostgreSQL migration upgrade/downgrade and data preservation |
| `pnpm nx run api:test-integration` | Real Redis, MinIO, and OpenSearch adapter/API round trips |
| `pnpm ci:api:full` | All of the above test groups; a failure in any group fails the command |

The target currently named `typecheck` runs `compileall`; it checks Python syntax, not static types.
The default test target excludes `slow`, `migration`, and `external_integration`. A default pass
does not establish external-service readiness. Keep inexpensive auth/input checks in the default
group. Native terminal lifecycle tests require Linux and tmux because the launcher uses Linux
parent-death signalling; run the complete suite in the Linux validation environment.
Install the repository's Node dependencies with `pnpm install --frozen-lockfile` as well as the
API's Python package: Docs codec tests launch the real BlockNote Node subprocess, and terminal
tests launch a separate Python interpreter that must be able to import the installed API package.
Test collection supplies synthetic required settings before importing registries, so it does not
need an ignored env file or live application credentials. Database execution still requires the
explicitly verified test infrastructure below.

Before database tests, configure `OPEN_WORK_HUB_TEST_POSTGRES_TEMPLATE_DSN` for a dedicated
non-production PostgreSQL instance with pgvector available and a role allowed to create/drop test
databases and enable the extension. Use compatible `pg_dump`/`pg_restore` clients. The fixture also
accepts the verified development DSN from ignored env files, but never resets that database: each
worker creates its own `open_work_hub_test_*` database, migrates it, and restores the seeded data
between tests. A setup failure also removes the database created by that attempt. Keep production
identity/profile checks enabled. API clients also use a unique test instance ID so terminal sockets
cannot attach to another test run or a running development API. External-service settings and CI preparation are owned by the
[installation guide](../../INSTALL.md#226-ci-변수-등록과-실제-실행-확인).

For a focused database/authorization regression run:

```bash
cd apps/api
uv run --python 3.12 --group dev python -m pytest \
  tests/test_dm_conversation_queries.py tests/test_dm_read_state.py \
  tests/test_dm_company_security.py tests/test_ai_runtime_persistence.py -q
```

- Exercise SQL filters, ordering, limits, constraints, and persistence with the migrated database.
  Include excluded rows (other users/resources, left memberships, pre-join history) and boundary
  values; returning a predetermined row from a fake `scalar`/`scalars` cannot validate a query.
- Keep deterministic substitutes at external boundaries such as LLM output or object storage for
  focused policy tests. They do not establish live provider quality or service compatibility;
  the external integration group exercises actual service adapters separately.
- Default API tests publish worker jobs through Celery's `memory://` transport and purge those
  messages between tests. Serialization, routing, and after-commit publication still execute;
  tests never send jobs to the developer's configured broker. The publisher delivery contract
  also runs against isolated Redis in the external integration group. This checks broker handoff,
  not Worker task execution.
- Assert response content and durable effects, not just a success/error status. For rejected byte
  grants, check the documented non-enumerating error and that storage is never opened. For file
  deletion, check grant revocation and physical object absence as well as the database tombstone.
- Read committed records in a fresh session when testing persistence. Keep pure normalization
  tests in their owner module; persistence tests must also exercise the write path.
- When replacing a weak test, check that a representative defect (removed filter, skipped
  redaction/deletion) makes it fail. Run experiments in an isolated test process/copy so a live
  development server never reloads deliberately broken source.

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
