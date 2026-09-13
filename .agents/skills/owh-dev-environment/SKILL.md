---
name: owh-dev-environment
description: Use when setting up dependencies or operating the local dev stack. Covers minimal/full services and local smoke checks; excludes production operations and env-contract changes.
---

# Development Environment

## Contract

- Local stack: Node + pnpm, Python + `uv`, Docker Compose.
- Read versions from root `package.json` and Python project files. Initialize ignored `.env` only if absent; preserve existing values.
- Full infra: `ops/compose/open-work-hub-dev.infra.yml`.
- Minimal infra: PostgreSQL + Redis; disables storage/AI/search/video/RAG startup deps.
- Defaults: Web `127.0.0.1:4200`, API `127.0.0.1:8001`.
- For server setup, set `OPEN_WORK_HUB_WEB_DEV_HOST=0.0.0.0` in the development env and verify seed login through the server IP from the user's network; keep API and development databases on loopback. Follow [server access](../../../INSTALL.md#5-내-pc-브라우저에서-서버-접속).
- No shared-server, internal-network, OS-specific, native-DB-only, or fixed-checkout assumptions.
- Use `agent-browser` for first-run browser verification and interactive UI checks; follow [installation and browser verification](../../../INSTALL.md#41-agent-browser로-셋업-화면-확인).

## Commands

```bash
bash .agents/skills/owh-env-contracts/scripts/local-env-files.sh status --source .env.example --target .env
# Only for requested setup and status=missing_target:
bash .agents/skills/owh-env-contracts/scripts/local-env-files.sh install --source .env.example --target .env
pnpm install --frozen-lockfile
pnpm dev:infra:up
pnpm dev
pnpm dev:minimal
pnpm dev:login-smoke
./dev.sh --status
./dev.sh --restart
./dev.sh --stop
```

## Checks

- For organization bootstrap that includes GitLab/CI, follow [installation completion](../../../INSTALL.md#7-실행-종료재시작과-완료-확인): use IP-based GitLab without waiting for a domain, complete the authorized MR pipeline, and leave the development server running with verified external seed login. A local smoke pass is an intermediate result.
- Prepare Playwright only when running existing regression/E2E tests or when the requested change requires them; use the [conditional test setup](../../../INSTALL.md#42-기존-playwright-회귀검사가-필요한-경우). Preserve required test/CI checks; interactive browser verification does not replace them.
- Env semantics: `pnpm check:env-contract`.
- Runtime paths: `pnpm check:path-hardcoding`.
- Migration drift: inspect; do not stamp/delete to bypass.
- Production operations belong to `owh-production`.
