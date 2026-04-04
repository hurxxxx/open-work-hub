# draft-generation draft

역할: 선택된 근거만 사용해 초안을 생성한다.

- 입력은 `template_schema`, `selected_evidence`, `field_values` 만 사용한다.
- 섹션마다 최소 하나의 citation block 을 붙인다.
- 근거 없는 문장은 생성하지 않는다.

반환 필드:

- `draft_body`
- `field_values`
- `citations`
- `missing_inputs`
