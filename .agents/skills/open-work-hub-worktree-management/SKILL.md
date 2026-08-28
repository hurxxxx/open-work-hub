---
name: open-work-hub-worktree-management
description: Safely create, select, inspect, and remove Git branches or worktrees for Open Work Hub without disturbing unrelated changes. Use when branch/worktree operations are requested, editing an existing MR source branch, or recovering from a dirty or wrong-branch checkout. Do not use for ordinary edits in the current suitable checkout.
---

# Worktree Management

## Rules

- Branch and mutation authorization lives in root `AGENTS.md`.
- Routine work stays on the existing clean `dev` checkout; do not create a persistent branch or worktree.
- Use a temporary detached worktree from `origin/dev` only to preserve unrelated dirty work, then remove it after handoff.
- Do not switch/rebase/remove branches with unrelated dirty changes.
- Worktree isolation does not authorize edits/commits/push/MR mutations.
- Use explicit sibling path; no fixed internal path.
- Remove only safely merged/abandoned/represented state.

## Commands

```bash
git status --short --branch
git worktree list
git remote -v
git fetch origin dev
git worktree add --detach ../open-work-hub-<task-slug> origin/dev
git -C ../open-work-hub-<task-slug> status --short --branch
git worktree remove ../open-work-hub-<task-slug>
git worktree prune
```

Resolve an explicitly requested existing branch or MR before checkout. Force removal/delete only after explicit discard confirmation.
