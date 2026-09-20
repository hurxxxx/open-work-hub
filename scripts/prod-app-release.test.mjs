import assert from 'node:assert/strict';
import test from 'node:test';

import {
  readReleaseEvidence,
  validateReleaseEvidence,
} from './prod-app-release.mjs';

const SOURCE = 'a'.repeat(40);
const MERGE = 'b'.repeat(40);
const TREE = 'c'.repeat(40);

function releaseMr(overrides = {}) {
  return {
    iid: 49,
    state: 'merged',
    source_branch: 'dev',
    target_branch: 'main',
    source_project_id: 1,
    target_project_id: 1,
    sha: SOURCE,
    merge_commit_sha: MERGE,
    head_pipeline: {
      id: 141,
      project_id: 1,
      source: 'merge_request_event',
      ref: 'refs/merge-requests/49/head',
      status: 'success',
      sha: SOURCE,
    },
    ...overrides,
  };
}

const context = {
  expectedIid: '49',
  headRevision: MERGE,
  headTree: TREE,
  sourceTree: TREE,
  pipelineJobs: [
    { name: 'release_validation', status: 'success', allow_failure: false },
  ],
};

test('accepts the successful release MR whose source tree became current main', () => {
  assert.deepEqual(validateReleaseEvidence(releaseMr(), context), {
    sourceRevision: SOURCE,
    mergeRevision: MERGE,
    pipelineId: 141,
  });
});

for (const [name, mutate] of [
  ['unmerged MR', (mr) => (mr.state = 'opened')],
  ['wrong branches', (mr) => (mr.source_branch = 'feature')],
  ['cross-project MR', (mr) => (mr.source_project_id = 2)],
  ['failed pipeline', (mr) => (mr.head_pipeline.status = 'failed')],
  ['stale pipeline', (mr) => (mr.head_pipeline.sha = 'd'.repeat(40))],
  ['wrong pipeline source', (mr) => (mr.head_pipeline.source = 'push')],
]) {
  test(`rejects ${name}`, () => {
    const mr = releaseMr();
    mutate(mr);
    assert.throws(
      () => validateReleaseEvidence(mr, context),
      /merged same-project dev-to-main MR with a successful current release pipeline/,
    );
  });
}

test('rejects a merge commit or tree that is not the production source', () => {
  assert.throws(
    () =>
      validateReleaseEvidence(releaseMr(), {
        ...context,
        headRevision: 'd'.repeat(40),
      }),
    /merge commit/,
  );
  assert.throws(
    () =>
      validateReleaseEvidence(releaseMr(), {
        ...context,
        sourceTree: 'd'.repeat(40),
      }),
    /source tree/,
  );
});

test('rejects a pipeline without the required successful release validation', () => {
  for (const pipelineJobs of [
    [],
    [{ name: 'release_validation', status: 'failed', allow_failure: false }],
    [{ name: 'release_validation', status: 'success', allow_failure: true }],
  ]) {
    assert.throws(
      () => validateReleaseEvidence(releaseMr(), { ...context, pipelineJobs }),
      /release_validation/,
    );
  }
});

test('reads GitLab evidence and resolves only validated commit identities', () => {
  const calls = [];
  const result = readReleaseEvidence('/synthetic/prod', '49', {
    run(command, args) {
      calls.push([command, args]);
      if (command === 'glab' && args[0] === 'mr')
        return JSON.stringify(releaseMr());
      if (command === 'glab') return JSON.stringify(context.pipelineJobs);
      if (args.at(-1) === 'HEAD') return MERGE;
      return TREE;
    },
  });
  assert.deepEqual(result, {
    sourceRevision: SOURCE,
    mergeRevision: MERGE,
    pipelineId: 141,
  });
  assert.deepEqual(calls[0], [
    'glab',
    ['mr', 'view', '49', '--output', 'json'],
  ]);
});

test('rejects a nonnumeric MR before invoking an external command', () => {
  assert.throws(
    () =>
      readReleaseEvidence('/synthetic/prod', '49; unsafe', {
        run: () => assert.fail('must not invoke a command'),
      }),
    /positive integer/,
  );
});
