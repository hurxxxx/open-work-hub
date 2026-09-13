# Hermes Setup and Runtime Contract

Hermes is the shared generative engine for the chatbot and registered application workloads. Open Work Hub owns identity, current admission/ACL, model policy, durable dispatch, approvals and result validation. Hermes owns model calls, reasoning, tool iterations, delegation and conversation execution. Durable application graphs still own their business stages and checkpoints; their LLM nodes use the same Hermes gateway.

## Ownership and maintenance rule

This is the single owner for Hermes installation, image/configuration, profiles, MCP, execution isolation, service topology, limits and recovery. Update the affected code, tests, INSTALL links and this document together. [AI Gateway](gateway.md) owns workload routing/security; [AI Execution](execution.md) owns application graphs and published artifacts.

## Pinned runtime contract

- Image: `nousresearch/hermes-agent:v2026.8.31@sha256:64923faeae267792bf9bf87fe3b4c4869e35004e360c7df01730ad801b74d524`.
- One multiplex gateway process serves independent native runs and conversations. A user has private profiles partitioned by `local`/`external`; a profile is not a terminal process or a concurrency slot.
- Administrator PostgreSQL model configuration selects provider, endpoint, model, route and output cap per workload. There is no fixed Hermes model and no local/external fallback. Interactive chat, the displayed runtime model and administrator model reapplication use the registered `chatbot` workload policy. Reapplication refuses a profile from another route partition.
- Before admission, the management API installs an immutable named custom provider and a profile-local credential env key. The opaque provider key changes on policy or credential rotation. Each OWH run snapshots this selection, including non-secret display metadata. Native `/v1/runs` receives only its documented provider/model/model-options overrides.
- OpenAI-compatible local/external providers (including the registered OpenRouter provider), Anthropic Messages and Gemini's official `/v1beta/openai` compatibility endpoint are supported. Custom headers use native provider `extra_headers`. Unsupported transports fail closed.
- Native auxiliary tasks explicitly follow `main`, with empty fallback chains; delegation inherits the admitted main model. The root profile is never a credential fallback for a managed profile. `model.max_tokens` is unset so the immutable provider entry supplies the output cap. Bootstrap never rewrites administrator provider/model policy.
- Compression keeps the existing threshold/target/pruning settings in `ops/hermes/bootstrap.py`. Native retries use the pinned supported configuration; no application output-repair loop calls a second provider.
- Gateway/dashboard and legacy broker use fixed loopback host ports. Hermes runtime UID/GID is `10000`; named volumes retain that ownership.
- The official image supplies Hermes, Python, Node/npm, Chromium assets, `rg`, FFmpeg and build tools. Tool registration alone does not provision optional search/media services.

## Configuration ownership map

| Contract                                                     | Owner                                                                                    |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Admin policy translation and immutable per-run snapshot      | `domains/hermes/model_policy.py`, `service.py`, AI model settings                        |
| Common registered execution/results                          | `domains/ai/gateway.py`, `domains/hermes/workloads.py`                                   |
| PostgreSQL dispatch, serialization, approvals, file metadata | `domains/hermes/models.py`, `repository.py`, `execution.py`, `mcp_router.py`, `files.py` |
| Native config/bootstrap                                      | `ops/hermes/bootstrap.py`                                                                |
| Multiplex profile discovery                                  | `ops/hermes/gateway_entry.py`                                                            |
| Run-bound tool transport and isolated execution              | `ops/hermes/plugins/owh_runtime/`                                                        |
| Controlled public egress                                     | `ops/hermes/terminal_egress.py`                                                          |
| Retired PTY drain/archive/recovery                           | `domains/hermes_terminal/`                                                               |
| Runtime settings, limits and topology                        | API/worker settings, `.env.example`, both Compose files, `scripts/prod-app-config.mjs`   |
| Chat controls/files/reconnection                             | `apps/web/src/app-modules/chatbot/`                                                      |

Paths under `domains/` are relative to `apps/api/src/open_work_hub_api/`. Keep the pin in API constants, Compose, bootstrap and legacy broker aligned. Generate API/app contracts through repository commands.

## Fresh environment setup

### Prerequisites

Follow [Development Installation](../../../INSTALL.md). Docker Engine/Compose must support named volumes, internal networks and `volume-subpath` mounts. On Docker Desktop, enable Settings → Resources → Network → **Enable host networking**, then Apply & Restart, as described in [Docker's host-network documentation](https://docs.docker.com/engine/network/drivers/host/). Verify the management health URL from the host: container-internal health alone does not prove that the API can connect. Do not install Hermes on the host.

The trusted gateway now needs the Docker socket to create execution sandboxes. Set `OPEN_WORK_HUB_HERMES_DOCKER_GID` to the socket's numeric group (default `0`); on Linux inspect it with `stat -c '%g' /var/run/docker.sock`. Never make the socket world-writable. The gateway uses the image's Python entrypoint directly because the stock entrypoint resets supplemental groups; the official environment provider still owns sandbox lifecycle.

Configure a provider/model in administrator LLM settings and verify that its endpoint is reachable from the host-network gateway. A local-only installation needs no OpenRouter key. Development startup accepts an enabled Hermes without that key; egress health requires the public CA and listening proxy, not a legacy token file. `OPENROUTER_API_KEY` is optional legacy egress configuration for draining existing Terminal sessions; if retained, it stays only in the trusted egress container. It is not the new model-policy source.

### Development checkout

API and worker both require `jsonschema` in their default dependency groups for shared structured workloads; optional local-ML extras are not a runtime prerequisite. After updating the checkout, sync both locked Python environments before starting services:

```bash
uv sync --frozen --python 3.12 --directory apps/api
uv sync --frozen --python 3.12 --directory apps/worker
```

1. Preserve existing ignored `.env`; add missing keys from `.env.example` without replacing credentials.
2. Set `OPEN_WORK_HUB_HERMES_ENABLED=true` explicitly. Generation fails unavailable when Hermes is disabled; it does not silently use the old SDK. The historical dev script can derive enablement from an OpenRouter key only when this flag is absent, so explicit configuration is required for local providers.
3. Configure distinct runtime, management and MCP control secrets. Keep declared URL/port pairs aligned.
4. Set `OPEN_WORK_HUB_HERMES_MAX_CONCURRENT_RUNS=10` unless capacity planning requires a different positive value. It is a global OWH dispatch limit, not a per-user limit. Match worker concurrency to the intended throughput.
5. Start infrastructure, migrate through the normal API startup path, and start API/web/worker:

```bash
./scripts/dev-infra.sh up
./scripts/dev-infra.sh status
./dev.sh --with-worker --no-infra
```

6. Configure the active provider/model and workload routes in Admin LLM settings. Open the chatbot; its work/files panel exposes concurrent runs, stop, uploaded/generated files and owned legacy Terminal archives. A worker and the shared Beat scheduler are required for interactive queue recovery.

Before saving any provider credential, configure a private `OPEN_WORK_HUB_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY` for API and worker, preserving an existing key. For OpenRouter, include `openrouter` in the configured external provider allowlists, enable its administrator provider entry at `https://openrouter.ai/api/v1`, save the credential in that entry, discover and approve the selected model's capabilities, then select it for the external workload route. A legacy `OPENROUTER_API_KEY` alone does not configure the administrator model policy. Model selection is stored in PostgreSQL and is never a source-code default.

Development ports: runtime `18642`, dashboard `19119`, legacy broker `18765`. Production: `8642`, `9119`, `8765`. The broker container always listens on `18765`. Never select an arbitrary fallback port when a declared port is occupied.

### Production checkout

Production remains governed by the [Release Domain](../release/README.md); this implementation does not authorize deployment. Provide enabled Hermes, distinct non-placeholder control secrets, aligned loopback runtime/management/broker URLs and ports, the API MCP URL, broker relay/socket paths, an explicit non-development resource namespace, queue capacity and Docker socket group. Keep `OPEN_WORK_HUB_HERMES_PROFILE_CLONE_SOURCE=default` for the retained legacy bootstrap contract; new user route partitions are created fresh through the native profile API.

```bash
node scripts/prod-app-config.mjs .env
./scripts/prod-app.sh status
```

The validator rejects disabled Hermes, missing/duplicate control secrets, unsafe URL/port pairs, port collisions, invalid namespaces and an invalid legacy key when supplied. Provider credentials are configured through administrator LLM settings. Run Alembic before application startup.

The forward migration merges only enabled chatbot/Terminal audiences. Selected user and group grants are unioned; an enabled `all` audience remains `all`. Disabled-app grants never expand the resulting enabled audience. Terminal admission and launcher registration are retired. Personal history and archive ownership are unchanged. Migration also changes old Bento adapter overrides to `hermes`.

The schema downgrade deliberately refuses to merge or discard private route partitions. An incompatible rollback uses the [paired database/configuration rollback procedure](../release/README.md#incompatible-database-and-configuration-cutovers), restoring matching application revision, database, env and host-mounted Hermes helpers, including the plugin directory. It cannot reverse external actions or restore process memory. Preserve profile/object volumes and never adopt another database's resource namespace.

## Identity, tools and approvals

User APIs are under `/api/v1/agent`; administrative inventory/reconciliation remains under `/api/v1/admin/hermes`. Administrator role never grants another user's conversation, file or archive access.

Internal MCP requires a profile-derived HMAC bearer plus `X-Hermes-Run-Id` from Hermes' native approval context. The model cannot supply this identity. Every invocation resolves that exact active run/profile and rechecks active account, owning-app admission, run tool scope and source ACL. Discovery without a run supplies schemas only; it never authorizes a call. There is no newest-run or single-active-profile inference. The pinned management API stores MCP bearer headers as environment references. The narrow run-bound transport uses native `tools.mcp_tool._interpolate_env_vars` to resolve the current profile secret scope and rejects unresolved references; the public middleware does not expose a resolved MCP transport. Keep this pinned internal helper covered by native-image and fail-closed regression checks.

Write consent is bound to the exact server, tool and canonical argument SHA-256 before the approval is shown. Only one-time approve/deny is exposed. Consumption is atomic, expires after five minutes and cannot be replayed for different arguments or another run. Stopping/revoked runs cannot invoke tools. Provider errors, absent context and transport failures block tool dispatch.

Globally unique physical MCP names prevent Hermes' process-global connection registry from mixing profiles. Research source enablement remains an audited platform policy at `/admin/ai-tools`; profile reconciliation applies it. Browser, image, voice, cron tools and other integrations without an OWH execution policy are not exposed in interactive API toolsets. Interactive tools include terminal/file/code execution, web, skills, memory, todo, session search, delegation and entitled MCP tools. Optional web services still need their official credentials.

Structured application workloads use `owh_submit_result`. JSON Schema and registered semantic validators return bounded errors to the same Hermes loop; an invalid result never becomes successful text fallback. Terminal completion without a required accepted object becomes `invalid_output`. Common results carry text, structured output and usage; app code consumes that contract rather than raw SDK tool calls. Authoritative text and structured results are bounded to 2 MB separately from the smaller retained event payloads; oversize text fails explicitly. Bento plan/document/edit and RAG/query rewrite use schemas. Mail/meeting/recording and graph LLM nodes use the same registered gateway. Execution owner is explicit for system tasks while the original audit actor is retained.

Native tools are denied for application workloads unless the registered descriptor explicitly permits a read-only tool. `web_search.answer` permits Hermes `web_search` and `web_extract`; it retains its current administrator-controlled external model route and external-data policy. Each native call needs a durable, run-locked admission, bounded by the request budget (maximum 20 calls across search and extraction). The snapshot is intersected with the current registry before execution. Web search returns a validated answer/citations object through the common Hermes result contract; it no longer invokes the Anthropic SDK directly. Native Tool Search may describe schemas, but its `tool_call` bridge still executes through this middleware and admission check.

Native cron controls remain available through a separate `-jobs` profile with all MCP servers removed. They use administrator policy at profile reconciliation. Jobs do not receive an OWH interactive run or sandbox identity; the managed middleware denies tool execution without that identity. Native cron scheduling is separate from the OWH run queue and is not a route to app writes.

## Durability and concurrency

PostgreSQL owns user/profile/session/run bindings, inputs, sanitized events, exact approvals, execution leases and the dispatch outbox. Publication is at least once; native run creation uses the durable OWH run ID as its idempotency key. Client keys are bound to request digests. Active leases fence duplicate consumers.

Admission atomically enforces the global queue capacity (default ten) and oldest-first execution within a conversation. Different conversations from the same user can run concurrently. Capacity/session waits defer the outbox without consuming retry attempts. Application callers can drive their staged workload through the same durable dispatcher; lost callers are recovered through the outbox. Specialized graph checkpoints remain owned by LangGraph.

Synchronous application generation runs in worker threads; calling it directly on the ASGI event loop fails before staging, so Hermes callbacks can still reach the API. MCP handlers and synchronous conversation preparation use the ASGI thread pool. The [RAG tool contract](../rag/README.md) returns evidence to the calling agent and avoids a nested generation that would wait behind its own occupied queue slot.

OWH stop intent commits before native stop. The dispatcher rechecks current owning-app access after claim and during event consumption; revocation triggers native stop. Maintenance expires approvals, revokes jobs, cleans retained events/files and recovers stale dispatches under fenced database leases. Shared Beat health matters even when the API/gateway are healthy.

The browser consumes OWH's replayable SSE projection. Changing conversations or closing a stream detaches the observer; explicit stop cancels the run. Returning to an active conversation reconnects without creating another run. Reconnects back off from one to thirty seconds within the one-hour bound; a closed event log resolves the durable run projection. Application-stage streaming currently emits completed stage output; interactive progress/tool/approval/text events stream live.

## Execution workspace and files

The shared gateway executes terminal, native file tools and `execute_code` in an isolated `/workspace` container via Hermes' official environment provider. Sandboxes have no host home/config/credential bind, no Docker socket, no provider credentials, a read-only root, UID/GID 10000, dropped capabilities, no new privileges, two CPUs, 2 GiB memory/no swap, 512 processes and bounded tmpfs. Workspace capacity is 256 MiB; `/tmp` is 256 MiB and home/`/opt/data` are 64 MiB each. The image's implicit `/opt/data` volume is explicitly replaced by tmpfs.

Only the public egress CA file is mounted through a volume subpath, not the adjacent legacy proxy token. The internal sandbox network and iron-proxy are the only public egress path. Proxy loopback, private, link-local and metadata CIDR denial remains enabled; no host port is published. New model calls happen in the trusted gateway using administrator credentials. Provider-token replacement is retained only for old Terminal runners when a legacy key is supplied. The upstream response-header timeout is bounded at 300 seconds.

User uploads are authenticated bounded binary bodies (`application/octet-stream`, percent-encoded `X-File-Name`), at most 64 MiB and sixty seconds. Same-conversation run admission serializes with uploads; uploads during an active run are rejected. Downloads recheck owner/session/admission and send attachment, no-store and nosniff headers.

Successful terminal operations save regular `/workspace` files to object storage before their tool result returns; later environments restore them. PostgreSQL owns path/hash/size/retention metadata and durable object upload reservations/deletion intent. Failed object deletion is retried without losing its intent. Per-session bounds are 256 MiB and 10,000 files; path traversal, symlinks/special files and internal runtime paths are rejected. Retention uses the existing thirty-day artifact setting. Replacing a saved path replaces its saved content; deleting it inside the transient sandbox preserves the last saved file for recovery.

A sandbox/process is disposable. Native lifecycle cleanup removes it and a one-hour container deadline bounds gateway-crash orphans. Packages, running processes and memory are not restored. Only acknowledged file snapshots are durable; files still changing in a background process or at a hard crash may not be saved. A save failure returns a tool error requiring retry.

## Retired Terminal recovery

New raw Terminal session creation returns `410`; PTY attachment is closed. The chatbot replaces its launcher and interactive UI. Owned legacy session/archive APIs remain available under current chatbot admission. They do not expose another user's history, including to administrators. Codex Terminal is a separate unchanged app.

Retain the legacy broker/egress services and their namespaced resources while old sessions drain and archives remain. Terminal maintenance stops revoked sessions, archives files/profile state, retries interrupted archives with fenced claims and quarantines genuinely failed/missing workspaces for recovery. Do not remove broker resources merely because the launcher is gone. Legacy archive limits/timeouts retain their existing typed settings. No process, installed package or mutable container filesystem is migrated into the new sandbox.

Replacing the database requires a fresh explicit `OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE`. Stop exact old-namespace active runners before cutover and retain the matching env/resources for rollback. Brokers must never clean or adopt another namespace. Never run global Docker prune or delete profile/workspace volumes as a setup fix.

## Pinned upstream gaps

Use official public surfaces first. The remaining adapters are version-bound to the image above:

- `gateway_entry.py`: multiplex API startup discovers only the launch profile's MCP servers. It invokes native idempotent discovery for the authenticated profile and rejects admission when discovery or the required plugin fails. Remove it when an official profile-discovery lifecycle hook covers this requirement.
- `owh_runtime` tool middleware: native HTTP MCP headers are profile-static. A separate request adds native run identity without mutating shared connections. Native middleware exceptions fall through, so this callback catches policy/import/transport failures and returns an error. Remove the forwarding adapter when official per-call authenticated headers support trusted run context.
- `owh_runtime/sandbox.py`: native `DockerEnvironment` unconditionally mounts host credentials/skills/cache and has no supported off switch. The adapter implements only the public `BaseEnvironment` transport/provider contract with safe Docker arguments; Hermes retains wrapping, timeout/interrupt and environment lifecycle. Replace it when native Docker configuration can guarantee no host mounts plus file snapshot hooks.
- `terminal_egress.py`: the public egress setup CLI is interactive and cannot express these container listeners and deny policy. The adapter uses exported iron-proxy functions; replace it when the CLI exposes the needed unattended configuration.

## Operations and change checklist

Gateway waits for successful bootstrap and healthy egress. Dashboard/API/worker dependencies remain explicit in both Compose files. The gateway uses official `--no-supervise`; Compose owns restart. Keep the legacy broker healthy during drain. Restart the affected Compose control services after bootstrap/plugin/credential-transport changes; DB model changes apply at subsequent admission without rewriting already admitted provider snapshots.

Non-inference development checks:

```bash
./scripts/dev-infra.sh status
curl --fail http://127.0.0.1:18765/healthz
curl --fail http://127.0.0.1:19119/api/health
docker inspect --format '{{.State.Health.Status}}' open-work-hub-dev-hermes-gateway
docker inspect --format '{{.State.Health.Status}}' open-work-hub-dev-hermes-terminal-egress
```

Do not print container envs, profile config/credentials, prompts or sensitive runtime logs. [Release storage policy](../release/README.md#build-and-test-storage) must preserve current/previous images, container references, user profile volumes and archive objects.

For every runtime change: inspect the pinned public surfaces and reassess each adapter, update the ownership map's affected files and INSTALL, verify credential/network/owner isolation, queue concurrency and same-conversation order, result correction, cancellation/recovery and workspace retention. Run focused checks first, then shared contracts:

```bash
(cd apps/api && uv run --python 3.12 --group dev pytest tests/test_hermes_integration.py tests/test_hermes_runtime.py tests/test_hermes_plugin.py tests/test_hermes_bootstrap.py tests/test_hermes_gateway_entry.py tests/test_hermes_terminal.py tests/test_hermes_terminal_egress.py tests/test_admin_hermes_tools.py -q)
(cd apps/api && uv run --python 3.12 --group dev pytest tests/test_hermes_migration.py tests/test_alembic_migrations.py -m migration -q)
(cd apps/worker && uv run --python 3.12 --group dev pytest tests/test_worker_task_registration.py tests/test_app_execution_policy_workers.py tests/test_ai_graph_tasks.py -q)
pnpm check:api-contract
pnpm check:api-architecture
pnpm check:web-architecture
pnpm nx typecheck web
pnpm check:env-contract
pnpm check:alembic-graph
pnpm check:path-hardcoding
pnpm test:prod-app
pnpm check:skills
git diff --check
```

Use the repository's explicit non-production PostgreSQL test configuration for integration/migration tests. Verify actual pinned-image environment/plugin loading, two isolated sandboxes and file save/restore without a paid model call. A health check alone does not establish live provider quality or end-to-end UI behavior; report unavailable validation.

## Official references

- [Open WebUI integration](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/open-webui): OpenAI-compatible UI integration; OWH uses native runs for durable controls.
- [Native API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server): runs, sessions, SSE and lifecycle controls.
- [Pinned implementation](https://github.com/NousResearch/hermes-agent/tree/v2026.8.31): inspect matching profile config, plugins/middleware, terminal environment provider, approval context and iron-proxy implementation before an upgrade.
- [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai).
