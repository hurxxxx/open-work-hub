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
- Bootstrap and profile model-policy synchronization apply the same [conversation context policy](#conversation-context-policy), including profiles created after gateway startup. Native retries use the pinned supported configuration; no application output-repair loop calls a second provider.
- OpenAI-wire workload temperatures, including zero, are preserved through the named provider's supported `extra_body` request overrides. The provider identity and run snapshot include the requested value so concurrent workloads cannot overwrite each other's sampling settings. The pinned Anthropic Messages request builder drops these overrides; an explicit temperature therefore fails with the common `LlmProviderError` before profile provisioning or run staging. Anthropic calls that omit temperature retain native defaults. Native `model_options` supports reasoning/service tier, not temperature. The public request middleware does not expose the immutable run's request overrides; do not infer sampling from a mutable profile default or silently change routes.
- Gateway/dashboard and legacy broker use fixed loopback host ports. Hermes runtime UID/GID is `10000`; named volumes retain that ownership.
- The official image supplies Hermes, Python, Node/npm, Chromium assets, `rg`, FFmpeg and build tools. Tool registration alone does not provision optional search/media services. The image does **not** supply Python or Node Playwright; static-result verification uses `owh_preview` and the installed headless shell without another browser SDK or model call.

## Configuration ownership map

| Contract                                                     | Owner                                                                                    |
| ------------------------------------------------------------ | ---------------------------------------------------------------------------------------- |
| Admin policy translation and immutable per-run snapshot      | `domains/hermes/model_policy.py`, `service.py`, AI model settings                        |
| Common registered execution/results                          | `domains/ai/gateway.py`, `domains/hermes/workloads.py`                                   |
| PostgreSQL dispatch, reconciliation, approvals, file metadata | `domains/hermes/models.py`, `repository.py`, `execution.py`, `maintenance.py`, `mcp_router.py`, `files.py`, `file_router.py` |
| Native config/bootstrap and compression policy               | `ops/hermes/bootstrap.py`, `domains/hermes/client.py`, `domains/hermes/model_policy.py` |
| Multiplex discovery and native admission cancellation       | `ops/hermes/gateway_entry.py`, `domains/hermes/client.py`                                 |
| Run-bound tool transport and isolated execution              | `ops/hermes/plugins/owh_runtime/`                                                        |
| Controlled public egress                                     | `ops/hermes/terminal_egress.py`                                                          |
| Retired PTY drain/archive/recovery                           | `domains/hermes_terminal/`                                                               |
| Runtime settings, limits and topology                        | API/worker settings, `.env.example`, both Compose files, `scripts/prod-app-config.mjs`   |
| Chat controls/files/reconnection                             | `apps/web/src/app-modules/chatbot/`                                                      |

Paths under `domains/` are relative to `apps/api/src/open_work_hub_api/`. Keep the pin in API constants, Compose, bootstrap and legacy broker aligned. Generate API/app contracts through repository commands.

## Conversation context policy

`managed_compression_policy()` supplies the native compression settings for profile synchronization and the retained legacy model-update path. `ops/hermes/bootstrap.py` applies the same settings at startup; `test_hermes_bootstrap.py` checks parity because bootstrap runs outside the API package. Fresh local/external profiles receive the policy before activation, and existing profiles and isolated scheduled-job profiles receive it on reconciliation. A rejected configuration update fails admission and is not cached as successful.

The managed settings enable compression with `threshold=0.50`, `threshold_tokens=100000`, `target_ratio=0.20`, and `protect_last_n=20`. Proactive tool-result pruning starts at `48000` tokens, with `8000` minimum result characters and `4096` minimum reclaimed tokens. The token threshold triggers compaction; it is not a hard per-request input limit. Hermes owns token accounting, model-window adjustments, summary/tail selection and persistence. Auxiliary compression follows the admitted main model with no fallback chain. The `session_search` restriction under [identity, tools and approvals](#identity-tools-and-approvals) still applies.

For a development update limited to this API/worker profile policy, load the updated application code with `./dev.sh --restart --with-worker --no-infra`. The next profile reconciliation applies the settings without gateway recreation or user-profile recreation. New profiles receive them immediately; existing profiles follow the reconciliation cache's normal expiry. Bootstrap/plugin/Compose changes instead follow [the gateway update procedure](#updating-an-existing-development-installation).

## Fresh environment setup

### Prerequisites

Follow [Development Installation](../../../INSTALL.md). Docker Engine/Compose must support named volumes, internal networks and `volume-subpath` mounts. On Docker Desktop, enable Settings → Resources → Network → **Enable host networking**, then Apply & Restart, as described in [Docker's host-network documentation](https://docs.docker.com/engine/network/drivers/host/). Verify the management health URL from the host: container-internal health alone does not prove that the API can connect. Do not install Hermes on the host.

The trusted gateway now needs the Docker socket to create execution sandboxes. Set `OPEN_WORK_HUB_HERMES_DOCKER_GID` to the socket's numeric group (default `0`); on Linux inspect it with `stat -c '%g' /var/run/docker.sock`. Never make the socket world-writable. The gateway uses the image's Python entrypoint directly because the stock entrypoint resets supplemental groups; the official environment provider still owns sandbox lifecycle.

Compose owns the physical sandbox network and public egress CA volume. Its `x-hermes-sandbox-resources` anchors supply the existing service-internal `OWH_HERMES_TERMINAL_SANDBOX_NETWORK` and `OWH_HERMES_TERMINAL_EGRESS_CLIENT_VOLUME` values to both the gateway and retained broker, and name the actual Docker resources. These are deployment wiring, not additional user `.env` settings. `OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE` identifies database/legacy-runner ownership; never derive physical egress resource names from it. Custom deployments must provide both internal resource values to the gateway and retain an internal network plus the CA file-only mount.

Native file writes additionally require a Linux Docker host/VM with [Landlock ABI 3 or newer](https://docs.kernel.org/userspace-api/landlock.html) enabled (x86_64 or aarch64, with its syscalls permitted by the container security profile). The native-tool smoke below checks enforcement inside the actual sandbox. Both gateway Compose definitions set the upstream `HERMES_WRITE_SAFE_ROOT=/workspace`; custom deployments must retain this fixed value. No additional user `.env` setting or global unattended approval is required.

Configure a provider/model in administrator LLM settings and verify that its endpoint is reachable from the host-network gateway. A local-only installation needs no OpenRouter key. Development startup accepts an enabled Hermes without that key; egress health requires the public CA and listening proxy, not a legacy token file. `OPENROUTER_API_KEY` is optional legacy egress configuration for draining existing Terminal sessions; if retained, it stays only in the trusted egress container. It is not the new model-policy source.

### Required file storage

MinIO is required for Hermes chatbot workspace files, including files created by
`terminal` and `execute_code`. PostgreSQL stores file metadata; MinIO stores the
bytes. A healthy gateway and successful sandbox creation do not verify storage.
Start MinIO before accepting chatbot file work. A remote MinIO deployment may be
used instead of a local container, but it must be reachable from both API and worker.

For a local development installation, use the pinned service and persistent volume:

```bash
(
  source scripts/dev-env.sh
  dev_docker compose --env-file "$(dev_compose_env_file)" \
    -f "$(dev_compose_file)" up -d --no-deps minio
)
```

Match `OPEN_WORK_HUB_MINIO_ENDPOINT`, `OPEN_WORK_HUB_MINIO_ACCESS_KEY`,
`OPEN_WORK_HUB_MINIO_SECRET_KEY` and `OPEN_WORK_HUB_MINIO_BUCKET` in the actual
API/worker environment to the service. For local Compose, the credentials must
match `OPEN_WORK_HUB_INFRA_MINIO_ROOT_USER` and
`OPEN_WORK_HUB_INFRA_MINIO_ROOT_PASSWORD`, and the endpoint port must match
`OPEN_WORK_HUB_INFRA_MINIO_PORT`. Preserve existing credentials and storage;
record installed credentials in `.auth_info` under the installation guide's rules.

Verify authenticated bucket access and a synthetic object write/read/delete using
the application settings. Then run the sandbox checks below and create/reopen a
saved file through the chatbot. The sandbox smoke scripts mock file RPC, so their
PASS results alone do not establish API-to-MinIO connectivity. A
`Workspace files could not be saved` error requires checking the API's first
storage error, including refused connections, credentials and bucket permissions,
before changing sandbox lifecycle code. Recreating a sandbox cannot restore a
missing storage service or recover bytes that were never saved.

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
bash scripts/dev-infra.sh up
bash scripts/dev-infra.sh status
./dev.sh --with-worker --no-infra
```

6. Configure the active provider/model and workload routes in Admin LLM settings. Open the chatbot; its work/files panel exposes concurrent runs, stop, uploaded/generated files and owned legacy Terminal archives. A worker and the shared Beat scheduler are required for interactive queue recovery.

7. Complete the [sandbox execution check](#sandbox-execution-check), including the terminal call in a new chatbot conversation. Gateway health and a completed conversation alone do not prove that a tool executed successfully.

Before saving any provider credential, configure a private `OPEN_WORK_HUB_AI_MODEL_CREDENTIAL_ENCRYPTION_KEY` for API and worker, preserving an existing key. For OpenRouter, include `openrouter` in the configured external provider allowlists, enable its administrator provider entry at `https://openrouter.ai/api/v1`, save the credential in that entry, discover and approve the selected model's capabilities, then select it for the external workload route. A legacy `OPENROUTER_API_KEY` alone does not configure the administrator model policy. Model selection is stored in PostgreSQL and is never a source-code default.

Development ports: runtime `18642`, dashboard `19119`, legacy broker `18765`. Production: `8642`, `9119`, `8765`. The broker container always listens on `18765`. Never select an arbitrary fallback port when a declared port is occupied.

### Updating an existing development installation

Run these commands from the development checkout root after updating the gateway plugin or Compose sandbox resource wiring. Preserve the current configuration according to [resource ownership](#prerequisites); this update requires no new user `.env` keys.

1. Finish or stop active development chatbot runs. Confirm that bootstrap has completed successfully and egress is healthy using the [development health checks](#operations-and-change-checklist). If the infrastructure is missing, first use `bash scripts/dev-infra.sh up` from the fresh-install procedure; the targeted command below intentionally does not start dependencies.
2. Recreate the gateway to load both the updated plugin and Compose-provided resource values. `--force-recreate` also covers plugin-only updates, whose bind-mounted source change does not change the container configuration. A Docker restart cannot add new container environment values.

```bash
(
  source scripts/dev-env.sh
  dev_docker compose --env-file "$(dev_compose_env_file)" \
    -f "$(dev_compose_file)" \
    up -d --no-deps --force-recreate --wait hermes-gateway
)
```

Keep chatbot traffic paused between gateway recreation and application restart when the plugin file-checkpoint protocol changes.

3. After the gateway is healthy, restart the development web, API and worker to load the matching application code:

```bash
./dev.sh --restart --with-worker --no-infra
```

4. Run the [sandbox execution check](#sandbox-execution-check). If it fails, follow [sandbox startup recovery](#sandbox-startup-recovery) and repeat the check after recovery. Keep the gateway-before-API update order described in [pinned upstream gaps](#pinned-upstream-gaps).

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

Write consent is bound to the exact server, tool and canonical argument SHA-256 before the approval is shown. Only one-time approve/deny is exposed. Consumption is atomic, expires after five minutes and cannot be replayed for different arguments or another run. Stopping/revoked runs cannot invoke tools. Provider errors, absent context and transport failures before submission block tool dispatch. The middleware-owned HTTPX transport keeps connection/write/control waits at 30 seconds and permits 3,900 seconds for `tools/call` response reads, covering the bounded one-hour application workload and dispatch/cleanup overhead. Native MCP SDK timeout settings do not govern this separate HTTP request. Calls are never automatically retried; an unconfirmed response after submission is reported as an unknown outcome requiring result verification, rather than claiming that execution was blocked.

Globally unique physical MCP names prevent Hermes' process-global connection registry from mixing profiles. Research source enablement remains an audited platform policy at `/admin/ai-tools`; profile reconciliation applies it. General browser, image, voice, cron tools and other integrations without an OWH execution policy are not exposed in interactive API toolsets. The separately registered `owh_preview` only renders saved conversation HTML in an offline container under the current authenticated interactive run; it cannot navigate public URLs or invoke app writes. Interactive tools advertise terminal/file/code execution, web, skills, memory, todo, delegation and entitled MCP tools, subject to native approval and file guards. Unattended `api_server` calls can use `execute_code` only after authenticated OWH admission and verification of the actual isolated OWH environment. Global unattended approval remains denied; the exception changes only the whole-script guard for that call. Native `session_search` is excluded from official API toolsets and denied by middleware, including direct session reads and stale profile configurations. The pinned history search reads shared profile workload transcripts without a trusted OWH app/resource ACL filter; source labels or model-supplied filters cannot provide authorization. Re-enable it only through a source-authorized OWH contract or an upstream trusted filtering capability. Optional web services still need their official credentials.

Structured application workloads use `owh_submit_result`. JSON Schema and registered semantic validators return bounded errors to the same Hermes loop; an invalid result never becomes successful text fallback. Terminal completion without a required accepted object becomes `invalid_output`. Common results carry text, structured output and usage; app code consumes that contract rather than raw SDK tool calls. Authoritative text and structured results are bounded to 2 MB separately from the smaller retained event payloads; oversize text fails explicitly. Bento plan/document/edit and RAG/query rewrite use schemas. Mail/meeting/recording and graph LLM nodes use the same registered gateway. Execution owner is explicit for system tasks while the original audit actor is retained.

Retained application tool/approval steps (including `/chatbot/chat/stream` and graph agent nodes) request a typed next-action object through the same `owh_submit_result` path. The pinned native run API has no raw provider-turn response, so `tool_decisions.py` translates only this existing application contract: eligible tool names, argument schemas, required/named/disabled choice and parallel limits constrain the result. Prior tool exchanges remain role-labelled conversation data. The existing application dispatcher retains ACL, write consent, checkpoints and budgets; the translator never executes a tool. Missing or invalid results fail closed. Remove this translation when those callers adopt native interactive runs and approval events. Native `/agent` chat continues to use Hermes' own tool loop directly.

Session pagination orders local activity by accepted user run admission, with a stable ID tie-breaker. Listing sessions and replaying an idempotent request do not advance activity timestamps.

Native tools are denied for application workloads unless the registered descriptor explicitly permits a read-only tool. `web_search.answer` permits Hermes `web_search` and `web_extract`; it retains its current administrator-controlled external model route and external-data policy. Each native call needs a durable, run-locked admission, bounded by the request budget (maximum 20 calls across search and extraction). The snapshot is intersected with the current registry before execution. Web search returns a validated answer/citations object through the common Hermes result contract; it no longer invokes the Anthropic SDK directly. Native `tool_search`/`tool_describe` inspect the current native tool assembly after authenticated interactive admission; they do not authorize execution. Native Tool Search may describe schemas, but its `tool_call` bridge still executes through this middleware and admission check.

Native cron controls remain available through a separate `-jobs` profile with all MCP servers removed. They use administrator policy at profile reconciliation. Jobs do not receive an OWH interactive run or sandbox identity; the managed middleware denies tool execution without that identity. Native cron scheduling is separate from the OWH run queue and is not a route to app writes.

## Durability and concurrency

PostgreSQL owns user/profile/session/run bindings, inputs, sanitized events, exact approvals, execution leases and the dispatch outbox. Publication is at least once; native run creation uses the durable OWH run ID as its idempotency key. Client keys are bound to request digests. Active leases fence duplicate consumers.

Admission atomically enforces the global queue capacity (default ten) and oldest-first execution within a conversation. Different conversations from the same user can run concurrently. Capacity/session waits defer the outbox without consuming retry attempts. Nested generation from a server-bound MCP tool retains its parent run ID. It can use a free slot, but when admission finds the global limit full it atomically fails with `hermes.nested_capacity` instead of waiting behind the parent. This includes meeting insight refresh tools: the caller receives the common LLM failure immediately, and outbox recovery cannot generate a late result. Top-level workloads retain normal capacity waiting. Application callers can drive their staged workload through the same durable dispatcher; lost callers are recovered through the outbox. Specialized graph checkpoints remain owned by LangGraph.

Provisioning and execution transport failures use the common `LlmProviderError` contract so application callers retain localized failure responses and LLM error audit records. Synchronous application generation runs in worker threads; calling it directly on the ASGI event loop fails before staging, so Hermes callbacks can still reach the API. MCP callbacks use AnyIO’s explicit thread limiters: eight control/result operations and sixteen potentially long file/tool operations per event loop, separate from the default ASGI pool. Their async database dependency closes its session through control capacity. Synchronous public callers and nested MCP generation can wait without consuming the capacity needed to submit their results. Synchronous conversation preparation uses the default ASGI thread pool. The [RAG tool contract](../rag/README.md) returns evidence to the calling agent and avoids a nested generation that would wait behind its own occupied queue slot.

OWH stop intent commits before native stop. Cancelling an application caller returns its execution lease and persists stop intent; a confirmed native terminal response frees capacity immediately, while a control outage retains the stop for normal outbox recovery. A claimed run with no returned native ID remains `stopping`, retains its original input and continues to occupy capacity. Recovery sends the original request/key to the runtime-key-authenticated, profile-scoped `/v1/owh/runs/cancel-admission` adapter. It atomically uses Hermes' durable idempotency reservation: an existing admission returns its native ID for stopping; an absent admission gets a cancelled reservation so a delayed creation request cannot start an agent. It never replays ordinary creation to find an ID. Unsupported gateways, unavailable durable storage and exhausted worker/publication retries leave cancellation recoverable with backoff. Cleanup remains permitted after profile/app revocation; new generation does not. Never-claimed runs cancel locally.

Terminal admission/stop responses identify the run but do not carry its full result. The dispatcher polls the native durable status before finalizing completion, usage or failure details; a status outage retains the attached native ID and stop intent for recovery.

The dispatcher polls durable native status every five seconds even while SSE remains open; a lost terminal event or continuing keepalive cannot leave a finished run running. These polls project terminal results and newly pending approvals, not duplicate tool events. Beat also reconciles native terminal status independently of worker leases, using bounded rotating scans and row locks. Control outages preserve the current state; silence is not proof of failure. Terminal projections cannot be reopened by late tool events. Admission responses, including an idempotent replay of completed work, are followed by a durable result read before completion.

The dispatcher rechecks current owning-app access after claim and during event consumption; revocation triggers native stop. Maintenance expires approvals, revokes jobs, cleans retained events/files and recovers stale dispatches under fenced database leases. Shared Beat health matters even when the API/gateway are healthy.

Run lists filter by current owning-app admission before counting and pagination; individual reads and controls require that admission as well as ownership. SSE replay rechecks both Chatbot and owning-app admission before each event batch and closes immediately on revocation. Bounded native-status reconciliation rotates both reachable and failed lookups, so an unavailable old run cannot starve later completion recovery; lookup failures retain run status and execution claims. A failed auxiliary status poll never cancels a healthy SSE subscription or drops its dequeued event; polling resumes after the normal five-second interval. Terminal polling freezes the SSE producer and retains dequeued/buffered nonterminal events before publishing completion. The web adapter reconciles partial deltas with the durable final text (or the completion event if the final lookup is unavailable), independently of later conversation refresh. The browser consumes OWH's replayable SSE projection. Changing conversations or closing a stream detaches the observer; explicit stop cancels the run. Returning to an active conversation reconnects without creating another run. Reconnects back off from one to thirty seconds within the one-hour bound; a closed event log resolves the durable run projection. Application-stage streaming currently emits completed stage output; interactive progress/tool/approval/text events stream live.

## Execution workspace and files

The shared gateway routes admitted terminal/native file/code operations through an isolated `/workspace` container via Hermes' official environment provider. The code guard verifies current run/profile transport, registered provider, actual cached environment type/backend and live container before dispatch. Sandboxes have no host home/config/credential bind, no Docker socket, no provider credentials, a read-only root, UID/GID 10000, dropped capabilities, no new privileges, two CPUs, 2 GiB memory/no swap, 512 processes and bounded tmpfs. Workspace capacity is 256 MiB; `/tmp` is 256 MiB and home/`/opt/data` are 64 MiB each. The image's implicit `/opt/data` volume is explicitly replaced by tmpfs.

Native `write_file`/`patch` use `/workspace` as their safe root. Their subprocesses also receive a Landlock write rule for `/workspace` (plus output to `/dev/null`), so final symlink targets, renames and deletes are checked inside the sandbox, including concurrent path changes. Unsupported kernels fail closed. The upstream patch engine and credential-file guards remain active. Arbitrary code and terminal commands retain disposable scratch space inside their isolated container; this file-tool rule is not a filesystem promise for arbitrary Python. Code tool RPC re-enters the same middleware and current-run admission. Business MCP writes still require explicit per-call consent; uncertain writes are never replayed.

Timeout/interruption disposes the owned sandbox, including detached descendants. The next admitted tool call retires a closed environment through native cache cleanup and restores already persisted workspace files in a fresh sandbox; concurrent recovery calls share an instance lock and recheck the cached object before removal. Unsaved changes and Python memory may be lost. A generated-script exception followed by a corrected call is Hermes tool-loop iteration, not an OWH transport retry or proof that a denied action was permitted.

Before container creation the provider verifies the deployment's network and CA volume, so a typo cannot silently create an empty volume. Invalid configuration, unavailable resources, missing CA files and startup failures use native `EnvironmentConnectionError` with a bounded, sanitized reason and administrator recovery hint. Hermes returns its structured degraded tool result and evicts the failed backend for a later retry. Raw Docker arguments, stderr and host paths are not returned. Recovery requires restoring the configured resources/CA or gateway Docker access; do not change the database namespace or create an unrestricted fallback network. A tool failure can be followed by an assistant explanation and a completed run; inspect the actual tool result when validating execution.

Only the public egress CA file is mounted through a volume subpath, not the adjacent legacy proxy token. The internal sandbox network and iron-proxy are the only public egress path. Proxy loopback, private, link-local and metadata CIDR denial remains enabled; no host port is published. New model calls happen in the trusted gateway using administrator credentials. Provider-token replacement is retained only for old Terminal runners when a legacy key is supplied. The upstream response-header timeout is bounded at 300 seconds.

User uploads are authenticated bounded binary bodies (`application/octet-stream`, percent-encoded `X-File-Name`), at most 64 MiB and sixty seconds. Same-conversation run admission serializes with uploads; uploads during an active run are rejected. Downloads recheck owner/session/admission and send attachment, no-store and nosniff headers. Public uploads recheck admission after receiving the body. Public uploads and internal MCP file transfers run their database work, object I/O, conversions and response serialization in the thread pool; slow storage does not block the API event loop or other run controls. Deferred file/tool operations recheck current run, owner/profile, session and app authority after thread admission. Reads recheck after object I/O; native saves lock and recheck their active run before publishing catalog metadata, and public uploads recheck app admission there. Rejected late uploads retain their durable object reservation for cleanup and preserve previously saved content. Tool approval consumption occurs after queue waiting and current tool admission.

Successful terminal operations save regular `/workspace` files to object storage before their tool result returns; later environments restore the latest saved paths. PostgreSQL owns path/hash/size/retention metadata and durable object upload reservations/deletion intent. Failed object deletion is retried without losing its intent. Per-session bounds are 256 MiB and 10,000 unexpired file revisions, including previous versions; path traversal, symlinks/special files and internal runtime paths are rejected. Retention uses the existing thirty-day artifact setting. Session-locked saves reject ancestor/descendant file-path collisions so every current catalog can be restored to a fresh filesystem, including concurrent uploads. Replacing a saved path publishes a new immutable revision and preserves previous bytes until their own expiry; identical live content is normally a no-op. Every workspace save invokes the run-bound, idempotent `owh/files/checkpoint`; server timestamps identify unchanged HTML entries that predate dependency changes and refresh them through the same bounded object/revision pipeline. No sandbox-local pending flag owns recovery state. All entries in a checkpoint share the saved batch's dependency cutoff timestamp; retrying a partially saved batch does not create another version for entries already covered. This allows a JS/CSS-only edit to publish a new preview version. A failed checkpoint is recovered by the next save, including after sandbox or gateway recreation; concurrent entry changes are rejected rather than overwritten. Checkpoints count against the same revision and byte limits. Deleting a path inside the transient sandbox preserves the last saved file for recovery.

`hermes_file_revisions` records the owned session, logical file ID, immutable object/hash/size and the trusted generating run when saved by that execution. The initial legacy-file backfill uses one coherent per-session snapshot cutoff; the repair migration aligns only backfill revisions, retaining catalog modification times and later immutable revisions. Its row and latest-file pointer commit together after object persistence and the final active-run check. Uploads and migration snapshots have no generating run. The pinned `/v1/runs` API does not provide a reliable native message ID for this association: the UI links versions to the generating task, never guesses an answer from its text or filename. Revision metadata and downloads recheck session ownership, expiry and generating-app admission; downloads use attachment/no-store/nosniff headers. Preview limits and route behavior belong to the [chatbot UI contract](../../apps/chatbot/hermes-desktop/README.md).

Migration `hermes_file_versions_20260914` backfills each existing latest file as one known snapshot with its current object key and expiry; it does not reconstruct lost versions. Its downgrade removes revision metadata while preserving the latest-file catalog and durable object cleanup intent. Historical version selection is unavailable after downgrade; preserve the database/object backup for a rollback requiring history.

A sandbox/process is disposable. Native lifecycle cleanup removes it and a one-hour container deadline bounds gateway-crash orphans. Packages, running processes and memory are not restored. Only acknowledged file snapshots are durable; files still changing in a background process or at a hard crash may not be saved. A save failure returns a tool error requiring retry.

## Static preview execution

`ops/hermes/plugins/owh_runtime/preview.py` registers `owh_preview` through the native plugin toolset. It accepts only a saved workspace `.html` or `.htm` path. `preview.mjs` uses Chromium's public DevTools pipe to serve only bounded local files through request interception, collect console/resource errors, capture a 1024×768 JPEG, and verify the actual renderer's namespace, `Seccomp: 2` and `NoNewPrivs: 1` state. Successful vision-capable native runs receive the screenshot in Hermes' multimodal result format; other models receive the bounded diagnostics. Rendering failures return JSON errors so the pinned native detector marks the tool event as failed; it treats multimodal envelopes as successes. A rendered page is evidence, not an assertion that it satisfies the user's task.

Each check creates a separate disposable container with `--network=none`, no published ports, no credentials or host mounts, the normal read-only root/UID/capability/resource restrictions, and the saved conversation files. The helper permits at most 100 dependencies, 2 MiB per file and 10 MiB total, caps console output and screenshots, and stops browser execution after 25 seconds (35-second transport bound). Its container is removed in `finally`, including timeout/error paths. Temporary browser files are never published as conversation results. This can temporarily add one sandbox per previewing run; account for that alongside the configured dispatch capacity.

The browser container additionally uses `chromium-seccomp.json`, derived from the [Moby default profile at commit 61eaf32614c7c71b60bd8927d3e6a4ffc8ff1f31](https://github.com/moby/profiles/blob/61eaf32614c7c71b60bd8927d3e6a4ffc8ff1f31/seccomp/default.json), retaining its default-deny policy and license. As in [Playwright's Chromium sandbox guidance](https://playwright.dev/docs/docker#crawling-and-scraping), it permits `clone`, `setns` and `unshare`; `chroot` is also required because OWH drops **all** capabilities. These calls create Chromium's inner sandbox, without granting host capabilities. The regular terminal/code container retains Docker's standard profile. Do not use `--no-sandbox`, `seccomp=unconfined`, host IPC, `SYS_ADMIN`, or a global AppArmor/user-namespace bypass. Unsupported Docker/kernel/AppArmor configurations must fail the actual preview check below.

Interactive admission supplies this environment contract through the native instructions field: save deliverables and dependencies under `/workspace`, inspect actual tool results, use `owh_preview` after visual changes, and stop repeating unchanged infrastructure failures. It does not select a model, inject a task-specific answer, or implement another agent retry loop. Missing files, invalid imports and script errors remain actionable tool failures for Hermes to correct in its own loop.

The web preview builds one document-wide module graph using pinned `esbuild-wasm 0.28.1` and its official ESM/code-splitting output. An import map maps generated module identifiers to embedded data URLs, preserving top-level await, cycles and shared module instances across entry scripts. Responsive image candidates use pinned [`@prettier/parse-srcset 3.1.0`](https://github.com/prettier/parse-srcset) and the same snapshot loader, preserving density/width descriptors and picture media selection. Classic scripts also use embedded URLs so the browser retains native parsing/defer/async and global-variable semantics. Both native and web previews support saved PNG/JPEG/GIF/WebP/SVG images. Stylesheets, inline-style URL assets and images are embedded through the same bounded saved-file loader; stylesheet media conditions remain browser-controlled. A trusted outer opaque-origin iframe owns `frame-src 'none'` and embeds the guest via `srcdoc`; the separately sandboxed guest cannot navigate itself to an external URL, alter the outer policy or access the authenticated page. Both documents restrict inline/data scripts, resources, fetch, forms and workers through CSP. A source/channel-checked bridge forwards errors only. This uses the browser's [CSP frame navigation checks](https://www.w3.org/TR/CSP/#directive-frame-src), not guest-script interception. The real-browser regressions in `pnpm nx e2e-shell web` cover execution semantics and the network/parent boundary. It fetches no remote dependency. The API resolves assets within the entry revision's owned session at or before its snapshot timestamp, rejects expired/unauthorized assets without falling back, and rechecks access after storage I/O. External scripts/imports, fetch, live servers and unsupported runtime asset loading remain unavailable. The browser reports missing dependencies and runtime/CSP failures visibly; downloading the original file remains available. Exact UI bounds and behavior belong to the [chatbot owner](../../apps/chatbot/hermes-desktop/README.md).

## Retired Terminal recovery

New raw Terminal session creation returns `410`; PTY attachment is closed. The chatbot replaces its launcher and interactive UI. Owned legacy session/archive APIs remain available under current chatbot admission. They do not expose another user's history, including to administrators. Codex Terminal is a separate unchanged app.

Retain the legacy broker/egress services and their namespaced resources while old sessions drain and archives remain. Terminal maintenance stops revoked sessions, archives files/profile state, retries interrupted archives with fenced claims and quarantines genuinely failed/missing workspaces for recovery. Do not remove broker resources merely because the launcher is gone. Legacy archive limits/timeouts retain their existing typed settings. No process, installed package or mutable container filesystem is migrated into the new sandbox.

Replacing the database requires a fresh explicit `OPEN_WORK_HUB_HERMES_TERMINAL_RESOURCE_NAMESPACE`. Stop exact old-namespace active runners before cutover and retain the matching env/resources for rollback. Brokers must never clean or adopt another namespace. Never run global Docker prune or delete profile/workspace volumes as a setup fix.

## Pinned upstream gaps

Use official public surfaces first. The remaining adapters are version-bound to the image above:

- `gateway_entry.py`: multiplex API startup discovers only the launch profile's MCP servers. It invokes native idempotent discovery for the authenticated profile and rejects admission when discovery or the required plugin fails. Remove it when an official profile-discovery lifecycle hook covers this requirement.
- `gateway_entry.py` cancellation route: native `/v1/runs` can resolve an idempotency key only by creating on a miss. The adapter reuses `RunIdempotencyStore.reserve`, native auth/profile scope and the pinned body/session-header fingerprint to atomically cancel missing admissions without an agent task. It requires durable storage and rejects unsupported request shapes. Pinned-image checks must cover both orderings of admission/cancellation, later native replay, conflicting inputs, profile isolation and unauthenticated requests. Remove this adapter when the public native API supports atomic cancellation by idempotency key. Deploy the updated gateway entry before API/worker changes; an older gateway returns 404 and leaves the OWH run stopping for recovery.
- `owh_runtime` tool middleware: native HTTP MCP headers are profile-static. A separate request adds native run identity without mutating shared connections. Native middleware exceptions fall through, so this callback catches policy/import/transport failures and returns an error. Remove the forwarding adapter when official per-call authenticated headers support trusted run context.
- `owh_runtime/native_execution.py`: the pinned whole-script guard ignores the documented custom-provider guard capability. A source-fingerprinted adapter shares a per-call ContextVar across plugin loads and admits only a verified OWH sandbox, retaining native dispatch. It does not alter the shared terminal guard or `approvals.unattended_mode`. Unknown source versions fail plugin startup/admission. Remove it when the official whole-script guard supports custom sandbox providers.
- `owh_runtime/file_write_boundary.py`: native safe-root canonicalization runs on the gateway, while native shell file mutations resolve symlinks in the remote environment. The public environment transport applies a Linux Landlock restriction to file-tool subprocesses without copying the patch engine. Remove this boundary adapter when native remote file guards enforce final filesystem operations within the configured root.
- `owh_runtime/sandbox.py`: native `DockerEnvironment` unconditionally mounts host credentials/skills/cache and has no supported off switch. The adapter implements the public `BaseEnvironment` transport/provider contract and `EnvironmentConnectionError` failure contract with safe Docker arguments; Hermes retains wrapping, timeout/interrupt and environment lifecycle. Compose supplies its physical resources independently of database namespaces. Deploy/recreate the updated gateway with both resource values before deploying the API context change that removes inferred network/volume names; the updated provider ignores those obsolete fields from older APIs. Replace it when native Docker configuration can guarantee no host mounts plus file snapshot hooks.
- `terminal_egress.py`: the public egress setup CLI is interactive and cannot express these container listeners and deny policy. The adapter uses exported iron-proxy functions; replace it when the CLI exposes the needed unattended configuration.

## Operations and change checklist

Gateway waits for successful bootstrap and healthy egress. Dashboard/API/worker dependencies remain explicit in both Compose files. The gateway uses official `--no-supervise`; Compose owns restart. Keep the legacy broker healthy during drain. Restart the affected Compose control services after bootstrap/plugin/credential-transport changes; DB model changes apply at subsequent admission without rewriting already admitted provider snapshots.

Non-inference development checks:

```bash
bash scripts/dev-infra.sh status
curl --fail http://127.0.0.1:18765/healthz
curl --fail http://127.0.0.1:19119/api/health
docker inspect --format '{{.State.Status}} {{.State.ExitCode}}' open-work-hub-dev-hermes-bootstrap
docker inspect --format '{{.State.Health.Status}}' open-work-hub-dev-hermes-gateway
docker inspect --format '{{.State.Health.Status}}' open-work-hub-dev-hermes-terminal-egress
```

Bootstrap must report `exited 0`; the gateway and egress must report `healthy`.

Do not print container envs, profile config/credentials, prompts or sensitive runtime logs. [Release storage policy](../release/README.md#build-and-test-storage) must preserve current/previous images, container references, user profile volumes and archive objects.

### Sandbox execution check

Run this check after fresh installation or gateway recreation, from the development checkout root. It exercises the actual pinned provider without inference: it creates and removes two isolated sandboxes plus a replacement, verifies security limits and CA readability, and saves/restores a synthetic file through the real workspace transport. Only the file RPC uses test fixtures in the short-lived check process; this does not replace the PostgreSQL/object-storage tests or a chatbot end-to-end check.

```bash
docker exec -i open-work-hub-dev-hermes-gateway python - \
  "$(docker inspect --format '{{.Image}}' open-work-hub-dev-hermes-gateway)" \
  < ops/hermes/check_sandbox.py
```

The command must exit with code `0` and print `PASS: two isolated sandboxes, security limits, CA access, file save/restore`.

Also run the native-tool check. It keeps native dispatch, middleware, approvals, file tools and code execution, with synthetic profile/context/file RPC fixtures and disposable containers:

```bash
docker exec -i open-work-hub-dev-hermes-gateway python - \
  "$(docker inspect --format '{{.Image}}' open-work-hub-dev-hermes-gateway)" \
  < ops/hermes/check_native_tools.py
```

Require exit `0` and all PASS lines for unattended code execution, concurrent conversation isolation, native write/patch and code RPC, outside/symlink denial, timeout recovery and cancellation of detached children. The original guard must remain denied outside an admitted code call. These checks make no model calls.

Run the offline preview check as well; it needs neither Playwright installation nor inference:

```bash
docker exec -i open-work-hub-dev-hermes-gateway python - \
  "$(docker inspect --format '{{.Image}}' open-work-hub-dev-hermes-gateway)" \
  < ops/hermes/check_preview.py
```

Require all PASS lines for local module rendering with verified browser isolation, observable JavaScript/console errors, vision/non-vision output and native failure classification, and missing/external dependency rejection. Then verify a normal chatbot task creates HTML plus a local dependency, calls `owh_preview`, corrects a rendering error, and produces a visible saved result. Change only its dependency in a follow-up and verify a new preview version; reopen the previous version and verify its previous dependency. After stop/reconnection and worker recovery, compare the displayed terminal state with native durable status. Do not declare installation complete from a healthy gateway or successful text response alone.

Then open a new chatbot conversation, request `execute_code` to create a small file under `/workspace`, and request native `patch` to modify it. Verify successful native tool results and the saved file revision/content. Also request a single terminal invocation of `printf OWH_SANDBOX_OK`. Verify that the actual tool result contains `OWH_SANDBOX_OK` and `exit_code: 0`. The assistant's explanation and the conversation's `completed` state are not sufficient acceptance evidence. This final check uses the configured chatbot workload and its normal model usage.

### Sandbox startup recovery

Use the structured tool error code to select the recovery step. Older gateways may expose only a long `docker run` command and exit status `127`; follow the [existing-installation update](#updating-an-existing-development-installation) before retrying.

| Error code | Check and recovery |
| --- | --- |
| `sandbox.configuration_invalid` | The gateway resource values are missing or invalid. Recreate it from the matching Compose definition using the update procedure above; verify custom deployment wiring against [prerequisites](#prerequisites). |
| `sandbox.network_unavailable`, `sandbox.volume_unavailable` | The gateway could not inspect the declared resource. Check gateway Docker access and that the Compose-declared network and CA volume exist; restore missing infrastructure through the normal development startup procedure. |
| `sandbox.egress_ca_missing` | The client volume lacks `ca.crt`. Recover the egress service's certificate publication and verify its health before rerunning the sandbox check. |
| `sandbox.docker_unavailable` | Check the pinned gateway image's Docker client, socket mount and supplemental Docker group described in [prerequisites](#prerequisites). |
| `sandbox.start_timeout`, `sandbox.start_failed` | Check Docker daemon health, host capacity and the pinned image. The safe error identifies a startup failure; inspect only relevant, sanitized diagnostics before retrying. |
| `sandbox.cleanup_failed` | Removal of the exact owned sandbox was not confirmed. Restore Docker connectivity and retry cleanup; the closed instance cannot execute more commands. The one-hour container deadline remains an orphan limit. |
| `preview.browser_unavailable`, `preview.browser_start_failed`, `preview.browser_sandbox_unverified` | Verify the pinned Chromium assets and read-only plugin/seccomp files, Docker user-namespace support and applicable AppArmor policy. Run `check_preview.py`; preserve both container and Chromium sandboxes. |
| `preview.timeout` | Inspect the saved HTML for blocking JavaScript or excessive rendering work. The disposable browser is removed; do not start another installer or disable isolation. |
| `sandbox.file_boundary_unavailable` | Enable Landlock ABI 3+ on the Docker host/VM and permit the Landlock syscalls in its security profile. Re-run the native-tool check; never bypass the file guard. |

Retain the existing database/runner namespace and profile/workspace volumes during this recovery. Do not rename resources to match a database namespace, manufacture an empty certificate volume, or use a global Docker prune. Once infrastructure is restored, retry the command; Hermes creates a fresh backend after the failed attempt.

### Runtime change validation

For every runtime change: inspect the pinned public surfaces and reassess each adapter, update the ownership map's affected files and INSTALL, verify credential/network/owner isolation, queue concurrency and same-conversation order, result correction, cancellation/recovery and workspace retention. Run focused checks first, then shared contracts:

```bash
(cd apps/api && uv run --python 3.12 --group dev pytest tests/test_hermes_reconciliation.py tests/test_hermes_preview_assets.py tests/test_hermes_integration.py tests/test_hermes_runtime.py tests/test_hermes_deferred_io.py tests/test_hermes_plugin.py tests/test_hermes_native_execution.py tests/test_hermes_sandbox.py tests/test_hermes_bootstrap.py tests/test_hermes_gateway_entry.py tests/test_hermes_terminal.py tests/test_hermes_terminal_egress.py tests/test_admin_hermes_tools.py -q)
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

Check the native admission/cancellation contract with actual pinned handlers and durable storage. This disposable offline check replaces only model task scheduling and uses no application data, credentials or Docker socket:

```bash
docker run --rm -i --network none --entrypoint python \
  --mount "type=bind,src=$PWD/ops/hermes/gateway_entry.py,dst=/opt/owh_gateway_entry.py,readonly" \
  nousresearch/hermes-agent:v2026.8.31@sha256:64923faeae267792bf9bf87fe3b4c4869e35004e360c7df01730ad801b74d524 \
  - < ops/hermes/check_native_cancellation.py
```

Use the repository's explicit non-production PostgreSQL test configuration for integration/migration tests. Verify actual pinned-image environment/plugin loading, two isolated sandboxes and file save/restore without a paid model call. A health check alone does not establish live provider quality or end-to-end UI behavior; report unavailable validation.

## Official references

- [Open WebUI integration](https://hermes-agent.nousresearch.com/docs/user-guide/messaging/open-webui): OpenAI-compatible UI integration; OWH uses native runs for durable controls.
- [esbuild code splitting](https://esbuild.github.io/api/#splitting) and [HTML import maps](https://html.spec.whatwg.org/multipage/webappapis.html#import-maps): shared browser module execution from embedded bytes.
- [Native API server](https://hermes-agent.nousresearch.com/docs/user-guide/features/api-server): runs, sessions, SSE and lifecycle controls.
- [Pinned implementation](https://github.com/NousResearch/hermes-agent/tree/v2026.8.31): inspect matching profile config, plugins/middleware, terminal environment provider, approval context and iron-proxy implementation before an upgrade.
- [Gemini OpenAI compatibility](https://ai.google.dev/gemini-api/docs/openai).
