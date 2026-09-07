---
name: diagnose
description: Disciplined reproduction and hypothesis loop for unclear or hard bugs and performance regressions. Use when the user explicitly asks to diagnose/debug, the cause is unknown after initial inspection, reproduction or instrumentation is required, or performance regressed. Do not use for routine implementation or a known-cause fix with an existing focused test.
---

# Diagnose

Use current code/tests, owner docs, and root ADRs. Do not guess past a missing feedback loop.

## Loop

1. Build deterministic pass/fail signal: focused test, curl/script, CLI fixture, Playwright, trace replay, throwaway harness, fuzz loop, bisection, or `scripts/hitl-loop.template.sh`.
2. Reproduce the user's exact failure. Capture symptom and repeatability.
3. Rank the hypotheses supported by current evidence. Each predicts what probe will prove or disprove it; do not pad the list to a fixed count.
4. Instrument one variable per probe. Use debugger/REPL first, then targeted tagged logs like `[DEBUG-a4f2]`. For perf, measure before fixing.
5. For diagnosis-only requests, report the cause, evidence, and proposed fix without modifying product code.
6. When repair is requested, fix the cause, add a regression test at the real bug seam when useful, and re-run the original loop. Use authorization already given in this task.
7. Remove temporary debug code. Record actual cause and validation.

## Stop

- No credible loop after attempts: report attempts and ask for repro environment, artifact, or scoped instrumentation.
- Failure differs from user report: do not fix nearby bug as if it were the target.
