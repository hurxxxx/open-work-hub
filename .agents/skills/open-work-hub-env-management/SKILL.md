---
name: open-work-hub-env-management
description: Manage Open Work Hub environment-variable contracts and local ignored env files without exposing values. Use when adding, renaming, removing, auditing, or safely installing `.env` settings or GitLab CI variable metadata. Do not use for incidental env mentions; secret rotation, GitLab writes, service restarts, and production changes require explicit scope.
---

# Open Work Hub Env Management

## Ground Rules

- Never print, paste, commit, diff, or summarize secret values. Report key names, counts, file modes, scopes, checksums, and redacted status only.
- `.env`, `.env.local`, and `.env.*` are ignored runtime files. `.env.example` is the committed safe key/default contract.
- Project-owned settings use `OPEN_WORK_HUB_*`; browser-exposed settings use `VITE_OPEN_WORK_HUB_*`. Never place a secret in a `VITE_*` variable.
- Keep typed settings, scripts, Compose files, documentation, and `.env.example` aligned when semantics change.
- Do not reintroduce retired project prefixes or internal-server paths.
- GitLab CI variables and secure files are external metadata. `glab variable list` and `glab securefile list` are for explicitly requested redacted audits only; they cannot reconstruct or synchronize a local `.env` file.

## Redacted Audit

```bash
bash .agents/skills/open-work-hub-env-management/scripts/env-inventory.sh
bash .agents/skills/open-work-hub-env-management/scripts/env-inventory.sh --gitlab
pnpm check:env-contract
```

To compare a candidate file's keyset and install it with mode `0600` without showing values:

```bash
bash .agents/skills/open-work-hub-env-management/scripts/local-env-files.sh \
  status --source /path/to/candidate.env --target .env

bash .agents/skills/open-work-hub-env-management/scripts/local-env-files.sh \
  install --source /path/to/candidate.env --target .env --dry-run
```

Run the install without `--dry-run` only when replacing the target is explicitly in scope. An existing differing target requires `--force`; the script creates a mode-`0600` backup first.

## Change Workflow

1. Search typed settings, scripts, Compose, Vite config, docs, and tests for the key.
2. Decide whether it is runtime config, a secret, browser-visible config, CI metadata, or a constant that belongs in code.
3. Update all in-scope consumers and `.env.example` safe placeholders/defaults.
4. Update ignored local env files only when requested; never copy their values into tracked fixtures or chat.
5. Run `pnpm check:env-contract` and focused settings/runtime tests.
6. Restart affected local processes only when the user asked for an operational update; env is normally read at process start.

For explicitly authorized GitLab CI variable changes, prefer input redirection or GitLab protected/masked variable mechanisms so values stay out of arguments, shell history, logs, and chat. Do not create project/group CI variables merely because a local setting was added.

## Verification

- Contract: `pnpm check:env-contract`
- Path assumptions: `pnpm check:path-hardcoding`
- Shell syntax: `bash -n dev.sh scripts/dev-env.sh scripts/dev-infra.sh scripts/infra-stack.sh`
- Final review: `git diff --check`, `git status --short`, and confirm no ignored env file was force-added.
