---
name: tdd
description: Test-driven development with a red-green-refactor loop. Use when the user explicitly requests TDD, red-green-refactor, or test-first implementation. Do not use merely because the task needs tests or an integration test.
---

# TDD

## Rules

- Test public behavior through public interfaces.
- One vertical slice at a time: one failing test, minimal implementation, pass, repeat.
- Do not write all tests first or implement broad speculative support.
- Do not refactor while red.
- Confirm interface and priority behaviors with user before code when not already clear.
- Use owner docs/ADRs for names and contract boundaries.

## Loop

1. Pick one behavior.
2. Write one failing test.
3. Implement only enough to pass.
4. Repeat for next behavior.
5. Refactor after green; run tests after each refactor.

## Checks

- behavior, not implementation
- public interface only
- survives internal refactor
- no own-module mocks
- no speculative features

Refs: [tests](tests.md), [mocking](mocking.md), [deep modules](deep-modules.md), [interface design](interface-design.md), [refactoring](refactoring.md).
