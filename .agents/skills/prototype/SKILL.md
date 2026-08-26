---
name: prototype
description: Build a throwaway prototype to flush out a design before committing to it. Routes between two branches — a runnable terminal app for state/business-logic questions, or several radically different UI variations toggleable from one route. Use when the user wants to prototype, sanity-check a data model or state machine, mock up a UI, explore design options, or says "prototype this", "let me play with it", "try a few designs".
---

# Prototype

Prototype = throwaway code that answers one question.

## Choose

- Logic/state/data shape: [LOGIC.md](LOGIC.md).
- Visual/UI layout: [UI.md](UI.md).

## Rules

- Mark as prototype and place near future real code.
- One command to run using existing task runner.
- In-memory state by default; real DB only if persistence is the question.
- No production polish, broad abstractions, or tests.
- Show full relevant state after actions or variant switch.
- When answered, delete prototype or fold decision into real code.
- Keep only the answer in durable docs/issue/ADR/commit.
