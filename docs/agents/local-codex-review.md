# Local Codex MR Review

Feature MR(`* → dev`) 파이프라인은 `codex_review` 하나만 실행한다. 비-Codex 전체
검증은 release MR(`dev → main`)의 `release_validation`에서 수행한다. 정확한 실행
계약은 `scripts/codex-review-ci.sh`와 CI contract test가 소유한다.

## Trust Boundary

- GitLab job은 MR checkout의 script가 아니라
  `/home/dwdcc/.local/bin/ai-do-codex-review-ci`를 호출한다.
- Source checkout은 read-only review 대상이다. Target SHA의 승인된 CI·policy·evidence를
  사용하고 source의 agent/skill/prompt 변경은 review 대상으로만 본다.
- Codex에는 GitLab/CI token, credentialed remote, 임의 MR note 본문을 전달하지 않는다.
- `codex_review`는 include, alias, `extends`, `needs`, inherited variable, 실행 hook이 없는
  canonical non-inheriting job이다.

## Runner Gate

같은 feature MR의 별도 validation job은 요구하지 않는다. Runner는 다음 핵심 조건만
fail-closed로 확인한다.

- 현재 source/diff-base와 review-start target snapshot
- 현재 Codex job의 SHA, runner, tag, stage, `allow_failure`
- protected external CI의 full-SHA pin과 canonical CI contract
- MR evidence, conflict, unresolved discussion, merge simulation
- Final comment 직전 source/target/contract 재확인

Draft/Ready는 gate가 아니다. Source나 review target snapshot이 바뀌면 결과는 stale이다.

## Decision And Artifacts

Final review에는 아래 heading과 정확히 하나의 undecorated token을 둔다.

```text
## 병합 가능 여부
MERGE_READY
MERGE_BLOCKED
```

Runner gate가 실패하거나 integration blocker가 있으면 `MERGE_BLOCKED`로 job을
실패시킨다. Progress/final/disposition comment는 append-only이며 prompt와 run log는
maintainer-only artifact로 남긴다. Codex는 edit, push, merge를 수행하지 않는다.

## Installation

Repository file과 설치본은 자동 동기화되지 않는다. 변경을 `dev`에 push한 뒤 clean
checkout의 `HEAD == origin/dev`에서 설치한다.

```bash
bash scripts/install-codex-review-runner.sh
```

Protected external CI는 `ops/ci/ci-first.gitlab-ci.yml`을 외부 저장소에 commit하고 원본
project의 `ci_config_path`를 그 full SHA로 pin한다.

## Validation PostgreSQL

`release_validation`은 운영·개발 DB와 분리된 `18/ai_do_ci` 클러스터만 사용한다.
`scripts/configure-ci-validation-env.sh`가 listener, role, credential과 test workload
설정을 소유한다. 이 클러스터에는 영속 데이터를 두지 않으며 per-test
`TRUNCATE + pg_restore`의 checkpoint 비용을 피하기 위해 durable write 설정을 끈다.
`checkpoint_timeout=1min`과 `checkpoint_completion_target=0`은 테스트가 만든
relation sync 요청을 짧고 즉시 실행되는 checkpoint로 비워, 격리 DB 삭제가 누적
요청을 정리하느라 수분간 멈추는 것을 막는다.
호스트 또는 OS crash 뒤 cluster 정합성이 의심되면 결과를 신뢰하거나 복구하지 말고
validation runner를 멈춘 상태에서 cluster를 재프로비저닝한다.

Release MR의 external lane은 Redis, MinIO, OpenSearch 제품 adapter의 DB-free
real-service canary를 실행한다. 애플리케이션 DB와 ACL을 포함한 전체 external E2E는
scheduled regression이 소유한다.
