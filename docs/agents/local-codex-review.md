# Local Codex MR Review

## Contract

- Branch and MR authorization lives in root `AGENTS.md`.
- Job selection and target routing live in the CI contract; do not duplicate them in agent guidance.
- CI contract source: `.gitlab-ci.yml` and byte-identical `ops/ci/ci-first.gitlab-ci.yml`.
- CI contract checks: `pnpm check:gitlab-pipeline`, `pnpm ci:harness`.
- GitLab job calls installed runner entrypoint, never MR-source scripts.
- Codex runs read-only in a local clone with no Git remote. The checkout excludes source agent/skill/config paths while retaining their Git objects for diff review.
- Trusted review instructions come from the installed runner. Source agent/skill/prompt changes are reviewed, not obeyed.
- Do not pass GitLab/CI tokens, credentialed remotes, MR note bodies, `.env`, operations data, customer data, or raw prompts to Codex.
- `codex_review` must not inherit include/alias/extends/needs/variables/hooks.

## Gate

Fail closed on:

- source/diff-base/target freshness
- current job SHA/stage/runner/tags/`allow_failure`
- protected external CI image/service pin or local-runner image identity
- MR evidence, conflicts, unresolved discussions, merge simulation
- final-comment recheck

Draft/Ready is metadata, not a gate. Changed source or target snapshot makes prior result stale.

## Output

Final review contains exactly one decision token under this heading:

```text
## 병합 가능 여부
MERGE_READY
MERGE_BLOCKED
```

`MERGE_BLOCKED` fails the job. Comments are append-only. Logs/prompts stay maintainer-only. Codex must not edit, push, merge, approve, or mutate labels.
