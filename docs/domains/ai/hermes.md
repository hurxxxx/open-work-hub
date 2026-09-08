# Hermes Setup and Runtime Contract

Hermes powers both the headless general-purpose chatbot and the raw Hermes Terminal app. Open Work Hub owns identity, current user/app authorization, durable projections, and UI controls; Hermes owns the autonomous agent loop, model calls, tool orchestration, sessions, and native terminal behavior. Specialized durable AI graph workloads remain on the existing graph runtime.

## Ownership and maintenance rule

This file is the single current owner for Hermes installation, configuration, runtime boundaries, and operational setup. Update it in the same change whenever Hermes image pins, model/provider policy, environment variables, ports, profiles, MCP, tool availability, egress, terminal mounts, lifecycle, limits, Compose services, or bootstrap/deployment behavior changes. An ADR is appropriate only for a new cross-domain architectural decision; the ADR must link here instead of duplicating mutable setup values.

Code and tests remain authoritative for implemented behavior. Use the [configuration ownership map](#configuration-ownership-map) and [change checklist](#change-checklist) to keep every duplicated pin and contract aligned.

## Fixed runtime contract

- Hermes image: `nousresearch/hermes-agent:v2026.8.31@sha256:64923faeae267792bf9bf87fe3b4c4869e35004e360c7df01730ad801b74d524`.
- Provider: `openrouter`.
- Model: `qwen/qwen3.8-flash`.
- Model policy: the main model is fixed and `z-ai/glm-5.3-flash` is the single ordered fallback. Hermes' official `auxiliary.openrouter_model` setting replaces its built-in Gemini auxiliary fallback with the primary Qwen model. Bootstrap removes the legacy `fallback_model` key; no Hermes runtime patch is used for model routing.
- Resilience policy: the primary SDK performs no nested retries at this Hermes pin, `agent.api_max_retries=1` gives the primary one total attempt before fallback, and OpenRouter routes only to providers supporting every requested parameter with `sort=throughput`. Requests opt into OpenRouter router metadata through `model.default_headers`.
- Context policy: compression is enabled at the lower of the normal 50% threshold or 100,000 tokens, retains a 20% target and the last 20 messages, and deterministically prunes old tool results starting at 48,000 tokens when at least 4,096 tokens can be reclaimed.
- Provider credential: `OPENROUTER_API_KEY`. Headless bootstrap persists it in the Hermes profile store. Terminal mode passes the real key only to the trusted iron-proxy container; terminal runners receive a revocable proxy token and public CA instead. The credential is explicitly removed from Open Work Hub API, worker, web, migration, beat, terminal broker, and terminal runner processes.
- Terminal broker Python dependencies are pinned in `ops/hermes-terminal-broker/Dockerfile` and aligned with the API lockfile: FastAPI 0.141.1, Pydantic 2.13.5, Uvicorn 0.52.4, HTTPX 0.28.1, and Docker SDK 7.2.0.
- Runtime, dashboard, and terminal broker bind to loopback host addresses. The API reaches them through the declared `OPEN_WORK_HUB_HERMES_*_BASE_URL` values.
- The official image runtime user is UID/GID `10000`. Named-volume ownership and runner processes must continue to use that identity.

Do not add a model selector to the chatbot or accept a caller-supplied provider/model. The server constants in `apps/api/src/open_work_hub_api/core/settings.py` are authoritative. Hermes upstream supports additional providers such as OpenAI, Anthropic, Gemini, Ollama, and other OpenAI-compatible endpoints, but this deployment intentionally configures only OpenRouter. Enabling another provider is a setup and credential-boundary change, not an automatic consequence of its client library being present in the image.

## Official image baseline and capability boundary

Open Work Hub uses the official Hermes Docker image rather than running the macOS, Windows, or Linux host installer. At the current pin the image includes Hermes and its Python extras, Node.js/npm, Playwright Chromium assets, `ripgrep`, `ffmpeg`, Git, SSH client, `xz`, and build tooling. It is not a reduced API-only Hermes installation.

Hermes can register broad built-in toolsets including web, browser, terminal, file, code execution, vision, image generation, text-to-speech, skills, todo, memory, session search, clarification, delegation, cron, and computer use. Registration does not mean every tool is operational. Optional search/browser/media backends still require their documented credentials, services, or lazy-installed executables. The current Open Work Hub contract supplies OpenRouter and the Open Work Hub MCP bridge only; it does not implicitly provision Firecrawl, Exa, Browserbase, FAL, voice providers, Home Assistant, Spotify, or host desktop access. Platform administrators manage Semantic Scholar, arXiv, OpenAlex, and Crossref independently at `/admin/ai-tools`. Defaults are Semantic Scholar off and the other three on.

Terminal runners are headless, container-isolated environments. They do not inherit the host user's home directory, GUI applications, native clipboard, Docker socket, private network, or macOS/Windows integrations. Use Hermes' official `hermes doctor` and `hermes tools list` commands to inspect a pinned image or profile, but never treat a registered tool as ready without checking its credential and runtime requirements. Do not make a paid inference solely as a readiness check.

## Configuration ownership map

| Contract                        | Current owner paths                                                                                                                                                                                             | Alignment rule                                                                                                                                                  |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Release, provider, model        | `apps/api/src/open_work_hub_api/core/settings.py`, `ops/hermes/bootstrap.py`, `apps/api/src/open_work_hub_api/domains/hermes_terminal/broker_runtime.py`, `apps/web/src/app-modules/chatbot/api/chatbot-api.ts` | Keep release/provider/model metadata identical; regenerate API contracts when the exposed schema changes.                                                       |
| Official image and digest       | `ops/compose/open-work-hub-dev.infra.yml`, `ops/compose/open-work-hub-prod.app.yml`, terminal broker runtime                                                                                                    | Pin every service and dynamically created runner to the same immutable digest.                                                                                  |
| Headless profile bootstrap      | `ops/hermes/bootstrap.py`                                                                                                                                                                                       | Use Hermes public config/profile APIs for credentials, model, fallback, retry, routing, compression, and the observability header; do not overwrite DB policy.  |
| Research source policy          | `hermes_research_source_settings`, `domains/hermes/research_settings.py`, `domains/hermes/research_sources.py`, `/admin/ai-tools`                                                                               | Persist one audited platform policy; reconcile headless profiles on their next admission and pass the same exact policy to every new terminal session.          |
| Multiplex gateway adapter       | `ops/hermes/gateway_entry.py`                                                                                                                                                                                   | Keep the adapter narrow and version-bound; remove it when the pinned Hermes release exposes an official per-profile discovery hook.                             |
| Terminal runner/profile/TUI     | `apps/api/src/open_work_hub_api/domains/hermes_terminal/broker_runtime.py`                                                                                                                                      | Use official CLI flags, environment variables, and config keys; keep `/workspace` consistent across command, safe root, mounts, listing, archive, and download. |
| Terminal egress                 | `ops/hermes/terminal_egress.py`, both Compose files                                                                                                                                                             | The real OpenRouter key stays in iron-proxy; runners receive only proxy credentials and the public CA.                                                          |
| Application settings and limits | `apps/api/src/open_work_hub_api/core/settings.py`, `.env.example`, `scripts/dev-env.sh`, `scripts/prod-app-config.mjs`                                                                                          | Add every operator-facing setting to the example and production validator as appropriate.                                                                       |
| Dev/prod service topology       | `ops/compose/open-work-hub-dev.infra.yml`, `ops/compose/open-work-hub-prod.app.yml`, `dev.sh`, `scripts/dev-infra.sh`, `scripts/prod-app.sh`                                                                    | Keep service dependencies, health checks, fixed ports, volumes, and credential exposure equivalent across environments.                                         |
| User-facing terminal behavior   | `apps/web/src/app-modules/hermes-terminal/`, `apps/web/src/components/terminal/WebSocketTerminalSurface.tsx`                                                                                                    | The UI controls session state, approvals, and downloads; it does not reimplement Hermes' agent loop or TUI.                                                     |

## Fresh environment setup

### Prerequisites

- Docker Engine with Compose and permission to create named volumes, private networks, and the trusted broker container that owns the Docker socket.
- The normal repository development or production prerequisites from the root `README.md`.
- An OpenRouter key valid for both `qwen/qwen3.8-flash` and `z-ai/glm-5.3-flash`.
- An OpenRouter provider-side guardrail that allows exactly `qwen/qwen3.8-flash` and `z-ai/glm-5.3-flash` and rejects other models. This is required because a YOLO terminal can issue arbitrary public network requests through the controlled egress path.
- Distinct, non-placeholder runtime, management, and MCP secrets in production.

Do not install Hermes globally on the host for this service. Compose pulls the pinned official image and named volumes hold its durable state.

### Development checkout

1. Create `.env` from `.env.example` if it does not exist.
2. Set `OPEN_WORK_HUB_HERMES_ENABLED=true` and `OPENROUTER_API_KEY` in the development checkout's `.env`. When `OPEN_WORK_HUB_HERMES_ENABLED` is absent, development derives it from whether the OpenRouter key is present; set it explicitly so a copied `.env.example` value of `false` cannot silently disable Hermes.
3. Keep the development defaults for the runtime, dashboard, broker, MCP URL, and socket unless the complete matching URL/port set must change. Ports are fixed declarations, not candidates for automatic fallback.
4. Start infrastructure, then the API/web/worker processes:

```bash
./scripts/dev-infra.sh up
./scripts/dev-infra.sh status
./dev.sh --with-worker --no-infra
```

5. Open All Apps and verify both the general chatbot path and a personal Hermes Terminal session. The worker is required for queued headless runs.

The development defaults are runtime `18642`, dashboard `19119`, and terminal broker `18765`. The production defaults are runtime `8642`, dashboard `9119`, and terminal broker `8765`. These fixed host ports intentionally differ when both environments run on one machine; the broker container still listens internally on `18765`. The application API remains on its separately declared environment port. A foreign listener on a fixed Hermes Terminal broker port is a startup/deployment error; stop the listener instead of selecting a random replacement port.

### Production checkout

Production `.env` must explicitly provide and align:

- `OPEN_WORK_HUB_HERMES_ENABLED=true`
- `OPENROUTER_API_KEY`
- `OPEN_WORK_HUB_HERMES_API_KEY`
- `OPEN_WORK_HUB_HERMES_MANAGEMENT_TOKEN`
- `OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET`
- runtime, management, and terminal broker ports plus their matching loopback base URLs
- `OPEN_WORK_HUB_HERMES_MCP_SERVER_URL` targeting the production API's `/api/v1/internal/hermes/mcp`
- `OPEN_WORK_HUB_HERMES_TERMINAL_MCP_RELAY_URL` targeting the broker's internal Compose name
- `OPEN_WORK_HUB_HERMES_TERMINAL_MCP_SOCKET_PATH`
- `OPEN_WORK_HUB_HERMES_PROFILE_CLONE_SOURCE=default`
- the terminal admission, timeout, approval, retention, and archive limits listed in `.env.example`

The production validator rejects disabled Hermes, missing or duplicate secrets, non-loopback control URLs, mismatched URL/port pairs, configured port collisions, the wrong MCP path, and a non-default clone source. Before building or migrating, the guarded deployment also rejects a live terminal broker port unless it belongs to the expected existing production broker container. Validate before using the normal release runbook:

```bash
node scripts/prod-app-config.mjs .env
./scripts/prod-app.sh status
```

Deployment remains governed by `docs/domains/release/README.md` and requires explicit release authorization. Development and production checkouts have separate `.env` files and must not share placeholder secrets.

For an incompatible application/database cutover, the [paired rollback procedure](../release/README.md#incompatible-database-and-configuration-cutovers) restores the previous revision's Compose and host-mounted Hermes bootstrap, gateway, and terminal helpers together with its env. Reusing new host helpers with the old API image is not a complete rollback. This operation preserves Hermes volumes; it does not reverse profile mutations or external actions. New deployment identities must not adopt retained users' profile identities implicitly.

## Ownership and authorization

Each `(environment, user_id)` has one deterministic, isolated Hermes profile. Open Work Hub never exposes Hermes credentials to the browser. User routes are under `/api/v1/agent`; administrator inventory, toolset status, research-source settings, runtime health, and reconciliation routes are under `/api/v1/admin/hermes`. The administrator screen at `/admin/ai-tools` reads Hermes' official `/v1/toolsets` response for a selected managed profile, shows MCP servers and skills, and reports headless/broker readiness, recovery backlogs, quarantined workspaces, and durable maintenance heartbeats.

Hermes accesses Open Work Hub tools only through `/api/v1/internal/hermes/mcp` with a profile-derived HMAC bearer token. The bridge revalidates the active user and chatbot app admission on every request. It exposes a stable environment/user-entitled discovery surface only while that profile has exactly one active local run, then re-lists and validates tools against that run's `allowed_app_ids` immediately before every call. Missing run context fails closed. The headless internal MCP server is configured as `untrusted`, so write-capable tools pass through Hermes approval before execution. Approval evidence is bound to the exact server, tool, local run, and normalized argument digest, expires after five minutes, and cannot be replayed.

Hermes MCP connections are process-global and keyed by server name. Every interactive managed profile therefore uses a deterministic, globally unique physical name for its internal and administrator-added MCP servers. Normal profile reconciliation before session/run admission removes inherited or legacy unscoped names.

Hermes `v2026.8.31` multiplex API mode discovers MCP servers from the launch profile and exposes no documented per-request-profile discovery hook. The pinned gateway therefore uses the narrow, version-bound `ops/hermes/gateway_entry.py` adapter to perform Hermes' own idempotent discovery for the authenticated request profile before run admission. It fails admission with `503` if the managed internal bridge is not connected. It does not replace the run loop, tool dispatcher, sessions, approval machinery, or lifecycle management.

Hermes-native cron jobs run in a second deterministic `-jobs` profile. That profile inherits the fixed model/provider credentials but removes and verifies the absence of every MCP server. Scheduled jobs may use Hermes-native built-in tools, but they cannot use MCP integrations or Open Work Hub app tools.

## Durability and control

Open Work Hub persists profile/session/job bindings, run state, sanitized run events, approval records, run inputs, and a transactional dispatch outbox. A dedicated Celery queue executes Hermes runs; beat republishes pending outbox records and requeues a dispatched record when no valid execution lease appears within two minutes. Browser-generated `Idempotency-Key` values are bound to a canonical request digest per profile, and the durable local run ID remains the idempotency key sent to Hermes' official run API. A replay returns the original run; reusing a key for a different request fails with `409`.

Stop intent is committed locally before calling Hermes. The worker checks stop and current user/app authorization every two seconds while consuming the official event stream, retries the official stop request without erasing intent, and rechecks authorization immediately after claiming queued work. Expired approvals are denied through Hermes' official approval API; an approval whose remote run was never recorded is failed locally without requiring Hermes to be reachable. Active jobs are paused through Hermes' official job API when access is revoked. The 30-second headless maintenance cycle also expires approvals, cleans retained run events, and persists a `headless` heartbeat. A fenced PostgreSQL lease prevents overlapping beat deliveries from running the same maintenance component concurrently. Run/job scan cursors are persisted in the same state so a large authorized prefix cannot permanently starve later revoked work. Headless approval and event retention deliberately reuse the existing terminal approval-timeout and artifact-retention settings because both surfaces have the same five-minute and thirty-day policy.

The browser consumes Open Work Hub's replayable SSE projection instead of connecting to Hermes directly. It resumes from `Last-Event-ID` with a one-to-thirty-second reconnect delay for up to the one-hour run bound. An intentional `stream.closed` resolves the authoritative durable run projection, covering a retained run whose terminal event is no longer in the event log or already precedes `Last-Event-ID`. Cancelling the browser response aborts both the current source and its reconnect delay. Initial SSE connection failure therefore cannot fall through to the synchronous chat path and create a second paid run.

Supported controls are status and capability inspection, recent run monitoring, stop, steer, one-time approve/deny, job create/list/pause/resume/run/delete, profile reconciliation, fixed-model enforcement, MCP inventory, and skill toggles. Only one active run is admitted per profile so MCP scope cannot become ambiguous.

## Hermes Terminal

`hermes-terminal` appears in All Apps for users admitted by its company user/group audience when `hermes_enabled` is enabled. Each session belongs to exactly one user; another company user or platform administrator cannot list, attach to, stop, approve, or download its data. The administrator-only Codex Terminal remains a separate app.

The release migration places Hermes Terminal into an existing localized All Apps category without replacing administrator-managed placement; if no launcher category exists, it creates the default All Apps category. Production deployment must run Alembic before starting the API, and the migration is idempotent so an existing placement is preserved.

The browser renders Hermes' official raw TUI through the shared xterm surface. It does not reimplement the agent loop or tool UI. Desktop places generated files and pending Open Work Hub approvals on the right; narrow screens place the same panel below the terminal. Active files come from the private runner workspace, completed-session artifacts come from object storage, and every download is reauthorized by current account status, app admission, and session ownership.

Creating a session always starts in standard mode. YOLO can be selected only after a fresh acknowledgement in that creation dialog; the browser never remembers it as a default. The broker appends Hermes' official `--yolo` flag only for that session. YOLO disables Hermes-native dangerous-command prompts, but it never bypasses Open Work Hub authentication, membership checks, exact write-tool approval, network isolation, container isolation, the fixed model, or artifact limits.

The broker invokes the pinned image with Hermes' public CLI:

```text
chat --tui --in /workspace --checkpoints --provider openrouter --model qwen/qwen3.8-flash [--yolo]
```

Terminal profile configuration uses Hermes' public `config set`, `config unset`, and `config check` commands:

- `model.provider=openrouter`
- `model.default=qwen/qwen3.8-flash`
- `model.default_headers={"X-OpenRouter-Metadata":"enabled"}`
- `fallback_providers=[{"provider":"openrouter","model":"z-ai/glm-5.3-flash"}]` and no legacy `fallback_model`
- `agent.api_max_retries=1`
- `agent.environment_hint` is generated from the current administrator policy only when at least one managed research source is disabled; it is unset when all four sources are enabled
- `compression.enabled=true`, `threshold=0.50`, `threshold_tokens=100000`, `target_ratio=0.20`, and `protect_last_n=20`
- `compression.proactive_prune_tokens=48000`, `proactive_prune_min_result_chars=8000`, and `proactive_prune_min_reclaim_tokens=4096`
- `provider_routing.sort=throughput` and `provider_routing.require_parameters=true`
- `auxiliary.free_only=false`
- `auxiliary.openrouter_model=qwen/qwen3.8-flash`
- `display.mouse_tracking=off`
- one session-scoped Open Work Hub MCP server and fresh proxy/MCP tokens

The runner environment and mounts must preserve these path contracts:

- `HERMES_HOME=/opt/data/profiles/terminal`: private user profile and Hermes state.
- `XDG_CACHE_HOME=/opt/data/cache` and `UV_CACHE_DIR=/opt/data/cache/uv`: regenerable package caches remain private and reusable while staying outside the durable profile archive.
- `/opt/data`: a private named profile volume. It is a container path, not the host machine's `/opt` directory.
- `/workspace`: a separate private session volume and the only generated-result root exposed by file listing and download.
- `HERMES_WRITE_SAFE_ROOT=/workspace`: Hermes' official file safety boundary, aligned with `--in /workspace` and the artifact panel.
- `HERMES_TUI_DISABLE_MOUSE=1` plus `display.mouse_tracking=off`: Hermes' official browser-TUI behavior, allowing xterm drag selection and normal clipboard copy shortcuts.
- `HTTP_PROXY`/`HTTPS_PROXY`, the iron-proxy CA variables, and the sandbox network: the only runner egress route.
- `NO_PROXY` includes the apex and wildcard domains for every disabled research source. Those domains bypass iron-proxy into the runner's internal-only network and therefore fail closed; enabled sources continue through controlled proxy egress.

Research-source switches are server-owned settings, not prompt-only preferences. The generated environment hint guides generic web search and is needed for headless profiles, where Hermes has no upstream per-source switch. Terminal enforcement is additionally authoritative at the network layer. Changing a switch clears the headless reconciliation cache; it applies on the next headless profile admission and to newly created terminal sessions. Running terminal containers are never mutated.

Do not move generated results to `/opt/data`, extend artifact listing into the profile volume, add Gemini filtering, rewrite model requests, patch the TUI, or add a file-copy workaround. Correct the official Hermes setting or the shared `/workspace` contract instead. Existing containers receive environment changes only after a new terminal session starts.

Terminal profiles are separate from headless profiles while retaining the same deterministic environment/user binding. Before a profile archive is exported, the broker uses official `hermes checkpoints clear --force` and `uv cache clean --force` commands to remove filesystem rollback data that belongs to the ended workspace and regenerable package cache data. It then uses the official `hermes config unset` command to remove the temporary proxy token and session MCP token before invoking official profile export. Import and export archives are staged at the reserved private-volume paths `/opt/data/.owh-terminal-profile-import.tar.gz` and `/opt/data/.owh-terminal-profile-export.tar.gz`, then removed immediately after the official CLI consumes them or Docker copies them. Docker's archive API rejects writes to, and cannot reliably read from, the read-only utility container root even when `/tmp` is tmpfs-backed, while `/opt/data` is the intentionally writable private profile volume. Hermes sessions, memories, skills, configuration, and other durable profile data remain in the archive. The next session restores fresh credentials through the same public configuration surface; durable profile archives never carry ephemeral credentials or ended-workspace caches.

The terminal MCP server is trusted by the Hermes profile because Open Work Hub itself creates and enforces the exact write approval at the MCP boundary. Discovery is restricted to server-derived `allowed_app_ids`; every write request is bound to the exact tool and normalized argument digest, expires after five minutes, and is consumed atomically once. This approval remains mandatory in YOLO mode.

### Terminal isolation and retention

- The trusted terminal broker is the only component with the Docker socket. Runners have a read-only root filesystem, private workspace/profile volumes, dropped capabilities, resource limits, no Docker socket, and only the internal sandbox network.
- Runner containers start detached with a reusable open TTY. The broker drives Docker attach sockets with cancellable non-blocking I/O and explicitly shuts down the raw socket when a browser WebSocket closes, so reconnects cannot strand blocking reader threads or exhaust broker health and control requests. Only one browser writer may attach to a session at a time. The browser sends a 25-second heartbeat, treats 75 seconds without a pong as stale, retries with a capped 30-second delay, and resumes automatically when a hidden tab becomes visible. Docker replay resets the xterm buffer before reconnection output, preventing duplicated terminal history.
- Hermes' official iron-proxy is the runner's only public egress path. Its loopback, link-local, RFC1918, and cloud-metadata deny list remains enabled. The pinned iron-proxy 0.39 secrets transform uses its supported `require: false` setting so TLS CONNECT can complete before the inner proxy token is replaced; the real OpenRouter key remains available only inside the proxy process. The managed adapter raises `proxy.upstream_response_header_timeout` from the pinned helper's 120 seconds to 300 seconds. The egress service publishes no host port.
- The pinned release's public `hermes egress setup` command is interactive and does not expose the required container listen/allow-list settings. `ops/hermes/terminal_egress.py` is a narrow non-interactive adapter over Hermes' exported iron-proxy functions; replace it with the CLI when Hermes exposes those controls.
- The broker binds only to `127.0.0.1:${OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_PORT}`. Development uses fixed host port `18765`; production uses fixed host port `8765`; the container port remains `18765`. A foreign listener or mismatched project container is a hard error before production build or migration; there is no automatic port fallback.
- Docker resources carry an explicit Compose namespace (`dev` or `prod`) in names and labels. A broker ignores another namespace. It adopts an unlabeled legacy runner only when its sandbox network, egress mount, profile mount, and workspace mount exactly match the current broker; ambiguity fails closed. The 60-second maintenance cycle removes only old namespaced orphan runners/workspaces and stale utility containers, never reusable profile volumes or another environment's resources.
- Limits default to one active session per user and twenty total. Admission is serialized in PostgreSQL. Each runner is bounded to two CPUs, 2 GiB memory with no swap allowance, 512 processes, bounded file descriptors, a 512 MiB `/tmp`, and a 512 MiB non-durable `/opt/data/cache` tmpfs. Docker's supported `core=0` ulimit prevents process memory dumps from becoming workspace artifacts. Do not apply a process-wide `fsize` ulimit: Hermes' official lazy-package installer writes outside the workspace and can legitimately exceed a small artifact-oriented file bound. The live workspace limit equals `OPEN_WORK_HUB_HERMES_TERMINAL_WORKSPACE_ARCHIVE_MAX_BYTES` (256 MiB by default); a five-second broker watchdog stops a runner that exceeds it. Reusing the archive limit avoids a second operator setting for the same storage boundary.
- Idle sessions stop after two hours and completed artifacts expire after thirty days. Archive attempts use immutable object keys and a fifteen-minute database claim; maintenance neither replaces nor quarantines an attempt before that claim expires, and only the current claim may publish the profile pointer or terminal state. Workspace scanning rejects and counts links, hard-linked/special files, duplicate or invalid paths, internal runtime paths, and files over the per-file bound. It accepts at most 10,000 regular files, preserves them up to the total archive bound, and reports every omitted file count in the UI.
- A failed or interrupted archive remains in `archiving` while maintenance retries it. Terminal maintenance has its own fenced sixteen-minute singleton lease (longer than the worker's fifteen-minute hard limit) and serializes archive-capable operations, avoiding overlapping beat jobs and multi-archive memory spikes. If a naturally exited runtime is running again after an operator restart, reconciliation restores the live session. If a manually stopped/failed runtime restarts, reconciliation stops it again through the broker before retrying the requested archive. After three genuine archive failures the session closes with an archive failure but retains and marks its workspace as quarantined for operator recovery; it is never silently deleted. A live runtime that disappears unexpectedly is likewise failed and quarantined without deleting a possibly surviving workspace volume. Profile volumes remain private and reusable.

## Operations and verification

App build/deploy storage preflight and generated-image retention follow [Release Domain](../release/README.md#build-and-test-storage). Retention preserves current/previous app images and all container references; it must not delete Hermes profile/workspace volumes or archive objects. After storage maintenance, verify gateway/dashboard, terminal broker/egress and shared Beat health. No paid inference is required for this check.

The bootstrap service must complete before gateway startup; gateway and dashboard must be healthy before API and worker startup. The terminal broker health endpoint performs a live Docker/dependency check and returns `503` when it is not ready. Re-run Compose startup after changing the managed Hermes policy or rotating runtime/OpenRouter credentials so bootstrap synchronizes the root and existing named profiles. Terminal runner environment and in-memory agent settings apply only after a new terminal session starts. The gateway uses Hermes' official `--no-supervise`/`HERMES_GATEWAY_NO_SUPERVISE` behavior while Compose owns restart; bootstrap records stopped s6 intent with the official `hermes gateway stop` command so the image does not restore a second gateway.

Development non-inference checks:

```bash
./scripts/dev-infra.sh status
curl --fail http://127.0.0.1:18765/healthz
curl --fail http://127.0.0.1:19119/api/health
docker inspect --format '{{.State.Health.Status}}' open-work-hub-dev-hermes-gateway
docker inspect --format '{{.State.Health.Status}}' open-work-hub-dev-hermes-terminal-egress
docker inspect --format '{{.State.Health.Status}}' open-work-hub-dev-hermes-terminal-broker
```

Use `docker compose --env-file .env -f ops/compose/open-work-hub-dev.infra.yml logs --tail 200 <service>` for focused development logs. Relevant services are `hermes-bootstrap`, `hermes-gateway`, `hermes-dashboard`, `hermes-terminal-egress`, and `hermes-terminal-broker`. Do not print container environments or profile configuration files because they can contain credentials.

For a terminal session, verify that generated files appear under `/workspace`, the broker file-list endpoint sees them, drag selection works in the browser, downloads are ownership-authorized, and stopping the session archives artifacts before terminal state. Never expose the broker port through a public reverse proxy.

## Troubleshooting

| Symptom                                             | Check                                                                                                                     | Resolution boundary                                                                                                                                          |
| --------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------- | ------------------------------------------------------------------------------------------------------------------------------------------------------------ |
| Public site returns `502 Bad Gateway`               | API/web listener, development reverse proxy, then Hermes service health                                                   | Restore the expected fixed listener; do not move a service to an arbitrary port.                                                                             |
| Chat request returns `500`                          | `hermes-bootstrap` completion, gateway health/logs, enabled flag, API key, both allowed OpenRouter models, managed policy | Correct environment/bootstrap configuration; preserve the single explicit fallback and do not add request rewriting.                                         |
| Model call returns `502` after about 300 seconds    | iron-proxy log, OpenRouter provider attempts/router metadata, primary/fallback transition                                 | Treat 300 seconds as the bounded upstream-header deadline; repair provider routing or credentials instead of adding layered retries.                         |
| Paper research repeatedly returns `429`             | `/admin/ai-tools`, selected profile toolsets, and the enabled research source                                             | Disable the throttled source or provision its supported credential, then use another enabled source. Start a new terminal for terminal-policy changes.       |
| Terminal remains “preparing”                        | broker and egress health, Docker socket access, sandbox network, session row/runtime reconciliation                       | Repair the failed control-plane dependency; preserve the user's private profile and workspace volume.                                                        |
| `Title already in use by session ...`               | active/archiving session ownership and whether its labeled runner is actually live                                        | Adopt the one valid live runtime or complete archival; do not create a second session with the same profile.                                                 |
| Generated file is absent from downloads             | file location, `HERMES_WRITE_SAFE_ROOT`, `/workspace` mount, broker listing                                               | Results belong in `/workspace`; `/opt/data` is profile state and must never be exposed as artifacts. Start a new session after runner-environment changes.   |
| Text cannot be selected by dragging                 | `display.mouse_tracking` and the final TUI mouse-mode state                                                               | Keep browser TUI mouse tracking off; after selection use macOS `Cmd+C`, Windows/Linux `Ctrl+C`, or the conventional `Ctrl+Shift+C`.                          |
| Terminal stops after `Ctrl+C` but remains preparing | session projection, broker exit code, terminal maintenance heartbeat, and stopped runner status                           | Exit codes `0` and `130` are normal exits. Let reconciliation archive the session; repair a stale maintenance heartbeat rather than creating another runner. |
| Browser/web/search/media tool is listed but fails   | `hermes doctor`, `hermes tools list`, required backend credential/service, runner network policy                          | Provision the official backend deliberately and document its credential owner and isolation. Do not infer readiness from tool registration.                  |
| Fixed port is occupied                              | exact listener and expected project container identity                                                                    | Stop the foreign or stale listener. No automatic fallback ports are allowed.                                                                                 |

## Change checklist

Hermes run republishing and terminal-session maintenance depend on the shared Celery Beat scheduler. Its Redis dependency and successful-publication health check are owned by [Release Domain](../release/README.md#production-app-contract). Check Beat health when maintenance stops even if the API, gateway, and worker are healthy. A persistent development runtime must also outlive the interactive terminal that launched it; use the supervisor contract in [Release Domain](../release/README.md#persistent-development-runtime).

For every Hermes setup or runtime configuration change:

1. Check the pinned Hermes release's official CLI, config key, environment variable, headless mode, or extension point before adding an adapter. Record any remaining upstream gap next to the narrow adapter.
2. Update every applicable row in the [configuration ownership map](#configuration-ownership-map), including both Compose environments, `.env.example`, validators, constants, tests, and this document.
3. For an image upgrade, inspect the immutable digest, runtime UID/GID, Dockerfile dependencies, `hermes --version`, `hermes doctor`, `hermes tools list`, gateway/dashboard health endpoints, profile/config schema, MCP discovery behavior, iron-proxy API, and public CLI flags. Reassess and remove version-bound adapters when official support exists.
4. Verify that only the intended trusted containers can read `OPENROUTER_API_KEY`, that runner egress remains fail-closed, and that no secret is exported in profile archives, logs, API responses, or browser payloads.
5. Verify headless fixed-model/fallback behavior and terminal `/workspace`, profile, MCP approval, standard/YOLO, drag-selection, file-list/download, stop/archive, and broker-restart behavior affected by the change.
6. Run focused checks, widening when shared contracts change:

```bash
cd apps/api
uv run --python 3.12 --group dev pytest \
  tests/test_admin_hermes_tools.py \
  tests/test_hermes_bootstrap.py \
  tests/test_hermes_integration.py \
  tests/test_hermes_terminal.py \
  tests/test_hermes_terminal_egress.py \
  tests/test_alembic_migrations.py -q
cd ../..
pnpm check:api-contract
pnpm check:api-architecture
pnpm check:web-architecture
pnpm nx typecheck web
pnpm test:prod-app
pnpm check:skills
git diff --check
```

No health, smoke, or setup validation should make a paid model inference solely to prove readiness.

## Official upstream references

- [Hermes Docker](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/docker.md)
- [Hermes installation](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/getting-started/installation.md)
- [Hermes tools](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/tools.md)
- [Hermes toolsets reference](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/reference/toolsets-reference.md)
- [Hermes web search](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/web-search.md)
- [Hermes tool gateway](https://github.com/NousResearch/hermes-agent/blob/main/website/docs/user-guide/features/tool-gateway.md)

For implementation decisions, inspect the source matching the pinned image before relying on `main` documentation that may describe a newer release.
