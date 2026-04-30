# 최종 검토 보고서: Doowon Evidence-First Agent Runtime의 Hybrid LLM / External Search 확장안

## 0. 결론

지금까지의 대화 내용을 다시 검토한 결과, 큰 방향은 **타당**합니다. 다만 몇 가지 표현과 설계 위치는 수정해야 합니다.

최종 권장 방향은 다음입니다.

> 기존 계획의 **Evidence-First Agent Runtime**을 폐기하지 말고, 이를 **Evidence-First Hybrid Agent Runtime**으로 확장한다.
> 내부 문서, PLM, 주문서, PPT, 제품 사양 등 민감 데이터 처리는 로컬 LLM과 내부 tool gateway에서 수행한다.
> 외부 LLM은 내부 데이터 processor가 아니라 **정책적으로 통제된 planning / reasoning / quality review provider**로 사용한다.
> 웹·외부 공개 자료 검색은 v1에서 별도 검색 인프라를 직접 구축하지 않고, OpenAI / Claude 계열 SDK 또는 API의 search capability를 **ExternalSearchProvider**로 활용한다.
> 단, query sanitization, egress policy, evidence normalization, trust labeling, audit, verifier integration은 반드시 Doowon runtime이 소유해야 한다.

기존 계획은 이미 단순 multi-agent 구조가 아니라 **deterministic shortcut + graph orchestrator + evidence-first specialist runtime**을 목표로 하고 있습니다. 이 방향은 유지해야 합니다.

---

# 1. 지금까지 논의한 내용의 타당성 검토

## 1.1 타당한 판단

### 1.1.1 로컬 LLM만으로 모든 것을 처리하는 전략은 한계가 있다

기존 계획은 `Qwen/local model profile`를 canonical model로 두고, 로컬 MLX PoC checkpoint로 `mlx-community/local model profile-4bit`를 사용하는 방향을 전제합니다. 동시에 긴 context와 tool calling은 가능하지만, 큰 tool catalog와 긴 대화 이력에는 취약하다고 보고 있습니다.

이 판단은 맞습니다. 로컬 35B급 모델은 내부 데이터 처리에는 유리하지만, 다음 작업에서는 외부 manager model 또는 SDK 기반 agent/search capability가 더 효율적일 수 있습니다.

```text
- 복잡한 사용자 의도 분해
- execution graph 후보 생성
- 다중 도메인 planning
- 보고서 목차 설계
- 품질 검토
- 최신 공개 자료 검색
- 외부 법규/표준/시장 자료 확인
```

따라서 **local-first**는 맞지만, **local-only**는 장기적으로 비효율적입니다.

---

### 1.1.2 기존 계획의 core runtime은 그대로 유지해야 한다

기존 계획은 다음을 이미 잘 갖추고 있습니다.

```text
- deterministic fast path
- manager-controlled graph
- structured ExecutionGraph
- EvidencePacket
- verifier
- risk-based approval
- ModelProfile
- RuntimeProfile
- AgentRun / AgentInvocation / AgentTraceEvent
- feature flag rollout
- fallback / rollback plan
```

특히 자유로운 agent handoff가 아니라 manager가 실행 graph를 통제하고, specialist가 자기 tool allowlist와 context source 안에서만 실행되도록 한 점은 매우 중요합니다.

이 구조는 제조/PLM/내부 문서 업무처럼 보안, 감사, 재현성, 승인 흐름이 중요한 시스템에 적합합니다.

---

### 1.1.3 OpenAI / Claude SDK를 외부 검색에 활용하는 방향은 타당하다

v1에서 자체 웹 검색 인프라를 만드는 것은 과합니다. 자체 구축하려면 다음이 필요합니다.

```text
- search API
- crawler
- fetcher
- HTML cleaner
- PDF parser
- source ranking
- spam filtering
- freshness 판단
- cache
- citation extraction
- robots/rate limit 대응
- prompt injection 방어
```

반면 OpenAI Responses API는 built-in tool로 web search, file search, function calling 등을 지원합니다. ([OpenAI Platform][1])
OpenAI의 web search guide도 모델이 최신 인터넷 정보를 검색하고 citation이 있는 답변을 생성할 수 있다고 설명하며, Responses API에서 `web_search` tool을 사용할 수 있다고 설명합니다. ([OpenAI Platform][2])

Anthropic 역시 Claude API의 web search tool을 통해 실시간 웹 콘텐츠 접근과 source citation을 제공한다고 설명합니다. ([Claude 플랫폼][3])

따라서 외부 공개 자료 검색은 v1에서 SDK/API search capability에 의존하는 것이 현실적입니다.

---

## 1.2 수정이 필요한 판단

### 1.2.1 “Claude Code SDK를 검색 provider로 쓰자”는 표현은 조정해야 한다

Claude Code SDK 문서상 파일 작업, 코드 실행, 웹 검색, MCP 확장성, 권한 제어 등을 제공하는 agent harness로 설명됩니다. ([Claude API Docs][4])

하지만 운영 runtime에서 외부 웹 검색 provider로 가장 깔끔한 표현은 다음입니다.

```text
좋은 표현:
Claude API / Claude SDK의 web search capability를 ExternalSearchProvider로 사용한다.

주의할 표현:
Claude Code SDK를 운영 검색 인프라로 직접 사용한다.
```

Claude Code SDK는 다음 용도에 더 적합합니다.

```text
- 개발 자동화
- 코드베이스 분석
- 커넥터 코드 작성
- 테스트 코드 생성
- 내부 개발자 agent 구축
- CI/CD 보조 agent
```

운영 시스템의 외부 자료 검색은 **Claude Web Search API capability** 또는 **OpenAI Responses web_search**를 provider adapter로 추상화하는 편이 더 안전합니다.

---

### 1.2.2 OpenAI Agents SDK의 guardrail에 과신하면 안 된다

OpenAI Agents SDK는 agents, handoffs, guardrails를 핵심 primitive로 제공하고, tracing도 포함합니다. ([OpenAI GitHub][5])
또한 guardrails는 input/output/tool validation을 지원합니다. ([OpenAI GitHub][6])

하지만 중요한 한계가 있습니다. OpenAI Agents SDK 문서상 hosted tools, 예를 들어 `WebSearchTool`, `FileSearchTool`, `HostedMCPTool`, `CodeInterpreterTool` 등은 일반 function tool guardrail pipeline을 그대로 사용하지 않습니다. ([OpenAI GitHub][6])

따라서 Doowon runtime에서는 다음 원칙이 필요합니다.

```text
SDK guardrail에만 의존하지 않는다.
외부 검색 query sanitization은 SDK 호출 전에 Doowon runtime에서 수행한다.
외부 검색 결과 normalization도 SDK 밖에서 수행한다.
```

이 부분은 기존 계획 수정 시 반드시 반영해야 합니다.

---

### 1.2.3 OpenAI Agents SDK의 tracing도 그대로 신뢰하면 안 된다

OpenAI Agents SDK는 LLM generation, tool call, handoff, guardrail 등을 tracing한다고 설명합니다. ([OpenAI GitHub][7])

이 기능은 개발과 디버깅에는 유용하지만, Doowon의 내부 감사 로그를 대체하면 안 됩니다. 기존 계획처럼 internal trace table을 source of truth로 유지하고, 외부 tracing은 export 또는 secondary observability로만 봐야 합니다. 기존 계획도 internal trace table을 source of truth로 유지하고 Langfuse, Phoenix, MLflow, 기존 APM은 export 후보로만 둔다고 명시합니다.

---

# 2. 최종 아키텍처 방향

## 2.1 기존 계획의 명칭 변경

기존 제목:

```text
Evidence-First Agent Runtime
```

권장 제목:

```text
Evidence-First Hybrid Agent Runtime
```

이 변경은 단순 명칭 변경이 아니라, 다음을 의미합니다.

```text
기존:
Local-first runtime

수정:
Local-first + policy-controlled external reasoning/search runtime
```

---

## 2.2 최종 구조

```text
[User Request]
  ↓
[Fast Path Router]
  ├─ deterministic shortcut
  └─ manager graph path
        ↓
[Runtime Profile Selector]
        ↓
[Data Sensitivity Classifier]
        ↓
[ModelRouter / SearchRouter]
        ├─ Local Model Profile
        ├─ External OpenAI Profile
        ├─ External Claude Profile
        ├─ Internal RAG Search
        └─ External Search Provider
        ↓
[ExecutionGraph]
        ↓
[Specialist Invocation]
        ↓
[EvidencePacket]
        ↓
[Verifier / Writer / Approval]
        ↓
[Final Answer / Report / Artifact]
```

핵심은 다음입니다.

```text
Doowon runtime owns:
  - policy
  - evidence
  - approval
  - audit
  - verifier
  - trace
  - model routing
  - external egress control

External providers provide:
  - reasoning capability
  - web/public search capability
  - optional quality review
```

---

# 3. 역할 분리

## 3.1 Local LLM의 역할

로컬 LLM은 내부 데이터 접근이 필요한 작업을 담당해야 합니다.

```text
- 내부 문서 RAG
- 주문서/계약서/보고서 검색 및 요약
- PLM DB 질의 해석
- PPT 제품 사양 비교
- 내부 기준 문서 기반 보고서 작성
- 사내 용어 해석
- 내부 evidence 생성
- sensitive draft generation
```

로컬 LLM은 내부 데이터 processor입니다.

---

## 3.2 External LLM의 역할

외부 LLM은 내부 데이터 processor가 아니라 policy-controlled reasoning provider입니다.

```text
- 복잡한 요청 decomposition
- execution graph 후보 생성
- report outline
- redacted quality review
- clarification question 생성
- 다중 도메인 reasoning 보조
- 최신 공개 정보 기반 보조 판단
```

외부 LLM에 보내면 안 되는 것:

```text
- 내부 문서 원문
- EvidencePacket raw item
- PLM row
- 주문서 전문
- 고객명
- 제품코드
- BOM
- 원가/가격
- 계약 조건
- 내부 시스템 URL
```

외부 LLM에 보낼 수 있는 것:

```text
- sanitized user intent
- available agent 목록
- public tool description
- domain metadata
- ExternalSafeEvidenceSummary
- redacted draft
- evidence coverage summary
- missing intents
```

---

## 3.3 External Search Provider의 역할

외부 검색은 내부 RAG의 대체물이 아닙니다. 공개 자료 확인용 보조 provider입니다.

```text
- 최신 기술 동향
- 공개 법규/인증/표준
- 공급사 공개 사양
- 시장 정보
- 경쟁사 공개 자료
- 일반 기술 배경
```

OpenAI web search는 Responses API에서 사용할 수 있고, non-reasoning search와 reasoning model 기반 agentic search 형태를 모두 설명합니다. ([OpenAI Platform][2])
Claude API도 web search tool을 통해 최신 웹 콘텐츠와 citation을 제공한다고 설명합니다. ([Claude 플랫폼][3])

따라서 v1에서는 다음 방식이 좋습니다.

```text
ExternalSearchProvider
  ├─ OpenAIResponsesWebSearchProvider
  ├─ ClaudeWebSearchProvider
  └─ FutureProvider
```

---

# 4. 기존 계획에 추가해야 할 핵심 Runtime Primitive

## 4.1 DataSensitivity

```ts
type DataSensitivity =
  | "public"
  | "internal"
  | "confidential"
  | "restricted"
  | "secret";
```

권장 정책:

| 등급           |      외부 LLM |       외부 검색 | 원문 전송 |
| ------------ | ----------: | ----------: | ----: |
| public       |          허용 |          허용 |    가능 |
| internal     |       제한 허용 |       제한 허용 |    금지 |
| confidential | 승인 기반 제한 허용 | 승인 기반 제한 허용 |    금지 |
| restricted   |       기본 금지 |       기본 금지 |    금지 |
| secret       |          금지 |          금지 |    금지 |

---

## 4.2 ExternalEgressPolicy

```ts
type ExternalEgressPolicy = {
  policy_id: string
  workspace_id: string
  domain?: string
  sensitivity: DataSensitivity

  allow_external_llm: boolean
  allow_external_search: boolean

  allow_raw_user_prompt: boolean
  allow_raw_evidence: boolean
  allow_redacted_summary: boolean

  require_approval: boolean
  require_query_sanitization: boolean
  require_prompt_redaction: boolean

  allowed_providers: string[]
  blocked_domains?: string[]
  allowed_domains?: string[]

  retention_policy?: string
}
```

이 정책은 외부 LLM과 외부 검색 모두에 적용되어야 합니다.

---

## 4.3 ModelRouter

```ts
type ModelRouteDecision = {
  selected_profile: string
  selected_provider: "local" | "external"
  selected_provider_name?: "qwen" | "openai" | "claude" | "other"

  runtime_profile: RuntimeProfile
  reason: string

  sensitivity: DataSensitivity
  egress_policy_id?: string

  redaction_required: boolean
  approval_required: boolean
  fallback_profile: string
}
```

ModelRouter는 다음 기준으로 local/external을 선택합니다.

```text
- task complexity
- reasoning depth
- data sensitivity
- egress policy
- user/workspace setting
- latency budget
- cost budget
- provider availability
- fallback policy
```

---

## 4.4 ExternalSafeEvidenceSummary

기존 `EvidencePacket`은 내부 전용입니다. 외부 provider에는 직접 전달하면 안 됩니다.

```ts
type ExternalSafeEvidenceSummary = {
  task_intent: string
  domains: string[]

  evidence_coverage: {
    intents_covered: string[]
    intents_missed: string[]
  }

  claim_summaries: Array<{
    claim_id: string
    claim_type: string
    support_status: "supported" | "partial" | "unsupported" | "contradicted"
    confidence: number
    redacted_summary: string
  }>

  conflicts?: Array<{
    conflict_type: string
    redacted_description: string
    severity: "low" | "medium" | "high"
  }>

  missing_requirements?: string[]
  omitted_sensitive_fields?: string[]
}
```

금지:

```text
- raw excerpt
- internal resource ref
- customer identifier
- product code
- order id
- PLM row
- BOM/cost/price
- contract terms
```

---

## 4.5 ExternalSearchProvider

```ts
type ExternalSearchProvider =
  | "openai"
  | "claude"
  | "other";
```

OpenAI / Claude SDK 또는 API search capability는 이 boundary 뒤에 둡니다.

---

## 4.6 SanitizedExternalSearchQuery

외부 검색 query도 데이터 반출입니다.

```ts
type SanitizedExternalSearchQuery = {
  original_query_ref: string
  sanitized_query: string

  removed_entities: Array<{
    type:
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
    replacement: string
  }>

  sensitivity_before: DataSensitivity
  sensitivity_after: DataSensitivity

  external_search_allowed: boolean
  policy_decision_reason: string
}
```

예:

```text
원본:
A고객의 DX-2400B 주문서 기준으로 유럽 CE 인증 리스크를 검색해줘.

금지 query:
A고객 DX-2400B 주문서 유럽 CE 인증 리스크

허용 query:
industrial electronic component CE certification EU regulatory requirements recent changes
```

---

## 4.7 ExternalSearchResult

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
}
```

---

# 5. EvidencePacket 수정 방향

기존 계획의 EvidencePacket은 유지하되 external source를 표현할 수 있게 확장합니다.

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
    external_search_provider?: string
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
  }>

  coverage: {
    intents_covered: string[]
    intents_missed: string[]
  }
}
```

운영 규칙:

```text
- 내부 ACL을 통과한 내부 evidence는 trusted 가능
- 외부 웹 결과는 기본 untrusted 또는 mixed
- 공식 기관/표준기관 allowlist는 trusted 승격 가능
- vendor page는 mixed
- news/blog/forum은 untrusted
- 내부 evidence와 외부 evidence가 충돌하면 내부 evidence 우선
- 외부 evidence만으로 high-risk action 실행 금지
```

---

# 6. Search Executor 수정

기존 계획의 `search.executor`는 내부 RAG/domain service thin adapter로 시작합니다.
이를 다음처럼 확장합니다.

```text
search.executor
  ├─ internal.rag.search
  ├─ internal.domain.search
  ├─ external.web.openai
  ├─ external.web.claude
  └─ external.document.fetch
```

실행 흐름:

```text
SearchPlan
  ↓
Internal Search
  ↓
Internal EvidencePacket candidate
  ↓
External search need 판단
  ↓
ExternalSearchQuerySanitizer
  ↓
ExternalEgressPolicy
  ↓
ExternalSearchProvider
  ↓
ExternalSearchResult normalization
  ↓
EvidencePacket merge
  ↓
Verifier / Writer
```

외부 검색 허용 조건:

```text
- 사용자가 최신 공개 정보를 요청
- 법규/표준/인증 공개 정보 필요
- 공급사 공개 사양 필요
- 내부 evidence만으로 배경 설명이 부족
- workspace policy 허용
- query sanitization 성공
```

외부 검색 금지 조건:

```text
- query sanitization 실패
- restricted/secret data 기반 query
- 고객명/제품코드 제거 불가
- workspace policy가 external search 금지
- 사용자가 no-external-search 명시
- provider budget/latency 초과
```

---

# 7. OpenAI SDK / Claude SDK의 위치

## 7.1 OpenAI Responses API

OpenAI Responses API는 built-in tools로 web search, file search, function calling 등을 사용할 수 있습니다. ([OpenAI Platform][1])
OpenAI web search는 최신 인터넷 정보 접근과 source citation을 지원하며, Responses API에서 `web_search` tool을 사용할 수 있습니다. ([OpenAI Platform][2])

Doowon에서의 위치:

```text
OpenAI Responses API
  = ExternalSearchProvider 후보
  = ExternalPlanningProvider 후보
  = ExternalQualityReviewProvider 후보
```

단, OpenAI SDK가 Doowon runtime contract를 대체하지 않습니다.

---

## 7.2 OpenAI Agents SDK

OpenAI Agents SDK는 agents, handoffs, guardrails, tracing을 지원합니다. ([OpenAI GitHub][5])
Handoffs는 specialist agent에 위임하는 구조를 지원하지만, handoff는 LLM이 호출하는 tool처럼 표현됩니다. ([OpenAI GitHub][8])

Doowon에서의 위치:

```text
사용 가능:
- external planning prototype
- external supervisor prototype
- quality review agent prototype
- tracing 참고
- guardrail pattern 참고

사용 주의:
- Doowon runtime core로 직접 채택 금지
- free handoff 구조로 확장 금지
- hosted web search tool guardrail에 과신 금지
```

기존 계획의 manager-controlled graph 원칙을 유지해야 합니다.

---

## 7.3 Claude API / SDK

Claude API web search tool은 최신 웹 콘텐츠 접근과 citation을 지원합니다. ([Claude 플랫폼][3])

Doowon에서의 위치:

```text
Claude API / SDK
  = ExternalSearchProvider 후보
  = ExternalQualityReviewProvider 후보
  = 긴 공개 문서 요약 후보
```

---

## 7.4 Claude Code SDK

Claude Code SDK는 custom AI agents를 만들기 위한 SDK이며, file operations, code execution, web search, MCP extensibility, permission control 등을 제공한다고 설명됩니다. ([Claude API Docs][4])

Doowon에서의 위치:

```text
권장:
- 개발 자동화
- 코드베이스 분석
- 커넥터 작성
- 테스트 자동화
- migration script 초안
- developer assistant

비권장:
- 운영 runtime의 기본 external search provider
- 내부 DB/PLM 직접 실행 agent
- 사용자 요청 기반 임의 코드 실행
```

즉, Claude Code SDK는 **개발 생산성 도구**로 우선 보고, 운영 runtime의 외부 검색은 Claude API Web Search 또는 OpenAI Responses Web Search provider adapter로 두는 것이 좋습니다.

---

# 8. 기존 문서 수정 가이드

## 8.1 Context 섹션에 추가할 문장

```markdown
Doowon AI runtime은 local-first를 기본 원칙으로 유지하지만 external LLM과 external search를 완전히 배제하지 않는다. 내부 데이터 원문 처리, PLM row 해석, 주문서/문서 전문 분석, 제품 사양 비교는 local model과 workspace-scoped tool gateway 안에서 수행한다.

반면 복잡한 planning, execution graph candidate generation, report outline, redacted quality review, clarification generation, 외부 공개 자료 검색은 `DataSensitivity`, `ExternalEgressPolicy`, `ModelProfile`, `RuntimeProfile`, `ToolSecurityPolicy`를 통과한 경우 external provider profile을 사용할 수 있다.

External provider는 runtime core가 아니라 policy-controlled provider adapter다. `EvidencePacket`은 내부 runtime contract로 유지하며 외부 provider에 직접 전달하지 않는다. 외부 reasoning에는 `ExternalSafeEvidenceSummary`를 사용하고, 외부 검색에는 sanitized query만 사용한다. 외부 검색 결과는 `ExternalSearchResult`로 정규화한 뒤 trust level, provenance, provider metadata를 포함해 `EvidencePacket`에 편입한다.
```

---

## 8.2 Architecture / Principles에 추가할 섹션

```markdown
### External LLM usage is policy-controlled, not prompt-controlled

Doowon runtime은 local-first를 기본 원칙으로 유지하되, external LLM을 완전히 배제하지 않는다. 내부 데이터 원문 접근, PLM row 해석, 주문서/문서 전문 처리, 제품 사양 비교는 local model과 workspace-scoped tool gateway 안에서 수행한다.

반면 복잡한 planning, execution graph candidate generation, report outline, redacted quality review, clarification generation은 데이터 민감도와 egress policy를 통과한 경우 external LLM profile을 사용할 수 있다.

External LLM은 내부 데이터 processor가 아니라 policy-controlled reasoning provider다. `EvidencePacket`은 외부 provider로 직접 전달하지 않으며, 필요한 경우 `ExternalSafeEvidenceSummary`로 축약, 익명화, 최소화한 뒤 전송한다.

External LLM 사용 여부는 사용자 prompt가 아니라 runtime policy, workspace setting, data sensitivity, provider availability, cost/latency budget, approval policy가 결정한다.
```

---

## 8.3 External Search Provider Boundary 추가

```markdown
### External Search Provider Boundary

Doowon runtime은 외부 웹/공개 자료 검색을 자체 crawler 또는 별도 search infrastructure로 먼저 구축하지 않는다. v1에서는 OpenAI/Claude 등 external provider SDK 또는 API의 web/search capability를 `ExternalSearchProvider`로 사용할 수 있다.

단, external provider는 search infrastructure일 뿐 runtime contract의 source of truth가 아니다. Doowon runtime은 다음 책임을 계속 소유한다.

- external search eligibility decision
- query sanitization
- data egress policy
- provider routing
- result normalization
- evidence trust labeling
- citation preservation
- cache and audit log
- verifier integration

외부 검색 query는 데이터 반출로 취급한다. 고객명, 제품코드, 주문번호, 도면번호, 내부 URL, 가격, 원가, BOM, 계약 조건은 external search query에 포함하지 않는다.

External search result는 기본적으로 untrusted 또는 mixed trust level로 EvidencePacket에 들어간다. 내부 evidence와 충돌하는 경우 내부 evidence가 우선하며, 외부 자료는 보조 근거로만 사용한다.
```

---

## 8.4 RuntimeProfile 수정

기존:

```text
interactive_read
grounded_report
long_doc
high_risk_action
```

수정:

```ts
type RuntimeProfile =
  | "interactive_read"
  | "grounded_report"
  | "long_doc"
  | "high_risk_action"
  | "external_planning"
  | "external_reasoning"
  | "external_quality_review"
  | "external_search";
```

---

## 8.5 LLM Gateway Boundary 수정

기존 방향:

```text
Doowon Agent Runtime
  -> ModelProfile / RuntimeProfile
  -> LLM Gateway boundary
       -> SGLang
       -> vLLM
       -> External Provider
```

수정 방향:

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
            -> Claude web_search
```

---

## 8.6 Agent Set v1에 추가할 descriptor

```text
external.planning
  - sanitized user intent, available agent list, domain metadata를 기반으로 execution graph candidate 또는 report outline을 만든다.
  - raw internal evidence를 보지 않는다.
  - manager output validator를 반드시 통과해야 한다.

external.quality_review
  - redacted report draft, ExternalSafeEvidenceSummary, missing intent summary를 기반으로 품질 검토를 수행한다.
  - 내부 ref, raw excerpt, PLM row를 보지 않는다.
  - verifier를 대체하지 않는다.

external.search
  - sanitized query를 기반으로 OpenAI/Claude SDK/API search capability를 호출한다.
  - raw user prompt를 직접 받지 않는다.
  - ExternalSearchResult로 normalize한 결과만 반환한다.
  - internal RAG를 대체하지 않는다.
```

---

# 9. Implementation Phases 수정안

## Phase A 추가

```text
- DataSensitivity enum 추가
- ExternalEgressPolicy contract 추가
- ModelRouter contract 추가
- ExternalSafeEvidenceSummary DTO 추가
- ExternalSearchRequest DTO 추가
- SanitizedExternalSearchQuery DTO 추가
- ExternalSearchResult DTO 추가
- ExternalCallProposal DTO 추가
- ModelProfile에 provider/search capability 필드 추가
- SearchProfile에 external search policy 필드 추가
- trace event taxonomy에 external routing, egress decision, query sanitization, provider call, external result normalization 추가
```

---

## Phase B 추가

```text
- manager graph path에서 external planning 후보 평가
- external planning은 feature flag 뒤에서 시작
- external planning output도 ExecutionGraph validator 통과
- external planning 실패 시 local manager path 또는 single-loop fallback
- external call cost/latency/error trace 기록
```

Feature flags:

```text
AIDOO_AI_EXTERNAL_LLM_ENABLED=false
AIDOO_AI_EXTERNAL_PLANNING_ENABLED=false
AIDOO_AI_EXTERNAL_REASONING_ENABLED=false
AIDOO_AI_EXTERNAL_QUALITY_REVIEW_ENABLED=false
```

---

## Phase C 추가

```text
- ExternalSearchProvider boundary 추가
- OpenAI / Claude web search provider adapter 후보 추가
- ExternalSearchQuerySanitizer 구현
- ExternalSearchResult normalization 구현
- EvidencePacket에 external source kind, trust_level, provider, retrieved_at, published_at 반영
- internal evidence와 external evidence merge policy 구현
- external search provider failure fallback 구현
```

Feature flags:

```text
AIDOO_AI_EXTERNAL_SEARCH_ENABLED=false
AIDOO_AI_EXTERNAL_SEARCH_PROVIDER=openai
```

---

## Phase D 추가

```text
- 외부 evidence trust level을 verifier 판단에 반영
- external-only evidence에 confidence cap 적용
- internal/external evidence conflict 감지 rule 추가
- external search retry 최대 1회 제한
- external evidence 부족 시 internal-only partial answer 또는 사용자 질문으로 전환
```

---

## Phase E 추가

```text
- ExternalCallProposal을 approval flow에 연결
- confidential context에서 external call 시 approval/review queue 적용
- external call resume은 same AgentRun, new AgentInvocation 원칙 유지
- approval resume 시 payload 변경 여부 idempotency check 수행
```

---

## Phase F 추가

```text
- external quality review 후보 추가
- writer.template output을 외부 provider에 보낼 경우 redacted draft만 허용
- external quality review는 verifier를 대체하지 않음
- redacted report draft leakage eval 추가
- external search citation quality eval 추가
- external provider cost/latency/quality tradeoff 측정
```

---

# 10. Verification 추가 항목

## 10.1 External LLM routing

```text
- raw internal document가 external LLM으로 전달되지 않는다.
- confidential input은 redacted summary로만 external provider에 전달된다.
- restricted/secret input은 external provider 호출이 차단된다.
- external planning output은 ExecutionGraph schema와 runtime validator를 통과해야 한다.
- external planning 실패 시 local manager path 또는 single-loop fallback이 작동한다.
- external LLM provider 장애 시 fallback policy가 작동한다.
- external reasoning invocation rate와 cost가 trace에 남는다.
```

---

## 10.2 External search

```text
- external search query에서 고객명, 제품코드, 주문번호, 도면번호, 내부 URL, 가격, 원가, BOM이 제거된다.
- sanitizer 실패 시 external search가 차단된다.
- external search result는 ExternalSearchResult로 normalize된다.
- external search result는 EvidencePacket에서 source_kind와 trust_level을 가진다.
- external web result는 기본 untrusted 또는 mixed trust로 들어간다.
- 공식 기관 allowlist source는 trusted로 승격 가능하다.
- 내부 evidence와 외부 evidence가 충돌하면 내부 evidence를 우선한다.
- 외부 evidence만으로 high-risk action이 실행되지 않는다.
- external search provider 장애 시 partial answer 또는 internal-only answer로 fallback한다.
- external search query와 provider response metadata가 trace에 남는다.
```

---

## 10.3 Data egress

```text
- external LLM 호출 전 ExternalEgressPolicy가 항상 평가된다.
- external search 호출 전 ExternalEgressPolicy가 항상 평가된다.
- approval이 필요한 external call은 review queue 또는 approval gate로 전환된다.
- raw EvidencePacket이 external provider에 전달되지 않는다.
- ExternalSafeEvidenceSummary에 raw excerpt, internal ref, customer/product identifiers가 포함되지 않는다.
- 외부 전송 payload는 audit 가능한 deterministic DTO로 보존된다.
- raw provider reasoning trace는 저장하지 않는다.
```

---

# 11. Alternatives Considered에 추가할 항목

| 대안                                                 | 결론 | 이유                                                                                                                                    |
| -------------------------------------------------- | -- | ------------------------------------------------------------------------------------------------------------------------------------- |
| 외부 LLM 완전 배제                                       | 기각 | 보안상 안전하지만 planning, report outline, quality review, 최신 공개 정보 검색에서 로컬 모델 한계가 커진다.                                                      |
| 외부 LLM을 manager 기본값으로 사용                           | 기각 | 비용, provider 장애, 데이터 반출 리스크가 커진다. local-first와 policy-controlled escalation이 더 안전하다.                                                  |
| 외부 LLM에 EvidencePacket 직접 전달                       | 기각 | raw excerpt, internal ref, 민감 정보 노출 가능성이 있다. ExternalSafeEvidenceSummary를 사용해야 한다.                                                    |
| 자체 웹 검색 인프라 우선 구축                                  | 보류 | crawler, ranking, parsing, cache, freshness 판단 운영 부담이 크다. v1에서는 SDK/API search capability가 현실적이다.                                     |
| SDK 검색 결과를 그대로 최종 답변에 사용                           | 기각 | provider ranking/citation을 그대로 신뢰하면 감사, 재현성, 신뢰도 문제가 생긴다. ExternalSearchResult와 EvidencePacket으로 normalize해야 한다.                      |
| external search query sanitizer 생략                 | 기각 | query 자체가 데이터 반출이다. 고객명, 제품코드, 주문번호 등이 query에 포함될 수 있다.                                                                               |
| Claude Code SDK를 운영 runtime search provider로 직접 사용 | 보류 | Claude Code SDK는 개발 자동화와 coding agent에 더 적합하다. 운영 external search는 Claude API/Web Search 또는 OpenAI Responses Web Search로 추상화하는 편이 낫다. |

---

# 12. Decision Log에 추가할 항목

## 확정 결정 추가

| 항목                            | 결정                                                                                        |
| ----------------------------- | ----------------------------------------------------------------------------------------- |
| 외부 LLM 사용                     | v1에서 완전 배제하지 않고 feature flag 뒤에서 policy-controlled capability로 도입                         |
| 외부 LLM 역할                     | 내부 데이터 processor가 아니라 planning, reasoning, quality review provider                        |
| 외부 원문 전송                      | 내부 문서 원문, PLM row, 주문서 전문, 고객명, 제품코드, BOM, 원가, 가격, 계약 조건은 전송 금지                           |
| EvidencePacket 외부 전달          | 금지                                                                                        |
| 외부 전달 DTO                     | ExternalSafeEvidenceSummary 사용                                                            |
| 외부 검색                         | 별도 검색 인프라 우선 구축 대신 OpenAI/Claude SDK/API search capability를 ExternalSearchProvider로 활용 가능 |
| 외부 검색 query                   | 데이터 반출로 취급                                                                                |
| query sanitization            | mandatory                                                                                 |
| external search result        | ExternalSearchResult로 normalize 후 EvidencePacket에 편입                                      |
| external source trust         | 기본 untrusted 또는 mixed                                                                     |
| internal vs external conflict | 내부 evidence 우선                                                                            |
| provider SDK/API              | runtime contract가 아니라 adapter                                                             |
| 외부 호출 승인                      | ExternalCallProposal을 approval/review queue에 연결                                           |

---

## 검증 전 가설 추가

| 항목                                                                    | 검증 방식                                     |
| --------------------------------------------------------------------- | ----------------------------------------- |
| external planning이 local manager보다 복잡한 요청에서 더 좋은 graph를 만든다           | routing / graph success eval              |
| external quality review가 template output의 누락 항목을 줄인다                  | report quality eval                       |
| SDK/API search가 자체 infra 없이도 v1 외부 검색 요구를 충족한다                        | external search relevance / citation eval |
| query sanitizer가 업무 식별자 제거에 충분하다                                      | leakage eval                              |
| external search result를 EvidencePacket에 normalize하면 verifier 품질이 유지된다 | groundedness / citation coverage eval     |
| external provider 비용이 허용 범위 안에 있다                                     | cost per successful run                   |
| external provider latency가 UX를 해치지 않는다                                | profile별 p95 latency                      |

---

## 차후 결정 추가

| 항목                                      | 결정 시점                           |
| --------------------------------------- | ------------------------------- |
| 기본 external LLM provider                | Phase B/C provider bakeoff 이후   |
| 기본 external search provider             | Phase C external search eval 이후 |
| external search cache 정책                | Phase C 이후                      |
| provider별 data retention 설정             | security review 이후              |
| confidential external call approval 기본값 | workspace admin policy 설계 시     |
| external quality review 기본 활성화 여부       | Phase F eval 이후                 |
| 자체 search infra 도입 여부                   | SDK/API search 한계가 명확해진 이후      |

---

# 13. Rollback Plan 수정

```text
1. AIDOO_AI_EXTERNAL_LLM_ENABLED=false로 모든 external LLM 호출을 중단한다.
2. AIDOO_AI_EXTERNAL_SEARCH_ENABLED=false로 모든 external search 호출을 중단한다.
3. external planning path를 local manager path로 되돌린다.
4. external quality review를 비활성화하고 local verifier만 사용한다.
5. ExternalSearchProvider 장애 시 internal-only search로 fallback한다.
6. external call trace와 ExternalCallProposal은 read-only로 보존한다.
7. egress policy 위반이 발견되면 provider key를 revoke하고 affected AgentRun을 audit 대상으로 표시한다.
```

---

# 14. 최종 권장안

최종적으로 기존 계획은 다음 구조로 수정하는 것이 가장 좋습니다.

```text
Evidence-First Hybrid Agent Runtime

Core Runtime:
  - deterministic fast path
  - manager-controlled graph
  - structured ExecutionGraph
  - EvidencePacket
  - VerifierResult
  - writer.template
  - risk-based approval
  - WriteProposal / ApprovalPreview
  - AgentRun / AgentInvocation / AgentTraceEvent

Local Processing:
  - local model profile
  - local RAG
  - PLM DB query
  - internal docs
  - PPT/document comparison
  - sensitive report drafting

External Reasoning:
  - OpenAI / Claude provider profile
  - planning
  - reasoning over redacted summary
  - quality review
  - report outline
  - clarification generation

External Search:
  - OpenAI / Claude SDK or API search capability
  - sanitized query only
  - ExternalSearchResult normalization
  - EvidencePacket merge
  - trust labeling
  - verifier integration

Governance:
  - DataSensitivity
  - ExternalEgressPolicy
  - ToolSecurityPolicy
  - ModelRouter
  - ExternalCallProposal
  - audit trace
  - approval / review queue
```

---

# 15. 최종 보고 문장

기존 계획을 수정할 때 다음 문장을 핵심 방향으로 삼으면 됩니다.

> Doowon AI runtime은 local-first를 기본 원칙으로 유지하되, external LLM과 external search를 완전히 배제하지 않는다. 내부 데이터 원문 처리, PLM row 해석, 주문서/문서 전문 분석, 제품 사양 비교는 local model과 workspace-scoped tool gateway 안에서 수행한다. 반면 복잡한 planning, execution graph candidate generation, report outline, redacted quality review, clarification generation, 외부 공개 자료 검색은 `DataSensitivity`, `ExternalEgressPolicy`, `ModelProfile`, `RuntimeProfile`, `ToolSecurityPolicy`를 통과한 경우 external provider profile을 사용할 수 있다.
>
> External provider는 runtime core가 아니라 policy-controlled provider adapter다. `EvidencePacket`은 내부 runtime contract로 유지하며 외부 provider에 직접 전달하지 않는다. 외부 reasoning에는 `ExternalSafeEvidenceSummary`를 사용하고, 외부 검색에는 sanitized query만 사용한다. 외부 검색 결과는 `ExternalSearchResult`로 정규화한 뒤 trust level, provenance, provider metadata를 포함해 `EvidencePacket`에 편입한다. 최종 답변과 보고서는 항상 verifier, writer, approval policy를 통과해야 한다.

---

# 16. 최종 판단

기존 계획은 기술적으로 매우 좋은 기반입니다. 하지만 기존 계획은 로컬 LLM 중심 가정이 강하기 때문에, 최종 제품 목표가 “보안적으로 안전한 범위 내에서 외부 API를 활용”하는 것이라면 반드시 보완해야 합니다.

따라서 최종 결정은 다음입니다.

```text
기존 계획을 폐기하지 않는다.
기존 계획을 Evidence-First Hybrid Agent Runtime으로 확장한다.
외부 LLM은 reasoning provider로 제한한다.
외부 검색은 SDK/API 기반 ExternalSearchProvider로 도입한다.
query, prompt, evidence는 모두 egress policy와 sanitizer를 통과시킨다.
EvidencePacket은 내부 전용으로 유지한다.
외부 결과는 trust-labeled evidence로 정규화한다.
```

이 방식이 보안, 개발 속도, 운영 현실성, 모델 교체성, 향후 확장성을 모두 고려했을 때 가장 균형 잡힌 수정안입니다.

[1]: https://platform.openai.com/docs/api-reference/responses/retrieve?utm_source=chatgpt.com "Responses | OpenAI API Reference"
[2]: https://platform.openai.com/docs/guides/tools-web-search?api-mode=responses&utm_source=chatgpt.com "Web search | OpenAI API"
[3]: https://platform.claude.com/docs/en/agents-and-tools/tool-use/web-search-tool?utm_source=chatgpt.com "Web search tool - Claude API Docs"
[4]: https://docs.anthropic.com/en/docs/claude-code/sdk?utm_source=chatgpt.com "Overview - Anthropic"
[5]: https://openai.github.io/openai-agents-python/?utm_source=chatgpt.com "OpenAI Agents SDK"
[6]: https://openai.github.io/openai-agents-python/guardrails/?utm_source=chatgpt.com "Guardrails - OpenAI Agents SDK"
[7]: https://openai.github.io/openai-agents-python/tracing/?utm_source=chatgpt.com "Tracing - OpenAI Agents SDK"
[8]: https://openai.github.io/openai-agents-python/handoffs/?utm_source=chatgpt.com "Handoffs - OpenAI Agents SDK"
