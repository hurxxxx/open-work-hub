---
name: open-work-hub-release-promotion
description: Prepare or validate an Open Work Hub promotion from `dev` to `main`. Use when the user explicitly requests that release action. Do not infer production checkout updates or deployment authorization from completed development work.
---

# Release Promotion

- Authorization lives in root `AGENTS.md`; never trigger this workflow automatically.
- Inspecting, creating an MR, merging, updating the production checkout, and deploying are separate actions and must each be in scope.
- Never push directly to protected `main`.
- Evidence binds to latest source SHA or equivalent merge result.
- Application rollout uses the guarded `pnpm app:prod:deploy` entrypoint from the production checkout, but promotion and deployment remain separately authorized actions.

```bash
git rev-parse HEAD
glab mr view <id-or-branch> --output json
glab ci list -r main
```

Required: affected checks, mergeability, configured GitLab checks, env/migration/data compatibility, image build evidence, rollback compatibility, and known limitations. After an explicitly authorized production-checkout update, hand deployment to the production-operations workflow.
