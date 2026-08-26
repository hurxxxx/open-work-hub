---
name: open-work-hub-mr-review-validation
description: Review an Open Work Hub GitLab merge request for mergeability, regressions, and project-contract risk. Use when the user explicitly asks to review an MR, decide whether it is safe to merge, or address existing MR findings. Do not use for ordinary implementation, local code reading, or an unrequested pre-commit self-review.
---

# MR Review Validation

## Target

1. Read `AGENTS.md`, affected code/tests, owner docs, accepted ADRs.
2. If live GitLab access is in scope: `glab mr view <id-or-branch> --output json`, `glab mr diff <id-or-branch>`.
3. Compare against target branch/merge result, not only working tree.
4. Record reviewed source SHA.
5. Do not checkout/edit/comment/approve/merge/push unless requested.

## Review Lens

- Contract: API/OpenAPI/generated clients/migrations/env/i18n/public TS types.
- Platform: manifests, workspace API prefixes, router composition, registries, LLM workloads, approval/audit/discovery.
- Security: server auth, secrets, upload/preview, SSRF, input bounds, prompt/log leakage.
- Architecture: app-module imports, extension points, state ownership, a11y, stable keys, test surface.
- Runtime/data: transactions, concurrency, retention, cleanup, queue routing, migrations, rollback.

Use [Vibe Harness](../../../docs/agents/vibe-coding-harness.md) for affected checks. Merge-ready requires latest SHA, clean mergeability, passing required checks, resolved blockers, and named residual risk.
