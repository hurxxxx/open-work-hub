# RAG

Workspace document search with grounded answers.

Active sources:

- Docs native documents
- Files sources activated through operator gate

Contract:

- Each source owns ACL and projection adapter.
- Backend workspace/visibility metadata is not final auth.
- Recheck source ACL before response, summary, citation, or external LLM payload.
- Extraction/chunking/embedding/vector/keyword projection follow versioned outbox.
- Model/index schema changes require staged generation, validation, then cutover.

Current source list: [Source Matrix](source-matrix.md).
