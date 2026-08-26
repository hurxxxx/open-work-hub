# ADR 0004: Retrieval and RAG Boundary Policy

- Status: Accepted
- Date: 2026-07-08

## Decision

- Retrieval is the canonical caller-facing search surface:
  - `POST /api/v1/workspaces/{workspace_slug}/retrieval/query`
  - `GET /api/v1/workspaces/{workspace_slug}/retrieval/sources`
  - `retrieval.search`
  - `retrieval.list_sources`
- `/rag/query`, `/rag/sources`, `rag.query`, and `rag.list_sources` remain compatibility wrappers.
- New code must prefer Retrieval over RAG compatibility surfaces.
- Active RAG sources: Docs native documents; approved Files sources behind activation gate.
- Meeting, PMS, Planner, and knowledge-source docs are not active RAG sources without explicit ACL/ingestion/source/quality tests.
- Files empty production bootstrap may activate a structurally validated zero-row OpenSearch/Qdrant pair with `quality_status=deferred_until_nonempty`.
- `graph_hybrid` means query-time keyword/RAG fusion only; it does not imply persistent graph store.
- Retrieval owns cross-backend normalization, dedupe, RRF (`k=60`), global rerank, and final grounding.
- Backends own ingestion, indexing, native candidate generation, ACL mechanics, and compatibility ranking.
- Do not compare OpenSearch BM25 and Qdrant cosine raw scores.
- Explicit invalid/unavailable source fails closed; default multi-source query may return degraded available results.
- Source filters stay backend-specific under `filters.keyword` and `filters.rag`.

## Follow-Up Gate

- New active source requires source matrix update, ACL/citation tests, ingestion/projection plan, and quality corpus.
- Non-empty Files generation requires judged 60-query evaluation before activation.
- Index cutover consumes generation-bound quality artifact, mapping/version evidence, counts, and rollback plan.
