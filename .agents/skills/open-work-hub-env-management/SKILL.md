---
name: open-work-hub-env-management
description: Manage Open Work Hub environment-variable contracts and local ignored env files without exposing values. Use when adding, renaming, removing, auditing, or safely installing `.env` settings or GitLab CI variable metadata. Do not use for incidental env mentions; secret rotation, GitLab writes, service restarts, and production changes require explicit scope.
---

# Env Management

## Rules

- Never print/paste/commit/diff secret values. Report keys/counts/modes/scopes/checksums/redacted status only.
- `.env*` runtime files are ignored; `.env.example` is committed safe contract.
- Project env: `OPEN_WORK_HUB_*`; browser env: `VITE_OPEN_WORK_HUB_*`; no secrets in `VITE_*`.
- Keep typed settings, scripts, Compose, docs, tests, and `.env.example` aligned.
- GitLab CI variables/secure files are external metadata; audit with `glab` only when requested.

## Commands

```bash
bash .agents/skills/open-work-hub-env-management/scripts/env-inventory.sh
bash .agents/skills/open-work-hub-env-management/scripts/env-inventory.sh --gitlab
bash .agents/skills/open-work-hub-env-management/scripts/local-env-files.sh status --source /path/to/candidate.env --target .env
bash .agents/skills/open-work-hub-env-management/scripts/local-env-files.sh install --source /path/to/candidate.env --target .env --dry-run
pnpm check:env-contract
pnpm check:path-hardcoding
```

Install without `--dry-run` or use `--force` only when replacement is explicitly in scope. Restart processes only when operational update was requested.
