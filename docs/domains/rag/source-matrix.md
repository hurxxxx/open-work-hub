# RAG Source Matrix

`generic_rag` and `keyword` are caller-facing Retrieval backend channels. They are not source-app
or resource identities. This first table is an executable mirror of the Retrieval source catalog;
keep the identifier values exact.

| Source        | Scope     | Backend        | Active |
| ------------- | --------- | -------------- | ------ |
| `generic_rag` | workspace | qdrant         | true   |
| `keyword`     | workspace | keyword_search | true   |

RAG projection and query participation is resource-owned:

| App     | Resource type       | Registered projection/ACL | Default RAG query and workspace reindex                            | Listed source kinds               |
| ------- | ------------------- | ------------------------- | ------------------------------------------------------------------ | --------------------------------- |
| Docs    | `docs_native_doc`   | yes                       | yes                                                                | visible official native-doc kinds |
| Files   | `file_manager_file` | yes                       | only while the Files operator gate and active generation pair pass | `files` while active              |
| Meeting | `meeting`           | yes                       | no                                                                 | none                              |
| PMS     | `pms_task`          | yes                       | no                                                                 | none                              |
| Planner | `planner_event`     | yes                       | no                                                                 | none                              |

The registered Meeting, PMS, and Planner adapters support explicit projection and future
activation; registration alone does not put them in default RAG queries or source listings.

A new active resource requires executable app identity, a
[Source Access](../source-access/README.md) adapter, retrieval-partition adapter, projection
lifecycle, app/runtime gate, ACL matrix, citation tests, and a quality corpus.
