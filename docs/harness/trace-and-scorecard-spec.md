# Trace 및 Scorecard 계약

## `TraceEvent`

하나의 사용자 요청 또는 배치 실행을 대표하는 최상위 레코드다.

필수 필드:

- `trace_id`
- `scenario_id`
- `workflow_version`
- `prompt_version`
- `retrieval_profile`
- `llm_profile`
- `eval_profile`
- `user_role`
- `acl_scope`
- `status`
- `started_at`
- `ended_at`

예시:

```json
{
  "trace_id": "trc_20260403_0001",
  "scenario_id": "documents-rag",
  "workflow_version": "documents-rag-wf-v1",
  "prompt_version": "documents-rag-prompt-v1",
  "retrieval_profile": "documents-rag-ret-v1",
  "llm_profile": "qwen3-32b-instruct-bf16",
  "eval_profile": "documents-rag-eval-v1",
  "user_role": "engineer",
  "acl_scope": ["doc:engineering", "plm:read"],
  "status": "success",
  "started_at": "2026-04-03T09:00:00Z",
  "ended_at": "2026-04-03T09:00:02Z"
}
```

## `SpanRecord`

각 trace 안의 세부 처리 단계를 나타낸다.

필수 필드:

- `trace_id`
- `span_id`
- `name`
- `status`
- `input_ref`
- `output_ref`
- `latency_ms`
- `started_at`
- `ended_at`

권장 필드:

- `model`
- `tool`
- `document_ids`
- `citation_ids`
- `safety_flags`

## `OnlineEvalResult`

비동기 평가 실행 결과다.

필수 필드:

- `trace_id`
- `scenario_id`
- `evaluator_id`
- `metric`
- `score`
- `passed`
- `recorded_at`

## `GuardrailDecision`

동기 차단 정책 결과다.

필수 필드:

- `trace_id`
- `policy_id`
- `decision`
- `reason`
- `action`
- `recorded_at`

`decision` 값:

- `allow`
- `fallback`
- `block`

## `Scorecard`

시나리오별 release gate 판단용 요약 객체다.

필수 필드:

- `scenario_id`
- `candidate_version`
- `baseline_version`
- `status`
- `metrics`
- `regressions`
- `gate_decision`
- `generated_at`

예시:

```json
{
  "scenario_id": "plm-query",
  "candidate_version": "plm-query-wf-v2",
  "baseline_version": "plm-query-wf-v1",
  "status": "green",
  "metrics": {
    "unsafe_sql_block_rate": 1.0,
    "approved_query_success_rate": 0.97,
    "summary_fidelity": 0.92
  },
  "regressions": [],
  "gate_decision": "go",
  "generated_at": "2026-04-03T09:15:00Z"
}
```

## `ReleaseGateDecision`

최종 배포 판단이다.

필수 필드:

- `scenario_id`
- `scorecard_status`
- `decision`
- `owner`
- `summary`
- `recorded_at`

`decision` 값:

- `go`
- `hold-until-review`
- `hold`
- `rollback-candidate`

## `TraceGradeSpec`

trace/span 단위 grading 기준은 시나리오별 `TraceGradeSpec` 으로 분리한다.

- 위치: [docs/harness/manifests/trace-grade-specs](/Users/edward/projects/doowon/docs/harness/manifests/trace-grade-specs)
- 목적: span별 grader, sampling 비율, blocking guardrail 명시
- 사용처: online eval sampler, scorecard 보조 지표, release gate 근거

## 훅 계약

프로젝트 훅은 최소 아래 세 가지 출력을 사용한다.

- `deny`: 차단해야 하는 편집/명령
- `allow`: 특별한 제약 없이 허용
- `async-notice`: 비동기 후속 점검 또는 로그 기록

관련 스키마:

- [hook-decision.schema.json](/Users/edward/projects/doowon/docs/harness/schemas/hook-decision.schema.json)
- [trace-event.schema.json](/Users/edward/projects/doowon/docs/harness/schemas/trace-event.schema.json)
- [scorecard.schema.json](/Users/edward/projects/doowon/docs/harness/schemas/scorecard.schema.json)
- [release-gate-decision.schema.json](/Users/edward/projects/doowon/docs/harness/schemas/release-gate-decision.schema.json)
- [trace-grade-spec.schema.json](/Users/edward/projects/doowon/docs/harness/schemas/trace-grade-spec.schema.json)
