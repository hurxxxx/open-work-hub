---
name: open-work-hub-release-promotion
description: Prepare and validate an Open Work Hub GitHub pull request into `main`, then hand off the merged revision to an explicitly owned release process. Use when preparing a release PR, validating a release candidate, or coordinating a Compose-infrastructure rollout. Do not use for ordinary feature PRs or claim full application deployment support.
---

# Open Work Hub Release Promotion

## Current Flow

1. Confirm the candidate branch and intended release scope; the repository's integration branch is `main`.
2. Run affected checks from `docs/agents/vibe-coding-harness.md` and record the exact candidate SHA.
3. Inspect or create a GitHub PR into `main` only when the user explicitly requests the external action.
4. Require mergeability, review, and configured GitHub checks for the exact head SHA.
5. Merge only with explicit authorization. Do not push directly to `main` as a release shortcut.
6. Update a dedicated clean `prod` checkout to the resulting `origin/main` only when that checkout and rollout are in scope.
7. The repository can manage production Compose infrastructure with `pnpm infra:prod:status` and `pnpm infra:prod:up`; it cannot deploy the full application.

Useful read-only evidence:

```bash
git rev-parse HEAD
gh pr view <number> --json baseRefName,headRefName,headRefOid,mergeable,mergeStateStatus,statusCheckRollup
gh pr checks <number>
```

## Required Evidence

- The PR targets `main` and the reviewed/check SHA matches its latest head.
- Affected repository checks pass; use `pnpm ci:all` only when release risk justifies the full suite.
- Environment, migration, data compatibility, and rollback responsibilities are explicit.
- Release notes, when requested, describe user-visible outcomes and known limitations without claiming unavailable deployment automation.

## Stop Conditions

Stop if release would require an unrequested push/merge, a dirty or ambiguous production checkout, unknown env ownership, unsafe migration, missing rollback, or a full application deploy. The missing deploy entrypoint must be handled by an owner-approved runbook or implementation before claiming rollout completion.
