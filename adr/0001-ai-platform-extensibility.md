# ADR 0001: AI Platform Extensibility Contracts

- Status: Accepted
- Date: 2026-04-18

## Decision

- `GET /api/v1/auth/me` stays identity-only.
- Workspace shell/app truth comes from `GET /api/v1/workspaces/{workspace_slug}/bootstrap`.
- Bootstrap combines admin app metadata, workspace entitlement, and code capability registry.
- Admin DB owns app display/category/visibility. Code registry owns route/component/backend/AI capability.
- Admin row without implementation capability must not expose an app as executable.
- Each domain owns optional `register_ai_capabilities(registry)`.
- AI core owns common runtime/contract only, not domain capability definitions.
- Router and AI tools call shared application/domain service functions.
- Service boundary accepts workspace, principal, and input; ACL/business rules stay inside it.
- `CallerPrincipal` is common caller model: kind, workspace, source, user/service/session identity.
- Future external consumers default to workspace-scoped service account/API key. Platform-wide clients are out of scope.

## Do Not

- Add central hardcoded AI task/tool policy lists.
- Give router, worker, AI tool, and API separate DB/auth logic for the same behavior.
- Infer route/component/backend implementation from an admin-created app row.
- Add automatic file-scan plugin architecture.

## Consequences

- App shell and AI capability extension are registry-driven.
- Registry/admin catalog consistency must be tested.
- Service-layer migration may be incremental.
