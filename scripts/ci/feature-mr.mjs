#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { createHash } from 'node:crypto';
import fs from 'node:fs';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

import { checkAppPlatformGuardrails } from '../app-platform-guardrails/engine.mjs';
import { parseGitNameStatus } from '../app-platform-guardrails/git-changes.mjs';

const TARGET_BRANCH = 'dev';
const PRODUCTION_BRANCH = 'main';
const MAX_DESCRIPTION_LENGTH = 2700;
const TARGET_REMOTE_REF = `refs/remotes/origin/${TARGET_BRANCH}`;
const CANONICAL_MR_LANES = new Set([
  'app-sandbox',
  'core-platform',
  'harness-and-policy',
]);


function requireArgValue(argv, index, flag) {
  const value = argv[index + 1];
  if (!value || value.startsWith('--')) {
    throw new Error(`${flag} requires a value.`);
  }
  return value;
}

export function parseArgs(argv) {
  const command = argv[0];
  if (!['preflight', 'publish'].includes(command)) {
    throw new Error(
      'Usage: feature-mr.mjs <preflight|publish> --description-file <path> [--title <title>]',
    );
  }

  const options = {
    command,
    descriptionFile: null,
    title: null,
  };
  for (let index = 1; index < argv.length; index += 1) {
    const arg = argv[index];
    if (arg === '--') {
      continue;
    }
    if (arg === '--description-file') {
      options.descriptionFile = requireArgValue(argv, index, arg);
      index += 1;
    } else if (arg === '--title') {
      options.title = requireArgValue(argv, index, arg);
      index += 1;
    } else if (arg === '--help' || arg === '-h') {
      options.help = true;
    } else {
      throw new Error(`Unknown argument: ${arg}`);
    }
  }

  if (options.help) {
    return options;
  }
  if (command === 'publish' && !options.title?.trim()) {
    throw new Error('--title is required for publish.');
  }
  if (!options.descriptionFile) {
    throw new Error('--description-file is required.');
  }
  return options;
}

function allChangePaths(changes) {
  return [
    ...new Set(
      changes.flatMap((change) =>
        [change.previousPath, change.path].filter(Boolean),
      ),
    ),
  ].sort();
}


function guardrailFailureMessage(result) {
  return result.failures
    .map((failure) => {
      const details = [
        failure.message,
        ...(failure.details ?? []),
        ...(failure.hits ?? []).map((hit) => hit.path),
      ];
      return details.filter(Boolean).join(' ');
    })
    .join('\n');
}

export function inferFeatureMrLane(changes, { repoRoot = process.cwd() } = {}) {
  const preliminary = checkAppPlatformGuardrails(changes, {
    env: {},
    repoRoot,
  });
  const lane = preliminary.expectedMergeRequestLane;
  if (!lane || !CANONICAL_MR_LANES.has(lane)) {
    throw new Error(
      'The full target diff does not resolve to one canonical feature MR lane.',
    );
  }
  const label = `lane::${lane}`;
  const result = checkAppPlatformGuardrails(changes, {
    env: {
      CI_PIPELINE_SOURCE: 'merge_request_event',
      CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'local-preflight',
      CI_MERGE_REQUEST_TARGET_BRANCH_NAME: TARGET_BRANCH,
      CI_MERGE_REQUEST_LABELS: label,
    },
    repoRoot,
  });
  if (!result.ok) {
    throw new Error(guardrailFailureMessage(result));
  }
  return { lane, label, result };
}

function hashDescription(description) {
  return createHash('sha256').update(description).digest('hex');
}

function assertCleanWorktree(capture) {
  const status = capture('git', [
    'status',
    '--porcelain',
    '--untracked-files=all',
  ]);
  if (status) {
    throw new Error(
      'Feature MR preflight requires a clean worktree with every source change committed.',
    );
  }
}

function readDescription(descriptionFile, readFile) {
  const description = readFile(descriptionFile, 'utf8');
  if (!description.trim()) {
    throw new Error('MR description is empty.');
  }
  return description;
}

function createDefaultDependencies({
  cwd = process.cwd(),
  env = process.env,
  output = console,
} = {}) {
  return {
    cwd,
    env,
    output,
    readFile: fs.readFileSync,
    capture(command, args, options = {}) {
      return execFileSync(command, args, {
        cwd,
        encoding: 'utf8',
        env: options.env ?? env,
        stdio: ['ignore', 'pipe', 'inherit'],
      }).trim();
    },
    run(command, args, options = {}) {
      output.log(
        `[feature-mr] ${options.displayName ?? [command, ...args].join(' ')}`,
      );
      execFileSync(command, args, {
        cwd,
        env: options.env ?? env,
        stdio: 'inherit',
      });
    },
  };
}

function normalizeDependencies(overrides = {}) {
  const defaults = createDefaultDependencies(overrides);
  return { ...defaults, ...overrides };
}

function requireCurrentFeatureBranch(capture) {
  const branch = capture('git', ['branch', '--show-current']);
  if (!branch) {
    throw new Error('Feature MR preflight does not run from a detached HEAD.');
  }
  if ([TARGET_BRANCH, PRODUCTION_BRANCH].includes(branch)) {
    throw new Error(
      `Feature MR preflight requires a feature branch, not ${branch}.`,
    );
  }
  return branch;
}

function assertTargetIsContained(run) {
  try {
    run(
      'git',
      ['merge-base', '--is-ancestor', `origin/${TARGET_BRANCH}`, 'HEAD'],
      { displayName: `verify HEAD contains current origin/${TARGET_BRANCH}` },
    );
  } catch {
    throw new Error(
      `HEAD must contain the exact current origin/${TARGET_BRANCH} before preflight. Update the branch and rerun.`,
    );
  }
}

function buildSyntheticMrEnv(context, baseEnv) {
  const env = { ...baseEnv };
  for (const key of Object.keys(env)) {
    if (key.startsWith('CI_MERGE_REQUEST_')) {
      delete env[key];
    }
  }
  delete env.AI_DO_ALLOW_REPO_WIDE_REWRITE;
  delete env.AI_DO_CHANGE_LANE;
  delete env.AI_DO_GUARDRAILS_BASE;

  return {
    ...env,
    AI_DO_CHANGE_LANE: context.lane,
    AI_DO_GUARDRAILS_BASE: context.diffBaseSha,
    CI: 'true',
    CI_COMMIT_BRANCH: context.branch,
    CI_COMMIT_REF_NAME: context.branch,
    CI_COMMIT_SHA: context.sourceSha,
    CI_MERGE_REQUEST_DESCRIPTION: context.publishedDescription,
    CI_MERGE_REQUEST_DESCRIPTION_IS_TRUNCATED: 'false',
    CI_MERGE_REQUEST_DIFF_BASE_SHA: context.diffBaseSha,
    CI_MERGE_REQUEST_IID: 'local-preflight',
    CI_MERGE_REQUEST_LABELS: context.label,
    CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: context.branch,
    CI_MERGE_REQUEST_TARGET_BRANCH_NAME: TARGET_BRANCH,
    CI_MERGE_REQUEST_TARGET_BRANCH_SHA: context.targetSha,
    CI_PIPELINE_SOURCE: 'merge_request_event',
  };
}

function inspectRepository(options, dependencies) {
  const { capture, cwd, readFile, run } = dependencies;
  assertCleanWorktree(capture);
  const branch = requireCurrentFeatureBranch(capture);
  run('git', ['fetch', 'origin', `+${TARGET_BRANCH}:${TARGET_REMOTE_REF}`], {
    displayName: `fetch origin/${TARGET_BRANCH}`,
  });
  const sourceSha = capture('git', ['rev-parse', 'HEAD']);
  const targetSha = capture('git', [
    'rev-parse',
    `origin/${TARGET_BRANCH}^{commit}`,
  ]);
  assertTargetIsContained(run);
  const diffBaseSha = capture('git', [
    'merge-base',
    `origin/${TARGET_BRANCH}`,
    'HEAD',
  ]);
  if (diffBaseSha !== targetSha) {
    throw new Error(
      `The diff base ${diffBaseSha} is not the current target head ${targetSha}.`,
    );
  }
  const diffRange = `${diffBaseSha}...HEAD`;
  const changes = parseGitNameStatus(
    capture('git', ['diff', '--name-status', '-M', '-C', diffRange]),
  );
  if (changes.length === 0) {
    throw new Error(
      `There are no committed changes against origin/${TARGET_BRANCH}.`,
    );
  }
  run('git', ['diff', '--check', diffRange], {
    displayName: `git diff --check ${diffRange}`,
  });
  run(
    'git',
    ['merge-tree', '--write-tree', `origin/${TARGET_BRANCH}`, 'HEAD'],
    { displayName: `simulate merge into origin/${TARGET_BRANCH}` },
  );

  const descriptionFile = path.resolve(cwd, options.descriptionFile);
  const description = readDescription(descriptionFile, readFile);
  const laneResult = inferFeatureMrLane(changes, { repoRoot: cwd });
  const publishedDescription = description;
  if (publishedDescription.length > MAX_DESCRIPTION_LENGTH) {
    throw new Error(
      `MR description is ${publishedDescription.length} characters; GitLab evidence is limited to ${MAX_DESCRIPTION_LENGTH}.`,
    );
  }
  return {
    branch,
    changes,
    changedPaths: allChangePaths(changes),
    description,
    descriptionFile,
    descriptionHash: hashDescription(description),
    diffBaseSha,
    label: laneResult.label,
    lane: laneResult.lane,
    publishedDescription,
    sourceSha,
    targetSha,
  };
}

function assertPreflightStateUnchanged(context, dependencies) {
  const { capture, readFile, run } = dependencies;
  assertCleanWorktree(capture);
  const currentSourceSha = capture('git', ['rev-parse', 'HEAD']);
  if (currentSourceSha !== context.sourceSha) {
    throw new Error('HEAD changed while submission checks were running.');
  }
  const description = readDescription(context.descriptionFile, readFile);
  if (hashDescription(description) !== context.descriptionHash) {
    throw new Error(
      'MR description changed while submission checks were running.',
    );
  }
  run('git', ['fetch', 'origin', `+${TARGET_BRANCH}:${TARGET_REMOTE_REF}`], {
    displayName: `recheck origin/${TARGET_BRANCH} after submission checks`,
  });
  const currentTargetSha = capture('git', [
    'rev-parse',
    `origin/${TARGET_BRANCH}^{commit}`,
  ]);
  if (currentTargetSha !== context.targetSha) {
    throw new Error(
      `origin/${TARGET_BRANCH} moved during submission checks. Update the branch and retry.`,
    );
  }
  assertTargetIsContained(run);
}

export function runLocalPreflight(options, dependencyOverrides = {}) {
  const dependencies = normalizeDependencies(dependencyOverrides);
  const context = inspectRepository(options, dependencies);
  const validationPlan = [];

  dependencies.output.log(
    `[feature-mr] computed ${context.label} for ${context.changedPaths.length} changed path(s)`,
  );
  assertPreflightStateUnchanged(context, dependencies);
  dependencies.output.log(
    `[feature-mr] submission checks complete source=${context.sourceSha.slice(0, 8)} target=${context.targetSha.slice(0, 8)} lane=${context.label}; Codex review runs in feature MR CI`,
  );
  return { ...context, validationPlan };
}

function assertPublishedMr(mr, context) {
  const laneLabels = (mr.labels ?? []).filter((label) => /^lane::/.test(label));
  const failures = [];
  if (mr.draft !== false) failures.push('MR is Draft');
  if (mr.source_branch !== context.branch)
    failures.push('source branch changed');
  if (mr.target_branch !== TARGET_BRANCH)
    failures.push('target branch is not dev');
  if (mr.sha !== context.sourceSha) failures.push('source SHA changed');
  if (mr.diff_refs?.head_sha !== context.sourceSha) {
    failures.push('MR diff head SHA changed');
  }
  if (mr.diff_refs?.start_sha !== context.targetSha) {
    failures.push('MR target SHA changed before creation');
  }
  if (mr.description !== context.publishedDescription)
    failures.push('description changed');
  if (laneLabels.length !== 1 || laneLabels[0] !== context.label) {
    failures.push(`lane labels are ${laneLabels.join(', ') || 'missing'}`);
  }
  if (mr.merge_when_pipeline_succeeds === true) {
    failures.push('auto-merge is enabled');
  }
  if (failures.length > 0) {
    throw new Error(
      `Created MR failed post-publish verification: ${failures.join('; ')}.`,
    );
  }
}

function findExistingFeatureMr(context, dependencies) {
  const mergeRequests = JSON.parse(
    dependencies.capture('glab', [
      'mr',
      'list',
      '--source-branch',
      context.branch,
      '--target-branch',
      TARGET_BRANCH,
      '--output',
      'json',
    ]),
  );
  if (!Array.isArray(mergeRequests)) {
    throw new Error('GitLab returned an invalid open MR list.');
  }
  if (mergeRequests.length > 1) {
    throw new Error(
      `Multiple open MRs use ${context.branch}; publisher refuses an ambiguous update.`,
    );
  }
  return mergeRequests[0] ?? null;
}

export function publishFeatureMr(context, options, dependencyOverrides = {}) {
  const dependencies = normalizeDependencies(dependencyOverrides);
  assertPreflightStateUnchanged(context, dependencies);
  const existingMr = findExistingFeatureMr(context, dependencies);
  if (existingMr?.merge_when_pipeline_succeeds === true) {
    throw new Error(
      'The existing MR has auto-merge enabled. Cancel auto-merge and rerun the full local publisher.',
    );
  }
  if (existingMr) {
    const staleLaneArgs = [
      'lane::app-sandbox',
      'lane::core-platform',
      'lane::harness-and-policy',
    ]
      .filter((label) => label !== context.label)
      .flatMap((label) => ['--unlabel', label]);
    dependencies.run(
      'glab',
      [
        'mr',
        'update',
        String(existingMr.iid),
        '--title',
        options.title,
        '--description',
        context.publishedDescription,
        ...staleLaneArgs,
        '--label',
        context.label,
        '--ready',
        '--yes',
      ],
      {
        displayName: `prepare Ready MR !${existingMr.iid} with ${context.label}`,
      },
    );
  }
  dependencies.run(
    'git',
    ['push', '--set-upstream', 'origin', `HEAD:${context.branch}`],
    { displayName: `push validated source ${context.sourceSha.slice(0, 8)}` },
  );
  const pushedSourceSha = dependencies.capture('git', [
    'rev-parse',
    `origin/${context.branch}^{commit}`,
  ]);
  if (pushedSourceSha !== context.sourceSha) {
    throw new Error(
      'The pushed source branch does not match the validated SHA.',
    );
  }
  assertPreflightStateUnchanged(context, dependencies);

  if (!existingMr) {
    dependencies.run(
      'glab',
      [
        'mr',
        'create',
        '--source-branch',
        context.branch,
        '--target-branch',
        TARGET_BRANCH,
        '--title',
        options.title,
        '--description',
        context.publishedDescription,
        '--label',
        context.label,
        '--yes',
      ],
      { displayName: `create Ready MR with ${context.label}` },
    );
  }
  const mr = JSON.parse(
    dependencies.capture('glab', [
      'mr',
      'view',
      String(existingMr?.iid ?? context.branch),
      '--output',
      'json',
    ]),
  );
  assertPublishedMr(mr, context);
  dependencies.output.log(`[feature-mr] published ${mr.web_url}`);
  return mr;
}

export function runFeatureMrCommand(options, dependencyOverrides = {}) {
  const runPreflight =
    dependencyOverrides.runPreflight ??
    ((currentOptions) =>
      runLocalPreflight(currentOptions, dependencyOverrides));
  const publishMr =
    dependencyOverrides.publishMr ??
    ((context, currentOptions) =>
      publishFeatureMr(context, currentOptions, dependencyOverrides));

  const context = runPreflight(options);
  if (options.command === 'preflight') {
    return context;
  }
  return publishMr(context, options);
}

function printHelp(output = console) {
  output.log(`Usage:
  pnpm mr:preflight -- --description-file <path>
  pnpm mr:publish -- --title <title> --description-file <path>

The lane is computed from the complete origin/dev...HEAD diff. Publish performs only
repository-state and merge-simulation checks, pushes the exact source SHA, and creates
or refreshes a Ready MR with one exact lane label. Required validation runs in the
GitLab pipeline, and auto-merge remains disabled.`);
}

export function main(argv = process.argv.slice(2), dependencyOverrides = {}) {
  const output = dependencyOverrides.output ?? console;
  try {
    const options = parseArgs(argv);
    if (options.help) {
      printHelp(output);
      return 0;
    }
    runFeatureMrCommand(options, dependencyOverrides);
    return 0;
  } catch (error) {
    output.error(
      `[feature-mr] ${error instanceof Error ? error.message : String(error)}`,
    );
    return 1;
  }
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  process.exitCode = main();
}
