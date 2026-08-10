import assert from 'node:assert/strict';
import test from 'node:test';

import {
  FAILURE_MESSAGE,
  buildLegacyPathPattern,
  findLegacyPathReferences,
  formatPathHardcodingFindings,
  isExcludedPath,
  runCli,
} from './check-path-hardcoding.mjs';

const legacyBase = '/projects/open-alm-';
const legacyPath = (suffix) => `${legacyBase}${suffix}`;

test('buildLegacyPathPattern detects legacy prod and dev checkouts only at path boundaries', () => {
  const pattern = buildLegacyPathPattern();

  assert.equal(pattern.test(`${legacyPath('prod')}/current`), true);
  assert.equal(pattern.test(`cd ${legacyPath('dev')}`), true);
  assert.equal(pattern.test(`${legacyPath('prod')}uction`), false);
  assert.equal(pattern.test(`${legacyPath('dev')}-local`), false);
  assert.equal(pattern.test(`${legacyPath('dev')}_local`), false);
});

test('findLegacyPathReferences detects legacy prod and dev paths from in-memory files', () => {
  const files = ['scripts/deploy.sh', 'apps/api/config.py', 'apps/web/src/App.tsx'];
  const sources = new Map([
    ['scripts/deploy.sh', `rsync ${legacyPath('prod')}/releases/current\n`],
    ['apps/api/config.py', `DEV_ROOT = "${legacyPath('dev')}"\n`],
    ['apps/web/src/App.tsx', `const workspace = "${legacyPath('devel')}";\n`],
  ]);

  const findings = findLegacyPathReferences({
    files,
    readFile: (file) => sources.get(file),
  });

  assert.deepEqual(findings, [
    {
      file: 'scripts/deploy.sh',
      line: 1,
      lineText: `rsync ${legacyPath('prod')}/releases/current`,
      legacyPaths: [legacyPath('prod')],
    },
    {
      file: 'apps/api/config.py',
      line: 1,
      lineText: `DEV_ROOT = "${legacyPath('dev')}"`,
      legacyPaths: [legacyPath('dev')],
    },
  ]);
});

test('findLegacyPathReferences excludes learning and docs reference paths', () => {
  const files = [
    'learning/setup.md',
    'docs/reference/deploy.md',
    'docs/reference/nested/deploy.md',
    'docs/runbook.md',
  ];
  const sources = new Map(files.map((file) => [file, `legacy=${legacyPath('prod')}\n`]));

  const findings = findLegacyPathReferences({
    files,
    readFile: (file) => sources.get(file),
  });

  assert.deepEqual(findings.map((finding) => finding.file), ['docs/runbook.md']);
  assert.equal(isExcludedPath('learning/setup.md'), true);
  assert.equal(isExcludedPath('docs/reference/deploy.md'), true);
  assert.equal(isExcludedPath('docs/runbook.md'), false);
});

test('formatPathHardcodingFindings preserves git grep style output', () => {
  const lineText = `ROOT="${legacyPath('dev')}/runtime"`;
  const findings = findLegacyPathReferences({
    files: ['scripts/dev.sh'],
    readFile: () => `${lineText}\n`,
  });

  assert.equal(formatPathHardcodingFindings(findings), `scripts/dev.sh:1:${lineText}`);
});

test('runCli returns existing quiet success and failure report behavior with injected files', () => {
  const stdout = [];
  const stderr = [];

  assert.equal(
    runCli({
      files: ['docs/reference/deploy.md'],
      readFile: () => `ROOT="${legacyPath('prod')}"\n`,
      stdout: (message) => stdout.push(message),
      stderr: (message) => stderr.push(message),
    }),
    0,
  );
  assert.deepEqual(stdout, []);
  assert.deepEqual(stderr, []);

  assert.equal(
    runCli({
      files: ['apps/api/config.py'],
      readFile: () => `ROOT="${legacyPath('prod')}"\n`,
      stdout: (message) => stdout.push(message),
      stderr: (message) => stderr.push(message),
    }),
    1,
  );
  assert.deepEqual(stdout, [`apps/api/config.py:1:ROOT="${legacyPath('prod')}"`]);
  assert.deepEqual(stderr, [FAILURE_MESSAGE]);
});
