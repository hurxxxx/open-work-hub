# Project Agent Rules

## 1. Think Before Coding

**Don't assume. Don't hide confusion. Surface tradeoffs.**

Before implementing:
- State your assumptions explicitly. If uncertain, ask.
- If multiple interpretations exist, present them - don't pick silently.
- If a simpler approach exists, say so. Push back when warranted.
- If something is unclear, stop. Name what's confusing. Ask.

## 2. Simplicity First

**Minimum code that solves the problem. Nothing speculative.**

- No features beyond what was asked.
- No abstractions for single-use code.
- No "flexibility" or "configurability" that wasn't requested.
- No error handling for impossible scenarios.
- If you write 200 lines and it could be 50, rewrite it.

Ask yourself: "Would a senior engineer say this is overcomplicated?" If yes, simplify.

## 3. Surgical Changes

**Touch only what you must. Clean up only your own mess.**

When editing existing code:
- Don't "improve" adjacent code, comments, or formatting.
- Don't refactor things that aren't broken.
- Match existing style, even if you'd do it differently.
- If you notice unrelated dead code, mention it - don't delete it.

When your changes create orphans:
- Remove imports/variables/functions that YOUR changes made unused.
- Don't remove pre-existing dead code unless asked.

The test: Every changed line should trace directly to the user's request.

## 4. Goal-Driven Execution

**Define success criteria. Loop until verified.**

Transform tasks into verifiable goals:
- "Add validation" → "Write tests for invalid inputs, then make them pass"
- "Fix the bug" → "Write a test that reproduces it, then make it pass"
- "Refactor X" → "Ensure tests pass before and after"

For multi-step tasks, state a brief plan:
```
1. [Step] → verify: [check]
2. [Step] → verify: [check]
3. [Step] → verify: [check]
```

Strong success criteria let you loop independently. Weak criteria ("make it work") require constant clarification.

---

## Project-Specific Rules

### Source of Truth
- 활성 에이전트 지시는 루트 `agents.md` 하나만 사용한다. `AGENTS.md`, `CLAUDE.md`, `.claude/`, `.codex/` 등 도구별 경로를 다시 만들지 않는다.
- 과거 지시 파일이 필요하면 Git 히스토리에서 복원한다 (`git log --all -- <path>` → `git restore --source <commit> -- <path>`).

### Git
- 별도 요청이 없으면 `git commit` / `git push` 를 하지 않는다.
- 명시적 요청 시 브랜치 미지정이면 기본 대상은 `main`.

### Legacy
- `legacy_ai_portal_prototype/` 는 보관용. 새 구현의 기준 구조나 재사용 소스로 삼지 않고, 요청이 없으면 수정하지 않는다. 흐름·화면·프롬프트·샘플 데이터 확인 용도로만 참고한다.

### UI
- 통계 카드 남발, BoxShadow 카드, 두꺼운 외곽선 지양.
- ClickUp/Jira 류의 평면 레이아웃, 넉넉한 여백, dense typography 우선.

### Web App Boundaries
- web 앱별 화면, 라우트, 사이드바 구현은 `apps/web/src/app-modules/<appId>/` 내부에 둔다.
- 다른 앱이나 shell 은 app module 내부(`routes`, `sidebar`, `views`)를 직접 import 하지 않고 public root 또는 `manifest` 경계만 사용한다.
- 앱 전용 API 는 해당 `app-modules/<appId>/api` 내부에 두고, 외부 공유가 필요하면 `<appId>/public-api` 로만 노출한다. `apps/web/src/domains/*` 경로를 새 진입점으로 만들지 않는다.
- 공용 코드는 실제로 여러 앱에서 쓰이는 순수 UI/유틸만 `shared`, `components`, `lib`, `platform` 쪽에 둔다. 특정 앱 전용이면 해당 app module 로 이동한다.
- web 구조 변경 후에는 `pnpm check:web-architecture` 와 필요한 경우 `pnpm nx e2e-shell web` 을 함께 확인한다.

### API Boundaries
- FastAPI router 등록은 `ai_do_api.api_registry` 를 composition root 로 사용한다. domain service/module 에서 `*.router` 를 import 하지 않는다.
- 재사용 가능한 domain 로직은 router 가 아니라 `service`, `read_model`, 또는 명시적인 helper 모듈에 둔다.
- OpenAPI 타입은 `pnpm generate:api-client` 로 갱신하고, 사람이 `apps/web/src/platform/api/openapi.generated.d.ts` 를 직접 수정하지 않는다.
- API 계약/경계 변경 후에는 `pnpm check:api-contract` 와 `pnpm check:api-architecture` 를 확인한다.

### Context
- 기본은 코드와 현재 작업 파일. `/docs` 는 보관용 참고 자료.
- `docs/planning/`, `docs/product/`, `docs/meetings/` 는 사용자가 지목한 경우에만 읽는다.
- 명시 없으면 문서보다 현재 코드/테스트 우선.

### Review Method
사용자가 리뷰를 요청하면 구현 성격에 맞는 방법을 먼저 고르고, 그 방법의 불변식 기준으로 findings 를 정리한다.
- 상태 전이·승인 게이트·스트리밍·워크플로·재시도·async orchestration → **상태기계/불변식 리뷰**
- API·이벤트·스키마·DB 모델·외부 계약 변경 → **계약 기반 리뷰**
- 트랜잭션·락·경쟁 조건·idempotency → **동시성/원자성 리뷰**
- 파서·변환기·정규화·diff/merge → **property/edge-case 리뷰**
- UI·상호작용·네비게이션·권한 차단 → **사용자 흐름/E2E 리뷰**

테스트는 happy path 개수가 아니라 **핵심 불변식을 실제로 검증하는지**로 판단한다.

### AI Capability Platform
정본은 [`adr/0002-mcp-capability-platform.md`](./adr/0002-mcp-capability-platform.md).
- 새 AI tool/capability 는 ad-hoc 분기 대신 `register_ai_capabilities(registry)` + `AiCapabilityRegistry` 경로 사용.
- 인간용 REST request model 재사용 금지, **AI 전용 DTO** 로 정의.
- handler 는 router 로직 복제 대신 **application service 경계** 호출.
- write capability 는 승인 게이트 우회 금지. `approval_required=True` 면 preview builder + discoverability predicate 같이 등록.
- capability 계약 변경 PR 은 ADR/테스트도 같은 PR 에서 갱신.

### UI E2E
- 실제 UI/E2E 요청 시 로컬 서버 + `agent-browser` 로 상호작용 기반 점검. CLI surface 가 불명확하면 `agent-browser --help` 먼저 확인.
- 기본 포트: web `127.0.0.1:4200`, api `127.0.0.1:8000`. 안 떠 있으면 `pnpm nx dev web` / `pnpm nx dev api`.
- named session 사용 (예: `--session doowon-e2e`).
- ref (`@e1` 류) 안정성을 위해 한 셸 호출 안에서 `open → wait → snapshot → click/fill/upload → wait → snapshot` 으로 묶는다.
- 매 점검에서 URL (`get url`), snapshot, console, errors 를 함께 확인한다.
- 파일 업로드/다운로드 화면은 실제 왕복 한 번 확인. 임시 산출물은 `/tmp` 아래.
- seed quick-login 카드 클릭이 불안정하면 이메일/비밀번호 직접 입력으로 진행.
- workspace shell 회귀 점검:
  - legacy 최상위 경로 (`/meeting`, `/docs`, `/pms`, `/planner`, `/ai`) 는 PR1 `cfe4215` 에서 제거. 진입은 `/w/:workspaceSlug/<app>` 만 사용하고, 위 경로는 `NotFoundView` 로 떨어져야 정상 (자동 리다이렉트 없음).
  - 접근 가능 / 불가 workspace·app 조합 양쪽 확인.
  - `/w/:workspaceSlug/settings` 와 `/admin/workspaces` 의 detail/member flow.
- 브라우저 기반 점검 결과는 작업 기록 문서에 간단히 남겨 다음 세션이 이어받을 수 있게 한다.
