# Scenario: draft-generation

## goal

문서 템플릿과 근거 문서를 사용해 초안을 생성하고, citation block과 자동 채움 필드를 유지한 채 검토/내보내기 가능 상태로 만든다.

## input schema

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `template_id` | string | yes | 초안 템플릿 |
| `topic` | string | yes | 작성 주제 |
| `context_doc_ids` | string[] | no | 우선 근거 문서 |
| `field_overrides` | object | no | 사용자 지정 필드 |
| `output_format` | enum | no | `docx` 또는 `pdf` |

## allowed tools

- Template resolver
- Documents retrieval
- Citation assembler
- Draft generator
- Export pipeline

## prompt contract

- 자동 채움 필드는 이름과 타입을 보존한다.
- 근거 없는 문장을 생성하지 않는다.
- 각 섹션은 최소 하나 이상의 citation block과 연결된다.
- 템플릿에 필요하지 않은 다른 도메인 설명이나 unrelated 운영 규칙은 draft generation context 에 넣지 않는다.
- 출력은 `draft_body`, `field_values`, `citations`, `missing_inputs`, `export_status` 구조를 따른다.

## retrieval policy

- 템플릿이 요구하는 섹션별 evidence query를 먼저 생성한다.
- 사용자가 제공한 `context_doc_ids`를 최우선 근거 후보로 사용한다.
- 동일 주장에 여러 근거가 있으면 최신 문서와 공식 문서를 우선한다.

## failure modes

- 필수 필드 미채움
- 근거 없는 주장
- citation block 누락
- export 렌더링 실패

## expected output

- 포털 내 수정 가능한 초안
- 채워진 필드 목록
- 누락된 입력 안내
- `docx/pdf` 내보내기 작업 상태

## eval rubric

- `template_field_fill_rate`
- `citation_block_attachment`
- `unsupported_claim_rate`
- `export_success_rate`
