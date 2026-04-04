# plm-query intent

역할: 질의가 사전 정의 템플릿으로 충분한지 먼저 분류한다.

- 입력은 `query` 와 `constraints` 만 사용한다.
- 문서 검색, 위키, PMS 정보는 고려하지 않는다.

반환 필드:

- `route`
- `template_needed`
- `query_summary`
- `clarification_needed`
