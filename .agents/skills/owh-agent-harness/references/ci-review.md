# Codex Review Harness

## Contract

- Branch and MR authorization lives in root `AGENTS.md`; CI files own job routing and target policy.
- CI job calls installed runner entrypoint, not MR-source script. Its trusted policy is the runner prompt plus target-SHA root/scoped `AGENTS.md` selected by changed path.
- Codex receives no tokens, credentialed remotes, `.env`, MR note bodies, raw prompts, customer/ops data.
- Runner fails closed for job identity, source/target/evidence freshness, unresolved discussions, merge simulation, final comment.
- Final output has `## 병합 가능 여부` plus exactly one token: `MERGE_READY` or `MERGE_BLOCKED`.
- Codex may review/comment only; no edit/commit/push/approve/merge/label mutation.

## Maintenance

Read `docs/agents/local-codex-review.md` and `docs/agents/vibe-coding-harness.md`.

CI contract owners:

- `.gitlab-ci.yml`
- `ops/ci/ci-first.gitlab-ci.yml`
- `scripts/check-gitlab-pipeline.mjs`
- `scripts/check-mr-target-policy.mjs`
- `scripts/check-mr-contract-evidence.mjs`
- `scripts/codex-review-ci.sh`
- `scripts/install-codex-review-runner-entrypoint.sh`

```bash
pnpm check:gitlab-pipeline
pnpm ci:harness
python3 scripts/check-skill-harness.py
python3 -m unittest scripts.tests.test_skill_harness
```
