import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';

import {
  applyApiRegressionTier,
  applyExternalReleaseCanary,
  createApiTestExecutionPlan,
  isApiReleasePromotion,
  requiresFullMigrationRegression,
  selectAffectedApiPytests,
  standardApiPytestMarker,
} from './api-test-selection.mjs';
import { readAppManifestContracts } from './app-platform-guardrails/manifest.mjs';

const existing = new Set([
  'apps/api/tests/test_pms_issues.py',
  'apps/api/tests/test_pms_links.py',
  'apps/api/tests/test_patent.py',
  'apps/api/tests/test_direct.py',
  'apps/api/tests/test_endpoint_contract_for_pms.py',
  'apps/api/tests/test_workspace_keyword_search_registry.py',
  'apps/api/tests/test_workspace_migration.py',
]);
const pathExists = (filePath) => existing.has(filePath);
const manifests = [
  {
    appId: 'pms',
    manifestPath: 'apps/web/src/app-modules/pms/manifest.ts',
    apiDomain: 'pms',
    appLocalTests: ['apps/api/tests/test_pms_issues.py'],
  },
  {
    appId: 'patent-compose',
    manifestPath: 'apps/web/src/app-modules/patent-compose/manifest.ts',
    apiDomain: 'patent',
    appLocalTests: ['apps/api/tests/test_patent.py'],
  },
  {
    appId: 'patent-report',
    manifestPath: 'apps/web/src/app-modules/patent-report/manifest.ts',
    apiDomain: 'patent',
    appLocalTests: ['apps/api/tests/test_patent.py'],
  },
  {
    appId: 'legacy-issues',
    manifestPath: 'apps/web/src/app-modules/legacy-issues/manifest.ts',
    apiDomain: 'legacy_issues',
    appLocalTests: ['apps/web/src/app-modules/legacy-issues/view.spec.ts'],
  },
];

function select(changes, options = {}) {
  return selectAffectedApiPytests({
    changes,
    manifests,
    apiTestPaths: [...existing],
    pathExists,
    ...options,
  });
}

test('selects declared and convention-owned API tests for an app domain', () => {
  const result = select([
    { status: 'M', path: 'apps/api/src/open_alm_api/domains/pms/router.py' },
  ]);
  assert.equal(result.scope, 'focused');
  assert.deepEqual(result.paths, [
    'apps/api/tests/test_pms_issues.py',
    'apps/api/tests/test_pms_links.py',
  ]);
});

test('deduplicates tests shared by multiple manifests for one domain', () => {
  const result = select([
    { status: 'M', path: 'apps/api/src/open_alm_api/domains/patent/router.py' },
  ]);
  assert.deepEqual(result.paths, ['apps/api/tests/test_patent.py']);
});

test('falls back to the full suite for core and unregistered API domains', () => {
  assert.equal(
    select([
      { status: 'M', path: 'apps/api/src/open_alm_api/domains/ai/router.py' },
    ]).scope,
    'full',
  );
  assert.equal(
    select([
      { status: 'M', path: 'apps/api/src/open_alm_api/domains/unknown/router.py' },
    ]).scope,
    'full',
  );
});

test('falls back to full when a mapped domain declares no API pytest', () => {
  const result = select([
    {
      status: 'M',
      path: 'apps/api/src/open_alm_api/domains/legacy_issues/router.py',
    },
  ]);
  assert.equal(result.scope, 'full');
  assert.match(result.reasons[0], /does not declare/);
});

test('falls back to full when a manifest-declared API pytest path is missing', () => {
  const result = select(
    [{ status: 'M', path: 'apps/api/src/open_alm_api/domains/pms/router.py' }],
    {
      pathExists: (testPath) =>
        testPath !== 'apps/api/tests/test_pms_issues.py' &&
        pathExists(testPath),
    },
  );
  assert.equal(result.scope, 'full');
  assert.match(result.reasons[0], /does not declare/);
});

test('falls back to full when a declared or changed API pytest has no items', () => {
  const result = select(
    [{ status: 'M', path: 'apps/api/src/open_alm_api/domains/pms/router.py' }],
    {
      pathHasPytestItem: (testPath) =>
        testPath !== 'apps/api/tests/test_pms_issues.py',
    },
  );
  assert.equal(result.scope, 'full');
  assert.match(result.reasons[0], /does not declare/);

  const changedTest = select(
    [{ status: 'M', path: 'apps/api/tests/test_direct.py' }],
    { pathHasPytestItem: () => false },
  );
  assert.equal(changedTest.scope, 'full');
  assert.match(changedTest.reasons[0], /contains no items/);
});

test('selects directly changed tests and both sides of a rename', () => {
  const result = select([
    { status: 'M', path: 'apps/api/tests/test_direct.py' },
    {
      status: 'R',
      previousPath: 'apps/api/src/open_alm_api/domains/patent/old.py',
      path: 'apps/api/src/open_alm_api/domains/pms/new.py',
    },
  ]);
  assert.equal(result.scope, 'focused');
  assert.deepEqual(result.paths, [
    'apps/api/tests/test_direct.py',
    'apps/api/tests/test_patent.py',
    'apps/api/tests/test_pms_issues.py',
    'apps/api/tests/test_pms_links.py',
  ]);
});

test('selects API tests when an app manifest changes', () => {
  const result = select([
    { status: 'M', path: 'apps/web/src/app-modules/pms/manifest.ts' },
  ]);
  assert.deepEqual(result.paths, [
    'apps/api/tests/test_pms_issues.py',
    'apps/api/tests/test_pms_links.py',
  ]);
});

test('search projection changes include the workspace keyword registry contract', () => {
  const result = select([
    {
      status: 'M',
      path: 'apps/api/src/open_alm_api/domains/pms/search_projection.py',
    },
  ]);

  assert.equal(result.scope, 'focused');
  assert.ok(
    result.paths.includes(
      'apps/api/tests/test_workspace_keyword_search_registry.py',
    ),
  );
  assert.ok(result.paths.includes('apps/api/tests/test_pms_issues.py'));
});

test('deleted search registration escalates to the full API suite', () => {
  const result = select([
    {
      status: 'D',
      path: 'apps/api/src/open_alm_api/domains/pms/search_projection.py',
    },
  ]);

  assert.equal(result.scope, 'full');
});

test('domain selection deduplicates a directly changed declared test', () => {
  const result = select([
    { status: 'M', path: 'apps/api/tests/test_pms_issues.py' },
    { status: 'M', path: 'apps/api/src/open_alm_api/domains/pms/router.py' },
  ]);
  assert.deepEqual(result.paths, [
    'apps/api/tests/test_pms_issues.py',
    'apps/api/tests/test_pms_links.py',
  ]);
});

test('adds convention and import-discovered tests outside appLocalTests', () => {
  const result = select(
    [{ status: 'M', path: 'apps/api/src/open_alm_api/domains/pms/router.py' }],
    {
      apiTestsByDomain: {
        pms: ['apps/api/tests/test_endpoint_contract_for_pms.py'],
      },
    },
  );
  assert.deepEqual(result.paths, [
    'apps/api/tests/test_endpoint_contract_for_pms.py',
    'apps/api/tests/test_pms_issues.py',
    'apps/api/tests/test_pms_links.py',
  ]);
});

test('app registration boundaries and deleted API tests run the full suite', () => {
  assert.equal(
    select([
      {
        status: 'M',
        path: 'apps/api/src/open_alm_api/domains/pms/app_catalog.py',
      },
    ]).scope,
    'full',
  );
  assert.equal(
    select([{ status: 'D', path: 'apps/api/tests/test_direct.py' }]).scope,
    'full',
  );
});

test('returns none for changes outside the API contract', () => {
  const result = select([{ status: 'M', path: 'docs/README.md' }]);
  assert.deepEqual(result, { scope: 'none', paths: [], reasons: [] });
});

test('scheduled, shared harness, and manifest parse failures run full', () => {
  assert.equal(select([], { pipelineSource: 'schedule' }).scope, 'full');
  assert.equal(
    select([{ status: 'M', path: 'apps/api/tests/conftest.py' }]).scope,
    'full',
  );
  assert.equal(
    select([
      { status: 'M', path: 'scripts/tests/test_check_api_test_budget.py' },
    ]).scope,
    'full',
  );
  assert.equal(
    select([{ status: 'M', path: 'scripts/ci/run-api-pytest.test.sh' }]).scope,
    'full',
  );
  assert.equal(
    select([{ status: 'M', path: 'ops/ci/validation-runner/Dockerfile' }])
      .scope,
    'full',
  );
  assert.equal(
    select([], { manifestErrors: [{ message: 'bad' }] }).scope,
    'full',
  );
});

test('full fallback retains directly changed tests for the routine tier', () => {
  const result = select([
    {
      status: 'M',
      path: 'apps/api/tests/test_workspace_migration.py',
    },
    {
      status: 'M',
      path: 'apps/api/src/open_alm_api/core/db.py',
    },
  ]);

  assert.equal(result.scope, 'full');
  assert.deepEqual(result.paths, []);
  assert.deepEqual(result.requiredPaths, [
    'apps/api/tests/test_workspace_migration.py',
  ]);
});

test('standard marker always excludes separately owned lanes', () => {
  assert.equal(
    standardApiPytestMarker('schedule'),
    'not slow and not external_integration and not migration',
  );
  assert.equal(
    standardApiPytestMarker('push'),
    'not slow and not external_integration and not migration',
  );
});

test('external execution plan exits early when selected files have no external items', () => {
  const plan = createApiTestExecutionPlan(
    {
      scope: 'focused',
      paths: [
        'apps/api/tests/test_pms_issues.py',
        'apps/api/tests/test_diagrams.py',
      ],
      reasons: ['app API domain change: pms'],
    },
    'external',
    {
      pathHasExternalMarker: (testPath) =>
        testPath.endsWith('test_diagrams.py'),
    },
  );
  assert.equal(plan.scope, 'focused');
  assert.equal(plan.empty, false);
  assert.deepEqual(plan.paths, ['apps/api/tests/test_diagrams.py']);

  const emptyPlan = createApiTestExecutionPlan(
    {
      scope: 'focused',
      paths: ['apps/api/tests/test_pms_issues.py'],
      reasons: ['app API domain change: pms'],
    },
    'external',
    { pathHasExternalMarker: () => false },
  );
  assert.equal(emptyPlan.scope, 'none');
  assert.equal(emptyPlan.empty, true);
  assert.match(emptyPlan.reasons.at(-1), /no external_integration/);
});

test('full machine-readable execution plan keeps empty paths as run-all', () => {
  const plan = createApiTestExecutionPlan(
    { scope: 'full', paths: [], reasons: ['shared API change'] },
    'standard',
  );
  assert.deepEqual(plan, {
    schemaVersion: 1,
    lane: 'standard',
    scope: 'full',
    runAll: true,
    empty: false,
    marker: 'not slow and not external_integration and not migration',
    paths: [],
    requiredPaths: [],
    reasons: ['shared API change'],
  });
});

test('routine full fallback combines the critical manifest with changed tests', () => {
  const plan = applyApiRegressionTier(
    createApiTestExecutionPlan(
      {
        scope: 'full',
        paths: [],
        requiredPaths: ['apps/api/tests/test_workspace_migration.py'],
        reasons: ['shared API change'],
      },
      'migration',
    ),
    [
      'tests/test_workspace_migration.py::test_changed',
      'tests/test_pms_migration.py::test_critical',
    ],
    { CI_PIPELINE_SOURCE: 'merge_request_event' },
  );

  assert.equal(plan.runAll, false);
  assert.deepEqual(plan.paths, [
    'apps/api/tests/test_pms_migration.py::test_critical',
    'apps/api/tests/test_workspace_migration.py',
  ]);
  assert.match(plan.reasons.at(-1), /required affected tests: 1 files/);
});

test('dev to main release promotion uses the risk-based regression tier', () => {
  const releaseEnv = {
    CI_PIPELINE_SOURCE: 'merge_request_event',
    CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'dev',
    CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'main',
  };
  const plan = createApiTestExecutionPlan(
    {
      scope: 'full',
      paths: [],
      requiredPaths: [],
      reasons: ['release promotion full regression: dev -> main'],
    },
    'standard',
  );

  assert.equal(isApiReleasePromotion(releaseEnv), true);
  assert.equal(
    isApiReleasePromotion({
      ...releaseEnv,
      CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'feature/api',
    }),
    false,
  );
  assert.deepEqual(
    applyApiRegressionTier(plan, ['tests/test_direct.py::test_one'], releaseEnv),
    {
      ...plan,
      runAll: false,
      paths: ['apps/api/tests/test_direct.py::test_one'],
      reasons: [
        'release promotion full regression: dev -> main',
        'routine critical manifest: 1 tests',
      ],
    },
  );
});

test('release external lane uses DB-free real-service canaries', () => {
  const plan = createApiTestExecutionPlan(
    {
      scope: 'full',
      paths: [],
      requiredPaths: ['apps/api/tests/test_keyword_search.py'],
      reasons: ['shared API change'],
    },
    'external',
  );
  const canaries = [
    'tests/test_realtime_hub.py::test_redis',
    'tests/test_external_services_canary.py::test_minio',
  ];
  const releaseEnv = {
    CI_PIPELINE_SOURCE: 'merge_request_event',
    CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'dev',
    CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'main',
  };

  assert.deepEqual(
    applyExternalReleaseCanary(plan, canaries, releaseEnv),
    {
      ...plan,
      scope: 'focused',
      runAll: false,
      empty: false,
      paths: [...canaries]
        .sort()
        .map((nodeid) => `apps/api/${nodeid}`),
      requiredPaths: [],
      reasons: [
        'shared API change',
        'release external real-service canary: 2 tests',
        'full external regression remains scheduled',
      ],
    },
  );
  assert.deepEqual(
    applyExternalReleaseCanary(plan, canaries, {
      CI_PIPELINE_SOURCE: 'schedule',
    }),
    plan,
  );
});

test('execution plans keep marker ownership for every API lane', () => {
  const selection = {
    scope: 'full',
    paths: [],
    reasons: ['shared API change'],
  };
  assert.equal(
    createApiTestExecutionPlan(selection, 'slow').marker,
    'slow and not external_integration and not migration',
  );
  assert.equal(
    createApiTestExecutionPlan(selection, 'migration').marker,
    'migration',
  );
  assert.equal(
    createApiTestExecutionPlan(selection, 'external').marker,
    'external_integration',
  );
});

test('migration marker ownership follows the migration filename CI contract', () => {
  const testsRoot = path.resolve('apps/api/tests');
  const visit = (directory) => {
    for (const entry of fs.readdirSync(directory, { withFileTypes: true })) {
      const absolutePath = path.join(directory, entry.name);
      if (entry.isDirectory()) {
        visit(absolutePath);
      } else if (
        entry.name.startsWith('test_') &&
        entry.name.endsWith('.py') &&
        fs.readFileSync(absolutePath, 'utf8').includes('pytest.mark.migration')
      ) {
        assert.match(
          entry.name,
          /migration/i,
          `${path.relative(process.cwd(), absolutePath)} uses the migration marker but cannot trigger app_api_migrations`,
        );
      }
    }
  };
  visit(testsRoot);
});

test('migration regression expands only for DB and migration-sensitive changes', () => {
  assert.equal(
    requiresFullMigrationRegression([
      {
        status: 'M',
        path: 'apps/api/src/open_alm_api/domains/hr/models.py',
      },
    ]),
    true,
  );
  assert.equal(
    requiresFullMigrationRegression([
      {
        status: 'A',
        path: 'apps/api/alembic/versions/123_add_field.py',
      },
    ]),
    true,
  );
  assert.equal(
    requiresFullMigrationRegression([
      {
        status: 'M',
        path: 'apps/api/src/open_alm_api/domains/hr/service.py',
      },
    ]),
    false,
  );
});

test('manifest loader exposes literal workspace API prefixes for ownership discovery', () => {
  const result = readAppManifestContracts({ repoRoot: process.cwd() });
  const filesManifest = result.manifests.find(
    (manifest) => manifest.appId === 'files',
  );
  assert.deepEqual(filesManifest.workspaceApiPrefixes, ['/api/v1/files']);
});
