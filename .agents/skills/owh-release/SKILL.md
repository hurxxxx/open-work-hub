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
- Default to full release validation. For an explicit simplified/urgent/fast request, use the [release owner's opt-in procedure](../../../docs/domains/release/README.md#impact-based-release-validation); inspect the complete release diff, record selected/skipped checks, and let the selector fall back to full for higher impact. Do not parse prompt keywords or edit CI to bypass a failing check.
- Application rollout uses the guarded `pnpm app:prod:deploy` entrypoint from the production checkout, but promotion and deployment remain separately authorized actions.

```bash
git rev-parse HEAD
glab mr view <id-or-branch> --output json
glab ci list -r main
```

Required: affected checks, mergeability, configured GitLab checks, env/migration/data compatibility, image build evidence, rollback compatibility, and known limitations. Fast validation changes test selection only; production rollout gates remain intact. After an explicitly authorized production-checkout update, hand deployment to the production-operations workflow.
