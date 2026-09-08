import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

// The release selector is part of the pipeline contract, including in ci:harness.
import './release-validation.test.mjs';
import './prepare-validation-runtime.test.mjs';

import {
  CODEX_ENTRYPOINT,
  CONTRACT,
  FEATURE_MR_RULE,
  RELEASE_MR_RULE,
  validateGitlabPipelineFiles,
  validateGitlabPipelineSource,
} from './check-gitlab-pipeline.mjs';

const repoRoot = path.dirname(path.dirname(fileURLToPath(import.meta.url)));
const rootCi = path.join(repoRoot, '.gitlab-ci.yml');
const externalCi = path.join(repoRoot, 'ops/ci/ci-first.gitlab-ci.yml');

function readRootCi() {
  return fs.readFileSync(rootCi, 'utf8');
}

test('root and ops CI share one contract', () => {
  assert.equal(
    fs.readFileSync(rootCi, 'utf8'),
    fs.readFileSync(externalCi, 'utf8'),
  );
  assert.equal(validateGitlabPipelineFiles(repoRoot), CONTRACT);
});

test('CI has the feature review and release validation lanes', () => {
  const source = readRootCi();

  assert.ok(source.includes(FEATURE_MR_RULE));
  assert.ok(source.includes(RELEASE_MR_RULE));
  assert.ok(source.includes(CODEX_ENTRYPOINT));
  assert.ok(source.includes('codex_review:'));
  assert.ok(source.includes('release_validation:'));
  assert.ok(source.includes('contracts_publish:'));
});

test('contract rejects extra or weakened jobs', () => {
  const source = readRootCi();
  const mutations = [
    `${source}\nunexpected_check:\n  script: [true]\n`,
    source.replace(
      '  allow_failure: false\n  rules:\n',
      '  allow_failure: true\n  rules:\n',
    ),
    source.replace('$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME == "dev" && ', ''),
    source.replace('node scripts/release-validation.mjs ci', 'pnpm ci:harness'),
    source.replace("    OPEN_WORK_HUB_API_PYTEST_WORKERS: '2'\n", ''),
    source.replace("    VITEST_MAX_WORKERS: '1'", "    VITEST_MAX_WORKERS: '8'"),
    source.replace("    PLAYWRIGHT_WORKERS: '1'", "    PLAYWRIGHT_WORKERS: '8'"),
    source.replace(
      'node scripts/release-validation.mjs ci',
      'node scripts/release-validation.mjs ci --mode fast',
    ),
  ];

  for (const mutated of mutations) {
    assert.throws(
      () => validateGitlabPipelineSource(mutated),
      /feature-codex-release-v1/,
    );
  }
});

test('contract rejects retired source project identifiers', () => {
  assert.throws(
    () =>
      validateGitlabPipelineSource(
        `${readRootCi()}\n# ${'dw'}${'dcc'} legacy\n`,
      ),
    /retired project identifiers/,
  );
});
