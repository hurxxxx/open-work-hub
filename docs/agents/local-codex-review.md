# Local Codex MR Review

Feature MR(`* -> dev`) pipeline은 `codex_review` gate를 소유한다. 비-Codex 전체 검증은 release
MR(`dev -> main`)의 `release_validation`에서 수행한다. 정확한 실행 계약은 다음 단계에서 추가될
CI script와 contract test가 소유하며, 이 문서는 review boundary와 artifact 형식을 정의한다.

## Trust Boundary

- GitLab job은 MR checkout의 임의 script가 아니라 local runner에 설치된 canonical review entrypoint를
  호출한다.
- Source checkout은 read-only review 대상이다. Target SHA의 승인된 CI, policy, evidence를 사용하고
  source의 agent/skill/prompt 변경은 review 대상으로만 본다.
- Codex에는 GitLab/CI token, credentialed remote, 임의 MR note 본문, `.env` 내용 또는 운영 데이터를
  전달하지 않는다.
- `codex_review`는 include, alias, `extends`, `needs`, inherited variable, 실행 hook이 없는
  non-inheriting job이어야 한다.

## Runner Gate

같은 feature MR의 별도 validation job은 요구하지 않는다. Runner는 다음 핵심 조건만 fail-closed로
확인한다.

- 현재 source/diff-base와 review-start target snapshot
- 현재 Codex job의 SHA, runner, tag, stage와 `allow_failure`
- protected external CI의 full-SHA pin과 canonical CI contract
- MR evidence, conflict, unresolved discussion과 merge simulation
- final comment 직전 source/target/contract 재확인

Draft/Ready는 gate가 아니다. Source나 review target snapshot이 바뀌면 결과는 stale이다.

## Decision And Artifacts

Final review에는 아래 heading과 정확히 하나의 undecorated token을 둔다.

```text
## 병합 가능 여부
MERGE_READY
MERGE_BLOCKED
```

Runner gate가 실패하거나 integration blocker가 있으면 `MERGE_BLOCKED`로 job을 실패시킨다.
Progress/final/disposition comment는 append-only이며 prompt와 run log는 maintainer-only artifact로
남긴다. Codex는 edit, push, merge를 수행하지 않는다.

## Installation Boundary

Repository file과 runner 설치본은 자동 동기화되지 않는다. CI runner script가 추가된 뒤에는 clean
`dev` checkout의 `HEAD == origin/dev`에서만 설치본을 갱신한다. 설치 명령, system path, protected
external CI pin은 다음 GitLab pipeline 구현 단계의 contract test가 소유한다.

## Validation Boundary

Release MR의 external lane은 제품 adapter의 real-service canary를 실행한다. 애플리케이션 DB와 ACL을
포함한 더 넓은 external E2E는 별도 scheduled regression이 소유한다. 이 문서는 아직 존재하지 않는
CI job을 통과 증거로 주장하지 않는다.
