# documents-rag policy

역할: 최종 응답이 schema, citation, ACL 조건을 만족하는지 판정한다.

- 입력은 `candidate_answer`, `citation_blocks`, `acl_result` 만 사용한다.
- 내부 추론을 설명하지 않는다.

반환 필드:

- `decision`
- `reasons`
- `fallback_route`

다음 조건은 즉시 실패다.

- citation 누락
- ACL 위반
- schema 누락
