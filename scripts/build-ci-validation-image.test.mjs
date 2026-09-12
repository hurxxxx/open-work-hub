import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import { fileURLToPath } from 'node:url';
import test from 'node:test';

const repoRoot = fileURLToPath(new URL('../', import.meta.url));
const digest = `postgres@sha256:${'a'.repeat(64)}`;

function fixture(t) {
  const root = fs.mkdtempSync(path.join(os.tmpdir(), 'owh-validation-build-'));
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const write = (name, content) => {
    const target = path.join(root, name);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, content);
    return target;
  };
  for (const name of [
    'scripts/build-ci-validation-image.sh',
    'ops/ci/validation-runner/Dockerfile',
  ]) write(name, fs.readFileSync(path.join(repoRoot, name)));
  for (const name of [
    'package.json', 'pnpm-lock.yaml', 'pnpm-workspace.yaml',
    'packages/contracts/package.json', 'packages/core-web/package.json',
    'packages/ui/package.json', 'apps/api/pyproject.toml', 'apps/api/uv.lock',
    'apps/worker/pyproject.toml', 'apps/worker/uv.lock',
  ]) write(name, name.endsWith('.json') ? '{}' : name);
  const docker = write('bin/docker', `#!${process.execPath}
const fs = require('node:fs');
const args = process.argv.slice(2);
if (args[0] === '--config') args.splice(0, 2);
fs.appendFileSync(process.env.TEST_DOCKER_LOG, JSON.stringify(args) + '\\n');
if (args[0] === 'version') console.log(process.env.TEST_PLATFORM || 'linux/amd64');
else if (args[0] === 'buildx') {
  if (process.env.TEST_RESOLVE_FAILURE) process.exit(1);
  console.log(JSON.stringify({ digest: 'sha256:' + 'a'.repeat(64) }));
} else if (args[0] === 'image') {
  if (!fs.existsSync(process.env.TEST_DOCKER_STATE)) process.exit(1);
  console.log(fs.readFileSync(process.env.TEST_DOCKER_STATE, 'utf8'));
} else if (args[0] === 'build') {
  const contract = args.find(arg => arg.startsWith('VALIDATION_CONTRACT_SHA256='));
  fs.writeFileSync(process.env.TEST_DOCKER_STATE, contract.split('=')[1]);
} else if (args[0] === 'run') {
  if (process.env.TEST_VERIFY_FAILURE) process.exit(1);
} else process.exit(3);
`);
  fs.chmodSync(docker, 0o755);
  const log = path.join(root, 'docker.log');
  const env = {
    PATH: `${path.dirname(docker)}:${process.env.PATH}`,
    OPEN_WORK_HUB_VALIDATION_REPO_ROOT: root,
    TEST_DOCKER_LOG: log,
    TEST_DOCKER_STATE: path.join(root, 'docker.state'),
  };
  return {
    root, write, env,
    calls: () => fs.existsSync(log)
      ? fs.readFileSync(log, 'utf8').trim().split('\n').map(JSON.parse) : [],
    run: (args = [], overrides = {}) => spawnSync(
      'bash', [path.join(root, 'scripts/build-ci-validation-image.sh'), ...args],
      { env: { ...env, ...overrides }, encoding: 'utf8', timeout: 10000 },
    ),
  };
}

test('building requires an explicit server major and immutable overrides', (t) => {
  const f = fixture(t);
  for (const args of [[], ['--postgres-major'], ['--postgres-major', '18.6'],
    ['--postgres-major', '18', '--postgres-client-image', 'postgres:18'],
    ['--postgres-major', '18', '--platform', 'linux/unknown']]) {
    assert.equal(f.run(args).status, 2);
  }
  assert.deepEqual(f.calls(), [], 'invalid input must not invoke Docker');
  assert.equal(f.run(['--print-contract']).status, 0);
  assert.deepEqual(f.calls(), [], 'source identity inspection does not require Docker');
});

test('selected server majors resolve official immutable images on the native platform', (t) => {
  for (const major of ['17', '18']) {
    const f = fixture(t);
    const result = f.run(['--postgres-major', major], { TEST_PLATFORM: 'linux/arm64' });
    assert.equal(result.status, 0, result.stderr);
    assert.ok(f.calls().find(args => args[0] === 'buildx').includes(`postgres:${major}-bookworm`));
    const build = f.calls().find(args => args[0] === 'build');
    assert.ok(build.includes(`POSTGRES_MAJOR=${major}`));
    assert.ok(build.includes(`POSTGRES_CLIENT_IMAGE=${digest}`));
    assert.ok(build.includes('linux/arm64'));
    const run = f.calls().find(args => args[0] === 'run');
    assert.equal(run[run.length - 4], major);
    assert.match(result.stdout, new RegExp(`postgres_major=${major}`));
    assert.match(result.stdout, /Built and verified/);
  }
});

test('reuses only the same verified version, digest, platform and source dependencies', (t) => {
  const f = fixture(t);
  const args = ['--postgres-major', '18', '--postgres-client-image', digest];
  assert.equal(f.run(args).status, 0);
  assert.match(f.run(args).stdout, /Reused and verified/);
  assert.equal(f.calls().filter(args => args[0] === 'build').length, 1);
  assert.equal(f.calls().filter(args => args[0] === 'run').length, 2);
  f.write('apps/api/uv.lock', 'updated dependencies');
  assert.match(f.run(args).stdout, /Built and verified/);
  assert.match(f.run(args, { TEST_PLATFORM: 'linux/arm64' }).stdout, /Built and verified/);
  assert.match(f.run(['--postgres-major', '17', '--postgres-client-image', digest]).stdout, /Built and verified/);
  assert.match(f.run(['--postgres-major', '18', '--postgres-client-image', `postgres@sha256:${'b'.repeat(64)}`]).stdout, /Built and verified/);
  assert.equal(f.calls().filter(args => args[0] === 'build').length, 5);
  assert.equal(f.calls().some(args => args[0] === 'buildx'), false, 'explicit digest avoids tag resolution');
});

test('registry and client/runtime verification failures never report success', (t) => {
  const f = fixture(t);
  const args = ['--postgres-major', '18'];
  assert.notEqual(f.run(args, { TEST_RESOLVE_FAILURE: '1' }).status, 0);
  assert.equal(f.calls().some(args => args[0] === 'build'), false);
  assert.equal(f.run(args).status, 0);
  const failedReuse = f.run(args, { TEST_VERIFY_FAILURE: '1' });
  assert.notEqual(failedReuse.status, 0);
  assert.doesNotMatch(failedReuse.stdout, /Reused and verified|Built and verified/);
});

test('PostgreSQL preflight handles compatibility and redacts connection failures', () => {
  const result = spawnSync('python3', [
    '-m', 'unittest', 'discover', '-s', 'scripts/tests', '-p', 'test_validation_postgres.py',
  ], { cwd: repoRoot, encoding: 'utf8', timeout: 15000 });
  assert.equal(result.status, 0, `${result.stdout}\n${result.stderr}`);
});
