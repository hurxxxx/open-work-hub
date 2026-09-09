# ADR 0012: Company Apps, Directory Groups, And App-Owned Authorization

- Status: Accepted
- Date: 2026-09-08

## Decision

One deployment remains one company. Product workspaces, their memberships,
availability overrides, route selectors, and execution identities are removed.
There is no replacement default workspace. Filesystem working directories,
terminal sandboxes, and package-manager workspaces are unrelated and remain.

The platform owns accounts, the organization directory, reusable groups, app
admission, directory APIs, and selection components. Apps own their business
containers, role definitions, ACL tables, and approval workflows. PMS spaces
remain PMS resources; they are not platform groups.

- Organization groups contain only users whose current primary organization is
  that exact organization. Membership is derived, not copied. Descendants and
  department heads are not implicitly included.
- Manual groups contain explicitly assigned users. Organization changes never
  rewrite manual membership. Both group kinds use one principal interface.
- Each organization can name one head; one person can head several organizations.
  This is directory information, not platform or business authorization.
- App admission requires an active account, company enablement, feature/role
  requirements, and either an all-users audience or a matching user/group grant.
  Missing configuration and empty selected audiences deny. Platform admins may
  bypass audience selection, but not company disablement or personal ACLs.
- Platform administrators manage core settings and may read company business
  resources. Personal mail, calendars, conversations, AI runs, and personal
  documents remain owner/participant/explicit-share restricted.
- Standalone authoring starts personal. Explicit sharing preserves personal
  ownership; publication to company work or a project is an explicit ownership
  transition. Removing a project link does not undo publication.
- Source apps enforce the same current ACL for REST, search, AI, notifications,
  collaboration, and content delivery. A resource grant never grants app use.
- Group, account, organization, app-policy, and source changes invalidate open
  projections. Cached claims, queues, and approvals do not preserve access.

## Delivery

Development accounts and business data are reset after replacement code and
schema are validated. Prior schema history is replaced by a fresh company schema
baseline; Git retains the historical definitions. Existing routes, identifiers,
data, and migration compatibility are intentionally unsupported. Reset applies
only to the explicitly authorized development database. Production changes and
an external HR connector are separate work. Core organization updates provide
the authoritative integration seam for future HR ingestion.

This decision supersedes ADRs 0006, 0007, and 0011 and the former scope,
principal, route, and baseline requirements in ADRs 0001, 0002, 0004, 0005,
and 0009. Their remaining capability, workload, and retrieval safety contracts
continue to apply.
Mutable contracts remain in [App Platform](../docs/domains/app-platform/README.md),
[Organization](../docs/domains/organization/README.md),
[Source Access](../docs/domains/source-access/README.md),
[AI Execution](../docs/domains/ai/execution.md), and
[Hermes](../docs/domains/ai/hermes.md).
