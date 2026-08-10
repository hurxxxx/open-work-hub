---
name: improve-codebase-architecture
description: Find deepening opportunities in Open ALM using current code, tests, owning domain/app documentation, and accepted decisions in root adr/. Use when the user wants to improve architecture, find refactoring opportunities, consolidate tightly-coupled modules, or make a codebase more testable and AI-navigable.
---

# Improve Codebase Architecture

Surface architectural friction and propose **deepening opportunities** — refactors that turn shallow modules into deep ones. The aim is testability and AI-navigability.

## Glossary

Use these terms exactly in every suggestion. Consistent language is the point — don't drift into "component," "service," "API," or "boundary." Full definitions in [LANGUAGE.md](LANGUAGE.md).

- **Module** — anything with an interface and an implementation (function, class, package, slice).
- **Interface** — everything a caller must know to use the module: types, invariants, error modes, ordering, config. Not just the type signature.
- **Implementation** — the code inside.
- **Depth** — leverage at the interface: a lot of behaviour behind a small interface. **Deep** = high leverage. **Shallow** = interface nearly as complex as the implementation.
- **Seam** — where an interface lives; a place behaviour can be altered without editing in place. (Use this, not "boundary.")
- **Adapter** — a concrete thing satisfying an interface at a seam.
- **Leverage** — what callers get from depth.
- **Locality** — what maintainers get from depth: change, bugs, knowledge concentrated in one place.

Key principles (see [LANGUAGE.md](LANGUAGE.md) for the full list):

- **Deletion test**: imagine deleting the module. If complexity vanishes, it was a pass-through. If complexity reappears across N callers, it was earning its keep.
- **The interface is the test surface.**
- **One adapter = hypothetical seam. Two adapters = real seam.**

This skill is informed by the project's current contracts. Owning domain and app documentation gives names to good seams; accepted ADRs record decisions the skill should not casually re-litigate.

## Process

### 1. Explore

Read current code and tests first, followed by `agents.md`, the relevant owner documents under `docs/current/`, `docs/domains/`, or `docs/apps/`, and accepted decisions under root `adr/`.

Use parallel read-only subagents when the runtime provides capacity and the exploration can be split into non-overlapping areas. Otherwise explore directly. Note where you experience friction:

- Where does understanding one concept require bouncing between many small modules?
- Where are modules **shallow** — interface nearly as complex as the implementation?
- Where have pure functions been extracted just for testability, but the real bugs hide in how they're called (no **locality**)?
- Where do tightly-coupled modules leak across their seams?
- Which parts of the codebase are untested, or hard to test through their current interface?

Apply the **deletion test** to anything you suspect is shallow: would deleting it concentrate complexity, or just move it? A "yes, concentrates" is the signal you want.

### 2. Present candidates

Present a numbered list of deepening opportunities. For each candidate:

- **Files** — which files/modules are involved
- **Problem** — why the current architecture is causing friction
- **Solution** — plain English description of what would change
- **Benefits** — explained in terms of locality and leverage, and also in how tests would improve

Use terminology from the owning domain/app documents for the domain and [LANGUAGE.md](LANGUAGE.md) for the architecture. Prefer the user-facing domain concept over an incidental implementation class name.

**ADR conflicts**: if a candidate contradicts an existing ADR, only surface it when the friction is real enough to warrant revisiting the ADR. Mark it clearly (e.g. _"contradicts ADR-0007 — but worth reopening because…"_). Don't list every theoretical refactor an ADR forbids.

Do NOT propose interfaces yet. Ask the user: "Which of these would you like to explore?"

### 3. Grilling loop

Once the user picks a candidate, drop into a grilling conversation. Walk the design tree with them — constraints, dependencies, the shape of the deepened module, what sits behind the seam, what tests survive.

Capture decisions only when documentation changes are part of the user's request:

- Add a confirmed term or current contract to the existing owning document under `docs/domains/` or `docs/apps/`; do not create a parallel glossary.
- Offer an ADR only for a durable, non-obvious trade-off that future reviews would otherwise reopen. ADRs live in root `adr/`; see [ADR-FORMAT.md](../grill-with-docs/ADR-FORMAT.md).
- For review-only requests, report recommended documentation changes without editing files.
- To explore alternative interfaces for the deepened module, use [INTERFACE-DESIGN.md](INTERFACE-DESIGN.md).
