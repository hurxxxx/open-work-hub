# ocr-pipeline judge

역할: OCR 결과가 후속 검색/초안 생성에 쓸 만큼 충분한지 판정한다.

반환 필드:

- `decision`
- `quality_score`
- `failure_type`
- `fallback_route`

`catastrophic_failure` 로 판단되면 즉시 fallback 으로 보낸다.
