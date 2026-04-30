# Evidence-First Hybrid Agent Runtime

> 문서 성격: Doowon AI runtime 재설계를 위한 실행 설계 문서.  
> 참고 연구 문서: [`01-agentic-harness-engineering-report.md`](../docs/planning/01-agentic-harness-engineering-report.md)
> 목표: 교체 가능한 AI manager adapter와 local model profile 기반 독립 internal agent runtime을 결합해, 외부 manager model의 계획/감시 능력과 내부 local model의 데이터 경계를 함께 쓰는 agent 운영 구조를 만든다. 첫 manager adapter만 OpenAI Agents SDK를 사용한다.

## Context

현재 Doowon AI 플랫폼은 MCP-shaped capability registry, workspace-scoped tool gateway, RAG provider, approval flow, streaming envelope를 이미 갖고 있다. 다만 agent 실행 모델은 아직 단일 agent loop 중심이다. 이 구조는 단기 구현에는 빠르지만, 다음 요구가 커질수록 유지보수 비용이 높아진다.

- v1 내부 agent 모델은 `ModelProfile`/환경 설정에서 선택한다. 서비스명, 패키지명, agent id에는 특정 모델명(Qwen/Gemma/DeepSeek/OpenAI/Claude)을 박지 않는다.
- 로컬 MLX 개발/PoC checkpoint는 환경 설정으로 주입하며, 문서와 코드의 runtime 경계는 `configured local model profile`로만 표현한다.
- configured local model profile는 긴 context와 tool calling을 지원할 수 있지만, 큰 tool catalog와 긴 대화 이력에 취약할 수 있다.
- PMS, Meeting, Docs, Planner, RAG 같은 도메인 컨텍스트가 계속 늘어난다.
- 추후 LLM 모델이나 serving stack이 바뀌어도 agent contract와 tool/context boundary는 유지되어야 한다.
- 사용자 정의 템플릿, batch 작업, ambient/event-driven 작업까지 확장하려면 실행 trace와 approval policy가 agent 단위로 남아야 한다.

따라서 목표는 "모든 요청을 multi-agent로 비싸게 실행"하는 것이 아니라, **deterministic shortcut + 교체 가능한 AI manager adapter + evidence-first local model internal agent runtime**을 만드는 것이다.

Doowon AI runtime은 local-first 데이터 처리 원칙을 유지하지만, 복잡한 계획/감시/리뷰에는 external manager model을 적극 사용한다. 내부 문서 원문, PLM row, 주문서/문서 전문, 제품 사양 비교, sensitive draft generation은 local model과 workspace-scoped tool gateway 안에서 처리한다.

반면 요구 분석, 작업 계획, internal agent 지시, 결과 리뷰, gap 판단, clarification generation은 AI manager adapter path를 우선 사용한다. MVP 첫 adapter는 OpenAI Agents SDK지만, external provider는 내부 데이터 processor가 아니라 교체 가능한 manager runtime이다. Claude Agent SDK는 MCP-heavy 대안 spike 후보로 남기되, Phase 6 MVP 기본 runtime에는 포함하지 않는다.

`EvidencePacket`은 내부 runtime contract로 유지하며 external manager에 직접 전달하지 않는다. 외부 manager에는 `LocalAgentResult`, redacted evidence summary, coverage/gap summary, artifact reference만 전달한다. 외부 검색이 필요한 경우는 후속 단계에서 `ExternalSearchResult`로 정규화한 뒤 trust level, provenance, provider metadata를 포함해 `EvidencePacket`에 편입한다.

이 문서는 별도 검토에서 채택한 기술 항목을 반영한 정본 계획이다. 검토 로그 원문과 내부 메타데이터는 실행 기준으로 취급하지 않는다.

## Architecture / Principles

### 1. Deterministic shortcut first

모든 요청을 LLM manager가 먼저 분해하지 않는다. 다음 경우는 manager decomposition 없이 바로 fast path로 보낸다.

- conversation scope가 명확한 경우. 예: meeting-scoped conversation.
- `allowed_app_ids`가 단일 도메인으로 좁혀진 경우.
- 명확한 single-domain read intent가 keyword/rule로 판정되는 경우.
- 사용자가 text-only 또는 no-tool scope를 명시한 경우.

복잡하거나 애매한 요청만 AI manager path로 올린다. 이때도 요구 분석, specialist 선택, success criteria는 한 번의 manager planning step에서 먼저 받는다.

### 2. AI manager adapter, not free handoff

에이전트가 서로 자유롭게 위임하는 구조는 루프, 비용, 디버깅 리스크가 크다. Doowon v1 MVP는 AI manager adapter가 전체 작업의 최종 책임을 가진다.

- Manager는 `run_local_specialist` delegate tool을 호출해 domain/RAG/tool 작업을 지시한다.
- PMS/Planner/Docs internal agent는 OpenAI SDK Agent/handoff가 아니라 `domains.ai.internal_agents` 아래에서 실행된다.
- Internal agent는 자기 tool allowlist와 context source 안에서만 실행된다.
- Internal agent는 raw internal data가 아니라 `LocalAgentResult`를 반환한다.
- MVP domain action surface는 의도적으로 좁힌다. PMS는 approval-gated issue create/update/comment/delete, Planner는 approval-gated event create/update/delete까지 허용하고, Docs는 AI read-only(`docs.list_hub/get_item/list_pages/read_page`)로 둔다.
- Manager는 `LocalAgentResult`를 리뷰하고 재작업, 사용자 질문, partial answer, final answer 중 하나를 선택한다.
- Recovery는 bounded loop로 제한하며 기본 최대 3 review cycle을 넘지 않는다.

### 3. External manager usage is policy-controlled, not data processing

Doowon runtime은 내부 데이터 처리는 local-first로 유지하되, 외부 manager model을 manager로 사용한다. 내부 데이터 원문 접근, PLM row 해석, 주문서/문서 전문 처리, 제품 사양 비교는 local model과 workspace-scoped tool gateway 안에서 수행한다.

OpenAI Agents SDK manager adapter는 내부 데이터 processor가 아니라 policy-controlled planner/reviewer다. 사용할 수 있는 역할은 요구 분석, 작업 계획, internal agent 호출, 결과 리뷰, gap 판단, clarification question generation, redacted quality review로 제한한다.

External manager 사용 여부는 feature flag, runtime policy, workspace setting, data sensitivity, provider availability, cost/latency budget, approval policy가 결정한다. 사용자 prompt도 데이터 반출 대상이므로 `RequestSensitivityClassifier`가 먼저 raw prompt 허용, redacted prompt 필요, external manager 차단 중 하나로 결정한다. `EvidencePacket`은 external manager로 직접 전달하지 않으며, 필요한 경우 `LocalAgentResult`와 redacted summary로 축약, 익명화, 최소화한 뒤 전송한다.

External manager에 보낼 수 있는 데이터는 다음이다.

- `RequestSensitivityClassifier`가 safe로 판정한 사용자 prompt 원문.
- raw prompt가 민감 엔티티를 포함하는 경우 redacted prompt와 redaction summary.
- available agent/tool 목록과 public description.
- workspace/app metadata 중 민감하지 않은 값.
- low-sensitivity personal planning data. 예: 개인 계획, 식단표.
- `LocalAgentResult`의 redacted evidence summary, artifact reference, coverage/gap summary.
- missing intents, clarification candidates, review status.

External manager에 보내면 안 되는 데이터는 다음이다.

- 내부 문서 원문.
- raw RAG chunk.
- raw tool result.
- `EvidencePacket` raw item.
- PLM row.
- 주문서 전문.
- 고객명, 제품코드, 주문번호, 도면번호.
- BOM, 원가, 가격, 계약 조건.
- 내부 시스템 URL.
- credentials, secrets.
- sensitivity classification 전의 raw prompt 또는 classifier가 민감 엔티티를 제거하지 못한 prompt.

OpenAI Agents SDK는 Phase 6 MVP manager runtime으로 채택한다. SDK의 guardrail, human review, result/state, streaming, tracing은 활용할 수 있지만 Doowon의 ACL, approval, redaction, audit, internal trace source of truth를 대체하지 않는다. MVP manager path는 Responses model path를 쓰되 provider-side response storage를 비활성화하고, sensitive tracing capture를 끄며, OpenAI hosted tools를 붙이지 않는다. Claude Agent SDK는 MCP-heavy alternative spike로 보류한다.

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

External search result는 기본적으로 `untrusted` 또는 `mixed` trust level로 `EvidencePacket`에 들어간다. 다만 공식 기관, 표준기관, 규제기관 allowlist source는 policy에 따라 `trusted`로 승격될 수 있다. Internal/external conflict는 단순 source 위치가 아니라 `authority_class`, freshness, trust level, workspace policy, verifier confidence를 기준으로 판단한다. Claude Agent SDK는 개발 자동화와 MCP-heavy agent spike에는 사용할 수 있지만, Phase 6 MVP manager runtime으로 직접 채택하지 않는다.

### 5. SDK manager outputs and structured boundaries

SDK manager path의 핵심 산출물은 자유 텍스트가 아니라 manager plan/result contract로 제한한다. OpenAI Agents SDK function tool schema, Responses structured output, Pydantic schema, runtime business validator를 함께 사용한다.

```text
OpenAI Agents SDK manager
  -> function tool schema / structured output
  -> Pydantic validation
  -> runtime business validator
  -> fallback or retry
```

적용 원칙:

- `AiManagerInput`, `ManagerPlan`, `LocalAgentTask`, `LocalAgentResult`, `ManagerReview`를 MVP contract로 둔다.
- `run_local_specialist`는 external manager adapter가 호출할 수 있는 유일한 internal-data-touching delegate tool이다.
- `LocalAgentResult`는 raw internal payload를 포함하지 않는다.
- manager final answer는 `LocalAgentResult`와 redacted summary 기준으로 작성한다.
- `search.planner`는 deterministic builder를 우선하고, LLM query expansion이 필요한 경우에만 constrained output을 사용한다.
- `approval.proposal_preview`의 설명은 LLM이 만들 수 있지만, 실제 실행 대상은 deterministic canonical object여야 한다.
- Pydantic validation은 mandatory지만 첫 번째 방어선으로 보지 않는다.

```python
class LocalAgentTask(BaseModel):
    agent_id: str
    objective: str
    allowed_tool_names: list[str] = []
    tool_arguments: dict[str, Any] = {}
    approved_call_id: str | None = None
    context_boundary: str
    expected_output: str


class LocalAgentResult(BaseModel):
    agent_id: str
    status: Literal["completed", "blocked", "failed"]
    redacted_summary: str
    artifact_refs: list[str] = []
    coverage: dict[str, list[str]]
    sensitivity_labels: list[str] = []
    blocked_reason: str | None = None
```

검증 규칙은 runtime에서 강제한다.

- `agent_id`는 DB enum migration이 필요한 closed enum으로 고정하지 않고 registry-validated open string으로 둔다.
- `agent_id`는 workspace entitlement, `allowed_app_ids`, `AgentDefinitionResolver` 결과 안에 있어야 한다.
- `run_local_specialist` 입력의 `allowed_tool_names`는 현재 entitlement와 specialist allowlist의 교집합이어야 한다.
- write-touching tool이 포함되면 manager 출력과 무관하게 approval gate를 통과해야 한다. `approved_call_id`가 없으면 `approval_required`로 차단한다.
- Docs internal agent는 MVP에서 write/delete tool을 받지 않는다. 문서 생성/수정/삭제가 필요하면 향후 별도 UX와 approval proposal을 설계한 뒤 capability registry에 다시 노출한다.
- `run_local_specialist`는 function-tool input/output guardrail 또는 동등한 local validation을 매 호출마다 적용한다.
- provider adapter가 strict function schema를 요구하면 exact tool arguments는 JSON string 형태로 받아 내부 `LocalAgentTask.tool_arguments` object로 변환한다. 내부 contract는 provider SDK의 schema 제약에 종속되지 않는다.
- guardrail은 malformed task input, out-of-scope tool, raw internal data가 포함된 tool output을 차단한다.
- manager output validation이 실패하면 기존 single-loop path 또는 clear failure로 전환한다.
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

v1의 default `ModelProfile`은 환경 설정으로 선택되는 `configured local model profile`이다. 로컬 MLX serving model id도 설정값으로 주입한다. 모델 교체는 서비스명 변경이 아니라 `ModelProfile`과 eval gate 변경으로 처리한다.

`ModelProfile`은 다음을 포함한다.

- tool-call parser/format.
- native tool-calling support 여부와 fallback strategy.
- reasoning field visibility와 streaming behavior.
- finish_reason mapping.
- malformed tool call retry policy.
- per-model prompt fragment override.
- reasoning mode support와 disable mechanism.
- thinking mode 기본값과 budget.
- hidden/parsed reasoning channel이 content budget을 잠식하는 정도와 safe minimum `max_tokens`.
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

`AgentDefinition`은 모델 독립 기본 prompt를 갖고, `ModelProfile`이 local/open-source/external provider 계열 override를 제공한다. `ModelProfile`은 `AgentRun` 생성 시 고정한다. 실행 중 모델 프로필이 바뀌면 기존 invocation을 조용히 이어가지 않고, 거부하거나 새 profile로 새 invocation을 시작한다. OpenAI-compatible API는 transport compatibility로만 취급하고, reasoning field, native tool-call parsing, finish reason, structured output guarantee는 `ModelProfile`이 관리한다.

2026-04-30 Gemma MLX bakeoff 결과, text-only chat은 가능했지만 native tool-calling은 `No function provided` parser failure로 실패했다. 따라서 `OpenAI-compatible`은 `supports_native_tool_calling=true`를 의미하지 않는다. native tool-calling이 불안정한 profile은 plain-text JSON/tool proposal 방식의 non-native gateway로 내려가야 한다.

### 10. Runtime profiles over always-on reasoning

로컬 model profile/DGX Spark 운영에서는 "긴 context와 thinking을 쓸 수 있다"와 "항상 써야 한다"를 분리한다. Doowon runtime은 요청마다 runtime profile을 고정하고, profile별 budget을 trace에 남긴다.

- `interactive_read`
  - 기본 profile.
  - non-thinking이 기본값이다.
  - 단순 read/search/summary 요청은 AI manager path보다 deterministic fast path를 우선한다.
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

local model profile은 provider-specific reasoning side channel을 기본 chat content와 분리한다. 모델별 thinking/reasoning option은 `ModelProfile.reasoning_escalation_policy`, adapter, prompt override가 흡수하며, 런타임 공통 계약에는 특정 모델의 chat template flag를 박지 않는다. GPT/Claude 등 외부 profile도 같은 contract를 유지한다.

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

Agent runtime은 serving stack에 종속되지 않지만, 로컬 model profile 운영 현실은 설계 가정에 반영한다.

- PoC와 Phase A~C는 단일 local OpenAI-compatible endpoint를 기준으로 한다.
- v1 내부 agent 모델은 설정된 `ModelProfile`로 선택한다.
- MLX 개발/PoC 기본 checkpoint는 환경 설정으로 선택한다.
- DGX Spark/local model profile 경로는 SGLang을 PoC default serving candidate로 두고, vLLM을 compatibility/bakeoff serving candidate로 검증한다.
- SGLang/vLLM 선택은 serving engine bakeoff로만 다룬다. 모델 후보 비교는 v1 범위에서 제외한다.
- Serving engine 선택은 runtime profile별로 결정한다. `interactive_read`는 TTFT/TPOT/cache hit, `grounded_report`는 structured output과 evidence token 처리, `high_risk_action`은 tool-call argument 안정성, `long_doc`은 context degradation과 memory pressure를 본다.
- DGX Spark는 local validation, pilot serving, batch/offline worker 후보로 평가한다. 별도 benchmark gate 없이 high-concurrency production 기준으로 가정하지 않는다.
- K8s, Ray, Spark, LoRA 학습 파이프라인은 v1 runtime contract의 선행 조건이 아니다.
- 두 번째 DGX Spark를 도입해도 초기 기본 전략은 tensor parallel보다 RAG/embedding, prefill/decode, domain worker 같은 service separation이다.
- OpenAI Agents SDK는 MVP manager runtime dependency로 채택한다. NIM, Triton, TensorRT-LLM, NVIDIA Dynamo, model-specific agent frameworks, LangGraph는 serving/agent 확장 평가 후보로만 둔다.
- 장기 model adaptation은 공통 base model + domain LoRA/PEFT + retrieval source + policy template 조합을 후보로 둔다. 자주 바뀌는 사실은 fine-tuning이 아니라 RAG로 처리한다.

### 13. Observable and reversible rollout

AI manager path는 feature flag 뒤에서 시작한다.

- `AIDOO_AI_MANAGER_ENABLED=false`가 기본값이다.
- `AIDOO_AI_MANAGER_TRACE_SENSITIVE_DATA=false`, `AIDOO_AI_MANAGER_STORE_RESPONSE=false`, `AIDOO_AI_MANAGER_HOSTED_TOOLS_ENABLED=false`가 MVP 기본값이다.
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

- `manager.adapter.openai`
  - OpenAI Agents SDK 기반 manager adapter. 요구 분석, internal agent task 생성, 결과 리뷰, 사용자 질문, 최종 synthesis를 담당한다. 이 adapter는 교체 가능한 외부 manager 구현이며 내부 domain agent의 소유자가 아니다.
- `tool.run_local_specialist`
  - external manager adapter가 호출할 수 있는 유일한 internal-data-touching delegate tool. 내부 실행은 provider-independent `domains.ai.internal_agents` dispatcher, local model, local tool gateway가 담당한다.
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
  - MVP에서는 manager review의 일부로 시작하고, 후속 단계에서 별도 local invocation으로 분리한다.
- `writer.template`
  - MVP에서는 manager final answer 또는 existing artifact parser를 사용하고, 후속 단계에서 EvidencePacket 기반 template writer로 분리한다.
- `approval.proposal_preview`
  - write/batch 실행 전 사용자 검토용 preview를 만든다. 기존 `approvals.py::ApprovalPreview`와 중복 모델을 만들지 않고 연결한다.
- `external.search`
  - MVP 이후 단계의 provider adapter다.
  - sanitized query를 기반으로 OpenAI/Claude SDK/API search capability를 호출한다.
  - raw user prompt를 직접 받지 않고, `ExternalSearchResult`로 normalize한 결과만 반환한다.
  - `external.search`는 `search.executor` 내부의 provider adapter로만 호출된다.

Domain agent는 새 domain service layer가 아니다. `{prompt fragment, tool allowlist, EvidencePacket shape, skills}`를 가진 runtime descriptor이며, 실제 실행은 기존 application service와 MCP capability를 통과한다.

PMS/Planner/Docs/domain agent는 OpenAI SDK `Agent(...)`, OpenAI handoff, Claude SDK subagent가 아니다. 현재 구현은 `configured local model profile` 기반 내부 agent runtime으로 유지하며, future manager가 Claude Agent SDK, OSS manager model, custom manager로 바뀌어도 `LocalAgentTask -> LocalAgentResult` 계약은 유지한다.

### Artifact boundary

기존 fast path와 single-loop fallback은 현재 artifact tag flow를 유지한다. 즉 assistant output의 `<artifact type="document|html|code|svg">...</artifact>`는 기존 `ArtifactStreamParser`가 처리한다.

AI manager path에서는 raw artifact tag를 internal agent가 직접 external manager로 전달하지 않는다. Artifact가 필요한 경우 local boundary 안에서 artifact reference를 만들고, manager는 redacted summary와 artifact reference를 기준으로 최종 응답을 작성한다.

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

1. Chat request가 들어오면 `AIDOO_AI_MANAGER_ENABLED`와 fast path 조건을 먼저 평가한다.
2. Entrypoint가 `interactive_read`, `grounded_report`, `long_doc`, `high_risk_action` 중 runtime profile을 고정한다.
3. `RequestSensitivityClassifier`가 user request, conversation scope, attached data, requested context, available tool scope를 기준으로 pre-routing `DataSensitivityDecision`을 생성한다.
4. `ModelRouter`가 runtime profile, `DataSensitivityDecision`, external manager feature flag, provider availability, cost/latency budget을 기준으로 AI manager eligibility를 결정한다.
5. Feature flag가 꺼져 있으면 기존 single-loop path로 간다.
6. Fast path면 해당 domain agent invocation을 바로 생성한다.
7. Manager path면 선택된 manager adapter를 생성한다. MVP의 첫 adapter는 OpenAI Agents SDK이며 `AiManagerInput`을 전달한다.
8. Manager는 `run_local_specialist` function tool을 통해 `LocalAgentTask`를 생성한다.
9. `run_local_specialist`는 provider adapter boundary에서 `domains.ai.internal_agents`로 위임하고, agent id, workspace entitlement, `allowed_app_ids`, tool allowlist, approval policy를 검증한다.
10. Internal agent는 local model gateway, 기존 MCP capability/RAG/domain service, workspace-scoped tool gateway를 사용해 internal evidence를 수집한다.
11. Internal agent는 raw internal data가 아니라 `LocalAgentResult`를 반환한다.
12. Manager는 `LocalAgentResult`를 리뷰하고 final answer, 추가 specialist call, 사용자 질문, partial answer 중 하나를 선택한다.
13. 추가 specialist call은 `AIDOO_AI_MANAGER_MAX_LOOPS` 안에서만 허용한다. 기본값은 3 review cycle이다.
14. 외부 공개 자료 검색은 MVP 후속 단계다. 활성화 시에도 external search result는 `ExternalSearchResult`로 normalize한 뒤 `EvidencePacket`에 merge한다.
15. Write/external/batch action은 risk-based approval gate 또는 review queue를 통과한다. MVP에서는 기존 `AiToolApproval` 흐름을 유지한다.

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

Interactive agent execution은 MVP에서 API process 안의 OpenAI Agents SDK runner와 기존 stream path로 유지한다. Long-running document analysis, batch jobs, ambient workflows, approval wait은 pilot 이후 durable workflow backend로 위임할 수 있게 둔다.

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
- Local model thinking/non-thinking control success rate.
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
- OpenAI manager adapter structured output, `LocalAgentTask`, `LocalAgentResult`, redaction leakage, internal agent tool-call stability를 Phase A 착수 전 hard gate로 측정한다.
- AI manager rollout kill criteria에는 concurrency dimension을 포함한다. 예: manager path p95는 baseline x2 이내 조건을 1인 단독뿐 아니라 지정 동시성에서도 만족해야 한다.
- external provider는 Phase 0에서 운영 호출을 전제하지 않고, sandbox/eval 환경에서 cost, latency, citation quality, redaction leakage baseline만 측정한다.
- AI manager rollout kill criteria: manager path p95는 baseline x2 이내, recovery path는 baseline x3 이내를 시작 기준으로 둔다.

### Phase A - AI manager MVP foundation

- `openai-agents` Python dependency를 추가한다.
- OpenAI Agents SDK를 Phase 6 MVP manager runtime으로 채택한다.
- Claude Agent SDK는 MCP-heavy spike 후보로만 문서화하고 첫 구현에 포함하지 않는다.
- PMS/Planner/Docs internal agents는 OpenAI SDK Agent/handoff가 아니라 `domains.ai.internal_agents` 아래 provider-independent local agents로 둔다.
- `AIDOO_AI_MANAGER_ENABLED=false`, `AIDOO_AI_MANAGER_PROVIDER=openai`, `AIDOO_AI_MANAGER_MODEL`, `AIDOO_AI_MANAGER_MAX_LOOPS=3`, `AIDOO_AI_MANAGER_TRACE_SENSITIVE_DATA=false`, `AIDOO_AI_MANAGER_STORE_RESPONSE=false`, `AIDOO_AI_MANAGER_HOSTED_TOOLS_ENABLED=false` 설정을 추가한다. MVP/dev smoke 권장 manager model은 `gpt-5.4-mini`이며, production에는 silent default를 두지 않는다.
- `AiManagerInput`, `ManagerPlan`, `LocalAgentTask`, `LocalAgentResult`, `ManagerReview` DTO를 추가한다.
- `LocalAgentResult`는 raw internal data를 포함할 수 없고, redacted summary, artifact ref, coverage/gap, sensitivity label만 포함한다.
- OpenAI Agents SDK tracing은 sensitive data capture off 또는 scrubbed mode를 기본으로 둔다.
- Responses storage는 SDK/API가 지원하는 범위에서 off로 고정하고, MVP manager에는 OpenAI hosted web/file/MCP/code/shell tools를 연결하지 않는다.
- 기존 `AgentRun`, `AgentInvocation`, `AgentTraceEvent`, inspection endpoint, graph scheduler hardening은 지금 더 확장하지 않고 MVP 관측/호환 레이어로 둔다.

### Phase B - Internal agents and delegate tool

- OpenAI manager adapter에 `run_local_specialist` function tool을 추가한다.
- `run_local_specialist`는 내부 데이터에 닿는 유일한 external-manager-visible delegate tool이다.
- tool input은 `agent_id`, `objective`, `allowed_tool_names`, `context_boundary`, `expected_output`으로 제한한다.
- tool 실행 전 workspace entitlement, `allowed_app_ids`, specialist allowlist, current registry, approval policy를 검증한다.
- tool 내부 실행은 `domains.ai.internal_agents`의 provider-independent dispatcher로 위임한다.
- PMS/Planner/Docs는 OpenAI SDK Agent/handoff가 아니며, 현재는 local model/MLX, 기존 `agent.py` loop, MCP-shaped capability registry, RAG/domain service, workspace ACL을 재사용한다.
- raw tool result, raw RAG chunk, internal document text는 OpenAI manager로 반환하지 않는다.
- function-tool input/output guardrail 또는 동등한 local validation이 malformed input, out-of-scope tool, raw-data-bearing output을 차단한다.
- blocked/failed/approval-required 케이스도 `LocalAgentResult`로 반환해 manager가 사용자 질문, partial answer, final failure 중 하나를 선택하게 한다.

### Phase C - OpenAI manager stream path

- 기존 chat stream 진입점 앞에 AI manager eligibility check를 추가한다.
- feature flag가 꺼져 있거나 provider 설정이 없으면 기존 single-loop path로 간다.
- manager path는 OpenAI Agents SDK Runner를 사용하고, Responses model path를 기본으로 한다.
- manager는 request sensitivity classification을 통과한 raw user prompt 또는 redacted prompt, non-sensitive metadata, available agent/tool description, prior redacted summaries를 입력으로 받는다.
- manager run config는 sensitive trace capture off, response storage off, hosted tools disabled를 강제한다.
- manager output은 existing `AgentEventEnvelope`로 planning, specialist-running, review, final/gap 상태를 노출한다.
- manager loop는 `AIDOO_AI_MANAGER_MAX_LOOPS` 안에서만 specialist 재호출을 허용한다.
- OpenAI API failure, malformed tool args, internal agent failure, loop limit exceeded는 clear failure 또는 partial answer로 종료한다.
- cancellation은 SDK run과 internal agent boundary 사이에 전파한다.

### Phase D - Search and evidence

- 기존 RAG/domain tool result를 internal agent boundary 안에서 `EvidencePacket`으로 normalize한다.
- external manager에는 raw `EvidencePacket`이 아니라 `LocalAgentResult`와 redacted evidence summary만 전달한다.
- external search는 MVP 후속 단계로 둔다. 활성화 시에도 manager direct search가 아니라 `search.executor` provider adapter를 통과한다.
- external result는 `ExternalSearchResult`로 normalize한 뒤에만 `EvidencePacket`에 들어간다.

### Phase E - Post-MVP hardening

- MVP가 API stream/UI에서 검증된 뒤 external search, dedicated verifier, template writer, review queue, durable workflow, retention/inspection hardening을 재킥오프한다.
- 이 단계에서도 OpenAI manager에는 raw `EvidencePacket`을 전달하지 않는다.
- Claude Agent SDK는 internal capability를 MCP server로 안정적으로 노출한 뒤 MCP tool search/permissions spike로 평가한다. Spike 조건은 `setting_sources=[]` 또는 동등 설정, auto memory disabled, explicit MCP server allowlist, no `.claude/` active instruction path다.
- LangGraph 또는 model-specific agent framework는 OpenAI Agents SDK manager loop가 실제 요구를 충족하지 못하거나 durable workflow/checkpoint/resume 요구가 명확해질 때만 재평가한다.

## Verification

- AI manager adapter
  - OpenAI manager adapter가 structured plan을 만들고 `run_local_specialist` delegate tool을 호출한다.
  - manager는 sensitivity classification을 통과한 raw user prompt 또는 redacted prompt와 non-sensitive metadata만 받을 수 있다.
  - manager loop는 `AIDOO_AI_MANAGER_MAX_LOOPS`를 넘지 않는다.
  - OpenAI API failure, malformed tool args, internal agent failure, loop limit exceeded가 clear failure 또는 partial answer로 끝난다.
- Internal agent boundary
  - PMS/Planner/Docs internal agents는 OpenAI SDK Agent/handoff가 아니다.
  - `domains.ai.internal_agents`는 local model gateway와 existing domain/RAG tools만 사용하며 provider SDK를 import하지 않는다.
  - raw internal document, raw RAG chunk, raw tool result, PLM row, order/contract data가 OpenAI manager로 반환되지 않는다.
  - invalid agent id, out-of-scope tool, hidden workspace app, ACL denied, approval-required cases가 blocked `LocalAgentResult`로 표현된다.
  - `LocalAgentResult`는 redacted summary, artifact refs, coverage/gap, sensitivity labels만 포함한다.
- Streaming and UI
  - SSE는 planning, specialist-running, review, final/gap 상태를 노출한다.
  - feature flag off 상태에서는 기존 single-loop chat behavior가 변하지 않는다.
  - UI E2E는 final URL, accessibility snapshot, console, page errors를 기록한다.
- Data boundary and observability
  - OpenAI Agents SDK tracing은 sensitive data capture off 또는 scrubbed mode로 동작한다.
  - Responses storage는 disabled로 설정되고, MVP manager에 OpenAI hosted tools가 등록되지 않는다.
  - internal trace/audit remains source of truth.
  - raw `EvidencePacket`은 external manager에 전달되지 않는다.
  - 외부 전송 payload는 DTO 단위로 테스트 가능하다.
- Post-MVP gates
  - external search, dedicated verifier, template writer, durable workflow, review queue는 MVP E2E가 통과한 뒤 별도 gate로 시작한다.

## Alternatives Considered

| 대안 | 결론 | 이유 |
|---|---|---|
| OpenAI Agents SDK | 채택 | manager loop, function tools, streaming, result/state, approvals, tracing을 제공해 custom orchestration 구현보다 MVP 구조를 줄인다. |
| Claude Agent SDK | 보류 | 파일/명령/MCP-heavy agent에는 강하지만, 현재 업무 데이터 MVP에서는 내부 data boundary를 위해 동일한 internal agent delegate tool이 여전히 필요하다. 안정적 MCP server와 filesystem/memory/tool allowlist 제약을 갖춘 뒤 spike한다. |
| LangGraph/model-specific agent framework 직접 의존 | 보류 | OpenAI Agents SDK로 MVP loop를 먼저 검증하고, durable workflow/checkpoint/resume 요구가 명확해질 때 재평가한다. |
| Fast path only | 기각, 단 Phase B의 일부로 채택 | latency 개선에는 좋지만 grounding, verifier, template writer, context package 확장성을 해결하지 못한다. |
| Verifier only | 기각, Phase D로 흡수 | 환각 억제에는 유용하지만 큰 tool catalog와 manager/specialist 경계 문제를 해결하지 못한다. |
| 기존 `AgentRunSnapshot` 확장 | 차후 migration 상세에서 재검토 | additive migration은 안전하지만 approval 전용 모델에 runtime 전체 의미를 얹으면 장기적으로 상태 의미가 흐려진다. Phase A에서 shadow-write/compat projection과 cutover shape를 먼저 정하고, Phase E에서 상세 이관과 제거 시점을 결정한다. |
| Local model bakeoff | 보류 | v1 MVP는 설정된 `ModelProfile` 하나로 vertical slice를 검증한다. Qwen/Gemma/DeepSeek 등 모델 비교는 서비스명 변경 없이 후속 eval gate에서 수행한다. |
| 외부 A2A 또는 managed-agent runtime 우선 도입 | v1 제외 | 내부 제품 runtime의 tool/context/approval 계약을 먼저 안정화해야 한다. 외부 agent interoperability는 장기 후보로 둔다. |
| 모든 task agent를 별도 invocation으로 분리 | 기각 | 로컬 LLM 비용과 latency가 커진다. 일반 task는 domain skill로 inline 처리하고 verifier/write/template만 분리한다. |
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
| 외부 LLM을 내부 데이터 processor로 사용 | 기각 | 내부 문서 원문과 raw tool result가 provider로 나갈 위험이 커진다. external LLM은 manager/reviewer로 제한하고 실제 데이터 처리는 local model internal agent가 맡는다. |
| 외부 LLM에 `EvidencePacket` 직접 전달 | 기각 | raw excerpt, internal ref, 민감 정보 노출 가능성이 있다. external manager에는 `LocalAgentResult`와 redacted summary만 전달한다. |
| 자체 웹 검색 인프라 우선 구축 | 보류 | crawler, ranking, parsing, cache, freshness 판단 운영 부담이 크다. v1에서는 SDK/API search capability가 현실적이다. |
| SDK 검색 결과를 그대로 최종 답변에 사용 | 기각 | provider ranking/citation을 그대로 신뢰하면 감사, 재현성, 신뢰도 문제가 생긴다. `ExternalSearchResult`와 `EvidencePacket`으로 normalize해야 한다. |
| external search query sanitizer 생략 | 기각 | query 자체가 데이터 반출이다. 고객명, 제품코드, 주문번호 등이 query에 포함될 수 있다. |
| Claude Agent SDK를 MVP manager runtime으로 사용 | 보류 | MCP tool search/permissions spike 후보로 남기되, 첫 구현 provider는 OpenAI Agents SDK로 고정한다. |
| `external.search`를 일반 agent로 노출 | 기각 | manager가 sanitizer/egress policy를 우회해 외부 검색을 직접 호출할 위험이 있다. external search는 `search.executor` provider adapter로만 실행한다. |
| external planning output을 그대로 실행 | 기각 | 외부 provider가 execution authority를 갖게 된다. manager는 `LocalAgentTask` 후보만 만들고 local boundary가 entitlement, tool allowlist, data policy를 다시 검증해야 한다. |
| sanitizer를 external LLM으로 수행 | 기각 | sanitization 자체가 data egress가 된다. sanitizer는 local/pre-egress로 수행해야 한다. |
| 내부 evidence 항상 우선 | 부분 수정 | 내부 업무 사실에는 맞지만 법규/표준/인증은 official external authority가 더 우선될 수 있다. `authority_class` 기반 conflict rule을 사용한다. |
| external search result cache 생략 | 기각 | 외부 검색 결과는 비결정적이다. 감사와 재현성을 위해 normalized result와 query hash를 저장해야 한다. |
| external quality review output 직접 사용 | 기각 | 외부 output이 verifier/writer를 우회할 수 있다. suggestion으로만 사용하고 `writer.template`이 최종 산출물을 다시 생성한다. |
| Phase A에서 full hybrid contract 전체 구현 | 부분 수정 | 정본 contract는 유지하되 첫 구현은 OpenAI manager adapter, internal agent delegate tool, DTO/redaction boundary, eval harness로 제한한다. Persistence/inspection hardening은 후속 단계로 미룬다. |
| `review_queue_required`를 Phase 6 v1에서 즉시 emit | 보류 | review queue backend/admin policy surface가 없으면 실행 의미가 없다. Phase 6 v1은 approval 또는 denied로 수렴하고, review queue는 Phase 7 이후 활성화한다. |
| `ManagerPlan`/`LocalAgentTask` domain/intent/output을 closed enum으로 고정 | 기각 | 새 domain 추가 때 DB enum migration과 prompt/cache churn이 커진다. registry-validated open string으로 검증한다. |

## Decision Log

### 확정 결정

| 항목 | 결정 |
|---|---|
| 외부 A2A | v1 범위에서 제외 |
| MVP manager runtime | OpenAI Agents SDK |
| External manager API | Direct OpenAI, Responses model path through Agents SDK |
| Claude Agent SDK | Deferred MCP-heavy spike. 조건: stable MCP servers, explicit server allowlist, filesystem settings disabled, auto memory disabled |
| LangGraph/model-specific agent framework | MVP 제외. durable workflow/checkpoint/resume 요구가 생기면 후속 재평가 |
| 기본 internal agent 모델 | 설정된 `ModelProfile` |
| 로컬 MLX 기본 checkpoint | 환경 설정으로 주입 |
| 기본 제어 방식 | AI manager adapter가 최종 답변을 소유하고 provider-independent internal agent runtime을 `run_local_specialist` delegate tool로 호출 |
| 단순 요청 처리 | deterministic fast path 우선 |
| decomposition | 모든 요청에 수행하지 않고 manager-eligible path에서만 manager가 수행 |
| structured output | OpenAI function tool schema/structured output + Pydantic validation + runtime business validator |
| manager output | `ManagerPlan`, `LocalAgentTask`, `ManagerReview` contract |
| internal agent output | `LocalAgentResult` contract |
| rollout flag | `AIDOO_AI_MANAGER_ENABLED=false` 기본값 |
| 외부 LLM 사용 | MVP의 OpenAI AI manager adapter는 planning, internal agent 지시, review, clarification, final synthesis에 사용 |
| 외부 LLM 역할 | 내부 데이터 processor가 아니라 manager/reviewer |
| 외부 원문 전송 | 사용자 raw prompt는 request sensitivity classification 통과 시에만 허용. 민감 엔티티가 있으면 redacted prompt 또는 차단. 내부 문서 원문/PLM/order/raw tool result/식별자/가격/계약/secret은 금지 |
| 외부 전달 DTO | raw `EvidencePacket`이 아니라 `LocalAgentResult`와 redacted summary 사용 |
| OpenAI response storage | MVP manager path는 provider-side response storage disabled 기본 |
| OpenAI hosted tools | MVP manager에는 hosted web/file/MCP/code/shell tools 등록 금지 |
| OpenAI trace sensitive data | sensitive data capture disabled 또는 scrubbed mode 기본 |
| 외부 검색 | 별도 검색 인프라 우선 구축 대신 OpenAI/Claude SDK/API search capability를 `ExternalSearchProvider`로 활용 가능 |
| 외부 검색 query | 데이터 반출로 취급하며 sanitization mandatory |
| external search result | `ExternalSearchResult`로 normalize 후 `EvidencePacket`에 편입 |
| external source trust | 기본 `untrusted` 또는 `mixed` |
| sensitivity classification | pre-routing `RequestSensitivityClassifier`와 pre-egress `PayloadSensitivityClassifier`로 나눠 수행 |
| external.search 호출 경계 | manager direct invocation 금지, `search.executor` provider adapter로만 호출 |
| internal agent boundary | PMS/Planner/Docs는 OpenAI SDK Agent/handoff가 아니라 독립 local agents. External manager가 호출하는 유일한 internal-data-touching delegate tool은 `run_local_specialist` |
| sanitizer 실행 위치 | external provider 호출 전 local/deterministic sanitizer 수행 |
| evidence conflict 판단 | source 위치가 아니라 `authority_class`, freshness, trust level, workspace policy, verifier confidence 기준 |
| external search cache | 동일 `AgentRun`/report generation 안에서 동일 sanitized query는 동일 cached result 사용 |
| provider data-use policy | retention/training/region/logging policy가 workspace policy와 충돌하면 provider 사용 금지 |
| external quality review | final artifact가 아니라 suggestion으로만 사용 |
| external.document.fetch | SSRF/private network/file/MIME/safe parser boundary 필수 |
| external call approval | 모든 external call 승인 강제가 아니라 policy decision에 따라 auto/trace/approval/review/deny로 분류 |
| review queue decision | Phase 6 v1에서 review queue backend가 없으면 `review_queue_required`를 emit하지 않고 approval/deny로 수렴 |
| Phase A 구현 범위 | OpenAI Agents SDK dependency/settings, manager DTO, redaction boundary |
| AgentRunSnapshot cutover | MVP 이후 필요할 때 상세 이관한다. 현재는 기존 path를 유지한다 |
| resume scope | approval halt 시 resolved tool/agent allowlist를 저장하고 resume 시 scope widening을 차단한다 |
| trace ordering | `AgentTraceEvent` ordering은 UUID가 아니라 per-run monotonic sequence를 사용한다 |
| task agent | extract/summarize/compare/draft는 domain agent 내부 skill |
| 별도 invocation | MVP 이후 verifier, write_proposal, approval.proposal_preview, writer.template 분리 |
| evidence | `EvidencePacket`을 verifier/writer/search/domain 공통 contract로 사용 |
| recovery | OpenAI manager review loop가 결정하되 기본 최대 3 cycle |
| search executor | 기존 `domains/rag/application.py`와 domain tools의 thin adapter |
| search planner | deterministic-first, LLM query expansion은 optional |
| artifact ownership | MVP는 기존 parser와 artifact ref를 유지, template writer는 후속 분리 |
| template writer | deterministic renderer + evidence-bound LLM section filler |
| approval preview | canonical `WriteProposal`과 LLM explanation 분리 |
| 모델 교체성 | adapter + `ModelProfile` + per-model prompt override |
| OpenAI-compatible API | transport compatibility로만 취급 |
| reasoning 기본값 | non-thinking 기본, thinking은 runtime profile과 escalation policy가 허용할 때만 사용 |
| context 기본값 | interactive는 32K 시작, 64K 이상은 benchmark gate 후 확장 |
| retrieval budget | 후보 20~40개, rerank 4~8개, 일반 final evidence 2K~4K token 시작점 |
| memory | short-term은 8~16턴과 현재 evidence/tool result, long-term은 typed/audited state만 저장 |
| serving v1 | 설정된 local OpenAI-compatible endpoint 기준 |
| Serving engine 평가 | 설정된 model profile 기준으로 SGLang/vLLM runtime profile별 bakeoff |
| Internal tools | typed service + tool gateway 유지 |
| MCP | 외부 capability boundary 중심 |
| Observability | internal trace source of truth + OTel export |
| Eval fixture | Phase A부터 starter dataset과 pass/fail gate 정의 |
| batch 승인 | 장기적으로 DB/workspace admin policy |

### 검증 전 가설

| 항목 | 검증 방식 |
|---|---|
| AI manager path가 비용 대비 충분한 결과 품질 개선을 만든다 | Phase 0 baseline과 Phase C/E perf-quality gate |
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
| OpenAI manager가 local-only single loop보다 복잡한 요청에서 더 좋은 task plan과 gap review를 만든다 | routing / manager plan success eval |
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
| 기본 general chat external provider | Phase 6 manager MVP 이후 필요 시 |
| 기본 external search provider | MVP 이후 external search gate 착수 시 |
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
| A2A protocol 도입 여부 | MVP flow와 data boundary 검증 후 |

## Rollback Plan

이 문서는 설계 계획이므로 코드 rollback은 없다. 이후 구현 단계에서 문제가 생기면 다음 순서로 되돌린다.

1. `AIDOO_AI_MANAGER_ENABLED=false`로 AI manager 진입을 중단한다.
2. OpenAI provider key 또는 manager provider 설정을 비활성화해 모든 external manager 호출을 중단한다.
3. `AIDOO_AI_EXTERNAL_SEARCH_ENABLED=false`로 모든 external search 호출을 중단한다.
4. AI manager path를 기존 single-loop/local path로 되돌린다.
5. external quality review를 비활성화하고 local verifier만 사용한다.
6. ExternalSearchProvider 장애 시 internal-only search로 fallback한다.
7. chat entrypoint를 기존 single-loop agent path로 전환한다.
8. 새 manager trace와 external call trace는 read-only로 보존하고 신규 write만 중단한다.
9. approval flow는 기존 approval endpoint 계약을 유지한 채 compatibility shim 또는 old snapshot path로 되돌린다.
10. egress policy 위반이 발견되면 provider key를 revoke하고 affected `AgentRun`을 audit 대상으로 표시한다.
11. 실패 원인을 eval fixture와 trace event로 정리한 뒤 단계별 재도입한다.
