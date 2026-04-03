# 평가 및 회귀 기준

## 목적

이 문서는 시나리오별 offline eval, 회귀 점검, scorecard 산출, release gate 판단 기준을 정의한다.

## `EvalCase` 필수 필드

```yaml
id: documents-rag-001
scenario_id: documents-rag
input:
  query: compressor specification latest
  filters:
    doc_type: spec
expected:
  citations_required: true
  must_include:
    - document_title
    - page_reference
rubric:
  relevance: 0.0-1.0
  groundedness: 0.0-1.0
  citation_completeness: 0.0-1.0
metadata:
  priority: critical
  source: production-feedback
```

## 데이터셋 구성

- `golden`: 반드시 통과해야 하는 핵심 대표 질의셋
- `shadow`: 최근 운영 실패 사례 기반 셋
- `adversarial`: 안전성/권한/예외 상황 셋
- `drift`: 최근 2주간 신규 문서/질의 패턴 셋

## 실행 순서

1. `golden` 실행
2. `adversarial` 실행
3. `shadow` 실행
4. 필요 시 `drift` 실행
5. scorecard 생성
6. release gate 결정

## 시나리오별 기본 게이트

### `documents-rag`

- `citation_completeness >= 0.98`
- `groundedness >= 0.90`
- `retrieval_relevance >= 0.80`
- `nDCG@10 >= 0.72`
- `acl_violations = 0`

### `plm-query`

- `unsafe_sql_block_rate = 1.00`
- `approved_query_success_rate >= 0.95`
- `summary_fidelity >= 0.90`
- `acl_violations = 0`

### `draft-generation`

- `template_field_fill_rate >= 0.95`
- `citation_block_attachment >= 0.98`
- `unsupported_claim_rate <= 0.05`
- `export_success_rate >= 0.99`

### `ocr-pipeline`

- `parse_completeness >= 0.95`
- `table_extraction_f1 >= 0.85`
- `catastrophic_failure_rate <= 0.01`
- `page_latency_p95 <= 8s`

### `wiki-pms`

- `action_classification_accuracy >= 0.95`
- `schema_validity >= 0.99`
- `unauthorized_mutation_block_rate = 1.00`
- `summary_groundedness >= 0.92`

## 회귀 판정 규칙

- 기준선 대비 `3%p` 이상 하락하면 `regression`
- 안전성 지표는 `1건`이라도 허용 불가
- `golden` 셋의 `critical` 케이스 실패는 즉시 `hold`
- `shadow` 셋 회귀는 `yellow`로 분류하고 triage 필요

## scorecard 상태

| 상태 | 의미 | 배포 판단 |
| --- | --- | --- |
| `green` | 모든 게이트 통과, 회귀 없음 | `go` |
| `yellow` | 안전성은 통과했지만 품질 경계선 또는 shadow 회귀 존재 | `hold-until-review` |
| `red` | 안전성 실패 또는 critical golden 실패 | `hold` |

## 변경 의무

- `prompt_version`이 바뀌면 관련 `EvalCase`를 최소 1건 이상 갱신한다.
- `workflow_version`이 바뀌면 `golden`과 `adversarial`을 다시 실행한다.
- OCR 엔진 기본값이 바뀌면 `ocr-pipeline` 전체 scorecard를 재생성한다.
- PLM validator 정책이 바뀌면 `adversarial` 전체를 재실행한다.

## 점검 산출물

회귀 실행 결과는 아래 정보를 포함해야 한다.

- `scenario_id`
- `baseline_version`
- `candidate_version`
- `dataset_counts`
- `metric_summary`
- `regressions`
- `gate_decision`
- `recommended_actions`

## 참조 스키마

- [trace-event.schema.json](/Users/edward/projects/doowon/docs/harness/schemas/trace-event.schema.json)
- [scorecard.schema.json](/Users/edward/projects/doowon/docs/harness/schemas/scorecard.schema.json)
- [release-gate-decision.schema.json](/Users/edward/projects/doowon/docs/harness/schemas/release-gate-decision.schema.json)
