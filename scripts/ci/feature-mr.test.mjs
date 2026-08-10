import assert from 'node:assert/strict';
import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import { evaluateFeatureMrPreflightReceipt } from '../check-feature-mr-preflight-receipt.mjs';
import {
  attachLocalPreflightReceipt,
  verifyLocalPreflightReceipt,
} from './feature-mr-receipt.mjs';
import {
  inferFeatureMrLane,
  parseArgs,
  publishFeatureMr,
  runFeatureMrCommand,
  runLocalPreflight,
} from './feature-mr.mjs';

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '../..',
);
const silentOutput = {
  error: () => undefined,
  log: () => undefined,
};

test('feature MR arguments do not accept a manually selected lane', () => {
  assert.throws(
    () =>
      parseArgs([
        'publish',
        '--lane',
        'app-sandbox',
        '--title',
        'Example',
        '--description-file',
        '/tmp/mr.md',
      ]),
    /Unknown argument: --lane/,
  );
});

test('publish requires an explicit title and description file', () => {
  assert.throws(
    () => parseArgs(['publish', '--description-file', '/tmp/mr.md']),
    /--title is required/,
  );
  assert.throws(
    () => parseArgs(['publish', '--title', 'Example']),
    /--description-file is required/,
  );
});

test('documented pnpm argument separator reaches the feature MR CLI', () => {
  const output = execFileSync('pnpm', ['mr:preflight', '--', '--help'], {
    cwd: repoRoot,
    encoding: 'utf8',
  });

  assert.match(output, /pnpm mr:publish/);
});

test('lane inference maps app-only changes to App Sandbox', () => {
  const result = inferFeatureMrLane(
    [
      {
        status: 'M',
        path: 'apps/web/src/app-modules/management-tasks/views/HealthCheckupView.tsx',
      },
    ],
    { repoRoot },
  );

  assert.equal(result.lane, 'app-sandbox');
  assert.equal(result.label, 'lane::app-sandbox');
});

test('lane inference catches central app i18n as Core Platform before MR creation', () => {
  const result = inferFeatureMrLane(
    [
      {
        status: 'M',
        path: 'apps/web/src/app-modules/management-tasks/views/HealthCheckupView.tsx',
      },
      {
        status: 'M',
        path: 'apps/web/src/platform/i18n/resources.ts',
      },
    ],
    { repoRoot },
  );

  assert.equal(result.lane, 'core-platform');
  assert.equal(result.label, 'lane::core-platform');
});

test('lane inference rejects app delivery mixed with harness policy', () => {
  assert.throws(
    () =>
      inferFeatureMrLane(
        [
          {
            status: 'M',
            path: 'apps/web/src/app-modules/management-tasks/views/HealthCheckupView.tsx',
          },
          { status: 'M', path: 'CLAUDE.md' },
        ],
        { repoRoot },
      ),
    /must not share a merge request/,
  );
});

test('preflight receipt binds the source, target, lane, and description', () => {
  const context = {
    description: 'Complete evidence',
    label: 'lane::app-sandbox',
    sourceSha: 'a'.repeat(40),
    targetSha: 'b'.repeat(40),
  };
  const description = attachLocalPreflightReceipt(context);

  assert.equal(
    verifyLocalPreflightReceipt({ ...context, description }).ok,
    true,
  );
  assert.equal(
    verifyLocalPreflightReceipt({
      ...context,
      description,
      sourceSha: 'c'.repeat(40),
    }).ok,
    false,
  );
  assert.equal(
    evaluateFeatureMrPreflightReceipt({
      CI_COMMIT_SHA: context.sourceSha,
      CI_MERGE_REQUEST_DESCRIPTION: context.description,
      CI_MERGE_REQUEST_DESCRIPTION_IS_TRUNCATED: 'false',
      CI_MERGE_REQUEST_DIFF_BASE_SHA: context.targetSha,
      CI_MERGE_REQUEST_IID: '1',
      CI_MERGE_REQUEST_LABELS: context.label,
      CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'feature/direct',
      CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
      CI_PIPELINE_SOURCE: 'merge_request_event',
    }).ok,
    false,
  );
});

test('repository instructions retain the canonical local-first MR publisher contract', () => {
  const packageJson = JSON.parse(
    fs.readFileSync(path.join(repoRoot, 'package.json'), 'utf8'),
  );
  assert.equal(
    packageJson.scripts['mr:preflight'],
    'node scripts/ci/feature-mr.mjs preflight',
  );
  assert.equal(
    packageJson.scripts['mr:publish'],
    'node scripts/ci/feature-mr.mjs publish',
  );
  assert.equal(
    packageJson.scripts['check:feature-mr-preflight-receipt'],
    'node scripts/check-feature-mr-preflight-receipt.mjs',
  );

  const canonicalCommand =
    'pnpm mr:publish -- --title "<title>" --description-file /tmp/ai-do-mr.md';
  for (const relativePath of [
    'CLAUDE.md',
    'agents.md',
    'docs/agents/vibe-coding-harness.md',
    '.agents/skills/ai-do-vibe-app-delivery/SKILL.md',
  ]) {
    const instructions = fs.readFileSync(
      path.join(repoRoot, relativePath),
      'utf8',
    );
    assert.ok(
      instructions.includes(canonicalCommand),
      `${relativePath} is missing the canonical feature MR publisher`,
    );
    assert.match(instructions, /auto-merge/);
  }

  const claudeInstructions = fs.readFileSync(
    path.join(repoRoot, 'CLAUDE.md'),
    'utf8',
  );
  assert.match(claudeInstructions, /glab mr create/);
  assert.match(claudeInstructions, /lane을\s+수동\s+선택/);
  assert.match(claudeInstructions, /실패했거나 실행하지 않았으면/);

  const template = fs.readFileSync(
    path.join(repoRoot, '.gitlab/merge_request_templates/Vibe_Domain_App.md'),
    'utf8',
  );
  const templateWithReceipt = attachLocalPreflightReceipt({
    description: template,
    label: 'lane::app-sandbox',
    sourceSha: 'a'.repeat(40),
    targetSha: 'b'.repeat(40),
  });
  assert.ok(templateWithReceipt.length <= 2700);
});

test('publisher never creates an MR when local preflight fails', () => {
  const events = [];

  assert.throws(
    () =>
      runFeatureMrCommand(
        {
          command: 'publish',
          title: 'Example',
          descriptionFile: '/tmp/mr.md',
        },
        {
          runPreflight() {
            events.push('preflight');
            throw new Error('lane mismatch');
          },
          publishMr() {
            events.push('publish');
          },
        },
      ),
    /lane mismatch/,
  );
  assert.deepEqual(events, ['preflight']);
});

test('publisher creates a Ready MR after lightweight submission checks', () => {
  const events = [];
  const context = {
    branch: 'feature/example',
    description: 'complete',
    label: 'lane::app-sandbox',
    lane: 'app-sandbox',
    sourceSha: 'a'.repeat(40),
    targetSha: 'b'.repeat(40),
  };

  const result = runFeatureMrCommand(
    {
      command: 'publish',
      title: 'Example',
      descriptionFile: '/tmp/mr.md',
    },
    {
      runPreflight() {
        events.push('preflight');
        return context;
      },
      publishMr(receivedContext, options) {
        events.push('publish');
        assert.equal(receivedContext, context);
        assert.equal(options.title, 'Example');
        return { draft: false, web_url: 'http://gitlab.example/mr/1' };
      },
    },
  );

  assert.deepEqual(events, ['preflight', 'publish']);
  assert.equal(result.draft, false);
});

function createRepositoryFakes({
  branch = 'feature/example',
  changedFile = 'apps/web/src/platform/i18n/resources.ts',
  description = 'complete description',
  sourceSha = 'a'.repeat(40),
  targetSha = 'b'.repeat(40),
} = {}) {
  const events = [];
  const capture = (command, args) => {
    const invocation = [command, ...args].join(' ');
    events.push(`capture:${invocation}`);
    if (invocation === 'git status --porcelain --untracked-files=all') {
      return '';
    }
    if (invocation === 'git branch --show-current') {
      return branch;
    }
    if (invocation === 'git rev-parse HEAD') {
      return sourceSha;
    }
    if (invocation === 'git rev-parse origin/dev^{commit}') {
      return targetSha;
    }
    if (invocation === `git rev-parse origin/${branch}^{commit}`) {
      return sourceSha;
    }
    if (invocation === 'git merge-base origin/dev HEAD') {
      return targetSha;
    }
    if (invocation === `git diff --name-status -M -C ${targetSha}...HEAD`) {
      return `M\t${changedFile}`;
    }
    throw new Error(`Unexpected capture: ${invocation}`);
  };
  const run = (command, args, options = {}) => {
    events.push({
      type: 'run',
      invocation: [command, ...args].join(' '),
      options,
    });
  };
  return {
    branch,
    capture,
    changedFile,
    description,
    events,
    readFile: () => description,
    run,
    sourceSha,
    targetSha,
  };
}

function preflightDependencies(fakes) {
  return {
    ...fakes,
    cwd: repoRoot,
    env: { PATH: process.env.PATH },
    output: silentOutput,
  };
}

function appSandboxContext(fakes) {
  const label = 'lane::app-sandbox';
  return {
    branch: fakes.branch,
    changedPaths: [fakes.changedFile],
    description: fakes.description,
    descriptionFile: '/tmp/mr.md',
    descriptionHash: createHash('sha256')
      .update(fakes.description)
      .digest('hex'),
    diffBaseSha: fakes.targetSha,
    label,
    lane: 'app-sandbox',
    publishedDescription: fakes.description,
    sourceSha: fakes.sourceSha,
    targetSha: fakes.targetSha,
  };
}

test('real preflight rejects a dirty worktree before validation or publish', () => {
  const fakes = createRepositoryFakes();
  const originalCapture = fakes.capture;
  fakes.capture = (command, args) => {
    if (
      [command, ...args].join(' ') ===
      'git status --porcelain --untracked-files=all'
    ) {
      return ' M apps/web/src/example.ts';
    }
    return originalCapture(command, args);
  };

  assert.throws(
    () =>
      runFeatureMrCommand(
        {
          command: 'publish',
          descriptionFile: '/tmp/mr.md',
          title: 'Example',
        },
        preflightDependencies(fakes),
      ),
    /clean worktree/,
  );
  assert.equal(
    fakes.events.some(
      (event) =>
        typeof event === 'object' &&
        /^(pnpm|glab)|git push/.test(event.invocation),
    ),
    false,
  );
});

test('local submission preparation does not run dependency or test commands', () => {
  const fakes = createRepositoryFakes();
  const context = runLocalPreflight(
    {
      command: 'preflight',
      descriptionFile: '/tmp/mr.md',
      title: null,
    },
    preflightDependencies(fakes),
  );
  const invocations = fakes.events
    .filter((event) => typeof event === 'object')
    .map((event) => event.invocation);
  assert.deepEqual(context.validationPlan, []);
  assert.equal(invocations.some((invocation) => invocation.startsWith('pnpm ')), false);
});

test('target movement after validation invalidates preflight before publish', () => {
  const fakes = createRepositoryFakes();
  const originalCapture = fakes.capture;
  let targetReads = 0;
  fakes.capture = (command, args) => {
    if ([command, ...args].join(' ') === 'git rev-parse origin/dev^{commit}') {
      targetReads += 1;
      return targetReads === 1 ? fakes.targetSha : 'c'.repeat(40);
    }
    return originalCapture(command, args);
  };

  assert.throws(
    () =>
      runFeatureMrCommand(
        {
          command: 'publish',
          descriptionFile: '/tmp/mr.md',
          title: 'Example',
        },
        preflightDependencies(fakes),
      ),
    /origin\/dev moved during submission checks/,
  );
});

test('source movement after validation invalidates preflight before publish', () => {
  const fakes = createRepositoryFakes();
  const originalCapture = fakes.capture;
  let sourceReads = 0;
  fakes.capture = (command, args) => {
    if ([command, ...args].join(' ') === 'git rev-parse HEAD') {
      sourceReads += 1;
      return sourceReads === 1 ? fakes.sourceSha : 'c'.repeat(40);
    }
    return originalCapture(command, args);
  };

  assert.throws(
    () =>
      runFeatureMrCommand(
        {
          command: 'publish',
          descriptionFile: '/tmp/mr.md',
          title: 'Example',
        },
        preflightDependencies(fakes),
      ),
    /HEAD changed/,
  );
});

test('description movement after validation invalidates preflight before publish', () => {
  const fakes = createRepositoryFakes();
  let descriptionReads = 0;
  fakes.readFile = () => {
    descriptionReads += 1;
    return descriptionReads === 1
      ? fakes.description
      : `${fakes.description} changed`;
  };

  assert.throws(
    () =>
      runFeatureMrCommand(
        {
          command: 'publish',
          descriptionFile: '/tmp/mr.md',
          title: 'Example',
        },
        preflightDependencies(fakes),
      ),
    /description changed/,
  );
});

test('merge simulation failure prevents validation and publish', () => {
  const fakes = createRepositoryFakes();
  const originalRun = fakes.run;
  fakes.run = (command, args, options) => {
    originalRun(command, args, options);
    if ([command, ...args].join(' ').startsWith('git merge-tree ')) {
      throw new Error('merge conflict');
    }
  };

  assert.throws(
    () =>
      runFeatureMrCommand(
        {
          command: 'publish',
          descriptionFile: '/tmp/mr.md',
          title: 'Example',
        },
        preflightDependencies(fakes),
      ),
    /merge conflict/,
  );
  assert.equal(
    fakes.events.some(
      (event) =>
        typeof event === 'object' &&
        /^(pnpm|glab)|git push/.test(event.invocation),
    ),
    false,
  );
});

test('local preflight computes MR metadata without running validation', () => {
  const fakes = createRepositoryFakes();
  const context = runLocalPreflight(
    {
      command: 'preflight',
      descriptionFile: '/tmp/mr.md',
      title: null,
    },
    preflightDependencies(fakes),
  );

  assert.equal(context.label, 'lane::core-platform');
  const validationRuns = fakes.events.filter(
    (event) =>
      typeof event === 'object' &&
      event.type === 'run' &&
      event.invocation.startsWith('pnpm '),
  );
  assert.deepEqual(validationRuns, []);
  assert.deepEqual(context.validationPlan, []);
  assert.equal(context.publishedDescription, fakes.description);
});

test('real publisher uses exact source SHA, Ready state, and computed lane without auto-merge', () => {
  const fakes = createRepositoryFakes({
    changedFile:
      'apps/web/src/app-modules/management-tasks/views/HealthCheckupView.tsx',
  });
  const context = appSandboxContext(fakes);
  const originalCapture = fakes.capture;
  fakes.capture = (command, args) => {
    if (command === 'glab') {
      if (args[1] === 'list') {
        return '[]';
      }
      return JSON.stringify({
        description: context.publishedDescription,
        diff_refs: {
          head_sha: context.sourceSha,
          start_sha: context.targetSha,
        },
        draft: false,
        labels: [context.label],
        merge_when_pipeline_succeeds: false,
        sha: context.sourceSha,
        source_branch: context.branch,
        target_branch: 'dev',
        web_url: 'http://gitlab.example/mr/1',
      });
    }
    return originalCapture(command, args);
  };

  const mr = publishFeatureMr(
    context,
    { title: 'Example' },
    preflightDependencies(fakes),
  );

  const runs = fakes.events
    .filter((event) => typeof event === 'object' && event.type === 'run')
    .map((event) => event.invocation);
  const createInvocation = runs.find((invocation) =>
    invocation.startsWith('glab mr create '),
  );
  assert.ok(createInvocation);
  assert.doesNotMatch(createInvocation, /--draft/);
  assert.match(createInvocation, /--yes$/);
  assert.match(createInvocation, /--label lane::app-sandbox/);
  assert.doesNotMatch(createInvocation, /auto-merge/);
  assert.ok(
    runs.indexOf(`git push --set-upstream origin HEAD:${context.branch}`) <
      runs.indexOf(createInvocation),
  );
  assert.equal(mr.draft, false);
});

test('existing auto-merge prevents branch push and MR refresh', () => {
  const fakes = createRepositoryFakes({
    changedFile:
      'apps/web/src/app-modules/management-tasks/views/HealthCheckupView.tsx',
  });
  const context = appSandboxContext(fakes);
  const originalCapture = fakes.capture;
  fakes.capture = (command, args) => {
    if (command === 'glab' && args[1] === 'list') {
      return JSON.stringify([
        {
          draft: false,
          iid: 248,
          merge_when_pipeline_succeeds: true,
          source_branch: context.branch,
          target_branch: 'dev',
        },
      ]);
    }
    return originalCapture(command, args);
  };

  assert.throws(
    () =>
      publishFeatureMr(
        context,
        { title: 'Example' },
        preflightDependencies(fakes),
      ),
    /auto-merge enabled/,
  );
  assert.equal(
    fakes.events.some(
      (event) =>
        typeof event === 'object' && event.invocation.startsWith('git push '),
    ),
    false,
  );
});

test('existing MR is refreshed before the validated push starts its pipeline', () => {
  const fakes = createRepositoryFakes({
    changedFile:
      'apps/web/src/app-modules/management-tasks/views/HealthCheckupView.tsx',
  });
  const context = appSandboxContext(fakes);
  const originalCapture = fakes.capture;
  fakes.capture = (command, args) => {
    if (command === 'glab' && args[1] === 'list') {
      return JSON.stringify([
        {
          draft: false,
          iid: 248,
          merge_when_pipeline_succeeds: false,
          source_branch: context.branch,
          target_branch: 'dev',
        },
      ]);
    }
    if (command === 'glab' && args[1] === 'view') {
      return JSON.stringify({
        description: context.publishedDescription,
        diff_refs: {
          head_sha: context.sourceSha,
          start_sha: context.targetSha,
        },
        draft: false,
        labels: [context.label],
        merge_when_pipeline_succeeds: false,
        sha: context.sourceSha,
        source_branch: context.branch,
        target_branch: 'dev',
        web_url: 'http://gitlab.example/mr/248',
      });
    }
    return originalCapture(command, args);
  };

  publishFeatureMr(context, { title: 'Example' }, preflightDependencies(fakes));

  const invocations = fakes.events
    .filter((event) => typeof event === 'object')
    .map((event) => event.invocation);
  const pushIndex = invocations.indexOf(
    `git push --set-upstream origin HEAD:${context.branch}`,
  );
  const updateIndex = invocations.findIndex((invocation) =>
    invocation.startsWith('glab mr update 248 '),
  );
  assert.ok(updateIndex >= 0);
  assert.ok(updateIndex < pushIndex);
  assert.equal(
    invocations[updateIndex].includes(`--unlabel ${context.label}`),
    false,
  );
  assert.equal(
    invocations[updateIndex].includes('--unlabel lane::core-platform'),
    true,
  );
  assert.equal(
    invocations[updateIndex].includes('--unlabel lane::harness-and-policy'),
    true,
  );
  assert.equal(
    invocations.some((invocation) => invocation.startsWith('glab mr create ')),
    false,
  );
});
