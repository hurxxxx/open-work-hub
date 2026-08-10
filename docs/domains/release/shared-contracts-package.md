# Shared Contracts Package

`@ai-do/contracts` is the public package boundary for TypeScript/JSON contracts shared outside the `dwdcc/ai-do` monorepo.

## Ownership

- Source of truth: `dwdcc/ai-do`
- Package source: `packages/contracts`
- Package name: `@ai-do/contracts`
- Registry: GitLab npm Package Registry for `dwdcc/ai-do`
- Registry URL: `http://128.1.253.101:8929/api/v4/projects/1/packages/npm/`
- Source version: `packages/contracts/package.json`에서 확인
- Published versions: GitLab npm Package Registry에서 확인
- First external consumer: `dwdcc/ai-do-desktop`

Do not publish this package to public npm. Do not copy `packages/contracts` into split repositories. Split repositories consume exact package versions from the GitLab registry.

## Exports

The package publishes compiled ESM and declaration files from `dist/`.

- `@ai-do/contracts`
- `@ai-do/contracts/api`
- `@ai-do/contracts/auth`
- `@ai-do/contracts/ai-do-desktop-update-feed`
- `@ai-do/contracts/ai-do-desktop-update-feed.manifest.json`
- `@ai-do/contracts/openapi`
- `@ai-do/contracts/dm`
- `@ai-do/contracts/notifications`
- `@ai-do/contracts/realtime`

When adding a new public contract, update `packages/contracts/package.json` `exports`, add tests under `packages/contracts/src`, and run `pnpm ci:contract`.

## Publish Flow

Contract package releases are tag-driven. The tag must exactly match the package version.

1. Change `packages/contracts`.
2. Update `packages/contracts/package.json` `version`.
3. Run:

   ```bash
   pnpm ci:contract
   pnpm nx typecheck web
   ```

4. Merge/promote the change through the normal `dev` -> `main` release path.
5. Tag the release commit:

   ```bash
   git tag contracts-vX.Y.Z
   git push origin contracts-vX.Y.Z
   ```

6. GitLab CI runs `contracts_publish`, checks the tag with `scripts/check-contracts-publish-tag.mjs`, builds the package, and publishes it with `CI_JOB_TOKEN`.
7. GitLab CI then runs `contracts_desktop_compatibility`, which triggers the `dwdcc/ai-do-desktop` pipeline with `AI_DO_CONTRACTS_VERSION=contracts-vX.Y.Z`.

The publish job intentionally does not run on every branch push because package registries reject duplicate package versions.

## Consumer Flow

Consumers depend on exact versions:

```json
"@ai-do/contracts": "X.Y.Z"
```

For `dwdcc/ai-do-desktop`:

- `.npmrc` pins `@ai-do` to the `dwdcc/ai-do` GitLab npm registry.
- `pnpm-workspace.yaml` keeps `minimumReleaseAge` for public packages and excludes `@ai-do/contracts`, because GitLab's npm metadata can omit the `time` field pnpm needs for release-age checks.
- CI appends a temporary auth line to `.npmrc` using `CI_JOB_TOKEN`.
- `dwdcc/ai-do` job token inbound allowlist includes `dwdcc/ai-do-desktop`, so desktop CI can read the package registry without a personal token.

After bumping the consumer version:

```bash
pnpm install --lockfile-only
pnpm run ci
```

Local developer installs need GitLab registry auth outside the repository. Do not commit auth tokens.

```bash
npm config set @ai-do:registry http://128.1.253.101:8929/api/v4/projects/1/packages/npm/
npm config set //128.1.253.101:8929/api/v4/projects/1/packages/npm/:_authToken "$GITLAB_TOKEN"
```

## Rules

- Keep the monorepo as the contract source of truth.
- Keep split repositories as consumers.
- Use exact versions, not compatibility aliases or copied source.
- Do not deep-import package internals outside exported subpaths.
- Do not use public npm for AI-DO internal contracts.
- If a contract change breaks a consumer, fix the contract or consumer explicitly and publish a new version. Do not patch consumer aliases back to monorepo source paths.
