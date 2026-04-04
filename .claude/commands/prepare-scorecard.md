---
description: Draft a scenario scorecard from eval outputs or a change summary.
argument-hint: [scenario-id-or-eval-summary]
disable-model-invocation: true
allowed-tools: Read Grep Glob
---

Prepare a scorecard draft for:

$ARGUMENTS

Steps:
1. Read `docs/harness/trace-and-scorecard-spec.md`.
2. Read `docs/harness/eval-regression-spec.md`.
3. Read the matching `TraceGradeSpec` and `EvalSuite` manifest.
4. Map the provided evidence to the required scorecard fields.
5. Produce a `green`, `yellow`, or `red` status and a `go`, `hold-until-review`, `hold`, or `rollback-candidate` recommendation.
6. Highlight which metrics are missing before a final decision can be made.
