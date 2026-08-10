# RAG Source Matrix

| Source | Scope | Backend | Active |
| --- | --- | --- | --- |
| `generic_rag` | workspace | qdrant | true |
| `keyword` | workspace | keyword_search | true |
| `documents_demo` | workspace | fixture | false |

새 source는 app identity, source access adapter, retrieval partition adapter, projection lifecycle,
ACL matrix와 citation 검증을 함께 제공해야 한다.
