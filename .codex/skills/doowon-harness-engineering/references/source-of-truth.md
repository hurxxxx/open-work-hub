# Source Of Truth Map

## Read first

- `docs/agents/context-loading-policy.md`
- `docs/agents/agent-operating-standard.md`
- `docs/harness/harness-overview.md`

## Read by task type

### Architecture or repo structure

- `docs/architecture/system-blueprint.md`

### Runtime service behavior

- `docs/harness/service-runtime-harness.md`
- `docs/harness/trace-and-scorecard-spec.md`

### Eval, regression, release gate

- `docs/harness/eval-regression-spec.md`
- `docs/ops/release-gates-and-alerts.md`

### Scenario-specific work

- `docs/harness/scenarios/documents-rag.md`
- `docs/harness/scenarios/plm-query.md`
- `docs/harness/scenarios/draft-generation.md`
- `docs/harness/scenarios/ocr-pipeline.md`
- `docs/harness/scenarios/wiki-pms.md`

## Adapter files

These files must stay aligned with the docs above and should not invent new rules:

- `agents.md`
- `CLAUDE.md`
- `.claude/rules/*`
- `.claude/commands/*`
- `.claude/agents/*`
- `.github/copilot-instructions.md`
- `.cursor/rules/*`
