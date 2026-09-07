# Source Access

Source Access is the shared authorization composition point for registered searchable resources.
It gives keyword search, Retrieval, and RAG one way to ask a source whether the current caller may
read a canonical candidate. It never replaces the source app's own ACL or makes an index/storage
locator authoritative. Notifications and content delivery have separate dispatchers but must reuse
the same source-owned authorization semantics.

## Contract

- `SourceAclPolicy` is built for an authenticated workspace or company execution context.
- Each registered resource type has exactly one source-access adapter with an explicit owning
  `app_id`. Missing adapters or owner app identities deny
  access. Batch/RAG authorization admits a non-workspace context only when the paired retrieval
  partition adapter declares that candidate scope; callers must not use a workspace-only adapter
  through an unguarded direct path.
- Direct, batch, RAG, and source-discovery dispatch apply the same execution-scope admission.
  Company calls to workspace-only sources return a denial without invoking their adapter.
- Every dispatch rechecks current account status, login blocking, runtime app availability, and
  active workspace membership where applicable. A previously constructed `SourceAclPolicy` and
  an ORM-loaded user graph are not authorization snapshots that survive revocation. Adapters
  receive the current workspace role; batch calls check execution once per resource type.
- Company file corpora remain accessible through an authenticated company execution policy and
  their own cohort/explicit-grant ACL. Company scope never admits workspace-only sources.
- The source app owns direct and batch authorization predicates, inactive/deleted handling, and
  keyword ACL branches. The shared policy groups candidates and dispatches to those adapters.
- Registered resource types are `docs_native_doc`, `file_manager_file`, `meeting`, `pms_task`, and
  `planner_event`.
- Candidate partition, workspace metadata, search index fields, notification rows, signed content
  grants, and browser routes are never grants. Recheck current source-owned access against
  PostgreSQL before exposing the resource.
- Final authorization precedes result counts, facets, highlights, reranking, summaries, external
  LLM input, grounding, and citations.
- Batch authorization may optimize the decision but must preserve the same result as direct
  source authorization. Returned IDs are intersected with requested candidates. Filtering
  survivors must not reorder them.
- Scope rules accept only supported scope kinds. A workspace administrator may manage user
  scopes within an already workspace-constrained source query, but cannot authorize another
  workspace ID, an inactive/foreign team, or an unknown scope kind. Source queries must still
  constrain resource ownership to the policy workspace.
- A new indexed resource type requires a source-access adapter, explicit registry composition,
  retrieval-partition alignment when applicable, and direct/batch/revocation tests. A non-indexed
  notification/content source may instead use its owning dispatcher's explicit branch.

Retrieval partition and projection rules are owned by
[ADR 0009](../../../adr/0009-retrieval-partition-projection-generations.md). Signed byte delivery
is owned by [Content Access](../content-access/README.md); source-event visibility is owned by
[Notifications](../notifications/README.md).

## Checks

```bash
(cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/test_source_access_policy.py tests/test_platform_adapter_registries.py tests/test_search_query_policy.py tests/test_notification_visibility.py tests/test_retrieval.py -q)
```
