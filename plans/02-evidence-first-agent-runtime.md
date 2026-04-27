# Evidence-First Hybrid Agent Runtime

> 문서 성격: Doowon AI runtime 재설계를 위한 실행 설계 문서.  
> 참고 연구 문서: [`01-agentic-harness-engineering-report.md`](../docs/planning/01-agentic-harness-engineering-report.md)
> 목표: Qwen3.6-35B-A3B 기반 local-first runtime을 유지하면서, 정책적으로 통제된 external LLM/search provider를 붙일 수 있는 agent 운영 구조를 만든다.

## Context

현재 Doowon AI 플랫폼은 MCP-shaped capability registry, workspace-scoped tool gateway, RAG provider, approval flow, streaming envelope를 이미 갖고 있다. 다만 agent 실행 모델은 아직 단일 agent loop 중심이다. 이 구조는 단기 구현에는 빠르지만, 다음 요구가 커질수록 유지보수 비용이 높아진다.

- v1 canonical 모델은 `Qwen/Qwen3.6-35B-A3B`로 고정한다.
- 로컬 MLX 개발/PoC checkpoint는 `mlx-community/Qwen3.6-35B-A3B-4bit`를 기본값으로 사용한다.
- Qwen3.6-35B-A3B는 긴 context와 tool calling을 지원하지만, 큰 tool catalog와 긴 대화 이력에 취약하다.
- PMS, Meeting, Docs, Planner, RAG 같은 도메인 컨텍스트가 계속 늘어난다.
- 추후 LLM 모델이나 serving stack이 바뀌어도 agent contract와 tool/context boundary는 유지되어야 한다.
- 사용자 정의 템플릿, batch 작업, ambient/event-driven 작업까지 확장하려면 실행 trace와 approval policy가 agent 단위로 남아야 한다.

따라서 목표는 "모든 요청을 multi-agent로 비싸게 실행"하는 것이 아니라, **deterministic shortcut + graph orchestrator + evidence-first specialist runtime**을 만드는 것이다.

Doowon AI runtime은 local-first를 기본 원칙으로 유지하지만 external LLM과 external search를 완전히 배제하지 않는다. 내부 문서 원문, PLM row, 주문서/문서 전문, 제품 사양 비교, sensitive draft generation은 local model과 workspace-scoped tool gateway 안에서 처리한다.

반면 복잡한 planning, execution graph candidate generation, report outline, redacted quality review, clarification generation, 외부 공개 자료 검색은 `DataSensitivity`, `ExternalEgressPolicy`, `ModelProfile`, `RuntimeProfile`, `ToolSecurityPolicy`를 통과한 경우 external provider profile을 사용할 수 있다. External provider는 runtime core가 아니라 policy-controlled provider adapter다.

`EvidencePacket`은 내부 runtime contract로 유지하며 external provider에 직접 전달하지 않는다. 외부 reasoning에는 `ExternalSafeEvidenceSummary`를 사용하고, 외부 검색에는 sanitized query만 사용한다. 외부 검색 결과는 `ExternalSearchResult`로 정규화한 뒤 trust level, provenance, provider metadata를 포함해 `EvidencePacket`에 편입한다.

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

### 3. External LLM usage is policy-controlled, not prompt-controlled

Doowon runtime은 local-first를 기본 원칙으로 유지하되, external LLM을 완전히 배제하지 않는다. 내부 데이터 원문 접근, PLM row 해석, 주문서/문서 전문 처리, 제품 사양 비교는 local model과 workspace-scoped tool gateway 안에서 수행한다.

External LLM은 내부 데이터 processor가 아니라 policy-controlled reasoning provider다. 사용할 수 있는 역할은 sanitized intent 기반 planning, execution graph candidate generation, report outline, redacted quality review, clarification question generation으로 제한한다.

External LLM 사용 여부는 사용자 prompt가 아니라 runtime policy, workspace setting, data sensitivity, provider availability, cost/latency budget, approval policy가 결정한다. `EvidencePacket`은 external provider로 직접 전달하지 않으며, 필요한 경우 `ExternalSafeEvidenceSummary`로 축약, 익명화, 최소화한 뒤 전송한다.

External LLM에 보내면 안 되는 데이터는 다음이다.

- 내부 문서 원문.
- `EvidencePacket` raw item.
- PLM row.
- 주문서 전문.
- 고객명, 제품코드, 주문번호, 도면번호.
- BOM, 원가, 가격, 계약 조건.
- 내부 시스템 URL.

External LLM에 보낼 수 있는 데이터는 다음으로 제한한다.

- sanitized user intent.
- available agent 목록.
- public tool description.
- domain metadata.
- `ExternalSafeEvidenceSummary`.
- redacted draft.
- evidence coverage summary.
- missing intents.

OpenAI/Claude SDK와 API는 runtime contract가 아니라 provider adapter다. OpenAI Agents SDK의 guardrail/tracing이나 Claude SDK의 agent harness 기능은 참고할 수 있지만, Doowon의 egress decision, sanitizer, verifier, approval, trace source of truth를 대체하지 않는다.

### 4. External Search Provider Boundary

Doowon runtime은 외부 웹/공개 자료 검색을 자체 crawler 또는 별도 search infrastructure로 먼저 구축하지 않는다. v1에서는 OpenAI/Claude 등 external provider SDK 또는 API의 web/search capability를 `ExternalSearchProvider`로 사용할 수 있다.

단, external provider는 search infrastructure일 뿐 runtime contract의 source of truth가 아니다. Doowon runtime은 external search eligibility decision, query sanitization, data egress policy, provider routing, result normalization, evidence trust labeling, citation preservation, audit log, verifier integration을 계속 소유한다.

외부 검색 query는 데이터 반출로 취급한다. 고객명, 제품코드, 주문번호, 도면번호, 내부 URL, 가격, 원가, BOM, 계약 조건은 external search query에 포함하지 않는다.

`ExternalSearchQuerySanitizer`와 external prompt redaction은 external provider 호출 전에 local/pre-egress 단계에서 수행한다. 기본 구현은 deterministic rule, local NER, local model, workspace metadata dictionary를 사용한다. Sanitization 또는 redaction을 위해 raw prompt, raw evidence, raw tool result를 external provider에 보내지 않는다.

Sanitizer가 민감 정보를 제거할 수 없거나 sensitivity를 낮출 수 없는 경우 external search 또는 external LLM 호출은 차단한다.

External search 허용 조건은 다음이다.

- 사용자가 최신 공개 정보를 요청한다.
- 법규, 표준, 인증 같은 공개 정보가 필요하다.
- 공급사 공개 사양 또는 공개 시장 정보가 필요하다.
- 내부 evidence만으로 배경 설명이 부족하다.
- workspace policy가 external search를 허용한다.
- query sanitization이 성공한다.

External search 금지 조건은 다음이다.

- query sanitization이 실패한다.
- restricted/secret data 기반 query다.
- 고객명, 제품코드, 주문번호, 도면번호, 내부 URL, 가격, 원가, BOM, 계약 조건을 제거할 수 없다.
- workspace policy가 external search를 금지한다.
- 사용자가 no-external-search를 명시했다.
- provider budget, latency, rate limit을 초과한다.

Sanitization 예시는 다음을 기본 leakage eval seed로 사용한다.

```text
원본:
A고객의 DX-2400B 주문서 기준으로 유럽 CE 인증 리스크를 검색해줘.

금지 query:
A고객 DX-2400B 주문서 유럽 CE 인증 리스크

허용 query:
industrial electronic component CE certification EU regulatory requirements recent changes
```

External search result는 기본적으로 `untrusted` 또는 `mixed` trust level로 `EvidencePacket`에 들어간다. 다만 공식 기관, 표준기관, 규제기관 allowlist source는 policy에 따라 `trusted`로 승격될 수 있다. Internal/external conflict는 단순 source 위치가 아니라 `authority_class`, freshness, trust level, workspace policy, verifier confidence를 기준으로 판단한다. Claude Code SDK는 개발 자동화와 coding agent에는 사용할 수 있지만, 운영 runtime의 기본 external search provider로 직접 채택하지 않는다.

### 5. Structured outputs and constrained generation

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
    agent_id: str
    inputs_ref: str | None = None
    must_run_after: list[str] = []
    purpose: str


class ExecutionGraph(BaseModel):
    intent: str
    domains: list[str]
    risk: RiskLevel
    output_kind: str
    invocations: list[InvocationSpec]
    requires_verifier: bool
    requires_approval_preview: bool
```

검증 규칙은 runtime에서 강제한다.

- `agent_id`, `intent`, `domains`, `output_kind`는 DB enum migration이 필요한 closed enum으로 고정하지 않고 registry-validated open string으로 둔다.
- `agent_id`는 workspace entitlement, `allowed_app_ids`, `AgentDefinitionResolver` 결과 안에 있어야 한다.
- `intent`, `domains`, `output_kind`는 runtime registry와 prompt revision별 allowlist로 검증한다.
- `external.search`는 direct invocation target이 될 수 없다. External search는 `search.executor` sub-path에서만 실행 가능하다.
- manager output에 `agent_id=external.search`가 포함되면 graph validation failure로 처리하고 local manager path 또는 single-loop fallback으로 전환한다.
- write-touching tool이 graph 안에 있으면 manager 출력과 무관하게 risk floor는 `high`다.
- manager output validation이 실패하면 `AIDOO_AI_RUNTIME_GRAPH_ENABLED`가 켜져 있어도 기존 single-loop path로 fallback한다.
- malformed output은 serving stack, `ModelProfile`, prompt revision, invocation kind별로 trace에 남긴다.

### 6. Evidence-first

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
    external_search_used?: boolean
    external_search_provider?: "openai" | "claude" | "other"
    sanitized_query_ref?: string
  }
  items: Array<{
    ref: ResourceRef
    source_kind:
      | "internal_doc"
      | "plm_db"
      | "order_doc"
      | "ppt"
      | "meeting"
      | "pms"
      | "planner"
      | "external_web"
      | "external_pdf"
      | "external_vendor_page"
      | "external_regulation"
      | "external_news"
    excerpt: string
    score?: number
    freshness?: string
    access_scope?: string
    provenance?: string
    trust_level?: "trusted" | "untrusted" | "mixed"
    provider?: "local" | "openai" | "claude" | "other"
    retrieved_at?: string
    published_at?: string
    citation_url?: string
    authority_class?:
      | "internal_system_of_record"
      | "official_regulation"
      | "standard_body"
      | "vendor_official"
      | "public_web"
      | "news_media"
      | "unknown"
  }>
  coverage: {
    intents_covered: string[]
    intents_missed: string[]
  }
}
```

Verifier는 claim과 evidence를 이 DTO 기준으로 매칭한다. 도메인별 tool result shape이 달라도 manager 이후 단계는 동일한 evidence contract를 본다. Cross-workspace 필터링은 packet build 시점이 아니라 query/tool execution 시점에 수행해야 한다.

Internal evidence는 ACL, provenance, source quality에 따라 `trusted`가 될 수 있다. External web evidence는 기본 `untrusted` 또는 `mixed`로 시작하고, 공식 기관/표준기관 allowlist처럼 별도 정책이 있는 경우에만 `trusted`로 승격할 수 있다.

내부 업무 사실, PLM row, 주문서, 고객 조건, 사내 승인 상태는 `internal_system_of_record` evidence를 우선한다. 반면 법규, 표준, 인증, 공개 규제 변경은 `official_regulation` 또는 `standard_body` source가 더 높은 authority를 가질 수 있다. Internal/external conflict는 `authority_class`, freshness, trust level, workspace policy, verifier confidence를 함께 보고 판단한다. 외부 evidence만으로 `high_risk_action`을 실행하지 않는다.

기본 trust mapping은 다음에서 시작하고 workspace/domain policy로만 강화한다.

| source kind | default authority_class | 기본 trust level |
|---|---|---|
| PLM DB | `internal_system_of_record` | `trusted` |
| 주문서/계약서 내부 문서 | `internal_system_of_record` | `trusted` 가능 |
| 내부 승인 문서 | `internal_system_of_record` | `trusted` 가능 |
| 공식 규제기관 | `official_regulation` | `trusted` 가능 |
| 표준기관 | `standard_body` | `trusted` 가능 |
| 공급사 공식 페이지 | `vendor_official` | `mixed` |
| 일반 웹 | `public_web` | `mixed` 또는 `untrusted` |
| 뉴스/블로그/포럼 | `news_media` | `untrusted` |

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

### 7. Task skills are inline by default

`extract`, `summarize`, `compare`, `draft` 같은 일반 task는 별도 agent invocation으로 분리하지 않는다. 로컬 LLM 비용과 latency를 줄이기 위해 domain agent 내부 skill로 처리한다.

별도 invocation으로 분리하는 예외는 다음이다.

- `verifier`: 산출물 검증과 grounding 판단 책임을 분리해야 한다.
- `write_proposal`: write action 전 변경 의도를 별도 구조로 고정해야 한다.
- `approval.proposal_preview`: 사용자 승인 경계와 연결된다.
- `writer.template`: 사용자 정의 템플릿과 최종 산출물 품질을 독립적으로 평가해야 한다.

### 8. Risk-based approval

승인은 prompt 지시가 아니라 runtime policy로 강제한다.

- read/internal search/extract/draft는 기본 자동 실행.
- write, 외부 전송, 권한 변경, 고비용 batch, 낮은 verifier confidence는 승인 또는 review queue 필요.
- external LLM/search 호출은 `ExternalEgressPolicy`와 sanitizer를 통과해야 하며, confidential context에서는 approval 또는 review queue를 요구할 수 있다.
- batch 작업은 step마다 묻지 않고 workspace/domain/risk policy에 따라 자동 실행하거나 review queue로 보낸다.
- 사용자가 승인하는 canonical 대상은 LLM 설명문이 아니라 deterministic `WriteProposal`이다.
- `ApprovalPreview`는 사람이 이해하기 쉬운 설명이며 실제 execution source가 아니다.

### 9. ModelProfile for model swap

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

### 10. Runtime profiles over always-on reasoning

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

`RuntimeProfile`은 workload 성격을 나타내며 local/external provider 선택 기준으로 확장하지 않는다. `external_planning`, `external_reasoning`, `external_quality_review`, `external_search` 같은 값은 `RuntimeProfile`에 넣지 않고 `AgentInvocation` purpose, `ModelRouteDecision`, provider decision, feature flag로 표현한다.

Qwen3.6-35B-A3B profile은 `enable_thinking=false`에 해당하는 non-thinking 경로를 기본값으로 보고, thinking은 `ModelProfile.reasoning_escalation_policy`가 허용할 때만 켠다. GPT/Claude 등 외부 profile도 같은 contract를 유지하되, provider별 reasoning control은 adapter와 prompt override가 흡수한다.

Thinking escalation은 다음 조건에서만 허용한다.

- 다문서 evidence 충돌.
- 복수 도메인 synthesis.
- high-risk action planning.
- verifier가 unsupported 또는 contradicted evidence를 감지한 경우.
- 사용자가 명시적으로 reasoning-heavy 분석을 요청한 경우.

### 11. Token, retrieval, and memory budgets

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

### 12. Serving profile and deployment assumptions

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

### 13. Observable and reversible rollout

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
  - ordering은 UUID 정렬에 의존하지 않고 `(run_seq, invocation_seq, event_seq)`처럼 `AgentRun` 안에서 monotonic한 정수 sequence로 고정한다.
- `SearchProfile`
  - source kind, query expansion, filters, candidate top-k, rerank top-k, final evidence token budget, rerank strategy, recency weighting, embedding model version.
  - retrieval budget과 ranking/search behavior만 표현한다. external provider eligibility, provider preference, sanitizer policy, trust default는 `ExternalSearchDecision`과 policy contract가 소유한다.
- `VerifierResult`
  - `status`, `missing_evidence`, `unsupported_claims`, `contradictory_evidence`, `policy_risks`, `evidence_coverage`, `suggested_recovery`, `confidence`.
- `ModelProfile`
  - model-family-specific tool, reasoning mode support, prompt, retry behavior, runtime profile limits, structured decoding availability, prompt-cache policy.
  - provider type, hosted search capability, retention/data-use constraints, provider-specific reasoning/search control을 표현한다.
- `ProviderDataPolicy`
  - external provider의 data retention, training/data-use setting, region, enterprise contract status, logging behavior를 표현한다.
- `ProviderProfile`
  - provider capability, hosted search availability, provider data policy, region, cost/latency class, health status를 표현한다.
- `ExternalSearchDecision`
  - `SearchProfile`이 만든 검색 의도와 `ExternalEgressPolicy` 결과를 결합해 external search 허용 여부, provider, sanitized query requirement, cache policy, fallback reason을 표현한다.

```ts
type ProviderDataPolicy = {
  retention_mode: "none" | "limited" | "provider_default" | "unknown"
  training_use_allowed: boolean
  enterprise_contract_required: boolean
  region?: string
  logging_behavior?: "none" | "metadata_only" | "provider_default" | "unknown"
  policy_verified_at?: string
}

type ModelProfileProviderFields = {
  model_id: string
  provider: "local" | "openai" | "claude" | "other"
  provider_data_policy?: ProviderDataPolicy
}
```

- `DataSensitivityClassifier`
  - 단일 실행 지점이 아니라 `RequestSensitivityClassifier`와 `PayloadSensitivityClassifier`를 묶는 runtime component다.
  - `RequestSensitivityClassifier`는 user request, selected workspace, `allowed_app_ids`, conversation scope, attached file, requested tool scope를 기준으로 pre-routing `DataSensitivityDecision`을 생성한다.
  - `PayloadSensitivityClassifier`는 external provider 호출 직전에 selected context, retrieval result metadata, tool result metadata, redacted payload를 다시 검사한다.
  - request classification은 `ModelRouter`보다 먼저 수행하고, payload classification은 `ExternalEgressPolicy`와 provider invocation 직전에 수행한다.
  - sensitivity classification을 위해 raw prompt, raw evidence, raw tool result를 external provider에 보내지 않는다.
  - 기본 구현은 deterministic rules, local NER, local model, workspace metadata dictionary를 사용한다.
  - confidence 부족, unknown sensitive entity, unsupported attachment type, policy mismatch를 감지하면 sensitivity를 낮추지 않는다.
  - classification 실패 또는 ambiguity의 기본값은 conservative escalation이며, Phase 6 v1에서는 external provider 호출을 차단하거나 approval path로 전환한다. review queue 전환은 queue infrastructure가 있는 경우에만 사용한다.
  - classification 결과는 `AgentTraceEvent`에 남긴다.

```ts
type DataSensitivityDecision = {
  sensitivity: DataSensitivity
  reason_codes: string[]
  inspected_inputs: Array<{
    input_ref: string
    input_kind:
      | "user_prompt"
      | "attachment"
      | "context_ref"
      | "tool_result"
      | "evidence"
      | "conversation_scope"
    detected_entities: Array<{
      entity_type:
        | "customer"
        | "product_code"
        | "order_id"
        | "drawing_id"
        | "price"
        | "cost"
        | "bom"
        | "contract_term"
        | "internal_url"
        | "person_name"
        | "project_name"
        | "unknown_sensitive"
      redacted: boolean
    }>
  }>
  policy_id?: string
  classifier_version: string
  classifier_stage: "request" | "payload"
}
```

- `DataSensitivity`
  - `public`, `internal`, `confidential`, `restricted`, `secret` 등급으로 external LLM/search eligibility를 판정하는 기본 분류다.
  - 기본 정책 매트릭스는 workspace admin policy의 seed로 사용하고, 더 느슨한 정책은 명시적 admin 설정과 audit 대상 변경으로만 허용한다.

| sensitivity | external LLM | external search | raw payload egress |
|---|---|---|---|
| `public` | 허용 | 허용 | 가능 |
| `internal` | 제한 허용 | 제한 허용 | 금지 |
| `confidential` | 승인 기반 제한 허용 | 승인 기반 제한 허용 | 금지 |
| `restricted` | 기본 금지 | 기본 금지 | 금지 |
| `secret` | 금지 | 금지 | 금지 |

- `ExternalEgressPolicy`
  - workspace/domain/sensitivity별 external LLM/search 허용 여부, raw prompt/evidence 전송 금지, redacted summary 허용, approval requirement, provider/domain allowlist, retention rule을 표현한다.
- `ModelRouter` / `ModelRouteDecision`
  - runtime profile, task complexity, data sensitivity, egress policy, cost/latency budget, provider availability를 기준으로 local/external provider와 fallback profile을 결정한다.
  - routing decision에는 selected profile/provider, sensitivity, policy id, redaction requirement, approval requirement, fallback profile이 남아야 한다.
- `ExternalSafeEvidenceSummary`
  - external reasoning provider에 넘길 수 있는 redacted/minimized summary다.
  - raw excerpt, internal resource ref, customer/product identifiers, PLM row, BOM/cost/price, contract terms는 포함하지 않는다.
- `SanitizedExternalSearchQuery`
  - original query reference, sanitized query, removed entity types, sensitivity before/after, external search allow/deny reason을 기록한다.
- `ExternalSearchResult`
  - provider search response를 title, url, source name, retrieved/published time, snippet/excerpt, provider trace id, trust level, provenance로 normalize한 DTO다.
  - cache key, cache hit, search session id를 포함해 audit/reproducibility boundary를 제공한다.

```ts
type ExternalSearchResult = {
  title: string
  url: string
  source_name?: string
  published_at?: string
  retrieved_at: string
  snippet: string
  content_excerpt?: string
  provider: "openai" | "claude" | "other"
  provider_trace_id?: string
  confidence?: number
  trust_level: "untrusted" | "mixed" | "trusted"
  provenance:
    | "external_web"
    | "external_pdf"
    | "external_vendor_page"
    | "external_regulation"
    | "external_news"
  cache_key?: string
  cache_hit?: boolean
  search_session_id?: string
}
```

- `ExternalCallProposal`
  - external call이 approval 또는 review queue 대상이 되는 경우 사용자가 승인하거나 검토하는 deterministic payload다.
  - 모든 external call에 항상 사용자 승인을 요구한다는 의미는 아니다.
  - Runtime은 workspace/domain/sensitivity policy에 따라 external call을 `auto_allowed`, `trace_only`, `approval_required`, `review_queue_required`, `denied` 중 하나로 분류할 수 있다.
  - Phase 6 v1 구현은 review queue backend가 존재하지 않으면 `review_queue_required`를 emit하지 않는다. 이 경우 confidential/high-risk external call은 `approval_required` 또는 `denied`로만 수렴한다.
  - approval 또는 review가 필요한 경우 사용자가 승인하는 대상은 LLM 설명문이 아니라 deterministic `ExternalCallProposal`이다.
  - `ExternalCallProposal`은 provider, sanitized payload reference, egress policy decision, expected data class, cost/latency budget, redaction summary를 포함한다.

```ts
type ExternalCallDecision =
  | "auto_allowed"
  | "trace_only"
  | "approval_required"
  | "review_queue_required"
  | "denied"

type ExternalCallProposal = {
  proposal_id: string
  decision: ExternalCallDecision
  decision_supported_in_v1: boolean
  provider: "openai" | "claude" | "other"
  purpose:
    | "planning"
    | "reasoning"
    | "quality_review"
    | "external_search"
  sensitivity: DataSensitivity
  egress_policy_id: string
  payload_kind:
    | "sanitized_query"
    | "redacted_prompt"
    | "external_safe_evidence_summary"
    | "redacted_report_draft"
  payload_ref: string
  redaction_summary: string
  data_not_sent: string[]
  estimated_cost?: number
  latency_budget_ms?: number
  approval_required: boolean
}
```
- `ToolSecurityPolicy`
  - 독립 보안 시스템이 아니라 capability metadata/policy extension으로 둔다.
  - auth mode, OAuth scope, token passthrough 제한, input sanitizer, output trust level, PII redaction, network policy를 표현한다.
- `WriteProposal`
  - 사용자가 승인하는 deterministic diff/action object.
  - `ApprovalPreview`는 이 object를 설명할 수 있지만 실행 근거가 될 수 없다.
- `ClaimCheck`
  - `grounded_report`, `high_risk_action`, template output에서 선택적으로 남기는 claim-level grounding result.

### Runtime state machines

Phase A는 단일 선형 상태기계가 아니라 `AgentRun`, `AgentInvocation`, approval 상태를 분리해 고정한다. 기존 approval flow도 이미 snapshot status와 approval status를 분리하고 있으므로, 새 runtime도 이 경계를 유지한다.

```text
AgentRun:
pending
  -> running
  -> awaiting_approval
  -> completed
  -> failed
  -> cancelled
  -> abandoned

AgentInvocation:
pending
  -> running
  -> awaiting_approval
  -> resumed
  -> completed
  -> failed
  -> cancelled
  -> abandoned

Approval:
pending
  -> approved
  -> rejected
  -> expired
  -> executed
  -> failed
  -> cancelled
```

불변식:

- 한 `AgentRun`에는 여러 invocation이 있을 수 있다.
- 한 conversation에는 live `AgentRun`이 하나만 있어야 하며, `running`, `awaiting_approval`, `resumed` 계열 상태를 DB partial unique index 또는 동일 효력의 lock으로 보호한다.
- 한 `AgentRun`에는 pending approval이 하나만 있어야 하며, DB partial unique index와 concurrent test로 검증한다.
- approval resume은 새 `AgentRun`을 만들지 않고 같은 `AgentRun` 아래 새 `AgentInvocation`으로 이어진다.
- approval halt 시점에는 resolved tool/agent allowlist, `allowed_app_ids`, payload hash, policy decision을 checkpoint에 저장한다. resume 요청은 저장된 scope와 동일하거나 더 좁아야 하며, 생략으로 tool surface가 넓어지는 동작은 차단한다.
- `approved` 되었지만 resume되지 않은 approval도 expiry와 abandon 정책을 가진다.
- re-halt는 같은 `AgentRun` 아래 새 `AgentInvocation`과 새 approval checkpoint로 표현한다.
- cutover 동안 `AgentRun.id`와 기존 `AgentRunSnapshot.id` 연속성은 Phase A migration shape에서 먼저 다룬다. Phase E는 상세 이관과 제거 시점만 결정한다.

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
- `external.planning`
  - feature flag 뒤에서만 사용하는 optional descriptor다.
  - sanitized user intent, available agent list, domain metadata를 기반으로 execution graph candidate 또는 report outline을 만든다.
  - raw internal evidence를 보지 않고, output은 `ExecutionGraph` validator를 반드시 통과한다.
  - `external.planning`의 output은 final execution graph가 아니라 candidate graph다.
  - candidate graph는 local `manager.orchestrator` 또는 runtime validator가 workspace scope, agent allowlist, risk floor, egress policy, approval policy를 검증한 뒤에만 실행 가능한 `ExecutionGraph`로 승격된다.
  - external planning provider는 execution authority를 갖지 않는다.
- `external.quality_review`
  - redacted report draft, `ExternalSafeEvidenceSummary`, missing intent summary를 기반으로 품질 검토를 수행한다.
  - verifier를 대체하지 않으며 내부 ref, raw excerpt, PLM row를 보지 않는다.
  - external quality review output은 직접 최종 보고서가 되지 않는다.
  - Runtime은 external quality review의 suggestion만 수용할 수 있으며, 최종 draft는 `writer.template`이 내부 `EvidencePacket`, verifier result, redacted-safe suggestion을 기준으로 다시 생성한다.
  - external quality review suggestion도 policy, schema validation, leakage check를 통과해야 한다.
- `external.search`
  - sanitized query를 기반으로 OpenAI/Claude SDK/API search capability를 호출한다.
  - raw user prompt를 직접 받지 않고, `ExternalSearchResult`로 normalize한 결과만 반환한다.
  - `external.search`는 manager가 직접 invoke할 수 있는 general-purpose agent가 아니다.
  - `external.search`는 `search.executor` 내부의 provider adapter로만 호출된다.
  - 모든 external search 호출은 `SearchPlanBuilder`, `ExternalSearchQuerySanitizer`, `ExternalEgressPolicy`를 통과해야 한다.
  - manager의 `ExecutionGraph`가 `external.search`를 직접 invocation으로 지정하는 것은 `ManagerOutputValidator`가 차단한다.

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
3. `RequestSensitivityClassifier`가 user request, conversation scope, attached data, requested context, available tool scope를 기준으로 pre-routing `DataSensitivityDecision`을 생성한다.
4. `ModelRouter`가 runtime profile, `DataSensitivityDecision`, `ExternalEgressPolicy`, provider availability, cost/latency budget을 기준으로 local/external provider eligibility를 결정한다.
5. Feature flag가 꺼져 있으면 기존 single-loop path로 간다.
6. Fast path면 해당 domain agent invocation을 바로 생성한다.
7. Graph path면 manager가 `ExecutionGraph`를 만든다. External planning 후보는 feature flag가 켜진 경우 sanitized intent와 metadata만으로 candidate graph를 생성한다.
8. External planning output은 final execution graph가 아니며, `ManagerOutputValidator`가 schema, workspace app scope, agent allowlist, risk floor, egress policy, approval policy를 검증한 뒤에만 실행 가능한 `ExecutionGraph`로 승격된다.
9. 검증 실패 시 local manager path 또는 기존 single-loop path로 fallback한다.
10. Domain agent는 필요한 경우 `SearchPlan`을 만들거나 `search.planner`를 호출한다.
11. `search.executor`가 기존 MCP capability/RAG/domain service를 사용해 internal evidence를 수집한다.
12. 외부 공개 자료가 필요하고 policy가 허용하면 `PayloadSensitivityClassifier`, `ExternalSearchQuerySanitizer`, `ExternalEgressPolicy`를 통과한 뒤 `ExternalSearchProvider`를 호출한다. Manager가 `external.search`를 직접 invocation으로 지정하는 것은 허용하지 않는다.
13. External search result는 `ExternalSearchResult`로 normalize하고 trust level, `authority_class`, provider, retrieved_at, citation URL을 붙인 뒤 `EvidencePacket`에 merge한다.
14. Domain agent는 inline skill로 extract/summarize/compare/draft를 수행한다.
15. 고위험 또는 cross-domain 산출물은 verifier가 `VerifierResult`를 만든다.
16. Internal/external evidence conflict는 `authority_class`, freshness, trust level, workspace policy, verifier confidence를 기준으로 판단한다.
17. Verifier fail이면 manager가 recovery policy로 재검색, 추가 domain invocation, 사용자 질문, partial answer 중 하나를 선택한다.
18. Template 요청이면 `writer.template`이 최종 산출물을 만든다.
19. External quality review가 활성화된 경우에도 review output은 suggestion으로만 사용하며, 최종 산출물은 `writer.template`이 내부 `EvidencePacket`과 verifier result를 기준으로 다시 생성한다.
20. Write/external/batch action은 risk-based approval gate 또는 review queue를 통과한다.

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
  -> RuntimeProfile
  -> ModelProfile
  -> ModelRouter
  -> ExternalEgressPolicy
  -> LLM Gateway boundary
       -> Local Provider
            -> SGLang
            -> vLLM
            -> MLX
       -> External LLM Provider
            -> OpenAI API / SDK
            -> Claude API / SDK
       -> External Search Provider
            -> OpenAI web_search
            -> Claude web search
```

- Agent runtime은 risk, approval, evidence, trace, runtime policy를 소유한다.
- `ModelProfile`은 parser, reasoning mode, tool-call format, retry behavior, prompt override를 소유한다.
- `ModelRouter`와 `ExternalEgressPolicy`는 provider selection, redaction requirement, external approval requirement를 소유한다.
- External provider selection은 기능 지원 여부만으로 결정하지 않는다. `ModelRouter`는 provider의 data retention, training/data-use setting, regional availability, enterprise contract status, logging behavior를 `ModelProfile`과 `ExternalEgressPolicy` 기준으로 검증해야 한다.
- Provider data-use policy가 workspace policy와 충돌하면 해당 provider는 사용할 수 없다. Provider capability가 충분하더라도 retention 또는 data-use 조건이 맞지 않으면 local fallback, 다른 provider fallback, user clarification, review queue 중 하나로 전환한다.
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

### External Search Cache and Reproducibility

External search result는 provider raw response를 그대로 source of truth로 삼지 않는다. Runtime은 normalized `ExternalSearchResult`, sanitized query hash, provider, retrieved_at, result URL, title, snippet/content excerpt, trust level, citation URL을 audit 가능한 형태로 저장한다.

Cache policy는 workspace/domain/source policy에 따라 TTL을 가진다. Regulation, standard, official source는 상대적으로 긴 TTL을 가질 수 있고, news, market, general web source는 짧은 TTL을 가진다.

동일 `AgentRun` 또는 동일 report generation 안에서는 동일 sanitized query에 대해 동일 cached result를 사용해 재현성을 유지한다. Cache hit 여부와 cache key는 trace에 남긴다.

Provider raw response는 retention policy에 따라 저장 여부를 결정한다. Raw provider reasoning trace는 저장하지 않는다.

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
- Korean enterprise eval seed corpus를 먼저 만든다. 최소 범위는 routing, RAG relevance, grounded answer, sanitizer leakage, approval-safe drafting이다.
- launch SLO를 수치로 고정한다. 최소 항목은 concurrent active users, p95 TTFT, p95 report latency, queue depth, approval wait time이다.
- Qwen3.6-35B-A3B와 serving stack별 `ExecutionGraph` schema success rate, tool-call stability, malformed output rate를 Phase A 착수 전 hard gate로 측정한다.
- graph rollout kill criteria에는 concurrency dimension을 포함한다. 예: graph path p95는 baseline x2 이내 조건을 1인 단독뿐 아니라 지정 동시성에서도 만족해야 한다.
- external provider는 Phase 0에서 운영 호출을 전제하지 않고, sandbox/eval 환경에서 cost, latency, citation quality, redaction leakage baseline만 측정한다.
- graph rollout kill criteria: graph path p95는 baseline x2 이내, recovery path는 baseline x3 이내를 시작 기준으로 둔다.

### Phase A - Runtime contract foundation

- Phase A 구현 범위는 최소 kernel을 먼저 고정한다. 첫 PR은 `AgentRun`, `AgentInvocation`, `AgentTraceEvent`, minimal `ExecutionGraph`, minimal `EvidencePacket`, eval harness, feature flag skeleton에 집중한다.
- full hybrid DTO는 정본 contract로 유지하되, `ExternalSafeEvidenceSummary`, `SanitizedExternalSearchQuery`, `ExternalSearchResult`, `ExternalCallProposal`, `ProviderDataPolicy` 같은 external DTO 구현은 실제 external path가 열리는 PR에서 추가한다.
- `AgentDefinition`, `AgentDefinitionResolver`, `AgentRun`, `AgentInvocation`, `AgentTraceEvent`, `ExecutionGraph`, `EvidencePacket`, `SearchProfile`, `VerifierResult`, `ModelProfile` DTO를 추가한다.
- runtime profile enum과 token/context/memory budget DTO를 추가한다.
- `ModelProfile.reasoning_mode_support`와 structured decoding availability matrix를 추가한다.
- `DataSensitivity`, `RequestSensitivityClassifier`, `PayloadSensitivityClassifier`, `DataSensitivityDecision`, `ExternalEgressPolicy`, `ModelRouter`, `ProviderProfile`, `ExternalSearchDecision`, `ExternalSafeEvidenceSummary`, `SanitizedExternalSearchQuery`, `ExternalSearchResult`, `ExternalCallDecision`, `ExternalCallProposal` contract를 추가한다.
- `ModelProfile`에 `ProviderDataPolicy`, provider/search capability, retention/data-use constraint, provider-specific reasoning/search control 필드를 추가한다.
- `SearchProfile`은 retrieval-only로 유지한다. external search eligibility, sanitizer policy, provider preference, external result trust default는 `ExternalSearchDecision`과 `ExternalEgressPolicy`가 소유한다.
- `EvidencePacket.items[].authority_class`를 추가한다.
- external search cache 관련 `cache_key`, `cache_hit`, `search_session_id` 필드를 추가한다.
- `ToolSecurityPolicy`, `WriteProposal`, `ClaimCheck`는 개념 contract로 추가하되 세부 컬럼은 상세 구현에서 확정한다.
- `AgentRun`, `AgentInvocation`, `Approval` 상태기계와 approval/resume/rehalt 불변식을 문서와 테스트로 고정한다.
- 한 conversation의 live run, 한 run의 pending approval을 DB partial unique index 또는 동일 효력의 lock으로 보호하고 concurrent test를 추가한다.
- approval halt 시 resolved tool/agent allowlist와 `allowed_app_ids`를 checkpoint에 저장하고, resume 시 동일성 또는 축소 여부를 검증한다.
- 기존 `AgentRunSnapshot`과 새 `AgentRun`/`AgentInvocation`의 additive migration shape를 Phase A에서 정의한다. 초기 구현은 shadow-write와 read flag/compat projection으로 cutover risk를 낮춘다.
- `AgentTraceEvent` ordering과 OTel export naming map을 정의하고 GenAI semantic convention version을 고정한다. ordering은 per-run monotonic sequence를 사용한다.
- `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false` feature flag를 추가한다.
- external feature flag는 다음 이름으로 고정한다: `AIDOO_AI_EXTERNAL_LLM_ENABLED=false`, `AIDOO_AI_EXTERNAL_PLANNING_ENABLED=false`, `AIDOO_AI_EXTERNAL_REASONING_ENABLED=false`, `AIDOO_AI_EXTERNAL_QUALITY_REVIEW_ENABLED=false`, `AIDOO_AI_EXTERNAL_SEARCH_ENABLED=false`.
- provider config는 feature flag와 분리한다. 기본값은 `AIDOO_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER=openai`, `AIDOO_AI_ALLOWED_EXTERNAL_PROVIDERS=openai,claude`로 둔다. 단일 config를 쓰는 경우 `AIDOO_AI_EXTERNAL_SEARCH_PROVIDER=none|openai|claude`로 두고, `none`은 `AIDOO_AI_EXTERNAL_SEARCH_ENABLED=false`와 동일하게 취급한다.
- workspace policy storage seed를 추가한다. 최소 후보는 `workspace_egress_policies`, `workspace_external_provider_allowlist`, `workspace_url_allowlist`, `workspace_external_call_limits`이며 Phase 6에서는 read-only seed로 시작할 수 있다.
- trace event taxonomy에 external routing, egress decision, query sanitization, provider call, external result normalization을 추가한다.
- read-only inspection endpoint를 추가한다.
- eval fixture format과 starter dataset을 정의한다. 기본 위치는 `apps/api/tests/fixtures/ai_runtime/`로 두고, Phase A는 seed cases를 고정하며 rollout gate의 목표 케이스 수는 Phase F까지 확장한다.
- DB migration은 실행 전 상세 플랜에서 확정하되, one live run per conversation, one pending approval per run, retention/scrub 정책, snapshot compatibility/cutover 전략은 Phase A 산출물로 고정한다.
- raw thinking/reasoning trace는 영구 저장하지 않고, distilled state와 evidence reference만 저장하는 retention rule을 고정한다.

### Phase B - Fast path and manager graph

- 기존 chat stream 진입점 앞에 fast path router를 추가한다.
- runtime profile selector를 추가한다. 기본값은 `interactive_read`다.
- manager graph path는 constrained generation이 가능한 경우 이를 사용해 `ExecutionGraph`를 생성한다.
- `ManagerOutputValidator`를 구현한다.
- `ExecutionGraph`의 `intent`, `domains`, `output_kind`, `agent_id`는 registry-validated open string으로 검증한다. closed enum migration이 필요한 설계는 v1 기본값으로 삼지 않는다.
- malformed manager output, out-of-scope agent, invalid risk 또는 registry value는 기존 single-loop path로 fallback하고 fallback reason taxonomy를 trace에 남긴다.
- risk floor를 적용한다. write-touching graph는 항상 high risk 이상이다.
- `ModelProfile`을 `AgentRun` 생성 시 고정한다.
- graph path 진입 시 transport envelope에 planning 상태 이벤트를 낼 수 있어야 한다. manager output 검증이 끝날 때까지 UI가 무응답처럼 보이지 않게 한다.
- external planning 후보는 `AIDOO_AI_EXTERNAL_LLM_ENABLED`와 `AIDOO_AI_EXTERNAL_PLANNING_ENABLED` 뒤에서만 실행하고, sanitized intent, available agent list, domain metadata만 입력으로 사용한다.
- external reasoning escalation은 `AIDOO_AI_EXTERNAL_REASONING_ENABLED` 뒤에서만 실행한다.
- external planning output은 candidate graph로만 취급한다.
- candidate graph는 local manager 또는 runtime validator가 검증한 뒤에만 실행 가능한 `ExecutionGraph`로 승격한다.
- provider data-use policy가 workspace policy와 충돌하면 external planning/reasoning을 차단한다.
- external planning output도 기존 `ExecutionGraph` schema와 `ManagerOutputValidator`를 반드시 통과한다.
- external planning 실패 시 local manager path 또는 single-loop fallback으로 전환한다.
- external provider cost, latency, error, fallback reason을 trace에 남긴다.
- `ModelRouter`는 workspace/provider budget을 확인한다. daily/monthly bucket과 latency budget을 초과하면 local fallback, approval, 또는 denial로 수렴한다.
- non-thinking default와 thinking escalation policy를 `ModelProfile`에서 강제한다.
- OpenAI-compatible transport와 provider behavior contract를 분리한다.
- SGLang/vLLM manager output success rate를 같은 fixture로 비교한다.
- cancellation은 LLM stream과 graph node 사이마다 전파한다.
- 기존 `agent.py` loop는 specialist invocation 내부 실행기 또는 fallback path로 축소한다.

### Phase C - Search and evidence

- `search.planner`와 `search.executor` 경계를 도입한다.
- `SearchPlanBuilder`는 deterministic-first로 구현하고, LLM query expansion은 optional path로 제한한다.
- `search.executor`는 기존 `domains/rag/application.py`와 domain tools를 호출하는 thin adapter로 구현한다.
- `search.executor` sub-path는 `internal.rag.search`, `internal.domain.search`, `external.web.openai`, `external.web.claude`, `external.document.fetch`로 구분한다.
- `external.search`는 manager direct invocation이 아니라 `search.executor` provider adapter로만 호출한다.
- `ExternalSearchProvider` boundary와 OpenAI/Claude web search adapter 후보를 추가한다.
- external search provider 선택은 `AIDOO_AI_EXTERNAL_SEARCH_ENABLED`, `AIDOO_AI_DEFAULT_EXTERNAL_SEARCH_PROVIDER`, `AIDOO_AI_ALLOWED_EXTERNAL_PROVIDERS`로 제어한다.
- `ExternalSearchQuerySanitizer`는 local/pre-egress로 실행한다.
- `ExternalSearchQuerySanitizer`를 구현하고, sanitizer 실패 또는 restricted/secret query는 external search를 차단한다.
- `external.document.fetch`는 URL allowlist/blocklist, SSRF 방어, private network 접근 차단, redirect 제한, file size limit, MIME type allowlist, timeout, safe parser boundary를 통과해야 한다.
- `external.document.fetch`는 Cookie, Authorization, 내부 `X-*` header를 전달하지 않는다. 기본 허용 header는 `User-Agent`, `Accept` 같은 공개 fetch에 필요한 최소값으로 제한한다.
- `external.document.fetch` redirect는 hop마다 URL allowlist/blocklist, scheme, DNS/IP classification을 다시 검증한다. HTTP downgrade, private IP/localhost/link-local/metadata endpoint 이동, mixed-script IDN/punycode homograph는 차단한다.
- DNS rebinding 방지를 위해 resolve, IP classification, connection 대상, `Host` header 처리 순서를 명시하고 테스트한다.
- external document fetch는 external search와 동일하게 data egress/audit 대상이며, fetched content는 기본 `untrusted` 또는 `mixed` trust level로 시작한다.
- PDF, HTML, office 문서 등은 parser sandbox 또는 safe extraction boundary를 통과해야 한다.
- `ExternalSearchResult` normalization을 구현한다.
- 기존 RAG/domain tool result를 `EvidencePacket`으로 normalize한다.
- external source kind, trust level, provider, retrieved_at, published_at, citation URL을 `EvidencePacket`에 반영한다.
- external evidence에 `authority_class`를 부여한다.
- external search cache key, cache hit, search session id를 trace에 남긴다.
- 동일 `AgentRun` 안에서는 동일 sanitized query에 대해 동일 cached result를 사용한다.
- source kind별 cache TTL 정책을 정의한다.
- internal/external evidence merge policy를 구현한다. 내부 업무 사실, PLM row, 주문서, 고객 조건, 사내 승인 상태는 `internal_system_of_record` evidence를 우선한다. 법규, 표준, 인증, 공개 규제 변경은 `authority_class`, freshness, trust level, workspace policy, verifier confidence를 기준으로 판단한다.
- external search provider failure는 internal-only answer, partial answer, 사용자 질문 중 하나로 fallback한다.
- candidate top-k, rerank top-k, final evidence token budget, source kind, rerank, recency, embedding version, top-k policy를 trace에 남긴다.
- pgvector/Qdrant 또는 기존 store 후보와 reranker 후보를 같은 Korean 업무 eval set으로 비교한다.
- tool output trust level, malicious retrieved content handling, source provenance를 EvidencePacket normalization에 반영한다.
- malicious/untrusted retrieved content는 structural separator와 source label로 격리하고, 다음 turn memory에 raw instruction처럼 carryover되지 않도록 한다.
- EvidencePacket response shaper는 shared helper로 둔다.
- workspace isolation은 query/tool execution 시점에서 검증한다.
- trace event는 raw reasoning delta를 저장하지 않고 invocation 종료 시 summary/buffer flush 방식으로 기록한다.

### Phase D - Verifier and recovery

- `verifier.grounding`을 별도 invocation으로 추가한다.
- `VerifierResult`와 recovery policy table을 구현한다.
- claim-level `ClaimCheck`는 `grounded_report`, `high_risk_action`, template output에서 먼저 검토한다.
- verifier false pass/false fail eval을 추가한다.
- contradicted evidence와 verifier unavailable policy를 명시한다.
- external-only evidence에는 confidence cap을 적용한다.
- internal/external evidence conflict는 `authority_class`, freshness, trust level, workspace policy, verifier confidence를 기준으로 판단한다.
- 법규/표준/인증 관련 source는 `official_regulation` 또는 `standard_body` authority를 고려한다.
- external search retry는 기본 최대 1회로 제한한다.
- 재검색/추가 도메인/사용자 질문/partial answer 전환을 traceable하게 만든다.
- recovery latency gate와 recovery token budget cap을 둔다.
- verifier unavailable이면 answer를 unverified로 표시하고, 고위험 path에서는 사용자 검토로 보낸다.

### Phase E - Approval and batch policy

- 기존 approval flow를 `AgentRun` checkpoint로 흡수한다.
- canonical `WriteProposal`과 LLM-assisted `ApprovalPreview`를 분리한다.
- `ExternalCallProposal`을 approval flow와 review queue에 연결한다.
- `ExternalCallProposal`은 모든 external call 승인 강제가 아니라 policy decision object로 사용한다.
- external call decision은 `auto_allowed`, `trace_only`, `approval_required`, `review_queue_required`, `denied` 중 하나다. 다만 Phase 6 v1은 review queue backend가 없으면 `review_queue_required`를 emit하지 않고 `approval_required` 또는 `denied`로 수렴한다.
- confidential context에서 external call이 필요한 경우 approval을 경유한다. review queue는 Phase 7/admin policy surface 또는 durable workflow가 준비된 뒤 활성화한다.
- ApprovalPreview는 설명일 뿐 actual execution source가 아님을 명시한다.
- approval halt/resume은 same `AgentRun`, new `AgentInvocation` 원칙을 따른다.
- approval resume idempotency와 tool surface widening 방지 test를 추가한다.
- approval halt에서 저장한 resolved tool/agent allowlist와 resume 요청의 `allowed_app_ids`가 일치하거나 더 좁은지 검증한다.
- external call approval resume 시 sanitized payload와 policy decision이 변경되지 않았는지 idempotency check를 수행한다.
- 기존 `AgentRunSnapshot` compatibility/cutover 전략과 idempotent migration script는 Phase A migration shape를 기반으로 상세화한다.
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
- external quality review 후보는 `AIDOO_AI_EXTERNAL_LLM_ENABLED`와 `AIDOO_AI_EXTERNAL_QUALITY_REVIEW_ENABLED` 뒤에서만 추가하고 verifier를 대체하지 않는다.
- writer output을 external provider에 보낼 경우 redacted draft와 `ExternalSafeEvidenceSummary`만 허용한다.
- external quality review output은 final artifact가 아니라 review suggestion으로만 저장한다.
- writer.template은 internal `EvidencePacket`과 verifier result를 기준으로 최종 산출물을 다시 생성한다.
- external quality review suggestion에 민감 정보가 포함되거나 unsupported claim이 포함되면 폐기한다.
- redacted draft leakage eval과 external search citation quality eval을 추가한다.
- external provider cost/latency/quality tradeoff를 측정한다.
- routing, evidence, verifier, recovery, model swap, context addition eval fixture를 만든다.
- prefix-cache hit rate와 `ModelProfile.prompt_revision` invalidation을 검증한다.
- interactive/grounded_report/long_doc/high_risk_action profile별 latency, token, verifier pass rate를 비교한다.
- profile별 SGLang/vLLM serving engine bakeoff 결과를 rollout decision에 반영한다.

## Verification

- Baseline and rollout gates
  - single-loop baseline latency, malformed tool-call rate, duplicate-loop rate, eval pass rate를 기록한다.
  - TTFT, TPOT, thinking tokens, cache hit rate, groundedness, citation coverage, loop-abort rate를 기록한다.
  - routing confusion matrix, fast path false-positive/false-negative rate, cost per successful run을 기록한다.
  - launch SLO와 concurrency baseline을 기록한다.
  - Korean enterprise eval seed corpus가 존재하고 routing/RAG/grounding/sanitizer/approval-safe drafting fixture가 실행된다.
  - Qwen3.6-35B-A3B의 `ExecutionGraph` schema success, tool-call stability, malformed output gate가 Phase A 착수 전에 측정된다.
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
  - out-of-scope agent와 invalid registry value는 validator가 차단한다.
  - `ExecutionGraph`의 intent/domain/output kind는 registry-validated open string으로 검증된다.
  - write-touching graph는 high risk로 승격된다.
- Evidence contract
  - PMS/Meeting/Docs/Planner/RAG 검색 결과가 동일한 `EvidencePacket` shape로 normalize된다.
  - verifier와 writer는 domain별 raw result를 직접 보지 않는다.
  - external result는 `ExternalSearchResult`로 normalize된 뒤에만 `EvidencePacket`에 들어간다.
  - workspace isolation은 query/tool execution 시점에서 보장된다.
  - retrieval candidate/rerank/final evidence token budget이 `SearchProfile`과 trace에 남는다.
  - source provenance, access scope, provider, retrieved/published time, tool output trust level이 evidence normalization에 반영된다.
- RAG and search
  - deterministic `SearchPlanBuilder`가 대부분의 single-domain 요청을 LLM 없이 처리한다.
  - LLM query expansion invocation rate가 trace에 남는다.
  - vector store와 reranker 후보는 같은 Korean 업무 eval set으로 비교한다.
  - malicious retrieved content가 writer/verifier를 오염시키지 않는지 테스트한다.
  - external search provider 장애 시 internal-only answer, partial answer, 사용자 질문 fallback이 동작한다.
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
  - approval halt에 저장된 resolved tool/agent allowlist와 resume 요청 scope가 일치하거나 더 좁은지 검증한다.
  - 같은 approval을 재개해도 idempotency가 깨지지 않는다.
  - one live `AgentRun` per conversation과 one pending approval per run 불변식을 검증한다.
  - live run과 pending approval partial unique index 또는 동등한 lock이 concurrent test로 검증된다.
  - 기존 `AgentRunSnapshot`과 새 `AgentRun` shadow-write/compat projection parity를 검증한다.
- Model swap
  - Qwen local profile과 OpenAI-compatible external profile에서 같은 agent contract가 유지된다.
  - tool parser, finish reason, prompt override 차이를 `ModelProfile`로 흡수한다.
  - `ModelProfile`은 run 시작 시 lock된다.
  - non-thinking default와 thinking escalation policy가 provider별로 같은 runtime contract를 유지한다.
  - OpenAI-compatible response shape 차이를 기록한다.
  - Qwen reasoning/non-thinking control이 `ModelProfile.reasoning_mode_support`대로 동작한다.
- External LLM routing
  - `RequestSensitivityClassifier`가 pre-routing 단계에서 실행된다.
  - `PayloadSensitivityClassifier`가 external provider 호출 직전에 항상 실행된다.
  - sensitivity classification을 위해 raw prompt, raw evidence, raw tool result가 external provider로 전달되지 않는다.
  - classifier가 confidence 부족, unknown sensitive entity, unsupported attachment type, policy mismatch를 감지하면 sensitivity를 낮추지 않고 conservative escalation을 적용한다.
  - classification 실패 또는 ambiguity가 있으면 external provider 호출을 차단하거나 approval path로 전환한다. review queue는 backend가 있을 때만 허용한다.
  - raw internal document, raw evidence, PLM row, order content가 external LLM으로 전달되지 않는다.
  - confidential input은 approval/review policy를 통과한 redacted summary로만 external provider에 전달된다.
  - restricted/secret input은 external provider 호출이 차단된다.
  - external planning output은 candidate graph이며, validator를 통과하기 전에는 실행되지 않는다.
  - external planning output은 `ExecutionGraph` schema와 runtime validator를 통과해야 한다.
  - external planning 실패 시 local manager path 또는 single-loop fallback이 작동한다.
  - provider data retention, training/data-use, region, logging policy가 workspace policy와 충돌하면 external provider 호출이 차단된다.
  - provider policy 검증 결과가 `ModelRouteDecision`과 trace에 남는다.
  - external provider invocation rate, cost, latency, error가 trace에 남는다.
  - workspace/provider daily/monthly cost budget과 rate limit을 초과하면 external provider 호출이 차단되거나 fallback된다.
- External search
  - manager output에 `agent_id=external.search`가 포함되면 validator가 차단한다.
  - `ExternalSearchQuerySanitizer`는 deterministic rule, local NER, local model, workspace metadata dictionary 기반으로 실행된다.
  - sanitization/redaction을 수행하기 위해 raw prompt, raw evidence, raw tool result가 external provider로 전달되지 않는다.
  - external search query에서 고객명, 제품코드, 주문번호, 도면번호, 내부 URL, 가격, 원가, BOM, 계약 조건이 제거된다.
  - sanitizer가 customer, product code, order id, drawing id, price, cost, BOM, contract term, internal URL을 제거하지 못하면 external call이 차단된다.
  - sanitizer 실패 또는 policy deny 시 external search가 차단된다.
  - external web result는 기본 `untrusted` 또는 `mixed` trust로 들어간다.
  - external evidence에는 `authority_class`가 부여된다.
  - 공식 기관/표준기관 allowlist source는 정책에 따라 `trusted`로 승격 가능하다.
  - 내부 업무 사실은 `internal_system_of_record` evidence가 우선한다.
  - 법규/표준/인증 관련 conflict는 `official_regulation` 또는 `standard_body` authority가 우선될 수 있다.
  - verifier는 conflict 판단 시 `authority_class`, freshness, trust level, workspace policy를 함께 고려한다.
  - 외부 evidence만으로 high-risk action이 실행되지 않는다.
  - 동일 `AgentRun` 안에서 동일 sanitized query는 동일 cached result를 사용한다.
  - external search query와 provider response metadata가 trace에 남는다.
  - `external.document.fetch`는 private IP, localhost, internal domain, metadata endpoint에 접근할 수 없다.
  - redirect를 통해 private network로 이동하는 URL은 차단된다.
  - HTTP downgrade, mixed-script IDN/punycode homograph, DNS rebinding, Cookie/Authorization/internal header passthrough가 차단된다.
  - file size limit, MIME type allowlist, timeout이 적용된다.
  - fetched external document는 기본 `untrusted` 또는 `mixed`로 `EvidencePacket`에 들어간다.
- Data egress
  - external LLM/search 호출 전 `ExternalEgressPolicy`가 항상 평가된다.
  - external call은 `auto_allowed`, `trace_only`, `approval_required`, `review_queue_required`, `denied` 중 하나로 분류된다.
  - Phase 6 v1에서 review queue backend가 없으면 `review_queue_required`는 emit되지 않는다.
  - approval이 필요한 external call은 approval gate로 전환되고, review queue는 backend가 존재할 때만 사용된다.
  - raw `EvidencePacket`은 external provider에 전달되지 않는다.
  - `ExternalSafeEvidenceSummary`에 raw excerpt, internal ref, customer/product identifiers가 포함되지 않는다.
  - 외부 전송 payload는 audit 가능한 deterministic DTO로 보존된다.
  - raw provider reasoning trace는 저장하지 않는다.
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
  - external quality review output은 final artifact로 직접 사용되지 않는다.
  - external quality review suggestion에 민감 정보 또는 unsupported claim이 포함되면 폐기된다.
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
| 기존 `AgentRunSnapshot` 확장 | 차후 migration 상세에서 재검토 | additive migration은 안전하지만 approval 전용 모델에 runtime 전체 의미를 얹으면 장기적으로 상태 의미가 흐려진다. Phase A에서 shadow-write/compat projection과 cutover shape를 먼저 정하고, Phase E에서 상세 이관과 제거 시점을 결정한다. |
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
| 외부 LLM 완전 배제 | 기각 | 보안상 단순하지만 planning, report outline, quality review, 최신 공개 정보 검색에서 로컬 모델 한계가 커진다. |
| 외부 LLM을 manager 기본값으로 사용 | 기각 | 비용, provider 장애, 데이터 반출 리스크가 커진다. local-first와 policy-controlled escalation이 더 안전하다. |
| 외부 LLM에 `EvidencePacket` 직접 전달 | 기각 | raw excerpt, internal ref, 민감 정보 노출 가능성이 있다. `ExternalSafeEvidenceSummary`를 사용해야 한다. |
| 자체 웹 검색 인프라 우선 구축 | 보류 | crawler, ranking, parsing, cache, freshness 판단 운영 부담이 크다. v1에서는 SDK/API search capability가 현실적이다. |
| SDK 검색 결과를 그대로 최종 답변에 사용 | 기각 | provider ranking/citation을 그대로 신뢰하면 감사, 재현성, 신뢰도 문제가 생긴다. `ExternalSearchResult`와 `EvidencePacket`으로 normalize해야 한다. |
| external search query sanitizer 생략 | 기각 | query 자체가 데이터 반출이다. 고객명, 제품코드, 주문번호 등이 query에 포함될 수 있다. |
| Claude Code SDK를 운영 runtime search provider로 직접 사용 | 보류 | Claude Code SDK는 개발 자동화와 coding agent에 더 적합하다. 운영 external search는 Claude API/Web Search 또는 OpenAI Responses Web Search provider adapter로 둔다. |
| `external.search`를 일반 agent로 노출 | 기각 | manager가 sanitizer/egress policy를 우회해 외부 검색을 직접 호출할 위험이 있다. external search는 `search.executor` provider adapter로만 실행한다. |
| external planning output을 그대로 실행 | 기각 | 외부 provider가 execution authority를 갖게 된다. candidate graph만 생성하고 runtime validator가 검증해야 한다. |
| sanitizer를 external LLM으로 수행 | 기각 | sanitization 자체가 data egress가 된다. sanitizer는 local/pre-egress로 수행해야 한다. |
| 내부 evidence 항상 우선 | 부분 수정 | 내부 업무 사실에는 맞지만 법규/표준/인증은 official external authority가 더 우선될 수 있다. `authority_class` 기반 conflict rule을 사용한다. |
| external search result cache 생략 | 기각 | 외부 검색 결과는 비결정적이다. 감사와 재현성을 위해 normalized result와 query hash를 저장해야 한다. |
| external quality review output 직접 사용 | 기각 | 외부 output이 verifier/writer를 우회할 수 있다. suggestion으로만 사용하고 `writer.template`이 최종 산출물을 다시 생성한다. |
| Phase A에서 full hybrid contract 전체 구현 | 부분 수정 | 정본 contract는 유지하되 첫 구현은 minimal kernel, state/migration invariant, eval harness를 먼저 둔다. External DTO와 provider adapter는 실제 external path가 열리는 PR에서 구현한다. |
| `review_queue_required`를 Phase 6 v1에서 즉시 emit | 보류 | review queue backend/admin policy surface가 없으면 실행 의미가 없다. Phase 6 v1은 approval 또는 denied로 수렴하고, review queue는 Phase 7 이후 활성화한다. |
| `ExecutionGraph` domain/intent/output을 closed enum으로 고정 | 기각 | 새 domain 추가 때 DB enum migration과 prompt/cache churn이 커진다. registry-validated open string으로 검증한다. |

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
| ExecutionGraph value type | `agent_id`, `intent`, `domains`, `output_kind`는 registry-validated open string으로 두고 closed enum migration을 피한다 |
| graph rollout | `AIDOO_AI_RUNTIME_GRAPH_ENABLED=false` 기본값 |
| 외부 LLM 사용 | v1에서 완전 배제하지 않고 feature flag 뒤 policy-controlled capability로 도입 |
| 외부 LLM 역할 | 내부 데이터 processor가 아니라 planning, reasoning, quality review provider |
| 외부 원문 전송 | 내부 문서 원문, PLM row, 주문서 전문, 고객명, 제품코드, BOM, 원가, 가격, 계약 조건은 전송 금지 |
| 외부 전달 DTO | raw `EvidencePacket`이 아니라 `ExternalSafeEvidenceSummary` 사용 |
| 외부 검색 | 별도 검색 인프라 우선 구축 대신 OpenAI/Claude SDK/API search capability를 `ExternalSearchProvider`로 활용 가능 |
| 외부 검색 query | 데이터 반출로 취급하며 sanitization mandatory |
| external search result | `ExternalSearchResult`로 normalize 후 `EvidencePacket`에 편입 |
| external source trust | 기본 `untrusted` 또는 `mixed` |
| sensitivity classification | pre-routing `RequestSensitivityClassifier`와 pre-egress `PayloadSensitivityClassifier`로 나눠 수행 |
| external.search 호출 경계 | manager direct invocation 금지, `search.executor` provider adapter로만 호출 |
| external planning 권한 | final execution graph가 아니라 candidate graph 생성만 허용 |
| sanitizer 실행 위치 | external provider 호출 전 local/deterministic sanitizer 수행 |
| evidence conflict 판단 | source 위치가 아니라 `authority_class`, freshness, trust level, workspace policy, verifier confidence 기준 |
| external search cache | 동일 `AgentRun`/report generation 안에서 동일 sanitized query는 동일 cached result 사용 |
| provider data-use policy | retention/training/region/logging policy가 workspace policy와 충돌하면 provider 사용 금지 |
| external quality review | final artifact가 아니라 suggestion으로만 사용 |
| external.document.fetch | SSRF/private network/file/MIME/safe parser boundary 필수 |
| external call approval | 모든 external call 승인 강제가 아니라 policy decision에 따라 auto/trace/approval/review/deny로 분류 |
| review queue decision | Phase 6 v1에서 review queue backend가 없으면 `review_queue_required`를 emit하지 않고 approval/deny로 수렴 |
| Phase A 구현 범위 | full hybrid DTO freeze가 아니라 minimal kernel, state/migration invariant, eval harness를 먼저 구현 |
| AgentRunSnapshot cutover | Phase A에서 shadow-write/compat projection shape를 정의하고 Phase E에서 상세 이관한다 |
| resume scope | approval halt 시 resolved tool/agent allowlist를 저장하고 resume 시 scope widening을 차단한다 |
| trace ordering | `AgentTraceEvent` ordering은 UUID가 아니라 per-run monotonic sequence를 사용한다 |
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
| external planning이 local manager보다 복잡한 요청에서 더 좋은 graph를 만든다 | routing / graph success eval |
| external quality review가 template output의 누락 항목을 줄인다 | report quality eval |
| SDK/API search가 자체 infra 없이도 v1 외부 검색 요구를 충족한다 | external search relevance / citation eval |
| query sanitizer가 업무 식별자 제거에 충분하다 | leakage eval |
| external search result를 `EvidencePacket`에 normalize하면 verifier 품질이 유지된다 | groundedness / citation coverage eval |
| external provider 비용과 latency가 허용 범위 안에 있다 | cost per successful run, profile별 p95 latency |
| request/payload sensitivity classifier가 egress decision에 충분한 precision/recall을 제공한다 | leakage eval, false allow/false deny 측정 |
| `authority_class` 기반 conflict rule이 내부/외부 evidence 충돌 판단을 개선한다 | regulation/standard/vendor/internal conflict fixture |
| external search cache가 보고서 재현성을 개선한다 | repeated run consistency eval |
| provider data-use policy enforcement가 workspace별 보안 정책을 만족한다 | policy compliance test |
| external quality review를 suggestion으로만 사용해도 품질 개선 효과가 있다 | report quality eval |
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
| 기본 external LLM provider | Phase B/C provider bakeoff 이후 |
| 기본 external search provider | Phase C external search eval 이후 |
| external search cache 정책 | Phase C 이후 |
| provider별 data retention 설정 | security review 이후 |
| confidential external call approval 기본값 | workspace admin policy 설계 시 |
| external quality review 기본 활성화 여부 | Phase F eval 이후 |
| 자체 search infra 도입 여부 | SDK/API search 한계가 명확해진 이후 |
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
2. `AIDOO_AI_EXTERNAL_LLM_ENABLED=false`로 모든 external LLM 호출을 중단한다.
3. `AIDOO_AI_EXTERNAL_SEARCH_ENABLED=false`로 모든 external search 호출을 중단한다.
4. external planning path를 local manager path로 되돌린다.
5. external quality review를 비활성화하고 local verifier만 사용한다.
6. ExternalSearchProvider 장애 시 internal-only search로 fallback한다.
7. chat entrypoint를 기존 single-loop agent path로 전환한다.
8. 새 runtime trace table과 external call trace는 read-only로 보존하고 신규 write만 중단한다.
9. approval flow는 기존 approval endpoint 계약을 유지한 채 compatibility shim 또는 old snapshot path로 되돌린다.
10. egress policy 위반이 발견되면 provider key를 revoke하고 affected `AgentRun`을 audit 대상으로 표시한다.
11. 실패 원인을 eval fixture와 trace event로 정리한 뒤 단계별 재도입한다.
