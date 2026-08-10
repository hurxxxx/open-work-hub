# Project Agent Rules

## Scope And Safety

- Preserve user changes and keep edits within this repository unless the user explicitly
  expands the scope.
- Never commit secrets, credentials, production data, customer documents, generated
  backups, or local runtime artifacts. Runtime configuration belongs in ignored `.env`
  files; `.env.example` contains safe placeholders only.
- Model AI and retrieval behavior with reusable schemas and operators. Do not add branches
  that recognize a particular customer, document, query, or example.
- Avoid destructive Git operations and do not commit or push unless the user requests it.

## Project Structure

- Web routes, UI, and API clients live under `apps/web/src/app-modules/<appId>/`.
- FastAPI routers are composed through `open_alm_api.api_registry`.
- Shared frontend contracts and primitives live in `packages/`; do not reach across app
  boundaries with deep imports.
- Shared or auditable data must use an approved database or object store. Browser-local,
  process-local, and temporary files are not authoritative shared storage.
- API contracts, persistence models, RBAC, workspace scope, worker registration, and
  generated clients are part of each feature contract. Add Alembic migrations for schema
  changes and regenerate OpenAPI types when the API changes.
- Generative model calls use the registered workload interface. Application code must not
  select providers directly or bypass the shared gateway with ad-hoc SDK or HTTP calls.

## Documentation Routing

Read only the material relevant to the current change:

| Change surface | Reference |
| --- | --- |
| Code structure and abstractions | `docs/agents/llm-friendly-development.md` |
| Validation depth | `docs/agents/vibe-coding-harness.md` |
| App identity and registration | `docs/domains/app-platform/README.md` |
| UI components and interaction | `docs/agents/ui-components.md` |
| AI capabilities | `adr/0002-mcp-capability-platform.md`, `adr/0005-registered-llm-workload.md` |
| Retrieval and RAG | `docs/domains/retrieval/README.md`, `adr/0009-retrieval-partition-projection-generations.md` |
| Deployment | `docs/domains/release/production-deployment-layout.md` |

The documentation index is `docs/README.md`.

## Git And Review

- Use short-lived branches and GitHub pull requests. Keep each pull request focused on one
  complete outcome.
- Do not change branches or discard modifications in a dirty working tree.
- Investigate current logs and reproduce failures before changing CI or guardrails. Do not
  weaken tests, policy, CODEOWNERS, or exclusions merely to make a feature pass.
- Bind validation evidence to the source revision. Re-run affected checks after source or
  target changes that alter the tested surface.

## Validation

- Match validation depth to risk. Start with focused tests and expand for shared contracts,
  migrations, external integrations, or uncertain blast radius.
- `pnpm ci:harness` checks repository policy but is not sufficient evidence for a feature.
  Test the affected API, web, worker, migration, file, network, and user-flow surfaces.
- Keep generated artifacts deterministic and verify them with their checked-in generators.
