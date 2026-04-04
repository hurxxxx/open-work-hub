# draft-generation intent

역할: 템플릿, 주제, 입력 필드를 확인하고 생성 전 준비 상태를 정리한다.

- 입력은 `template_id`, `topic`, `field_overrides` 만 사용한다.
- 초안과 직접 관련 없는 다른 도메인 설명은 넣지 않는다.

반환 필드:

- `template_resolution`
- `required_fields`
- `missing_inputs`
- `evidence_queries`
