---
name: doowon-harness-engineering
description: Use for any work in this repository that touches architecture, agent adapters, prompts, workflows, RAG, PLM, OCR, draft generation, wiki/PMS, or eval/release-gate behavior. Map the task to a scenario, read the source-of-truth docs, update eval implications, and report results in the repository's standard format.
---

# Doowon Harness Engineering

Use this skill whenever a task in this repository affects LLM behavior, service workflows, docs, or agent consistency.

## Workflow

1. Map the request to exactly one `scenario_id`, using a path hint first when the task already points at a file or folder.
2. Read `docs/agents/context-loading-policy.md`.
3. Read `docs/agents/agent-operating-standard.md`.
4. Read the matching `DomainRuleManifest` and `ScenarioManifest` first.
5. Read only the matching scenario doc under `docs/harness/scenarios/`.
6. Read `docs/harness/eval-regression-spec.md` only if the task touches prompts, workflows, retrieval, guardrails, trace, exports, or release gates.
7. If the task changes service behavior, read `docs/harness/service-runtime-harness.md`.
8. If the task changes stage prompts or online scoring, read the matching `workflow.json`, `EvalSuite`, and `TraceGradeSpec`.
9. Read `docs/ops/sprint-workflow.md` and `docs/ops/learnings-and-checkpoints.md` only when the task is substantial or introduces a new pattern.
10. Search official docs or the referenced implementation first before designing unfamiliar runtime, infrastructure, or agent patterns from scratch.
11. Summarize the work using the repository contract:
   - `scenario_id`
   - `changed surfaces`
   - `tests/evals`
   - `open risks`

## Required behaviors

- Treat `docs/*` plus the structured assets under `docs/harness/manifests`, `docs/harness/prompt-bundles`, and `docs/harness/evals` as source of truth, and adapter files as projections.
- Keep root context minimal and load only the documents required for the current scenario.
- Do not read unrelated scenario docs or broad architecture docs unless the current task requires them.
- Do not make prompt-only or workflow-only changes without matching eval implications.
- Treat citation-free generated responses as failures.
- Do not edit `legacy_ai_portal_prototype/` unless the user explicitly asks.

## Additional resources

- Source-of-truth map: [references/source-of-truth.md](references/source-of-truth.md)
- Scenario rubrics and gate summaries: [references/scenario-rubrics.md](references/scenario-rubrics.md)
- Output format expectations: [references/response-contract.md](references/response-contract.md)
- Workflow habits from gstack-style adaptation: [references/workflow-adaptations.md](references/workflow-adaptations.md)

## Helper scripts

- `python3 .codex/skills/doowon-harness-engineering/scripts/select_scenario.py [--path <file-path>] "<request>"`
- `python3 .codex/skills/doowon-harness-engineering/scripts/select_context_docs.py <scenario-id> [surface]`
- `python3 .codex/skills/doowon-harness-engineering/scripts/select_context_docs.py --path <file-path> [surface]`
- `python3 .codex/skills/doowon-harness-engineering/scripts/required_regressions.py <scenario-id>`
- `bash .codex/skills/doowon-harness-engineering/scripts/install_to_codex_home.sh`
