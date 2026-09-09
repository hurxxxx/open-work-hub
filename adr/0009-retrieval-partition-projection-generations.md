# ADR 0009: Retrieval Candidate Partitions and Projection Generations

- Status: Accepted; scope and baseline policy superseded by [ADR 0012](0012-company-app-access-without-workspaces.md)
- Date: 2026-07-22

Current company policy follows [App Platform](../docs/domains/app-platform/README.md)
and [Source Access](../docs/domains/source-access/README.md). This ADR retains candidate
partition, projection, and generation safety contracts.

## Partitions

- `retrieval_partition_id` is opaque immutable UUID for backend routing/coarse candidate filtering.
- It is not a resource grant.
- PostgreSQL `retrieval_partitions` is source namespace, owner, candidate scope, state, metadata version source.
- Candidate scopes: `company`, `personal`.
- Backend query must include server-resolved non-empty partition predicate.
- Backend payload partition/scope/ACL hints are not authority.
- Source-owned PostgreSQL ACL is final authority.
- Publication/ownership transition updates source rows and partition directory in one transaction.
- Final ACL batch statement after candidate generation is the authorization linearization point.

## Source Policy

- Retrieval discovers supported scope/transition policy from source adapters.
- Built-in sources use `transition_mode=source_owned`.
- Generic partition transition must not bypass source ACL transaction.
- Partition binding does not activate inactive sources.
- Raw REST/MCP query input does not accept partition ID.
- Files corpora use a source-owned `files_corpus` security cohort with a stable company
  partition before upload; file grants remain source-owned authorization.

## Physical Identity

- Canonical identity: length-delimited `(resource_type, resource_id)`.
- OpenSearch document ID derives from canonical identity.
- Qdrant point UUID derives from canonical `(resource_type, resource_id, chunk_id)`.
- Candidate scope/partition never enters physical ID or routing key.
- Deterministic encoding has fixed test vectors.

## Projection Ordering

- Projection head is permanent per `(resource_type, resource_id)`.
- Head stores monotone version, current partition, desired state/tombstone, checksum.
- Source mutation, head increment, and immutable outbox insert are one transaction.
- Search/RAG supersession identity: `(backend, resource_type, resource_id)`.
- Delete is versioned tombstone; stale workers exit `superseded`.
- OpenSearch uses strict external version.
- Qdrant workers acquire the PostgreSQL projection-head fence and recheck current version before
  writing; concurrent stale/current worker behavior requires a two-session fence test.

## Generation Cutover

- Backend schema/ID/payload changes use new physical index/collection.
- Do not mix old/new Qdrant point IDs in one collection.
- Create Qdrant payload index before ingest.
- Replay changes after baseline watermark.
- Validate key set, counts, checksum, ACL matrix, and retrieval quality.
- Switch backend aliases atomically per backend.
- Cross-backend cutover state lives in PostgreSQL control plane with validation/compensation/rollback.
- Old generation remains read-disabled through rollback window.
- Without online replay, freeze producers and drain queues for maintenance migration.

## Query/ACL

- Use backend coarse hints only when scope transition cannot remove authorized candidates.
- Otherwise use partition predicate plus source-owned final ACL/refill.
- ACL check precedes facet, highlight, rerank, summarization, external LLM input, grounding, and citation.
- Bounded refill fills after ACL rejection; OpenSearch refill uses PIT and `search_after`.
- Source adapter provides batch authorization and records rejection/refill metrics.
- Response metadata hydrates from canonical resource/source metadata, not backend payload.
- Signed raw-content capability issuance, caller binding, reauthorization, and response handling
  follow [Content Access](../docs/domains/content-access/README.md).

## PostgreSQL Schema Changes

- ADR 0012 replaced the previous migration chain with a fresh company baseline. The
  retired nullable-binding backfill is not an installation or authorization fallback.
- Future changes to populated tables need staged constraints, bounded cursor backfills,
  parent-before-child ordering, orphan quarantine, reconciliation, and cutover evidence.
- An expand/backfill/contract rollout requires dual-write and a null audit before applying
  required NOT NULL/check/FK constraints. Create needed indexes concurrently when the
  deployment requires online migration.
- Empty server scope must not become unfiltered fallback.
- Do not update large source tables in one Alembic transaction.

## Related Decisions

- [ADR 0004](0004-retrieval-rag-boundary-policy.md) owns Retrieval/backend separation.
- [ADR 0012](0012-company-app-access-without-workspaces.md) owns the company boundary
  and app-owned authorization model.
