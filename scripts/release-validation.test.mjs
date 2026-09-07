import assert from 'node:assert/strict';
import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  MARKER,
  LIMITS,
  collectChanges,
  selectValidation,
  fastRequest,
  executePlan,
} from './release-validation.mjs';

const script = fileURLToPath(
  new URL('./release-validation.mjs', import.meta.url),
);
const source = 'a'.repeat(40);
const target = 'b'.repeat(40);
const request = (head = source, base = target) =>
  `${MARKER} mode=fast source=${head} target=${base} -->`;
const change = (file, extra = {}) => ({
  path: file,
  oldMode: '100644',
  newMode: '100644',
  lines: 10,
  ...extra,
});
const planFor = (changes, mode = 'fast') => selectValidation({ changes, mode });

test('full is the default, and invalid modes are rejected', () => {
  assert.equal(
    selectValidation({ changes: [change('README.md')] }).mode,
    'full',
  );
  assert.throws(() => planFor([], 'emergency'), /must be full or fast/);
  assert.equal(planFor([]).mode, 'full');
});

test('docs/instructions use focused guidance checks without app suites', () => {
  const plan = planFor([
    change('docs/domains/release/README.md'),
    change('AGENTS.md'),
  ]);
  assert.equal(plan.mode, 'fast');
  assert.deepEqual(plan.checks, [
    'check:skills',
    'test:skill-harness',
    'test:claude-skills',
  ]);
  assert.ok(plan.skipped.includes('ci:api:full'));
  assert.ok(plan.skipped.includes('ci:web'));
});

for (const file of [
  '.agents/skills/owh-release/SKILL.md',
  '.codex/hooks.json',
  'scripts/setup-claude-skills.mjs',
  'scripts/codex-review-ci.sh',
]) {
  test(`agent setup/review CI has service-free harness coverage: ${file}`, () => {
    assert.deepEqual(planFor([change(file)]).checks, ['ci:harness']);
  });
}

for (const file of [
  'apps/api/src/app.py',
  'apps/web/src/app.tsx',
  'apps/worker/src/task.py',
  'apps/api/alembic/versions/new.py',
  'apps/api/tests/test_api.py',
  'packages/contracts/README.ts',
  'package.json',
  'pnpm-lock.yaml',
  'apps/api/pyproject.toml',
  'apps/worker/uv.lock',
  'dev.sh',
  'ops/compose/open-work-hub-prod.app.yml',
  'ops/app/Dockerfile',
  '.env.example',
  'scripts/prod-app.sh',
  'scripts/ci/prepare-validation-runtime.sh',
  'ops/ci/validation-runner/Dockerfile',
  '.gitlab-ci.yml',
  'ops/ci/ci-first.gitlab-ci.yml',
  'scripts/check-gitlab-pipeline.mjs',
  'scripts/check-gitlab-pipeline.test.mjs',
  'scripts/release-validation.mjs',
  'scripts/release-validation.test.mjs',
  'scripts/new-unknown-tool.sh',
]) {
  test(`mixed runtime/control/unknown change forces full: ${file}`, () => {
    const plan = planFor([change('README.md'), change(file)]);
    assert.equal(plan.mode, 'full');
    assert.deepEqual(plan.checks, ['ci:all']);
    assert.deepEqual(plan.skipped, []);
  });
}

test('binary, symlink, submodule, mode and unsafe path changes fail closed', () => {
  for (const item of [
    change('README.md', { lines: null }),
    change('README.md', { lines: undefined }),
    change('README.md', { newMode: '120000' }),
    change('README.md', { oldMode: '160000' }),
    change('README.md', { newMode: '100755' }),
    change('docs/../apps/api/README.md'),
    change('docs/bad\nREADME.md'),
    change('docs/bad\\README.md'),
    change('/docs/README.md'),
  ])
    assert.equal(planFor([item]).mode, 'full');
});

test('bounded additions/deletions allowed, large non-runtime changes stay full', () => {
  assert.equal(
    planFor([
      change('docs/new.md', { oldMode: '000000' }),
      change('docs/old.md', { newMode: '000000' }),
    ]).mode,
    'fast',
  );
  assert.equal(
    planFor([change('docs/big.md', { lines: LIMITS.lines + 1 })]).mode,
    'full',
  );
  assert.equal(
    planFor(
      Array.from({ length: LIMITS.files + 1 }, (_, i) =>
        change(`docs/${i}.md`),
      ),
    ).mode,
    'full',
  );
});

test('fast request is exact, unique, first-line, untruncated and bound to both full SHAs', () => {
  assert.equal(
    fastRequest({
      description: `${request()}\nReason: explicit user request.`,
      source,
      target,
    }),
    'fast',
  );
  for (const description of [
    '',
    '긴급 빠른 배포 fast release',
    request('c'.repeat(40)),
    request(source, 'd'.repeat(40)),
    request(source.slice(0, 8)),
    `${request()}\n${request()}`,
    `Example:\n${request()}`,
    request().replace('mode=fast', 'mode=skip'),
  ]) {
    assert.equal(fastRequest({ description, source, target }), 'full');
  }
  assert.equal(
    fastRequest({ description: request(), source, target, truncated: true }),
    'full',
  );
});

test('executor runs only selected checks and records successful fresh evidence', () => {
  const commands = [];
  const evidence = [];
  let checkedFresh = false;
  executePlan(
    { source, target, mergeTree: source, ...planFor([change('README.md')]) },
    {
      run: (command, args) => {
        commands.push([command, ...args]);
        return 0;
      },
      record: (value) => evidence.push(value),
      fresh: () => {
        checkedFresh = true;
      },
    },
  );
  assert.deepEqual(
    commands.map((argv) => argv.slice(0, 2)),
    [
      ['git', 'diff'],
      ['pnpm', 'check:skills'],
      ['pnpm', 'test:skill-harness'],
      ['pnpm', 'test:claude-skills'],
    ],
  );
  assert.ok(checkedFresh);
  assert.match(evidence.at(-1), /Status: passed/);
  assert.match(evidence.at(-1), /ci:api:full: no application\/runtime change/);
});

test('failed checks or changed source/target never yield passing evidence', () => {
  for (const stale of [false, true]) {
    let lastEvidence;
    const commands = [];
    assert.throws(
      () =>
        executePlan(
          { source, target, ...planFor([change('README.md')]) },
          {
            run: (command, args) => {
              commands.push([command, ...args]);
              return stale ? 0 : 1;
            },
            record: (value) => {
              lastEvidence = value;
            },
            fresh: () => {
              throw new Error('stale');
            },
          },
        ),
      stale ? /stale/ : /check failed/,
    );
    assert.match(lastEvidence, /Status: failed/);
    if (!stale) assert.equal(commands.length, 1);
  }
});

function fixture(t) {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), 'owh-release-validation-'),
  );
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const git = (args) =>
    execFileSync('git', args, {
      cwd: root,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', 'pipe'],
    }).trim();
  const write = (file, value) => {
    fs.mkdirSync(path.dirname(path.join(root, file)), { recursive: true });
    fs.writeFileSync(path.join(root, file), value);
  };
  const commit = () => {
    git(['add', '.']);
    git(['commit', '-qm', 'fixture']);
    return git(['rev-parse', 'HEAD']);
  };
  git(['init', '-q', '--initial-branch=dev']);
  git(['config', 'user.name', 'Release Test']);
  git(['config', 'user.email', 'release@example.invalid']);
  write('.gitignore', 'release-validation-context.md\n');
  write('README.md', 'before\n');
  write('apps/api/app.py', 'runtime\n');
  const base = commit();
  git(['branch', 'main']);
  git(['remote', 'add', 'origin', root]);
  return { root, git, write, commit, base };
}

test('storage exhaustion fails before suites and cannot produce passing evidence', () => {
  let evidence = '';
  assert.throws(
    () =>
      executePlan(
        {
          source,
          target,
          mergeTree: source,
          ...planFor([change('README.md')]),
        },
        {
          preflight: () => {
            throw new Error('Insufficient disk headroom');
          },
          run: () => assert.fail('must not launch suites'),
          fresh: () => assert.fail('must not reach final success'),
          record: (value) => {
            evidence = value;
          },
        },
      ),
    /Insufficient disk headroom/,
  );
  assert.match(evidence, /Status: failed/);
  assert.match(evidence, /storage headroom preflight: failed/);
});

test('real Git snapshots catch deleted/renamed runtime paths and filenames with tabs', (t) => {
  const f = fixture(t);
  fs.mkdirSync(path.join(f.root, 'docs'));
  f.git(['mv', 'apps/api/app.py', 'docs/moved.md']);
  f.write('docs/name\twith-tab.md', 'text\n');
  const head = f.commit();
  const changes = collectChanges(f.base, head, f.root);
  assert.ok(
    changes.some(
      (item) => item.path === 'apps/api/app.py' && item.newMode === '000000',
    ),
  );
  assert.ok(changes.some((item) => item.path === 'docs/name\twith-tab.md'));
  assert.equal(planFor(changes).mode, 'full');
});

test('plan is read-only, resolves real SHAs and rejects unavailable/incorrect refs', (t) => {
  const f = fixture(t);
  f.write('README.md', 'after\n');
  const head = f.commit();
  const run = (...args) =>
    spawnSync(process.execPath, [script, 'plan', ...args], {
      cwd: f.root,
      encoding: 'utf8',
    });
  const result = run('--base', f.base, '--mode', 'fast');
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /"mode": "fast"/);
  assert.ok(result.stdout.includes(request(head, f.base)));
  assert.equal(f.git(['status', '--porcelain']), '');
  assert.notEqual(run('--base', '--bad-ref').status, 0);
  assert.notEqual(run('--base', f.base, '--mode', 'skip').status, 0);
});

test('unsynchronized target changes cannot be validated as the source tree', (t) => {
  const f = fixture(t);
  f.git(['checkout', '-q', 'main']);
  f.write('docs/target-only.md', 'target change\n');
  const targetHead = f.commit();
  f.git(['checkout', '-q', 'dev']);
  f.write('README.md', 'source change\n');
  f.commit();
  const result = spawnSync(
    process.execPath,
    [script, 'plan', '--base', targetHead, '--mode', 'fast'],
    {
      cwd: f.root,
      encoding: 'utf8',
    },
  );
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /does not represent the merge result/);
});

test('CI CLI rejects non-release context and command-line bypasses before running tests', (t) => {
  const f = fixture(t);
  for (const args of [['ci'], ['ci', '--mode', 'fast']]) {
    const result = spawnSync(process.execPath, [script, ...args], {
      cwd: f.root,
      env: {},
      encoding: 'utf8',
    });
    assert.notEqual(result.status, 0);
    assert.equal(
      fs.existsSync(path.join(f.root, 'release-validation-context.md')),
      false,
    );
  }
});

test('CI executes fast/full suites in a synthetic repository and rejects stale pipelines', (t) => {
  const f = fixture(t);
  // Stand-in pnpm is outside tracked source; no real services, credentials or suites.
  const bin = path.join(f.root, '.git', 'test-bin');
  fs.mkdirSync(bin);
  fs.writeFileSync(path.join(bin, 'pnpm'), '#!/bin/sh\nexit 0\n', {
    mode: 0o755,
  });
  f.write('README.md', 'after\n');
  let head = f.commit();
  const run = (description, sha = head) =>
    spawnSync(process.execPath, [script, 'ci'], {
      cwd: f.root,
      encoding: 'utf8',
      env: {
        PATH: `${bin}:${process.env.PATH}`,
        CI_PIPELINE_SOURCE: 'merge_request_event',
        CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'dev',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'main',
        CI_PROJECT_ID: '1',
        CI_MERGE_REQUEST_SOURCE_PROJECT_ID: '1',
        CI_MERGE_REQUEST_EVENT_TYPE: 'detached',
        CI_COMMIT_SHA: sha,
        CI_MERGE_REQUEST_DESCRIPTION: description,
      },
    });
  let result = run(request(head, f.base));
  assert.equal(result.status, 0, result.stderr);
  assert.match(
    fs.readFileSync(path.join(f.root, 'release-validation-context.md'), 'utf8'),
    /Selected: fast[\s\S]+Status: passed/,
  );
  f.write('README.md', 'uncommitted input must not pass as the tested SHA\n');
  assert.notEqual(run(request(head, f.base)).status, 0);
  f.write('README.md', 'after\n');
  result = run('');
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /full; selected: ci:all/);
  const oldHead = head;
  f.write('apps/api/app.py', 'runtime change\n');
  head = f.commit();
  assert.notEqual(run(request(oldHead, f.base), oldHead).status, 0);
  result = run(request(head, f.base));
  assert.equal(result.status, 0, result.stderr);
  assert.match(result.stdout, /full; selected: ci:all/);

  // A target advance during otherwise successful validation invalidates evidence.
  fs.writeFileSync(
    path.join(bin, 'pnpm'),
    '#!/bin/sh\ngit update-ref refs/heads/main HEAD\n',
    { mode: 0o755 },
  );
  result = run(request(head, f.base));
  assert.notEqual(result.status, 0);
  assert.match(result.stderr, /source\/target changed/);
  assert.match(
    fs.readFileSync(path.join(f.root, 'release-validation-context.md'), 'utf8'),
    /Status: failed/,
  );

  // Evidence cannot follow a symlink into another file, even on the full path.
  const evidencePath = path.join(f.root, 'release-validation-context.md');
  fs.unlinkSync(evidencePath);
  fs.symlinkSync('README.md', evidencePath);
  const readme = fs.readFileSync(path.join(f.root, 'README.md'), 'utf8');
  assert.notEqual(run('').status, 0);
  assert.equal(fs.readFileSync(path.join(f.root, 'README.md'), 'utf8'), readme);
});
