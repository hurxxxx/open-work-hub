# RAG

Company and personal document search with grounded answers.

Active sources:

- Docs native documents
- Files sources activated through operator gate

Contract:

- Each source owns ACL semantics and its projection adapter; shared orchestration follows
  [Source Access](../source-access/README.md).
- Backend candidate partition/visibility metadata is not final auth.
- Recheck source ACL before response, summary, citation, or external LLM payload.
- Extraction/chunking/embedding/vector/keyword projection follow versioned outbox.
- Model/index schema changes require staged generation, validation, then cutover.

The distinction between retrieval channels, default-query resources, and registered inactive
adapters is in the [Source Matrix](source-matrix.md).
