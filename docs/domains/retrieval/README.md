# Retrieval

Caller-facing multi-backend search layer combining keyword search and RAG.

Surfaces:

- `POST /api/v1/retrieval/query`
- `GET /api/v1/retrieval/sources`
- AI tools `retrieval.search`, `retrieval.list_sources`

Contract:

- Backends own ingestion, indexing, and native candidate generation. Source apps own ACL semantics
  through the shared [Source Access](../source-access/README.md) adapter contract.
- Retrieval owns source selection, canonical identity, dedupe, rank fusion, global rerank, final grounding.
- Do not compare raw backend scores.
- Explicit inactive/unavailable source fails closed.
- Default multi-source query may return degraded available results.
- Every evidence/citation passes source-owned final ACL before presentation or external model input.

`generic_rag` and `keyword` are retrieval backend channels, not app or resource identities. Active
RAG resource adapters are listed in the [RAG Source Matrix](../rag/source-matrix.md).

## Company Keyword Search

`POST /api/v1/search/query` is the non-grounded keyword/facet surface
used by the shell. It composes app-owned `SearchEntityAdapter` projections, preserves backend order
after ACL filtering, and returns the keyword-search response contract. It is not a legacy RAG alias
and does not imply that every keyword entity participates in `generic_rag`.
