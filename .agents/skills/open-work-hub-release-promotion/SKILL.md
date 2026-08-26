---
name: open-work-hub-release-promotion
description: Prepare and validate an Open Work Hub GitLab release MR from `dev` to `main`, then hand off the merged revision to an explicitly owned release process. Use when preparing a release MR, validating a release candidate, or coordinating a Compose-infrastructure rollout. Do not use for ordinary feature MRs or claim full application deployment support.
---

# Open Work Hub Release Promotion

## Current Flow

1. Confirm the candidate branch and intended release scope; site integration lands on `dev` and production promotion targets protected `main`.
2. Run affected checks from `docs/agents/vibe-coding-harness.md` and record the exact candidate SHA.
3. Inspect or create a GitLab MR from `dev` to `main` only when the user explicitly requests the external action.
4. Require mergeability, review, and configured GitLab checks for the exact source SHA.
5. Merge only with explicit authorization. Do not push directly to `main` as a release shortcut.
6. Update a dedicated clean `prod` checkout to the resulting `origin/main` only when that checkout and rollout are in scope.
7. The repository can manage production Compose infrastructure with `pnpm infra:prod:status` and `pnpm infra:prod:up`; it cannot deploy the full application.

Useful read-only evidence:

```bash
git rev-parse HEAD
glab mr view <id-or-branch> --output json
glab ci list -r main
```

## Required Evidence

- The MR targets `main` from `dev` and the reviewed/check SHA matches its latest source head.
- Affected repository checks pass; use `pnpm ci:all` only when release risk justifies the full suite.
- When release validation CI is introduced, its evidence is bound to the same source SHA or equivalent merge result.
- Environment, migration, data compatibility, and rollback responsibilities are explicit.
- Release notes, when requested, describe user-visible outcomes and known limitations without claiming unavailable deployment automation.

## Stop Conditions

Stop if release would require an unrequested push/merge, a dirty or ambiguous production checkout, unknown env ownership, unsafe migration, missing rollback, or a full application deploy. The missing deploy entrypoint must be handled by an owner-approved runbook or implementation before claiming rollout completion.
