# Scenario: plm-query

## goal

PLM 데이터를 읽기 전용으로 안전하게 조회하고, 자연어 요청을 표 형태 결과와 짧은 해석으로 반환한다.

## input schema

| 필드 | 타입 | 필수 | 설명 |
| --- | --- | --- | --- |
| `query` | string | yes | 사용자 질의 |
| `template_id` | string | no | 사전 정의 조회 템플릿 |
| `constraints` | object | no | 기간, 품목, 프로젝트 등 조건 |
| `preview_only` | boolean | no | 기본값 true |

## allowed tools

- Intent router
- Template matcher
- SQL planner
- SQL validator
- Read-only executor
- Result summarizer

## prompt contract

- 생성 SQL은 validator를 통과하기 전까지 실행하지 않는다.
- 허용 view/table allowlist 밖의 객체는 참조하지 않는다.
- 쓰기, DDL, 권한 변경, 주석 힌트, 멀티스테이트먼트는 금지한다.
- 현재 PLM 조회와 직접 관련 없는 문서 RAG, Wiki, PMS 설명은 prompt context 에 포함하지 않는다.
- 출력은 `query_plan`, `sql_preview`, `result_summary`, `result_table`, `warnings` 구조를 따른다.

## retrieval policy

- 자연어에서 먼저 템플릿 매칭을 시도한다.
- 템플릿 적합도가 낮을 때만 생성형 SQL 계획으로 이동한다.
- 실제 실행은 validator가 `safe`를 반환한 단일 statement에 한정한다.

## failure modes

- unsafe SQL 생성
- 허용되지 않은 스키마 참조
- 결과 과다로 인한 실행 부담
- 요약이 실제 결과와 불일치

## expected output

- 표 중심 결과
- 사용된 필터와 정렬 기준
- 필요한 경우 다음 refinement 제안

## eval rubric

- `unsafe_sql_block_rate`
- `template_match_accuracy`
- `execution_accuracy`
- `summary_fidelity`
- `acl_correctness`
