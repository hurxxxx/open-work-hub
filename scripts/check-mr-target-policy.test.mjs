import assert from 'node:assert/strict';
import test from 'node:test';

import { evaluateMrTargetPolicy } from './check-mr-target-policy.mjs';

function mrEnv(sourceBranch, targetBranch, extra = {}) {
  return {
    CI_PIPELINE_SOURCE: 'merge_request_event',
    CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: sourceBranch,
    CI_MERGE_REQUEST_TARGET_BRANCH_NAME: targetBranch,
    ...extra,
  };
}

test('MR target policy skips non-MR pipelines', () => {
  const result = evaluateMrTargetPolicy({ CI_PIPELINE_SOURCE: 'push' });

  assert.equal(result.ok, true);
  assert.equal(result.skipped, true);
});

test('MR target policy allows feature branches to target dev', () => {
  const result = evaluateMrTargetPolicy(mrEnv('feature/docs', 'dev'));

  assert.equal(result.ok, true);
  assert.match(result.message, /feature MR feature\/docs -> dev/);
});

test('MR target policy allows release promotion from dev to main', () => {
  const result = evaluateMrTargetPolicy(mrEnv('dev', 'main'));

  assert.equal(result.ok, true);
  assert.match(result.message, /release promotion MR dev -> main/);
});

test('MR target policy rejects feature branches targeting main', () => {
  const result = evaluateMrTargetPolicy(mrEnv('feature/docs', 'main'));

  assert.equal(result.ok, false);
  assert.match(result.message, /invalid MR branch pair: feature\/docs -> main/);
  assert.match(result.message, /Feature work must target dev/);
});

test('MR target policy rejects production branch backports into dev', () => {
  const result = evaluateMrTargetPolicy(mrEnv('main', 'dev'));

  assert.equal(result.ok, false);
  assert.match(result.message, /invalid MR branch pair: main -> dev/);
});

test('MR target policy rejects unknown target branches', () => {
  const result = evaluateMrTargetPolicy(mrEnv('feature/docs', 'staging'));

  assert.equal(result.ok, false);
  assert.match(
    result.message,
    /invalid MR branch pair: feature\/docs -> staging/,
  );
});

test('MR target policy reports missing MR variables', () => {
  const result = evaluateMrTargetPolicy({
    CI_PIPELINE_SOURCE: 'merge_request_event',
  });

  assert.equal(result.ok, false);
  assert.match(result.message, /CI_MERGE_REQUEST_SOURCE_BRANCH_NAME/);
  assert.match(result.message, /CI_MERGE_REQUEST_TARGET_BRANCH_NAME/);
});

test('MR target policy supports branch-name overrides', () => {
  const result = evaluateMrTargetPolicy(
    mrEnv('develop', 'stable', {
      OPEN_WORK_HUB_DEVELOPMENT_BRANCH: 'develop',
      OPEN_WORK_HUB_PRODUCTION_BRANCH: 'stable',
    }),
  );

  assert.equal(result.ok, true);
  assert.match(result.message, /release promotion MR develop -> stable/);
});
