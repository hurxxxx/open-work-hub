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
- Authenticated AI health: `/api/v1/workspaces/{workspace_slug}/chatbot/health`
- Workspace AI routes mount only behind `require_current_user` plus workspace membership.

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
- Baseline revision: `0b843a383b2b_baseline_2026_04_10`.

```bash
cd apps/api
uv run --python 3.12 alembic revision --autogenerate -m "change"
uv run --python 3.12 alembic upgrade head
uv run --python 3.12 alembic downgrade -1
```

Rules:

- Autogenerate only against intended dev DB from typed env.
- Review generated migration manually.
- Local developer launcher must not auto-migrate shared dev DB.
- Test DB applies Alembic/runtime seed once per isolated run.
- Staging/prod migrations are explicit pre-start operations.
- Do not `stamp`, `DROP`, or repair drift without approved plan.
- `test_alembic_check_reports_no_model_drift` guards model/migration drift.
