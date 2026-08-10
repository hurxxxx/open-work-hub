---
name: open-alm-release-promotion
description: Promote Open ALM changes from dev to production through GitLab merge requests, validation checks, and production checkout deployment. Use when preparing a release, promoting dev to main, or coordinating production rollout.
---

# Open ALM Release Promotion

## Flow

1. Work on `/projects/open-alm/dev` branch `dev`.
2. Push `dev` to `origin/dev`.
3. Open a GitLab MR from `dev` to `main`.
4. Require the MR's single `release_validation` job to pass. It owns all
   non-Codex repository, Python, API, DB, and Web checks; Codex does not run here.
5. Merge the exact source SHA; do not push directly to `main`.
6. After merge, update `/projects/open-alm/prod` to `origin/main`.
7. In prod checkout, run `pnpm prod:deploy -- --dry-run`, then `pnpm prod:deploy`.

The standard flow and release-gate contract are owned by [production deployment layout](../../../docs/domains/release/production-deployment-layout.md). Do not replace the deploy entrypoint with a hand-assembled build/migrate/restart sequence.

## Protected Main Policy

- `main` is protected. Direct `git push origin main` is expected to fail and must not be used as the promotion path.
- Use `glab mr create --source-branch dev --target-branch main ... --yes`.
- Merge with a full source SHA guard, for example:
  ```bash
  SOURCE_SHA="$(git -C /projects/open-alm/dev rev-parse origin/dev)"
  glab mr merge <iid> --sha "$SOURCE_SHA" --auto-merge=false --message "Merge branch 'dev' into 'main'" --yes
  ```
- In `/projects/open-alm/prod`, deploy only the remote merge result:
  ```bash
  git fetch origin main dev
  git pull --ff-only origin main
  ```

## Required Evidence

- Latest `dev → main` pipeline has a successful `release_validation`.
- Runtime separation, env, API/DB and Web evidence is produced by that job.
- Production dry-run is still required before the actual deploy.

## Release Notes

When preparing user-facing release announcements, follow
`docs/domains/release/release-notes-guidelines.md`. Keep the skill focused on
promotion flow; the document is the source of truth for release note wording,
same-day update naming, and user-friendly phrasing.

## Stop Conditions

- Production env does not report `environment=production`.
- Working tree is dirty in prod before deploy.
- `main` promotion requires direct push instead of a GitLab MR.
- Migration safety is unclear or rollback path is missing.
