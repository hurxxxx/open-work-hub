# 구현 검증 하네스

이 문서는 구현 위험에 맞는 검증 깊이와 GitHub PR 전달 경계를 소유한다. 코드 구조는
[LLM 친화 개발 기준](llm-friendly-development.md), 앱 등록은
[앱 플랫폼 계약](../domains/app-platform/README.md), 정확한 실행 동작은 현재 `package.json`,
Nx project 설정, script와 test가 정본이다.

단순 설명, 문서 읽기와 copy/translation-only 수정에는 이 문서를 전부 적용하지 않는다. 현재
코드·테스트에서 시작해 실제 변경 표면에 해당하는 섹션과 owner reference만 사용한다.

## Context Selection

1. 사용자 요청과 현재 working tree/diff, 코드와 테스트를 확인한다.
2. 아래 risk router에서 실제 변경 표면을 고른다.
3. 그 표면의 owner 문서·ADR와 focused check만 연다.

관련 없는 앱, 과거 계획, raw QA/benchmark와 원시 로그는 기본 컨텍스트가 아니다. 문서에 적힌
명령이나 파일 경로도 실행 전에 현재 저장소에 실제로 존재하는지 확인한다.

## Delivery Boundary

기존 app scaffold 안의 view, copy, 계산, parsing, app-local state와 focused test 수정은 일반
app-local 변경이다. 다음 protected surface가 새로 필요하거나 바뀔 때는 app-local diff와 공통
플랫폼 변경을 구분하고 영향 범위를 명시한다.

- app/feature identity, manifest registration, entitlement와 bootstrap
- shell route/nav composition, protected API composition, OpenAPI/generated client
- shared RBAC/data scope, shared table, worker bootstrap/runtime
- file/network platform pipeline, AI capability/workload extension point
- migration, CI/automation, agent policy, checker와 architecture guardrail

필요한 extension point가 없으면 앱 내부 특례나 checker 예외로 우회하지 않는다. 먼저 독립적으로
검증 가능한 공통 경계를 추가하고 기본 비활성 또는 호환 가능한 상태로 배포할 수 있는지 확인한다.

현재 Git remote는 GitHub이고 기본 브랜치는 `main`이다. 다른 저장소의 별도 release lane,
Draft gate, 변경 발행 도구와 외부 review runner 계약을 이 저장소에 가져오지 않는다.

## Contract Map

복합 기능이나 protected boundary 변경은 구현 전에 실제 관련 행만 작업 메모 또는 PR evidence에
기록한다. 확인할 수 없는 제품·권한 결정을 추정하지 않는다.

| 표면 | 확인할 계약 |
| --- | --- |
| Identity/route | app/feature ID, owner, route context, availability, entitlement, scaffold 존재 여부 |
| Data/auth | company/personal/workspace scope, authoritative store, transaction/concurrency, retention, read/write 역할 |
| API/UI | request/response/error, workspace prefix, OpenAPI/client, i18n, accessibility, time와 stale response |
| File/network | parser/type 검증, size/decompression limits, redirect/TLS/active content, cleanup |
| AI | workload ID, server-selected app ID, route/budget, audit/approval, external-data policy |
| Worker/runtime | import/registration, queue/beat, retry/idempotency, dependency와 배포 경로 |
| Migration | target head, model metadata, existing-row compatibility, upgrade와 rollback |
| Search/retrieval | owner, source ACL, partition, projection/outbox, lifecycle hook, backfill/cutover/rollback |

## Risk Router

| 실제 변경 표면 | Owner reference | 핵심 불변식 |
| --- | --- | --- |
| App identity/manifest/API prefix | [앱 플랫폼](../domains/app-platform/README.md), [ADR 0007](../../adr/0007-company-tenant-workspace-scope.md) | 기존 composition/registration을 사용하고 local allowlist·deep import를 만들지 않는다. Route slug나 UI 노출을 권한 증거로 쓰지 않는다. |
| UI component/time/feedback | [UI 컴포넌트](ui-components.md), [UI 원칙](../product/ui-design-principles.md) | 공용 UI, i18n, accessibility, semantic token과 user time contract를 재사용한다. |
| API/data/auth | 현재 domain code/tests, [ADR 0001](../../adr/0001-ai-platform-extensibility.md) | 서버 RBAC, workspace isolation, authoritative persistence와 compatibility를 유지한다. |
| AI capability/LLM | [AI Gateway](../domains/ai/gateway.md), [AI Write Policy](../domains/ai/write-policy.md), [ADR 0002](../../adr/0002-mcp-capability-platform.md), [ADR 0005](../../adr/0005-registered-llm-workload.md) | Registered workload/common interface, server route, budget/audit/approval, no direct provider call. |
| Search/RAG/projection | [Retrieval](../domains/retrieval/README.md), [RAG](../domains/rag/README.md), [ADR 0004](../../adr/0004-retrieval-rag-boundary-policy.md), [ADR 0009](../../adr/0009-retrieval-partition-projection-generations.md) | Partition은 ACL이 아니며 source ACL, stable identity, version fence와 generation cutover를 적용한다. |
| File/network | 현재 parser/service와 security tests | Observed type와 counted limits, redirect마다 SSRF 검증, TLS, safe content disposition와 실패 cleanup. |
| Worker | `apps/worker/src/open_work_hub_worker/`, worker tests | 배포 import/registration, queue/beat, retry와 idempotency. |
| Migration/model | `apps/api/alembic/`, model registry와 migration tests | Current/single head, metadata registration, 실제 upgrade와 existing-row 보존. |

공유·감사 가능 데이터는 DB/object-store 계약을 사용한다. UI button 숨김, `/tmp`, process-local
lock, JSON load-modify-write와 browser local storage는 권한이나 공유 데이터의 정본이 아니다.
기능을 통과시키기 위한 policy/checker self-bypass는 기능 변경에 섞지 않는다.

## Proportional Validation

아래 표는 모든 명령을 매번 실행하라는 목록이 아니다. 실제 바뀐 행의 최소 evidence를 선택하고
shared, cross-domain, migration, external 또는 blast radius가 불확실할 때만 확대한다.

| 변경 | 최소 evidence | 확대 조건 |
| --- | --- | --- |
| 문서/skill/policy | `git diff --check`, 내부 link/path 확인, `pnpm check:skills`(skill 변경 시) | Executable policy, checker 또는 harness 동작 변경 |
| Translation | `pnpm check:i18n`, key compatibility | Shared identifier·consumer contract 변경 |
| Env contract | `pnpm check:env-contract`, `pnpm check:path-hardcoding` | Startup/deploy wiring 또는 secret storage 변경 |
| Web app-local | `pnpm check:web-architecture`, `pnpm nx typecheck web`, 관련 Vitest | Shell/cross-app route 또는 critical browser flow |
| API/domain | `pnpm check:api-architecture`, 관련 Pytest | Shared core/fixture/registry 또는 service-wide impact |
| OpenAPI/generated | `pnpm check:api-contract`; 의도된 변경은 `pnpm generate:api-client` 후 재검사 | Cross-package consumer compatibility |
| Worker | 관련 worker Pytest와 task registration | Shared scheduler/queue/runtime 변경 |
| Migration/model | `pnpm check:alembic-graph`, migration-marked test | Destructive/data migration 또는 supported upgrade path |
| File/network | malformed/oversized/redirect/failure-cleanup focused test | External service 또는 active-content boundary |
| AI capability | registry/direct-call guard와 focused invoke test | 새 Adapter/route/approval/external-data behavior |

Focused test의 현재 실행 예시는 다음과 같다. `<path>`는 실제 존재하는 test 경로로 바꾼다.

```bash
pnpm --dir apps/web exec vitest run <path>
cd apps/api && uv run --python 3.12 --group dev python -m pytest <path> -q
cd apps/worker && uv run --python 3.12 --group dev python -m pytest <path> -q
```

공통 app/API contract 경계를 넓게 바꿨다면 `pnpm ci:app-api-contracts` 또는
`pnpm ci:app-web-contracts`, 저장소 전체 위험이면 `pnpm ci:all`까지 확대할 수 있다. External,
slow, migration, browser와 full suite는 관련 없는 작은 변경에 관성적으로 추가하지 않는다.

## One-Pass Review Loop

- 같은 사용자 결과의 구현·리뷰·검증 수정은 현재 working tree/branch에서 일관되게 끝내고,
  독립 결과만 분리한다.
- 실패 시 현재 SHA와 환경의 로그·finding을 모아 원인을 함께 수정한다. 반복 실패는 추가 push보다
  로컬에서 재현 가능한 focused preflight를 먼저 만든다.
- CI·checker 변경은 canonical contract와 rollback 경계를 유지한다.
- Diff base, generated artifact와 evidence는 리뷰 시작에 확인하고 source가 바뀌면 affected
  evidence를 갱신한다.
- 테스트 실패를 숨기기 위해 exclusion, marker, architecture allowlist와 guardrail을 약화하지 않는다.

## GitHub PR Handoff

PR 생성·수정·push는 사용자가 명시적으로 요청한 경우에만 수행한다. 그 경우에도 clean/committed
branch, `main` base, 실제 diff와 검증 evidence를 확인하고 GitHub CLI를 사용한다.

```bash
gh pr create --base main --head <branch> --title "<title>" --body-file <file>
```

PR 본문에는 변경 이유, 사용자 영향, contract/migration 여부, 실행한 검증과 실행하지 못한 검증을
구분한다. Review와 merge 판단은 latest head SHA와 current base를 기준으로 하고 source나
generated contract가 바뀌면 관련 evidence를 다시 만든다.

## Stop Conditions

- 과거 계획이나 다른 저장소의 지침을 현재 요구사항으로 사용한다.
- 앱/API/AI/retrieval/security boundary를 local bypass로 우회한다.
- 필요한 protected scaffold 없이 feature diff를 플랫폼 전체로 확대한다.
- 기능 변경이 CI, agent policy, checker, exclusion 또는 architecture guard를 약화해 스스로 통과한다.
- 시크릿, 운영 데이터, 대량 삭제 또는 destructive migration을 필요한 승인 없이 다룬다.
