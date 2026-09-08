# Source Access

Source Access composes source-owned authorization for keyword search, Retrieval, and RAG.
Indexes and partitions identify candidates; PostgreSQL source ACLs decide disclosure.
Notifications and content delivery use separate dispatchers with the same owning-app rules.

## Contract

- `SourceAclPolicy.for_user(db, user=...)` carries the authenticated caller. There is no global
  workspace or replacement company container identifier.
- Each registered resource type has one source adapter and an explicit owning `app_id`. Missing
  adapters, unknown scope kinds, inactive accounts, and unavailable apps deny access.
- Every direct, batch, RAG, discovery, and keyword dispatch rechecks current app admission. A
  constructed policy, queued job, approval, token, or ORM user graph cannot preserve revoked rights.
- Apps own resource predicates, lifecycle handling, and role semantics. Core company groups are
  reusable principals, resolved from current active assignments; they are not business roles.
- Docs authoring starts personal. Direct user/group read or edit shares do not transfer ownership
  or permit resharing. PMS publication transfers ownership explicitly; removing its target does
  not restore personal ownership. `company_visible` grants an all-admitted-users read audience
  separately from company ownership. Company ownership grants platform administrators read only.
- PMS uses active app-local spaces, explicit user membership, live group bindings, and supported
  task grants. Platform administrators can read company business resources but do not inherit a
  space write role. Archived-list detail and active search exclusion remain source-owned rules.
- Meeting records, recordings, and generated meeting notes are company business resources.
  Administrators can read them while admitted to the relevant app. Participation or organizer
  authority is still required for business mutations. Personal planner events remain owner-only.
- Linked-resource metadata is independently authorized. Access to a meeting, document, or
  whiteboard cannot expose another app's private or disabled target title.
- File corpora and files retain source-owned scope, explicit grant, lifecycle, and content rules.
  Company candidate scope never makes personal files visible.
- Registered searchable types are `docs_native_doc`, `file_manager_file`, `meeting`, `pms_task`,
  and `planner_event`. A new type needs registry composition, source adapter, partition alignment,
  and direct/batch/revocation tests.
- Final source authorization precedes counts, facets, highlights, reranking, external model input,
  summaries, grounding, and citations. Candidate fields, signed grants, notification rows, routes,
  and retrieval partitions are never grants.
- Batch results must equal individual authorization, intersect the requested IDs, and preserve
  survivor order. PostgreSQL version, generation, checksum, and tombstone fences prevent stale
  projections from reappearing after replacement or deletion.

Company policy is owned by [App Platform](../app-platform/README.md) and
[Organization](../organization/README.md). Retrieval generations remain defined by
[ADR 0009](../../../adr/0009-retrieval-partition-projection-generations.md), with its former
workspace requirements superseded by [ADR 0012](../../../adr/0012-company-app-access-without-workspaces.md).
Byte grants are owned by [Content Access](../content-access/README.md), and source-event visibility
by [Notifications](../notifications/README.md).

## Checks

```bash
(cd apps/api && uv run --python 3.12 --group dev pytest tests/test_company_content_boundaries.py tests/test_company_groups.py tests/test_source_access_policy.py tests/test_platform_adapter_registries.py tests/test_search_query_policy.py tests/test_notification_visibility.py tests/test_retrieval.py -q)
```
