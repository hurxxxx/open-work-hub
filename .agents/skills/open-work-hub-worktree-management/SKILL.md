---
name: open-work-hub-worktree-management
description: Safely create, select, inspect, and remove Git branches or worktrees for Open Work Hub without disturbing unrelated changes. Use when branch/worktree operations are requested, editing an existing MR source branch, or recovering from a dirty or wrong-branch checkout. Do not use for ordinary edits in the current suitable checkout.
---

# Open Work Hub Worktree Management

## Invariants

- GitLab `origin` is the site canonical remote. GitHub `upstream` is source-only and must not receive site pushes.
- Site integration branch is `dev`; protected production branch is `main`.
- Do not switch, rebase, or remove branches in a checkout with unrelated dirty changes.
- A worktree isolates branch state; it does not authorize edits, commits, pushes, MR changes, or delegation beyond the user's request.
- Never treat a fixed internal server path as canonical. Resolve the current repository and use an explicit sibling worktree path.
- Do not remove a worktree until its changes are merged, intentionally abandoned, or safely represented elsewhere.

## Before Branch Operations

```bash
git status --short --branch
git worktree list
git remote -v
```

For a new site feature branch in a clean current checkout, base it on current GitLab `dev`. Fetching is a network read and should be done only when fresh remote state is needed:

```bash
git fetch origin dev
git switch -c feature/<task-slug> origin/dev
```

For isolated parallel work, choose and validate an explicit sibling target before creation:

```bash
git fetch origin dev
git worktree add -b feature/<task-slug> ../open-work-hub-<task-slug> origin/dev
```

For an existing MR source branch, inspect its head with `glab mr view` and create a dedicated worktree from the fetched remote branch. Do not switch the user's active dirty checkout.

## Cleanup

Inspect status first. Removal is allowed only when the exact worktree and branch are known safe:

```bash
git -C ../open-work-hub-<task-slug> status --short --branch
git worktree remove ../open-work-hub-<task-slug>
git branch -d feature/<task-slug>
```

Use forced removal or `git branch -D` only after explicit confirmation that unmerged state may be discarded.
