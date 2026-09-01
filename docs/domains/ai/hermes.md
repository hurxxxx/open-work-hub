# Hermes Headless Agent

Hermes is the headless runtime for the general-purpose chatbot. Open Work Hub owns identity, workspace authorization, durable projections, and UI controls; Hermes owns the autonomous agent loop, model calls, tool orchestration, approvals, sessions, and scheduled jobs. Specialized durable AI graph workloads remain on the existing graph runtime.

## Fixed runtime contract

- Hermes image: `nousresearch/hermes-agent:v2026.8.31`, pinned by digest in both compose files.
- Provider: `openrouter`.
- Model: `qwen/qwen3.8-flash`.
- Model policy: the main model is fixed, primary fallback chains are disabled, and Hermes' official `auxiliary.openrouter_model` setting replaces its built-in Gemini auxiliary fallback with the same Qwen model. Bootstrap also removes the legacy `fallback_model` key; no Hermes runtime patch is used for model routing.
- Provider credential: `OPENROUTER_API_KEY`. It is passed only to the one-shot Hermes bootstrap container, persisted in the Hermes profile store, and explicitly removed from Open Work Hub API, worker, web, migration, and beat processes.
- Runtime and dashboard bind to `127.0.0.1`. The API reaches them through `OPEN_WORK_HUB_HERMES_RUNTIME_BASE_URL` and `OPEN_WORK_HUB_HERMES_MANAGEMENT_BASE_URL`.

Do not add a model selector to the chatbot or accept a caller-supplied provider/model. The server-side constants in `apps/api/src/open_work_hub_api/core/settings.py` are authoritative.

## Ownership and authorization

Each `(workspace_id, user_id)` has one deterministic, isolated Hermes profile. Open Work Hub never exposes Hermes credentials to the browser. User routes are workspace-scoped under `/api/v1/workspaces/{workspace_slug}/agent`; administrator inventory and reconciliation routes are under `/api/v1/admin/hermes`.

Hermes accesses Open Work Hub tools only through `/api/v1/internal/hermes/mcp` with a profile-derived HMAC bearer token. The bridge revalidates the workspace, user, and membership on every request. It exposes a stable workspace/user-entitled discovery surface only while that profile has exactly one active local run, then re-lists and validates tools against that run's `allowed_app_ids` immediately before every call. This keeps Hermes' cached MCP discovery usable across runs without widening execution scope. Missing run context fails closed. The internal MCP server is configured as `untrusted`, so write-capable tools pass through Hermes approval before execution. The bridge also matches the official Hermes trust prompt to the exact profile-scoped server, tool, and local run, accepts only an approval resolved through the Open Work Hub API, binds it to the argument digest, and consumes it before execution. Approval evidence expires after five minutes and cannot be replayed.

Hermes MCP connections are process-global and keyed by server name. Every interactive managed profile therefore uses a deterministic, globally unique physical name for its internal and administrator-added MCP servers. The normal profile reconciliation performed before session/run admission removes inherited or legacy unscoped names; bootstrap does not duplicate that application-level reconciliation.

Hermes `v2026.8.31` multiplex API mode normally discovers MCP servers only from the launch profile; its `/v1/runs` handler has no documented per-request-profile discovery hook or configuration. The pinned gateway is therefore launched through the narrow, version-bound adapter `ops/hermes/gateway_entry.py`, which performs Hermes' own idempotent discovery for the already authenticated request profile in a worker thread before run admission. It fails admission with `503` if a managed interactive profile's internal bridge is not connected. This is the only private Hermes integration seam: it does not replace the run loop, tool dispatcher, sessions, approval machinery, or lifecycle management, and should be removed when Hermes exposes an official hook.

Hermes-native cron jobs run in a second deterministic `-jobs` profile. That profile inherits the fixed model/provider credentials but the service removes and verifies the absence of every MCP server. This separation is mandatory because Hermes permits API runs and cron agents to execute concurrently; without it, a cron agent could borrow an interactive profile's process-global MCP connection. Scheduled jobs may use Hermes-native built-in tools, but they cannot use MCP integrations or call workspace tools through the internal bridge.

## Durability and control

Open Work Hub persists profile/session/job bindings, run state, sanitized run events, approval records, run inputs, and a transactional dispatch outbox. A dedicated Celery queue executes Hermes runs; beat republishes pending outbox records. The browser consumes Open Work Hub's replayable SSE projection instead of connecting to Hermes directly.

Supported controls are status and capability inspection, recent run monitoring, stop, steer, one-time approve/deny, job create/list/pause/resume/run/delete, profile reconciliation, fixed-model enforcement, MCP inventory, and skill toggles. Only one active run is admitted per profile so MCP scope cannot become ambiguous.

## Required environment

Set these in both checkout environment files using distinct non-placeholder secrets:

- `OPENROUTER_API_KEY` (at least 16 characters)
- `OPEN_WORK_HUB_HERMES_API_KEY` (production: at least 32 characters)
- `OPEN_WORK_HUB_HERMES_MANAGEMENT_TOKEN` (production: at least 32 characters)
- `OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET` (at least 32 characters)

Production validation also requires `OPEN_WORK_HUB_HERMES_ENABLED=true`, loopback URLs whose ports match the declared Hermes ports, the internal MCP URL targeting the application API, and `OPEN_WORK_HUB_HERMES_PROFILE_CLONE_SOURCE=default`.

## Operations

Development infrastructure starts Hermes automatically when `OPENROUTER_API_KEY` is present:

```bash
./scripts/dev-infra.sh up
./scripts/dev-infra.sh status
```

Production commands validate the environment before migration or startup:

```bash
./scripts/prod-app.sh up
./scripts/prod-app.sh status
```

The bootstrap service must complete before gateway startup; gateway and dashboard must be healthy before API and worker startup. Re-run the compose startup after rotating either Hermes runtime or OpenRouter credentials so bootstrap synchronizes the root and existing named profiles. The gateway uses Hermes' official `--no-supervise`/`HERMES_GATEWAY_NO_SUPERVISE` behavior while Compose owns restart; bootstrap records the corresponding stopped s6 intent with the official `hermes gateway stop` command so the image does not restore a second gateway from persistent state. Do not remove or disable the profile-scoped internal MCP server from managed interactive profiles.

No deployment or smoke command should make a paid model inference solely as a health check. Runtime health, capabilities, authenticated profile inventory, and application contract tests are the non-billable readiness checks.
