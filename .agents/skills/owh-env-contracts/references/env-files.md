# Env Management

## Rules

- Never print/paste/commit/diff secret values. Report keys/counts/modes/scopes/checksums/redacted status only.
- `.env*` runtime files are ignored; `.env.example` is committed safe contract.
- Project env: `OPEN_WORK_HUB_*`; browser env: `VITE_OPEN_WORK_HUB_*`; no secrets in `VITE_*`.
- Keep typed settings, scripts, Compose, docs, tests, and `.env.example` aligned.
- GitLab CI variables/secure files are external metadata; audit with `glab` only when requested.

## Commands

```bash
bash .agents/skills/owh-env-contracts/scripts/env-inventory.sh
bash .agents/skills/owh-env-contracts/scripts/env-inventory.sh --gitlab
bash .agents/skills/owh-env-contracts/scripts/local-env-files.sh status --source /path/to/candidate.env --target .env
bash .agents/skills/owh-env-contracts/scripts/local-env-files.sh install --source /path/to/candidate.env --target .env --dry-run
pnpm check:env-contract
pnpm check:path-hardcoding
```

Install without `--dry-run` or use `--force` only when replacement is explicitly in scope. Restart processes only when operational update was requested.
