# Release Domain

- First development install and setup recovery: [Development Installation](../../../INSTALL.md).
- Environment-specific locale, browser, HTTPS, GitLab and Runner checks: [Installation operations](installation-operations.md).
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
- Initial sibling `dev`/`prod` checkout creation is documented in [installation §2.5](../../../INSTALL.md). Creating the `main` worktree does not configure production credentials, promote a release, or deploy; never copy the development `.env` into it.
- Keep `.env` aligned with `.env.example`; production preflight rejects dev login/seed flags, an unsafe attachment-signing key, an untrusted proxy wildcard, non-public or shared app/Bento origins, and host-port collisions.
- Route each public hostname directly from the external HTTPS proxy to its declared service port. `OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS` lists only the exact external proxy IPs. Bind Bento to loopback for a local proxy or the exact private proxy-facing IPv4 address; production rejects wildcard, public-IP, IPv6, and hostname bindings.
- The app image contains the web build, API, worker, migrations, and collaboration codec at one source revision. The Compose runtime starts the privacy filter, API, worker, and scheduler with restart policies and health checks.
- API and worker use redis-py 8.1.x. Its reentrant PubSub lock permits Celery result finalizers to unsubscribe during a subscription; the 5.3.1 lock can deadlock the scheduler. Keep both lockfiles aligned and run `apps/worker/tests/test_redis_pubsub_reentrancy.py` in both Python environments when changing Redis dependencies.
- OpenAI 3 and Anthropic 1 use HTTPX2. Keep OS CA certificates in the app image and suppress the `httpx2` request logger alongside `httpx` and `httpcore`; request URLs can contain credentials or user queries. Numeric SDK timeouts and the registered provider execution interface remain in use. Verify `apps/api/tests/test_logging_security.py` when changing HTTP clients.
- Ruff's explicit `E4`, `E7`, `E9`, and `F` selection preserves all pre-0.16 checks, including rules removed from the new defaults. Dependency upgrades must not silently replace the existing lint policy with a different upstream default set.
- Beat health requires a successful broker publication within 180 seconds. The official Celery `beat_init` and `after_task_publish` signals maintain a disposable `celerybeat-heartbeat` marker in Beat's working directory. Startup discards the previous marker; API and worker publications cannot refresh it. The marker stores no task or business data. Container health detects a stalled publisher after the freshness window and two failed 30-second checks; Docker restart policies alone do not restart an unhealthy process that is still running.
- The image build embeds the validated `OPEN_WORK_HUB_BENTO_SERVER_URL` in the static web bundle; changing that public origin requires a new app image.
- `pnpm app:prod:prepare --release-mr <iid>` verifies that the current `origin/main` is the named merged same-project `dev -> main` MR, that its current `release_validation` job passed, and that the validated source tree equals the production tree. It reuses a matching verified local candidate or builds it once from the committed Git snapshot, then prints its immutable image ID.
- `pnpm app:prod:deploy --release-mr <iid> --image sha256:<candidate-image-id>` rechecks the same GitLab, source-tree, platform, build-setting, image-label and runtime-content contract. It never builds an image. It rejects a terminal broker listener that is not the expected existing production container, promotes the exact candidate ID, applies migrations, replaces the app runtime, and requires direct and public health identity plus readiness, revision, bootstrap, and login-shell checks.
- Prepare, deploy and rollback are mutually exclusive host operations through a private runtime lock. Repeating prepare with the same commit, tree, platform and Bento URL verifies and returns the same candidate ID without building, including after a successful pipeline retry for the same source. A matching candidate that fails verification stops instead of rebuilding over the evidence.
- A failed migration, runtime start, or public smoke attempts to restore the previous app image and reports restoration failure explicitly. Default rollback retains the current database/configuration, so ordinary releases must keep them compatible with the previous image. Incompatible cutovers require the paired recovery procedure below.

Read-only checks:

```bash
pnpm app:prod:status
pnpm app:prod:smoke
```

Mutating commands require explicit production scope:

```bash
pnpm app:prod:prepare --release-mr <merged-dev-to-main-mr-iid>
pnpm app:prod:deploy --release-mr <same-mr-iid> --image 'sha256:<prepare-output>'
pnpm app:prod:rollback
pnpm app:prod:up
```

Run both release commands from the clean `prod` checkout after updating it to `origin/main`. The host needs an authenticated `glab` session for the internal GitLab project. Copy only the `sha256:...` line printed by prepare into deploy; tags are not accepted as deployment input.

## Incompatible database and configuration cutovers

A replacement Alembic baseline cannot upgrade an existing database from a deleted revision. Create a separate empty production database, apply the new baseline through the release's Alembic entrypoint, and retain the old database. Never stamp or clear the old schema to bypass this check. Isolate the new bucket, search index and vector collection prefixes, and Redis broker/result/collaboration/realtime namespaces so queued work and cleanup cannot affect retained data. Keep physical infrastructure identities unchanged unless separate instances are required.

Also assign a new [Hermes terminal resource namespace](../ai/hermes.md#terminal-isolation-and-retention) for a replacement database. Stop the previous namespace's active terminal runners without deleting their containers/volumes before cutover. The new database's empty session catalog must not reconcile the previous namespace as orphaned data.

Redis database numbers isolate stored keys and queues, [not Pub/Sub channels](https://redis.io/docs/latest/develop/pubsub/#database--scoping). The replacement uses new user/resource IDs and replaces the previous runtime; do not run a clone with retained IDs concurrently on the same Pub/Sub channels. Concurrent independent deployments require distinct channel prefixes or Redis instances. Preserve this distinction when checking namespace separation.

Before exposing an empty deployment, initialize its administrator through the new application model and role/audit services in an isolated process. For an authorized replacement, transfer only explicitly retained active, unblocked administrator login identity and password hashes; use new user IDs and copy no sessions, business data, groups, or app grants. Verify that public first-user setup is closed before starting the public runtime. Business apps remain disabled until an administrator enables them and configures their audiences.

An incompatible deployment must supply both options to the guarded entrypoint:

```bash
pnpm app:prod:deploy --release-mr <iid> --image 'sha256:<candidate-image-id>' --rollback-env-file /protected/path/previous.env --rollback-image 'sha256:<previous-image-id>'
pnpm app:prod:rollback --rollback-env-file /protected/path/previous.env --rollback-image 'sha256:<previous-image-id>'
```

The env backup must be a regular non-symlink file with mode 0600. The image must be immutable and match the current image before deploy or the previous image before manual rollback. Its full revision label must identify an available Git commit. Preflight snapshots that revision's `ops`, `scripts`, and `package.json` under the ignored, protected `.runtime/prod-app/rollback/` directory and validates the backup with the previous revision's config validator before build or migration.

Recovery stops only the production app Compose project without deleting volumes, atomically restores the root `.env` with mode 0600, and starts the immutable previous image using the previous revision's Compose and host-mounted helpers. The snapshot also contains its matching `.env`, because Compose's service `env_file` is resolved relative to its file. Recovery uses the previous revision's smoke validator and does not run migrations. Restoring a tag alone, or validating an old env with the new code's renamed keys, is insufficient. Keep the paired old database/namespaces and backup until the rollback retention decision is made; do not automatically delete them after a successful deployment. Snapshot restoration does not rewind shared persistent volumes or external side effects, which require separate compatibility review.

## Public runtime configuration

[`config/runtime.json`](../../../config/runtime.json) owns reviewed, non-secret API/Worker
startup defaults: database pools, LLM call timeouts, agent limits, retry/retention limits,
collaboration limits, and embedding/reranker model IDs and revisions. The versioned JSON
schema allowlists the supported typed `OPEN_WORK_HUB_*` keys and validates their ranges.
Missing files, unknown keys/profiles, duplicate JSON keys and invalid values fail startup;
validation errors do not print supplied values. `pnpm check:env-contract` validates this
document as well as the remaining env contract. Public config keys may be absent from
env files or appear as overrides; non-config key coverage/order and duplicate checks remain.
Sibling dev/prod checkouts are each checked against their own versioned template, typed
settings, public defaults and retired-key declaration. Different release versions may
therefore use different keys during a staged cutover; missing peer contracts and invalid
peer settings still fail validation. Source-token scanning covers the active checkout.
API and Worker Nx inputs include these files, so config-only edits invalidate their cached
checks. Runtime config and pool regressions run in the API/Worker contract test targets.

Settings precedence, highest first: explicit constructor values (tests), process environment,
checkout `.env`, Pydantic secret files when configured, selected `profiles` overrides,
`defaults`, typed code defaults. `OPEN_WORK_HUB_ENV_PROFILE` selects `local`, `dev`, `prod`,
`preview` or `test`; `development`/`production` map to `dev`/`prod`. With no profile, `local`
applies. Settings are cached per process; changes require its normal restart.

Credentials, signing/encryption keys, DSNs, site endpoints/namespaces, feature admission
and Hermes settings remain in protected env configuration. Active generative provider/model
and workload routing remain authoritative in the Admin database; see [AI Gateway](../ai/gateway.md).
Embedding-model changes still require the retrieval owner's index/version migration contract.
Do not copy real env values into Git or add an unused model-preset file.

Existing installations can run `uv run --frozen --python 3.12 --directory apps/api python
../../scripts/runtime-config-migrate.py` from their checkout root. The default is a dry run;
`--apply` atomically removes only public values equal to that profile's defaults, retains
custom overrides and interpolation dependencies, and creates a mode-0600 `.env.backup-config-*`
recovery copy. The tool rejects tracked/symlink/non-0600 files, duplicate keys and changes to
unrelated multiline values. Review `.env.local` overlays separately. Protect backups like the
original env file; they are ignored by Git and Docker.

The application image contains both `config/runtime.json` and its schema. Deployment and
rollback therefore use the config from the corresponding immutable image. Production env
overrides remain compatible with the previous image; prune them only after the matching
code/config has been promoted and deployed. Config/env edits do not authorize promotion,
deployment or restart. Do not bind-mount a newer config over a rollback image.

## Database connection budgets

PostgreSQL's connection limit belongs to the physical server, including when development
and production use different databases on it. Budget every API process and Celery child,
plus migration/operator capacity, below the server's non-reserved connection limit.

| Runtime | Retained connections per process | Extra concurrent connections | Settings |
| --- | --- | --- | --- |
| API | 5 | 5 | `OPEN_WORK_HUB_API_DB_POOL_SIZE`, `OPEN_WORK_HUB_API_DB_MAX_OVERFLOW` |
| Worker child | 1 | 2 | `OPEN_WORK_HUB_WORKER_DB_POOL_SIZE`, `OPEN_WORK_HUB_WORKER_DB_MAX_OVERFLOW` |

Both `OPEN_WORK_HUB_API_DB_POOL_TIMEOUT` and `OPEN_WORK_HUB_WORKER_DB_POOL_TIMEOUT`
default to 45 seconds. These are lazy pool limits, not connections opened at startup.
For example, two API processes and eighteen worker children have a combined maximum
of `2 × (5 + 5) + 18 × (1 + 2) = 74` connections, retaining at most 28 after work finishes.
Additional processes/replicas and configuration overrides change that budget.

Worker startup binds API-domain database access to the same worker engine; mail, search,
media cleanup and shared worker tasks reuse it. Prefork children replace the inherited
pool with SQLAlchemy's `Engine.dispose(close=False)` through Celery's
`worker_process_init` signal. Existing session factories retain their engine binding.
The [SQLAlchemy pooling contract](https://docs.sqlalchemy.org/en/20/core/pooling.html)
owns connection retention, overflow closure, rollback-on-return and fork isolation.
Do not create a task-local engine, or use `pool_size=0` to disable pooling: zero removes
the pool size limit. SQLAlchemy's `NullPool` is the explicit no-pooling option.

`Session.close()` returns a connection to its pool; PostgreSQL `idle` alone is not proof
of a leaked session. Beat still runs maintenance every 30–60 seconds without users.
Inspect `pg_stat_activity` grouped by `application_name`, `state` and database/role,
excluding query text and business data. Clients identify themselves as
`owh:<environment>:api` or `owh:<environment>:worker`. Repeated empty maintenance cycles
must not grow the retained connection count. Investigate persistent `idle in transaction`
separately, and never terminate arbitrary connections to conceal a leak.

Authentication runs its synchronous database work through an application-scoped
[AnyIO `CapacityLimiter`](https://anyio.readthedocs.io/en/stable/threads.html), separate from the default request-thread limiter. Its
capacity is the existing API pool size plus overflow; it does not increase the
database connection budget. This keeps blocked authentication checkouts from
occupying every thread needed by authenticated requests to finish and return
their connections. Use AnyIO's public `to_thread.run_sync(..., limiter=...)`
interface; keep cancellation shielding enabled so a request cannot close a
session while its authentication thread still uses it. A larger database pool
or thread count does not fix this dependency scheduling cycle.

Verify concurrent authenticated reads with
`uv run --directory apps/api --group dev pytest tests/test_database_request_concurrency.py`.
The regression uses a smaller connection pool than the request-thread budget,
exercises real authentication and app admission, and checks connection return.
Long-lived streams must also release admission-only read transactions before
opening the stream; each later database poll owns a short session.

For existing installations, explicitly review the pool keys in each protected `.env`:
old API values of 32/64 override the new defaults. Apply reviewed values through the
development supervisor or the guarded production deployment procedure with the required
authorization; editing defaults does not update running workers or production images.
After rollout, verify connection counts over several Beat cycles and authenticated API
requests. No database recreation or PostgreSQL capacity increase is required by this change.

## Persistent development runtime

`dev.sh` is a foreground development command: its children stop when its session exits. A continuously available development address requires an independent host supervisor with restart-on-exit and persistent logs, using the same entrypoint, selected flags and checkout. For native minimal installation this is `./dev.sh --minimal-infra --no-infra`; use `./dev.sh --with-worker` when the selected configuration includes a worker. Manage that runtime through its supervisor instead of starting a second copy or stopping its children directly. Keep host-specific service definitions outside the repository.

Worker concurrency is the typed `OPEN_WORK_HUB_WORKER_CONCURRENCY` setting in `config/runtime.json` (default `1`, range `1..64`). Both development and the released production worker use Celery's public `worker_concurrency` configuration; the standard commands must not override it with a separate CLI count. One prefork child is the minimum for the demo deployment; the worker supervisor and single Beat scheduler remain required, and queued tasks run sequentially. CPU-count auto-detection is unsuitable for shared LXC hosts, where Python may see more CPUs than the process affinity allows. Include every child in the database and memory budgets. Raising concurrency requires a memory/throughput budget and worker restart. A source configuration change reaches production through the normal release image; Celery's targeted `pool_shrink` can reduce idle processes immediately, but is temporary and does not survive worker restart.

After startup, reboot or recovery, follow the shared [development access checks](installation-operations.md#development-access-checks): verify local listeners and API readiness, then use `pnpm dev:login-smoke` plus browser login, screens and logout for HTTP development access. `pnpm dev:public-smoke` remains required for an HTTPS public-domain development origin; it rejects HTTP and IP-address origins, including HTTPS IP addresses. Remote-PC installations also require a separate client-path browser check. INSTALL uses the same conditions; a server checking its own address does not establish client reachability.

## Build and test storage

`scripts/docker-storage.mjs` owns project image retention and capacity preflight. Before building a validation image or when production candidate preparation needs a new image, run `node scripts/docker-storage.mjs check` against the local Docker daemon. Require at least 15 GiB **and** 15% available on its filesystem; these are conservative minimums, not a guarantee that an arbitrary build fits. Reusing an already matching candidate does not require build headroom. Release CI checks its workspace filesystem before launching suites and records a failed preflight without running them. If CI services use another filesystem/host, inspect that storage at its owner too. Do not disable OpenSearch disk watermarks or index-creation protection to make tests pass.

Harness fixtures also run capacity checks on their temporary workspaces. If the default temporary directory is a small tmpfs, set `TMPDIR` to an ignored, owner-only directory on a filesystem that satisfies the same capacity threshold before running `pnpm ci:harness`. Check that filesystem's free space; do not lower the threshold or bypass preflight. For console tests, temporary attachment directories must also be outside every Git checkout; do not reuse a repository-local harness `TMPDIR` for `ci:codex-console`.

An explicitly authorized production deploy applies retention after successful public smoke. It does not clean before promotion, so the explicitly selected candidate ID cannot be retired between verification and tagging. `node scripts/docker-storage.mjs cleanup` is a read-only plan; `cleanup --apply` requires deploy or project artifact-cleanup scope. It removes recognized generated app/validation image tags and untagged validation images with a valid `io.open-work-hub.validation.contract` label older than 48 hours, preserving the prepared candidate, current production, its previous rollback image, the canonical CI image, every container-referenced image (including stopped containers), recent builds and unknown/manual tags. Each image is rechecked before non-force removal. Docker's own dangling-image pruning is restricted to positive project build-cache/app labels and the same age threshold. It never prunes volumes, containers, other projects, or the Docker daemon globally. Cleanup failure is reported; it does not roll back a healthy deployment.

Production and validation Dockerfile revision/contract metadata follows the dependency layers so a new commit or builder-script change does not reinstall heavy dependencies. Production copies third-party Python environments before installing the small API/worker wheels; application source changes reuse the dependency layers. The collaboration codec deployment also precedes the web source copy, avoiding a new dependency layer for each UI or documentation change. Build stages have a project cache label; the final runtime does not inherit the cache label. Python installs use `uv --no-cache`; do not retain package downloads alongside installed environments. The Docker context excludes local runtime, Beat state and browser test reports. Failed test evidence remains governed by CI artifact expiry; do not add local copies of every run.

Production candidate preparation sends `git archive HEAD`, rather than the working directory, as Docker's build context. The reusable candidate contract covers the full production commit, its Git tree, the validated release source, Docker platform, and a hash of the normalized Bento public URL. Image labels also record the release MR and the successful pipeline used at build time. A later successful pipeline retry for the same source is checked live without changing the image contract. Deployment accepts only the full local image ID and repeats the contract and content checks; it does not call `docker build`. Promoting an image already serving as current production leaves `prod-previous` unchanged.

CI preparation links both ordinary `apps/{api,worker}/.venv` and focused `.runtime/ci-*-venv` paths to the same hash-verified image environments. Normal `uv run` still installs the current source package; do not skip dependency identity checks or redirect API and worker into one shared environment. Missing/mismatched identity or an existing foreign environment fails closed without overwriting it. This avoids downloading/installing the full dependency tree again during each full suite. Test with `node --test scripts/prepare-validation-runtime.test.mjs` and confirm an actual CI run does not recreate a multi-gigabyte uv cache.

The full release job bounds API pytest to two processes and Vitest/Playwright to one worker each through their supported environment settings. Test selection, full-suite routing and failure gates remain unchanged. This avoids unbounded CPU-count concurrency exhausting memory on a runner that shares resources with services. Do not overlap a production image build with the full release suites on a constrained runner.

Release CI and the production web image build set Node's [V8 old-space limit](https://nodejs.org/download/release/v22.18.0/docs/api/cli.html#--max-old-space-sizesize-in-mib) to 3072 MiB. A 2048 MiB uncached build exhausted its heap; 3072 MiB completed. This is not a total process or container memory limit: native allocations, child processes and test services need additional capacity. Check the host's effective cgroup limit/events and available memory before resource-heavy validation; missing kernel journal access does not establish that no OOM occurred. On this shared host, temporarily pause development services during authorized release maintenance if needed, leave production serving, and restore development with the applicable [development access checks](installation-operations.md#development-access-checks) afterwards. Do not rely on a larger per-job limit to reserve memory from other services.

Release CI preserves Playwright's existing failure traces, videos, and error context under `test-results/` together with the validation context artifact, restricted to maintainers and expiring after 14 days. These shell tests use synthetic API fixtures. Do not archive runtime `.env` files or production browser sessions. A browser process crash is a failed check; retain its evidence and reproduce with the same image and resource settings before changing UI assertions, timeouts, or retry policy.

Do not export Docker tar backups for reproducible builds/test images. Preserve the current and previous runtime tags for image rollback; back up persistent business data only through its separately authorized data-retention policy. Image sizes share layers: compare filesystem free space before/after cleanup rather than summing `docker image ls` sizes. Verify current/previous image IDs and runtime health remain unchanged after maintenance. Run `pnpm test:prod-app`, `node --test scripts/release-validation.test.mjs`, and the release pipeline when changing these controls.

Image cleanup and BuildKit cache cleanup are separate: `docker image prune` does not bound BuildKit storage. Inspect `docker buildx du` and `docker buildx inspect` when filesystem usage keeps growing after image retirement. Prefer Docker's native [BuildKit garbage collection](https://docs.docker.com/build/cache/garbage-collection/) with an explicitly budgeted `builder.gc.defaultKeepStorage` on a project-owned daemon; inspect other owners before changing a shared daemon. A build cache is reproducible and is not a rollback backup. Never create tar copies before removing it. On a shared builder, identify exact unused project cache IDs and recheck ownership/reference state before targeted removal; descriptions alone do not establish ownership. For a small project-owned host, merge `"builder": {"gc": {"enabled": true, "defaultKeepStorage": "8GB"}}` into the existing daemon configuration, preserving runtime/network settings; larger caches need an explicit disk budget. This is a GC target, not a hard cap during a build, and it does not remove tagged runtime images or data volumes. Validate with `dockerd --validate --config-file /etc/docker/daemon.json`. Builder GC changes require a daemon restart on Docker 29; where supported, first enable/reload `live-restore`, verify `docker info` reports it active, then restart during authorized maintenance and verify existing container PIDs, images and health. Confirm the effective budget with `docker buildx inspect`; a saved configuration alone is not evidence that GC changed.

Do not create a full product Docker image merely to release the independent Codex Console: use its [release builder](../../apps/codex-console/README.md#배포-완료-확인). Verify the prepared product candidate directly; do not create a second `verify-*` copy. Product release validation remains required when its own image/runtime changes.

Official behavior: [Docker cache invalidation](https://docs.docker.com/reference/dockerfile/#impact-on-build-caching), [uv Docker caching](https://docs.astral.sh/uv/guides/integration/docker/#caching), [positive-label image pruning](https://docs.docker.com/reference/cli/docker/image/prune/).

## Validation image platform and database

Build from an approved source revision with `scripts/build-ci-validation-image.sh --postgres-major <installed-project-server-major>`. Read the actual project server's `server_version_num`, rather than the host client's version, and provision the CI database on the same major. PostgreSQL has no hardcoded default in this builder. Existing GitLab or production databases are never upgraded as part of image preparation. Host Node/Python versions do not override their pinned image toolchains.

The builder resolves the official `postgres:<major>-bookworm` tag through [Docker Buildx imagetools](https://docs.docker.com/reference/cli/docker/buildx/imagetools/inspect/) and passes its immutable manifest digest as `POSTGRES_CLIENT_IMAGE`, together with `POSTGRES_MAJOR`. A recorded `--postgres-client-image postgres@sha256:<digest>` reproduces the selected base without resolving a moving tag. Missing releases or mismatched client binaries fail the build; never fall back to an older server to satisfy an image.

The image contract includes the Dockerfile, builder, Node/API/worker dependency hashes, selected PostgreSQL major/digest, and platform. A matching local image is verified again and reused; changed inputs trigger a build using Docker's layer cache. Every verification checks client versions, stored dependency identities, native Nx execution and Chromium launch. The PostgreSQL major is stored alongside the API dependency identity. Record the resolved inputs in setup evidence; image labels also retain the contract hash, major and PostgreSQL base digest. `--print-contract` reports source/dependency hashes without Docker; PostgreSQL selection/platform fields remain empty unless explicitly supplied in that mode.

- Use the expected CI image name on the validation Runner's Docker daemon. The default platform is that daemon's Linux AMD64/ARM64 platform; `--platform linux/arm64` or `--platform linux/amd64` explicitly selects another. The official PostgreSQL manifest resolves the matching architecture during build.
- Keep the existing `NODE_IMAGE` and `UV_IMAGE` pins and all dependency checks. Unsupported base-image platforms or failed native/emulated execution remain failures. A successful manifest lookup alone does not establish platform compatibility.
- From the resulting image and Runner network, verify GitLab TLS trust and authenticated CI DB access. `release_validation` runs `prepare-validation-runtime.sh --postgres` before application tests: image identity, all three PostgreSQL client majors and the connected CI server major must match. Missing DB configuration, old images without identity, connection failures and mismatches fail closed without printing credentials. Contract-package publication uses the ordinary preparation mode and needs no DB.

Use a dedicated non-production CI database and login role with `CREATEDB`, without superuser or role-creation privileges; the suites create and drop test databases. It may share the project's non-production PostgreSQL instance when ownership and network/HBA access prevent access to development business databases. If stronger isolation requires a separate cluster, use the same major and separate data/port/account. GitLab's bundled database and production databases are excluded. See [installation and CI variables](../../../INSTALL.md#226-ci-변수-등록과-실제-실행-확인) for wiring.

On a dedicated CI cluster, the database administrator must install `vector` in `template1` before running the suites (`psql -d template1 -c 'CREATE EXTENSION IF NOT EXISTS vector'`). The fixtures create databases from that template; a remote non-superuser cannot install pgvector itself, and the native administrator fallback only supports loopback connections. Verify a disposable database created by the CI role inherits the extension. Do not grant CI superuser privileges to bypass this prerequisite, or change a shared cluster's template without its owner's approval.

These are application regression tests: migrations, database-backed APIs and authorization remain covered. `pg_dump`/`pg_restore` restore the test seed baseline between cases; [`pg_dump` cannot dump a newer server major](https://www.postgresql.org/docs/current/app-pgdump.html#APP-PGDUMP-NOTES). Initial setup verifies connections, migrations, seed login and a real development MR pipeline; full regression execution retains its existing `dev -> main` release routing. Image preparation does not authorize a release MR or remove any tests.

Validation: `node --test scripts/build-ci-validation-image.test.mjs scripts/prepare-validation-runtime.test.mjs`, `pnpm check:gitlab-pipeline`, `pnpm ci:harness`, `pnpm check:env-contract`, `pnpm check:path-hardcoding`, and `git diff --check`. Changes to this image also require an actual image build/verification and release pipeline before release; report unavailable Docker/CI checks explicitly.
