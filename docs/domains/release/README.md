# Release Domain

- Dev infra: `ops/compose/open-work-hub-dev.infra.yml`.
- Prod infra: `ops/compose/open-work-hub-prod.infra.yml`.
- Common entrypoint: `scripts/infra-stack.sh`.
- Immutable production app image: `ops/app/Dockerfile`.
- Production app runtime: `ops/compose/open-work-hub-prod.app.yml`.
- Guarded app entrypoint: `scripts/prod-app.sh`.
- CI contract: `.gitlab-ci.yml` and `ops/ci/ci-first.gitlab-ci.yml`.
- Branch, release, and deployment authorization: root `AGENTS.md`.
- Prefer shared physical infra plus isolated data namespaces when services support it: PostgreSQL database/schema, MinIO bucket/prefix, OpenSearch index prefix, Qdrant collection prefix, Redis DB/key prefix, queue name/group.
- Use env-named service instances only for incompatible lifecycle, security, capacity, or blast-radius requirements. `prod` checkout/branch is an operational guard, not a naming rule for every container.
- Contract package publish: `contracts-v*` tag publishes `@open-work-hub/contracts`.
- Do not document server/user/systemd/internal-network-specific deployment in repo source.
- GitLab `origin/main` is the production source; CI owns release-validation routing.

## Impact-based release validation

`release_validation` defaults to `pnpm ci:all`. Only an explicit user request for simplified, urgent, or fast validation enables consideration of the fast lane; the request is not permission to omit relevant checks, merge, or deploy. The agent interprets intent and records the opt-in below. No hook or CI script scans natural-language prompts for authorization.

`scripts/release-validation.mjs` owns deterministic selection. It compares the complete current target/source trees, including deletions and both sides of renames, and requires the tested tree to equal the merge result. It does not classify only the last commit or ignore pending app changes elsewhere in the release.

| Diff | Fast-request outcome |
| --- | --- |
| Known Markdown docs/instructions only | Whitespace, skills checker, skill-harness and Claude bridge tests; omit application suites |
| Skills, native agent setup/hooks, tested Codex review tooling | Whitespace and `pnpm ci:harness`; omit API, generated contract, web build/test and browser E2E suites |
| App/test code, dependencies/lockfiles, DB, env, dev/runtime startup, Compose, images, release selector/CI routing/gates, or unknown paths | Full `pnpm ci:all` |
| More than 40 files or 1,000 added/deleted lines; binary, symlink/submodule or mode changes | Full `pnpm ci:all` |

The size limits are conservative routing policy, not measured correctness thresholds. The executable allowlist is narrow: a `.sh`, `.yml`, or “setup/CI” name alone does not prove low impact. Release-control changes, including introducing this selector, cannot choose their own abbreviated validation.

For an authorized release with an explicit fast request:

1. Inspect dirty work separately; include only authorized changes. Commit/push only when authorized, then refresh `origin/dev` and `origin/main`.
2. Preview the **committed** release snapshots (this read-only command does not include dirty/untracked files):

   ```bash
   node scripts/release-validation.mjs plan --base origin/main --head origin/dev --mode fast
   ```

3. In the authorized `dev -> main` MR, place the emitted marker on the first line of its description, then state the user's opt-in, purpose, affected checks, and remaining risks. Use the full SHAs emitted by the command:

   ```text
   <!-- open-work-hub:release-validation:v1 mode=fast source=<full-dev-sha> target=<full-main-sha> -->
   ```

4. Create a fresh MR pipeline after updating the description. Missing, malformed, duplicated, stale or truncated opt-in metadata selects full validation. Do not assume retrying an old job refreshes pipeline metadata. Only detached same-project release pipelines can select fast; other release event types keep full validation.
5. Require successful `release_validation` for the latest source/target pair and recheck those refs before merge. CI refreshes both refs before and after checks and fails on stale source/target or merge-tree mismatch. Its maintainer-only `release-validation-context.md` artifact records immutable identities, selected mode, reasons, commands, results and skipped suites. A pending/failed artifact is not release evidence.

The marker uses GitLab's [predefined MR description snapshot](https://docs.gitlab.com/ci/variables/predefined_variables/#predefined-variables-for-merge-request-pipelines), which can be truncated. Keep fast-request metadata concise; never override predefined variables to force selection. The marker records workflow intent, not an independent authentication or approval boundary; protected branches and existing merge/deploy authority still apply.

CI image/dependency identity, pipeline/target checks, resource serialization and `allow_failure: false` remain enabled. The current single job still starts its test services; fast mode saves application suite execution, not service startup. Do not claim a measured speedup until comparable CI runs exist. Production image build/verification, env preflight, migration, revision identity, rollback and direct/public smoke are unchanged; do not skip these by calling Compose directly. An env-only deployment still requires its normal runtime checks even if there is no tracked app diff.

Selector maintenance checks: `node --test scripts/release-validation.test.mjs`, `pnpm test:gitlab-pipeline`, `pnpm ci:harness`, and `git diff --check`. Tests use disposable repositories and stand-in commands; they do not deploy or replace real release evidence.

## Production app contract

- Run app commands only from a clean checkout named `prod` at `origin/main`.
- Keep `.env` aligned with `.env.example`; production preflight rejects dev login/seed flags, an unsafe attachment-signing key, an untrusted proxy wildcard, non-public or shared app/Bento origins, and host-port collisions.
- Route each public hostname directly from the external HTTPS proxy to its declared service port. `OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS` lists only the exact external proxy IPs. Bind Bento to loopback for a local proxy or the exact private proxy-facing IPv4 address; production rejects wildcard, public-IP, IPv6, and hostname bindings.
- The app image contains the web build, API, worker, migrations, and collaboration codec at one source revision. The Compose runtime starts the privacy filter, API, worker, and scheduler with restart policies and health checks.
- API and worker use redis-py 6.4.x. Its reentrant PubSub lock permits Celery result finalizers to unsubscribe during a subscription; the 5.3.1 lock can deadlock the scheduler. Keep both lockfiles aligned and run `apps/worker/tests/test_redis_pubsub_reentrancy.py` in both Python environments when changing Redis dependencies.
- Beat health requires a successful broker publication within 180 seconds. The official Celery `beat_init` and `after_task_publish` signals maintain a disposable `celerybeat-heartbeat` marker in Beat's working directory. Startup discards the previous marker; API and worker publications cannot refresh it. The marker stores no task or business data. Container health detects a stalled publisher after the freshness window and two failed 30-second checks; Docker restart policies alone do not restart an unhealthy process that is still running.
- The image build embeds the validated `OPEN_WORK_HUB_BENTO_SERVER_URL` in the static web bundle; changing that public origin requires a new app image.
- `pnpm app:prod:deploy` first rejects a terminal broker listener that is not the expected existing production container, then builds and verifies the revision image, applies migrations, replaces the app runtime, and requires direct and public health identity plus readiness, revision, bootstrap, and login-shell checks.
- A failed runtime or public smoke restores the previous app image when one exists. Database migrations are not automatically reversed; releases must keep migrations backward-compatible with the previous image.

Read-only checks:

```bash
pnpm app:prod:status
pnpm app:prod:smoke
```

Mutating commands require explicit production scope:

```bash
pnpm app:prod:deploy
pnpm app:prod:rollback
pnpm app:prod:up
```

## Persistent development runtime

`./dev.sh --with-worker` is a foreground development command: its children stop when its session exits. A continuously available development domain requires an independent host supervisor with restart-on-exit and persistent logs, using the same entrypoint and checkout. Manage that runtime through its supervisor instead of starting a second copy or stopping its children directly. Development workers use two concurrent processes to bound their memory use on a host shared with other environments. Keep host-specific service definitions outside the repository. Validate local listeners and the public domain with `pnpm dev:public-smoke` after startup or recovery.

## Build and test storage

`scripts/docker-storage.mjs` owns project image retention and capacity preflight. Before building a validation image or starting an app build, run `node scripts/docker-storage.mjs check` against the local Docker daemon. Require at least 15 GiB **and** 15% available on its filesystem; these are conservative minimums, not a guarantee that an arbitrary build fits. Release CI checks its workspace filesystem before launching suites and records a failed preflight without running them. If CI services use another filesystem/host, inspect that storage at its owner too. Do not disable OpenSearch disk watermarks or index-creation protection to make tests pass.

An explicitly authorized production deploy applies retention before building and again after successful public smoke. `node scripts/docker-storage.mjs cleanup` is a read-only plan; `cleanup --apply` requires deploy or project artifact-cleanup scope. It removes only recognized generated app/validation image tags older than 48 hours, preserving current production, its previous rollback image, the canonical CI image, every container-referenced image (including stopped containers), recent builds and unknown/manual tags. Each image is rechecked before non-force removal. Docker's own dangling-image pruning is restricted to positive project build-cache/app labels and the same age threshold. It never prunes volumes, containers, other projects, or the Docker daemon globally. Cleanup failure is reported; it does not roll back a healthy deployment.

Production Dockerfile revision metadata follows the dependency layers so a new commit does not invalidate heavy dependency copies. Build stages have a project cache label; the final runtime does not inherit the cache label. Python installs use `uv --no-cache`; do not retain package downloads alongside installed environments. The Docker context excludes local runtime, Beat state and browser test reports. Failed test evidence remains governed by CI artifact expiry; do not add local copies of every run.

CI preparation links both ordinary `apps/{api,worker}/.venv` and focused `.runtime/ci-*-venv` paths to the same hash-verified image environments. Normal `uv run` still installs the current source package; do not skip dependency identity checks or redirect API and worker into one shared environment. Missing/mismatched identity or an existing foreign environment fails closed without overwriting it. This avoids downloading/installing the full dependency tree again during each full suite. Test with `node --test scripts/prepare-validation-runtime.test.mjs` and confirm an actual CI run does not recreate a multi-gigabyte uv cache.

Do not export Docker tar backups for reproducible builds/test images. Preserve the current and previous runtime tags for image rollback; back up persistent business data only through its separately authorized data-retention policy. Image sizes share layers: compare filesystem free space before/after cleanup rather than summing `docker image ls` sizes. Verify current/previous image IDs and runtime health remain unchanged after maintenance. Run `pnpm test:prod-app`, `node --test scripts/release-validation.test.mjs`, and the release pipeline when changing these controls.

Official behavior: [Docker cache invalidation](https://docs.docker.com/reference/dockerfile/#impact-on-build-caching), [uv Docker caching](https://docs.astral.sh/uv/guides/integration/docker/#caching), [positive-label image pruning](https://docs.docker.com/reference/cli/docker/image/prune/).
