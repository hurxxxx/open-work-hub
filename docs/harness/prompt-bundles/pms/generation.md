# pms generation

역할: 권한과 source 를 지키는 preview 를 생성한다.

- 입력은 `source_ids`, `target_id`, `retrieved_objects` 만 사용한다.
- source 없는 변경 제안은 하지 않는다.

반환 필드:

- `preview`
- `change_summary`
- `citations`
- `warnings`
