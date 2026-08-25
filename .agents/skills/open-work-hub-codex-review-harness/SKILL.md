---
name: open-work-hub-codex-review-harness
description: Maintain Open Work Hub's repository-owned local Codex review policy, deterministic review checks, and review-output contract. Use when changing review guidance or adding a reusable local pre-PR review harness. Do not use to review a particular GitHub PR; use `open-work-hub-pr-review-validation` for that outcome.
---

# Open Work Hub Codex Review Harness

## Contract

- The repository currently has no source-controlled Codex CI runner or automated review-comment publisher. Do not imply one exists.
- A local review harness may inspect code and run checks, but it must not edit, commit, push, open/merge a PR, or publish comments unless the user separately authorizes those actions.
- Never pass credentials, credentialed remotes, `.env` contents, raw prompts, or unnecessary customer data into review output or artifacts.
- Bind review evidence to the exact `HEAD`, base ref, and diff being reviewed. If the source changes, rerun affected checks.
- Review output leads with concrete findings ordered by severity, cites files and lines, and separates blockers from residual risk.
- Keep the check router aligned with scripts that actually exist in root `package.json` and focused tests that actually exist in the tree.

## Maintenance

1. Read `docs/agents/local-codex-review.md` and `docs/agents/vibe-coding-harness.md`.
2. Inspect any proposed harness script for write/network side effects and fail-closed behavior.
3. Add contract tests for deterministic parsing, base/SHA binding, secret redaction, and exit decisions when such a script is introduced.
4. Validate skill changes with:

   ```bash
   python3 scripts/check-skill-harness.py
   python3 -m unittest scripts.tests.test_skill_harness
   ```

Do not invent legacy lane rules, a permanent `dev` promotion branch, or unavailable CI jobs in this `main`-based repository.
