---
name: open-work-hub-codex-review-harness
description: Maintain Open Work Hub's GitLab Codex MR review policy, runner script contract, MR comment contract, and enforced review decision gate. Use when changing codex_review CI, review runner scripts, runner installation, or automated MR review behavior. Do not use to review a particular MR; use `open-work-hub-mr-review-validation` for that outcome.
---

# Open Work Hub Codex Review Harness

## Contract

- Feature MR (`* -> dev`) CI owns the canonical Codex review gate.
- Release MR (`dev -> main`) CI owns non-Codex repository validation; Codex does not run there.
- The GitLab job calls an installed local runner entrypoint, not an arbitrary script from the MR source checkout.
- Never pass tokens, credentialed remotes, `.env` contents, arbitrary MR note bodies, raw prompts, customer data, or operations data to Codex.
- The runner fails closed for job identity, source/target freshness, evidence freshness, unresolved discussions, merge simulation, and final comment publication.
- Final review output contains `## 병합 가능 여부` and exactly one decision token: `MERGE_READY` or `MERGE_BLOCKED`.
- Codex may review and comment only. It must not edit, commit, push, approve, merge, or mutate labels.
- Keep the check router aligned with scripts that actually exist in root `package.json` and focused tests that actually exist in the tree.

## Maintenance

1. Read `docs/agents/local-codex-review.md` and `docs/agents/vibe-coding-harness.md`.
2. Inspect proposed runner or CI changes for source-checkout script execution, credential leakage, inherited GitLab CI state, and fail-open behavior.
3. Add contract tests for deterministic parsing, base/SHA binding, secret redaction, GitLab API error handling, discussion freshness, merge simulation, and exit decisions when such scripts are introduced.
4. Validate guidance changes with:

   ```bash
   python3 scripts/check-skill-harness.py
   python3 -m unittest scripts.tests.test_skill_harness
   ```

Execution contracts will be owned by `scripts/codex-review-ci.sh`, GitLab CI, and any protected external runner configuration when those files are introduced. Until they exist, do not claim the automated gate exists.
