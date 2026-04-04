# 컨텍스트 선택 및 로딩 정책

## 목적

이 문서는 에이전트와 서비스 프롬프트에 불필요한 정보를 넣지 않기 위한 기준을 정의한다. 기본 원칙은 `작업에 꼭 필요한 정보만, 필요한 시점에만 로드한다` 이다.

## 왜 필요한가

최근 공식 문서와 대표 연구는 공통적으로 다음을 시사한다.

- 긴 컨텍스트가 가능해도 관련 정보가 묻히면 성능이 떨어질 수 있다.
- 불필요한 지시와 중복 설명은 지연과 비용만 늘리는 것이 아니라 정확도와 일관성도 해칠 수 있다.
- 긴 문서 작업에서는 관련 인용과 구조화가 없으면 노이즈가 커져 환각 가능성이 올라간다.

## 외부 근거에서 채택한 원칙

### 1. 길다고 다 넣지 않는다

- Anthropic은 프롬프트를 `clear but concise` 하게 유지하고 불필요한 세부사항과 중복 정보를 피하라고 권장한다.
- `Lost in the Middle`은 관련 정보가 긴 컨텍스트 중간에 묻힐 때 성능이 유의미하게 떨어질 수 있음을 보였다.
- Google의 long-context 문서는 긴 컨텍스트가 있어도 여러 개의 `needle`을 찾는 상황에서는 정확도가 넓게 흔들릴 수 있다고 설명한다.

### 2. 고정 지시와 가변 컨텍스트를 분리한다

- Anthropic의 prompt templates 가이드는 고정 지시와 매 요청마다 바뀌는 가변 컨텍스트를 분리하라고 권장한다.
- 이 저장소에서는 고정 지시는 최소 역할, 안전 규칙, 출력 계약만 담고, 가변 컨텍스트는 현재 작업과 직접 관련된 데이터만 넣는다.

### 3. 긴 문서는 구조화하고, 먼저 근거를 뽑는다

- Anthropic의 long context 팁은 긴 문서를 위쪽에 두고 질의/지시는 뒤에 두는 방식을 권장한다.
- 같은 문서는 XML 같은 구조화 태그와 quote-first 방식으로 노이즈를 줄이라고 권장한다.
- hallucination 가이드는 긴 문서 작업에서 직접 인용을 먼저 추출하도록 해서 환각을 줄이라고 권장한다.

### 4. 과도한 단계 지시는 줄인다

- Anthropic의 extended thinking 팁은 고수준 지시를 먼저 주고, 필요할 때만 더 세부적인 단계 지시를 추가하라고 권장한다.
- 이미 모델이 잘 풀 수 있는 문제에 지나치게 세세한 사고 지시를 넣으면 오히려 성능이 떨어질 수 있다.

## 저장소 기본 규칙

### 루트 컨텍스트

- 루트에서 항상 로드되는 정보는 최소로 유지한다.
- 기본 로드 대상은 `agents.md` 와 이 문서다.
- 상세 하네스, 시나리오, 운영 문서는 작업 선택 이후에만 읽는다.

### 작업 시작 시

1. 변경 대상 경로나 작업 대상 경로가 있으면 먼저 `DomainRuleManifest` 를 찾는다.
2. 그 다음 `scenario_id` 하나를 고른다.
3. 관련 `ScenarioManifest` 와 `workflow.json` 을 먼저 읽는다.
4. 관련 시나리오 문서 하나만 읽는다.
5. 필요할 때만 다음 보조 문서를 추가한다.
   - `eval-regression-spec`
   - `service-runtime-harness`
   - `release-gates-and-alerts`
   - `system-blueprint`
   - frontend 디자인 작업이면 `enterprise-portal-design-direction`
6. 관련 없는 다른 시나리오 문서는 기본적으로 읽지 않는다.

### 기본적으로 넣지 말아야 하는 것

- 현재 작업과 무관한 다른 도메인 설명
- 전체 디렉터리 트리 덤프
- 현재 시점의 상세 패키지/모듈 배치 스냅샷
- 장황한 프로젝트 배경 설명
- 바뀌지 않은 API 전체 명세
- 관련 없는 과거 실험 기록
- 모델이 이미 알고 있을 가능성이 높은 일반 코딩 상식

### 넣어야 하는 정보

- 현재 시나리오 문서
- 현재 `DomainRuleManifest`
- 현재 `ScenarioManifest`
- 현재 stage의 `PromptBundle`
- 현재 수정 중인 파일/계약
- 현재 요청의 입력 데이터 또는 질의
- 현재 release gate 와 eval 기준
- 현재 작업에서 실제로 참조해야 하는 근거 문서/quote

## 컨텍스트 확장 사다리

작업이 막히면 아래 순서로만 컨텍스트를 확장한다.

1. 현재 시나리오 문서
2. 현재 시나리오의 `EvalSuite`
3. 현재 시나리오의 `TraceGradeSpec`
4. 현재 시나리오의 런타임 하네스
5. 현재 작업과 직접 연결된 도메인 구조 문서
6. 정말 필요한 경우에만 cross-domain 문서

상위 단계로 갈수록 `왜 필요한지`를 먼저 설명하고 로드한다.

## 서비스 프롬프트 포장 규칙

- system prompt 는 역할, 안전 규칙, 출력 계약만 유지한다.
- `PromptBundle` 은 고정 지시 파일과 변수 슬롯을 분리한다.
- retrieved context 는 현재 질의와 ACL 을 통과한 관련 chunk 만 넣는다.
- 긴 문서 기반 작업은 quote-first 또는 extract-first 후 synthesis 로 나눈다.
- 관련 없는 문서, 부서, 기능 설명은 retrieval payload 에 넣지 않는다.
- top-k 는 크게 시작하지 말고 리랭크된 관련 chunk 기준으로 작게 시작하고 필요 시 확장한다.

## 에이전트 도구 적용

- `CLAUDE.md` 는 최소 import 만 유지한다.
- Codex skill 은 시나리오 선택 후 필요한 문서만 읽도록 유도한다.
- Claude Code 명령은 가능하면 `must_read_docs` 와 `do_not_load_by_default` 를 같이 출력한다.
- Adapter 파일은 원본 문서를 복제하지 않고 최소 참조만 유지한다.
- helper 스크립트는 하드코딩 목록보다 manifest 를 우선 읽는다.

## 참조

- Anthropic long context prompting tips: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/long-context-tips
- Anthropic reduce hallucinations: https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/reduce-hallucinations
- Anthropic reduce latency: https://docs.anthropic.com/en/docs/test-and-evaluate/strengthen-guardrails/reduce-latency
- Anthropic prompt templates and variables: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/prompt-templates-and-variables
- Anthropic extended thinking tips: https://docs.anthropic.com/en/docs/build-with-claude/prompt-engineering/extended-thinking-tips
- Google long context: https://docs.cloud.google.com/vertex-ai/generative-ai/docs/long-context
- Google prompt design strategies: https://cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/prompt-design-strategies
- Lost in the Middle: https://arxiv.org/abs/2307.03172
