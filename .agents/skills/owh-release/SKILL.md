---
name: owh-release
description: Use when explicitly preparing or validating dev-to-main promotion. Covers release evidence and the protected branch contract; does not include updating prod or deploying.
---

# Release Promotion

- Authorization lives in root `AGENTS.md`; never trigger this workflow automatically.
- Inspecting, creating an MR, merging, updating the production checkout, and deploying are separate actions and must each be in scope.
- Never push directly to protected `main`.
- Before creating or merging `dev -> main`, verify remote `dev` exists and is protected. Never request or allow source-branch removal for this release MR.
- Evidence binds to latest source SHA or equivalent merge result.
- Application rollout uses the guarded `pnpm app:prod:deploy` entrypoint from the production checkout, but promotion and deployment remain separately authorized actions.

```bash
git rev-parse HEAD
glab mr view <id-or-branch> --output json
glab ci list -r main
```

Required: affected checks, mergeability, configured GitLab checks, env/migration/data compatibility, image build evidence, rollback compatibility, and known limitations. After an explicitly authorized production-checkout update, hand deployment to the production-operations workflow.
