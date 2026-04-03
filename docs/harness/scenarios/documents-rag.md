# Scenario: documents-rag

## goal

권한이 있는 문서와 메타데이터를 기반으로 사용자가 원하는 자료를 빠르게 찾고, citation이 포함된 근거형 답변을 제공한다.

## input schema

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `query` | string | yes | 사용자 질의 |
| `filters.doc_type` | string[] | no | 문서 유형 필터 |
| `filters.project` | string[] | no | 프로젝트 필터 |
| `filters.department` | string[] | no | 부서 필터 |
| `top_k` | integer | no | 기본값 20 |
| `answer_mode` | enum | no | `search-only` 또는 `grounded-answer` |

## allowed tools

- OpenSearch hybrid search
- Qdrant vector retrieval
- Reranker
- Citation assembler
- ACL filter

## prompt contract

- 답변 전 반드시 retrieval 결과와 citation block을 확보한다.
- citation 없는 자유 생성 응답은 허용하지 않는다.
- 근거가 부족하면 추정하지 말고 추가 조건이나 검색 범위 재설정을 요청한다.
- 현재 질의와 관련 없는 다른 도메인 설명이나 기능 설명은 prompt context 에 포함하지 않는다.
- 출력은 `summary`, `key_points`, `citations`, `next_actions` 구조를 따른다.

## retrieval policy

- BM25 + vector hybrid를 기본값으로 사용한다.
- ACL 필터는 retrieval 전에 적용한다.
- re-rank는 top 50 후보에만 적용한다.
- citation 후보는 최종 답변에 사용한 문단과 페이지 기준으로 고정한다.

## failure modes

- ACL 적용 누락
- 검색 결과는 있으나 citation 연결 실패
- groundedness 부족
- 필터가 너무 좁아 결과 없음

## expected output

- 결과 목록만 필요한 경우: 문서 카드/리스트 + 메타데이터 + 열람 링크
- 답변이 필요한 경우: 요약 + 핵심 근거 + citation 목록 + 다음 액션

## eval rubric

- `retrieval_relevance`
- `citation_completeness`
- `groundedness`
- `acl_correctness`
- `response_schema_validity`
