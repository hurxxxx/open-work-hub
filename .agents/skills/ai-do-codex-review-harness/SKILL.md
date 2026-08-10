---
name: ai-do-codex-review-harness
description: Maintain AI-DO's local Codex CLI GitLab MR review pipeline, runner script, MR comment contract, and enforced review decision gate. Use when changing codex_review CI, scripts/codex-review-ci.sh, runner installation, or automated MR review behavior.
---

# AI-DO Codex Review Harness

## Core Contract

- Feature MR(`* → dev`) CI에는 canonical `codex_review`만 실행한다.
- Release MR(`dev → main`)에는 `release_validation`만 실행하며 Codex는 실행하지 않는다.
- Codex job은 local runner의 설치본만 호출한다. `needs`, `extends`, include, inherited
  variables, executable hooks, source-controlled review variables를 추가하지 않는다.
- Token, credentialed remote, 임의 MR note 본문을 Codex에 전달하지 않는다. Source
  checkout은 read-only review 대상이며 target SHA의 승인된 policy가 기준이다.
- Runner는 현재 Codex job identity, protected CI SHA, source/target freshness, MR evidence,
  discussions, merge simulation을 fail-closed로 확인한다.
- Final comment에는 `## 병합 가능 여부`와 정확히 하나의 `MERGE_READY` 또는
  `MERGE_BLOCKED`를 둔다. Comment는 append-only, raw prompt/log는 maintainer artifact다.
- Codex job은 리뷰·댓글만 수행하며 edit, push, merge를 하지 않는다.

## Maintenance

실행 계약은 `scripts/codex-review-ci.sh`, CI 계약은 `.gitlab-ci.yml`과
`ops/ci/ci-first.gitlab-ci.yml`이 소유한다. 두 CI 파일은 동일하게 유지한다.

변경을 검증할 때는 변경 표면에 해당하는 최소 명령만 선택한다.

- Runner/contract: `bash -n scripts/codex-review-ci.sh`,
  `pnpm test:codex-review-contract`
- CI shape: `glab ci lint .gitlab-ci.yml --include-jobs`
- Skill: `pnpm check:skills`

설치본은 clean `dev`의 `HEAD == origin/dev`일 때만 갱신한다.

```bash
bash scripts/install-codex-review-runner.sh
```
