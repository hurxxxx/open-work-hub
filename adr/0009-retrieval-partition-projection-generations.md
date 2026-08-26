# ADR 0009: Retrieval Candidate Partitions and Projection Generations

- Status: Accepted
- Date: 2026-07-22

## Partitions

- `retrieval_partition_id` is opaque immutable UUID for backend routing/coarse candidate filtering.
- It is not a resource grant.
- PostgreSQL `retrieval_partitions` is source namespace, owner, candidate scope, state, metadata version source.
- Candidate scopes: `company`, `workspace`, `personal`.
- Backend query must include server-resolved non-empty partition predicate.
- Backend payload partition/workspace/ACL hints are not authority.
- Source-owned PostgreSQL ACL is final authority.
- Publication/ownership transition updates source rows and partition directory in one transaction.
- Final ACL batch statement after candidate generation is the authorization linearization point.

## Source Policy

- Retrieval discovers supported scope/transition policy from source adapters.
- Built-in sources use `transition_mode=source_owned`.
- Generic partition transition must not bypass source ACL transaction.
- Partition binding does not activate inactive sources.
- Raw REST/MCP query input does not accept partition ID.
- Files large movable corpus needs source-owned `files_corpus` security cohort and non-default partition before upload.

## Physical Identity

- Canonical identity: length-delimited `(resource_type, resource_id)`.
- OpenSearch document ID derives from canonical identity.
- Qdrant point UUID derives from canonical `(resource_type, resource_id, chunk_id)`.
- Workspace/partition never enters physical ID or routing key.
- Deterministic encoding has fixed test vectors.

## Projection Ordering

- Projection head is permanent per `(resource_type, resource_id)`.
- Head stores monotone version, current partition, desired state/tombstone, checksum.
- Source mutation, head increment, and immutable outbox insert are one transaction.
- Search/RAG supersession identity: `(backend, resource_type, resource_id)`.
- Delete is versioned tombstone; stale workers exit `superseded`.
- OpenSearch uses strict external version.
- Qdrant uses PostgreSQL head fence; conditional update behavior/version is pinned by tests.

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
- Signed raw-content capability binds principal and ACL version; rechecks immediately before byte stream; no cache.

## PostgreSQL Rollout

- Expand: UUID directory, immutability trigger, nullable binding.
- Backfill: cursor batches, parent-before-child, orphan quarantine, reconciliation.
- Validate constraints separately; create needed indexes concurrently.
- Contract: apply NOT NULL/check/FK after dual-write and null audit.
- During nullable expand use `retrieval_partition_id IS NULL OR retrieval_partition_id IN (...)` with source ACL.
- Empty server scope must not become unfiltered fallback.
- Do not update large source tables in one Alembic transaction.

## Preserved ADRs

- ADR 0004 caller-facing Retrieval/backends remain.
- ADR 0007 company/workspace hierarchy and no `company_id` remain.
