# Retrieval

Caller-facing search layer combining keyword search and RAG.

Surfaces:

- `POST /api/v1/workspaces/{workspace_slug}/retrieval/query`
- `GET /api/v1/workspaces/{workspace_slug}/retrieval/sources`
- AI tools `retrieval.search`, `retrieval.list_sources`

Contract:

- Backends own ingestion, native candidates, and source ACL.
- Retrieval owns source selection, canonical identity, dedupe, rank fusion, global rerank, final grounding.
- Do not compare raw backend scores.
- Explicit inactive/unavailable source fails closed.
- Default multi-source query may return degraded available results.
- Every evidence/citation passes source-owned final ACL.
