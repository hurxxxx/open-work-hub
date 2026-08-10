# Project Agent Rules

## Scope And Safety

- 이 파일이 프로젝트 에이전트 지시의 정본이다. 일반 지시를 `AGENTS.md`, `CLAUDE.md`,
  `.codex/` 등에 복제하지 않는다. `CLAUDE.md`에는 Claude Code 실행 환경 노트만 둔다.
- 요청에 필요한 최소 변경만 수행하고 사용자 변경을 보존한다. 결과·권한·외부 상태를 크게
  바꾸는 모호함만 확인하고, 나머지는 안전한 가정을 밝힌 뒤 진행한다.
- 프로젝트 소유 경로(`/projects/ai-do/dev`, 명시된 worktree, 운영 점검 목적의
  `/projects/ai-do/prod`) 밖은 읽기 전용이다. 파괴적 작업 전에는 대상 `realpath`와 symlink
  경계를 확인한다.
- 시크릿, 운영 데이터, 토큰, 비밀번호를 코드·문서·로그·프롬프트·fixture·diff에 노출하지
  않는다. 런타임 설정은 typed settings, `AI_DO_*` 환경변수, GitLab 보호 저장소만 사용한다.
- 특정 질문·키워드·차종·필드·사례를 맞추는 AI/RAG 분기를 만들지 않는다. Planner schema와
  범용 operator로 모델링한다.

## Context And Skills

- 기본 컨텍스트는 사용자 요청과 현재 코드·테스트다. 필요한 경우에만 관련 owner 문서나 ADR
  하나로 내려간다. `docs/current/` 전체, 관련 없는 앱, 과거 계획, raw benchmark,
  `learning/**/*.md`를 관성적으로 읽지 않는다.
- 한 작업에는 요청을 완전히 다루는 최소 skill 집합만 사용한다. 사용자가 skill을 지목했거나
  description의 작업 유형이 정확히 일치하거나, 해당 skill이 보호하는 운영·보안 상태 변경을
  실제로 수행할 때만 연다.
- 파일명이나 도메인 단어가 언급됐다는 이유만으로 broad skill을 적용하지 않는다. 기존
  scaffold 안의 단순 UI/버그 수정은 app-delivery skill을, 일반 구현은 MR-review skill을,
  깨끗한 `dev`에서의 평범한 편집은 worktree skill을 자동으로 요구하지 않는다.
- 한 skill이 다른 문서나 skill을 언급해도 연쇄 로딩하지 않는다. 현재 변경 표면에 필요한
  branch/reference만 읽는다. 단순 설명·상태 확인에는 구현 workflow skill을 붙이지 않는다.
- Skill은 workflow와 프로젝트 고유 판단만 담고, 결정론적 규칙은 script/test가 소유한다.

### Owner Routing

| 변경 표면 | 필요할 때 읽을 정본 |
| --- | --- |
| 코드 구조·추상화 | `docs/agents/llm-friendly-development.md` |
| 검증 깊이·MR 전달 | `docs/agents/vibe-coding-harness.md` |
| 앱 identity·registration | `docs/domains/app-platform/README.md` |
| UI 컴포넌트·시간·알림 | `docs/agents/ui-components.md`, `docs/product/ui-design-principles.md` |
| AI capability·LLM workload | `adr/0002-mcp-capability-platform.md`, `adr/0005-registered-llm-workload.md` |
| 검색·RAG·projection | `docs/domains/retrieval/README.md`, `adr/0009-retrieval-partition-projection-generations.md` |
| 운영·배포 | `docs/domains/release/production-deployment-layout.md`와 해당 운영 skill |

문서 소유권과 전체 색인은 `docs/README.md`, `docs/agents/domain.md`에서 찾는다.

## Work And Git

- `/projects/ai-do/dev`는 live `dev` checkout이다. 여기서 checkout/switch/rebase하지 않는다.
  기존 MR branch 수정이나 사용자가 명시한 병렬 작업만 별도 worktree에서 수행한다.
- dirty checkout에서 branch를 바꾸거나 사용자 변경을 되돌리지 않는다.
- 별도 요청 없이는 commit/push하지 않는다. 기능 MR은 `feature` → `dev`, 운영 승격은
  `dev` → protected `main`만 사용한다.
- MR 하나는 하나의 완결된 사용자 결과를 전달한다. 같은 결과를 완성하는 구현·리뷰·검증 수정은
  새 MR로 만들지 말고 기존 MR에 계속 반영한다. 무관한 기능, 독립 배포 단위, 다른 소유 경계만
  별도 branch/MR로 분리한다.
- 파이프라인이나 리뷰가 실패하면 현재 SHA의 review/release-validation 로그·finding을 먼저 수집해
  원인군별로 한 번에 수정한다. 두 번째 실패 후에는 새 MR이나 즉시 patch를 만들지 말고,
  재현 가능한 preflight 또는 staging 검증을 만든 뒤 계속한다.
- 기능 MR 등록 명령은
  `pnpm mr:publish -- --title "<title>" --description-file /tmp/ai-do-mr.md`다.
  Publisher가 target·mergeability·diff·lane metadata를 확인한다. Feature MR pipeline은
  Codex review만, `dev → main` pipeline은 비-Codex 전체 검증만 수행한다. 수동 lane,
  직접 `glab mr create`, GitLab UI/API, 생성 즉시 auto-merge로 우회하지 않는다.
- Branch/worktree 조작이 실제로 필요할 때만
  `.agents/skills/ai-do-worktree-management/SKILL.md`를 적용한다.

## Platform Boundaries

- 현재 target의 extension point를 사용한다. 임의 상수, deep import, local rewrite, ad hoc
  registry, 수동 generated artifact로 기존 composition root나 public contract를 우회하지 않는다.
- App 화면·route·sidebar·API client는 `app-modules/<appId>/` 경계에 두고 외부 공유는 manifest,
  public API, bootstrap DTO로 노출한다. FastAPI router는 `ai_do_api.api_registry`에서 조립한다.
- API/request·response, persistence, i18n key, RBAC/workspace scope, worker registration,
  generated client는 기능 계약의 일부다. OpenAPI generated type은 재생성하고 새 DB schema는
  Alembic migration으로 관리한다.
- 공유/감사 가능 데이터는 승인된 DB/object-store를 정본으로 사용한다. UI 권한 숨김,
  `/tmp`, process-local state, JSON load-modify-write, client local storage를 공유 권한·데이터의
  정본으로 쓰지 않는다.
- 새 앱·포팅 또는 app identity/manifest, protected API composition, 공용 data/RBAC,
  worker bootstrap, file/network pipeline, AI extension point를 바꾸는 작업에만
  `ai-do-vibe-app-delivery`를 적용한다. 기존 scaffold 내부의 copy·번역·app-local UI·명확한
  버그 수정에는 자동 적용하지 않는다.
- 필요한 protected scaffold가 없으면 기능 구현을 확대하지 말고 Core Enablement로 분리한다.
  기능을 통과시키기 위해 같은 변경에서 CI, agent 지침, checker, guardrail exclusion,
  CODEOWNERS를 약화하지 않는다.
- 모든 생성형 LLM 실행은 등록된 `RegisteredLlmWorkload`와 공통 실행 interface를 사용한다.
  App code가 provider/model/pool을 선택하거나 direct SDK/HTTP, low-level gateway, cross-route
  fallback을 추가하지 않는다.
- Retrieval partition은 후보 범위일 뿐 권한 grant가 아니다. Source-owned ACL과 stable
  resource identity, versioned projection/outbox, generation cutover 계약은 ADR 0009를 따른다.

## Validation And Review

- 검증은 변경 위험에 비례한다. 관련 없는 API/DB/browser/full suite를 관성적으로 실행하지
  않고, shared·migration·external·불확실한 blast radius에서만 넓힌다.
- `pnpm ci:harness`는 정적 repository 계약이지 app merge-ready 증거가 아니다. 실제로 바뀐
  API/Web/worker/migration/file/network/user flow의 focused evidence를 사용한다.
- `dev` MR lane은 app delivery, protected platform, migration/generated/shared runtime,
  혼합 integration 경계를 바꿀 때만 필수다. 문서·번역·env 계약·harness/CI·단순 app-local
  변경에서는 advisory다. Draft/Ready 상태 자체는 검증 또는 병합 차단 조건이 아니다.
- MR review/merge 판단을 사용자가 요청하거나 review finding을 수정할 때만
  `ai-do-mr-review-validation`을 사용한다. 일반 구현 완료를 이유로 자동 로딩하지 않는다.
- Review와 evidence는 최신 source SHA와 target merge result에 결합한다. Source가 바뀌면
  affected evidence를 갱신하고, target이 바뀌어 영향 표면이 달라지면 다시 확인한다.

## Parallel Work

- 읽기·감사·로그 분석처럼 독립적인 workstream은 runtime 정책이 허용할 때 병렬 sub-agent를
  사용한다. 외부 권한, 시크릿, 파괴적 작업, 겹치는 파일 쓰기가 필요한 경우에는 위임하지 않는다.
- Main agent가 최종 범위, 통합, 변경, 검증 판단과 사용자 보고를 소유한다.
