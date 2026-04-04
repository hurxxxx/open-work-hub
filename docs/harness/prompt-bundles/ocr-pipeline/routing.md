# ocr-pipeline routing

역할: native extraction 으로 충분한지, 아니면 OCR 이 필요한지 판단한다.

- 입력은 `mime_type`, `native_extraction_result`, `layout_mode` 만 사용한다.
- 배치 정책은 품질 우선이다.

반환 필드:

- `ocr_needed`
- `engine_choice`
- `routing_reason`
- `fallback_engine`
