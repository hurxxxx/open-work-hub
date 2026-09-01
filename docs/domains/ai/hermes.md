# Hermes Setup and Runtime Contract

Hermes powers both the headless general-purpose chatbot and the raw Hermes Terminal app. Open Work Hub owns identity, workspace authorization, durable projections, and UI controls; Hermes owns the autonomous agent loop, model calls, tool orchestration, sessions, and native terminal behavior. Specialized durable AI graph workloads remain on the existing graph runtime.

## Ownership and maintenance rule

This file is the single current owner for Hermes installation, configuration, runtime boundaries, and operational setup. Update it in the same change whenever Hermes image pins, model/provider policy, environment variables, ports, profiles, MCP, tool availability, egress, terminal mounts, lifecycle, limits, Compose services, or bootstrap/deployment behavior changes. An ADR is appropriate only for a new cross-domain architectural decision; the ADR must link here instead of duplicating mutable setup values.

Code and tests remain authoritative for implemented behavior. Use the [configuration ownership map](#configuration-ownership-map) and [change checklist](#change-checklist) to keep every duplicated pin and contract aligned.

## Fixed runtime contract

- Hermes image: `nousresearch/hermes-agent:v2026.8.31@sha256:64923faeae267792bf9bf87fe3b4c4869e35004e360c7df01730ad801b74d524`.
- Provider: `openrouter`.
- Model: `qwen/qwen3.8-flash`.
- Model policy: the main model is fixed, primary fallback chains are disabled, and Hermes' official `auxiliary.openrouter_model` setting replaces its built-in Gemini auxiliary fallback with the same Qwen model. Bootstrap also removes the legacy `fallback_model` key; no Hermes runtime patch is used for model routing.
- Provider credential: `OPENROUTER_API_KEY`. Headless bootstrap persists it in the Hermes profile store. Terminal mode passes the real key only to the trusted iron-proxy container; terminal runners receive a revocable proxy token and public CA instead. The credential is explicitly removed from Open Work Hub API, worker, web, migration, beat, terminal broker, and terminal runner processes.
- Runtime, dashboard, and terminal broker bind to loopback host addresses. The API reaches them through the declared `OPEN_WORK_HUB_HERMES_*_BASE_URL` values.
- The official image runtime user is UID/GID `10000`. Named-volume ownership and runner processes must continue to use that identity.

Do not add a model selector to the chatbot or accept a caller-supplied provider/model. The server constants in `apps/api/src/open_work_hub_api/core/settings.py` are authoritative. Hermes upstream supports additional providers such as OpenAI, Anthropic, Gemini, Ollama, and other OpenAI-compatible endpoints, but this deployment intentionally configures only OpenRouter. Enabling another provider is a setup and credential-boundary change, not an automatic consequence of its client library being present in the image.

## Official image baseline and capability boundary

Open Work Hub uses the official Hermes Docker image rather than running the macOS, Windows, or Linux host installer. At the current pin the image includes Hermes and its Python extras, Node.js/npm, Playwright Chromium assets, `ripgrep`, `ffmpeg`, Git, SSH client, `xz`, and build tooling. It is not a reduced API-only Hermes installation.

Hermes can register broad built-in toolsets including web, browser, terminal, file, code execution, vision, image generation, text-to-speech, skills, todo, memory, session search, clarification, delegation, cron, and computer use. Registration does not mean every tool is operational. Optional search/browser/media backends still require their documented credentials, services, or lazy-installed executables. The current Open Work Hub contract supplies OpenRouter and the Open Work Hub MCP bridge only; it does not implicitly provision Firecrawl, Exa, Browserbase, FAL, voice providers, Home Assistant, Spotify, or host desktop access.

Terminal runners are headless, container-isolated environments. They do not inherit the host user's home directory, GUI applications, native clipboard, Docker socket, private network, or macOS/Windows integrations. Use Hermes' official `hermes doctor` and `hermes tools list` commands to inspect a pinned image or profile, but never treat a registered tool as ready without checking its credential and runtime requirements. Do not make a paid inference solely as a readiness check.

## Configuration ownership map

| Contract                        | Current owner paths                                                                                                                                                                                             | Alignment rule                                                                                                                                                  |
| ------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------------- | --------------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Release, provider, model        | `apps/api/src/open_work_hub_api/core/settings.py`, `ops/hermes/bootstrap.py`, `apps/api/src/open_work_hub_api/domains/hermes_terminal/broker_runtime.py`, `apps/web/src/app-modules/chatbot/api/chatbot-api.ts` | Keep release/provider/model metadata identical; regenerate API contracts when the exposed schema changes.                                                       |
| Official image and digest       | `ops/compose/open-work-hub-dev.infra.yml`, `ops/compose/open-work-hub-prod.app.yml`, terminal broker runtime                                                                                                    | Pin every service and dynamically created runner to the same immutable digest.                                                                                  |
| Headless profile bootstrap      | `ops/hermes/bootstrap.py`                                                                                                                                                                                       | Use Hermes public config/profile APIs for credentials, model, auxiliary model, and fallback policy.                                                             |
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
- An OpenRouter key valid for `qwen/qwen3.8-flash`.
- An OpenRouter provider-side guardrail that allows `qwen/qwen3.8-flash` and rejects other models. This is required because a YOLO terminal can issue arbitrary public network requests through the controlled egress path.
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

The development defaults are runtime `18642`, dashboard `19119`, and terminal broker `18765`. The application API remains on its separately declared development port. A foreign listener on a fixed Hermes Terminal broker port is a startup error; stop the listener instead of selecting a random replacement port.

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

The production validator rejects disabled Hermes, missing or duplicate secrets, non-loopback control URLs, mismatched URL/port pairs, port collisions, the wrong MCP path, and a non-default clone source. Validate before using the normal release runbook:

```bash
node scripts/prod-app-config.mjs .env
./scripts/prod-app.sh status
```

Deployment remains governed by `docs/domains/release/README.md` and requires explicit release authorization. Development and production checkouts have separate `.env` files and must not share placeholder secrets.

## Ownership and authorization

Each `(workspace_id, user_id)` has one deterministic, isolated Hermes profile. Open Work Hub never exposes Hermes credentials to the browser. User routes are workspace-scoped under `/api/v1/workspaces/{workspace_slug}/agent`; administrator inventory and reconciliation routes are under `/api/v1/admin/hermes`.

Hermes accesses Open Work Hub tools only through `/api/v1/internal/hermes/mcp` with a profile-derived HMAC bearer token. The bridge revalidates the workspace, user, and membership on every request. It exposes a stable workspace/user-entitled discovery surface only while that profile has exactly one active local run, then re-lists and validates tools against that run's `allowed_app_ids` immediately before every call. Missing run context fails closed. The headless internal MCP server is configured as `untrusted`, so write-capable tools pass through Hermes approval before execution. Approval evidence is bound to the exact server, tool, local run, and normalized argument digest, expires after five minutes, and cannot be replayed.

Hermes MCP connections are process-global and keyed by server name. Every interactive managed profile therefore uses a deterministic, globally unique physical name for its internal and administrator-added MCP servers. Normal profile reconciliation before session/run admission removes inherited or legacy unscoped names.

Hermes `v2026.8.31` multiplex API mode discovers MCP servers from the launch profile and exposes no documented per-request-profile discovery hook. The pinned gateway therefore uses the narrow, version-bound `ops/hermes/gateway_entry.py` adapter to perform Hermes' own idempotent discovery for the authenticated request profile before run admission. It fails admission with `503` if the managed internal bridge is not connected. It does not replace the run loop, tool dispatcher, sessions, approval machinery, or lifecycle management.

Hermes-native cron jobs run in a second deterministic `-jobs` profile. That profile inherits the fixed model/provider credentials but removes and verifies the absence of every MCP server. Scheduled jobs may use Hermes-native built-in tools, but they cannot use MCP integrations or Open Work Hub workspace tools.

## Durability and control

Open Work Hub persists profile/session/job bindings, run state, sanitized run events, approval records, run inputs, and a transactional dispatch outbox. A dedicated Celery queue executes Hermes runs; beat republishes pending outbox records. The browser consumes Open Work Hub's replayable SSE projection instead of connecting to Hermes directly.

Supported controls are status and capability inspection, recent run monitoring, stop, steer, one-time approve/deny, job create/list/pause/resume/run/delete, profile reconciliation, fixed-model enforcement, MCP inventory, and skill toggles. Only one active run is admitted per profile so MCP scope cannot become ambiguous.

## Hermes Terminal

`hermes-terminal` is a workspace app in All Apps and is available to every workspace member when `hermes_enabled` is enabled. Each session belongs to exactly one `(workspace_id, user_id)` pair; another member of the same workspace cannot list, attach to, stop, approve, or download its data. The administrator-only Codex Terminal remains a separate app.

The browser renders Hermes' official raw TUI through the shared xterm surface. It does not reimplement the agent loop or tool UI. Desktop places generated files and pending Open Work Hub approvals on the right; narrow screens place the same panel below the terminal. Active files come from the private runner workspace, completed-session artifacts come from object storage, and every download is reauthorized by workspace membership and session ownership.

Creating a session always starts in standard mode. YOLO can be selected only after a fresh acknowledgement in that creation dialog; the browser never remembers it as a default. The broker appends Hermes' official `--yolo` flag only for that session. YOLO disables Hermes-native dangerous-command prompts, but it never bypasses Open Work Hub authentication, membership checks, exact write-tool approval, network isolation, container isolation, the fixed model, or artifact limits.

The broker invokes the pinned image with Hermes' public CLI:

```text
chat --tui --in /workspace --checkpoints --provider openrouter --model qwen/qwen3.8-flash [--yolo]
```

Terminal profile configuration uses Hermes' public `config set`, `config unset`, and `config check` commands:

- `model.provider=openrouter`
- `model.default=qwen/qwen3.8-flash`
- `fallback_providers=[]` and no legacy `fallback_model`
- `auxiliary.free_only=false`
- `auxiliary.openrouter_model=qwen/qwen3.8-flash`
- `display.mouse_tracking=off`
- one session-scoped Open Work Hub MCP server and fresh proxy/MCP tokens

The runner environment and mounts must preserve these path contracts:

- `HERMES_HOME=/opt/data/profiles/terminal`: private user profile and Hermes state.
- `/opt/data`: a private named profile volume. It is a container path, not the host machine's `/opt` directory.
- `/workspace`: a separate private session volume and the only generated-result root exposed by file listing and download.
- `HERMES_WRITE_SAFE_ROOT=/workspace`: Hermes' official file safety boundary, aligned with `--in /workspace` and the artifact panel.
- `HERMES_TUI_DISABLE_MOUSE=1` plus `display.mouse_tracking=off`: Hermes' official browser-TUI behavior, allowing xterm drag selection and normal clipboard copy shortcuts.
- `HTTP_PROXY`/`HTTPS_PROXY`, the iron-proxy CA variables, and the sandbox network: the only runner egress route.

Do not move generated results to `/opt/data`, extend artifact listing into the profile volume, add Gemini filtering, rewrite model requests, patch the TUI, or add a file-copy workaround. Correct the official Hermes setting or the shared `/workspace` contract instead. Existing containers receive environment changes only after a new terminal session starts.

Terminal profiles are separate from headless profiles while retaining the same deterministic workspace/user binding. Before a profile archive is exported, the broker uses the official `hermes config unset` command to remove the temporary proxy token and session MCP token. The next session restores fresh values through the same public configuration surface; durable profile archives never carry those ephemeral credentials.

The terminal MCP server is trusted by the Hermes profile because Open Work Hub itself creates and enforces the exact write approval at the MCP boundary. Discovery is restricted to server-derived `allowed_app_ids`; every write request is bound to the exact tool and normalized argument digest, expires after five minutes, and is consumed atomically once. This approval remains mandatory in YOLO mode.

### Terminal isolation and retention

- The trusted terminal broker is the only component with the Docker socket. Runners have a read-only root filesystem, private workspace/profile volumes, dropped capabilities, resource limits, no Docker socket, and only the internal sandbox network.
- Hermes' official iron-proxy is the runner's only egress path. Its loopback, link-local, RFC1918, and cloud-metadata deny list remains enabled. The pinned iron-proxy 0.39 secrets transform uses its supported `require: false` setting so TLS CONNECT can complete before the inner proxy token is replaced; the real OpenRouter key remains available only inside the proxy process. The egress service publishes no host port.
- The pinned release's public `hermes egress setup` command is interactive and does not expose the required container listen/allow-list settings. `ops/hermes/terminal_egress.py` is a narrow non-interactive adapter over Hermes' exported iron-proxy functions; replace it with the CLI when Hermes exposes those controls.
- The broker binds only to `127.0.0.1:${OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_PORT}`. The default is `18765`. A foreign listener or mismatched project container is a hard error; there is no automatic port fallback.
- Limits default to one active session per workspace/user pair, two per user across workspaces, and twenty total. Admission is serialized in PostgreSQL. Idle sessions stop after two hours, completed artifacts expire after thirty days, and profile/workspace archives use the bounds in `.env.example`.
- A failed or interrupted archive remains in `archiving` while maintenance retries it. If the same runtime is running again after an operator restart, reconciliation restores the live session instead of archiving it as exited. After three genuine archive failures the session closes with an archive failure and maintenance removes its stopped runner and workspace volume. Profile volumes remain private and reusable.

## Operations and verification

The bootstrap service must complete before gateway startup; gateway and dashboard must be healthy before API and worker startup. Re-run Compose startup after rotating Hermes runtime or OpenRouter credentials so bootstrap synchronizes the root and existing named profiles. The gateway uses Hermes' official `--no-supervise`/`HERMES_GATEWAY_NO_SUPERVISE` behavior while Compose owns restart; bootstrap records stopped s6 intent with the official `hermes gateway stop` command so the image does not restore a second gateway.

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

| Symptom                                           | Check                                                                                                         | Resolution boundary                                                                                                                                        |
| ------------------------------------------------- | ------------------------------------------------------------------------------------------------------------- | ---------------------------------------------------------------------------------------------------------------------------------------------------------- |
| Public site returns `502 Bad Gateway`             | API/web listener, development reverse proxy, then Hermes service health                                       | Restore the expected fixed listener; do not move a service to an arbitrary port.                                                                           |
| Chat request returns `500`                        | `hermes-bootstrap` completion, gateway health/logs, enabled flag, API key, OpenRouter key, fixed model config | Correct environment/bootstrap configuration; do not add provider fallback or request rewriting.                                                            |
| Terminal remains “preparing”                      | broker and egress health, Docker socket access, sandbox network, session row/runtime reconciliation           | Repair the failed control-plane dependency; preserve the user's private profile and workspace volume.                                                      |
| `Title already in use by session ...`             | active/archiving session ownership and whether its labeled runner is actually live                            | Adopt the one valid live runtime or complete archival; do not create a second session with the same profile.                                               |
| Generated file is absent from downloads           | file location, `HERMES_WRITE_SAFE_ROOT`, `/workspace` mount, broker listing                                   | Results belong in `/workspace`; `/opt/data` is profile state and must never be exposed as artifacts. Start a new session after runner-environment changes. |
| Text cannot be selected by dragging               | `display.mouse_tracking` and the final TUI mouse-mode state                                                   | Keep browser TUI mouse tracking off; use macOS `Cmd+C` or Windows/Linux `Ctrl+Shift+C` after selection.                                                    |
| Browser/web/search/media tool is listed but fails | `hermes doctor`, `hermes tools list`, required backend credential/service, runner network policy              | Provision the official backend deliberately and document its credential owner and isolation. Do not infer readiness from tool registration.                |
| Fixed port is occupied                            | exact listener and expected project container identity                                                        | Stop the foreign or stale listener. No automatic fallback ports are allowed.                                                                               |

## Change checklist

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
  tests/test_hermes_bootstrap.py \
  tests/test_hermes_integration.py \
  tests/test_hermes_terminal.py -q
cd ../..
pnpm check:api-architecture
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
