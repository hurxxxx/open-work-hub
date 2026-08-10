import { execFileSync } from 'node:child_process';

function normalizePath(filePath) {
  return filePath.replace(/\\/g, '/').replace(/^\.\//, '');
}

function normalizeChange(rawChange) {
  if (!rawChange || typeof rawChange !== 'object') {
    throw new Error('Change entries must be objects.');
  }
  const status = String(rawChange.status ?? 'M')
    .trim()
    .toUpperCase();
  const filePath = normalizePath(
    String(rawChange.path ?? rawChange.file ?? '').trim(),
  );
  const previousPath = rawChange.previousPath
    ? normalizePath(String(rawChange.previousPath).trim())
    : null;
  if (!filePath) {
    throw new Error(
      `Change entry is missing a path: ${JSON.stringify(rawChange)}`,
    );
  }
  return {
    status,
    path: filePath,
    previousPath,
  };
}

export function dedupeChanges(changes) {
  const byKey = new Map();
  for (const change of changes.map(normalizeChange)) {
    const key = `${change.status}:${change.previousPath ?? ''}:${change.path}`;
    byKey.set(key, change);
  }
  return [...byKey.values()].sort((left, right) =>
    left.path.localeCompare(right.path),
  );
}

export function runGit(
  args,
  {
    allowFailure = false,
    cwd = process.cwd(),
    execFile = execFileSync,
    gitCommand = 'git',
  } = {},
) {
  return execFile(gitCommand, args, {
    cwd,
    encoding: 'utf8',
    stdio: ['ignore', 'pipe', allowFailure ? 'ignore' : 'pipe'],
  }).trim();
}

function createGitRunner(options = {}) {
  return (args, runOptions = {}) => runGit(args, { ...options, ...runOptions });
}

export function refExists(ref, { git = createGitRunner() } = {}) {
  try {
    git(['rev-parse', '--verify', `${ref}^{commit}`], { allowFailure: true });
    return true;
  } catch {
    return false;
  }
}

export function resolveBaseRef({
  env = process.env,
  explicitBase = null,
  git = createGitRunner(),
} = {}) {
  const candidates = [
    explicitBase,
    env.AI_DO_GUARDRAILS_BASE,
    env.CI_MERGE_REQUEST_DIFF_BASE_SHA,
    env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME
      ? `origin/${env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME}`
      : null,
    'origin/dev',
    'dev',
    'HEAD~1',
  ].filter(Boolean);

  return candidates.find((candidate) => refExists(candidate, { git })) ?? null;
}

export function parseGitNameStatus(output) {
  if (!output.trim()) {
    return [];
  }
  return output
    .split('\n')
    .filter(Boolean)
    .map((line) => {
      const parts = line.split('\t');
      const status = parts[0] ?? 'M';
      if (
        (status.startsWith('R') || status.startsWith('C')) &&
        parts.length >= 3
      ) {
        return { status: status[0], previousPath: parts[1], path: parts[2] };
      }
      return { status: status[0], path: parts[1] };
    });
}

export function collectGitChanges({
  baseRef = null,
  env = process.env,
  git = createGitRunner(),
} = {}) {
  const changes = [];
  const isMergeRequest =
    env.CI_PIPELINE_SOURCE === 'merge_request_event' ||
    Boolean(env.CI_MERGE_REQUEST_IID);
  const expectedDiffBase = env.CI_MERGE_REQUEST_DIFF_BASE_SHA ?? null;
  if (isMergeRequest && !expectedDiffBase) {
    throw new Error(
      'CI_MERGE_REQUEST_DIFF_BASE_SHA is required for MR guardrails. Guardrails refuse a partial change set.',
    );
  }
  if (
    isMergeRequest &&
    expectedDiffBase &&
    !refExists(expectedDiffBase, { git })
  ) {
    throw new Error(
      `MR diff base ${expectedDiffBase} is not available. Fetch full history before running guardrails.`,
    );
  }
  const resolvedBase = resolveBaseRef({ explicitBase: baseRef, env, git });
  if (isMergeRequest && !resolvedBase) {
    throw new Error(
      'Cannot resolve the MR target diff base. Guardrails refuse a partial change set.',
    );
  }

  if (resolvedBase) {
    let diffBase = resolvedBase;
    try {
      diffBase =
        git(['merge-base', resolvedBase, 'HEAD'], { allowFailure: true }) ||
        resolvedBase;
    } catch {
      diffBase = resolvedBase;
    }
    changes.push(
      ...parseGitNameStatus(
        git(['diff', '--name-status', '-M', '-C', `${diffBase}...HEAD`]),
      ),
    );
  }

  changes.push(
    ...parseGitNameStatus(
      git(['diff', '--name-status', '-M', '-C', '--cached']),
    ),
  );
  changes.push(
    ...parseGitNameStatus(git(['diff', '--name-status', '-M', '-C'])),
  );

  const untracked = git(['ls-files', '--others', '--exclude-standard']);
  if (untracked) {
    changes.push(
      ...untracked
        .split('\n')
        .filter(Boolean)
        .map((filePath) => ({
          status: 'A',
          path: filePath,
        })),
    );
  }

  return dedupeChanges(changes);
}

export function createGitChangeSource(options = {}) {
  const git = options.git ?? createGitRunner(options);
  return {
    collect: (context = {}) =>
      collectGitChanges({
        baseRef: context.baseRef ?? options.baseRef ?? null,
        env: context.env ?? options.env ?? process.env,
        git,
      }),
  };
}
