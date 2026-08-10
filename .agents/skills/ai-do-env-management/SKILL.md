---
name: ai-do-env-management
description: Manage AI-DO environment contracts and protected secret storage without exposing values. Use when changing or auditing env semantics, runtime .env files, GitLab CI/CD variables, or Secure Files, and when explicitly retrieving `.secure` as 시스템 운영 정보 대장, 시스템 관리 대장, 비번/비밀번호 관리, or 인증 관리. Do not use for incidental mentions or naming/policy questions; upload, restart, and rotation require explicit scope.
---

# AI-DO Env Management

## Ground Rules

- Never print, paste, commit, or summarize secret values. Show key names, counts, scopes, checksums, and redacted metadata only.
- `.env`, `.env.local`, and `.env.*` are ignored. `.env.example` is the committed key contract.
- The runtime `.env` keysets for `/projects/ai-do/dev`, `/projects/ai-do/prod`, `.env.local`, and `.env.example` must stay identical unless a deliberate exception is documented.
- Prod values must be production-only; local developer values may point app processes at the server dev infra through the published server dev ports.
- Project-owned keys use `AI_DO_*`. External/tooling keys may use their established names such as `COMPOSE_PROJECT_NAME`, `VITE_*`, `GITLAB_*`, and `HF_TOKEN`.
- Do not reintroduce the legacy aliases and provider-global names enumerated in `FORBIDDEN_ENV_PATTERNS` in `scripts/check-env-contract.py`, or ambiguous duplicate keys.
- If a key is added, removed, renamed, or defaults change in runtime `.env` files, update the matching GitLab Secure File profiles in the same workflow unless the user explicitly asks for a local-only change.
- Runtime processes read env at start. After changing env files or GitLab-sourced env, restart the affected dev/prod services before verification.

## Quick Audit

Run the bundled redacted inventory first:

```bash
bash .agents/skills/ai-do-env-management/scripts/env-inventory.sh /projects/ai-do/dev
```

Then run the contract checker from the checkout being changed:

```bash
pnpm check:env-contract
```

Expected healthy shape: no duplicate keys, matching keysets across dev/prod/example, all typed settings covered, and no forbidden legacy env tokens in tracked source.
Also run the value-level guard:

```bash
pnpm check:runtime-separation
```

Check Secure Files drift without printing values:

```bash
bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh status --profile production
bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh status --profile local
```

## Change Workflow

1. Locate usage before editing:
   - Search settings classes, scripts, compose files, Vite config, systemd templates, and docs with `rg`.
   - Confirm whether the key is runtime config, secret, build-time frontend config, CI metadata, or a derived constant that should not be env-managed.
2. Classify the key:
   - `AI_DO_*`: normal app/service config.
   - `VITE_*`: browser-exposed build/dev value; never put secrets here.
   - `GITLAB_*`: GitLab API/package handoff config.
   - Non-secret constant: keep in code or docs unless it genuinely differs by environment.
3. Update all required surfaces:
   - typed settings and validation logic
   - `.env.example`
   - dev runtime `.env`
   - prod runtime `.env`
   - `.env.local` when developer machines need the same contract
   - local/onboarding instructions when local developers need the key
   - scripts, compose files, systemd templates, and tests that consume it
4. Re-run `pnpm check:env-contract` and `pnpm check:runtime-separation`.
5. Compare and update Secure Files:
   ```bash
   bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh status --profile production
   bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh upload --profile production --source /projects/ai-do/prod/.env
   bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh status --profile local
   bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh upload --profile local --source /path/to/.env.local
   ```
   Skip an upload only when the target profile is intentionally unavailable or the user explicitly wants a local-only runtime change.
6. Restart affected services and verify actual instance separation with `pnpm check:runtime-separation:live` when prod/dev services are expected to be running.

## GitLab Storage Policy

- Use GitLab Secure Files for whole environment snapshots such as `.env.production` and `.env.local` when the goal is to distribute a full runtime env file.
- Use GitLab CI/CD Variables for individual pipeline values. Prefer environment scopes (`prod`, `local`, or `*`) and set `--masked`, `--hidden`, and `--protected` where GitLab allows them.
- Do not use the Generic Package Registry for `.env` secrets. In this repo it is for desktop release artifacts and other non-secret build handoffs.
- Secure Files are create/remove, not in-place update. To replace an env file, list metadata, remove the old file by id, upload the new file, then list metadata again. Do not download or display contents unless explicitly necessary, and never paste values into chat.
- Canonical Secure File profile names are:
  - `production` -> `.env.production`, normally sourced from `/projects/ai-do/prod/.env`
  - `local` -> `.env.local`, normally sourced from a developer-safe `.env.local`
- `.secure` is the System Operations Information Ledger (`시스템 운영 정보 대장`), not a runtime env file. Its remote GitLab Secure File is canonical; `/projects/ai-do/dev/.secure` is a Git-ignored `0600` working copy. Never source it.
- For `.env.local` setup on `http://128.1.253.101:8929/`, request a PAT with `api` scope only when `glab` is unauthenticated. Use a secure prompt, `--stdin`, and the keyring; never put the token in arguments or output.

## `.secure` Retrieval Requests

- Route explicit retrieve/download/open requests using the aliases in the description to `.secure`; naming or policy questions are read-only.
- Retrieval authorizes download only, never content display, upload, rotation, or service changes.
- Follow the GitLab Storage Policy above and the commands below: run redacted status first, reuse a matching `0600` copy, download a missing copy, and ask before replacing a differing copy unless refresh was explicit. Do not rely on a dated `docs/final/` snapshot as the current ledger procedure.
- Require `remote_count=1`, `status=match`, and mode `0600`; return only the path and redacted metadata.

```bash
bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh status --secure-file-name .secure --source /projects/ai-do/dev/.secure
bash .agents/skills/ai-do-env-management/scripts/secure-env-files.sh download --secure-file-name .secure --target /projects/ai-do/dev/.secure
stat -c '%a %n' /projects/ai-do/dev/.secure
```

Use `glab variable set SOME_KEY --scope=prod --masked --protected < /path/to/value.txt` for individual CI/CD variables, keeping values out of shell history when practical.

## Verification

- Contract: `pnpm check:env-contract`
- Runtime separation, static: `pnpm check:runtime-separation`
- Runtime separation, live server: `pnpm check:runtime-separation:live`
- Shell syntax: `bash -n dev.sh prod.sh scripts/dev-env.sh scripts/prod-systemd.sh scripts/infra-stack.sh`
- Dev API should identify as a dev instance on the dev port/proxy.
- Prod API should identify as `prod-api` with `environment=production` on port `8000`.
- Prod smoke: `./prod.sh smoke`
- Before commit: `git diff --check`, `git status --short`, and verify no ignored `.env` content was force-added.
