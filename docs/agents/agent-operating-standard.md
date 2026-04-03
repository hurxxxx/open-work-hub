# 에이전트 공통 실행 규약

## 목적

이 문서는 Codex, Claude Code, Copilot, Cursor 등 어떤 에이전트를 사용하더라도 같은 입력에서 비슷한 결과를 내기 위한 공통 규약이다. 도구별 어댑터는 이 문서를 요약하거나 참조할 수는 있지만, 규칙 자체를 바꾸면 안 된다.

## 진실원본 우선순위

1. [docs/agents/agent-operating-standard.md](/Users/edward/projects/doowon/docs/agents/agent-operating-standard.md)
2. [docs/agents/context-loading-policy.md](/Users/edward/projects/doowon/docs/agents/context-loading-policy.md)
3. 관련 [시나리오 문서](/Users/edward/projects/doowon/docs/harness/scenarios)
4. [docs/harness/eval-regression-spec.md](/Users/edward/projects/doowon/docs/harness/eval-regression-spec.md)
5. [docs/harness/service-runtime-harness.md](/Users/edward/projects/doowon/docs/harness/service-runtime-harness.md)
6. [docs/ops/release-gates-and-alerts.md](/Users/edward/projects/doowon/docs/ops/release-gates-and-alerts.md)

## 모든 작업의 시작 규칙

- 먼저 요청을 하나의 `scenario_id`에 매핑한다.
- 해당 시나리오 문서를 먼저 읽고, 필요한 경우에만 eval/runtime/ops 문서를 추가로 읽는다.
- `prompt`, `workflow`, `retrieval`, `guardrail`, `trace`, `export` 중 무엇이 바뀌는지 식별한다.
- 변경 산출물을 `code`, `docs`, `evals`, `ops`로 분류한다.
- 익숙하지 않은 런타임, 인프라, 라이브러리, 운영 패턴은 바로 설계하지 말고 공식 문서나 저장소를 먼저 탐색한다.

## 컨텍스트 로딩 규칙

- 루트 컨텍스트는 최소화한다.
- 기본적으로 관련 없는 다른 시나리오 문서와 도메인 설명은 읽지 않는다.
- `현재 시나리오 + 현재 변경 표면 + 현재 eval/gate`에 직접 관련된 문서만 선택적으로 읽는다.
- 전체 디렉터리 트리, 전체 API 명세, 장황한 프로젝트 배경은 요청이 직접 필요로 할 때만 읽는다.
- 긴 문서를 사용할 때는 quote-first 또는 extract-first 방식으로 관련 근거를 좁힌 뒤 생성 단계로 넘긴다.

## LLM 관련 변경 규칙

- Prompt 변경 시 대응 `EvalCase`를 같이 갱신한다.
- Workflow 변경 시 trace/span 영향과 release gate 영향을 같이 기록한다.
- 서비스 LLM 경로 추가/변경 시 online eval과 fallback 경로를 같이 점검한다.
- citation 없는 생성 응답을 성공으로 취급하지 않는다.
- 변경이 사용자 흐름, API, 운영 방법, eval 규칙에 영향을 주면 문서 동기화 여부를 같이 점검한다.

## 출력 계약

에이전트는 결과 설명이나 PR 설명에서 아래 항목을 항상 명시한다.

- `scenario_id`
- `changed surfaces`
- `required regressions`
- `open risks`

## 파일 소유권 규칙

- `legacy_ai_portal_prototype/`는 수정하지 않는다.
- 도메인 내부 구현은 해당 도메인 패키지 소유자만 직접 수정한다는 가정으로 접근한다.
- 조립 계층(`apps/*`)은 wiring만 한다.
- 공용 계약은 `packages/contracts` 또는 문서 계약에서 먼저 정의한다.
- 하네스 원본 문서는 `docs/*`에만 둔다.

## 금지 사항

- 시나리오 문서 없이 prompt/workflow만 단독으로 바꾸지 않는다.
- eval 없이 release gate를 바꾸지 않는다.
- 권한 정책 없이 PLM 실행 경로를 추가하지 않는다.
- 사용자의 별도 지시 없이 `git commit` 또는 `git push`를 하지 않는다.

## 기본 응답 형식

작업 결과를 설명할 때는 아래 구조를 우선한다.

```text
scenario_id: ...
changed surfaces: ...
tests/evals: ...
open risks: ...
```

## 멀티에이전트 협업 규칙

- 한 에이전트는 하나의 시나리오 또는 한 도메인 경계 안에서만 깊게 수정한다.
- 다른 에이전트가 소유한 파일을 건드려야 하면 contracts, docs, facade부터 검토한다.
- 리뷰 전용 에이전트는 가능하면 read-only 도구만 사용한다.

## 운영 습관

- 큰 변경 전에는 `checkpoint`를 남겨 현재 상태와 다음 위험을 요약한다.
- 비직관적인 패턴, 함정, 운영 인사이트를 발견하면 `learn` 흐름으로 남긴다.
- 의미 있는 변경이 끝나면 `document-release` 관점으로 문서 동기화를 점검한다.
- 큰 단위 작업이 끝나면 `retro` 관점으로 무엇이 반복 가능한지 정리한다.

## 도구별 적용

- Claude Code: `CLAUDE.md`, `.claude/rules`, `.claude/commands`, `.claude/agents`, hooks
- Codex: repo-owned skill
- Copilot: `.github/copilot-instructions.md`
- Cursor: `.cursor/rules/*.mdc`
- 명령/도구 카탈로그: `docs/agents/agent-tooling-registry.md`
