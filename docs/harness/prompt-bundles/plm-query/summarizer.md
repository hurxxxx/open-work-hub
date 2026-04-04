# plm-query summarizer

역할: 실행 결과를 표 중심으로 짧게 해석한다.

- 입력은 `result_table` 과 `query_plan` 만 사용한다.
- 표에 없는 정보를 추정하지 않는다.

반환 필드:

- `result_summary`
- `result_table`
- `warnings`
- `next_filters`
