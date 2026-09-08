# API Agent Rules

- Start with current API code/tests and the closest owning domain document; read accepted ADRs only for touched contracts.
- Assemble FastAPI routers through `open_work_hub_api.api_registry`; keep routers thin and domain behavior in application/service layers.
- Enforce actor, declared execution identity, current company app admission, and source-owned resource ACL on the server.
- Product workspaces are removed under ADR 0012. App-local spaces and groups never become a global execution container.
- API/OpenAPI changes must update response models and regenerate the client when `pnpm check:api-contract` requires it.
- Schema changes require an Alembic migration from current head; do not use `create_all`, hand SQL compatibility, `stamp`, or destructive repair.
- AI, retrieval, and external file/URL changes follow the root boundaries and their owner ADRs/docs.
- Rendered API errors use the existing localized message contract; preserve interpolation and locale parity. Developer logs and identifiers are not product translations. Run `pnpm check:api-i18n` for message changes.
- Run focused pytest first, then `pnpm check:api-architecture`; add `pnpm check:api-contract` for API shape and Alembic checks for models/migrations.
