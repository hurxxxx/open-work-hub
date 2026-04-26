# Evidence-First Agent Runtime

> 문서 성격: Doowon AI runtime 재설계를 위한 실행 설계 문서.  
> 기준 연구 문서: [`01-agentic-harness-engineering-report.md`](./01-agentic-harness-engineering-report.md)  
> 목표: 로컬 LLM 한계를 줄이고, 새 컨텍스트 추가와 모델 교체가 쉬운 agent 운영 구조를 만든다.

## Context

현재 Doowon AI 플랫폼은 MCP-shaped capability registry, workspace-scoped tool gateway, RAG provider, approval flow, streaming envelope를 이미 갖고 있다. 다만 agent 실행 모델은 아직 단일 agent loop 중심이다. 이 구조는 단기 구현에는 빠르지만, 다음 요구가 커질수록 유지보수 비용이 높아진다.

- 로컬 Qwen 계열 LLM은 긴 context와 tool calling을 지원하지만, 큰 tool catalog와 긴 대화 이력에 취약하다.
- PMS, Meeting, Docs, Planner, RAG 같은 도메인 컨텍스트가 계속 늘어난다.
- 추후 LLM 모델이나 serving stack이 바뀌어도 agent contract와 tool/context boundary는 유지되어야 한다.
- 사용자 정의 템플릿, batch 작업, ambient/event-driven 작업까지 확장하려면 실행 trace와 approval policy가 agent 단위로 남아야 한다.

따라서 목표는 "모든 요청을 multi-agent로 비싸게 실행"하는 것이 아니라, **deterministic shortcut + graph orchestrator + evidence-first specialist runtime**을 만드는 것이다.

## Architecture / Principles

### 1. Deterministic shortcut first

모든 요청을 LLM manager가 먼저 분해하지 않는다. 다음 경우는 manager decomposition 없이 바로 fast path로 보낸다.

- conversation scope가 명확한 경우. 예: meeting-scoped conversation.
- `allowed_app_ids`가 단일 도메인으로 좁혀진 경우.
- 명확한 single-domain read intent가 keyword/rule로 판정되는 경우.
- 사용자가 text-only 또는 no-tool scope를 명시한 경우.

복잡하거나 애매한 요청만 manager graph path로 올린다. 이때도 decomposition과 chosen execution graph는 한 번의 manager LLM 호출에서 함께 받는다.

### 2. Graph orchestrator, not free handoff

에이전트가 서로 자유롭게 위임하는 구조는 로컬 LLM 환경에서 루프, 비용, 디버깅 리스크가 크다. Doowon v1은 manager가 실행 graph를 통제한다.

- Manager가 domain agent, search, verifier, writer invocation을 생성한다.
- Specialist는 자기 tool allowlist와 context source 안에서만 실행된다.
- Verifier는 판단만 하고 recovery를 실행하지 않는다.
- Recovery 결정은 manager policy table이 담당한다.

### 3. Evidence-first

최종 답변과 보고서는 검색 결과 원문 전체가 아니라 `EvidencePacket`을 통해 만들어진다. `EvidencePacket`은 domain agent, verifier, template writer가 공유하는 정본 DTO다.

```ts
type EvidencePacket = {
  query_plan: {
    keywords: string[]
    filters: Record<string, unknown>
    source_kinds: string[]
    sources_used: string[]
    top_k: number
    rerank_strategy?: string
    recency_weighting?: string
    embedding_model_version?: string
  }
  items: Array<{
    ref: ResourceRef
    source_kind: string
    excerpt: string
    score?: number
    freshness?: string
    access_scope?: string
  }>
  coverage: {
    intents_covered: string[]
    intents_missed: string[]
  }
}
```

Verifier는 claim과 evidence를 이 DTO 기준으로 매칭한다. 도메인별 tool result shape이 달라도 manager 이후 단계는 동일한 evidence contract를 본다.

### 4. Task skills are inline by default

`extract`, `summarize`, `compare`, `draft` 같은 일반 task는 별도 agent invocation으로 분리하지 않는다. 로컬 LLM 비용과 latency를 줄이기 위해 domain agent 내부 skill로 처리한다.

별도 invocation으로 분리하는 예외는 다음이다.

- `verifier`: 산출물 검증과 grounding 판단 책임을 분리해야 한다.
- `write_proposal`: write action 전 변경 의도를 별도 구조로 고정해야 한다.
- `approval_preview`: 사용자 승인 경계와 연결된다.
- `template_writer`: 사용자 정의 템플릿과 최종 산출물 품질을 독립적으로 평가해야 한다.

### 5. Risk-based approval

승인은 prompt 지시가 아니라 runtime policy로 강제한다.

- read/search/extract/draft는 기본 자동 실행.
- write, 외부 전송, 권한 변경, 고비용 batch, 낮은 verifier confidence는 승인 또는 review queue 필요.
- batch 작업은 step마다 묻지 않고 workspace/domain/risk policy에 따라 자동 실행하거나 review queue로 보낸다.

### 6. ModelProfile for model swap

모델 교체성은 adapter만으로 충분하지 않다. tool call 형식, reasoning trace, finish reason, malformed tool call 회복 방식, prompt template이 모델마다 다르다.

`ModelProfile`은 다음을 포함한다.

- tool-call parser/format.
- reasoning field visibility와 streaming behavior.
- finish_reason mapping.
- malformed tool call retry policy.
- per-model prompt fragment override.
- thinking mode 기본값과 budget.

`AgentDefinition`은 모델 독립 기본 prompt를 갖고, `ModelProfile`이 Qwen/GPT/Claude 계열 override를 제공한다.

## Runtime Design

### Core models

`domains/ai/runtime/` 아래에 다음 runtime 정본을 둔다.

- `AgentDefinition`
  - `agent_id`, `role`, `purpose`, `non_goals`, `tool_allowlist`, `context_sources`, `skills`, `budget`, `failure_policy`, `model_prompt_overrides`, `eval_cases`.
- `AgentRun`
  - 사용자 요청 하나의 전체 실행 단위.
  - chat, batch, ambient entrypoint를 같은 실행 모델로 수용한다.
- `AgentInvocation`
  - manager/domain/search/verifier/writer 각각의 실행 단위.
  - tool allowlist, input/output, usage, error를 별도로 기록한다.
- `AgentTraceEvent`
  - routing, search plan, tool call, evidence packet, verifier result, approval decision, retry를 순서대로 기록한다.
- `SearchProfile`
  - source kind, query expansion, filters, top-k policy, rerank, recency weighting, embedding model version.
- `VerifierResult`
  - `status`, `missing_evidence`, `unsupported_claims`, `policy_risks`, `suggested_recovery`, `confidence`.
- `ModelProfile`
  - model-family-specific tool, reasoning, prompt, retry behavior.

### Agent set v1

- `manager.orchestrator`
  - fast path가 아닌 요청의 decomposition, graph 생성, recovery, 최종 synthesis를 담당한다.
- `domain.pms`
  - PMS issue/list/status context, issue summary, issue draft skill.
- `domain.meeting`
  - meeting search, transcript/insight context, action/decision/follow-up skill.
- `domain.docs`
  - docs hub/page context, document summary/draft skill.
- `domain.planner`
  - event lookup, availability context, schedule draft skill.
- `domain.rag`
  - cross-domain grounded search와 citation-oriented synthesis.
- `search.planner`
  - 검색 목적, keywords, filters, source kinds, fallback query를 만든다.
- `search.executor`
  - 실제 RAG/DB/tool 검색을 deterministic하게 실행한다.
- `verifier.grounding`
  - evidence coverage, unsupported claim, missing requirement, policy risk를 판단한다.
- `writer.template`
  - EvidencePacket과 사용자 정의 템플릿으로 최종 산출물을 작성한다.
- `approval.preview`
  - write/batch 실행 전 사용자 검토용 preview를 만든다.

### Execution flow

1. Chat request가 들어오면 fast path 조건을 먼저 평가한다.
2. Fast path면 해당 domain agent invocation을 바로 생성한다.
3. Graph path면 manager가 `intent/domain/risk/output`과 execution graph를 한 번에 만든다.
4. Domain agent는 필요한 경우 `SearchPlan`을 만들거나 `search.planner`를 호출한다.
5. `search.executor`가 기존 MCP capability/RAG/domain service를 사용해 evidence를 수집한다.
6. Domain agent는 inline skill로 extract/summarize/compare/draft를 수행한다.
7. 고위험 또는 cross-domain 산출물은 verifier가 `VerifierResult`를 만든다.
8. Verifier fail이면 manager가 recovery policy로 재검색, 추가 domain invocation, 사용자 질문, partial answer 중 하나를 선택한다.
9. Template 요청이면 `writer.template`이 최종 산출물을 만든다.
10. Write/external/batch action은 risk-based approval gate 또는 review queue를 통과한다.

### Recovery policy

기본 policy는 deterministic하게 둔다.

- 재검색 최대 2회.
- 추가 domain invocation 최대 1회.
- 그래도 evidence 부족이면 사용자 질문으로 전환.
- batch에서는 사용자 질문 대신 review queue로 전환.
- partial answer가 허용되면 unsupported claim을 제거하고 evidence가 있는 부분만 답한다.

### Context extension model

새 컨텍스트는 prompt 직접 수정이 아니라 package 단위로 추가한다.

- `ContextProvider`: 검색/조회 가능한 source.
- `Capability/Tool`: MCP-shaped descriptor와 AI 전용 DTO.
- `SearchProfile`: query expansion, filters, source kinds, rerank, recency, top-k.
- `DomainAgentDefinition`: 해당 context를 언제 쓸지 정의.
- `EvidenceSchema`: citation/reference 형식.
- `EvalFixture`: routing, retrieval, verifier, no-hallucination 회귀 케이스.

## Implementation Phases

### Phase A - Runtime contract foundation

- `AgentDefinition`, `AgentRun`, `AgentInvocation`, `AgentTraceEvent`, `EvidencePacket`, `SearchProfile`, `VerifierResult`, `ModelProfile` DTO를 추가한다.
- 기존 `AiCapabilityDescriptor`와 연결되는 tool allowlist 검증 경계를 정의한다.
- DB migration은 실행 전 별도 상세 플랜에서 확정한다.

### Phase B - Fast path and manager graph

- 기존 chat stream 진입점 앞에 fast path router를 추가한다.
- manager graph path는 decomposition과 execution graph를 한 번에 생성한다.
- 기존 `agent.py` loop는 specialist invocation 내부 실행기로 축소한다.

### Phase C - Search and evidence

- `search.planner`와 `search.executor` 경계를 도입한다.
- 기존 RAG/domain tool result를 `EvidencePacket`으로 normalize한다.
- source kind, rerank, recency, embedding version, top-k policy를 trace에 남긴다.

### Phase D - Verifier and recovery

- `verifier.grounding`을 별도 invocation으로 추가한다.
- `VerifierResult`와 recovery policy table을 구현한다.
- 재검색/추가 도메인/사용자 질문/partial answer 전환을 traceable하게 만든다.

### Phase E - Approval and batch policy

- 기존 approval flow를 `AgentRun` checkpoint로 흡수한다.
- batch 자동 승인 정책은 코드 상수가 아니라 DB 정책으로 둔다.
- 정책 축은 workspace, domain, risk level, max cost, allowed actions, review required 여부를 포함한다.

### Phase F - Template writer and eval

- 사용자 정의 템플릿 기반 `writer.template` invocation을 추가한다.
- routing, evidence, verifier, recovery, model swap, context addition eval fixture를 만든다.

## Verification

- Fast path
  - single-domain read 요청이 manager LLM 호출 없이 처리된다.
  - meeting-scoped conversation이 meeting domain agent로 바로 간다.
- Graph path
  - ambiguous/cross-domain/report 요청이 manager graph를 만든다.
  - decomposition과 chosen graph가 한 번의 manager 호출에서 나온다.
- Evidence contract
  - PMS/Meeting/Docs/Planner/RAG 검색 결과가 동일한 `EvidencePacket` shape로 normalize된다.
  - verifier와 writer는 domain별 raw result를 직접 보지 않는다.
- Verifier and recovery
  - unsupported claim이 fail 처리된다.
  - 재검색 max count 이후 사용자 질문 또는 review queue로 전환된다.
- Tool and approval security
  - specialist allowlist 밖 tool call은 실행 전 차단된다.
  - hidden workspace app tool은 manager/specialist 모두 접근할 수 없다.
  - approval resume 시 tool surface가 넓어지지 않는다.
- Model swap
  - Qwen local profile과 OpenAI-compatible external profile에서 같은 agent contract가 유지된다.
  - tool parser, finish reason, prompt override 차이를 `ModelProfile`로 흡수한다.
- Context addition
  - 새 context provider가 provider + search profile + agent definition + eval fixture 추가만으로 연결된다.

## Decision Log

### 결정 완료

| 항목 | 결정 |
|---|---|
| 외부 A2A | v1 범위에서 제외 |
| v1 실행 모델 | in-process graph orchestrator |
| 기본 제어 방식 | free handoff가 아니라 manager-controlled graph |
| 단순 요청 처리 | deterministic fast path 우선 |
| decomposition | 모든 요청에 수행하지 않고 graph path에서 manager routing과 결합 |
| task agent | extract/summarize/compare/draft는 domain agent 내부 skill |
| 별도 invocation | verifier, write_proposal, approval_preview, template_writer |
| evidence | `EvidencePacket`을 verifier/writer/search/domain 공통 contract로 사용 |
| recovery | verifier가 아니라 manager policy가 결정 |
| 모델 교체성 | adapter + `ModelProfile` + per-model prompt override |
| batch 승인 | 장기적으로 DB/workspace admin policy |

### 차후 결정

| 항목 | 결정 시점 |
|---|---|
| `AgentRun` DB schema 세부 컬럼 | Phase A 상세 구현 플랜 |
| 기존 approval snapshot 이관/삭제 방식 | Phase E 상세 구현 플랜 |
| 병렬 specialist 실행 | v2 확장 설계 |
| worker-backed long-running agent | batch/ambient agent 착수 시 |
| workspace admin policy UI 범위 | batch/admin UI 착수 시 |

## Rollback Plan

이 문서는 설계 계획이므로 코드 rollback은 없다. 이후 구현 단계에서 문제가 생기면 다음 순서로 되돌린다.

1. chat entrypoint를 기존 single-loop agent path로 feature flag 전환한다.
2. 새 runtime trace table은 read-only로 보존하고 신규 write만 중단한다.
3. approval flow는 기존 approval endpoint 계약을 유지한 채 old snapshot path로 되돌린다.
4. 실패 원인을 eval fixture와 trace event로 정리한 뒤 단계별 재도입한다.
