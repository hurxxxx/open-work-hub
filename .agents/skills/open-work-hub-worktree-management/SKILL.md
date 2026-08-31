---
name: open-work-hub-worktree-management
description: Safely create, select, inspect, and remove Git branches or worktrees for Open Work Hub without disturbing unrelated changes. Use when branch/worktree operations are requested, editing an existing MR source branch, or recovering from a dirty or wrong-branch checkout. Do not use for ordinary edits in the current suitable checkout.
---

# Worktree Management

## Rules

- Branch and mutation authorization lives in root `AGENTS.md`.
- The checkout root contains sibling `dev`, `prod`, and `worktrees/` paths; reserve `prod` for `main` production operations.
- Routine work stays on the existing clean `dev` checkout; explicitly requested feature worktrees live under `../worktrees/<slug>`.
- Use a temporary detached `../worktrees/<slug>` from `origin/dev` only to preserve unrelated dirty work, then remove it after handoff.
- Do not switch/rebase/remove branches with unrelated dirty changes.
- Worktree isolation does not authorize edits/commits/push/MR mutations.
- Remove only safely merged/abandoned/represented state.

## Commands

```bash
git status --short --branch
git worktree list
git remote -v
git fetch origin dev
git worktree add ../worktrees/<feature-slug> -b <feature-branch> origin/dev
git worktree add --detach ../worktrees/<task-slug> origin/dev
git -C ../worktrees/<task-slug> status --short --branch
git worktree remove ../worktrees/<task-slug>
git worktree prune
```

Resolve an explicitly requested existing branch or MR before checkout. Force removal/delete only after explicit discard confirmation.
