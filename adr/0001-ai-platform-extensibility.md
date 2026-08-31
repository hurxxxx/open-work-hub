# ADR 0001: AI Platform Extensibility Contracts

- Status: Accepted
- Date: 2026-04-18

## Decision

- `GET /api/v1/auth/me` stays identity-only.
- [ADR 0011](0011-app-first-workspace-context.md) is authoritative for launcher/bootstrap,
  canonical routes, runtime controls, and per-app workspace preference.
- Static executable app identity, route context, execution context, resource scope, and launcher
  placement come from `packages/contracts/app-contracts.json` and its generated projections.
- An admin row cannot create an executable app or infer route/component/backend/AI capability.
- Each domain owns optional `register_ai_capabilities(registry)`.
- AI core owns common runtime/contract only, not domain capability definitions.
- Router and AI tools call shared application/domain service functions.
- Service boundary accepts execution context, principal, and input; ACL/business rules stay inside
  it. Workspace is required only for workspace execution.
- `CallerPrincipal` is common caller model: kind, optional workspace, source, and
  user/service/session identity.
- External AI capability consumers default to a workspace-scoped service principal. Company-wide
  directory integration credentials are a separate non-AI contract owned by ADR 0010.

## Do Not

- Add central hardcoded AI task/tool policy lists.
- Give router, worker, AI tool, and API separate DB/auth logic for the same behavior.
- Infer route/component/backend implementation from an admin-created app row.
- Add automatic file-scan plugin architecture.

## Consequences

- App shell and AI capability extension are contract/registry-driven.
- Generated contract, backend/frontend registry, and runtime-control consistency must be tested.
- Service-layer migration may be incremental.

## Related

- [ADR 0011](0011-app-first-workspace-context.md) owns the current app-first route, launcher, and
  runtime availability contract.
- [ADR 0010](0010-platform-api-key-directory-integration.md) owns company-wide directory API keys.
