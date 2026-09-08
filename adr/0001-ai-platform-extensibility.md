# ADR 0001: AI Platform Extensibility Contracts

- Status: Accepted; scope and route policy superseded by [ADR 0012](0012-company-app-access-without-workspaces.md)
- Date: 2026-04-18

Current app admission, routes, and bootstrap are owned by
[App Platform](../docs/domains/app-platform/README.md). Durable user execution and
approval reauthorization are owned by [AI Execution](../docs/domains/ai/execution.md).

## Decision

- `GET /api/v1/auth/me` stays identity-only.
- Static executable app identity, route context, execution context, resource scope, and launcher
  placement come from `packages/contracts/app-contracts.json` and its generated projections.
- An admin row cannot create an executable app or infer route/component/backend/AI capability.
- Each domain owns optional `register_ai_capabilities(registry)`.
- AI core owns common runtime/contract only, not domain capability definitions.
- Router and AI tools call shared application/domain service functions.
- Service boundary accepts personal/company execution context, principal, and input;
  current app admission, source ACL, and business rules stay inside it.
- `CallerPrincipal` identifies caller kind, source, personal/company scope, and
  user/service/session identity. Execution scope alone does not authorize a resource.
- Service or system identity does not replace the requesting user's current authorization
  for user work. Company directory integration credentials are a separate non-AI contract
  owned by ADR 0010 and do not grant AI capability access.

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

- [ADR 0010](0010-platform-api-key-directory-integration.md) owns company-wide directory API keys.
