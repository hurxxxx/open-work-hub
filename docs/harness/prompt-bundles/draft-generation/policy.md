# draft-generation policy

역할: 초안이 export 전 조건을 만족하는지 판정한다.

반환 필드:

- `decision`
- `reasons`
- `fallback_route`

다음 조건은 실패다.

- citation block 누락
- 필수 field 누락
- unsupported claim 발견
