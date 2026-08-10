# ADR 0004: Retrieval and RAG Boundary Policy

- Status: Accepted
- Date: 2026-07-08

## Context

Open Work Hub has several search-like paths: Generic RAG, keyword search,
fixture document search, and AI graph evidence packing.
They share user intent but do not share one backend. Treating all of them as
one deep abstraction hides important differences in ownership, permissions,
index lifecycle, and evidence quality.

The project therefore needs one preferred query entrypoint for callers, while
the existing domain backends keep their own parser, index, ACL, and native
candidate-generation rules. Backend relevance scores are not directly
comparable: OpenSearch BM25 and Qdrant cosine similarity have different scales.

## Decision

### 1. Retrieval is the canonical caller-facing surface

New REST, OpenAPI, frontend, and MCP/AI consumers should use retrieval surfaces:

- `POST /api/v1/workspaces/{workspace_slug}/retrieval/query`
- `GET /api/v1/workspaces/{workspace_slug}/retrieval/sources`
- `retrieval.search`
- `retrieval.list_sources`

External partner-facing use should also be based on this retrieval contract.
Actual service-account/API-key exposure is blocked until the auth/key lifecycle
from ADR 0001 is implemented.

### 2. RAG compatibility surfaces stay in place

`/rag/query`, `/rag/sources`, `rag.query`, and `rag.list_sources` remain
compatibility surfaces. They preserve their current response contracts and pass
through the retrieval wrapper where applicable.

New code must not prefer `rag.query` over `retrieval.search`. The legacy RAG
tool remains available for hidden-tool and feature-flag fallback.

### 3. Source scope stays conservative

The active RAG scope is intentionally narrow:

- workspace: Docs native official documents
- workspace: approved Files sources behind their source activation gate

Knowledge source documents and documents from Meeting, PMS, and Planner are
not active RAG sources. They can be reconsidered only with
explicit ACL, ingestion, source listing, and quality tests.

Files is an approved source behind its named operator gate and exact
OpenSearch/Qdrant generation-pair contract. A production environment with zero
active Files rows may structurally activate a validated empty pair before users
upload content. This is an availability bootstrap, not a content-quality
approval: it must record `quality_status=deferred_until_nonempty`, pin the
embedding and reranker identities, and preserve fail-closed behavior when the
pair or either backend is unhealthy. A healthy empty pair returns a normal
zero-result response.

### 4. Graph RAG is not claimed yet

`graph_hybrid` is a retrieval profile that combines keyword search and Generic
RAG at query time. It does not imply a persistent graph store, entity extraction,
or relationship indexing.

Real Graph RAG requires a separate design and migration plan.

### 5. Demo searches are named by what they are

Fixture document search is a demo surface, not RAG. Its public scenario id is
`documents-demo`.

### 6. Retrieval owns cross-backend ranking and final grounding

Each backend owns ingestion, indexing, ACL enforcement, native candidate
generation, and compatibility-surface ranking. The canonical retrieval Module
owns the cross-backend query pipeline:

1. OpenSearch produces BM25 keyword candidates.
2. Qdrant produces dense-vector semantic candidates without backend-local
   sparse fusion or reranking.
3. Results are normalized to one canonical resource identity and deduplicated.
4. Multi-backend results are fused by rank with reciprocal rank fusion (RRF,
   `k=60`), not by mixing raw relevance scores.
5. Semantic and hybrid strategies run one global rerank pass.
6. The final top-k evidence set is grounded once.

The public RAG compatibility surface keeps its existing Qdrant dense plus
hashed term-frequency sparse RRF behavior. That sparse score is a compatibility
mechanism and must not be described as BM25. Canonical keyword and hybrid
retrieval use OpenSearch BM25.

If one requested backend is unavailable or times out, an implicit/default
multi-source query may return the available backend with a degraded profile.
An explicitly requested invalid source is rejected, and an explicitly requested
but unavailable source is forbidden; an explicit source whose runtime backend
fails returns 503. Whenever more than one backend contributes results, RRF is
applied regardless of the caller's strategy label. Source filtering remains backend-specific
under the `filters.keyword` and `filters.rag` namespaces.

## Consequences

### Positive

- Callers get one preferred retrieval entrypoint.
- Domain backends keep clear ownership of ingestion, ACL, indexing, and quality.
- RAG source growth requires explicit policy and tests instead of filename
  inference.
- Demo paths stop looking like hidden Generic RAG implementations.

### Negative

- Compatibility endpoints remain until their consumers are retired.
- A future external API-key product still needs auth/key lifecycle work.
- Real Graph RAG remains a separate feature, not a rename of existing fusion.
- Cross-backend ranking has a clear ownership boundary and can be evaluated as
  one pipeline without collapsing backend-specific ingestion and ACL rules.

## Follow-up

- Keep `docs/domains/rag/source-matrix.md` in sync with the retrieval source
  catalog test.
- Keep parser/OCR and Qdrant migration policy in the RAG domain docs.
- Add a dedicated implementation plan before enabling any new active RAG source.
- For a non-empty Files generation, build and pass the versioned 60-query
  retrieval evaluation corpus before activation. The sole exception is the
  explicitly confirmed, initial, zero-active-row production bootstrap above;
  its quality status remains deferred until representative content and judged
  queries exist.
- Index activation must consume a generation-bound quality artifact and verify
  the staged mapping version and backfilled document count before moving the
  alias. The empty bootstrap instead consumes structural evidence for two
  zero-count physical backends plus pinned model/config identities.
