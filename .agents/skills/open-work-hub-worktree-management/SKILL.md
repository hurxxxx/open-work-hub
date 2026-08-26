---
name: open-work-hub-worktree-management
description: Safely create, select, inspect, and remove Git branches or worktrees for Open Work Hub without disturbing unrelated changes. Use when branch/worktree operations are requested, editing an existing MR source branch, or recovering from a dirty or wrong-branch checkout. Do not use for ordinary edits in the current suitable checkout.
---

# Worktree Management

## Rules

- GitLab `origin` canonical; GitHub `upstream` source-only.
- Feature base `origin/dev`; production target `origin/main`.
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
git switch -c feature/<task-slug> origin/dev
git worktree add -b feature/<task-slug> ../open-work-hub-<task-slug> origin/dev
git -C ../open-work-hub-<task-slug> status --short --branch
git worktree remove ../open-work-hub-<task-slug>
git branch -d feature/<task-slug>
```

Use `glab mr view` for existing MR source branch. Force removal/delete only after explicit discard confirmation.
