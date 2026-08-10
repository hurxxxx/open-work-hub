# Shared Contracts Package

`@open-alm/contracts` is the public package boundary for TypeScript/JSON contracts shared outside the `open-alm/open-alm` monorepo.

## Ownership

- Source of truth: `open-alm/open-alm`
- Package source: `packages/contracts`
- Package name: `@open-alm/contracts`
- Registry: GitLab npm Package Registry for `open-alm/open-alm`
- Registry URL: `http://128.1.253.101:8929/api/v4/projects/1/packages/npm/`
- Source version: `packages/contracts/package.json`에서 확인
- Published versions: GitLab npm Package Registry에서 확인
- First external consumer: `open-alm/open-alm-desktop`

Do not publish this package to public npm. Do not copy `packages/contracts` into split repositories. Split repositories consume exact package versions from the GitLab registry.

## Exports

The package publishes compiled ESM and declaration files from `dist/`.

- `@open-alm/contracts`
- `@open-alm/contracts/api`
- `@open-alm/contracts/auth`
- `@open-alm/contracts/open-alm-desktop-update-feed`
- `@open-alm/contracts/open-alm-desktop-update-feed.manifest.json`
- `@open-alm/contracts/openapi`
- `@open-alm/contracts/dm`
- `@open-alm/contracts/notifications`
- `@open-alm/contracts/realtime`

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
7. GitLab CI then runs `contracts_desktop_compatibility`, which triggers the `open-alm/open-alm-desktop` pipeline with `OPEN_ALM_CONTRACTS_VERSION=contracts-vX.Y.Z`.

The publish job intentionally does not run on every branch push because package registries reject duplicate package versions.

## Consumer Flow

Consumers depend on exact versions:

```json
"@open-alm/contracts": "X.Y.Z"
```

For `open-alm/open-alm-desktop`:

- `.npmrc` pins `@open-alm` to the `open-alm/open-alm` GitLab npm registry.
- `pnpm-workspace.yaml` keeps `minimumReleaseAge` for public packages and excludes `@open-alm/contracts`, because GitLab's npm metadata can omit the `time` field pnpm needs for release-age checks.
- CI appends a temporary auth line to `.npmrc` using `CI_JOB_TOKEN`.
- `open-alm/open-alm` job token inbound allowlist includes `open-alm/open-alm-desktop`, so desktop CI can read the package registry without a personal token.

After bumping the consumer version:

```bash
pnpm install --lockfile-only
pnpm run ci
```

Local developer installs need GitLab registry auth outside the repository. Do not commit auth tokens.

```bash
npm config set @open-alm:registry http://128.1.253.101:8929/api/v4/projects/1/packages/npm/
npm config set //128.1.253.101:8929/api/v4/projects/1/packages/npm/:_authToken "$GITLAB_TOKEN"
```

## Rules

- Keep the monorepo as the contract source of truth.
- Keep split repositories as consumers.
- Use exact versions, not compatibility aliases or copied source.
- Do not deep-import package internals outside exported subpaths.
- Do not use public npm for Open ALM internal contracts.
- If a contract change breaks a consumer, fix the contract or consumer explicitly and publish a new version. Do not patch consumer aliases back to monorepo source paths.
