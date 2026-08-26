---
name: open-work-hub-release-promotion
description: Prepare and validate an Open Work Hub GitLab release MR from `dev` to `main`, then hand off the merged revision to an explicitly owned release process. Use when preparing a release MR, validating a release candidate, or coordinating a Compose-infrastructure rollout. Do not use for ordinary feature MRs or claim full application deployment support.
---

# Release Promotion

- Candidate branch: `dev`; target: protected `main`.
- Create/inspect GitLab MR only when requested.
- Merge only with explicit authorization; no direct push to `main`.
- Evidence binds to latest source SHA or equivalent merge result.
- Production checkout update to `origin/main` only when rollout is scoped.
- Repo owns production Compose infra, not full app deploy automation.

```bash
git rev-parse HEAD
glab mr view <id-or-branch> --output json
glab ci list -r main
```

Required: affected checks, mergeability, configured GitLab checks, env/migration/data compatibility, rollback, known limitations. Stop on missing deploy entrypoint when full app rollout is requested.
