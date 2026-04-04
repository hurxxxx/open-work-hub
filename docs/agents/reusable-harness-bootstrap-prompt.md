# 재사용용 프로젝트 하네스 부트스트랩 프롬프트

이 파일은 새 프로젝트에서 “최소 루트 컨텍스트 + 시나리오 중심 문서 + 구조화 manifest + stage별 prompt bundle + eval/trace 기준 + Claude/Codex 어댑터” 구성을 다시 세팅할 때 사용하는 재사용 프롬프트다.

## 사용 방법

- 아래 프롬프트에서 placeholder만 새 프로젝트에 맞게 바꾼다.
- 프로젝트에 Cursor/Copilot을 쓰지 않으면 그대로 비활성 상태로 둔다.
- 실제 코드 스캐폴드가 없다면 상세 디렉터리 트리를 만들지 말고, 책임/경계/manifest 중심으로만 세팅하게 한다.

## Prompt

```text
You are setting up a new repository-wide harness engineering standard for the project below.

Project name:
<PROJECT_NAME>

Project goal:
<PROJECT_GOAL>

Primary product/workflow domains:
<PRIMARY_DOMAINS>

Expected scenario candidates:
<SCENARIO_CANDIDATES>

Current or intended stack:
<STACK>

Deployment/runtime constraints:
<DEPLOYMENT_AND_PROVIDER_CONSTRAINTS>

Agent tools we actually want to support:
<AGENT_TOOLS_TO_SUPPORT>

Important preferences:
- Keep root context minimal.
- Do not put volatile directory snapshots into root prompts or long-lived memory.
- Separate prose docs from structured machine-readable assets.
- Use scenario-first design.
- Use path/domain-scoped context loading.
- Split service prompts by stage instead of one giant prompt.
- For authenticated product surfaces, prefer an enterprise portal app shell with a persistent left sidebar on desktop.
- Do not default to hero-first, card-heavy, or marketing-style SPA layouts.
- Avoid generic AI-generated visual tropes such as purple gradients, glassmorphism, neon glow, and bento-card dashboards.
- Prefer provider-neutral contracts for runtime traces and evals.
- Default eval runner should be promptfoo unless there is a strong reason not to.
- Claude Code and Codex should behave consistently from the same source-of-truth docs.
- Do not add adapters for tools we will not use.
- If the code scaffold does not exist yet, do not invent a fake detailed tree; document responsibilities and boundaries only.
- Do not create heavy automation unless clearly needed; prioritize update discipline and source-of-truth clarity.

First, research the latest relevant official guidance before designing anything. Use official documentation first, especially:
- OpenAI official docs for evaluation best practices, prompting, model optimization, trace grading, prompt caching, latency optimization, and agent/runtime guidance
- Anthropic official docs for prompt templates/variables, long-context handling, hallucination reduction, Claude Code memory/rules/hooks/subagents/slash commands
- promptfoo official docs or repo
- Langfuse official docs or repo only as optional observability reference
- Inspect AI official docs or repo only as optional high-risk eval reference
- Any additional official or primary-source material that is directly relevant to this project's stack or constraints

Then do the following:

1. Validate whether a harness strategy like this is appropriate for the project. If something should be simplified, simplify it instead of copying blindly.

2. Create or update a source-of-truth document set under:
- `docs/architecture/`
- `docs/harness/`
- `docs/agents/`
- `docs/ops/`

3. Create or update the minimum core docs:
- `docs/architecture/system-blueprint.md`
- `docs/architecture/enterprise-portal-design-direction.md`
- `docs/harness/harness-overview.md`
- `docs/harness/service-runtime-harness.md`
- `docs/harness/eval-regression-spec.md`
- `docs/harness/trace-and-scorecard-spec.md`
- `docs/agents/agent-operating-standard.md`
- `docs/agents/context-loading-policy.md`
- `docs/agents/domain-context-mapping.md`
- `docs/agents/local-rule-template.md`
- `docs/agents/reusable-enterprise-portal-design-prompt.md`
- `docs/ops/release-gates-and-alerts.md`

4. Create structured source-of-truth assets, not just prose docs:
- `docs/agents/manifests/domain-rule-manifests/*.json`
- `docs/harness/manifests/scenarios/*.json`
- `docs/harness/manifests/eval-suites/*.json`
- `docs/harness/manifests/trace-grade-specs/*.json`
- `docs/harness/prompt-bundles/<scenario>/*`
- `docs/harness/evals/promptfoo/scenarios/*.yaml`
- `docs/harness/evals/datasets/<scenario>/*`
- JSON schemas for the key manifest types

5. Use these key structured contracts unless the project clearly needs a simpler variant:
- `ScenarioManifest`
- `DomainRuleManifest`
- `PromptBundle`
- `EvalSuite`
- `TraceGradeSpec`
- `TraceEvent`
- `Scorecard`
- `ReleaseGateDecision`
- `ContextSelectionResult`

6. Make the service harness stage-based. The default chain should be adapted per scenario, but generally follow:
- `intent/classification`
- `retrieval or planning`
- `grounding / quote extraction`
- `response synthesis`
- `policy / judge`

7. Enforce context minimalism:
- Root context should stay very small.
- Only load the current scenario and directly relevant support docs.
- Do not load unrelated domain docs by default.
- Do not keep detailed current directory/package layouts in long-lived instructions.
- When a file path is known, resolve domain first, then scenario.

8. Make the docs and assets usable by real agents:
- Root shared rule file such as `agents.md`
- `CLAUDE.md`
- `.claude/rules/`
- `.claude/commands/`
- `.claude/agents/`
- `.claude/settings.json`
- Claude hooks only for deterministic enforcement
- A repo-owned Codex skill

8a. Add a dedicated frontend design direction that is loaded only for UI work:
- Make it explicit that authenticated enterprise product screens should default to a left-sidebar app shell on desktop
- Define what “AI-looking” anti-patterns to avoid
- Provide one reusable design prompt for future projects and new screens
- Use official enterprise design systems and current primary-source references before inventing a house style

9. If the project has no real code scaffold yet:
- Do not fabricate detailed `apps/*` or `packages/*` structure
- Only document stable responsibilities, boundaries, and future local rule placement strategy
- Keep local `AGENTS.md` support as a template and a future-ready rule, not as fake files for nonexistent paths

10. Make updates maintainable:
- Changes should normally be scenario-scoped
- Each scenario should have one obvious set of source-of-truth assets to update
- Adapters must remain projections, not independent sources of rules

11. If you create hooks or helper scripts, keep them small and practical:
- Scenario selection helper
- Context doc selection helper
- Required regressions helper
- Optional lightweight asset validation only if it materially helps

12. Avoid unnecessary bloat:
- Do not create adapters for Cursor or Copilot unless explicitly requested
- Do not add CI-heavy automation unless the repository is ready for it
- Do not over-specify future code structure that does not exist yet

13. When done, report results in this format:
- `scenario_id` or `setup_scope`
- `changed surfaces`
- `tests/evals`
- `open risks`

14. If you are unsure about a pattern, prefer:
- the latest official docs
- primary-source repos
- project-specific simplification over generic enterprise ceremony

Now implement this in the current repository, not just as a proposal. Create the files, wire the references, and keep the structure internally consistent.
```

## 메모

- 이 프롬프트는 “지금 저장소의 설계 원칙”을 다른 프로젝트로 옮길 때 쓰는 부트스트랩용이다.
- 새 프로젝트의 실제 성숙도에 맞게 단순화하는 것을 허용하는 문구를 일부러 넣었다.
- 핵심은 `문서 설명 + 구조화 자산 + 최소 컨텍스트 + 시나리오 중심 업데이트`를 동시에 요구하는 것이다.
