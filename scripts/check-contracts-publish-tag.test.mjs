import assert from 'node:assert/strict';
import { spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const script = path.join(repoRoot, 'scripts/check-contracts-publish-tag.mjs');
const packageJson = JSON.parse(
  fs.readFileSync(
    path.join(repoRoot, 'packages/contracts/package.json'),
    'utf8',
  ),
);
const expectedTag = `contracts-v${packageJson.version}`;

function run(tag) {
  return spawnSync(process.execPath, [script], {
    cwd: repoRoot,
    env: {
      ...process.env,
      ...(tag === undefined ? {} : { CI_COMMIT_TAG: tag }),
    },
    encoding: 'utf8',
  });
}

test('accepts the package-version contract tag', () => {
  const result = run(expectedTag);

  assert.equal(result.status, 0, result.stderr);
});

test('rejects a missing or mismatched contract tag', () => {
  assert.notEqual(run(undefined).status, 0);
  assert.notEqual(run('contracts-v0.0.0').status, 0);
});
