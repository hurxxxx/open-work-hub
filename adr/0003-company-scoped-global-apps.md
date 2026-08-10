# ADR 0003: Company-Scoped Global App Policy

- Status: Accepted
- Date: 2026-06-23

## Context

AI-DO originally grew around workspace-scoped apps: routes live under
`/w/:workspaceSlug/...`, APIs are usually mounted under
`/api/v1/workspaces/{workspace_slug}/...`, and RAG documents carry a
`workspace_id`.

That model is wrong for company-wide business portal resources such as:

- community channels and posts
- management-team Q&A notices and uploaded reference documents
- future apps whose content is explicitly available to all authenticated users

If those resources are modeled as workspace documents, the platform gets the
wrong ownership boundary:

- users can infer that a company notice belongs to a particular workspace
- workspace API rewrite rules leak into global products
- RAG vectors become hard to query across the company corpus
- admin batch jobs need artificial workspace slugs
- future portal apps repeat one-off exceptions instead of following a policy

## Decision

AI-DO supports a first-class **company-scoped global app** contract.

### 1. Canonical route and API shape

Company-scoped apps use global frontend routes and protected global APIs:

- frontend route: `/<app-or-feature-route>`
- API route: `/api/v1/<domain>`

They do not use workspace API rewrite prefixes unless the product explicitly
introduces a workspace-scoped sub-resource.

Current examples:

- Community: `/community`, `/api/v1/community`
- Q&A Assistant: `/qa-assistant`, `/api/v1/qna`

Legacy workspace routes may remain only as redirects to the canonical global
route.

### 2. Manifest contract

App and feature manifests declare resource scope:

- `resourceScope: 'workspace'` for workspace-owned data
- `resourceScope: 'company'` for company-wide data
- `resourceScope: 'hybrid'` for parent apps that compose both workspace and
  company surfaces

The shell uses this contract when deciding whether a global route can show app
chrome without a selected workspace.

### 3. Persistence and storage

Company-scoped records use an explicit scope marker, not an implied workspace:

- domain tables should include `scope_kind = 'company'` when they share a table
  with workspace-era or workspace-owned rows
- new company records should store `workspace_id = NULL`
- object storage keys should live under a company namespace such as
  `company/qna/...`

Existing rows may retain legacy `workspace_id` only as a compatibility pointer
for old object storage keys. Access, indexing, and routing must not treat that
field as ownership.

### 4. RAG scope

RAG has two query/index scopes:

- `workspace`: vectors are filtered by `workspace_id`
- `company`: vectors have `workspace_id = NULL` and must carry a company
  visibility ref such as `company_public`

Company-scoped RAG queries do not require workspace membership. If answer
generation needs the AI Gateway's execution context, the gateway may use the
user's default or first active workspace as execution context only; that
workspace is not a data-scope filter.

### 5. Administration

Company-scoped corpus mutation is platform administration, not workspace
administration, unless a product decision says otherwise.

For Q&A:

- upload, delete, and board sync require platform admin context
- reads and asks are available to authenticated users
- groupware board sync has no configured workspace slug

## Consequences

### Positive

- Company-wide portal resources have a stable ownership model.
- Future global apps can follow manifest, route, API, storage, and RAG rules
  without inventing one-off exceptions.
- Workspace API rewrite policy stays meaningful: if a prefix appears there, it
  really is workspace-scoped.
- Company RAG can query all intended company-public sources without fake
  workspace filters.

### Negative

- Hybrid parent apps, such as AI, need shell logic that can handle both
  workspace and global child surfaces.
- Existing workspace-era rows may need backfill or compatibility fallbacks until
  object storage is migrated to company keys.
- Some generated contracts and app launcher DTOs must be updated when an app
  moves from workspace scope to company scope.

## Non-Goals

- This ADR does not make all apps global.
- This ADR does not introduce anonymous/public access. Company-scoped still
  means protected authenticated access unless a route explicitly declares
  otherwise.
- This ADR does not remove workspace-scoped RAG or workspace document ACLs.
