# Retrieval

Retrieval은 keyword search와 RAG를 조합하는 caller-facing 검색 계층이다.

- `POST /api/v1/workspaces/{workspace_slug}/retrieval/query`
- `GET /api/v1/workspaces/{workspace_slug}/retrieval/sources`
- AI tools `retrieval.search`, `retrieval.list_sources`

각 backend는 ingestion, native candidate generation과 source ACL을 소유한다. Retrieval은 source
선택, canonical resource identity, 중복 제거, rank fusion, global rerank와 최종 grounding을 소유한다.
서로 다른 backend의 raw score를 직접 비교하지 않는다.

명시적으로 요청한 source가 비활성 또는 실패 상태면 fail-closed한다. 기본 다중 source 조회는
사용 가능한 source 결과와 degraded 상태를 함께 반환할 수 있다. 모든 evidence와 citation은
source-owned 최종 ACL을 통과해야 한다.
