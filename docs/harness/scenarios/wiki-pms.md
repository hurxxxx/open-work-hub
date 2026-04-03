# Scenario: wiki-pms

## goal

Wiki/PMS에서 자연어 기반 생성 기능을 사용하더라도 승인된 구조와 권한 안에서만 요약, 초안, 상태 제안을 수행하도록 한다.

## input schema

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `request_type` | enum | yes | `wiki-summary`, `wiki-draft`, `task-update`, `issue-triage` |
| `source_ids` | string[] | no | 참조 문서/이슈/작업 ID |
| `instruction` | string | yes | 사용자 요청 |
| `target_id` | string | no | 수정 대상 ID |

## allowed tools

- Intent router
- Wiki reader/writer
- PMS reader/writer
- Policy checker
- Structured generator

## prompt contract

- 변경 작업은 반드시 preview를 먼저 생성한다.
- 권한이 없는 객체에는 쓰기 제안을 하지 않는다.
- 요약과 추천은 source_ids 또는 연결된 trace 근거를 남긴다.
- 출력은 `preview`, `change_summary`, `citations`, `warnings`, `next_actions` 구조를 따른다.

## retrieval policy

- 직접 참조 대상이 있으면 해당 객체를 우선 사용한다.
- 없으면 최근 관련 작업/문서를 검색하되 권한 필터를 먼저 적용한다.

## failure modes

- unauthorized mutation
- source 없는 요약
- 잘못된 상태 전이 제안
- schema 불일치

## expected output

- 승인 전 미리보기
- 상태/필드 변경 제안
- 관련 근거 링크

## eval rubric

- `action_classification_accuracy`
- `schema_validity`
- `unauthorized_mutation_block_rate`
- `summary_groundedness`
