# pms policy

역할: preview 가 권한과 schema 를 만족하는지 판정한다.

반환 필드:

- `decision`
- `reasons`
- `fallback_route`

다음 조건은 즉시 실패다.

- unauthorized mutation
- preview 누락
- schema 불일치
