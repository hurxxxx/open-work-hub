# Doowon Repository Instructions

Use the repository documentation as the source of truth.

- Read `docs/agents/agent-operating-standard.md` and `docs/agents/context-loading-policy.md` before proposing architecture or workflow changes.
- If a task touches LLM behavior, map it to exactly one scenario in `docs/harness/scenarios/`.
- Treat `docs/harness/harness-overview.md`, `docs/harness/service-runtime-harness.md`, `docs/harness/eval-regression-spec.md`, and `docs/harness/trace-and-scorecard-spec.md` as the canonical harness rules.
- Treat `docs/ops/sprint-workflow.md` and `docs/ops/learnings-and-checkpoints.md` as the canonical workflow habits.
- Prompt, workflow, retrieval, guardrail, trace, or export changes require matching eval and release-gate updates.
- Citation-free generated responses are failures.
- Load only the docs required for the current scenario; do not preload unrelated scenario or domain docs.
- Keep the UI search-first and low-card; prefer dense list, panel, and evidence layouts over generic dashboards.
- Do not modify `legacy_ai_portal_prototype/` unless the user explicitly asks.
- Do not commit or push unless the user explicitly asks.
- Search official docs or established patterns before designing unfamiliar runtime or infrastructure pieces from scratch.

When summarizing work, include:

- `scenario_id`
- changed surfaces
- required regressions
- open risks
