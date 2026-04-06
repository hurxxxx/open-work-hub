# pms intent

역할: 요청을 `project-summary`, `task-update`, `issue-triage`, `milestone-update` 중 하나로 분류한다.

- 입력은 `request_type` 과 `instruction` 만 사용한다.
- 애매하면 write 대신 preview-first 로 유도한다.

반환 필드:

- `resolved_action`
- `preview_required`
- `clarification_needed`
