---
name: ai-do-development-environment
description: Manage AI-DO development environments, including the shared server dev infra and local developer app setup through published dev infra ports. Use when setting up local development, starting dev services, checking dev infra, or onboarding developers.
---

# AI-DO Development Environment

## Model

- Server dev checkout lives at `/projects/ai-do/dev`.
- Server dev checkout uses `AI_DO_ENV_PROFILE=dev` and API port `8001`.
- `/projects/ai-do/dev` is the live development server checkout and must stay on the `dev` branch. On-server development uses this checkout directly unless the user explicitly requests a parallel worktree branch. Local developer machines create normal feature branches in their current checkout instead of using `/projects/ai-do/worktrees`.
- Local developer machines run app processes locally and reach the shared server dev infra through published dev infra ports; endpoints live in `.env.local`.
- PostgreSQL is a native service/database in server dev and tests, not a Docker container. Do not pull or run PostgreSQL Docker images for AI-DO. If `pgvector` is missing, install/enable the native PostgreSQL `vector` extension and keep the planned pgvector path instead of falling back to Qdrant or non-vector behavior.
- Windows developers work natively (no WSL). See `docs/reference/setup-windows.md`.
- Retired preview-style development profiles are not used.

## Server Dev

```bash
cd /projects/ai-do/dev
git pull --ff-only origin dev
pnpm check:env-contract
pnpm check:runtime-separation
pnpm dev:infra:up
./dev.sh
pnpm dev:smoke
```

When applying a merged `dev` change to the shared server dev runtime, restart
the user service or managed dev process after the pull, then run the smoke:

```bash
cd /projects/ai-do/dev
git pull --ff-only origin dev
systemctl --user restart ai-do-dev-app.service
pnpm dev:smoke
```

If `https://dev.dwdcc.kr/` stays on "세션 확인 중", treat it as an API/session
bootstrap failure first. Check the API proxy and service logs before changing
code:

```bash
curl -sS -D - --max-time 15 https://dev.dwdcc.kr/api/v1/auth/bootstrap-status
systemctl --user --no-pager --plain status ai-do-dev-app.service
journalctl --user -u ai-do-dev-app.service --since '10 minutes ago' --no-pager
```

If API startup fails during Alembic with drift errors such as
`DuplicateTable`, `DuplicateColumn`, or missing objects while `alembic_version`
is behind, assume the shared dev DB has stale partial schema from an abandoned
branch. Do not stamp blindly. Compare the existing object to the current
migration and check row counts. Only remove or repair an empty partial artifact
that is clearly superseded by the current migration; if it contains data or the
intended state is unclear, stop and ask before destructive DB changes. After the
repair, run `alembic upgrade head`, restart `ai-do-dev-app.service`, and run
`pnpm dev:smoke`.

## Local Developer

Use `.env.local` (GitLab Secure File, `AI_DO_*` contract per `.env.example`) at the repo root.
Endpoints point at the server dev host and dev infra ports, not production. Run a single local api instance and never auto-migrate the shared dev DB.

Windows (native): see `docs/reference/setup-windows.md`.
If `.env.local` is missing or stale, this becomes an environment-secret
management task too. Add `ai-do-env-management`, then authenticate `glab` if
needed and download/update the `.env.local` GitLab Secure File without printing
values:

```bash
bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh status --profile local
bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh download --profile local --target .env.local
```

```powershell
# Windows PowerShell 5.1 (pwsh/PS7 not required)
powershell -ExecutionPolicy Bypass -File scripts\dev-windows-bootstrap.ps1   # one-time: deps + y-py build
powershell -ExecutionPolicy Bypass -File scripts\dev-windows-fetch-env.ps1   # one-time: install glab + fetch .env.local from GitLab Secure Files
powershell -ExecutionPolicy Bypass -File scripts\dev-windows.ps1             # web + api against remote dev infra
```

The fetch script auto-installs glab via winget when missing, configures the dwdcc GitLab host (HTTP on :8929), reads `GLAB_PAT`/`GITLAB_TOKEN` from the environment for non-interactive auth (falls back to `glab auth login`), and downloads the secure file named `.env.local` into the repo root. PAT generation remains a human step at the GitLab UI.

Linux/macOS:

```bash
pnpm check:env-contract
pnpm check:runtime-separation
./dev.sh --no-infra
```
