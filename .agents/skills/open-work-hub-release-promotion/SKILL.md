---
name: open-work-hub-release-promotion
description: Prepare or validate an Open Work Hub promotion from `dev` to `main`. Use when the user explicitly requests that release action. Do not infer release or deployment authorization from completed development work, and do not claim full application deployment support.
---

# Release Promotion

- Authorization lives in root `AGENTS.md`; never trigger this workflow automatically.
- Inspecting, creating an MR, merging, updating the production checkout, and deploying are separate actions and must each be in scope.
- Never push directly to protected `main`.
- Evidence binds to latest source SHA or equivalent merge result.
- Repo owns production Compose infra, not full app deploy automation.

```bash
git rev-parse HEAD
glab mr view <id-or-branch> --output json
glab ci list -r main
```

Required: affected checks, mergeability, configured GitLab checks, env/migration/data compatibility, rollback, known limitations. Stop on missing deploy entrypoint when full app rollout is requested.
