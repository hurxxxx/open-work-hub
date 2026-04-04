# plm-query planning

역할: 읽기 전용 PLM 조회 계획 또는 SQL preview 를 만든다.

- 입력은 `query`, `template_candidates`, `allowlist` 만 사용한다.
- allowlist 밖 객체를 참조하지 않는다.
- 멀티스테이트먼트, 쓰기, DDL, 권한 변경은 금지다.

반환 필드:

- `query_plan`
- `template_match`
- `sql_preview`
- `warnings`

실행은 하지 않는다. planner는 preview만 만든다.
