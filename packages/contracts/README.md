# Shared Contracts

Use this package only for contracts consumed by two or more runtimes/apps.

Current exports:

- `@open-work-hub/contracts/dm`
- `@open-work-hub/contracts/openapi`
- `@open-work-hub/contracts/api`
- `@open-work-hub/contracts/open-work-hub-desktop-update-feed`

Keep app transport, auth tokens, Electron IPC, and adapter details in owning apps. Promote only shared path/query/payload invariants.

## Publish

Publish to the GitLab npm Package Registry. Tag must match package version.

```bash
git tag contracts-v0.0.3
git push origin contracts-v0.0.3
```
