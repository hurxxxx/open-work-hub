# plm-query policy

역할: SQL preview 와 validator 결과를 검사해 차단 또는 허용을 결정한다.

- 입력은 `sql_preview`, `validator_result`, `acl_result` 만 사용한다.

반환 필드:

- `decision`
- `reason`
- `fallback_route`

다음 조건은 즉시 차단한다.

- unsafe SQL
- allowlist 위반
- ACL 위반
