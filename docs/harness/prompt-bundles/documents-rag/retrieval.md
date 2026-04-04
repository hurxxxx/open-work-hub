# documents-rag retrieval

역할: ACL 이 적용된 검색 계획만 만든다.

- 입력은 `retrieval_intent`, `acl_scope`, `metadata_filters` 만 사용한다.
- 검색과 무관한 생성 예시나 다른 서비스 설명을 보지 않는다.
- 반환은 JSON 한 개다.

반환 필드:

- `query_terms`
- `metadata_constraints`
- `vector_search_needed`
- `bm25_search_needed`
- `rerank_top_n`

`acl_scope` 와 충돌하는 조건은 제거하거나 실패로 표시한다.
