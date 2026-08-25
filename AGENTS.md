# Open Work Hub Agent Rules

## Scope And Safety

- 이 파일은 저장소의 공통 에이전트 지침 정본이다. `CLAUDE.md`와
  `.github/copilot-instructions.md`는 도구별 진입점일 뿐 규칙을 복제하지 않는다.
- 사용자 요청을 만족하는 최소 변경만 수행하고 기존 사용자 변경을 보존한다. 결과, 권한 또는
  외부 상태를 크게 바꾸는 모호함만 확인하고 나머지는 안전한 가정을 밝힌 뒤 진행한다.
- 저장소 밖은 사용자가 명시적으로 범위에 넣지 않는 한 읽기 전용이다. 파괴적 작업 전에는 정확한
  대상과 symlink 경계를 확인하고, dirty checkout에서 파일을 되돌리거나 branch를 바꾸지 않는다.
- 시크릿, 토큰, 비밀번호, 운영·고객 데이터를 코드, 문서, 로그, prompt, fixture, diff에 노출하지
  않는다. 설정은 typed settings와 `OPEN_WORK_HUB_*` 환경변수를 사용하며 `.env`는 커밋하지 않는다.
- 특정 질문, 키워드, 데이터 필드 또는 예시만 맞추는 AI/RAG 분기를 만들지 않는다. 범용 schema,
  registry와 operator로 모델링한다.

## Context And Owner Routing

- 기본 컨텍스트는 사용자 요청과 현재 코드·테스트다. `docs/README.md`에서 시작해 현재 변경 표면의
  owner 문서와 ADR만 읽는다. 관련 없는 앱, 과거 계획, raw log나 문서 트리를 관성적으로 읽지 않는다.
- 프로젝트 skill은 설명의 트리거가 현재 작업과 정확히 일치하거나 사용자가 지목했을 때만 사용한다.
  `.agents/skills/open-work-hub-*`가 프로젝트 고유 workflow의 정본이다. 한 skill이 다른 자료를
  언급한다는 이유만으로 전부 연쇄 로딩하지 않는다. 결정론적 계약은 script와 test가 소유한다.

| 변경 표면 | 필요할 때 읽을 정본 |
| --- | --- |
| 코드 구조·얇은 추상화 | `docs/agents/llm-friendly-development.md`, `docs/agents/composable-abstractions.md` |
| 검증 깊이·PR 전달 | `docs/agents/vibe-coding-harness.md`, `docs/agents/local-codex-review.md` |
| 문서 구조·소유권 | `docs/agents/domain.md` |
| GitHub Issue 인입·triage | `docs/agents/issue-tracker.md`, `docs/agents/triage-labels.md` |
| 앱 identity·registration | `docs/domains/app-platform/README.md` |
| UI 컴포넌트·시간·알림 | `docs/agents/ui-components.md`, `docs/product/ui-design-principles.md` |
| AI capability·MCP·LLM workload | `adr/0002-mcp-capability-platform.md`, `adr/0005-registered-llm-workload.md`, `docs/domains/ai/write-policy.md` |
| 검색·RAG·projection | `docs/domains/retrieval/README.md`, `docs/domains/rag/README.md`, `adr/0009-retrieval-partition-projection-generations.md` |
| 로컬 환경·배포 | `README.md`, `docs/domains/release/README.md`와 해당 운영 skill |

전체 문서 색인과 소유권은 `docs/README.md`, `docs/agents/domain.md`를 따른다.

## Work And Git

- 기본 개발 환경은 이 GitHub 저장소의 현재 checkout과 로컬 Docker Compose다. 고정 서버 경로,
  사내 원격 인프라 또는 다른 저장소가 있다고 가정하지 않는다.
- 현재 기본 branch는 `main`이다. 사용자가 별도 workflow를 지정하지 않으면 저장소에 없는 branch
  승격 규칙, PR publisher, label lane 또는 CI gate를 만들거나 요구하지 않는다.
- 별도 요청 없이는 commit, push, PR 생성 또는 merge를 하지 않는다. 요청받은 PR은 일반적으로
  `main`을 대상으로 전체 base diff를 검토하고, 하나의 완결된 사용자 결과만 담는다.
- branch/worktree 변경이 실제로 필요할 때만 `open-work-hub-worktree-management` skill을 사용한다.
  실패한 검사나 리뷰는 현재 diff의 로그와 finding을 먼저 모아 원인별로 수정한다.
- 기능을 통과시키기 위해 같은 변경에서 checker, 테스트, CI, 에이전트 지침 또는 guardrail을
  약화하거나 exclusion을 추가하지 않는다.

## Platform Boundaries

- 기존 composition root, registry, manifest, public API와 generated contract를 사용한다. 임의 상수,
  deep import, local rewrite, ad hoc registry 또는 수동 generated artifact로 경계를 우회하지 않는다.
- 새 앱·포팅, app identity/manifest, protected API composition, 공유 data/RBAC, worker bootstrap,
  file/network pipeline 또는 AI extension point를 바꿀 때는 `open-work-hub-vibe-app-delivery` skill의
  contract map을 적용한다. 필요한 protected scaffold가 없으면 앱 변경에서 우회 구현하지 말고
  별도의 platform enablement 범위로 분리한다.
- Web 앱 화면, route, sidebar와 API client는 `apps/web/src/app-modules/<appId>/` 경계에 두고 외부에는
  manifest, public API 또는 bootstrap DTO로만 노출한다. 공유 UI·platform 계약은 각각
  `packages/ui`, `packages/core-web`, `apps/web/src/platform`의 기존 진입점을 먼저 찾는다.
- FastAPI router는 `open_work_hub_api.api_registry`에서 조립한다. API request/response가 바뀌면
  OpenAPI client를 재생성하고 검사한다. 새 DB schema와 호환성 변경은 Alembic migration으로 관리한다.
- persistence, i18n key, RBAC/workspace scope, worker registration과 generated client를 기능 계약의
  일부로 취급한다. 사용자 노출 문자열은 `ko-KR`과 `en-US`를 함께 유지한다.
- 공유·감사 가능 데이터는 승인된 PostgreSQL/object storage를 정본으로 사용한다. UI 권한 숨김,
  client local storage, `/tmp`, process-local state 또는 JSON load-modify-write를 공유 권한·데이터의
  정본으로 쓰지 않는다.
- 파일·URL·외부 네트워크 입력에는 크기, 형식, scheme/host, timeout, SSRF와 cleanup 경계를 두고,
  외부 서비스가 없는 실패 경로도 테스트한다.
- 인증과 workspace/app entitlement는 서버에서 fail-closed로 확인하고 negative test를 둔다.
  frontend 가시성이나 MCP discovery는 권한 부여가 아니며 실행 시 actor, workspace와 resource ACL을
  다시 확인한다. AI write capability는 명시적으로 활성화·승인되지 않으면 노출하거나 실행하지 않는다.
- 모든 생성형 LLM 호출은 등록된 `RegisteredLlmWorkload`와 공통 실행 interface를 사용한다. 앱 코드가
  provider/model/pool/credential을 고르거나 direct SDK/HTTP, 저수준 gateway, 암묵적 route fallback을
  추가하지 않는다.
- Retrieval partition은 후보 범위이지 권한 grant가 아니다. source-owned ACL, stable resource identity,
  versioned projection/outbox와 generation cutover 계약은 ADR 0009를 따른다.

## Validation And Review

- 검증은 변경 위험에 비례한다. 먼저 가장 가까운 focused test와 정적 검사를 실행하고, shared,
  migration, external integration 또는 불확실한 blast radius에서만 범위를 넓힌다.
- API test를 직접 고를 때는
  `(cd apps/api && uv run --python 3.12 --group dev python -m pytest tests/<file>.py -q)`를 사용한다.
  Worker test는 같은 방식으로 `apps/worker`에서 실행한다.

| 변경 유형 | 기본 검증 |
| --- | --- |
| 문서·에이전트 지침·skill | `git diff --check`, `pnpm check:skills` |
| Web 구조·UI·i18n | focused Vitest, `pnpm check:web-architecture`, `pnpm nx typecheck web` |
| API·OpenAPI 계약 | focused pytest, `pnpm check:api-architecture`, `pnpm check:api-contract` |
| DB migration | `pnpm check:alembic-graph`, `pnpm test:alembic-graph`, 필요 시 `pnpm nx run api:test-migrations` |
| Worker·queue 등록 | focused worker pytest, `pnpm nx lint worker` |
| Env·runtime 이름 | `pnpm check:env-contract`, `pnpm check:path-hardcoding` |
| AI capability·LLM workload | registry/invoke/ACL/direct-call guard의 focused API test와 관련 ADR 확인 |
| 브라우저 핵심 흐름 | `pnpm e2e:shell` 또는 실행 중인 로컬 stack에 맞는 login browser smoke |
| 넓은 release 전 검증 | 영향 범위가 정당화될 때 `pnpm ci:all` |

- API 계약을 바꾼 뒤 `pnpm check:api-contract`가 generated diff를 요구하면
  `pnpm generate:api-client`로 재생성하고 생성물과 호출부를 함께 검토한다.
- 보고에는 실제 실행한 명령과 결과, 실행하지 못한 검증, 남은 위험을 적는다. 문서에 적혔다는
  이유만으로 존재하지 않는 script, test, GitHub workflow를 성공 증거로 제시하지 않는다.
- review와 검증 증거는 확인한 source와 base 상태에 결합한다. 둘 중 하나가 바뀌면 affected diff와
  검증을 다시 판단한다.

## Parallel Work

- 읽기, 감사, 로그 분석처럼 독립적인 workstream은 사용자 또는 runtime 정책이 허용할 때 병렬
  sub-agent로 나눌 수 있다. 시크릿, 외부 권한, 파괴적 작업 또는 겹치는 파일 쓰기는 위임하지 않는다.
- Main agent가 최종 범위, 통합, 변경, 검증 판단과 사용자 보고를 소유한다.
