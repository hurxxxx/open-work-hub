# Release Gate 및 알림 기준

## 게이트 레벨

### `go`

- 시나리오 scorecard가 `green`
- 안전성 실패 없음
- 필수 offline eval 완료
- 운영 알림에 신규 high severity 없음

### `hold-until-review`

- scorecard가 `yellow`
- 안전성은 통과했으나 shadow/drift 회귀 존재
- 운영 triage 검토 후 재판단 필요

### `hold`

- scorecard가 `red`
- critical golden 실패 또는 안전성 실패 존재

### `rollback-candidate`

- 배포 후 online eval 또는 운영 알림에서 severe issue가 확인됨
- 최근 변경이 직접 원인일 가능성이 높음

## 알림 우선순위

| 우선순위 | 조건 | 기본 조치 |
| --- | --- | --- |
| `sev-1` | ACL 위반, unsafe SQL 실행 가능성, catastrophic OCR 대량 발생 | 즉시 차단, rollback 검토 |
| `sev-2` | citation 누락 급증, groundedness 급락, export 실패 급증 | hotfix 또는 fallback 전환 |
| `sev-3` | shadow set 회귀, 응답 지연 상승, 단일 시나리오 품질 저하 | 다음 릴리즈 전 조정 |
| `sev-4` | 경미한 UI/포맷 불일치, 비핵심 drift | backlog 편입 |

## 운영 루틴

### 매 요청

- trace 생성
- guardrail 실행
- online eval 샘플링

### 매일

- `triage/hard-fail` 검토
- 운영 실패 사례를 eval 편입 후보로 분류
- OCR 실패 분포와 엔진 fallback 현황 확인

### 매주

- 시나리오별 scorecard 추세 검토
- release gate 기준 대비 drift 확인
- false positive/false negative evaluator 점검
- `promptfoo` 구성과 dataset drift 를 점검

## 기본 경보 조건

- `acl_violations > 0`
- `unsafe_sql_block_rate < 1.00`
- `citation_completeness < 0.98` on `documents-rag`
- `template_field_fill_rate < 0.95` on `draft-generation`
- `catastrophic_failure_rate > 0.01` on `ocr-pipeline`

## triage 항목 필수 필드

- `trace_id`
- `scenario_id`
- `severity`
- `symptom`
- `suspected_surface`
- `first_seen_at`
- `latest_seen_at`
- `owner`
- `status`
- `next_action`

## 승인 규칙

- `documents-rag`, `plm-query`, `draft-generation`, `ocr-pipeline`는 각각 독립 release gate를 가진다.
- 하나의 시나리오가 `hold`여도 다른 시나리오 배포는 가능하지만, 공통 패키지나 공용 모델 프로필 변경이면 전체 게이트를 다시 본다.
- 공용 LLM profile, reranker, OCR 기본엔진 변경은 모든 관련 시나리오 scorecard를 다시 생성해야 한다.
- `PromptBundle` 또는 `TraceGradeSpec` 변경도 관련 시나리오 scorecard 재확인의 근거가 된다.

## 문서 동기화 규칙

- 기능, API, 운영 플로우, 시나리오 규약이 바뀌었는데 관련 문서가 갱신되지 않았다면 release gate를 바로 막지는 않더라도 `informational`로 남긴다.
- 문서 최신화가 필요한 경우 작업자는 `document-release` 흐름으로 정리한다.
- durable learning, checkpoint, retro는 운영 로그가 아니라 프로젝트 지식 자산으로 취급한다.
