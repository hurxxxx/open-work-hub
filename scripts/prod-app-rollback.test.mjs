import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import {
  chmodSync,
  existsSync,
  mkdtempSync,
  mkdirSync,
  readFileSync,
  readdirSync,
  rmSync,
  statSync,
  symlinkSync,
  writeFileSync,
} from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  prepareRollbackBundle,
  restoreRollbackEnvironment,
} from './prod-app-rollback.mjs';

const IMAGE = `sha256:${'a'.repeat(64)}`;
const OTHER = `sha256:${'b'.repeat(64)}`;
const PREVIOUS_ENV = 'DATABASE=old_database\nPREVIOUS_CONTRACT=required\n';
const CANDIDATE_ENV = 'DATABASE=new_database\n';
const script = readFileSync(new URL('./prod-app.sh', import.meta.url), 'utf8');
const helper = fileURLToPath(
  new URL('./prod-app-rollback.mjs', import.meta.url),
);
const shellQuote = (value) => `'${value.replaceAll("'", "'\\''")}'`;

function fixture(t, { symlink = false } = {}) {
  const directory = mkdtempSync(
    path.join(os.tmpdir(), 'owh-prod-rollback-test-'),
  );
  t.after(() => rmSync(directory, { recursive: true, force: true }));
  const rootDir = path.join(directory, 'prod');
  mkdirSync(rootDir);
  const files = {
    'ops/compose/open-work-hub-prod.app.yml':
      'services:\n  api:\n    image: open-work-hub-app:prod\n    env_file: [../../.env]\n',
    'ops/hermes/bootstrap.py': '# previous helper\n',
    'scripts/prod-app-config.mjs': `import {readFileSync} from 'node:fs';\nif (!readFileSync(process.argv[2], 'utf8').includes('PREVIOUS_CONTRACT=required')) { console.error('synthetic-sensitive-environment'); process.exit(1); }\n`,
    'scripts/prod-app-smoke.mjs': '// previous smoke\n',
    'package.json': '{"type":"module"}\n',
  };
  for (const [relative, content] of Object.entries(files)) {
    mkdirSync(path.dirname(path.join(rootDir, relative)), { recursive: true });
    writeFileSync(path.join(rootDir, relative), content);
  }
  if (symlink)
    symlinkSync(
      '/unrelated-host-location',
      path.join(rootDir, 'ops/hermes/link'),
    );
  const git = (...args) =>
    execFileSync('git', ['-C', rootDir, ...args], {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  git('init', '-q');
  git('add', 'ops', 'scripts', 'package.json');
  git(
    '-c',
    'user.name=Rollback Test',
    '-c',
    'user.email=rollback@example.test',
    'commit',
    '-qm',
    'previous deployment assets',
  );
  const revision = git('rev-parse', 'HEAD');
  writeFileSync(
    path.join(rootDir, 'ops/hermes/bootstrap.py'),
    '# candidate helper\n',
  );
  writeFileSync(
    path.join(rootDir, 'scripts/prod-app-config.mjs'),
    'throw new Error("candidate validator must not run for previous environment");\n',
  );
  writeFileSync(path.join(rootDir, '.env'), CANDIDATE_ENV, { mode: 0o600 });
  const envFile = path.join(directory, 'previous.env');
  writeFileSync(envFile, PREVIOUS_ENV, { mode: 0o600 });
  const calls = [];
  const run = (command, args) => {
    calls.push([command, ...args]);
    if (command === 'docker') return args[3] === '{{.Id}}' ? IMAGE : revision;
    return execFileSync(command, args, {
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  };
  const options = {
    rootDir,
    envFile,
    image: IMAGE,
    expectedImage: 'open-work-hub-app:prod',
  };
  return { rootDir, envFile, revision, run, options, calls, directory };
}

function prepared(t) {
  const f = fixture(t);
  return { ...f, bundle: prepareRollbackBundle(f.options, { run: f.run }) };
}

test('pins environment and exact Git deployment assets before any runtime change', (t) => {
  const f = prepared(t);
  assert.equal(statSync(f.bundle).mode & 0o777, 0o700);
  assert.equal(statSync(path.join(f.bundle, '.env')).mode & 0o777, 0o600);
  assert.equal(readFileSync(path.join(f.bundle, '.env'), 'utf8'), PREVIOUS_ENV);
  assert.equal(
    readFileSync(path.join(f.bundle, 'ops/hermes/bootstrap.py'), 'utf8'),
    '# previous helper\n',
  );
  assert.equal(
    readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
    CANDIDATE_ENV,
  );
  assert.ok(
    f.calls.some(
      (call) =>
        call[0] === 'git' &&
        call.includes('archive') &&
        call.includes(f.revision),
    ),
  );
  assert.equal(
    f.calls
      .filter((call) => call[0] === 'docker')
      .every((call) => call[1] === 'image' && call[2] === 'inspect'),
    true,
  );
  assert.ok(
    f.calls.some(
      (call) =>
        call[0] === 'node' &&
        call[1] === path.join(f.bundle, 'scripts/prod-app-config.mjs'),
    ),
  );
});

for (const invalid of [
  'mutable-tag',
  'wrong-image',
  'wrong-expected-image',
  'bad-revision',
  'missing-commit',
]) {
  test(`rejects ${invalid} before producing a rollback bundle`, (t) => {
    const f = fixture(t);
    const run = (command, args) => {
      if (command === 'docker') {
        if (args[3] === '{{.Id}}') {
          if (invalid === 'wrong-image' && args.at(-1) === IMAGE) return OTHER;
          if (
            invalid === 'wrong-expected-image' &&
            args.at(-1) === f.options.expectedImage
          )
            return OTHER;
          return IMAGE;
        }
        return invalid === 'bad-revision' ? 'unmanaged' : f.revision;
      }
      if (invalid === 'missing-commit' && command === 'git')
        throw new Error('missing');
      return f.run(command, args);
    };
    assert.throws(() =>
      prepareRollbackBundle(
        {
          ...f.options,
          image: invalid === 'mutable-tag' ? 'open-work-hub-app:prod' : IMAGE,
        },
        { run },
      ),
    );
    assert.equal(existsSync(path.join(f.rootDir, '.runtime')), false);
    assert.equal(
      readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
      CANDIDATE_ENV,
    );
  });
}

for (const invalid of [
  'public-mode',
  'symlink',
  'directory',
  'fifo',
  'missing',
  'active-env',
]) {
  test(`rejects ${invalid} previous environment without altering the active file`, (t) => {
    const f = fixture(t);
    let envFile = f.envFile;
    if (invalid === 'public-mode') chmodSync(envFile, 0o644);
    if (invalid === 'fifo') {
      envFile = path.join(f.directory, 'pipe.env');
      execFileSync('mkfifo', [envFile]);
      chmodSync(envFile, 0o600);
    }
    if (invalid === 'symlink') {
      envFile = path.join(f.directory, 'linked.env');
      symlinkSync(f.envFile, envFile);
    }
    if (invalid === 'directory') envFile = f.directory;
    if (invalid === 'missing') envFile += '.missing';
    if (invalid === 'active-env') envFile = path.join(f.rootDir, '.env');
    assert.throws(() =>
      prepareRollbackBundle({ ...f.options, envFile }, { run: f.run }),
    );
    assert.equal(existsSync(path.join(f.rootDir, '.runtime')), false);
    assert.equal(
      readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
      CANDIDATE_ENV,
    );
  });
}

test('previous-contract failure is sanitized and cannot leave a usable partial bundle', (t) => {
  const f = fixture(t);
  writeFileSync(f.envFile, CANDIDATE_ENV);
  assert.throws(
    () => prepareRollbackBundle(f.options, { run: f.run }),
    (error) => {
      assert.match(error.message, /previous environment validation failed/);
      assert.doesNotMatch(
        error.message,
        /synthetic-sensitive-environment|DATABASE/,
      );
      return true;
    },
  );
  assert.deepEqual(
    readdirSync(path.join(f.rootDir, '.runtime/prod-app/rollback')),
    [],
  );
});

test('refuses deployment snapshots containing host-escaping symlinks', (t) => {
  const f = fixture(t, { symlink: true });
  assert.throws(
    () => prepareRollbackBundle(f.options, { run: f.run }),
    /regular files/,
  );
  assert.deepEqual(
    readdirSync(path.join(f.rootDir, '.runtime/prod-app/rollback')),
    [],
  );
});

test('restores the actual environment atomically from the pinned snapshot, not a changed source backup', (t) => {
  const f = prepared(t);
  writeFileSync(f.envFile, 'DATABASE=changed_after_capture\n');
  chmodSync(path.join(f.rootDir, '.env'), 0o644);
  restoreRollbackEnvironment({ ...f, image: IMAGE });
  assert.equal(
    readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
    PREVIOUS_ENV,
  );
  assert.equal(readFileSync(path.join(f.bundle, '.env'), 'utf8'), PREVIOUS_ENV);
  assert.equal(statSync(path.join(f.rootDir, '.env')).mode & 0o777, 0o600);
  assert.equal(
    readdirSync(f.rootDir).some((name) => name.startsWith('.env.rollback-')),
    false,
  );
});

for (const invalid of [
  'changed-env',
  'wrong-image',
  'foreign-bundle',
  'symlink-destination',
]) {
  test(`refuses ${invalid} during restoration`, (t) => {
    const f = prepared(t);
    if (invalid === 'changed-env')
      writeFileSync(path.join(f.bundle, '.env'), CANDIDATE_ENV);
    if (invalid === 'symlink-destination') {
      rmSync(path.join(f.rootDir, '.env'));
      symlinkSync(
        path.join(f.directory, 'never-created'),
        path.join(f.rootDir, '.env'),
      );
    }
    assert.throws(() =>
      restoreRollbackEnvironment({
        rootDir: f.rootDir,
        bundle: invalid === 'foreign-bundle' ? f.directory : f.bundle,
        image: invalid === 'wrong-image' ? OTHER : IMAGE,
      }),
    );
    if (invalid !== 'symlink-destination')
      assert.equal(
        readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
        CANDIDATE_ENV,
      );
    assert.equal(existsSync(path.join(f.directory, 'never-created')), false);
  });
}

const functions = script.slice(
  script.indexOf('compose()'),
  script.indexOf('COMMAND='),
);
function shellRestore(
  t,
  failStage = '',
  mode = 'explicit',
  action = 'restore',
) {
  const f = prepared(t);
  const events = path.join(f.directory, 'events');
  const currentEnv = path.join(f.rootDir, '.env');
  const result = spawnSync(
    'bash',
    [
      '-c',
      `
set -euo pipefail
ROOT_DIR=${shellQuote(f.rootDir)}
ENV_FILE=${shellQuote(currentEnv)}
COMPOSE_FILE="$ROOT_DIR/ops/compose/open-work-hub-prod.app.yml"
COMPOSE_PROJECT_NAME=open-work-hub-prod-app
CURRENT_IMAGE=open-work-hub-app:prod
PREVIOUS_IMAGE=open-work-hub-app:prod-previous
ROLLBACK_IMAGE=${shellQuote(mode === 'explicit' ? IMAGE : '')}
ROLLBACK_BUNDLE=${shellQuote(mode === 'explicit' ? f.bundle : '')}
EVENTS=${shellQuote(events)}
FAIL_STAGE=${shellQuote(failStage)}
CLEANUP_COUNT=0
${functions}
docker() {
  if [[ "$1" == image ]]; then printf '%s\\n' ${shellQuote(f.revision)}; return 0; fi
  if [[ "$1" == tag ]]; then
    printf 'tag:%s\\n' "$2" >> "$EVENTS"
    [[ "$FAIL_STAGE" != tag ]] || return 4
    return 0
  fi
  printf '%s\\n' "$*" >> "$EVENTS"
  if [[ "$*" == *' down '* ]]; then [[ "$FAIL_STAGE" != stop ]] || return 4; fi
  if [[ "$*" == *' up '* ]]; then
    if [[ "$COMPOSE_FILE" == "$ROLLBACK_BUNDLE/"* ]]; then
      [[ "$FAIL_STAGE" != start ]] || return 4
      cmp "$ENV_FILE" "$ROOT_DIR/.env" || return 8
    else [[ "$FAIL_STAGE" != candidate-start ]] || return 4; fi
  fi
}
node() {
  if [[ "$1" == *docker-storage.mjs ]]; then
    CLEANUP_COUNT=$((CLEANUP_COUNT + 1))
    printf 'cleanup:%s\\n' "$CLEANUP_COUNT" >> "$EVENTS"
    [[ "$FAIL_STAGE:$CLEANUP_COUNT" != post-cleanup:2 ]] || return 4
  elif [[ "$*" == *' restore-env '* ]]; then
    printf 'restore-env\\n' >> "$EVENTS"
    [[ "$FAIL_STAGE" != env ]] || return 4
    ${shellQuote(process.execPath)} ${shellQuote(helper)} "\${@:2}"
  elif [[ "$1" == *prod-app-smoke.mjs ]]; then
    printf 'smoke:%s:%s\\n' "$1" "$OPEN_WORK_HUB_EXPECTED_REVISION" >> "$EVENTS"
    [[ "$FAIL_STAGE" != smoke ]] || return 4
  else return 9; fi
}
build_release_image() {
  printf 'build\\n' >> "$EVENTS"
  [[ "$FAIL_STAGE" != build ]] || return 4
  printf 'candidate-image\\n'
}
promote_image() {
  printf 'promote\\n' >> "$EVENTS"
  [[ "$FAIL_STAGE" != promote ]] || return 4
}
run_migrations() {
  printf 'candidate-migration\\n' >> "$EVENTS"
  [[ "$FAIL_STAGE" != migration && "$FAIL_STAGE" != env ]] || return 4
}
run_smoke() {
  printf 'candidate-smoke\\n' >> "$EVENTS"
  [[ "$FAIL_STAGE" != candidate-smoke ]] || return 4
}
if ${action === 'deploy' ? 'deploy' : 'restore_previous_runtime'}; then printf 'success\\n'; else printf 'failed\\n'; fi
`,
    ],
    { encoding: 'utf8', env: { PATH: process.env.PATH } },
  );
  assert.equal(result.status, 0, result.stderr);
  return {
    ...f,
    result,
    events: existsSync(events) ? readFileSync(events, 'utf8') : '',
  };
}

test('explicit rollback restores pinned image, root/bundle env, previous definitions and previous smoke without migration', (t) => {
  const f = shellRestore(t);
  assert.equal(f.result.stdout, 'success\n');
  assert.match(f.events, /down --remove-orphans/);
  assert.ok(
    f.events.indexOf('down --remove-orphans') < f.events.indexOf('restore-env'),
  );
  assert.ok(f.events.indexOf('restore-env') < f.events.indexOf(`tag:${IMAGE}`));
  assert.ok(f.events.indexOf(`tag:${IMAGE}`) < f.events.indexOf(' up '));
  assert.match(
    f.events,
    new RegExp(
      f.bundle.replace(/[.*+?^${}()|[\]\\]/g, '\\$&') +
        '/ops/compose/open-work-hub-prod.app.yml',
    ),
  );
  assert.ok(
    f.events.includes(
      `smoke:${f.bundle}/scripts/prod-app-smoke.mjs:${f.revision}`,
    ),
  );
  assert.doesNotMatch(f.events, /migrate|--volumes| down .* -v|prod-previous/);
  assert.equal(
    readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
    PREVIOUS_ENV,
  );
});

for (const stage of ['stop', 'env', 'tag', 'start', 'smoke']) {
  test(`rollback stops at ${stage} failure even in an OR/conditional caller`, (t) => {
    const f = shellRestore(t, stage);
    assert.equal(f.result.stdout, 'failed\n');
    if (stage === 'stop')
      assert.doesNotMatch(f.events, /restore-env|tag:| up |smoke:/);
    if (stage === 'env') assert.doesNotMatch(f.events, /tag:| up |smoke:/);
    if (stage === 'tag') assert.doesNotMatch(f.events, / up |smoke:/);
    if (stage === 'start') assert.doesNotMatch(f.events, /smoke:/);
    if (stage === 'stop' || stage === 'env')
      assert.equal(
        readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
        CANDIDATE_ENV,
      );
  });
}

test('default compatible-image rollback also stops after retag failure', (t) => {
  const f = shellRestore(t, 'tag', 'default');
  assert.equal(f.result.stdout, 'failed\n');
  assert.doesNotMatch(f.events, / up |smoke:/);
});

for (const stage of [
  'build',
  'promote',
  'migration',
  'candidate-start',
  'candidate-smoke',
]) {
  test(`failed deployment at ${stage} restores the pinned release and still returns failure`, (t) => {
    const f = shellRestore(t, stage, 'explicit', 'deploy');
    assert.equal(f.result.stdout, 'failed\n');
    assert.match(f.result.stderr, /restored and passed smoke/);
    assert.ok(f.events.includes(`tag:${IMAGE}`));
    assert.ok(
      f.events.includes(
        `smoke:${f.bundle}/scripts/prod-app-smoke.mjs:${f.revision}`,
      ),
    );
    assert.equal(
      readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
      PREVIOUS_ENV,
    );
    const restoration = f.events.slice(
      f.events.indexOf('down --remove-orphans'),
    );
    assert.doesNotMatch(restoration, /migration|candidate-smoke|cleanup:2/);
  });
}

test('failed automatic environment restoration is reported separately and never starts the old image against candidate data', (t) => {
  const f = shellRestore(t, 'env', 'explicit', 'deploy');
  assert.equal(f.result.stdout, 'failed\n');
  assert.match(
    f.result.stderr,
    /restoration failed; operator recovery is required/,
  );
  assert.doesNotMatch(f.result.stderr, /restored and passed smoke/);
  assert.doesNotMatch(f.events, /tag:| up |smoke:/);
  assert.equal(
    readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
    CANDIDATE_ENV,
  );
});

test('retention failure after a healthy deployment does not roll back that release', (t) => {
  const f = shellRestore(t, 'post-cleanup', 'explicit', 'deploy');
  assert.match(
    f.result.stdout,
    /completed and passed public smoke\.\nfailed\n$/,
  );
  assert.match(f.result.stderr, /Deployment is healthy/);
  assert.doesNotMatch(f.events, /restore-env|tag:|down --remove-orphans/);
  assert.equal(
    readFileSync(path.join(f.rootDir, '.env'), 'utf8'),
    CANDIDATE_ENV,
  );
});

test('both Compose paths discard inherited product overrides while preserving Docker connection and caller environment', () => {
  const result = spawnSync(
    'bash',
    [
      '-c',
      `
set -euo pipefail
ENV_FILE=/synthetic/candidate/.env
COMPOSE_FILE=/synthetic/candidate/ops/compose/open-work-hub-prod.app.yml
COMPOSE_PROJECT_NAME=open-work-hub-prod-app
ROLLBACK_BUNDLE=/synthetic/previous
export OPEN_WORK_HUB_HERMES_API_KEY=synthetic-candidate
export OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET=synthetic-candidate
export OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_PORT=19999
export OPENROUTER_API_KEY=synthetic-candidate
${functions}
docker() {
  local checked_key
  for checked_key in OPEN_WORK_HUB_HERMES_API_KEY OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_PORT OPENROUTER_API_KEY; do
    [[ ! -v "$checked_key" ]] || return 9
  done
  [[ "$DOCKER_HOST" == unix:///synthetic/docker.sock && -n "$PATH" ]] || return 9
  printf '%s\\n' "$*"
}
compose config
rollback_compose config
[[ "$OPEN_WORK_HUB_HERMES_API_KEY" == synthetic-candidate && "$OPENROUTER_API_KEY" == synthetic-candidate ]]
`,
    ],
    {
      encoding: 'utf8',
      env: {
        PATH: process.env.PATH,
        DOCKER_HOST: 'unix:///synthetic/docker.sock',
      },
    },
  );
  assert.equal(result.status, 0, result.stderr);
  const calls = result.stdout.trim().split('\n');
  assert.equal(calls.length, 2);
  assert.match(calls[0], /--env-file \/synthetic\/candidate\/\.env/);
  assert.match(calls[1], /--env-file \/synthetic\/previous\/\.env/);
  assert.doesNotMatch(result.stdout, /synthetic-candidate|19999/);
});

for (const command of ['deploy', 'rollback']) {
  test(`${command} validates the correct existing image before candidate validation or runtime mutation`, () => {
    const dispatcher = script.slice(script.indexOf('COMMAND='));
    const result = spawnSync(
      'bash',
      [
        '-c',
        `
set -euo pipefail
CURRENT_IMAGE=open-work-hub-app:prod
PREVIOUS_IMAGE=open-work-hub-app:prod-previous
ROLLBACK_IMAGE=""
ROLLBACK_ENV_FILE=""
require_prod_checkout() { printf 'checkout\\n'; }
require_release_source() { printf 'release\\n'; }
prepare_rollback_runtime() { printf 'prepare:%s\\n' "$1"; return 6; }
validate_environment() { printf 'unexpected-validation\\n'; }
deploy() { printf 'unexpected-deployment\\n'; }
restore_previous_runtime() { printf 'unexpected-restoration\\n'; }
${dispatcher}
`,
        'test',
        command,
        '--rollback-env-file',
        '/synthetic/backup.env',
        '--rollback-image',
        IMAGE,
      ],
      { encoding: 'utf8', env: { PATH: process.env.PATH } },
    );
    assert.equal(result.status, 6);
    assert.equal(
      result.stdout,
      `checkout\nrelease\nprepare:open-work-hub-app:${command === 'deploy' ? 'prod' : 'prod-previous'}\n`,
    );
  });
}

for (const args of [
  ['deploy', '--rollback-env-file', '/not-used'],
  ['rollback', '--rollback-image', IMAGE],
  ['status', '--rollback-env-file', '/not-used', '--rollback-image', IMAGE],
  [
    'deploy',
    '--rollback-image',
    IMAGE,
    '--rollback-image',
    IMAGE,
    '--rollback-env-file',
    '/not-used',
  ],
  ['deploy', '--unknown-option'],
]) {
  test(`rejects invalid rollback option combination ${args.slice(0, 2).join(' ')}`, () => {
    const result = spawnSync(
      'bash',
      [fileURLToPath(new URL('./prod-app.sh', import.meta.url)), ...args],
      { encoding: 'utf8', env: { PATH: process.env.PATH } },
    );
    assert.equal(result.status, 2);
    assert.match(result.stderr, /Usage:/);
  });
}
