#!/usr/bin/env node

import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import { parseArgs } from 'node:util';
import { pathToFileURL } from 'node:url';
import { requireDiskHeadroom } from './docker-storage.mjs';

export const MARKER = '<!-- open-work-hub:release-validation:v1';
export const LIMITS = Object.freeze({ files: 40, lines: 1000 });
const SHA = /^[0-9a-f]{40}$/;
const REPORT = 'release-validation-context.md';
const FULL_SUITES = [
  'ci:harness',
  'ci:python-contract-guardrails',
  'ci:contract',
  'ci:api:full',
  'ci:web',
];

// Changes to the selector or its execution contract cannot select their own shortcut.
const RELEASE_CONTROLS = new Set([
  '.gitlab-ci.yml',
  'ops/ci/ci-first.gitlab-ci.yml',
  'scripts/release-validation.mjs',
  'scripts/release-validation.test.mjs',
  'scripts/check-gitlab-pipeline.mjs',
  'scripts/check-gitlab-pipeline.test.mjs',
  'scripts/check-mr-target-policy.mjs',
  'scripts/check-mr-target-policy.test.mjs',
  'scripts/check-mr-contract-evidence.mjs',
  'scripts/check-mr-contract-evidence.test.mjs',
]);
const HARNESS_FILES = new Set([
  'scripts/codex-hooks.mjs',
  'scripts/codex-hooks.test.mjs',
  'scripts/agent-guidance-eval.mjs',
  'scripts/agent-guidance-eval.test.mjs',
  'scripts/check-skill-harness.py',
  'scripts/setup-claude-skills.mjs',
  'scripts/setup-claude-skills.test.mjs',
  'scripts/tests/test_skill_harness.py',
  'scripts/tests/test_docs_reader.py',
  'scripts/tests/test_env_helpers.py',
  'scripts/codex-review-ci.sh',
  'scripts/codex-review-ci.test.mjs',
  'scripts/install-codex-review-runner-entrypoint.sh',
]);

function surface(file) {
  if (RELEASE_CONTROLS.has(file)) return null;
  if (
    HARNESS_FILES.has(file) ||
    file.startsWith('.agents/skills/') ||
    file.startsWith('.codex/') ||
    file.startsWith('.claude/')
  )
    return 'harness';
  if (
    /^(?:AGENTS|CLAUDE|README)\.md$/.test(file) ||
    file === '.github/copilot-instructions.md' ||
    /^(?:apps|packages)\/[^/]+\/(?:AGENTS|CLAUDE|README)\.md$/.test(file) ||
    /^(?:docs|adr|\.gitlab)\/.+\.md$/.test(file)
  )
    return 'docs';
  return null;
}

function git(args, cwd) {
  try {
    return execFileSync('git', args, {
      cwd,
      encoding: 'utf8',
      maxBuffer: 16 * 1024 * 1024,
      stdio: ['ignore', 'pipe', 'pipe'],
      timeout: 60_000,
    });
  } catch {
    throw new Error(
      'Git snapshot/freshness check failed; refresh the release refs and retry.',
    );
  }
}

export function resolveCommit(ref, cwd = process.cwd()) {
  const sha = git(
    ['rev-parse', '--verify', '--end-of-options', `${ref}^{commit}`],
    cwd,
  ).trim();
  if (!SHA.test(sha)) throw new Error('Expected a full commit SHA.');
  return sha;
}

export function collectChanges(base, head, cwd = process.cwd()) {
  const args = ['diff', '--no-ext-diff', '--no-textconv', '--no-renames'];
  const raw = git([...args, '--raw', '-z', base, head, '--'], cwd).split('\0');
  const stats = new Map(
    git([...args, '--numstat', '-z', base, head, '--'], cwd)
      .split('\0')
      .filter(Boolean)
      .map((entry) => {
        const match = /^(\d+|-)\t(\d+|-)\t([\s\S]+)$/.exec(entry);
        if (!match) throw new Error('Unrecognized diff statistics.');
        return [
          match[3],
          match[1] === '-' || match[2] === '-'
            ? null
            : Number(match[1]) + Number(match[2]),
        ];
      }),
  );
  const changes = [];
  for (let index = 0; index < raw.length - 1; index += 2) {
    const match = /^:(\d{6}) (\d{6}) [0-9a-f]+ [0-9a-f]+ ([AMDT])$/.exec(
      raw[index],
    );
    const file = raw[index + 1];
    if (!match || !stats.has(file)) throw new Error('Unrecognized diff entry.');
    changes.push({
      path: file,
      oldMode: match[1],
      newMode: match[2],
      lines: stats.get(file),
    });
  }
  if (changes.length !== stats.size)
    throw new Error('Incomplete diff metadata.');
  return changes;
}

export function selectValidation({ mode = 'full', changes = [] } = {}) {
  if (!['full', 'fast'].includes(mode))
    throw new Error('Validation mode must be full or fast.');
  const reasons = [];
  if (mode === 'full')
    reasons.push(
      'No valid explicit fast request; full validation is the default.',
    );
  if (changes.length === 0) reasons.push('Empty release diff.');
  if (
    changes.length > LIMITS.files ||
    changes.reduce((sum, change) => sum + (change.lines ?? 0), 0) > LIMITS.lines
  ) {
    reasons.push('Change exceeds the bounded fast-validation size limit.');
  }
  for (const change of changes) {
    const file = change.path;
    const unsafePath =
      !file ||
      /[\x00-\x1f\x7f\\]/.test(file) ||
      file.split('/').some((part) => !part || part === '.' || part === '..');
    const modes = [change.oldMode, change.newMode];
    const regular = modes.every((value) =>
      ['000000', '100644', '100755'].includes(value),
    );
    const modeChange = !modes.includes('000000') && modes[0] !== modes[1];
    if (
      unsafePath ||
      !regular ||
      modeChange ||
      change.lines === null ||
      !Number.isSafeInteger(change.lines) ||
      change.lines < 0 ||
      !surface(file)
    ) {
      // Paths only, never file contents or Git output (which may contain secrets).
      reasons.push(
        `Full validation required for ${JSON.stringify(file)} (runtime, control, unknown, binary or mode change).`,
      );
    }
  }
  const effectiveMode = reasons.length ? 'full' : 'fast';
  const checks =
    effectiveMode === 'full'
      ? ['ci:all']
      : changes.some((change) => surface(change.path) === 'harness')
        ? ['ci:harness']
        : ['check:skills', 'test:skill-harness', 'test:claude-skills'];
  return {
    requestedMode: mode,
    mode: effectiveMode,
    reasons,
    checks,
    skipped:
      effectiveMode === 'full'
        ? []
        : FULL_SUITES.filter((suite) => !checks.includes(suite)),
  };
}

export function fastRequest({
  description = '',
  truncated = false,
  source,
  target,
}) {
  const firstLine = description.split(/\r?\n/, 1)[0];
  const expected = `${MARKER} mode=fast source=${source} target=${target} -->`;
  const valid =
    SHA.test(source ?? '') &&
    SHA.test(target ?? '') &&
    !truncated &&
    firstLine === expected &&
    description.split(MARKER).length === 2;
  return valid ? 'fast' : 'full';
}

export function renderEvidence(plan, results = [], status = 'pending') {
  return [
    '# Release validation',
    '',
    `Source: ${plan.source}`,
    `Target: ${plan.target}`,
    `Merge tree: ${plan.mergeTree}`,
    `Requested: ${plan.requestedMode}`,
    `Selected: ${plan.mode}`,
    `Status: ${status}`,
    '',
    '## Selection',
    '',
    ...(plan.reasons.length
      ? plan.reasons
      : ['Bounded non-runtime diff; explicit SHA-bound fast request.']
    ).map((reason) => `- ${reason}`),
    '',
    '## Checks',
    '',
    ...results.map((result) => `- ${result.command}: ${result.status}`),
    '',
    '## Skipped suites',
    '',
    ...(plan.skipped.length
      ? plan.skipped.map(
          (suite) =>
            `- ${suite}: no application/runtime change; focused checks selected.`,
        )
      : ['- None.']),
    '',
    'Production source/env, image, migration, rollback and smoke gates are unchanged.',
    '',
  ].join('\n');
}

export function executePlan(plan, { run, record, fresh, preflight }) {
  const results = [];
  record(renderEvidence(plan, results));
  try {
    if (preflight) {
      const result = {
        command: 'storage headroom preflight',
        status: 'failed',
      };
      results.push(result);
      preflight();
      result.status = 'passed';
    }
    const commands = [
      ['git', ['diff', '--check', plan.target, plan.source, '--']],
      ...plan.checks.map((check) => ['pnpm', [check]]),
    ];
    for (const [command, args] of commands) {
      const ok = run(command, args) === 0;
      results.push({
        command: [command, ...args].join(' '),
        status: ok ? 'passed' : 'failed',
      });
      record(renderEvidence(plan, results));
      if (!ok)
        throw new Error(`Release check failed: ${command} ${args.join(' ')}`);
    }
    fresh();
    record(renderEvidence(plan, results, 'passed'));
  } catch (error) {
    record(renderEvidence(plan, results, 'failed'));
    throw error;
  }
}

function snapshot(base, head, mode, cwd) {
  const target = resolveCommit(base, cwd);
  const source = resolveCommit(head, cwd);
  const mergeTree = git(
    ['merge-tree', '--write-tree', target, source],
    cwd,
  ).trim();
  if (mergeTree !== git(['rev-parse', `${source}^{tree}`], cwd).trim()) {
    throw new Error(
      'Source does not represent the merge result; synchronize dev with main before validation.',
    );
  }
  return {
    source,
    target,
    mergeTree,
    ...selectValidation({
      mode,
      changes: collectChanges(target, source, cwd),
    }),
  };
}

export function runCi({ env = process.env, cwd = process.cwd() } = {}) {
  if (
    env.CI_PIPELINE_SOURCE !== 'merge_request_event' ||
    env.CI_MERGE_REQUEST_SOURCE_BRANCH_NAME !== 'dev' ||
    env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME !== 'main' ||
    !env.CI_PROJECT_ID ||
    env.CI_MERGE_REQUEST_SOURCE_PROJECT_ID !== env.CI_PROJECT_ID ||
    !SHA.test(env.CI_COMMIT_SHA ?? '')
  )
    throw new Error('Expected a same-project dev -> main release job.');
  const refresh = () =>
    git(
      [
        'fetch',
        '--no-tags',
        'origin',
        '+refs/heads/dev:refs/remotes/origin/dev',
        '+refs/heads/main:refs/remotes/origin/main',
      ],
      cwd,
    );
  refresh();
  const target = resolveCommit('origin/main', cwd);
  const source = resolveCommit('origin/dev', cwd);
  const mode =
    env.CI_MERGE_REQUEST_EVENT_TYPE === 'detached'
      ? fastRequest({
          source,
          target,
          description: env.CI_MERGE_REQUEST_DESCRIPTION,
          truncated: env.CI_MERGE_REQUEST_DESCRIPTION_IS_TRUNCATED === 'true',
        })
      : 'full';
  // Full/merged-result pipelines must still validate the exact current merge surface.
  const plan = snapshot(target, env.CI_COMMIT_SHA, mode, cwd);
  const fresh = () => {
    git(['diff', '--quiet', 'HEAD', '--'], cwd);
    if (
      resolveCommit('HEAD', cwd) !== plan.source ||
      resolveCommit('origin/dev', cwd) !== source ||
      resolveCommit('origin/main', cwd) !== target ||
      (env.CI_MERGE_REQUEST_EVENT_TYPE === 'detached' &&
        source !== plan.source) ||
      git(['merge-tree', '--write-tree', target, source], cwd).trim() !==
        plan.mergeTree
    ) {
      throw new Error(
        'Release source/target changed or pipeline is stale; create a fresh pipeline.',
      );
    }
  };
  fresh();
  console.log(
    `[release-validation] ${plan.mode}; selected: ${plan.checks.join(', ')}`,
  );
  executePlan(plan, {
    preflight: () => requireDiskHeadroom(cwd),
    run: (command, args) =>
      spawnSync(command, args, { cwd, env, stdio: 'inherit' }).status,
    record: (evidence) => {
      const fd = fs.openSync(
        `${cwd}/${REPORT}`,
        fs.constants.O_WRONLY |
          fs.constants.O_CREAT |
          fs.constants.O_TRUNC |
          fs.constants.O_NOFOLLOW,
        0o600,
      );
      try {
        fs.writeFileSync(fd, evidence);
      } finally {
        fs.closeSync(fd);
      }
    },
    fresh: () => {
      refresh();
      fresh();
    },
  });
}

export function main(args = process.argv.slice(2)) {
  const { values, positionals } = parseArgs({
    args,
    allowPositionals: true,
    options: {
      base: { type: 'string', default: 'origin/main' },
      head: { type: 'string', default: 'HEAD' },
      mode: { type: 'string', default: 'full' },
      help: { type: 'boolean' },
    },
  });
  if (values.help) {
    console.log(
      'node scripts/release-validation.mjs plan [--base origin/main] [--head HEAD] [--mode full|fast]\nnode scripts/release-validation.mjs ci\nPlan is read-only and covers committed snapshots, not dirty/untracked work.',
    );
  } else if (positionals.length === 1 && positionals[0] === 'plan') {
    const plan = snapshot(values.base, values.head, values.mode, process.cwd());
    console.log(JSON.stringify(plan, null, 2));
    if (plan.requestedMode === 'fast')
      console.log(
        `${MARKER} mode=fast source=${plan.source} target=${plan.target} -->`,
      );
  } else if (
    positionals.length === 1 &&
    positionals[0] === 'ci' &&
    args.length === 1
  ) {
    runCi();
  } else throw new Error('Use plan or ci; see --help.');
}

if (
  process.argv[1] &&
  import.meta.url === pathToFileURL(process.argv[1]).href
) {
  try {
    main();
  } catch (error) {
    console.error(`[release-validation] ${error.message}`);
    process.exitCode = 1;
  }
}
