# CLAUDE.md — Claude Code 전용 운영 지침

일반 에이전트 지시·프로젝트 규칙의 정본은 루트 [`agents.md`](./agents.md) 다.
이 파일에는 **Claude Code 도구 실행 환경에만 해당하는 운영 노트**만 둔다(다른 도구·사람 온보딩과 무관).

## 최우선 규칙 — agents.md를 무시하지 말 것

- Claude Code 는 작업 시작 전에 반드시 루트 [`agents.md`](./agents.md)를 읽고 따른다.
- 이 파일은 `agents.md`를 대체하지 않는다. 충돌하면 `agents.md`가 우선이다.
- `agents.md`의 Non-Negotiable Contracts 는 선택사항이 아니다. 어기면 구현이 동작해도 실패한 작업이다.
- Claude Code 도구 편의, 로컬 관찰, 임시 파일, 샌드박스 제약을 이유로 `agents.md` 계약을 우회하지 않는다.
- 코드 구조, 얇은 추상화, 단일 진입점, 공통화 판단이 필요한 작업은 `agents.md`의 Project References에
  등록된 [`docs/agents/llm-friendly-development.md`](./docs/agents/llm-friendly-development.md)를 먼저 확인하고,
  필요한 경우 [`docs/agents/composable-abstractions.md`](./docs/agents/composable-abstractions.md)를 함께 확인한다.

## 지침 하네스 — 작업 시작 시 동적 적용 (누락 금지)

프로젝트 지침은 `agents.md` 한 파일이 아니라 **티어로 나뉜 문서·ADR·skill 트리**다. 전부를
선행 로드하지 않고, **작업 표면(변경 대상)에 맞춰 동적으로 끌어와** 적용한다. 규칙 본문은 아래
문서들이 정본이며 이 파일에 복제하지 않는다. 작업을 시작하면 매번 다음 순서를 따른다.

1. 현재 코드·테스트와 사용자 요청을 먼저 본다.
2. 루트 [`agents.md`](./agents.md) — **항상**. Core Rules, Non-Negotiable Contracts, Feature
   Branch Implementation Contracts 를 적용한다.
3. [`docs/current/project-status.md`](./docs/current/project-status.md),
   [`docs/current/ai-hub-transition-index.md`](./docs/current/ai-hub-transition-index.md) — **항상**.
   무엇이 구현됐고 무엇이 주력/보류인지(예: RAG 는 Docs 우선, Files/Knowledge Sources 운영 색인 제외)를
   현 방향으로 삼는다.
4. 변경 표면에 해당하는 티어 문서를 끌어온다(아래 매핑). 해당 없으면 읽지 않는다.
5. 트리거가 맞는 skill 을 Skill 도구로 호출한다(다음 절). skill 이 다루는 일을 직접 재구현하지 않는다.
6. 보고 전에 **변경 유형별 검증 하네스**를 돌린다.

### 변경 표면 → 문서 매핑 (정본 위치)

| 변경 표면 | 먼저 읽을 문서 |
| --- | --- |
| 구현 계약·검증 깊이·중단 조건 | [`docs/agents/vibe-coding-harness.md`](./docs/agents/vibe-coding-harness.md) |
| 코드 구조·얇은 추상화·단일 진입점 | [`docs/agents/llm-friendly-development.md`](./docs/agents/llm-friendly-development.md) |
| 비슷한 화면/기능의 공통화·추상화 판단 | [`docs/agents/composable-abstractions.md`](./docs/agents/composable-abstractions.md) |
| UI 생성/수정 | [`docs/agents/ui-components.md`](./docs/agents/ui-components.md), [`docs/product/ui-design-principles.md`](./docs/product/ui-design-principles.md) |
| 문서 구조 | [`docs/agents/domain.md`](./docs/agents/domain.md) |
| AI capability / MCP / registry | [`adr/0002-mcp-capability-platform.md`](./adr/0002-mcp-capability-platform.md), [`docs/domains/ai/write-policy.md`](./docs/domains/ai/write-policy.md) |
| 통합 검색/RAG/service layer | [`docs/domains/retrieval/README.md`](./docs/domains/retrieval/README.md), [`docs/domains/rag/README.md`](./docs/domains/rag/README.md) |
| embedding/rerank/Docling/ASR 추론 백엔드 | [`docs/domains/inference-gateway/backend-operations.md`](./docs/domains/inference-gateway/backend-operations.md), [`docs/domains/inference-gateway/dgx-spark-servers.md`](./docs/domains/inference-gateway/dgx-spark-servers.md) |
| 릴리스/배포/공유 계약 | [`docs/domains/release/production-deployment-layout.md`](./docs/domains/release/production-deployment-layout.md), [`docs/domains/release/shared-contracts-package.md`](./docs/domains/release/shared-contracts-package.md) |
| 이슈/작업 인입·triage | [`docs/agents/issue-tracker.md`](./docs/agents/issue-tracker.md), [`docs/agents/triage-labels.md`](./docs/agents/triage-labels.md) |

### 변경 유형 → 최소 검증 (정본: vibe-coding-harness 검증 하네스 표)

보고 전 변경 위험에 맞춰 실행한다. 상세·전체 목록은 vibe-coding-harness 문서를 정본으로 본다.

| 변경 유형 | 기본 확인 |
| --- | --- |
| 문서/지침 | `git diff --check`, `pnpm check:skills` |
| `.agents/skills` | `pnpm check:skills` |
| Web 구조/경계 | `pnpm check:web-architecture`, `pnpm nx typecheck web` |
| API/계약 | `pnpm check:api-contract`, `pnpm check:api-architecture`, focused pytest |
| Env/runtime | `pnpm check:env-contract`, `pnpm check:runtime-separation` |
| AI capability | registry/manifest/invoke/hidden-tool focused tests, ADR 0002 갱신 여부 |
| 릴리스 전 | `pnpm ci:harness` + affected app checks |

위 매핑은 빠른 진입점이다. 표에 없는 표면이 보이면 임의로 생략하지 말고 `agents.md` Project
References 와 `docs/` 트리에서 해당 문서를 찾아 적용한다.

## 프로젝트 skill — Claude Code 에서 쓸 수 있게 셋업 후 사용

프로젝트 skill 의 정본은 **git 추적되는 `.agents/skills/<name>/SKILL.md`** 다(거버넌스: `agents.md`
와 `ai-do-agent-skill-governance` skill). 그러나 Claude Code 는 skill 을 `.claude/skills/` 에서
발견하므로, **셋업하지 않으면 `ai-do-*` 프로젝트 skill 이 Skill 도구에 보이지 않는다.**

### 셋업 (없거나 깨졌으면 작업 시작 시 1회)

1. `.claude/skills/` 가 `.agents/skills` 를 가리키는지 확인한다. 없으면 노출한다.
   - 정본을 복제하지 않는다. Windows 디렉터리 **정션**으로 `.agents/skills` 를 그대로 노출한다.
     ```powershell
     New-Item -ItemType Junction -Path .claude\skills -Target .agents\skills
     ```
   - 정션이 막히면 per-skill 정션 또는 복사 대신, 정본 경로(`.agents/skills`)를 직접 읽어
     해당 SKILL.md 절차를 수행한다. **`.agents/skills` 를 편집·삭제하지 말고 정본으로만 둔다.**
2. `.claude/skills/` 는 **머신 로컬 노출물**이므로 커밋하지 않는다(`.gitignore` 의 `.claude/skills/`).
3. 노출 후 Skill 목록에 `ai-do-*` 가 보이는지 확인한다. 안 보이면 1번을 재실행한다.

### 포맷(변환)

- `.agents/skills/*/SKILL.md` 의 frontmatter(`name`, `Use when` 을 포함한 `description`)는 이미
  Claude Code skill 포맷과 호환된다. 보통 파일 재작성 없이 **경로 노출만으로 사용 가능**하다.
- frontmatter 가 빠졌거나 트리거가 불명확한 skill 을 발견하면, 사본이 아니라 **정본
  `.agents/skills` 에서** `name` + 명확한 `Use when` 트리거를 보강하고 `pnpm check:skills` 로 검증한다.

### 사용

- 작업이 skill 의 `Use when` 트리거에 닿으면 해당 skill 을 Skill 도구로 호출해 그 절차를 따른다.
  예: 워크트리/브랜치 → `ai-do-worktree-management`, 환경/연결 → `ai-do-development-environment`,
  i18n → `ai-do-i18n`, MR 리뷰 → `ai-do-mr-review-validation`, 릴리스 → `ai-do-release-promotion`,
  AI capability → `ai-do-mcp-capability-governance`, 작업 인입 → `ai-do-agent-work-intake`, 도메인 앱
  생성·포팅·app API/worker/file/AI 변경 → `ai-do-vibe-app-delivery`.
- 도메인 앱 요청은 코드 작성 전에 `ai-do-vibe-app-delivery`의 scaffold 확인과 contract map을 완료한다.
  protected scaffold가 없으면 core-enablement brief만 작성하고 구현을 중단한다. 기능을 통과시키기 위해
  shell/registry/generated contract/CI/checker/exclusion을 같은 MR에서 편집하거나 lane을 스스로 높이지 않는다.
- skill 이 다루는 절차를 임의로 우회·재구현하지 않는다. skill 내용과 `agents.md` 가 충돌하면
  `agents.md` 가 우선이다.
- `feature` -> `dev` MR은 반드시 clean/committed feature branch에서 아래 단일 진입점으로만
  등록한다.

  ```bash
  pnpm mr:publish -- --title "<title>" --description-file /tmp/ai-do-mr.md
  ```

  이 명령은 현재 `origin/dev`를 포함하는지 확인하고 전체 `origin/dev...HEAD` diff에서 lane을
  자동 계산한 뒤, 실제 MR 환경을 합성해 MR target policy, Python contract guardrails,
  repository harness, 그리고 변경 경로에 해당하는 API/migration/Web/affected 검증을 모두 로컬에서
  성공시킨 정확한 source/target SHA만 push한다. 그 다음에만 정확히 하나의 lane 라벨을 가진 Draft
  MR을 생성하거나 갱신하며 auto-merge를 켜지 않는다. 기존 MR에 auto-merge가 켜져 있으면 push
  전에 중단한다. source/target/lane/본문에 결합된 local-preflight receipt를
  본문에 붙이고 MR policy job이 이를 검증하므로, receipt가 없거나 내용이 달라진 직접 생성 MR은
  실패한다. lane을 수동 선택하거나 `glab mr create`, GitLab UI/API, push pipeline 성공으로 이
  gate를 우회하지 않는다. 실패했거나 실행하지 않았으면 push/MR 생성/Ready/auto-merge를 진행하지
  않는다.

- MR 본문을 먼저 완성해 repository 밖의 파일(예: `/tmp/ai-do-mr.md`)에 두어야 한다.
  `pnpm mr:preflight -- --description-file /tmp/ai-do-mr.md`는 dry run 용도이며,
  `mr:publish`는 publish 직전에 같은 검증 전체를 다시 실행한다. 검증 중 source SHA, target SHA,
  본문, worktree가 바뀌면 결과는 무효이며 처음부터 다시 실행한다.
- Claude Code 로 MR 을 열거나 ready 상태로 넘기기 전에는 구현과 검증을 마친 뒤 native `/review`
  workflow 를 반드시 실행한다. `/review` 는 target branch 기준 diff 를 보며, release blocker,
  contract/platform 경계, 누락 검증, merge conflict 를 찾는 마지막 gate 로 사용한다.
- `/review` workflow 가 해당 환경에서 보이지 않으면 MR 전 리뷰를 생략하지 말고
  `.agents/skills/ai-do-mr-review-validation/SKILL.md` 절차를 직접 수행한 뒤, fallback 으로
  수행했다는 사실과 남은 위험을 MR 본문 또는 최종 보고에 적는다.
- 도메인 앱 MR은 `.gitlab/merge_request_templates/Vibe_Domain_App.md`를 사용하고 Draft로 시작한다.
  `dev` 대상 MR의 lane은 `mr:publish`가 전체 diff에서 계산한다. `pnpm ci:harness`만으로 Ready로 바꾸지 않으며,
  source SHA가 바뀌면 affected checks와 `/review`를 다시 수행한다. target head가 바뀌면 merge-result
  diff와 리뷰를 다시 보고, 영향 표면이 달라진 경우 해당 affected checks도 다시 수행한다.

## 도구 샌드박스 — 원격 인프라 접근 시 비활성화

Windows 네이티브 로컬 개발자 머신은 원격 dev 인프라(`128.1.253.101` 의
Postgres/Redis/MinIO/OpenSearch/Qdrant, 내부 LLM)에 **네트워크로** 접속한다.
인프라는 직접 노출돼 있어 별도 터널 없이 접근 가능하다.

서버 dev checkout(`/projects/ai-do/dev`)에서 하는 Linux 개발·운영 작업은
`agents.md` 와 `ai-do-development-environment` skill 의 Server Dev 절을 따른다.
아래 샌드박스 주의사항은 Claude Code 로 Windows 로컬 셋업을 검증하거나 원격 dev
인프라 연결을 직접 확인할 때만 적용한다.

Claude Code 의 Bash/PowerShell 도구는 기본적으로 아웃바운드를 차단하는 샌드박스에서 실행된다
(`DefaultOutboundAction=Block` + `codex_sandbox_offline_block_outbound`). 그래서:

- 인프라 포트가 **실제로는 열려 있어도 도구 안에서는 "closed/FAIL" 로 보인다** (GitLab `8929` 같은 허용 대상만 통과).
- API 서버를 도구로 띄우면 원격 DB/Redis 등에 **연결하지 못해 기동이 실패**한다.

따라서 **Windows 로컬 셋업에서 원격 인프라나 외부 호스트에 접속하는 도구 호출은
샌드박스를 끄고 실행한다**(`dangerouslyDisableSandbox: true`). 대상:

- 연결성 테스트(Postgres/Redis/MinIO/OpenSearch/Qdrant reachability)
- API 서버 기동(`scripts\dev-windows.ps1`, uvicorn)과 그에 대한 health/login 검증
- 원격 인프라를 사용하는 migration·smoke

샌드박스가 켜진 상태의 "연결 실패" 결과만으로 **방화벽/인프라 다운이라 단정하지 말 것** — 샌드박스를 끄고 재확인한다.
순수 로컬 작업(파일 편집, `pnpm install`, 빌드, 로컬 git)은 샌드박스로 충분하다.
