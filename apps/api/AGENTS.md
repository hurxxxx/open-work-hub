# API Agent Rules

- Start with current API code/tests and the closest owning domain document; read accepted ADRs only for touched contracts.
- Assemble FastAPI routers through `open_work_hub_api.api_registry`; keep routers thin and domain behavior in application/service layers.
- Enforce actor, declared execution context, workspace membership, runtime app availability, and resource ACL on the server.
- Workspace routes never infer a workspace; global routes never invent one.
- API/OpenAPI changes must update response models and regenerate the client when `pnpm check:api-contract` requires it.
- Schema changes require an Alembic migration from current head; do not use `create_all`, hand SQL compatibility, `stamp`, or destructive repair.
- AI, retrieval, and external file/URL changes follow the root boundaries and their owner ADRs/docs.
- Run focused pytest first, then `pnpm check:api-architecture`; add `pnpm check:api-contract` for API shape and Alembic checks for models/migrations.
