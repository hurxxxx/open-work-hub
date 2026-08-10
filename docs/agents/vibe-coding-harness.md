# 바이브 코딩 하네스

이 문서는 구현 위험에 맞는 검증 깊이와 MR 전달 경계를 소유한다. 코드 구조는
[LLM 친화 개발 기준](llm-friendly-development.md), 앱 등록은
[앱 플랫폼 계약](../domains/app-platform/README.md), 정확한 CI 동작은 CI script와 test가
정본이다.

단순 설명, 문서 읽기, copy/translation-only 수정에는 이 문서를 전부 적용하지 않는다.
현재 코드·테스트에서 시작해 실제 변경 표면에 해당하는 섹션과 owner reference만 사용한다.

## Context Selection

1. 사용자 요청과 현재 diff/코드/테스트를 확인한다.
2. 아래 risk router에서 실제 변경 표면을 고른다.
3. 그 표면의 owner 문서·ADR와 focused check만 연다.

`docs/current/` 전체, 관련 없는 앱, 과거 계획, raw QA/benchmark,
`learning/**/*.md`는 기본 컨텍스트가 아니다.

## Delivery Boundary

기존 app scaffold 안의 view, copy, 계산, parsing, app-local state, focused test 수정은 일반
app-local 변경이다. 이 변경만으로 Core Enablement, app-delivery skill, exact lane, Draft
상태를 요구하지 않는다.

다음 protected surface가 새로 필요하거나 바뀔 때만 Core Enablement로 분리한다.

- app/feature identity, manifest registration, entitlement/bootstrap;
- shell route/nav composition, protected API composition, generated OpenAPI/client;
- shared RBAC/data scope, shared table, worker bootstrap/runtime;
- file/network platform pipeline, AI capability/workload extension point;
- CI, agent policy, checker, guardrail exclusion, CODEOWNERS.

필요한 extension point가 없으면 기능 MR을 확대하거나 lane을 높이지 말고
`open-alm-vibe-app-delivery`의 core-enablement brief를 작성한다. Core Enablement MR은
`.gitlab/merge_request_templates/Core_Enablement.md`를 사용하고 독립 배포·기본 비활성·
활성화 소유권을 명시한다.

Lane은 app delivery, protected platform, migration/generated/shared runtime, 혼합 integration
경계에서만 필수다. 문서, 번역, env contract, harness/CI, manifest/public boundary를 건드리지
않는 단일 app-local 변경에서는 advisory다. Draft/Ready는 workflow metadata이며 검증 gate가
아니다.

## Contract Map

복합 기능이나 protected boundary 변경은 구현 전에 해당 행만 MR evidence에 기록한다.
확인할 수 없는 제품·권한 결정은 추정하지 않는다.

| 표면 | 확인할 계약 |
| --- | --- |
| Identity/route | app/feature id, owner, route, entitlement, scaffold 존재 여부 |
| Data/auth | workspace/company/global scope, authoritative store, transaction/concurrency, retention, read/write 역할 |
| API/UI | request/response/error, workspace prefix, OpenAPI/client, i18n, accessibility, time/stale response |
| File/network | parser/type 검증, size/decompression limits, redirect/TLS/active content, cleanup |
| AI | workload id, server-selected app id, route/budget, audit/approval, external-data policy |
| Worker/runtime | import/registration, queue/beat, retry/idempotency, dependency, Linux path |
| Migration | target head, model metadata, existing-row compatibility, upgrade/rollback |
| Search/retrieval | owner, source ACL, partition, projection/outbox, lifecycle hook, backfill/cutover/rollback |

## Risk Router

| 실제 변경 표면 | Owner reference | 핵심 불변식 |
| --- | --- | --- |
| App identity/manifest/API prefix | `docs/domains/app-platform/README.md` | 기존 composition/registration을 사용하고 local allowlist·deep import를 만들지 않는다 |
| UI component/time/feedback | `docs/agents/ui-components.md`, `docs/product/ui-design-principles.md` | 공용 UI, i18n, accessibility, user time contract 재사용 |
| API/data/auth | 현재 domain code/tests | 서버 RBAC, workspace isolation, authoritative persistence, compatibility |
| AI capability/LLM | ADR 0002, ADR 0005, `open-alm-mcp-capability-governance` | registered workload/common interface, server route, budget/audit/approval, no direct provider call |
| Search/RAG/projection | `docs/domains/retrieval/README.md`, ADR 0009 | partition은 ACL이 아니며 source ACL·stable identity·version fence·generation cutover 적용 |
| File/network | 현재 parser/service와 security tests | observed type, counted limits, redirect마다 SSRF 검증, TLS, safe content disposition |
| Worker | worker bootstrap와 app task tests | 배포 import/registration, queue/beat, retry/idempotency |
| Migration/model | Alembic/model registry/tests | current head, single head, metadata, real upgrade, existing-row 보존 |

공유·감사 가능 데이터는 DB/object-store 계약을 사용한다. UI button 숨김, `/tmp`,
process-local lock, JSON load-modify-write, browser local storage는 권한이나 공유 데이터의 정본이
아니다. 기능을 통과시키기 위한 policy/checker self-bypass는 항상 별도 harness 변경이다.

## Proportional Validation

아래 표는 “파일이 존재하면 전부 실행” 목록이 아니다. 실제로 바뀐 행의 최소 evidence를 선택하고,
shared·cross-domain·migration·external·불확실한 blast radius에서만 확대한다.

| 변경 | 최소 evidence | 확대 조건 |
| --- | --- | --- |
| 문서/skill/policy | syntax/link/skill contract | executable policy 또는 harness 동작 변경 |
| Translation | locale parity, key compatibility, syntax/type | shared identifier·consumer contract 변경 |
| Env contract | env checker, runtime separation | startup/deploy wiring 또는 secret storage 변경 |
| Web app-local | typecheck, architecture, focused unit/component | shell/cross-app route 또는 critical browser flow |
| API/domain | source integrity, API architecture, focused pytest | shared core/fixture/registry 또는 service-wide impact |
| OpenAPI/generated | API contract regeneration | cross-repo consumer compatibility |
| Worker | focused task/bootstrap/routing tests | shared scheduler/runtime 변경 |
| Migration/model | graph, metadata, native DB upgrade/drift | destructive/data migration 또는 supported upgrade path |
| File/network | malformed/oversized/redirect/failure cleanup | external service or active-content boundary |
| AI capability | registry/direct-call guard, focused invoke tests | new Adapter/route/approval/external-data behavior |

`pnpm ci:harness`는 repository 정적 계약이며 app merge-ready 증거가 아니다. 관련 없는
API, DB, browser, external, full suite를 작은 변경에 추가하지 않는다. Feature MR CI는
Codex review만 수행하고, 비-Codex 전체 검증은 `dev → main` release MR에서 수행한다.

## One-Pass MR Loop

- 같은 사용자 결과의 구현·리뷰·검증 수정은 기존 MR에서 끝내고, 독립 결과만 분리한다.
- 실패 시 현재 SHA의 review 또는 release-validation 로그·finding을 모아 한 번에 수정한다.
  두 번째 실패부터는 추가 push/MR 대신 재현 가능한 preflight 또는 staging 검증을 먼저 만든다.
- CI·runner 변경은 canonical contract와 rollback 경계를 유지한다.
- source·diff-base·MR evidence는 policy 단계에서 먼저 확인하고, 실제 merge
  conflict는 merge/review gate에서 차단한다. Pipeline 생성 후 target이 전진했다는
  사실만으로 이미 실행 중인 source validation을 실패시키지 않는다.
- Feature MR의 Codex runner는 자체 job·freshness·merge·evidence gate만 확인한다.
- `dev → main` release MR은 Codex 없이 repository, Python, API, DB, Web 검증을 한 job에서 수행한다.

## MR Delivery

기능 MR은 clean/committed branch에서 다음 명령으로 등록한다.

```bash
pnpm mr:publish -- --title "<title>" --description-file /tmp/open-alm-mr.md
```

Publisher는 current target, clean state, merge result, diff와 lane metadata를 확인하고 동일 SHA의
MR을 만들거나 갱신한다. Feature MR 서버 pipeline은 Codex review만 수행하며 전체 기술 검증은
`dev → main` 승격 pipeline이 소유한다. 직접 `glab mr create`, GitLab UI/API, 수동 lane,
push pipeline, 생성 즉시 auto-merge로 이 흐름을 대체하지 않는다.

MR evidence와 review는 latest source SHA와 target merge result에 결합한다. Source가 바뀌면
affected evidence를 갱신하고, target이 바뀌어 merged surface가 달라지면 관련 검증을 다시 본다.
MR review/merge 판단을 실제로 요청한 경우에만 `open-alm-mr-review-validation`을 사용한다.

## Stop Conditions

- 과거 계획이나 `learning/**/*.md`를 현재 요구사항으로 사용한다.
- 앱/API/AI/retrieval/security boundary를 local bypass로 우회한다.
- 필요한 protected scaffold 없이 feature diff를 platform까지 확대한다.
- 기능 변경이 CI, agent policy, checker, exclusion, CODEOWNERS를 약화해 스스로 통과한다.
- 시크릿, 운영 데이터, 대량 삭제, destructive migration을 필요한 승인 없이 다룬다.
