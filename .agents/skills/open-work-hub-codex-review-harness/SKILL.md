---
name: open-work-hub-codex-review-harness
description: Maintain Open Work Hub's GitLab Codex MR review policy, runner script contract, MR comment contract, and enforced review decision gate. Use when changing codex_review CI, review runner scripts, runner installation, or automated MR review behavior. Do not use to review a particular MR; use `open-work-hub-mr-review-validation` for that outcome.
---

# Codex Review Harness

## Contract

- Feature MR `* -> dev`: Codex `codex_review`.
- Release MR `dev -> main`: non-Codex validation.
- CI job calls installed runner entrypoint, not MR-source script.
- Codex receives no tokens, credentialed remotes, `.env`, MR note bodies, raw prompts, customer/ops data.
- Runner fails closed for job identity, source/target/evidence freshness, unresolved discussions, merge simulation, final comment.
- Final output has `## 병합 가능 여부` plus exactly one token: `MERGE_READY` or `MERGE_BLOCKED`.
- Codex may review/comment only; no edit/commit/push/approve/merge/label mutation.

## Maintenance

Read `docs/agents/local-codex-review.md` and `docs/agents/vibe-coding-harness.md`. When scripts/CI are introduced, add contract tests for parsing, SHA binding, redaction, GitLab API errors, freshness, merge simulation, and exit decisions.

```bash
python3 scripts/check-skill-harness.py
python3 -m unittest scripts.tests.test_skill_harness
```
