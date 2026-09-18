# AI Gateway

Generative model calls use registered workloads and the common execution gateway. App code never chooses provider SDK or external HTTP endpoint.

Approval replay, graph execution, and artifact state are owned by [AI Execution](execution.md).

## Contract

- Workload registers ID, owner, routes, capability, output cap, audit/tracing, external-data policy.
- Admin saves multiple named connections (OpenRouter, OpenAI, Anthropic, Gemini or OpenAI-compatible). Connection IDs are distinct from provider/transport kinds. Local connections support optional API-key authentication.
- Global defaults → app defaults → `(app_id, workload_id)` overrides select connection/model/output cap per local/external route. Omitted values inherit; saving only a cap does not pin a resolved model. Output caps resolve explicit workload → app → global values, then the registered workload default (32K local / 64K external unless the workload declares another default). Untouched migration-seeded global caps are cleared by `llm_cap_defaults_20260918`; administrator edits are preserved. Global model changes use the selected connection default, while app/workload model overrides stay explicit.
- Runtime policy is DB-only: missing/disabled connections, missing credentials, inactive catalog models, incompatible capabilities and disallowed routes fail closed. No unique-provider or environment fallback is used. Provider allowlists remain infrastructure/security policy.
- External connections must also be admitted by both `OPEN_WORK_HUB_LLM_EXTERNAL_ALLOWED_PROVIDERS` and `OPEN_WORK_HUB_AI_ALLOWED_EXTERNAL_PROVIDERS` using their provider kind (for example `openrouter` or `openai_compatible`). Saving a connection does not widen either deployment allowlist; local compatible connections use the local host policy instead.
- App catalog registrations declare `ai_capability_modules`; the AI registry imports each hook once and fails for missing hooks. A shared workload has independent settings for each owning app.
- Credentials are encrypted per connection with `OPEN_WORK_HUB_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY`. GET returns only `has_api_key`; omission preserves, replacement rotates, explicit clearing removes the key. The master key remains outside the DB and must be preserved for restores.
- Structured output and tools require `tool_calling`, including tools/schema supplied at runtime. Model discovery does not approve capabilities automatically. Override writes validate the effective inherited route using the execution resolver before commit. Saved connection probes release the DB during I/O, recheck both connection and selected-model versions, and are invalidated by model edits/discovery.
- `execute_llm` and `stream_llm` return safe execution metadata, never credential-bearing transport configuration. Interactive Hermes sessions retain their lifecycle while resolving the same model policy.
- No local/external automatic fallback.
- External transfer passes classification, masking, approval policy, and audit.
- Tool execution checks the current user/execution principal, owning-app admission, descriptor discoverability, and
  source ACL; write tools also require approval.
- Audit records actor, app, workload, provider/model, token usage, trace ID.
- Every registered text/structured/stream completion delegates to [Hermes](hermes.md). Administrator workload policy still resolves model, data transfer and caps before dispatch. No SDK fallback is used when Hermes is unavailable.
- `AgentRuntimeAdapter` preserves the application orchestration interface; Bento registers only the Hermes implementation.
- `execution_user_id` declares a private runtime owner for system work without replacing its audit actor.
- `LlmCompletionResult.structured_output` is accepted through registered schema/semantic validation inside the Hermes loop. Apps never parse provider tool-call envelopes.

## Local Runtime

- Register the endpoint and optional key in Admin → LLM connections. vLLM and Ollama presets use OpenAI-compatible `/v1` endpoints; OWH does not install/start these servers or manage model downloads/GPU allocation. The selected model must actually support the declared tools/stream/structured behavior.
- Local endpoint hosts must be listed explicitly in `OPEN_WORK_HUB_LLM_LOCAL_ALLOWED_HOSTS`; include the address reachable from API and Hermes. Metadata, link-local and multicast addresses are rejected. External endpoints require public HTTPS on port 443. Model discovery does not follow redirects.
- Use the saved-connection test after approving a model. This checks reachability/model availability; it does not certify every capability. Verify an actual structured/tool workload before switching the global default.
- Model selection lives in Admin model catalog/routing, not env or app code.
- Non-secret LLM timeouts and preprocessing-model defaults live in the tracked
  [runtime configuration](../release/README.md#public-runtime-configuration); active model routing stays in the database.
- Docker Model Runner profile uses OpenAI-compatible API.
- Dev default: `http://127.0.0.1:12434/engines/v1`.
- Use `scripts/dev-local-qwen.sh` for model install/status/smoke.
- Qwen `reasoning_effort=none` maps to `chat_template_kwargs.enable_thinking=false`.
- Runtime health retains connection identity, including multiple connections of one provider family; local serving status enumerates enabled local connections.
- Legacy core adapter types remain for transport/health compatibility; application generation enters only the registered gateway.
