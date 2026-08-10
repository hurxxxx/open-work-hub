#!/usr/bin/env node

import { execFileSync, spawnSync } from 'node:child_process';
import fs from 'node:fs';
import path from 'node:path';
import process from 'node:process';
import { fileURLToPath } from 'node:url';

import {
  applyApiRegressionTier,
  applyExternalReleaseCanary,
  createApiTestExecutionPlan,
  requiresFullMigrationRegression,
  selectAffectedApiPytests,
} from './api-test-selection.mjs';
import { readAppManifestContracts } from './app-platform-guardrails/manifest.mjs';
import { parseGitNameStatus } from './app-platform-guardrails/git-changes.mjs';

const repoRoot = path.resolve(
  path.dirname(fileURLToPath(import.meta.url)),
  '..',
);
const apiRoot = path.join(repoRoot, 'apps/api');
const criticalManifestPath = path.join(
  repoRoot,
  'scripts/api-critical-test-manifest.txt',
);
const externalReleaseCanaryManifestPath = path.join(
  repoRoot,
  'scripts/api-release-external-canary-manifest.txt',
);
const lane = process.argv[2] ?? 'standard';
const selectOnly = process.argv.includes('--select-only');
const planJson = process.argv.includes('--plan-json');
if (!['standard', 'slow', 'migration', 'external'].includes(lane)) {
  console.error(
    'usage: run-affected-api-tests.mjs [standard|slow|migration|external] [--select-only|--plan-json]',
  );
  process.exit(2);
}

function git(args, { allowFailure = false } = {}) {
  try {
    return execFileSync('git', args, {
      cwd: repoRoot,
      encoding: 'utf8',
      stdio: ['ignore', 'pipe', allowFailure ? 'ignore' : 'inherit'],
    }).trim();
  } catch (error) {
    if (allowFailure) {
      return '';
    }
    throw error;
  }
}

function validCommit(ref) {
  if (!ref || /^0+$/.test(ref)) {
    return false;
  }
  try {
    execFileSync('git', ['cat-file', '-e', `${ref}^{commit}`], {
      cwd: repoRoot,
      stdio: 'ignore',
    });
    return true;
  } catch {
    return false;
  }
}

function collectChanges(env = process.env) {
  if (env.CI_PIPELINE_SOURCE === 'schedule') {
    return [];
  }
  const head = env.CI_COMMIT_SHA ?? 'HEAD';
  const isMergeRequest = env.CI_PIPELINE_SOURCE === 'merge_request_event';
  const base = isMergeRequest
    ? env.CI_MERGE_REQUEST_DIFF_BASE_SHA
    : env.CI_COMMIT_BEFORE_SHA;
  if (env.CI && (!validCommit(base) || !validCommit(head))) {
    return null;
  }
  if (base) {
    const range = isMergeRequest ? `${base}...${head}` : `${base}..${head}`;
    return parseGitNameStatus(
      git(['diff', '--name-status', '-M', '-C', range]),
    );
  }

  const changes = parseGitNameStatus(
    git(['diff', '--name-status', '-M', '-C', 'HEAD']),
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
  return changes;
}

function containsPytestMarker(testPath, marker) {
  const source = fs.readFileSync(path.join(repoRoot, testPath), 'utf8');
  return source.includes(`pytest.mark.${marker}`);
}

function containsPytestItem(testPath) {
  const source = fs.readFileSync(path.join(repoRoot, testPath), 'utf8');
  return /^\s*(?:async\s+)?def\s+test_[a-zA-Z0-9_]*\s*\(/m.test(source);
}

function collectApiTestInventory(
  manifests,
  directory = path.join(apiRoot, 'tests'),
) {
  const paths = [];
  const byDomain = new Map();
  const visit = (currentDirectory) => {
    for (const entry of fs.readdirSync(currentDirectory, {
      withFileTypes: true,
    })) {
      const absolutePath = path.join(currentDirectory, entry.name);
      if (entry.isDirectory()) {
        visit(absolutePath);
      } else if (/^test_.+\.py$/.test(entry.name)) {
        const relativePath = path
          .relative(repoRoot, absolutePath)
          .replaceAll(path.sep, '/');
        paths.push(relativePath);
        const source = fs.readFileSync(absolutePath, 'utf8');
        for (const match of source.matchAll(
          /\bopen_alm_api\.domains\.([a-z][a-z0-9_]*)\b/g,
        )) {
          const domainPaths = byDomain.get(match[1]) ?? new Set();
          domainPaths.add(relativePath);
          byDomain.set(match[1], domainPaths);
        }
        for (const manifest of manifests) {
          if (
            manifest.apiDomain &&
            manifest.workspaceApiPrefixes.some((apiPrefix) =>
              source.includes(apiPrefix),
            )
          ) {
            const domainPaths = byDomain.get(manifest.apiDomain) ?? new Set();
            domainPaths.add(relativePath);
            byDomain.set(manifest.apiDomain, domainPaths);
          }
        }
      }
    }
  };
  visit(directory);
  return {
    paths: paths.sort(),
    byDomain: new Map(
      [...byDomain].map(([apiDomain, domainPaths]) => [
        apiDomain,
        [...domainPaths].sort(),
      ]),
    ),
  };
}

function readNodeidManifest(manifestPath, description) {
  const nodeids = fs
    .readFileSync(manifestPath, 'utf8')
    .split('\n')
    .map((line) => line.trim())
    .filter(Boolean);
  if (nodeids.length !== new Set(nodeids).size) {
    throw new Error(`${description} contains duplicates`);
  }
  return nodeids;
}

const manifestResult = readAppManifestContracts({ repoRoot });
const changes = collectChanges();
const effectiveChanges =
  changes ?? [{ status: 'M', path: 'apps/api/project.json' }];
const apiTestInventory = collectApiTestInventory(manifestResult.manifests);
const selection = selectAffectedApiPytests({
  changes: effectiveChanges,
  manifests: manifestResult.manifests,
  manifestErrors: manifestResult.errors,
  pipelineSource: process.env.CI_PIPELINE_SOURCE ?? 'local',
  apiTestPaths: apiTestInventory.paths,
  apiTestsByDomain: apiTestInventory.byDomain,
  pathExists: (relativePath) =>
    fs.existsSync(path.join(repoRoot, relativePath)),
  pathHasPytestItem: containsPytestItem,
});
let executionPlan = createApiTestExecutionPlan(selection, lane, {
  pathHasExternalMarker: (testPath) =>
    containsPytestMarker(testPath, 'external_integration'),
  pipelineSource: process.env.CI_PIPELINE_SOURCE ?? 'local',
});
const scheduledRegression = process.env.CI_PIPELINE_SOURCE === 'schedule';
const fullMigrationRegression =
  lane === 'migration' &&
  !scheduledRegression &&
  requiresFullMigrationRegression(effectiveChanges);
if (lane === 'migration' && !scheduledRegression) {
  executionPlan = fullMigrationRegression
    ? {
        ...executionPlan,
        scope: 'full',
        runAll: true,
        empty: false,
        paths: [],
        reasons: [
          ...executionPlan.reasons,
          'migration, model, dependency, or DB test harness change',
        ],
      }
    : {
        ...executionPlan,
        scope: 'none',
        runAll: false,
        empty: true,
        paths: [],
        requiredPaths: [],
        reasons: ['no migration, model, dependency, or DB test harness change'],
      };
}
if (
  executionPlan.scope === 'full' &&
  !scheduledRegression &&
  !fullMigrationRegression
) {
  executionPlan = applyApiRegressionTier(
    executionPlan,
    readNodeidManifest(criticalManifestPath, 'critical API test manifest'),
    process.env,
  );
}
executionPlan = applyExternalReleaseCanary(
  executionPlan,
  readNodeidManifest(
    externalReleaseCanaryManifestPath,
    'release external canary manifest',
  ),
  process.env,
);

if (planJson) {
  console.log(JSON.stringify(executionPlan));
  process.exit(0);
}

console.log(
  `[api-test-selection] lane=${lane} scope=${executionPlan.scope}` +
    (executionPlan.paths.length ? ` tests=${executionPlan.paths.length}` : ''),
);
for (const reason of executionPlan.reasons) {
  console.log(`[api-test-selection] ${reason}`);
}
if (selectOnly) {
  process.exit(0);
}
if (executionPlan.empty) {
  process.exit(0);
}

const relativeTests = executionPlan.paths.map((testPath) =>
  path
    .relative(apiRoot, path.join(repoRoot, testPath))
    .replaceAll(path.sep, '/'),
);
const result = spawnSync(
  'bash',
  ['scripts/ci/run-api-pytest.sh', lane, ...relativeTests],
  {
    cwd: repoRoot,
    env:
      executionPlan.scope === 'focused'
        ? { ...process.env, OPEN_ALM_API_ALLOW_EMPTY: '1' }
        : process.env,
    stdio: 'inherit',
  },
);

if (result.error) {
  throw result.error;
}
process.exit(result.status ?? 1);
