# Evidence-First Agent Runtime

> 문서 성격: Doowon AI runtime 재설계를 위한 실행 설계 문서.  
> 참고 연구 문서: [`01-agentic-harness-engineering-report.md`](../docs/planning/01-agentic-harness-engineering-report.md)
> 목표: Qwen3.6-35B-A3B 기반 로컬 LLM 운영 한계를 줄이고, 새 컨텍스트 추가와 모델 교체가 쉬운 agent 운영 구조를 만든다.

## Context

현재 Doowon AI 플랫폼은 MCP-shaped capability registry, workspace-scoped tool gateway, RAG provider, approval flow, streaming envelope를 이미 갖고 있다. 다만 agent 실행 모델은 아직 단일 agent loop 중심이다. 이 구조는 단기 구현에는 빠르지만, 다음 요구가 커질수록 유지보수 비용이 높아진다.

- v1 canonical 모델은 `Qwen/Qwen3.6-35B-A3B`로 고정한다.
- 로컬 MLX 개발/PoC checkpoint는 `mlx-community/Qwen3.6-35B-A3B-4bit`를 기본값으로 사용한다.
- Qwen3.6-35B-A3B는 긴 context와 tool calling을 지원하지만, 큰 tool catalog와 긴 대화 이력에 취약하다.
- PMS, Meeting, Docs, Planner, RAG 같은 도메인 컨텍스트가 계속 늘어난다.
- 추후 LLM 모델이나 serving stack이 바뀌어도 agent contract와 tool/context boundary는 유지되어야 한다.
- 사용자 정의 템플릿, batch 작업, ambient/event-driven 작업까지 확장하려면 실행 trace와 approval policy가 agent 단위로 남아야 한다.

따라서 목표는 "모든 요청을 multi-agent로 비싸게 실행"하는 것이 아니라, **deterministic shortcut + graph orchestrator + evidence-first specialist runtime**을 만드는 것이다.

이 문서는 별도 검토에서 채택한 기술 항목을 반영한 정본 계획이다. 검토 로그 원문과 내부 메타데이터는 실행 기준으로 취급하지 않는다.

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

### 3. Structured outputs and constrained generation

Graph path의 manager LLM 응답은 자유 텍스트가 아니라 `ExecutionGraph` 구조로 고정한다. 출력은 serving stack이 지원하는 경우 JSON schema/function schema/constrained decoding으로 먼저 제한하고, 이후 Pydantic schema와 runtime business validator로 다시 검증한다.

```text
LLM structured generation
  -> constrained decoding / JSON schema / function schema
  -> Pydantic validation
  -> runtime business validator
  -> fallback or retry
```

적용 원칙:

- `manager.orchestrator`, `verifier.grounding`, `writer.template`의 구조화 산출물은 constrained generation을 우선 사용한다.
- `search.planner`는 deterministic builder를 우선하고, LLM query expansion이 필요한 경우에만 constrained output을 사용한다.
- `approval.proposal_preview`의 설명은 LLM이 만들 수 있지만, 실제 실행 대상은 deterministic canonical object여야 한다.
- Pydantic validation은 mandatory지만 첫 번째 방어선으로 보지 않는다.

```python
class InvocationSpec(BaseModel):
    agent_id: AgentId
    inputs_ref: str | None = None
    must_run_after: list[str] = []
    purpose: str


class ExecutionGraph(BaseModel):
    intent: IntentKind
    domains: list[DomainKind]
    risk: RiskLevel
    output_kind: OutputKind
    invocations: list[InvocationSpec]
    requires_verifier: bool
    requires_approval_preview: bool
```

검증 규칙은 runtime에서 강제한다.

- `agent_id`는 workspace entitlement, `allowed_app_ids`, `AgentDefinitionResolver` 결과 안에 있어야 한다.
- write-touching tool이 graph 안에 있으면 manager 출력과 무관하게 risk floor는 `high`다.
- manager output validation이 실패하면 `AIDOO_AI_RUNTIME_GRAPH_ENABLED`가 켜져 있어도 기존 single-loop path로 fallback한다.
- malformed output은 serving stack, `ModelProfile`, prompt revision, invocation kind별로 trace에 남긴다.

### 4. Evidence-first

최종 답변과 보고서는 검색 결과 원문 전체가 아니라 `EvidencePacket`을 통해 만들어진다. `EvidencePacket`은 domain agent, verifier, template writer가 공유하는 정본 DTO다.

```ts
type EvidencePacket = {
  query_plan: {
    keywords: string[]
    filters: Record<string, unknown>
    source_kinds: string[]
    sources_used: string[]
    candidate_top_k: number
    rerank_top_k: number
    final_evidence_token_budget: number
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
    provenance?: string
    trust_level?: "trusted" | "untrusted" | "mixed"
  }>
  coverage: {
    intents_covered: string[]
    intents_missed: string[]
  }
}
```

Verifier는 claim과 evidence를 이 DTO 기준으로 매칭한다. 도메인별 tool result shape이 달라도 manager 이후 단계는 동일한 evidence contract를 본다. Cross-workspace 필터링은 packet build 시점이 아니라 query/tool execution 시점에 수행해야 한다.

Claim-level grounding은 모든 응답에 강제하지 않는다. `grounded_report`, `high_risk_action`, cross-domain synthesis, 사용자 정의 template output에서는 선택적으로 `ClaimCheck`를 남길 수 있어야 한다.

```ts
type ClaimCheck = {
  claim_id: string
  claim_text: string
  required_evidence_type: "direct" | "inferential" | "none"
  supporting_refs: ResourceRef[]
  status: "supported" | "partially_supported" | "unsupported" | "contradicted"
  confidence: number
}
```

### 5. Task skills are inline by default

`extract`, `summarize`, `compare`, `draft` 같은 일반 task는 별도 agent invocation으로 분리하지 않는다. 로컬 LLM 비용과 latency를 줄이기 위해 domain agent 내부 skill로 처리한다.

별도 invocation으로 분리하는 예외는 다음이다.

- `verifier`: 산출물 검증과 grounding 판단 책임을 분리해야 한다.
- `write_proposal`: write action 전 변경 의도를 별도 구조로 고정해야 한다.
- `approval.proposal_preview`: 사용자 승인 경계와 연결된다.
- `writer.template`: 사용자 정의 템플릿과 최종 산출물 품질을 독립적으로 평가해야 한다.

### 6. Risk-based approval

승인은 prompt 지시가 아니라 runtime policy로 강제한다.

- read/search/extract/draft는 기본 자동 실행.
- write, 외부 전송, 권한 변경, 고비용 batch, 낮은 verifier confidence는 승인 또는 review queue 필요.
- batch 작업은 step마다 묻지 않고 workspace/domain/risk policy에 따라 자동 실행하거나 review queue로 보낸다.
- 사용자가 승인하는 canonical 대상은 LLM 설명문이 아니라 deterministic `WriteProposal`이다.
- `ApprovalPreview`는 사람이 이해하기 쉬운 설명이며 실제 execution source가 아니다.

### 7. ModelProfile for model swap

모델 교체성은 adapter만으로 충분하지 않다. tool call 형식, reasoning trace, finish reason, malformed tool call 회복 방식, prompt template이 모델마다 다르다.

v1의 default `ModelProfile`은 canonical model `Qwen/Qwen3.6-35B-A3B`다. 로컬 MLX serving model id는 `mlx-community/Qwen3.6-35B-A3B-4bit`로 둔다. 다른 모델은 migration 또는 fallback 후보가 아니라 후속 검증 대상이다.

`ModelProfile`은 다음을 포함한다.

- tool-call parser/format.
- reasoning field visibility와 streaming behavior.
- finish_reason mapping.
- malformed tool call retry policy.
- per-model prompt fragment override.
- reasoning mode support와 disable mechanism.
- thinking mode 기본값과 budget.
- context window, context profile, reasoning escalation policy.
- prefix-cache stable prompt segment와 dynamic slot 구분.
- structured decoding availability.
- `prompt_revision`.

```ts
type ReasoningModeSupport =
  | "non_thinking_only"
  | "thinking_only"
  | "hybrid_default_thinking"
  | "hybrid_default_non_thinking"
```

`AgentDefinition`은 모델 독립 기본 prompt를 갖고, `ModelProfile`이 Qwen/GPT/Claude 계열 override를 제공한다. `ModelProfile`은 `AgentRun` 생성 시 고정한다. 실행 중 모델 프로필이 바뀌면 기존 invocation을 조용히 이어가지 않고, 거부하거나 새 profile로 새 invocation을 시작한다. OpenAI-compatible API는 transport compatibility로만 취급하고, reasoning field, tool-call parsing, finish reason, structured output guarantee는 `ModelProfile`이 관리한다.

### 8. Runtime profiles over always-on reasoning

로컬 Qwen3.6-35B-A3B/DGX Spark 운영에서는 "긴 context와 thinking을 쓸 수 있다"와 "항상 써야 한다"를 분리한다. Doowon runtime은 요청마다 runtime profile을 고정하고, profile별 budget을 trace에 남긴다.

- `interactive_read`
  - 기본 profile.
  - non-thinking이 기본값이다.
  - 단순 read/search/summary 요청은 graph path보다 deterministic fast path를 우선한다.
  - context limit은 32K를 시작점으로 두고, 실측 후 64K까지 확장한다.
- `grounded_report`
  - EvidencePacket 기반 보고서/비교/종합 요청.
  - retrieval-first로 동작하고, 필요한 경우 verifier와 template writer를 실행한다.
  - thinking은 다문서 충돌, 모호한 요구, 복수 도메인 synthesis일 때만 승격한다.
- `long_doc`
  - 장문 문서 분석과 대량 batch 전용 profile.
  - interactive queue와 분리하고, 비동기 실행 또는 review queue를 기본으로 한다.
  - 64K 이상 context는 별도 benchmark gate를 통과한 뒤 연다.
- `high_risk_action`
  - write/external/permission/costly batch action 전용 profile.
  - verifier, approval preview, human approval 또는 review queue를 강제한다.

Qwen3.6-35B-A3B profile은 `enable_thinking=false`에 해당하는 non-thinking 경로를 기본값으로 보고, thinking은 `ModelProfile.reasoning_escalation_policy`가 허용할 때만 켠다. GPT/Claude 등 외부 profile도 같은 contract를 유지하되, provider별 reasoning control은 adapter와 prompt override가 흡수한다.

Thinking escalation은 다음 조건에서만 허용한다.

- 다문서 evidence 충돌.
- 복수 도메인 synthesis.
- high-risk action planning.
- verifier가 unsupported 또는 contradicted evidence를 감지한 경우.
- 사용자가 명시적으로 reasoning-heavy 분석을 요청한 경우.

### 9. Token, retrieval, and memory budgets

검색 품질과 latency는 context window보다 budget 관리에 더 크게 좌우된다.

- 하이브리드 검색은 초기 후보 20~40개를 기본 범위로 둔다.
- reranker는 최종 4~8개 evidence item만 domain agent/verifier/writer에 넘긴다.
- 일반 RAG 답변의 final evidence token budget은 2K~4K를 시작점으로 둔다.
- `SearchProfile`은 candidate top-k, rerank top-k, final evidence token budget, rerank strategy, recency weighting, embedding model version을 모두 포함한다.
- vector store, hybrid retrieval, reranker는 Phase C benchmark로 결정한다. 초기 후보는 기존 Postgres/pgvector 경로와 Qdrant 계열 독립 검색 서비스를 비교할 수 있게 둔다.
- reranker는 영어 public benchmark가 아니라 회의록, PMS, Docs, Planner, 한국어 업무 문서 eval set으로 선택한다.
- prompt는 prefix-cache 친화적으로 구성한다. system policy, domain rule, output schema는 stable segment로 고정하고, 사용자 요청과 evidence만 dynamic slot으로 넣는다.

Memory는 agent 성능 기능이 아니라 governance boundary로 다룬다.

- short-term memory는 최근 8~16턴, 현재 tool result, 현재 EvidencePacket reference로 제한한다.
- long-term memory는 사용자 선호, 진행 중 업무 상태, 승인 이력처럼 typed/audited state만 저장한다.
- raw thinking, provider reasoning trace, tool secret, 내부 prompt fragment는 영구 저장하지 않는다.
- 저장이 필요한 경우 distilled plan/state, verifier summary, evidence reference만 남긴다.

### 10. Serving profile and deployment assumptions

Agent runtime은 serving stack에 종속되지 않지만, 로컬 Qwen3.6-35B-A3B 운영 현실은 설계 가정에 반영한다.

- PoC와 Phase A~C는 단일 local OpenAI-compatible endpoint를 기준으로 한다.
- v1 canonical 모델은 `Qwen/Qwen3.6-35B-A3B`로 고정한다.
- MLX 개발/PoC 기본 checkpoint는 `mlx-community/Qwen3.6-35B-A3B-4bit`로 고정한다.
- DGX Spark/Qwen3.6-35B-A3B 경로는 SGLang을 PoC default serving candidate로 두고, vLLM을 compatibility/bakeoff serving candidate로 검증한다.
- SGLang/vLLM 선택은 serving engine bakeoff로만 다룬다. 모델 후보 비교는 v1 범위에서 제외한다.
- Serving engine 선택은 runtime profile별로 결정한다. `interactive_read`는 TTFT/TPOT/cache hit, `grounded_report`는 structured output과 evidence token 처리, `high_risk_action`은 tool-call argument 안정성, `long_doc`은 context degradation과 memory pressure를 본다.
- DGX Spark는 local validation, pilot serving, batch/offline worker 후보로 평가한다. 별도 benchmark gate 없이 high-concurrency production 기준으로 가정하지 않는다.
- K8s, Ray, Spark, LoRA 학습 파이프라인은 v1 runtime contract의 선행 조건이 아니다.
- 두 번째 DGX Spark를 도입해도 초기 기본 전략은 tensor parallel보다 RAG/embedding, prefill/decode, domain worker 같은 service separation이다.
- NIM, Triton, TensorRT-LLM, NVIDIA Dynamo, Qwen-Agent, LangGraph는 평가 후보로만 둔다. v1 문서는 특정 framework dependency를 runtime contract로 고정하지 않는다.
- 장기 model adaptation은 공통 base model + domain LoRA/PEFT + retrieval source + policy template 조합을 후보로 둔다. 자주 바뀌는 사실은 fine-tuning이 아니라 RAG로 처리한다.

### 11. Observable and reversible rollout

Graph runtime은 feature flag 뒤에서 시작한다.

- `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false`가 기본값이다.
- single-loop path는 Phase B 이후에도 eval/perf gate 통과 전까지 canonical fallback으로 유지한다.
- `AgentRun`, `AgentInvocation`, `AgentTraceEvent`는 read-only inspection endpoint를 제공한다. UI는 후속 UI 단계에서 붙이더라도 운영/검증은 SQL 없이 가능해야 한다.
- `AgentTraceEvent` 이름과 payload는 OTel-exportable하게 설계하고, GenAI semantic convention version을 고정한다.
- 내부 trace table은 source of truth로 유지한다. Langfuse, Phoenix, MLflow, 기존 APM은 export 대상 후보일 뿐 lock-in하지 않는다.
- 최소 metric set은 service, model, RAG, agent 계층으로 나눈다.
  - service: p50/p95/p99 TTFT, TPOT, end-to-end latency, request/sec.
  - model: prompt tokens, completion tokens, thinking tokens, cache hit rate, malformed tool-call rate.
  - RAG: retrieval recall, rerank hit rate, groundedness, citation coverage, ACL-denied hit rate.
  - agent: plan depth, step count, tool success rate, human override rate, loop-abort rate, recovery count.

## Runtime Design

### Core models

`domains/ai/runtime/` 아래에 다음 runtime 정본을 둔다.

- `AgentDefinition`
  - `agent_id`, `role`, `purpose`, `non_goals`, `tool_allowlist`, `context_sources`, `skills`, `budget`, `failure_policy`, `model_prompt_overrides`, `eval_cases`.
- `AgentDefinitionResolver`
  - workspace entitlement, `allowed_app_ids`, discoverability predicate를 반영해 manager가 볼 수 있는 agent와 tool allowlist를 계산한다.
- `AgentRun`
  - 사용자 요청 하나의 전체 실행 단위.
  - chat, batch, ambient entrypoint를 같은 실행 모델로 수용한다.
  - recovery loop counter와 locked `ModelProfile`을 가진다.
- `AgentInvocation`
  - manager/domain/search/verifier/writer 각각의 실행 단위.
  - tool allowlist, input/output, usage, error를 별도로 기록한다.
  - resume/recovery 반복은 같은 `AgentRun` 아래 새 `AgentInvocation`으로 남긴다.
- `AgentTraceEvent`
  - routing, search plan, tool call, evidence packet, verifier result, approval decision, retry를 순서대로 기록한다.
  - ordering은 `(run_seq, invocation_id, invocation_seq)`로 고정한다.
- `SearchProfile`
  - source kind, query expansion, filters, candidate top-k, rerank top-k, final evidence token budget, rerank strategy, recency weighting, embedding model version.
- `VerifierResult`
  - `status`, `missing_evidence`, `unsupported_claims`, `contradictory_evidence`, `policy_risks`, `evidence_coverage`, `suggested_recovery`, `confidence`.
- `ModelProfile`
  - model-family-specific tool, reasoning mode support, prompt, retry behavior, runtime profile limits, structured decoding availability, prompt-cache policy.
- `ToolSecurityPolicy`
  - 독립 보안 시스템이 아니라 capability metadata/policy extension으로 둔다.
  - auth mode, OAuth scope, token passthrough 제한, input sanitizer, output trust level, PII redaction, network policy를 표현한다.
- `WriteProposal`
  - 사용자가 승인하는 deterministic diff/action object.
  - `ApprovalPreview`는 이 object를 설명할 수 있지만 실행 근거가 될 수 없다.
- `ClaimCheck`
  - `grounded_report`, `high_risk_action`, template output에서 선택적으로 남기는 claim-level grounding result.

### AgentInvocation state machine

Phase A는 `AgentInvocation` 상태기계를 먼저 고정한다.

```text
pending
  -> running
  -> awaiting_approval
  -> resumed
  -> completed
  -> failed
  -> cancelled
  -> abandoned
```

불변식:

- 한 `AgentRun`에는 여러 invocation이 있을 수 있다.
- 한 conversation에는 live `AgentRun`이 하나만 있어야 한다.
- 한 `AgentRun`에는 pending approval이 하나만 있어야 한다.
- approval resume은 새 `AgentRun`을 만들지 않고 같은 `AgentRun` 아래 새 `AgentInvocation`으로 이어진다.
- cutover 동안 `AgentRun.id`와 기존 `AgentRunSnapshot.id` 연속성은 Phase E migration plan에서 명시적으로 다룬다.

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
  - 기본은 deterministic `SearchPlanBuilder`이며, LLM query expansion은 ambiguous/cross-domain/long natural language 요청에만 사용한다.
- `search.executor`
  - 실제 검색 실행기. 새 RAG 구현이 아니라 기존 `domains/rag/application.py`와 domain tools를 호출하는 thin adapter다.
- `verifier.grounding`
  - evidence coverage, unsupported claim, missing requirement, policy risk를 판단한다.
- `writer.template`
  - EvidencePacket과 사용자 정의 템플릿으로 최종 산출물을 작성한다.
- `approval.proposal_preview`
  - write/batch 실행 전 사용자 검토용 preview를 만든다. 기존 `approvals.py::ApprovalPreview`와 중복 모델을 만들지 않고 연결한다.

Domain agent는 새 domain service layer가 아니다. `{prompt fragment, tool allowlist, EvidencePacket shape, skills}`를 가진 runtime descriptor이며, 실제 실행은 기존 application service와 MCP capability를 통과한다.

### Artifact boundary

기존 fast path와 single-loop fallback은 현재 artifact tag flow를 유지한다. 즉 assistant output의 `<artifact type="document|html|code|svg">...</artifact>`는 기존 `ArtifactStreamParser`가 처리한다.

Graph path에서는 `writer.template`이 artifact emission의 소유자다. Domain/verifier/search invocation은 raw artifact tag를 직접 emit하지 않고, EvidencePacket, draft body, template output reference를 반환한다. Graph path에서 artifact가 필요한 경우 `writer.template`이 최종 artifact markup을 생성한다.

`writer.template`은 artifact 전체를 LLM 자유 생성에 맡기지 않는다.

```text
TemplateSpec
  -> deterministic section skeleton
  -> evidence-bound LLM section generation
  -> deterministic citation insertion
  -> deterministic artifact wrapper emission
  -> verifier
```

Artifact wrapper, section ordering, citation insertion, required field validation은 deterministic renderer가 담당한다.

### Execution flow

1. Chat request가 들어오면 `AIDOO_AI_RUNTIME_GRAPH_ENABLED`와 fast path 조건을 먼저 평가한다.
2. Entrypoint가 `interactive_read`, `grounded_report`, `long_doc`, `high_risk_action` 중 runtime profile을 고정한다.
3. Feature flag가 꺼져 있으면 기존 single-loop path로 간다.
4. Fast path면 해당 domain agent invocation을 바로 생성한다.
5. Graph path면 manager가 `ExecutionGraph`를 만든다.
6. Manager output validator가 schema, workspace app scope, agent allowlist, risk floor를 검사한다.
7. 검증 실패 시 기존 single-loop path로 fallback한다.
8. Domain agent는 필요한 경우 `SearchPlan`을 만들거나 `search.planner`를 호출한다.
9. `search.executor`가 기존 MCP capability/RAG/domain service를 사용해 evidence를 수집한다.
10. Domain agent는 inline skill로 extract/summarize/compare/draft를 수행한다.
11. 고위험 또는 cross-domain 산출물은 verifier가 `VerifierResult`를 만든다.
12. Verifier fail이면 manager가 recovery policy로 재검색, 추가 domain invocation, 사용자 질문, partial answer 중 하나를 선택한다.
13. Template 요청이면 `writer.template`이 최종 산출물을 만든다.
14. Write/external/batch action은 risk-based approval gate 또는 review queue를 통과한다.

### Recovery policy

기본 policy는 deterministic하게 둔다.

- 재검색 최대 2회.
- 추가 domain invocation 최대 1회.
- verifier loop counter는 `AgentRun`에 둔다.
- recovery path latency budget을 별도로 측정한다.
- recovery가 반복되어도 evidence token budget을 무한 확장하지 않는다.
- 그래도 evidence 부족이면 사용자 질문으로 전환.
- batch에서는 사용자 질문 대신 review queue로 전환.
- partial answer가 허용되면 unsupported claim을 제거하고 evidence가 있는 부분만 답한다.
- recovery iteration은 각각 별도 `AgentInvocation`으로 저장해 resume 시 같은 작업을 처음부터 반복하지 않게 한다.

### Context extension model

새 컨텍스트는 prompt 직접 수정이 아니라 package 단위로 추가한다.

- `ContextProvider`: 검색/조회 가능한 source.
- `Capability/Tool`: MCP-shaped descriptor와 AI 전용 DTO.
- `SearchProfile`: query expansion, filters, source kinds, candidate top-k, rerank top-k, final evidence token budget, rerank, recency, embedding model version.
- `DomainAgentDefinition`: 해당 context를 언제 쓸지 정의.
- `EvidenceSchema`: citation/reference 형식.
- `EvalFixture`: routing, retrieval, verifier, no-hallucination 회귀 케이스.

Internal domain services는 wholesale MCP server로 감싸지 않는다. 내부 도구는 typed application service + workspace-scoped tool gateway를 유지하고, MCP는 주로 external capability boundary로 사용한다. Production remote MCP는 identity verification, OAuth/resource metadata, gateway audit을 통과해야 한다.

## Future Extension Boundaries

v1에서 구현하지 않는 항목도 나중에 core runtime을 갈아엎지 않도록 boundary를 먼저 둔다. 이 섹션의 항목은 구현 약속이 아니라 extension contract다.

### LLM Gateway boundary

Agent runtime은 직접 provider를 호출하더라도, 호출 경계는 다음 구조로 추상화한다.

```text
Doowon Agent Runtime
  -> ModelProfile / RuntimeProfile
  -> LLM Gateway boundary
       -> SGLang
       -> vLLM
       -> External Provider
```

- Agent runtime은 risk, approval, evidence, trace, runtime policy를 소유한다.
- `ModelProfile`은 parser, reasoning mode, tool-call format, retry behavior, prompt override를 소유한다.
- Gateway 후보는 endpoint routing, fallback, rate limit, budget, health check를 소유한다.
- Gateway가 `ModelProfile`을 대체하지 않는다.

### Durable workflow boundary

Interactive agent execution은 v1에서 in-process graph runtime으로 유지한다. Long-running document analysis, batch jobs, ambient workflows, approval wait은 pilot 이후 durable workflow backend로 위임할 수 있게 둔다.

필요한 handoff 필드는 Phase A/E 상세 구현에서 검토한다.

- `AgentRun.idempotency_key`
- `AgentInvocation.retry_of`
- `ToolCall.idempotency_key`
- `checkpoint_ref`
- `resume_from_invocation_id`
- `approval_expires_at`
- `cancellation_requested_at`
- `abandoned_reason`

Temporal, Prefect, Airflow, custom worker는 후보일 뿐 v1 dependency가 아니다.

### Retrieval backend boundary

`search.executor`는 기존 RAG/domain service thin adapter로 시작하되, vector store와 reranker 교체를 막지 않는다.

- pgvector는 Postgres metadata, ACL, transaction, JOIN이 중요할 때 초기 후보가 된다.
- Qdrant 또는 독립 vector service는 hybrid retrieval 품질과 검색 독립 확장이 중요할 때 검증한다.
- reranker는 자체 Korean 업무 eval set으로 선택한다.
- retrieval backend 선택은 `SearchProfile`과 `EvidencePacket` contract를 바꾸지 않아야 한다.

### Observability export boundary

Internal trace table은 source of truth다. 동시에 Phase A부터 OTel span/event export가 가능해야 한다.

- GenAI semantic convention version을 pinning한다.
- trace로 routing, search, evidence, verifier, approval, recovery를 재현할 수 있어야 한다.
- raw reasoning delta는 export하거나 저장하지 않는다.
- Langfuse, Phoenix, MLflow, existing APM은 후속 UI/분석 후보로 둔다.

### External agent interop boundary

외부 A2A는 v1 범위에서 제외한다. 다만 내부 contract는 장기적으로 외부 agent protocol에 mapping 가능해야 한다.

- `AgentDefinition`
- `AgentInvocation`
- `EvidencePacket`
- `WriteProposal` / `ApprovalPreview`
- `VerifierResult`
- `AgentTraceEvent`

A2A를 도입하더라도 내부 tool/context/approval contract를 대체하지 않는다.

## Implementation Phases

### Phase 0 - Baseline and gates

구현 전 현 상태를 먼저 측정한다.

- current single-loop p50/p95 latency.
- p50/p95/p99 TTFT, TPOT, end-to-end latency.
- prompt/completion/thinking token usage.
- prefix-cache hit rate 또는 provider cache hit proxy metric.
- malformed tool-call rate by model/provider.
- structured decoding success rate by invocation/provider/serving stack.
- OpenAI-compatible response shape diff.
- Qwen thinking/non-thinking control success rate.
- tool error/retry/duplicate-loop rate.
- RAG citation coverage, groundedness, ACL-denied hit rate.
- RAG vector/reranker baseline.
- fast path false-positive/false-negative rate.
- malicious retrieved content containment baseline.
- verifier false pass/false fail baseline.
- agent step count, tool success rate, human override rate, loop-abort rate.
- eval pass rate for routing, grounding, no-tool restraint.
- single-domain vs cross-domain request split.
- graph rollout kill criteria: graph path p95는 baseline x2 이내, recovery path는 baseline x3 이내를 시작 기준으로 둔다.

### Phase A - Runtime contract foundation

- `AgentDefinition`, `AgentDefinitionResolver`, `AgentRun`, `AgentInvocation`, `AgentTraceEvent`, `ExecutionGraph`, `EvidencePacket`, `SearchProfile`, `VerifierResult`, `ModelProfile` DTO를 추가한다.
- runtime profile enum과 token/context/memory budget DTO를 추가한다.
- `ModelProfile.reasoning_mode_support`와 structured decoding availability matrix를 추가한다.
- `ToolSecurityPolicy`, `WriteProposal`, `ClaimCheck`는 개념 contract로 추가하되 세부 컬럼은 상세 구현에서 확정한다.
- `AgentInvocation` state machine과 approval/resume 불변식을 문서와 테스트로 고정한다.
- `AgentTraceEvent` ordering과 OTel export naming map을 정의하고 GenAI semantic convention version을 고정한다.
- `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false` feature flag를 추가한다.
- read-only inspection endpoint를 추가한다.
- eval fixture format과 starter dataset을 정의한다. Phase A는 seed cases를 고정하고, rollout gate의 목표 케이스 수는 Phase F까지 확장한다.
- DB migration은 실행 전 상세 플랜에서 확정하되, one live run per conversation, one pending approval per run, retention/scrub 정책은 Phase A 산출물로 고정한다.
- raw thinking/reasoning trace는 영구 저장하지 않고, distilled state와 evidence reference만 저장하는 retention rule을 고정한다.

### Phase B - Fast path and manager graph

- 기존 chat stream 진입점 앞에 fast path router를 추가한다.
- runtime profile selector를 추가한다. 기본값은 `interactive_read`다.
- manager graph path는 constrained generation이 가능한 경우 이를 사용해 `ExecutionGraph`를 생성한다.
- `ManagerOutputValidator`를 구현한다.
- malformed manager output, out-of-scope agent, invalid risk/output enum은 기존 single-loop path로 fallback하고 fallback reason taxonomy를 trace에 남긴다.
- risk floor를 적용한다. write-touching graph는 항상 high risk 이상이다.
- `ModelProfile`을 `AgentRun` 생성 시 고정한다.
- non-thinking default와 thinking escalation policy를 `ModelProfile`에서 강제한다.
- OpenAI-compatible transport와 provider behavior contract를 분리한다.
- SGLang/vLLM manager output success rate를 같은 fixture로 비교한다.
- cancellation은 LLM stream과 graph node 사이마다 전파한다.
- 기존 `agent.py` loop는 specialist invocation 내부 실행기 또는 fallback path로 축소한다.

### Phase C - Search and evidence

- `search.planner`와 `search.executor` 경계를 도입한다.
- `SearchPlanBuilder`는 deterministic-first로 구현하고, LLM query expansion은 optional path로 제한한다.
- `search.executor`는 기존 `domains/rag/application.py`와 domain tools를 호출하는 thin adapter로 구현한다.
- 기존 RAG/domain tool result를 `EvidencePacket`으로 normalize한다.
- candidate top-k, rerank top-k, final evidence token budget, source kind, rerank, recency, embedding version, top-k policy를 trace에 남긴다.
- pgvector/Qdrant 또는 기존 store 후보와 reranker 후보를 같은 Korean 업무 eval set으로 비교한다.
- tool output trust level, malicious retrieved content handling, source provenance를 EvidencePacket normalization에 반영한다.
- EvidencePacket response shaper는 shared helper로 둔다.
- workspace isolation은 query/tool execution 시점에서 검증한다.
- trace event는 raw reasoning delta를 저장하지 않고 invocation 종료 시 summary/buffer flush 방식으로 기록한다.

### Phase D - Verifier and recovery

- `verifier.grounding`을 별도 invocation으로 추가한다.
- `VerifierResult`와 recovery policy table을 구현한다.
- claim-level `ClaimCheck`는 `grounded_report`, `high_risk_action`, template output에서 먼저 검토한다.
- verifier false pass/false fail eval을 추가한다.
- contradicted evidence와 verifier unavailable policy를 명시한다.
- 재검색/추가 도메인/사용자 질문/partial answer 전환을 traceable하게 만든다.
- recovery latency gate와 recovery token budget cap을 둔다.
- verifier unavailable이면 answer를 unverified로 표시하고, 고위험 path에서는 사용자 검토로 보낸다.

### Phase E - Approval and batch policy

- 기존 approval flow를 `AgentRun` checkpoint로 흡수한다.
- canonical `WriteProposal`과 LLM-assisted `ApprovalPreview`를 분리한다.
- ApprovalPreview는 설명일 뿐 actual execution source가 아님을 명시한다.
- approval halt/resume은 same `AgentRun`, new `AgentInvocation` 원칙을 따른다.
- approval resume idempotency와 tool surface widening 방지 test를 추가한다.
- 기존 `AgentRunSnapshot` compatibility/cutover 전략과 idempotent migration script를 상세 플랜에서 작성한다.
- partial unique index와 live approval constraint는 concurrent test로 검증한다.
- batch 자동 승인 정책은 코드 상수가 아니라 DB 정책으로 둔다.
- 정책 축은 workspace, domain, risk level, max cost, allowed actions, review required 여부를 포함한다.
- approval wait, batch, review queue는 durable workflow boundary를 유지하되 구체 backend는 확정하지 않는다.

### Phase F - Template writer and eval

- 사용자 정의 템플릿 기반 `writer.template` invocation을 추가한다.
- Graph path artifact emission은 `writer.template`이 소유한다.
- deterministic renderer + LLM section filler 방식을 적용한다.
- artifact wrapper, citation insertion, required section validation은 deterministic 처리한다.
- template output schema validation과 hallucination eval을 추가한다.
- routing, evidence, verifier, recovery, model swap, context addition eval fixture를 만든다.
- prefix-cache hit rate와 `ModelProfile.prompt_revision` invalidation을 검증한다.
- interactive/grounded_report/long_doc/high_risk_action profile별 latency, token, verifier pass rate를 비교한다.
- profile별 SGLang/vLLM serving engine bakeoff 결과를 rollout decision에 반영한다.

## Verification

- Baseline and rollout gates
  - single-loop baseline latency, malformed tool-call rate, duplicate-loop rate, eval pass rate를 기록한다.
  - TTFT, TPOT, thinking tokens, cache hit rate, groundedness, citation coverage, loop-abort rate를 기록한다.
  - routing confusion matrix, fast path false-positive/false-negative rate, cost per successful run을 기록한다.
  - graph rollout은 feature flag와 perf gate를 통과한 뒤 활성화한다.
- Structured output
  - manager/verifier/writer output이 constrained generation으로 schema를 만족한다.
  - Pydantic validation failure rate가 baseline 대비 감소한다.
  - malformed JSON/tool-call 발생 시 fallback 또는 retry가 정상 동작한다.
  - serving stack별 structured output success rate를 비교한다.
- Fast path
  - single-domain read 요청이 manager LLM 호출 없이 처리된다.
  - meeting-scoped conversation이 meeting domain agent로 바로 간다.
  - ambiguous request는 graph path로 넘어간다.
- Graph path
  - ambiguous/cross-domain/report 요청이 `ExecutionGraph`를 만든다.
  - malformed manager output은 single-loop fallback으로 간다.
  - out-of-scope agent와 invalid enum은 validator가 차단한다.
  - write-touching graph는 high risk로 승격된다.
- Evidence contract
  - PMS/Meeting/Docs/Planner/RAG 검색 결과가 동일한 `EvidencePacket` shape로 normalize된다.
  - verifier와 writer는 domain별 raw result를 직접 보지 않는다.
  - workspace isolation은 query/tool execution 시점에서 보장된다.
  - retrieval candidate/rerank/final evidence token budget이 `SearchProfile`과 trace에 남는다.
  - source provenance, access scope, tool output trust level이 evidence normalization에 반영된다.
- RAG and search
  - deterministic `SearchPlanBuilder`가 대부분의 single-domain 요청을 LLM 없이 처리한다.
  - LLM query expansion invocation rate가 trace에 남는다.
  - vector store와 reranker 후보는 같은 Korean 업무 eval set으로 비교한다.
  - malicious retrieved content가 writer/verifier를 오염시키지 않는지 테스트한다.
- Verifier and recovery
  - unsupported claim이 fail 처리된다.
  - contradicted evidence가 감지된다.
  - partial support claim은 caveat로 낮춰진다.
  - verifier false pass와 false fail을 별도 측정한다.
  - 재검색 max count 이후 사용자 질문 또는 review queue로 전환된다.
  - recovery latency budget과 token budget cap을 지킨다.
  - recovery iteration은 distinct `AgentInvocation`으로 저장된다.
- Tool and approval security
  - specialist allowlist 밖 tool call은 실행 전 차단된다.
  - hidden workspace app tool은 manager/specialist 모두 접근할 수 없다.
  - token passthrough 제한, SSRF/private network 접근 방지, secret redaction 정책을 검증한다.
  - tool output은 trust level에 따라 처리된다.
  - external write action은 approval gate를 우회할 수 없다.
  - cross-workspace evidence leakage test를 통과한다.
  - 사용자가 승인하는 canonical 대상은 `WriteProposal`이다.
  - LLM `ApprovalPreview`는 execution source가 아니다.
  - approval resume 시 tool surface가 넓어지지 않는다.
  - 같은 approval을 재개해도 idempotency가 깨지지 않는다.
  - one live `AgentRun` per conversation과 one pending approval per run 불변식을 검증한다.
- Model swap
  - Qwen local profile과 OpenAI-compatible external profile에서 같은 agent contract가 유지된다.
  - tool parser, finish reason, prompt override 차이를 `ModelProfile`로 흡수한다.
  - `ModelProfile`은 run 시작 시 lock된다.
  - non-thinking default와 thinking escalation policy가 provider별로 같은 runtime contract를 유지한다.
  - OpenAI-compatible response shape 차이를 기록한다.
  - Qwen reasoning/non-thinking control이 `ModelProfile.reasoning_mode_support`대로 동작한다.
- Runtime profile and memory
  - single-domain read 요청은 `interactive_read`에서 manager 없이 실행된다.
  - 장문 요청은 `long_doc` profile로 분리되고 interactive queue를 막지 않는다.
  - short-term memory는 최근 대화와 현재 evidence/tool result로 제한된다.
  - long-term memory에는 typed/audited state만 저장되고 raw thinking은 저장되지 않는다.
- Artifact and template
  - fast path는 기존 artifact parser behavior를 유지한다.
  - graph path는 `writer.template`만 artifact markup을 emit한다.
  - artifact wrapper와 citation insertion은 deterministic renderer가 만든다.
  - template required section 누락이 validation에서 감지된다.
  - hallucinated section 또는 unsupported claim이 verifier에서 차단된다.
- Observability
  - 모든 `AgentInvocation`은 OTel-exportable trace를 남긴다.
  - internal trace table과 OTel span/event가 대응된다.
  - GenAI semantic convention version이 명시된다.
  - raw reasoning delta가 저장되지 않는다.
  - trace로 routing, search, evidence, verifier, approval, recovery를 재현할 수 있다.
- Future extension boundaries
  - approval wait 중 process restart가 발생해도 durable workflow boundary로 resume 가능하도록 handoff 필드를 설계한다.
  - batch retry 시 duplicate write를 막을 idempotency key 경계를 둔다.
  - LLM gateway 후보를 붙여도 `ModelProfile`과 runtime policy contract가 바뀌지 않는다.
  - A2A를 붙여도 내부 tool/context/approval contract를 대체하지 않는다.
- Context addition
  - 새 context provider가 provider + search profile + agent definition + eval fixture 추가만으로 연결된다.

## Alternatives Considered

| 대안 | 결론 | 이유 |
|---|---|---|
| Fast path only | 기각, 단 Phase B의 일부로 채택 | latency 개선에는 좋지만 grounding, verifier, template writer, context package 확장성을 해결하지 못한다. |
| Verifier only | 기각, Phase D로 흡수 | 환각 억제에는 유용하지만 큰 tool catalog와 manager/specialist 경계 문제를 해결하지 못한다. |
| 기존 `AgentRunSnapshot` 확장 | 차후 migration 상세에서 재검토 | additive migration은 안전하지만 approval 전용 모델에 runtime 전체 의미를 얹으면 장기적으로 상태 의미가 흐려진다. Phase E에서 compatibility shim과 cutover 전략을 결정한다. |
| Qwen model bakeoff | 기각 | v1 기본 모델은 `Qwen/Qwen3.6-35B-A3B`로 고정한다. 다른 모델 비교는 현재 실행 계획 범위가 아니다. |
| 외부 A2A 또는 managed-agent runtime 우선 도입 | v1 제외 | 내부 제품 runtime의 tool/context/approval 계약을 먼저 안정화해야 한다. 외부 agent interoperability는 장기 후보로 둔다. |
| 모든 task agent를 별도 invocation으로 분리 | 기각 | 로컬 LLM 비용과 latency가 커진다. 일반 task는 domain skill로 inline 처리하고 verifier/write/template만 분리한다. |
| LangGraph/Qwen-Agent 직접 의존 | 보류 | 상태 그래프와 Qwen worker 개념은 참고하되, v1 runtime contract를 특정 framework에 묶지 않는다. |
| 긴 context/thinking 기본값 | 기각 | 로컬 LLM에서는 latency와 동시성이 무너질 수 있다. runtime profile과 escalation policy로 제한한다. |
| Pydantic validation only | 기각 | 사후 검증만으로 malformed output을 줄이기 어렵다. 가능한 경우 constrained generation을 먼저 적용한다. |
| SGLang only | 보류 | PoC default 후보로는 가능하지만 vLLM과 runtime profile별 bakeoff가 필요하다. |
| vLLM only | 보류 | compatibility 후보로는 좋지만 SGLang과 structured output, latency, tool-call path 비교가 필요하다. |
| OpenAI-compatible API를 behavioral contract로 간주 | 기각 | reasoning field, tool parser, finish reason, structured output 보장이 provider/serving별로 다르다. |
| 모든 내부 tool을 MCP server로 변환 | 기각 | 내부 service는 typed service + gateway로 유지하고 MCP는 외부 capability boundary 중심으로 사용한다. |
| LLM search planner always-on | 기각 | deterministic query builder를 우선하고 LLM query expansion은 예외적으로 사용한다. |
| LLM writer가 artifact 전체 생성 | 기각 | artifact 구조와 citation insertion은 deterministic renderer가 담당한다. |
| Custom DB state machine만으로 batch/approval wait 처리 | 보류 | interactive는 가능하지만 long-running/batch/approval wait은 durable workflow boundary가 필요하다. |
| DGX Spark를 high-concurrency production 기준으로 가정 | 기각 | PoC, pilot, batch/offline worker 기준으로 평가한다. |

## Decision Log

### 확정 결정

| 항목 | 결정 |
|---|---|
| 외부 A2A | v1 범위에서 제외 |
| v1 실행 모델 | in-process graph orchestrator |
| 기본 canonical 모델 | `Qwen/Qwen3.6-35B-A3B` |
| 로컬 MLX 기본 checkpoint | `mlx-community/Qwen3.6-35B-A3B-4bit` |
| 기본 제어 방식 | free handoff가 아니라 manager-controlled graph |
| 단순 요청 처리 | deterministic fast path 우선 |
| decomposition | 모든 요청에 수행하지 않고 graph path에서 manager routing과 결합 |
| structured output | constrained generation + Pydantic validation + runtime business validator |
| manager output | `ExecutionGraph` schema + validator 필수 |
| graph rollout | `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false` 기본값 |
| task agent | extract/summarize/compare/draft는 domain agent 내부 skill |
| 별도 invocation | verifier, write_proposal, approval.proposal_preview, writer.template |
| evidence | `EvidencePacket`을 verifier/writer/search/domain 공통 contract로 사용 |
| recovery | verifier가 아니라 manager policy가 결정 |
| search executor | 기존 `domains/rag/application.py`와 domain tools의 thin adapter |
| search planner | deterministic-first, LLM query expansion은 optional |
| artifact ownership | graph path artifact는 `writer.template`이 소유, fast path는 기존 parser 유지 |
| template writer | deterministic renderer + evidence-bound LLM section filler |
| approval preview | canonical `WriteProposal`과 LLM explanation 분리 |
| 모델 교체성 | adapter + `ModelProfile` + per-model prompt override |
| OpenAI-compatible API | transport compatibility로만 취급 |
| reasoning 기본값 | non-thinking 기본, thinking은 runtime profile과 escalation policy가 허용할 때만 사용 |
| context 기본값 | interactive는 32K 시작, 64K 이상은 benchmark gate 후 확장 |
| retrieval budget | 후보 20~40개, rerank 4~8개, 일반 final evidence 2K~4K token 시작점 |
| memory | short-term은 8~16턴과 현재 evidence/tool result, long-term은 typed/audited state만 저장 |
| serving v1 | `Qwen/Qwen3.6-35B-A3B` local OpenAI-compatible endpoint 기준 |
| Serving engine 평가 | Qwen3.6-35B-A3B 고정 후 SGLang/vLLM runtime profile별 bakeoff |
| Internal tools | typed service + tool gateway 유지 |
| MCP | 외부 capability boundary 중심 |
| Observability | internal trace source of truth + OTel export |
| Eval fixture | Phase A부터 starter dataset과 pass/fail gate 정의 |
| batch 승인 | 장기적으로 DB/workspace admin policy |

### 검증 전 가설

| 항목 | 검증 방식 |
|---|---|
| Graph path가 로컬 LLM에서도 비용 대비 가치가 있다 | Phase 0 baseline과 Phase B/F perf gate |
| `EvidencePacket` query_plan 필드가 verifier/eval에 충분히 유용하다 | Phase C/D eval fixture |
| `writer.template`를 별도 invocation으로 두는 가치가 있다 | Phase F template output eval |
| new AgentRun tables가 Snapshot 확장보다 낫다 | Phase A/E migration 상세 플랜 |
| SGLang이 structured output에서 충분히 안정적이다 | manager/verifier/writer schema success rate |
| vLLM이 high-risk tool-call path에서 더 안정적일 수 있다 | tool-call-heavy eval bakeoff |
| OpenAI-compatible endpoint 간 behavior 차이가 크다 | response shape diff와 malformed rate 비교 |
| pgvector가 초기 RAG에 충분하다 | ACL/JOIN/search latency benchmark |
| Qdrant가 hybrid retrieval 품질을 개선한다 | dense+sparse retrieval eval |
| local reranker가 한국어 업무 데이터에 충분하다 | Korean 업무 eval set |
| deterministic search planner가 대부분 요청을 처리한다 | LLM query expansion invocation rate |
| constrained generation이 fallback rate를 낮춘다 | malformed manager output rate |
| claim-level verifier가 unsupported claim을 줄인다 | unsupported claim eval |
| OTel export가 운영 분석에 충분하다 | trace completeness eval |
| durable workflow가 approval wait/batch 안정성을 높인다 | retry/resume/idempotency test |
| service separation이 2대 DGX Spark에서 tensor parallel보다 실용적이다 | long-doc/RAG/embedding 부하 테스트 |

### 차후 결정

| 항목 | 결정 시점 |
|---|---|
| `AgentRun` DB schema 세부 컬럼 | Phase A 상세 구현 플랜 |
| 기존 approval snapshot 이관/삭제 방식 | Phase E 상세 구현 플랜 |
| 병렬 specialist 실행 | v2 확장 설계 |
| worker-backed long-running agent | batch/ambient agent 착수 시 |
| workspace admin policy UI 범위 | batch/admin UI 착수 시 |
| LoRA/PEFT domain adaptation 도입 | eval dataset과 운영 로그 큐레이션 체계 확정 후 |
| K8s/Ray/Spark 운영 스택 | single-node PoC와 pilot benchmark 이후 |
| LLM Gateway를 내부 구현할지 LiteLLM 등으로 갈지 | pilot benchmark 이후 |
| pgvector vs Qdrant | Phase C 검색 품질/운영성 검증 후 |
| reranker 모델 | 자체 Korean eval set 구축 후 |
| Temporal vs Prefect vs custom worker | batch/approval wait PoC 이후 |
| Langfuse/Phoenix/MLflow UI | OTel export와 내부 trace 안정화 후 |
| NVIDIA Dynamo 도입 여부 | multi-node/high-concurrency 요구 발생 후 |
| remote MCP production 범위 | external integration security review 후 |
| A2A protocol 도입 여부 | internal runtime contract 안정화 후 |

## Rollback Plan

이 문서는 설계 계획이므로 코드 rollback은 없다. 이후 구현 단계에서 문제가 생기면 다음 순서로 되돌린다.

1. `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false`로 graph runtime 진입을 중단한다.
2. chat entrypoint를 기존 single-loop agent path로 전환한다.
3. 새 runtime trace table은 read-only로 보존하고 신규 write만 중단한다.
4. approval flow는 기존 approval endpoint 계약을 유지한 채 compatibility shim 또는 old snapshot path로 되돌린다.
5. 실패 원인을 eval fixture와 trace event로 정리한 뒤 단계별 재도입한다.
