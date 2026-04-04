# 하네스 엔지니어링 개요

## 목적

이 프로젝트의 하네스 엔지니어링은 개발과 서비스 운영에서 사용하는 모든 LLM 경로를 동일한 계약 아래 관리하기 위한 체계다. 목표는 다음 세 가지다.

- 에이전트와 개발자가 같은 문서와 같은 시나리오 키를 사용하게 한다.
- Prompt 변경이 eval, release gate, 운영 trace와 분리되지 않게 한다.
- 서비스 품질을 정적 테스트가 아니라 `offline eval + online eval + feedback loop`로 안정화한다.

## 채택한 패턴

다음 공식 제품/문서에서 검증된 공통 패턴을 흡수한다.

- `Braintrust`, `Humanloop`, `HoneyHive`: dataset 중심 실험, prompt/workflow versioning, eval run과 배포 게이트 연결
- `LangSmith`, `Phoenix`, `Galileo`: trace/span 중심 관찰성, retriever/generator 분리 평가, step-level evaluator
- `W&B Weave`: 실험 로그와 운영 로그의 동일 개념 모델화
- `Patronus AI`: 실패 분류와 운영 가드레일 분리
- `Claude Code`: `CLAUDE.md`, `.claude/rules`, hooks, slash commands, subagents, skills 조합

## 진실원본

다음 문서는 모든 에이전트와 구현이 공통으로 참조해야 하는 원본이다.

- 컨텍스트 선택 기준: [docs/agents/context-loading-policy.md](/Users/edward/projects/doowon/docs/agents/context-loading-policy.md)
- 구조 기준: [docs/architecture/system-blueprint.md](/Users/edward/projects/doowon/docs/architecture/system-blueprint.md)
- 에이전트 규약: [docs/agents/agent-operating-standard.md](/Users/edward/projects/doowon/docs/agents/agent-operating-standard.md)
- 도메인 경로 매핑: [docs/agents/domain-context-mapping.md](/Users/edward/projects/doowon/docs/agents/domain-context-mapping.md)
- 서비스 하네스: [docs/harness/service-runtime-harness.md](/Users/edward/projects/doowon/docs/harness/service-runtime-harness.md)
- 평가/회귀: [docs/harness/eval-regression-spec.md](/Users/edward/projects/doowon/docs/harness/eval-regression-spec.md)
- trace/scorecard: [docs/harness/trace-and-scorecard-spec.md](/Users/edward/projects/doowon/docs/harness/trace-and-scorecard-spec.md)

## 구조화 자산

최신 하네스 엔지니어링 기준에 맞추기 위해, 이 저장소는 prose 문서만이 아니라 실행 가능한 구조화 자산을 함께 진실원본으로 둔다.

- `ScenarioManifest`: [docs/harness/manifests/scenarios](/Users/edward/projects/doowon/docs/harness/manifests/scenarios)
- `DomainRuleManifest`: [docs/agents/manifests/domain-rule-manifests](/Users/edward/projects/doowon/docs/agents/manifests/domain-rule-manifests)
- `PromptBundle`: [docs/harness/prompt-bundles](/Users/edward/projects/doowon/docs/harness/prompt-bundles)
- `EvalSuite`: [docs/harness/manifests/eval-suites](/Users/edward/projects/doowon/docs/harness/manifests/eval-suites)
- `TraceGradeSpec`: [docs/harness/manifests/trace-grade-specs](/Users/edward/projects/doowon/docs/harness/manifests/trace-grade-specs)
- `promptfoo` 실행 자산: [docs/harness/evals](/Users/edward/projects/doowon/docs/harness/evals)

문서는 원칙과 설명을 담당하고, 실제 로딩/평가/버전 연결은 위 자산이 담당한다.

## 컨텍스트 경제성

- 긴 컨텍스트를 넣을 수 있다고 해서 항상 많이 넣지 않는다.
- 기본 로딩은 `루트 규약 + 현재 시나리오`로 시작한다.
- 보조 문서는 eval, runtime, release gate가 실제로 필요할 때만 추가한다.
- 다른 도메인 설명과 unrelated 시나리오는 기본적으로 제외한다.

## 공통 객체

### `ScenarioManifest`

- 하나의 사용자 가치 또는 업무 흐름을 대표하는 최상위 단위
- 모든 LLM 작업은 먼저 정확히 하나의 `scenario_id`에 매핑한다

### `DomainRuleManifest`

- 파일 경로와 도메인 책임, 시나리오 후보, 기본 비로드 문서를 연결하는 계약
- path-scoped context loading 의 첫 번째 기준

### `PromptBundle`

- stage별 고정 지시, 변수 슬롯, 컨텍스트 계약을 버전 객체로 묶은 자산
- OpenAI/Anthropic 권장대로 고정 지시와 가변 컨텍스트를 분리한다

### `EvalSuite`

- dataset, grader, threshold, runner, promptfoo 설정을 묶은 실행 가능한 평가 계약

### `TraceGradeSpec`

- span별 grader, online sampling 정책, 동기 guardrail 을 정의하는 런타임 평가 계약

### `TraceEvent` / `SpanRecord`

- 서비스 요청을 추적하는 상위 이벤트와 하위 단계 기록

### `Scorecard`

- 시나리오별 품질 상태, 회귀 여부, 배포 가능 여부를 요약한 결과판

### `ReleaseGateDecision`

- `go`, `hold`, `rollback-candidate` 중 하나의 결정

### `ServiceGuardrailPolicy`

- 런타임에서 즉시 차단해야 하는 정책과 fallback 규칙

## 운영 루프

### 개발 루프

`ScenarioManifest 확정 -> PromptBundle/EvalSuite/TraceGradeSpec 갱신 -> Dataset 갱신 -> Offline Eval(promptfoo) -> Scorecard -> Release Gate`

### 서비스 루프

`Request -> Trace/Span 기록 -> Online Eval -> Alert/Feedback -> Failure Triage -> Dataset case 편입 -> 다음 Release Gate`

## 작업 흐름

이 저장소는 gstack의 스프린트형 사고방식 중 작업 순서 개념을 차용하되, 하네스 중심으로 재구성한다.

`탐색 -> 시나리오 확정 -> 계획/계약 정리 -> 구현 -> 리뷰/평가 -> 문서 동기화 -> 릴리즈 판단 -> 회고/학습`

- 탐색: 공식 문서, 기존 코드, 기존 eval 결과를 먼저 확인한다.
- 시나리오 확정: 하나의 `scenario_id`를 고정한다.
- 계획/계약 정리: `ScenarioManifest`, `PromptBundle`, `EvalSuite`, `TraceGradeSpec`, `ServiceGuardrailPolicy` 영향을 정리한다.
- 구현: 도메인 경계 안에서만 수정한다.
- 리뷰/평가: 관련 offline eval과 scorecard 조건을 다시 본다.
- 문서 동기화: 관련 `docs/*`와 에이전트 어댑터를 갱신한다.
- 릴리즈 판단: `ReleaseGateDecision`을 점검한다.
- 회고/학습: durable learning과 checkpoint를 남긴다.

## 버전 규칙

- `scenario_id`: 영문 kebab-case
- `workflow_version`: `<scenario>-wf-vN`
- `prompt_version`: `<scenario>-prompt-vN`
- `retrieval_profile`: `<scenario>-ret-vN`
- `eval_profile`: `<scenario>-eval-vN`

버전은 코드 커밋 해시와 별도로 관리한다. 코드 변경 없이 프롬프트/평가 기준만 바뀔 수 있기 때문이다.

## 문서와 구조화 자산의 역할 분리

모든 시나리오 문서는 아래 섹션을 반드시 포함한다.

1. `goal`
2. `input schema`
3. `allowed tools`
4. `prompt contract`
5. `retrieval policy`
6. `failure modes`
7. `expected output`
8. `eval rubric`

시나리오 문서는 [docs/harness/scenarios](/Users/edward/projects/doowon/docs/harness/scenarios) 아래에 저장한다.

동시에 각 시나리오에는 아래 구조화 자산이 함께 있어야 한다.

- `docs/harness/manifests/scenarios/<scenario>.json`
- `docs/harness/prompt-bundles/<scenario>/workflow.json`
- `docs/harness/manifests/eval-suites/<scenario>.json`
- `docs/harness/manifests/trace-grade-specs/<scenario>.json`
- `docs/harness/evals/promptfoo/scenarios/<scenario>.yaml`

## 변경 정책

- Prompt 또는 workflow를 바꾸면 해당 시나리오 문서와 `PromptBundle`, `EvalSuite`, `TraceGradeSpec` 도 같이 바꾼다.
- 서비스 LLM 경로를 추가하면 trace/span, online eval, release gate 영향까지 같이 기록한다.
- 운영에서 수집된 실패 사례는 익일 eval set 편입 후보로 등록한다.
- citation 없는 생성 응답은 성공으로 간주하지 않는다.
- ACL 위반, unsafe SQL, catastrophic OCR failure는 온라인 평가가 아니라 동기 가드레일로 차단한다.

## 시나리오 목록

- [documents-rag](/Users/edward/projects/doowon/docs/harness/scenarios/documents-rag.md)
- [plm-query](/Users/edward/projects/doowon/docs/harness/scenarios/plm-query.md)
- [draft-generation](/Users/edward/projects/doowon/docs/harness/scenarios/draft-generation.md)
- [ocr-pipeline](/Users/edward/projects/doowon/docs/harness/scenarios/ocr-pipeline.md)
- [wiki-pms](/Users/edward/projects/doowon/docs/harness/scenarios/wiki-pms.md)
