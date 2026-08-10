---
name: ai-do-worktree-management
description: Keep /projects/ai-do/dev on dev while performing branch or worktree operations. Use when switching/creating/removing branches or worktrees, editing an existing MR source branch, or recovering from a dirty/wrong-branch checkout. Do not use for ordinary edits when /projects/ai-do/dev is already clean and on dev.
---

# AI-DO Worktree Management

## Non-Negotiables

- `/projects/ai-do/dev` is the live development server checkout. It must stay on the `dev` branch because dev services run from this path.
- Never run `git checkout`, `git switch`, `git rebase`, or feature/MR branch work in `/projects/ai-do/dev`.
- Do not use `/projects/ai-do/dev` as a scratch branch-switching area, even for quick MR fixes.
- When working directly on the server checkout and the user has not explicitly asked for a worktree branch, edit `/projects/ai-do/dev` on the existing `dev` branch.
- On a local developer checkout, do not create `/projects/ai-do/worktrees/...`; create and checkout a normal feature branch in the current checkout.
- Use `/projects/ai-do/worktrees/<task-slug>` only when working on the development server and the user explicitly requests parallel branch/worktree work in addition to the live `dev` branch.
- A request to edit or fix an existing MR source branch counts as explicit authorization to create a dedicated worktree for that branch, because `/projects/ai-do/dev` must remain on `dev`.
- Root `agents.md` owns sub-agent selection; worktree choice does not imply delegation.
- Treat `/projects/ai-do/prod` as the production checkout only.
- Do not switch branches in a checkout with unrelated dirty changes.

## Principles

- Server direct development defaults to `/projects/ai-do/dev` on `dev`.
- Local development defaults to the current checkout with a normal feature branch.
- Server parallel branch/worktree work goes under `/projects/ai-do/worktrees/<task-slug>` only on explicit user request; existing MR branch edits are one such explicit case.
- Codex does not need a global working-directory change; set each command's `workdir` to the task worktree.
- If a command would require changing `/projects/ai-do/dev` away from `dev`, create a worktree instead.

## Start New Work

If the task is ordinary server-side development and `/projects/ai-do/dev` is already on `dev`, use `/projects/ai-do/dev` directly:

```bash
git -C /projects/ai-do/dev status --short --branch
```

If you are on a local developer checkout and need a feature branch, use the current checkout:

```bash
git fetch origin dev
git switch -c feature/<task-slug> origin/dev
```

If you are on the development server and the user explicitly asks for a parallel worktree branch, create a worktree without changing `/projects/ai-do/dev`:

```bash
git fetch origin dev
mkdir -p /projects/ai-do/worktrees
git worktree add -B feature/<task-slug> /projects/ai-do/worktrees/<task-slug> origin/dev
```

Then run all task commands for that parallel branch with the task worktree as the working directory:

```bash
cd /projects/ai-do/worktrees/<task-slug>
```

Use short, lowercase slugs such as `codex-ready-comment`, `windows-doc-fix`, or `lab-api`.

## Fix An Existing MR

On a local developer checkout, use the current checkout:

```bash
git fetch origin <source-branch> dev
git switch -c fix-mr<IID>-<slug> origin/<source-branch>
```

On the development server, use a dedicated worktree. Do not switch `/projects/ai-do/dev` away from `dev`:

```bash
git fetch origin <source-branch> dev
git worktree add -B fix-mr<IID>-<slug> /projects/ai-do/worktrees/mr<IID>-<slug> origin/<source-branch>
```

Commit and push back to the MR source branch:

```bash
git push origin HEAD:<source-branch>
```

## Before Editing

Run in the checkout you are about to use:

```bash
git status --short --branch
git worktree list
```

If the current checkout is `/projects/ai-do/dev`, confirm it is on `dev` before editing. Use it directly for ordinary server development unless the user explicitly requested a parallel worktree branch. If a local developer checkout is dirty with unrelated files, do not switch branches in that checkout.

## Cleanup

Only remove a worktree after its changes are merged, abandoned, or intentionally pushed elsewhere:

```bash
git -C /projects/ai-do/worktrees/<task-slug> status --short
git worktree remove /projects/ai-do/worktrees/<task-slug>
git branch -d feature/<task-slug>
```

Use `git branch -D` only after confirming the branch is intentionally abandoned or already represented remotely.

## Safety Checks

Before final response:

```bash
git status --short --branch
git diff --check
```

After merging an MR created from a worktree:

```bash
git fetch origin dev
git log --oneline -3 origin/dev
git worktree remove /projects/ai-do/worktrees/<task-slug>
```
