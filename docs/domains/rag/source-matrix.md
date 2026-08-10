# RAG Source Matrix

This file is intentionally testable. Keep the source, scope, backend, and active
columns aligned with `domains/retrieval/source_catalog.py`.

| source                    | scope     | backend              | active | policy                                         |
| ------------------------- | --------- | -------------------- | ------ | ---------------------------------------------- |
| `generic_rag`             | workspace | qdrant               | true   | Docs native official documents.                |
| `keyword`                 | workspace | keyword_search       | true   | OpenSearch-style workspace keyword search.     |
| `qna`                     | company   | qdrant               | true   | Company Q&A documents and notices.             |
| `legacy_issues`           | workspace | postgres_pgvector    | true   | Legacy issue evidence search; not Generic RAG. |
| `documents_demo`          | workspace | fixture              | false  | Fixture search demo; not RAG.                  |
| `learning_notes_personal` | user      | native_doc_embedding | false  | Personal note metadata only; not active RAG.   |

## Environment-gated and Excluded Sources

Meeting, PMS, Planner, and Learning Notes personal documents stay outside active
Generic RAG indexing. Enabling any of them requires explicit ACL, ingestion,
source listing, and quality tests. The retired generic Knowledge source is not an
activation candidate and must not be reintroduced as an integration shortcut.

Files는 fail-closed source다. Development는 quality-validated partition-aware pair를
사용하고, production은 structure-validated empty pair로 gate만 열려 있으며
`quality_status=deferred_until_nonempty`다. 현재 상태와 source 계약은
[Files Retrieval Source Activation](files-source-activation.md), 정확한 production 승격·rollback
경계는 [Files generation cutover runbook](files-generation-cutover-runbook.md)을 따른다. Files는
독립 top-level retrieval source가 아니라 `generic_rag`의 `source_kind=files`와 `keyword`의
`entity_type=file`로 참여한다.

mcloudoc 기반은 Files 안의 `source_managed=true`, `authorization_mode=explicit_grants`
corpus로 수용한다. 따라서 별도 `mcloudoc` RAG source kind나 resource type을 만들지 않는다.
대상 adapter와 승인된 운영 source가 없으므로 공동 E2E와 별도 활성화 변경 전에는 mcloudoc
문서를 운영 색인 대상으로 간주하지 않으며 worker/schedule도 제공하지 않는다. 상세 계약은
[mcloudoc 연계 경계](../mcloudoc/README.md)를 따른다.
