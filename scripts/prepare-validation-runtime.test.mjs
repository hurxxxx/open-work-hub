import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import os from 'node:os';
import path from 'node:path';
import test from 'node:test';

function fixture(t) {
  const root = fs.mkdtempSync(
    path.join(os.tmpdir(), 'owh-validation-runtime-'),
  );
  t.after(() => fs.rmSync(root, { recursive: true, force: true }));
  const write = (name, value) => {
    const target = path.join(root, name);
    fs.mkdirSync(path.dirname(target), { recursive: true });
    fs.writeFileSync(target, value);
    return target;
  };
  const groups = {
    NODE: [
      'package.json',
      'pnpm-lock.yaml',
      'pnpm-workspace.yaml',
      'packages/contracts/package.json',
      'packages/core-web/package.json',
      'packages/ui/package.json',
    ],
    API: ['apps/api/pyproject.toml', 'apps/api/uv.lock'],
    WORKER: ['apps/worker/pyproject.toml', 'apps/worker/uv.lock'],
  };
  const env = { PATH: process.env.PATH };
  const sha = (text) => createHash('sha256').update(text).digest('hex');
  for (const [name, files] of Object.entries(groups)) {
    const hash = sha(
      files
        .map((file) => {
          write(file, file);
          return `${sha(file)}\n`;
        })
        .join(''),
    );
    env[`OPEN_WORK_HUB_${name}_IMAGE_DEPENDENCY_FILE`] = write(
      `image/${name}.sha256`,
      `${hash}\n`,
    );
    const target = path.join(root, 'image', name);
    fs.mkdirSync(target);
    env[`OPEN_WORK_HUB_${name}_IMAGE_${name === 'NODE' ? 'MODULES' : 'VENV'}`] =
      target;
  }
  const script = write(
    'scripts/ci/prepare-validation-runtime.sh',
    fs.readFileSync(
      new URL('./ci/prepare-validation-runtime.sh', import.meta.url),
    ),
  );
  return {
    root,
    env,
    write,
    run: () => spawnSync('bash', [script], { env, encoding: 'utf8' }),
  };
}

test('full and focused CI share identity-checked Python environments without copying them', (t) => {
  const f = fixture(t);
  assert.equal(f.run().status, 0);
  assert.equal(f.run().status, 0, 'preparation is idempotent');
  for (const app of ['api', 'worker']) {
    for (const link of [`apps/${app}/.venv`, `.runtime/ci-${app}-venv`]) {
      assert.equal(
        fs.lstatSync(path.join(f.root, link)).isSymbolicLink(),
        true,
      );
      assert.equal(
        fs.realpathSync(path.join(f.root, link)),
        f.env[`OPEN_WORK_HUB_${app.toUpperCase()}_IMAGE_VENV`],
      );
    }
  }
});

test('dependency mismatch fails before creating any runtime link', (t) => {
  const f = fixture(t);
  f.write('apps/api/uv.lock', 'changed lock');
  const result = f.run();
  assert.equal(result.status, 2);
  assert.match(result.stderr, /dependency mismatch/);
  assert.equal(fs.existsSync(path.join(f.root, 'node_modules')), false);
  assert.equal(fs.existsSync(path.join(f.root, 'apps/api/.venv')), false);
});

test('default environment reuse never replaces a real environment or foreign symlink', (t) => {
  for (const kind of ['directory', 'symlink']) {
    const f = fixture(t);
    const target = path.join(f.root, 'apps/api/.venv');
    if (kind === 'directory')
      f.write('apps/api/.venv/keep', 'existing environment');
    else fs.symlinkSync(f.env.OPEN_WORK_HUB_WORKER_IMAGE_VENV, target);
    assert.equal(f.run().status, 2);
    if (kind === 'directory')
      assert.equal(
        fs.readFileSync(path.join(target, 'keep'), 'utf8'),
        'existing environment',
      );
    else
      assert.equal(
        fs.readlinkSync(target),
        f.env.OPEN_WORK_HUB_WORKER_IMAGE_VENV,
      );
  }
});
