import path from 'node:path';

import {
  apiDomainForPath,
  normalizePath,
} from './app-platform-guardrails/classifier.mjs';
import { CORE_API_DOMAINS } from './app-platform-guardrails/policy.mjs';

const API_DOMAIN_PREFIX = 'apps/api/src/ai_do_api/domains/';
const APP_MANIFEST_PATTERN =
  /^apps\/web\/src\/app-modules\/([^/]+)\/manifest\.ts$/;
const WORKSPACE_KEYWORD_SEARCH_CONTRACT_TEST =
  'apps/api/tests/test_workspace_keyword_search_registry.py';
const WORKSPACE_KEYWORD_SEARCH_APP_PATH =
  /^apps\/api\/src\/ai_do_api\/domains\/[^/]+\/search_(?:hooks|projection|registration)\.py$/;

function allChangePaths(changes) {
  return changes.flatMap((change) =>
    [change.previousPath, change.path]
      .filter(Boolean)
      .map((filePath) => normalizePath(filePath)),
  );
}

function isApiPytestPath(filePath) {
  return /^apps\/api\/tests\/(?:.+\/)?test_[^/]+\.py$/.test(filePath);
}

function isMigrationTestPath(filePath) {
  return (
    isApiPytestPath(filePath) && /migration/i.test(path.basename(filePath))
  );
}

export function requiresFullMigrationRegression(changes = []) {
  return allChangePaths(changes).some(
    (filePath) =>
      filePath === '.gitlab-ci.yml' ||
      filePath === 'apps/api/alembic.ini' ||
      filePath === 'apps/api/project.json' ||
      filePath === 'apps/api/pyproject.toml' ||
      filePath === 'apps/api/uv.lock' ||
      filePath === 'apps/api/src/ai_do_api/core/db.py' ||
      filePath === 'apps/api/src/ai_do_api/core/model_registry.py' ||
      filePath === 'apps/api/tests/conftest.py' ||
      filePath === 'apps/api/tests/integration_infra.py' ||
      filePath === 'apps/api/tests/test_api_test_runtime.py' ||
      filePath === 'scripts/api-test-selection.mjs' ||
      filePath === 'scripts/run-affected-api-tests.mjs' ||
      /^apps\/api\/alembic\//.test(filePath) ||
      /^apps\/api\/src\/ai_do_api\/.+\/models\.py$/.test(filePath) ||
      /^scripts\/ci\/run-api-pytest(?:\.test)?\.sh$/.test(filePath) ||
      isMigrationTestPath(filePath),
  );
}

function isFullSuitePath(filePath) {
  if (
    filePath === '.gitlab-ci.yml' ||
    filePath === '.dockerignore' ||
    filePath === 'package.json' ||
    filePath === 'nx.json' ||
    filePath === 'ops/ci/validation-runner/Dockerfile' ||
    /^packages\/contracts\//.test(filePath) ||
    /^apps\/api\/(?:alembic(?:\/|\.ini$)|project\.json$|pyproject\.toml$|uv\.lock$)/.test(
      filePath,
    ) ||
    /^apps\/api\/tests\/(?:conftest\.py|integration_infra\.py|test_api_test_runtime\.py)$/.test(
      filePath,
    ) ||
    filePath === 'scripts/check-api-test-budget.py' ||
    filePath === 'scripts/api-critical-test-manifest.txt' ||
    filePath === 'scripts/install-ci-validation-runner.sh' ||
    filePath === 'scripts/tests/test_check_api_test_budget.py' ||
    /^scripts\/(?:api-test-selection|run-affected-api-tests)\.mjs$/.test(
      filePath,
    ) ||
    /^scripts\/ci\/run-api-pytest(?:\.test)?\.sh$/.test(filePath) ||
    filePath === 'scripts/api-test-vm.sh' ||
    /^scripts\/app-platform-guardrails\/(?:classifier|manifest|manifest-contract-parser|policy)\.mjs$/.test(
      filePath,
    )
  ) {
    return true;
  }
  if (filePath.startsWith('apps/api/src/ai_do_api/core/')) {
    return true;
  }
  if (
    /^apps\/api\/src\/ai_do_api\/domains\/[^/]+\/(?:__init__|app_catalog)\.py$/.test(
      filePath,
    )
  ) {
    return true;
  }
  if (
    filePath.startsWith('apps/api/src/ai_do_api/') &&
    !filePath.startsWith(API_DOMAIN_PREFIX)
  ) {
    return true;
  }
  return isMigrationTestPath(filePath);
}

function conventionTestsForDomain(apiDomain, apiTestPaths) {
  const exactName = `test_${apiDomain}.py`;
  const prefix = `test_${apiDomain}_`;
  return apiTestPaths.filter((testPath) => {
    const filename = path.basename(testPath);
    return filename === exactName || filename.startsWith(prefix);
  });
}

function ownedTestsForDomain(apiDomain, apiTestsByDomain) {
  if (apiTestsByDomain instanceof Map) {
    return apiTestsByDomain.get(apiDomain) ?? [];
  }
  return apiTestsByDomain[apiDomain] ?? [];
}

function manifestApiTests(manifest, pathExists, pathHasPytestItem) {
  return (manifest.appLocalTests ?? []).filter(
    (testPath) =>
      isApiPytestPath(testPath) &&
      pathExists(testPath) &&
      pathHasPytestItem(testPath),
  );
}

export function standardApiPytestMarker() {
  return 'not slow and not external_integration and not migration';
}

export function isApiReleasePromotion(env = {}) {
  return (
    env.CI_PIPELINE_SOURCE === 'merge_request_event' &&
    env.CI_MERGE_REQUEST_SOURCE_BRANCH_NAME === 'dev' &&
    env.CI_MERGE_REQUEST_TARGET_BRANCH_NAME === 'main'
  );
}

export function createApiTestExecutionPlan(
  selection,
  lane,
  { pathHasExternalMarker = () => true, pipelineSource = 'push' } = {},
) {
  const marker = {
    standard: standardApiPytestMarker(pipelineSource),
    slow: 'slow and not external_integration and not migration',
    migration: 'migration',
    external: 'external_integration',
  }[lane];
  if (!marker) {
    throw new Error(`unsupported API test lane: ${lane}`);
  }
  if (lane !== 'external' || selection.scope !== 'focused') {
    return {
      schemaVersion: 1,
      lane,
      scope: selection.scope,
      runAll: selection.scope === 'full',
      empty: selection.scope === 'none',
      marker,
      paths: [...selection.paths],
      requiredPaths: [...(selection.requiredPaths ?? [])],
      reasons: [...selection.reasons],
    };
  }

  const externalPaths = selection.paths.filter(pathHasExternalMarker);
  const empty = externalPaths.length === 0;
  return {
    schemaVersion: 1,
    lane,
    scope: empty ? 'none' : 'focused',
    runAll: false,
    empty,
    marker: 'external_integration',
    paths: externalPaths,
    requiredPaths: [],
    reasons: empty
      ? [
          ...selection.reasons,
          'selected API tests contain no external_integration items',
        ]
      : [...selection.reasons],
  };
}

export function applyApiRegressionTier(
  executionPlan,
  criticalNodeids,
  env = {},
) {
  if (
    executionPlan.scope !== 'full' ||
    env.CI_PIPELINE_SOURCE === 'schedule'
  ) {
    return executionPlan;
  }

  const requiredPaths = [...new Set(executionPlan.requiredPaths ?? [])].sort();
  const requiredPathSet = new Set(requiredPaths);
  const routinePaths = criticalNodeids
    .filter((nodeid) => {
      const [testPath] = nodeid.split('::', 1);
      return !requiredPathSet.has(`apps/api/${testPath}`);
    })
    .map((nodeid) => `apps/api/${nodeid}`);
  const paths = [...new Set([...routinePaths, ...requiredPaths])];
  const reasons = [
    ...executionPlan.reasons,
    `routine critical manifest: ${criticalNodeids.length} tests`,
  ];
  if (requiredPaths.length > 0) {
    reasons.push(`required affected tests: ${requiredPaths.length} files`);
  }

  return {
    ...executionPlan,
    runAll: false,
    paths,
    reasons,
  };
}

export function applyExternalReleaseCanary(
  executionPlan,
  canaryNodeids,
  env = {},
) {
  if (
    executionPlan.lane !== 'external' ||
    !isApiReleasePromotion(env)
  ) {
    return executionPlan;
  }

  const paths = [...new Set(canaryNodeids)]
    .sort()
    .map((nodeid) => `apps/api/${nodeid}`);
  return {
    ...executionPlan,
    scope: paths.length === 0 ? 'none' : 'focused',
    runAll: false,
    empty: paths.length === 0,
    paths,
    requiredPaths: [],
    reasons: [
      ...executionPlan.reasons,
      `release external real-service canary: ${paths.length} tests`,
      'full external regression remains scheduled',
    ],
  };
}

export function selectAffectedApiPytests({
  changes = [],
  manifests = [],
  manifestErrors = [],
  pipelineSource = 'push',
  apiTestPaths = [],
  apiTestsByDomain = {},
  pathExists = () => true,
  pathHasPytestItem = pathExists,
} = {}) {
  if (pipelineSource === 'schedule') {
    return {
      scope: 'full',
      paths: [],
      requiredPaths: [],
      reasons: ['scheduled regression'],
    };
  }
  if (manifestErrors.length > 0) {
    return {
      scope: 'full',
      paths: [],
      requiredPaths: [],
      reasons: ['app manifest contract could not be loaded safely'],
    };
  }

  const paths = allChangePaths(changes);
  const fullReasons = [];
  const selected = new Set();
  const reasons = [];
  const manifestsByDomain = new Map();
  const manifestsByPath = new Map();
  for (const manifest of manifests) {
    manifestsByPath.set(normalizePath(manifest.manifestPath), manifest);
    if (manifest.apiDomain) {
      const entries = manifestsByDomain.get(manifest.apiDomain) ?? [];
      entries.push(manifest);
      manifestsByDomain.set(manifest.apiDomain, entries);
    }
  }

  for (const change of changes) {
    if (change.status === 'D' && isApiPytestPath(normalizePath(change.path))) {
      fullReasons.push(`deleted API test: ${normalizePath(change.path)}`);
    }
    const normalizedPath = normalizePath(change.path);
    if (WORKSPACE_KEYWORD_SEARCH_APP_PATH.test(normalizedPath)) {
      if (change.status === 'D') {
        fullReasons.push(
          `deleted workspace keyword search contract: ${normalizedPath}`,
        );
      } else if (pathExists(WORKSPACE_KEYWORD_SEARCH_CONTRACT_TEST)) {
        selected.add(WORKSPACE_KEYWORD_SEARCH_CONTRACT_TEST);
        reasons.push(
          `workspace keyword search contract change: ${normalizedPath}`,
        );
      } else {
        fullReasons.push('workspace keyword search registry test is missing');
      }
    }
  }

  const addManifestTests = (manifest, reason) => {
    const declaredApiTests = manifestApiTests(
      manifest,
      pathExists,
      pathHasPytestItem,
    );
    if (manifest.apiDomain && declaredApiTests.length === 0) {
      fullReasons.push(
        `${manifest.manifestPath} does not declare an app-local API test`,
      );
      return false;
    }
    for (const testPath of declaredApiTests) {
      selected.add(testPath);
    }
    if (declaredApiTests.length > 0) {
      reasons.push(reason);
    }
    return true;
  };

  const addDomainTests = (apiDomain, reason) => {
    const domainManifests = manifestsByDomain.get(apiDomain) ?? [];
    if (domainManifests.length === 0) {
      fullReasons.push(`API domain has no app manifest: ${apiDomain}`);
      return;
    }
    const allManifestsDeclareApiTests = domainManifests.every((manifest) =>
      addManifestTests(manifest, reason),
    );
    if (!allManifestsDeclareApiTests) {
      return;
    }
    for (const testPath of conventionTestsForDomain(
      apiDomain,
      apiTestPaths,
    )) {
      if (pathExists(testPath) && pathHasPytestItem(testPath)) {
        selected.add(testPath);
      }
    }
    for (const testPath of ownedTestsForDomain(
      apiDomain,
      apiTestsByDomain,
    )) {
      if (pathExists(testPath) && pathHasPytestItem(testPath)) {
        selected.add(testPath);
      }
    }
  };

  for (const filePath of paths) {
    if (isFullSuitePath(filePath)) {
      if (isApiPytestPath(filePath)) {
        if (pathExists(filePath) && pathHasPytestItem(filePath)) {
          selected.add(filePath);
        } else if (pathExists(filePath)) {
          fullReasons.push(`changed API test contains no items: ${filePath}`);
        }
      }
      fullReasons.push(`shared API or test harness change: ${filePath}`);
      continue;
    }

    if (isApiPytestPath(filePath)) {
      if (pathExists(filePath) && pathHasPytestItem(filePath)) {
        selected.add(filePath);
        reasons.push(`changed API test: ${filePath}`);
      } else if (pathExists(filePath)) {
        fullReasons.push(`changed API test contains no items: ${filePath}`);
      }
      continue;
    }

    const apiDomain = apiDomainForPath(filePath);
    if (apiDomain) {
      if (CORE_API_DOMAINS.has(apiDomain)) {
        fullReasons.push(`core API domain change: ${apiDomain}`);
        continue;
      }
      addDomainTests(apiDomain, `app API domain change: ${apiDomain}`);
      continue;
    }

    const manifestMatch = APP_MANIFEST_PATTERN.exec(filePath);
    if (manifestMatch) {
      const manifest = manifestsByPath.get(filePath);
      if (!manifest) {
        fullReasons.push(
          `changed app manifest could not be loaded: ${filePath}`,
        );
      } else if (manifest.apiDomain) {
        addDomainTests(
          manifest.apiDomain,
          `changed app manifest: ${manifest.appId}`,
        );
      } else {
        addManifestTests(manifest, `changed app manifest: ${manifest.appId}`);
      }
      continue;
    }

    if (filePath.startsWith('apps/api/')) {
      fullReasons.push(`unclassified API change: ${filePath}`);
    }
  }

  if (fullReasons.length > 0) {
    return {
      scope: 'full',
      paths: [],
      requiredPaths: [...selected].sort(),
      reasons: [...new Set(fullReasons)].sort(),
    };
  }
  if (selected.size === 0) {
    return { scope: 'none', paths: [], reasons: [] };
  }
  return {
    scope: 'focused',
    paths: [...selected].sort(),
    reasons: [...new Set(reasons)].sort(),
  };
}
