# Phase 6 AI Manager MVP Implementation Plan

> 문서 성격: `Evidence-First Hybrid Agent Runtime`의 새 Phase 6 구현 플랜.
> 기준 문서: [`02-evidence-first-agent-runtime.md`](./02-evidence-first-agent-runtime.md)
> 범위: 교체 가능한 AI manager adapter와 독립 local model internal agent runtime을 연결하는 최소 vertical slice. 첫 adapter만 OpenAI Agents SDK를 사용한다.

## Context

Phase 6의 구현 방향을 전환한다. 이전 runtime-kernel 우선 계획은 production foundation을 먼저 단단하게 만드는 방향이었고, 실제 사용자 경험인 "프롬프트 -> 계획 -> 내부 근거 수집 -> 리뷰 -> 최종 응답" 검증보다 runtime persistence, inspection, trace invariant hardening이 앞섰다.

이제 active 목표는 **OpenAI AI manager adapter + local model internal agent MVP**다. 외부 manager model은 계획, 작업 지시, 감시, 리뷰, 사용자 의사결정 요청을 담당한다. PMS/Planner/Docs 같은 내부 agent는 OpenAI SDK Agent/handoff가 아니라 provider-independent internal agent이며, 현재 모델은 `configured local model profile` 또는 로컬 MLX checkpoint다. 내부 문서, RAG, domain service, workspace-scoped tool gateway 접근은 이 internal agent runtime 안에서만 수행한다.

기존 runtime table, graph adapter, trace/inspection 코드는 폐기하지 않는다. 단, 지금부터는 더 키우지 않고 MVP 관측/호환 레이어로만 사용한다.

## Current Execution State

- Current PR/stage: PR1 through PR5 workspace draft implemented as a mockable AI Manager MVP vertical slice, with the first OpenAI Agents SDK adapter boundary and independent internal local-agent runner in place.
- Last completed: `openai-agents` dependency, AI manager settings, safe SDK defaults, module boundary, manager DTOs, prompt redaction boundary, `LocalAgentResult` safety validation, `run_local_specialist` adapter boundary, mock manager SSE stream path behind `AIDOO_AI_MANAGER_ENABLED`, bounded manager review loop tests, OpenAI Agents SDK agent/run-config/tool/stream adapter tests, provider-independent `LocalModelAgentRunner` using the existing local pool with `pool_hint="local"`, `ToolGatewayLocalAgentRunner` for read-tool evidence calls plus local model summary, real OpenAI smoke with `gpt-5.4-mini`, MLX local-model smoke for Docs/PMS/Planner read tasks, and approval-gated PMS/Planner CRUD capability expansion.
- Current domain write policy: PMS supports approval-gated create/update/comment/delete, Planner supports approval-gated create/update/delete, Meeting create remains approval-gated, and Docs is intentionally AI read-only for now. Docs write capability can be reconsidered later but must not be exposed in the MVP capability registry.
- Stopped/deferred: runtime-kernel expansion, graph persistence invariant hardening, runtime retention scheduler, inspection hardening, durable workflow backend design, high-risk graph support, approval-preview graph execution.
- Next exact task: Run an API-route smoke with AI manager enabled, local server dependencies available, and a seeded workspace prompt that covers Docs read, PMS read/write proposal, and Planner read/write proposal. Then add approval persistence/resume for manager-driven write execution if the smoke exposes a UX gap.
- Non-goal for the next task: LangGraph adoption, Claude Agent SDK adoption, external search, broad DB migration, new admin policy UI, durable long-running workflow, or OpenAI hosted tools.

## Architecture / Principles

### 1. OpenAI Agents SDK is the MVP manager runtime

Phase 6 MVP adopts OpenAI Agents SDK as the AI manager runtime. The SDK owns the agent loop, model calls, tool-call round trips, streaming result surface, resumable state concept, human-review concept, and optional tracing surface.

Implementation must use Direct OpenAI for this manager path, not the existing OpenRouter-compatible chat pool. The existing OpenRouter-compatible pool remains available for normal chat routing and later provider experiments.

Required implementation dependency:

- `openai-agents` Python package in `apps/api/pyproject.toml`.

Required feature flags/settings:

- `AIDOO_AI_MANAGER_ENABLED=false`
- `AIDOO_AI_MANAGER_PROVIDER=openai`
- `AIDOO_AI_MANAGER_MODEL=gpt-5.4-mini` for MVP/dev smoke, with no silent default in production
- `AIDOO_AI_MANAGER_MAX_LOOPS=3`
- `AIDOO_AI_MANAGER_TRACE_SENSITIVE_DATA=false`
- `AIDOO_AI_MANAGER_STORE_RESPONSE=false`
- `AIDOO_AI_MANAGER_HOSTED_TOOLS_ENABLED=false`

### 2. Manager owns decisions; internal agents own internal data

The OpenAI manager adapter may receive:

- raw user prompt only when `RequestSensitivityClassifier` allows it
- redacted user prompt when the raw prompt contains customer, order, product, price, contract, credential, or other forbidden entities
- conversation/task metadata
- available specialist agent ids and descriptions
- public tool descriptions
- workspace/app metadata that is not sensitive
- low-sensitivity personal planning data, such as personal plans or meal plans, when workspace policy allows it
- prior loop state, gap summaries, and redacted evidence summaries

The OpenAI manager adapter must not receive:

- unsanitized user prompt when the classifier detects forbidden or unresolved sensitive entities
- internal document raw text
- raw RAG chunks
- raw tool results
- PLM rows
- order, contract, BOM, cost, price, or quote details
- customer names, product codes, order numbers, drawing numbers, internal URLs, credentials, secrets
- raw `EvidencePacket`

Internal agent output returned to the manager must use `LocalAgentResult`: status, concise redacted evidence summary, artifact references, coverage/gap information, sensitivity labels, and blocked reason. Raw internal data remains inside the local execution boundary.

### 3. Internal agents are provider-independent, not OpenAI handoffs

PMS/Planner/Docs/domain agents must not be implemented as OpenAI SDK `Agent(...)` objects or SDK handoffs. They live behind the provider-independent `domains.ai.internal_agents` runtime and use local model/tool gateway/application services. The manager remains responsible for the final answer and calls internal agents through a single adapter-visible delegate tool:

```text
User
  -> AiManagerAdapter
       current: OpenAI Agents SDK
       future: Claude Agent SDK / OSS manager model / custom manager
     -> run_local_specialist adapter tool
        -> provider-independent internal agent dispatcher
           -> domain.docs / domain.pms / domain.planner
              model: configured local model profile
              data: workspace-scoped tools and application services
        <- LocalAgentResult only
  <- final answer / ask user / retry
```

`run_local_specialist` executes inside the API process and delegates to `domains.ai.internal_agents`. This internal module must not import OpenAI Agents SDK, Claude Agent SDK, or provider-specific manager code. It reuses the existing local LLM path, MCP-shaped capability registry, RAG/domain tools, approval guard, and workspace ACL checks. The function tool is only an adapter boundary between external reasoning and internal data.

### 4. Bounded loop first

The MVP loop is intentionally bounded:

1. Manager analyzes the user prompt and available agents.
2. Manager calls one or more internal agent tasks through the function tool.
3. Manager reviews each `LocalAgentResult`.
4. Manager either calls another specialist, asks the user a clarifying/approval question, or produces the final response.
5. The run stops at `AIDOO_AI_MANAGER_MAX_LOOPS`, default 3, with a partial answer and explicit gap if still unresolved.

No autonomous unbounded loop is allowed. A loop iteration means one manager review cycle after internal agent work, not every token/tool event inside the SDK.

### 5. Tracing is useful but not source of truth

OpenAI Agents SDK tracing may be used for development observability only when sensitive payload capture is disabled or scrubbed. Internal audit and trace remain the source of truth for production. Raw local tool inputs/outputs and internal evidence must not be sent to OpenAI tracing.

The manager path must use the Responses model path with provider-side response storage disabled where the SDK/API exposes that control. Do not enable OpenAI hosted tools in the MVP. `WebSearchTool`, `FileSearchTool`, hosted MCP, code interpreter, hosted shell, and other provider-side tools stay disabled until a separate external-tool gate exists.

Claude Agent SDK is deferred. It is a strong candidate for an MCP-heavy spike after internal capabilities are exposed as stable MCP servers, but it is not part of the first MVP. Any Claude spike must run with filesystem settings disabled (`setting_sources=[]` or equivalent), auto memory disabled, explicit MCP server allowlist, and no `.claude/` active instruction path in this repository.

LangGraph/custom graph runtime is deferred until there is a concrete durable-workflow need: long-running batch, approval-wait resume, retry across process restarts, review queue orchestration, or time-travel/debuggable graph state.

## Implementation Stages

### PR 1 — Documented Pivot And Dependency Skeleton

Goal: make the active plan and config surface unambiguous.

Changes:

- Add `openai-agents` to `apps/api/pyproject.toml`.
- Add AI manager settings to `core/settings.py`.
- Add a feature-gated module boundary, e.g. `domains/ai/manager_runtime/`.
- Add SDK run configuration defaults: tracing sensitive data off, response storage off, hosted tools off.
- Keep the feature disabled by default.
- Do not alter the default single-loop chat behavior.

Completion:

- Settings parse with defaults.
- Importing the new module does not require `OPENAI_API_KEY`.
- Defaults map to no OpenAI hosted tools, no sensitive trace capture, and no provider-side response storage.
- `git diff --check` passes.

### PR 2 — Manager DTOs And Redaction Boundary

Goal: define the minimum data shapes that prevent raw internal data leakage.

Contracts:

- `AiManagerInput`
- `ManagerPlan`
- `LocalAgentTask`
- `LocalAgentResult`
- `ManagerReview`

Rules:

- `AiManagerInput` can include raw user prompt only after request sensitivity classification allows it.
- If the prompt contains forbidden entities, `AiManagerInput` must carry a redacted prompt plus redaction summary.
- `LocalAgentResult` cannot include raw tool result, raw RAG chunk, or raw internal document text.
- Any internal artifact is referenced by id/ref, not copied into the manager payload.
- Sensitivity labels travel with all specialist results.

Completion:

- DTO tests cover allowed raw prompt and forbidden raw internal fields.
- DTO tests cover raw prompt allowed, redacted prompt required, and prompt blocked cases.
- Redaction/scrub tests reject representative customer/product/order/price/internal URL leakage.

### PR 3 — Internal Agents And Delegate Tool

Goal: expose independent local model internal agents to any AI manager adapter through one delegate tool.

Behavior:

- Tool name: `run_local_specialist`.
- Internal task inputs: `agent_id`, `objective`, `allowed_tool_names`, optional `tool_arguments`, optional `approved_call_id`, `context_boundary`, `expected_output`. The OpenAI function-tool adapter exposes exact tool args as `tool_arguments_json` to keep the SDK strict schema compatible, then parses it into internal `tool_arguments`.
- It resolves the requested specialist from the existing AI capability registry or runtime agent definitions.
- It executes through provider-independent `domains.ai.internal_agents`, local model, and local tool gateway only.
- PMS/Planner/Docs are not OpenAI SDK agents, Claude SDK agents, or handoffs.
- It applies existing workspace ACL and approval-required tool gates.
- It may execute approval-gated write tools only when an existing `approved_call_id` is supplied by the existing approval flow; otherwise it returns blocked `approval_required`.
- Docs internal agent is read-only in MVP. It may use `docs.list_hub`, `docs.get_item`, `docs.list_pages`, `docs.read_page`, and RAG read tools only.
- PMS/Planner internal agents may use approval-gated write/delete tools after approval. PMS supports `pms.create_issue`, `pms.update_issue`, `pms.add_comment`, `pms.delete_issue`; Planner supports `planner.create_event`, `planner.update_event`, `planner.delete_event`.
- It uses function-tool input/output guardrails or equivalent local validation around every call.
- It returns `LocalAgentResult`.

Completion:

- Unit tests use a fake internal agent runner and prove no raw result leaves the tool.
- Unit tests assert `domains.ai.internal_agents` has no OpenAI/Claude provider SDK dependency.
- Invalid `agent_id`, out-of-scope tool, and ACL-denied cases return blocked `LocalAgentResult`.
- Guardrail tests reject malformed task input and raw-data-bearing tool output.

### PR 4 — OpenAI Manager Agent Stream Path

Goal: connect the manager to the existing SSE chat surface without replacing normal chat.

Behavior:

- When `AIDOO_AI_MANAGER_ENABLED=false`, current chat behavior is unchanged.
- When enabled and a request is ai-manager eligible, the API creates an OpenAI manager adapter with the `run_local_specialist` function tool. No PMS/Planner/Docs OpenAI SDK agents or handoffs are created.
- The API streams manager planning, internal agent execution status, review status, and final answer through existing `AgentEventEnvelope` types where possible.
- SDK run state is not treated as the internal audit source of truth; internal run metadata stores only scrubbed summaries.
- Responses storage is disabled where supported, and OpenAI hosted tools are not attached to the manager agent in MVP.

Completion:

- Workspace draft status: mock manager path implemented and route-tested; OpenAI Agents SDK adapter now builds the real Agent/Runner boundary with safe defaults, fake-run tests, and real-key `gpt-5.4-mini` smoke.
- Mocked OpenAI manager test streams an end-to-end final answer.
- OpenAI failure returns clear error/done SSE events.
- Cancellation propagates to the active manager run and internal agent task where possible.
- Tests assert `trace_include_sensitive_data=False`, response storage disabled, and no hosted tools registered.

### PR 5 — Bounded Review Loop And User Decision Points

Goal: make the MVP behave like a supervised coding-agent loop without unbounded autonomy.

Behavior:

- Max review loops defaults to 3.
- Manager may request another internal agent call only while under the limit.
- Manager may stop and ask the user when evidence is missing, permission is needed, or intent is ambiguous.
- Approval-required write tools continue using existing `AiToolApproval`; SDK human review is a reference pattern, not a replacement in MVP. Docs write is excluded from MVP even if the base application supports manual Docs editing.

Completion:

- Workspace draft status: bounded mock manager loop implemented with unit coverage for final, retry, loop-limit partial, user-question, approval-required, and failed-review stops.
- Tests cover final success, one retry success, loop-limit partial answer, user-question stop, and approval-required stop.

### PR 6 — UI/E2E Smoke

Goal: verify the actual user experience rather than only runtime contracts.

Checks:

- Start local API, web, and MLX as needed.
- Enable AI manager with a test OpenAI key only in local/dev.
- Submit a prompt that requires internal RAG/domain evidence.
- Verify UI shows progress, internal agent work, manager review, and final/gap.
- Verify console and page errors are clean.

Completion:

- Record smoke result in this plan or a root work log.
- Include the final URL, accessibility snapshot summary, console, and page error summary.

## Verification

Targeted tests:

```bash
cd apps/api
uv run pytest tests/test_ai_stream.py tests/test_ai_events.py
uv run pytest \
  tests/test_ai_manager_config.py \
  tests/test_ai_manager_contracts.py \
  tests/test_ai_manager_live.py \
  tests/test_ai_manager_openai_adapter.py \
  tests/test_ai_manager_specialist_tool.py \
  tests/test_ai_manager_stream.py
uv run pytest \
  tests/test_ai_registry.py \
  tests/test_ai_mcp_bridge.py \
  tests/test_ai_tool_runtime.py \
  tests/test_ai_tools.py \
  tests/test_domain_write_services.py
```

Live OpenAI smoke, opt-in:

```bash
cd apps/api
AIDOO_RUN_LIVE_OPENAI_AI_MANAGER=1 \
AIDOO_AI_MANAGER_MODEL=gpt-5.4-mini \
uv run pytest tests/test_ai_manager_live.py
```

Static checks:

```bash
git diff --check
cd apps/api && uv run ruff check src tests
```

Document checks:

```bash
rg -n "Phase 0-A.*minimal.*runtime kernel|No external provider.*execution|Continue.*Phase 6 review pass" \
  plans/00-ai-platform-roadmap.md plans/02-evidence-first-agent-runtime.md plans/README.md \
  | rg -v "rg -n"
```

The command should return only historical/deferred notes, not active next-step instructions.

## Decision Log

| 항목 | 결정 |
|---|---|
| MVP manager runtime | OpenAI Agents SDK |
| External manager API | Direct OpenAI, Responses model path through Agents SDK |
| Claude Agent SDK | Deferred MCP-heavy spike |
| LangGraph/custom graph runtime | MVP 제외 |
| Internal agents | Provider-independent `domains.ai.internal_agents`; PMS/Planner/Docs are not OpenAI SDK agents or handoffs |
| Domain write surface | PMS and Planner have approval-gated CRUD where supported; Docs is AI read-only in MVP |
| Local model | `configured local model profile`, local MLX checkpoint for dev |
| Loop policy | bounded, default max 3 review cycles |
| Raw user prompt to manager | allowed only after request sensitivity classification |
| Raw internal data to manager | forbidden |
| SDK tracing | disabled or sensitive capture off by default |
| Responses storage | disabled by default where supported |
| OpenAI hosted tools | disabled in MVP |
| Raw prompt egress | allowed only after request sensitivity classification; otherwise redacted or blocked |
| Claude spike prerequisites | stable internal MCP servers, explicit server allowlist, filesystem settings disabled, auto memory disabled |
| LangGraph revisit trigger | durable workflow or checkpoint/resume requirement |
| Existing runtime hardening | stopped/deferred unless needed by MVP |

## 2026-04-30 Local E2E Findings

Environment:

- Reset local infra back to the existing Doowon stack and removed accidental `doowon-dev-*` resources.
- Used `doowon-postgres` / `doowon_ai_portal_dev`, API `127.0.0.1:8000`, web `127.0.0.1:4200`, and MLX local model server `127.0.0.1:8080`.
- Browser account: `delivery-hub-member@aidoo.local`, workspace route `/w/delivery-hub/ai`.
- Browser audit checked final URL, accessibility snapshots, console logs, and page errors. Console output was limited to Vite/React DevTools messages; `agent-browser errors` still showed blank historical entries without stack/message.

Test summary:

| Area | Case | Result | Time |
|---|---|---|---|
| Docs read | Launch checklist summary | Passed. Used Docs tools and produced the expected summary artifact. | 8s |
| Docs write denial | Delete launch checklist | Passed. No write tool exposed; write guard blocked completion. DB doc/page counts stayed `36 / 36`. | 6s |
| PMS read | Delivery-delay issues | Passed, but one response used `DEMO-??`; grounding/formatting needs tightening. | 11s |
| PMS create | Approval then create | Passed in the first smoke. Tool card closed correctly after approval. | ~9s |
| PMS create reject | Reject `AI E2E Hard Reject PMS 20260430` | Passed. `pms.create_issue` rejected; DB count `0`. | 4s approval, 9s total |
| PMS update | `DEMO-50`, search first then update | Passed. `pms.search_issues` resolved the UUID before `pms.update_issue`. | 4s approval, 9s total |
| PMS comment | Internal UUID | Passed. `pms.add_comment` succeeded and DB confirmed one comment. | 4s approval, 9s total |
| PMS comment | Human key `DEMO-50` | Failed after approval. Tool received `issue_id="DEMO-50"` and no comment was created. | 4s approval |
| PMS delete | Asked to skip approval | Approval gate still appeared. After tester approval, `pms.delete_issue` succeeded. | 5s approval, 9s total |
| Planner read | Onboarding events | Passed. Used `planner.list_events` and RAG fallback. | 7s |
| Planner create | Without location | Passed. `planner.create_event` succeeded. | 4s approval, 9s total |
| Planner create reject | Reject `AI E2E Hard Reject Planner 20260430` | Passed. DB count `0`. | 4s approval, 9s total |
| Planner create | With location | Failed. `planner.create_event` validation rejected unsupported `location`; assistant text was confusing. | 7s |
| Planner update/delete | Internal UUID | Passed in smoke/stress checks. DB confirmed changes/deletes. | 4-5s approval, 9s total |
| Planner update/delete | Title reference | Failed. `planner.list_events` ran but the model did not reliably resolve title to event UUID; guard blocked false success. | 8-9s |
| Multi-app read | Docs + PMS + Planner risk summary | Useful but slow. It unexpectedly called `meeting.list_meetings`, so scope discipline is loose. | 42s |
| Read-only injection style | “수정하지 말고” prompt | Failed safely but incorrectly. Negated write intent triggered the write guard false positive. | 9s |

Fixes already made from the E2E findings:

- API forces a no-tools final answer after useful tool results when the local model repeats calls or hits the turn cap.
- Web stream closes approval-resume tool cards when the final `tool_result` arrives in a resumed stream.
- Write-intent guard blocks false success when a create/update/delete request ends without a write tool result.

Priority follow-ups:

1. Add human-facing reference resolution for AI tools: `DEMO-50`, issue titles, event titles, and similar user-visible handles must resolve to internal UUIDs before write execution.
2. Make write-intent detection negation-aware so prompts like “수정하지 말고 요약해줘” are treated as read-only.
3. Align Planner `create_event` schema with user expectations by either supporting `location` at create time or making the model ask for a follow-up update.
4. Tighten tool scope discipline for multi-app read prompts; avoid opportunistic `meeting.*` calls unless requested or justified.
5. Improve answer grounding/formatting so partial identifiers like `DEMO-??` are never emitted.
6. Clean up noisy “응답을 생성하지 못했습니다.” flashes after approval-success flows.

Final cleanup state:

- Test-created hard resources were removed: `AI E2E Hard%` PMS issue count `0`, planner event count `0`.
- `DEMO-50` was deleted during the approval-gate bypass test after tester approval; it was a test-created issue from the earlier smoke.

## 2026-04-30 Gemma 4 26B A4B MLX Bakeoff

Purpose:

- Remove Qwen-specific chat-model defaults and workarounds from code/setup.
- Try `mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit` as a drop-in local MLX chat model.
- Check whether the same Docs/PMS/Planner AI tool flow quality is preserved.

Environment:

- Hardware: Apple M5 Pro, 48GB RAM.
- Model source: https://huggingface.co/mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit
- MLX server: `127.0.0.1:8080`, API `127.0.0.1:8000`, web `127.0.0.1:4200`.
- Browser account: `delivery-hub-member@aidoo.local`, route `/w/delivery-hub/ai`.
- Gemma cache size after first load: about `15G`.

Code/setup cleanup:

- `settings.py` no longer embeds a concrete local or external chat model as a silent default.
- `scripts/mlx-serve.sh` no longer embeds a model-specific default or Qwen `enable_thinking=false` workaround. It now requires `MLX_MODEL` or `DOOWON_LLM_LOCAL_DEFAULT_MODEL`.
- `.env.example` and API README use Gemma/OpenAI values only as explicit sample configuration.
- ASR and RAG embedding/reranker Qwen-family defaults were intentionally left unchanged because they are separate model surfaces, not the local chat/internal-agent model.

Results:

| Case | Result | Time / Note |
|---|---|---|
| MLX model load | Passed | First load downloaded and started successfully. |
| `/readyz` local pool | Passed | Local pool ready with `mlx-community/gemma-4-26B-A4B-it-OptiQ-4bit`, canonical `gemma/gemma-4-26b-a4b-it`. |
| Text-only browser SSE, no tools | Passed | `allowed_app_ids=[]`, `max_tokens=4096`, answer streamed in about `4.5s`. |
| Low-token text-only smoke | Failed quality | With small `max_tokens`, Gemma often spends tokens in hidden/parsed reasoning and returns no `content_delta` before `finish_reason=length`. |
| Natural-language Docs read with tools | Failed | MLX Gemma tool parser raised `ValueError("No function provided.")`; the browser stream ended without useful tool output. |
| UI prompt with “수정하지 마” | Failed safely but incorrectly | Existing write-intent guard treated the negated word `수정` as write intent and blocked a read request. |
| PMS/Planner CRUD natural-language parity | Not accepted | Same CRUD-quality test suite cannot be considered passed because native tool-calling fails before reliable internal agent execution. |

Conclusion:

- Gemma 4 26B A4B 4-bit is usable as a local text-only chat model on this machine.
- It is **not** a safe drop-in replacement for the current OpenAI-compatible native tool-calling loop under MLX.
- Current dev local profile is reverted to `mlx-community/Qwen3.6-35B-A3B-4bit` with explicit `MLX_CHAT_TEMPLATE_ARGS='{"enable_thinking":false}'` for stable content output.
- This Qwen choice is a profile selection, not a service/runtime name. Code and tests should keep model-neutral naming.
- Model interchangeability requires an explicit capability profile, at minimum:
  - `supports_text_chat`
  - `supports_streaming_content`
  - `supports_native_tool_calling`
  - `reasoning_channel_behavior`
  - `min_safe_max_tokens`
- For Gemma-class local models, the next architecture step should be a non-native tool path: manager emits structured JSON/tool proposals as plain text, server validates and executes internal tools, then the local model summarizes. Do not rely on MLX native tool parsing for CRUD.

Follow-up priority changes:

1. Add model capability profile config instead of assuming all local OpenAI-compatible models support native tool calls.
2. Add a non-native local tool planner/gateway path for models whose chat server cannot parse function calls reliably.
3. Make write-intent detection negation-aware before any more read/write E2E bakeoffs.
4. Re-run the same Docs/PMS/Planner CRUD suite only after the non-native tool path exists.

Current Qwen quality guardrails:

1. Keep native tool-calling enabled only for profiles that pass Docs/PMS/Planner tool smoke tests.
2. Keep current Qwen profile on non-thinking mode for user-facing chat and internal summaries unless an eval explicitly enables reasoning.
3. Pin every agent run to the resolved `ModelProfile`; do not silently continue a run if the local MoE checkpoint changes.
4. Treat future MoE models as new profiles that must prove text streaming, native tool calling, reasoning channel behavior, and approval-gated CRUD parity before becoming default.

## References

- OpenAI Agents SDK overview: https://developers.openai.com/api/docs/guides/agents
- OpenAI Agents SDK running/streaming/state: https://developers.openai.com/api/docs/guides/agents/running-agents
- OpenAI Agents SDK orchestration: https://developers.openai.com/api/docs/guides/agents/orchestration
- OpenAI Agents SDK guardrails/approvals: https://developers.openai.com/api/docs/guides/agents/guardrails-approvals
- OpenAI Agents SDK tracing: https://openai.github.io/openai-agents-python/tracing/
- Claude Agent SDK overview: https://code.claude.com/docs/en/agent-sdk/overview
- Claude Agent SDK Python reference: https://code.claude.com/docs/en/agent-sdk/python
- Claude Agent SDK MCP: https://platform.claude.com/docs/en/agent-sdk/mcp

## Rollback Plan

- Keep `AIDOO_AI_MANAGER_ENABLED=false` as the default.
- If the manager path fails, route back to the existing single-loop chat path.
- If a leakage risk is found, disable AI manager, revoke provider keys if needed, and preserve affected run summaries for audit.
- If OpenAI Agents SDK blocks required behavior, keep DTOs and internal agent boundary, then replace only the manager runner implementation.
