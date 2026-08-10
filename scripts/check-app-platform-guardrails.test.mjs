import assert from 'node:assert/strict';
import fs from 'node:fs';
import os from 'node:os';
import test from 'node:test';
import path from 'node:path';
import { fileURLToPath } from 'node:url';

import {
  checkAppPlatformGuardrails,
  classifyPath,
  collectGitChanges,
  formatGuardrailReport,
  LANES,
  parseGitNameStatus,
  runGuardrailSuite,
  validateAppManifestContracts,
  validateCodeownersProtectedSurface,
  validateGitlabCiGuardrailArtifact,
  validateManifestContractSource,
  validateWorkspaceKeywordSearchHarness,
  validateWindowsDevGuardrailSource,
  validateWindowsDevGuardrails,
} from './check-app-platform-guardrails.mjs';
import {
  parseManifestContractSource,
  validateManifestContract,
} from './app-platform-guardrails/manifest-contract-parser.mjs';
import './check-web-app-boundaries.test.mjs';

const __dirname = path.dirname(fileURLToPath(import.meta.url));
const fixtureDir = path.join(__dirname, 'fixtures/app-platform-guardrails');

function loadFixture(name) {
  return JSON.parse(fs.readFileSync(path.join(fixtureDir, name), 'utf8'));
}

function manifestSource(contractBlock) {
  return `
    import { Home } from 'lucide-react';

    export const homeManifest = {
      appBarItem: { id: 'home', title: 'home', icon: Home },
      contract: ${contractBlock},
      defaultActiveNavItemId: '',
      navItems: [],
      workspaceRoutePaths: ['/w/:workspaceSlug/home'],
    };
  `;
}

test('valid app-only fixture stays in the App Sandbox lane', () => {
  const fixture = loadFixture('app-only.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    declaredLane: fixture.declaredLane,
    env: {},
  });

  assert.equal(result.ok, fixture.expect.ok);
  assert.equal(result.requiredLane, LANES.APP_SANDBOX);
  assert.deepEqual(result.failures, []);
});

test('App Sandbox fixture touching protected platform surface fails with next actions', () => {
  const fixture = loadFixture('app-touching-platform.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    declaredLane: fixture.declaredLane,
    env: {},
  });

  assert.equal(result.ok, fixture.expect.ok);
  assert.deepEqual(
    result.failures.map((failure) => failure.code),
    fixture.expect.failureCodes,
  );
  const protectedFailure = result.failures.find(
    (failure) => failure.code === 'protected-surface',
  );
  assert.ok(protectedFailure);
  assert.ok(protectedFailure.hits.some((hit) => hit.path === '.gitlab-ci.yml'));
  assert.ok(
    protectedFailure.hits.every((hit) =>
      hit.surfaces.every((surface) => surface.nextAction),
    ),
  );
});

test('mass delete fixture fails without explicit maintenance override', () => {
  const fixture = loadFixture('mass-delete.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    declaredLane: fixture.declaredLane,
    env: {},
  });

  assert.equal(result.ok, fixture.expect.ok);
  assert.ok(result.failures.some((failure) => failure.code === 'mass-delete'));
});

test('approved maintenance override allows mass delete threshold', () => {
  const fixture = loadFixture('mass-delete.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    declaredLane: fixture.declaredLane,
    allowRepoWideRewrite: true,
    env: {},
  });

  assert.equal(result.ok, true);
});

test('GitLab MR labels can approve repo-wide maintenance rewrite', () => {
  const fixture = loadFixture('mass-delete.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    env: {},
    mergeRequestLabels: 'lane::core-platform,repo-wide::approved',
  });

  assert.equal(result.ok, true);
  assert.equal(result.declaredLane, LANES.CORE_PLATFORM);
  assert.equal(result.laneDeclarationSource, 'CI_MERGE_REQUEST_LABELS');
});

test('App Sandbox cannot self-approve a repo-wide rewrite label', () => {
  const fixture = loadFixture('mass-delete.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    env: {
      CI_PIPELINE_SOURCE: 'merge_request_event',
      CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
    },
    mergeRequestLabels: 'lane::app-sandbox,repo-wide::approved',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.some((failure) => failure.code === 'mass-delete'));
});

test('unknown lane declarations fail clearly', () => {
  const fixture = loadFixture('app-only.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    declaredLane: 'fast-app-magic',
    env: {},
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.some((failure) => failure.code === 'unknown-lane'));
});

test('GitLab MR lane labels declare the change lane', () => {
  const previousLane = process.env.AI_DO_CHANGE_LANE;
  delete process.env.AI_DO_CHANGE_LANE;
  const fixture = loadFixture('app-only.json');
  try {
    const result = checkAppPlatformGuardrails(fixture.changes, {
      env: {},
      mergeRequestLabels: 'ready,lane::app-sandbox',
    });

    assert.equal(result.ok, true);
    assert.equal(result.declaredLane, LANES.APP_SANDBOX);
    assert.equal(result.laneDeclarationSource, 'CI_MERGE_REQUEST_LABELS');
  } finally {
    if (previousLane === undefined) {
      delete process.env.AI_DO_CHANGE_LANE;
    } else {
      process.env.AI_DO_CHANGE_LANE = previousLane;
    }
  }
});

test('feature merge requests targeting dev require one lane label', () => {
  const fixture = loadFixture('app-only.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    env: {
      CI_PIPELINE_SOURCE: 'merge_request_event',
      CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
    },
    mergeRequestLabels: 'ready',
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.some((failure) => failure.code === 'missing-lane'));
});

test('low-risk review profiles do not require a lane label', () => {
  for (const filePath of [
    'apps/web/src/platform/i18n/resources.ts',
    '.env.example',
    'scripts/codex-review-ci.sh',
    'docs/apps/pms/README.md',
    'apps/web/src/app-modules/pms/views/PmsView.tsx',
  ]) {
    const result = checkAppPlatformGuardrails(
      [{ status: 'M', path: filePath }],
      {
        env: {
          CI_PIPELINE_SOURCE: 'merge_request_event',
          CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
        },
        mergeRequestLabels: '',
      },
    );

    assert.equal(result.ok, true, filePath);
    assert.equal(
      result.failures.some((failure) => failure.code === 'missing-lane'),
      false,
      filePath,
    );
  }
});

test('feature merge requests targeting dev reject multiple lane labels', () => {
  const fixture = loadFixture('app-only.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    env: {
      CI_PIPELINE_SOURCE: 'merge_request_event',
      CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
    },
    mergeRequestLabels: 'lane::app-sandbox,lane::core-platform',
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) => failure.code === 'multiple-lanes'),
  );
  assert.deepEqual(result.mergeRequestLaneDeclarations, [
    'app-sandbox',
    'core-platform',
  ]);
});

test('feature merge requests reject an inflated lane declaration', () => {
  const fixture = loadFixture('app-only.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    env: {
      CI_PIPELINE_SOURCE: 'merge_request_event',
      CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
    },
    mergeRequestLabels: 'lane::core-platform',
  });

  assert.equal(result.ok, false);
  assert.equal(result.expectedMergeRequestLane, LANES.APP_SANDBOX);
  assert.ok(
    result.failures.some((failure) => failure.code === 'lane-mismatch'),
  );
});

test('app delivery cannot be mixed with harness or policy changes', () => {
  const result = checkAppPlatformGuardrails(
    [
      { status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' },
      { status: 'M', path: '.gitlab-ci.yml' },
    ],
    {
      env: {
        CI_PIPELINE_SOURCE: 'merge_request_event',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
      },
      mergeRequestLabels: 'lane::harness-and-policy',
    },
  );

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some(
      (failure) => failure.code === 'mixed-app-harness-policy',
    ),
  );
});

test('test-only maintenance can update ordinary and protected API tests together', () => {
  const result = checkAppPlatformGuardrails(
    [
      { status: 'M', path: 'apps/api/tests/conftest.py' },
      { status: 'M', path: 'apps/api/tests/test_meeting.py' },
      { status: 'M', path: 'apps/api/tests/test_workspace_bootstrap.py' },
    ],
    {
      env: {
        CI_PIPELINE_SOURCE: 'merge_request_event',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
      },
      mergeRequestLabels: 'lane::harness-and-policy',
    },
  );

  assert.equal(result.ok, true);
  assert.equal(result.requiredLane, LANES.HARNESS_AND_POLICY);
  assert.equal(result.expectedMergeRequestLane, LANES.HARNESS_AND_POLICY);
  assert.deepEqual(result.failures, []);
});

test('feature merge requests map shared surfaces to the exact Core Platform lane', () => {
  const result = checkAppPlatformGuardrails(
    [{ status: 'M', path: 'packages/ui/src/Button.tsx' }],
    {
      env: {
        CI_PIPELINE_SOURCE: 'merge_request_event',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
      },
      mergeRequestLabels: 'lane::core-platform',
    },
  );

  assert.equal(result.ok, true);
  assert.equal(result.requiredLane, LANES.SHARED_CAPABILITY);
  assert.equal(result.expectedMergeRequestLane, LANES.CORE_PLATFORM);
});

test('Claude and agent guidance plus MR templates are protected policy surfaces', () => {
  for (const filePath of [
    'CLAUDE.md',
    'docs/agents/vibe-coding-harness.md',
    '.gitlab/merge_request_templates/Vibe_Domain_App.md',
    'scripts/tests/test_check_alembic_state.py',
    'scripts/web-i18n-message-checker.mjs',
  ]) {
    assert.deepEqual(classifyPath(filePath), {
      lane: LANES.HARNESS_AND_POLICY,
      protectedSurface: 'harness-policy',
      reason: 'guardrail, CI, agent, policy, or repository harness surface',
    });
  }
});

test('scaffolded app worker modules stay sandboxed while bootstrap remains core', () => {
  assert.deepEqual(
    classifyPath('apps/worker/src/ai_do_worker/tasks/apps/meal_invoice/run.py'),
    {
      lane: LANES.APP_SANDBOX,
      protectedSurface: null,
      reason: 'scaffolded app-owned worker task module',
    },
  );
  assert.equal(
    classifyPath('apps/worker/src/ai_do_worker/celery_app.py').lane,
    LANES.CORE_PLATFORM,
  );
  assert.equal(
    classifyPath('apps/worker/src/ai_do_worker/tasks/__init__.py')
      .protectedSurface,
    'core-platform',
  );
  assert.equal(
    classifyPath('apps/api/src/ai_do_api/api_registry.py').protectedSurface,
    'api-core',
  );
  assert.equal(
    classifyPath('apps/worker/tests/apps/meal_invoice/test_extract.py').lane,
    LANES.APP_SANDBOX,
  );
  assert.equal(
    classifyPath('apps/api/tests/test_ai_gateway_direct_call_guard.py')
      .protectedSurface,
    'harness-policy',
  );
  assert.equal(
    classifyPath('apps/worker/tests/test_worker_task_registration.py')
      .protectedSurface,
    'harness-policy',
  );
});

test('release promotion merge requests do not require a feature lane label', () => {
  const result = checkAppPlatformGuardrails(
    [
      { status: 'M', path: 'apps/web/src/app-modules/home/View.tsx' },
      { status: 'M', path: 'scripts/check-app-platform-guardrails.mjs' },
    ],
    {
      env: {
        CI_PIPELINE_SOURCE: 'merge_request_event',
        CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'dev',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'main',
      },
      mergeRequestLabels: '',
    },
  );

  assert.equal(result.ok, true);
});

test('non-dev merge requests targeting main do not receive release promotion exemptions', () => {
  const result = checkAppPlatformGuardrails(
    [
      { status: 'M', path: 'apps/web/src/app-modules/home/View.tsx' },
      { status: 'M', path: 'scripts/check-app-platform-guardrails.mjs' },
    ],
    {
      env: {
        CI_PIPELINE_SOURCE: 'merge_request_event',
        CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'feature/unsafe',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'main',
      },
      mergeRequestLabels: '',
    },
  );

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some(
      (failure) => failure.code === 'mixed-app-harness-policy',
    ),
  );
});

test('git name-status parser handles modified, renamed, and copied paths', () => {
  assert.deepEqual(
    parseGitNameStatus(
      [
        'M\tapps/web/src/app-modules/home/View.tsx',
        'R100\told/path.ts\tnew/path.ts',
        'C075\tsource/path.ts\tcopy/path.ts',
      ].join('\n'),
    ),
    [
      { status: 'M', path: 'apps/web/src/app-modules/home/View.tsx' },
      { status: 'R', previousPath: 'old/path.ts', path: 'new/path.ts' },
      { status: 'C', previousPath: 'source/path.ts', path: 'copy/path.ts' },
    ],
  );
});

test('MR change collection fails closed when the declared diff base is unavailable', () => {
  const git = (args) => {
    if (args[0] === 'rev-parse') {
      throw new Error('missing ref');
    }
    return '';
  };

  assert.throws(
    () =>
      collectGitChanges({
        env: {
          CI_PIPELINE_SOURCE: 'merge_request_event',
          CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
          CI_MERGE_REQUEST_DIFF_BASE_SHA: 'deadbeef',
        },
        git,
      }),
    /MR diff base deadbeef is not available/,
  );
});

test('MR change collection fails closed when the diff base variable is missing', () => {
  const git = (args) => {
    if (args[0] === 'rev-parse' && args[2] === 'HEAD~1^{commit}') {
      return 'head-parent';
    }
    return '';
  };

  assert.throws(
    () =>
      collectGitChanges({
        env: {
          CI_PIPELINE_SOURCE: 'merge_request_event',
          CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
        },
        git,
      }),
    /CI_MERGE_REQUEST_DIFF_BASE_SHA is required/,
  );
});

test('guardrail suite runs injected change sources and validators', () => {
  const fixture = loadFixture('app-only.json');
  const result = runGuardrailSuite({
    changeSource: () => fixture.changes,
    lane: LANES.APP_SANDBOX,
    env: {},
    repoRoot: __dirname,
    validators: [
      {
        code: 'fixture-validator',
        message: 'Fixture validator failed.',
        validate: ({ changes, repoRoot }) => {
          assert.equal(changes.length, fixture.changes.length);
          assert.equal(repoRoot, __dirname);
          return {
            ok: false,
            errors: [
              { filePath: 'fixture.json', message: 'synthetic failure' },
            ],
          };
        },
        formatError: (error) => `${error.filePath}: ${error.message}`,
      },
    ],
  });

  assert.equal(result.ok, false);
  assert.equal(result.requiredLane, LANES.APP_SANDBOX);
  assert.equal(result.declaredLane, LANES.APP_SANDBOX);
  assert.deepEqual(result.failures, [
    {
      code: 'fixture-validator',
      message: 'Fixture validator failed.',
      details: ['fixture.json: synthetic failure'],
    },
  ]);
});

test('guardrail suite can resolve the lane from an injected env object', () => {
  const fixture = loadFixture('app-only.json');
  const result = runGuardrailSuite({
    changes: fixture.changes,
    env: { AI_DO_CHANGE_LANE: LANES.APP_SANDBOX },
    validators: [],
  });

  assert.equal(result.ok, true);
  assert.equal(result.declaredLane, LANES.APP_SANDBOX);
  assert.equal(result.laneDeclarationSource, 'AI_DO_CHANGE_LANE');
});

test('guardrail report formats validation details and protected hits', () => {
  const report = formatGuardrailReport({
    ok: false,
    requiredLane: LANES.HARNESS_AND_POLICY,
    declaredLane: LANES.APP_SANDBOX,
    changedFileCount: 1,
    deletedFileCount: 0,
    failures: [
      {
        message: 'Synthetic validation failed.',
        details: ['fixture.json: failed'],
      },
      {
        message: 'Protected surface failed.',
        hits: [
          {
            path: '.gitlab-ci.yml',
            status: 'M',
            surfaces: [
              {
                label:
                  'CI, agent rule, repository harness, or guardrail policy',
                requiredLane: LANES.HARNESS_AND_POLICY,
                nextAction: 'Route this change as Harness And Policy.',
              },
            ],
          },
        ],
      },
    ],
  });

  assert.match(report, /required lane: Harness And Policy/);
  assert.match(report, /declared lane: App Sandbox/);
  assert.match(report, /fixture\.json: failed/);
  assert.match(
    report,
    /Surface: CI, agent rule, repository harness, or guardrail policy/,
  );
});

test('app-local additive migration fixture stays in App Sandbox', () => {
  const fixture = loadFixture('app-local-migration.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    declaredLane: fixture.declaredLane,
    env: {},
    readFile: (relativePath) => fixture.sources[relativePath] ?? '',
  });

  assert.equal(result.ok, true);
});

test('destructive migration fixture requires Core Platform lane', () => {
  const fixture = loadFixture('destructive-migration.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    declaredLane: fixture.declaredLane,
    env: {},
    readFile: (relativePath) => fixture.sources[relativePath] ?? '',
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) => failure.code === 'migration-escalation'),
  );
});

test('destructive migration MR passes with the exact Core Platform lane', () => {
  const fixture = loadFixture('destructive-migration.json');
  const result = checkAppPlatformGuardrails(fixture.changes, {
    env: {
      CI_PIPELINE_SOURCE: 'merge_request_event',
      CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
    },
    mergeRequestLabels: 'lane::core-platform',
    readFile: (relativePath) => fixture.sources[relativePath] ?? '',
  });

  assert.equal(result.ok, true);
  assert.equal(result.requiredLane, LANES.CORE_PLATFORM);
  assert.equal(result.expectedMergeRequestLane, LANES.CORE_PLATFORM);
});

test('valid manifest contract fixture passes validation', () => {
  const source = fs.readFileSync(
    path.join(fixtureDir, 'manifests/valid-manifest.ts'),
    'utf8',
  );
  const errors = validateManifestContractSource({
    appId: 'home',
    source,
    pathExists: () => true,
  });

  assert.deepEqual(errors, []);
});

test('invalid manifest contract fixture fails validation', () => {
  const source = fs.readFileSync(
    path.join(fixtureDir, 'manifests/invalid-missing-contract.ts'),
    'utf8',
  );
  const errors = validateManifestContractSource({
    appId: 'home',
    source,
    pathExists: () => true,
  });

  assert.ok(errors.some((error) => error.message === 'contract is required.'));
});

test('manifest contract rejects legacy frontend workspace search authority', () => {
  const errors = validateManifestContractSource({
    appId: 'home',
    source: manifestSource(`{
      owner: 'platform-shell',
      permissions: [],
      apiDomain: null,
      workspaceApiPrefixes: [],
      workspaceSearchSource: true,
      aiCapabilities: [],
      writeAuditActions: [],
      appLocalTests: ['fixture.ts'],
    }`),
    pathExists: () => true,
  });

  assert.ok(
    errors.some((error) =>
      error.message.includes('contract.workspaceSearchSource is forbidden'),
    ),
  );
});

test('workspace keyword search harness rejects misplaced adapter declarations', () => {
  const repoRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), 'ai-do-search-harness-'),
  );
  const apiPath = path.join(
    repoRoot,
    'apps/api/src/ai_do_api/domains/billing/service.py',
  );
  fs.mkdirSync(path.dirname(apiPath), { recursive: true });
  fs.writeFileSync(apiPath, 'SOURCE = SearchEntityAdapter()\n', 'utf8');

  const result = validateWorkspaceKeywordSearchHarness({ repoRoot });

  assert.equal(result.ok, false);
  assert.match(result.errors[0].message, /search_projection\.py/);
});

test('workspace keyword search harness enforces composition, lifecycle, and locale evidence', () => {
  const repoRoot = fs.mkdtempSync(
    path.join(os.tmpdir(), 'ai-do-search-contract-'),
  );
  const writeFixture = (relativePath, source) => {
    const absolutePath = path.join(repoRoot, relativePath);
    fs.mkdirSync(path.dirname(absolutePath), { recursive: true });
    fs.writeFileSync(absolutePath, source, 'utf8');
  };
  writeFixture(
    'apps/api/src/ai_do_api/domains/search/schemas.py',
    'class SearchEntityType:\n    BILLING_RECORD = "billing_record"\n',
  );
  writeFixture(
    'apps/api/src/ai_do_api/domains/billing/search_projection.py',
    `BILLING_SEARCH_ADAPTER = SearchEntityAdapter(
    entity_type=SearchEntityType.BILLING_RECORD.value,
    label_key="ai.search.entityBilling",
)
`,
  );
  writeFixture(
    'apps/api/src/ai_do_api/domains/search/default_entity_adapters.py',
    `from ai_do_api.domains.billing.search_projection import BILLING_SEARCH_ADAPTER

ADAPTERS = (BILLING_SEARCH_ADAPTER,)
`,
  );
  writeFixture(
    'apps/api/tests/test_search_index_hooks.py',
    `def test_billing_create_search_lifecycle():
    _process_pending_entity(
        search_client,
        entity_type="billing_record",
        entity_id=record_id,
        lifecycle_operation="create",
    )

def test_billing_update_search_lifecycle():
    _process_pending_entity(
        search_client,
        entity_type="billing_record",
        entity_id=record_id,
        lifecycle_operation="update",
    )

def test_billing_delete_search_lifecycle():
    _process_pending_delete(
        search_client,
        entity_type="billing_record",
        entity_id=record_id,
        lifecycle_operation="delete",
    )
`,
  );
  writeFixture(
    'apps/web/src/platform/i18n/resources.ts',
    `export const resources = {
  'ko-KR': {
    apps: {
      ai: {
        search: {
          entityBilling: '청구',
        },
      },
    },
  },
  'en-US': {
    apps: {
      ai: {
        search: {
          entityBilling: 'Billing',
        },
      },
    },
  },
} as const;
`,
  );

  assert.equal(validateWorkspaceKeywordSearchHarness({ repoRoot }).ok, true);

  writeFixture(
    'apps/api/tests/test_search_index_hooks.py',
    `# search-lifecycle-contract: billing_record:create
# search-lifecycle-contract: billing_record:update
# search-lifecycle-contract: billing_record:delete
# _process_pending_entity(entity_type="billing_record", lifecycle_operation="create")
`,
  );
  const commentOnlyResult = validateWorkspaceKeywordSearchHarness({ repoRoot });
  assert.equal(commentOnlyResult.ok, false);
  assert.ok(
    commentOnlyResult.errors.some((error) =>
      error.message.includes('billing_record:create'),
    ),
  );

  writeFixture(
    'apps/api/src/ai_do_api/domains/search/default_entity_adapters.py',
    `from ai_do_api.domains.billing.search_projection import BILLING_SEARCH_ADAPTER
`,
  );
  writeFixture(
    'apps/api/tests/test_search_index_hooks.py',
    `def test_billing_create_search_lifecycle():
    _process_pending_entity(
        search_client,
        entity_type="billing_record",
        entity_id=record_id,
        lifecycle_operation="create",
    )

def test_billing_delete_search_lifecycle():
    _process_pending_delete(
        search_client,
        entity_type="billing_record",
        entity_id=record_id,
        lifecycle_operation="delete",
    )
`,
  );
  writeFixture(
    'apps/web/src/platform/i18n/resources.ts',
    `export const resources = {
  'ko-KR': {
    apps: {
      ai: {
        search: {},
      },
    },
    unrelated: { entityBilling: '청구' },
  },
  'en-US': {
    apps: { ai: { search: { entityBilling: 'Billing' } } },
  },
};
`,
  );

  const result = validateWorkspaceKeywordSearchHarness({ repoRoot });

  assert.equal(result.ok, false);
  assert.ok(
    result.errors.some((error) => error.message.includes('composition root')),
  );
  assert.ok(
    result.errors.some((error) =>
      error.message.includes('billing_record:update'),
    ),
  );
  assert.ok(result.errors.some((error) => error.message.includes('(1/2)')));
});

test('manifest contract parser tolerates nested structures and template literal braces', () => {
  const source = `
    const ignored = \`template literal with { braces } and \${'interpolation'}\`;

    export const homeManifest = {
      appBarItem: { id: 'home', title: \`home { \${'title'} }\`, icon: Home },
      contract: {
        metadata: {
          owner: 'nested-owner-does-not-count',
          permissions: ['Not.Valid.At.Top.Level'],
          nested: [{ apiDomain: 'NestedValue' }],
        },
        notes: [\`array template with { braces } and \${'interpolation'}\`],
        owner: 'platform-shell',
        permissions: ['workspace.read'],
        apiDomain: null,
        aiCapabilities: ['rag.search'],
        writeAuditActions: ['home.update'],
        appLocalTests: ['apps/web/src/app/shell/app-registry.spec.ts'],
      },
      defaultActiveNavItemId: '',
      navItems: [],
      workspaceRoutePaths: ['/w/:workspaceSlug/home'],
    };
  `;
  const parsed = parseManifestContractSource(source);

  assert.deepEqual(parsed.diagnostics, []);
  assert.deepEqual(
    validateManifestContract(parsed.contract, {
      appId: 'home',
      manifestPath: 'fixture.ts',
      pathExists: () => true,
    }),
    [],
  );
});

test('extension host manifest contract allows registered app contract aggregation', () => {
  const source = `
    import { Plug } from 'lucide-react';

    const extensionAiCapabilities = extensionManifests.flatMap(
      (manifest) => manifest.contract.aiCapabilities,
    );
    const extensionWriteAuditActions = extensionManifests.flatMap(
      (manifest) => manifest.contract.writeAuditActions,
    );
    const extensionAppLocalTests = extensionManifests.flatMap(
      (manifest) => manifest.contract.appLocalTests,
    );

    export const extensionsManifest = {
      appBarItem: { id: 'extensions', title: 'extensions', icon: Plug },
      contract: {
        owner: 'customer-extension-host',
        permissions: [],
        apiDomain: null,
        aiCapabilities: unique(extensionAiCapabilities),
        writeAuditActions: unique(extensionWriteAuditActions),
        appLocalTests: unique(extensionAppLocalTests),
      },
      defaultActiveNavItemId: '',
      navItems: [],
      workspaceRoutePaths: ['/w/:workspaceSlug/extensions'],
    };
  `;
  const errors = validateManifestContractSource({
    appId: 'extensions',
    source,
    pathExists: () => true,
  });

  assert.deepEqual(errors, []);
});

test('non-extension manifests cannot use dynamic contract aggregation', () => {
  const errors = validateManifestContractSource({
    appId: 'home',
    source: manifestSource(`{
      owner: 'platform-shell',
      permissions: [],
      apiDomain: null,
      aiCapabilities: unique(extensionAiCapabilities),
      writeAuditActions: [],
      appLocalTests: ['apps/web/src/app/shell/app-registry.spec.ts'],
    }`),
    pathExists: () => true,
  });

  assert.ok(
    errors.some(
      (error) =>
        error.message === 'contract.aiCapabilities must be a string array.',
    ),
  );
});

test('manifest contract validation rejects invalid apiDomain values', () => {
  const errors = validateManifestContractSource({
    appId: 'home',
    source: manifestSource(`{
      owner: 'platform-shell',
      permissions: [],
      apiDomain: 'mail-service',
      aiCapabilities: [],
      writeAuditActions: [],
      appLocalTests: ['apps/web/src/app/shell/app-registry.spec.ts'],
    }`),
    pathExists: () => true,
  });

  assert.ok(
    errors.some(
      (error) =>
        error.message ===
        'contract.apiDomain must be snake_case or null, got "mail-service".',
    ),
  );
});

test('manifest contract validation rejects missing appLocalTests paths', () => {
  const missingPath = 'apps/web/src/app-modules/home/missing.spec.ts';
  const errors = validateManifestContractSource({
    appId: 'home',
    source: manifestSource(`{
      owner: 'platform-shell',
      permissions: [],
      apiDomain: null,
      aiCapabilities: [],
      writeAuditActions: [],
      appLocalTests: ['${missingPath}'],
    }`),
    pathExists: (relativePath) => relativePath !== missingPath,
  });

  assert.ok(
    errors.some(
      (error) =>
        error.message ===
        `contract.appLocalTests path does not exist: ${missingPath}`,
    ),
  );
});

test('feature manifest contract validates without shell app registry fields', () => {
  const errors = validateManifestContractSource({
    appId: 'dm',
    source: `
      export const dmManifest = {
        moduleKind: 'feature',
        moduleId: 'dm',
        contract: {
          owner: 'communications-platform',
          permissions: [],
          apiDomain: 'dm',
          aiCapabilities: [],
          writeAuditActions: [],
          appLocalTests: ['apps/api/tests/test_dm.py'],
        },
      };
    `,
    pathExists: () => true,
  });

  assert.deepEqual(errors, []);
});

test('feature manifest contract rejects shell app registry fields', () => {
  const errors = validateManifestContractSource({
    appId: 'dm',
    source: `
      export const dmManifest = {
        moduleKind: 'feature',
        moduleId: 'dm',
        appBarItem: { id: 'dm', title: 'dm', icon: Home },
        navItems: [],
        workspaceRoutePaths: [],
        contract: {
          owner: 'communications-platform',
          permissions: [],
          apiDomain: 'dm',
          aiCapabilities: [],
          writeAuditActions: [],
          appLocalTests: ['apps/api/tests/test_dm.py'],
        },
      };
    `,
    pathExists: () => true,
  });

  assert.ok(
    errors.some(
      (error) =>
        error.message === 'feature manifests must not declare appBarItem.',
    ),
  );
  assert.ok(
    errors.some(
      (error) =>
        error.message ===
        'feature manifests must not declare workspaceRoutePaths.',
    ),
  );
  assert.ok(
    errors.some(
      (error) =>
        error.message === 'feature manifests must not declare navItems.',
    ),
  );
});

test('current app module manifests satisfy the app platform contract', () => {
  const result = validateAppManifestContracts({
    repoRoot: path.resolve(__dirname, '..'),
  });

  assert.deepEqual(result.errors, []);
  assert.equal(result.ok, true);
});

test('Windows dev guardrail accepts dev-only fixture', () => {
  const source = fs.readFileSync(
    path.join(fixtureDir, 'windows/valid-dev-windows.ps1'),
    'utf8',
  );
  const errors = validateWindowsDevGuardrailSource(
    'scripts/dev-windows.ps1',
    source,
  );

  assert.deepEqual(errors, []);
});

test('Windows dev guardrail rejects production references', () => {
  const source = fs.readFileSync(
    path.join(fixtureDir, 'windows/invalid-prod-reference.ps1'),
    'utf8',
  );
  const errors = validateWindowsDevGuardrailSource(
    'scripts/dev-windows.ps1',
    source,
  );

  assert.ok(
    errors.some((error) => error.message.includes('production checkout path')),
  );
  assert.ok(
    errors.some((error) =>
      error.message.includes('production deployment command'),
    ),
  );
  assert.ok(
    errors.some((error) => error.message.includes('production API port 8000')),
  );
});

test('current Windows administrator dev surface avoids production references', () => {
  const result = validateWindowsDevGuardrails({
    repoRoot: path.resolve(__dirname, '..'),
  });

  assert.deepEqual(result.errors, []);
  assert.equal(result.ok, true);
});

test('current CODEOWNERS declares protected surface owners', () => {
  const result = validateCodeownersProtectedSurface({
    repoRoot: path.resolve(__dirname, '..'),
  });

  assert.deepEqual(result.errors, []);
  assert.equal(result.ok, true);
});

test('CODEOWNERS validation reports missing protected owner rules', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-do-codeowners-'));
  fs.writeFileSync(
    path.join(tempDir, 'CODEOWNERS'),
    '/apps/web/src/app/ @dwdcc\n',
    'utf8',
  );

  const result = validateCodeownersProtectedSurface({ repoRoot: tempDir });

  assert.equal(result.ok, false);
  assert.ok(
    result.errors.some((error) =>
      error.message.includes(
        'Missing protected surface owner rule: /.gitlab-ci.yml',
      ),
    ),
  );
});

test('current GitLab CI publishes the guardrail JSON artifact', () => {
  const result = validateGitlabCiGuardrailArtifact({
    repoRoot: path.resolve(__dirname, '..'),
  });

  assert.deepEqual(result.errors, []);
  assert.equal(result.ok, true);
});

test('GitLab CI validation rejects release validation bypasses', () => {
  const currentSource = fs.readFileSync(
    path.join(__dirname, '..', '.gitlab-ci.yml'),
    'utf8',
  );
  for (const source of [
    currentSource.replace(
      '    - AI_DO_POSTGRES_DSN=postgresql+psycopg://contract:contract@127.0.0.1:1/ai_do_ci_contracts AI_DO_WORKER_QUEUE_GROUP=default pnpm nx run api:ci-contracts --parallel=6 --outputStyle=static --skip-nx-cache',
      '    - AI_DO_POSTGRES_DSN=postgresql+psycopg://contract:contract@127.0.0.1:1/ai_do_ci_contracts AI_DO_WORKER_QUEUE_GROUP=default pnpm nx run api:ci-contracts --parallel=6 --outputStyle=static --skip-nx-cache || true',
    ),
    currentSource.replace(
      '    - pnpm ci:app-web-contracts',
      '    - pnpm ci:app-web-contracts || true',
    ),
    currentSource.replace(
      '$CI_MERGE_REQUEST_SOURCE_BRANCH_NAME == "dev" && ',
      '',
    ),
  ]) {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-do-gitlab-ci-'));
    try {
      fs.writeFileSync(path.join(tempDir, '.gitlab-ci.yml'), source, 'utf8');
      const result = validateGitlabCiGuardrailArtifact({ repoRoot: tempDir });
      assert.equal(result.ok, false);
      assert.ok(
        result.errors.some((error) =>
          error.message.includes('runner-owned semantic contract'),
        ),
      );
    } finally {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  }
});

test('GitLab CI validation rejects weakened Codex gates', () => {
  const currentSource = fs.readFileSync(
    path.join(__dirname, '..', '.gitlab-ci.yml'),
    'utf8',
  );
  const mutateCodexJob = (mutator) => {
    const start = currentSource.indexOf('\ncodex_review:\n');
    const end = currentSource.indexOf('\ncontracts_publish:\n', start);
    assert.ok(start >= 0 && end > start);
    return `${currentSource.slice(0, start)}${mutator(
      currentSource.slice(start, end),
    )}${currentSource.slice(end)}`;
  };
  const cases = [
    [
      mutateCodexJob((block) =>
        block.replace('  allow_failure: false', '  allow_failure: true'),
      ),
      'allow_failure: false',
    ],
    [
      mutateCodexJob((block) =>
        block.replace(
          '  dependencies: []',
          '  dependencies: [release_validation]',
        ),
      ),
      'dependencies: []',
    ],
    [
      mutateCodexJob((block) =>
        block.replace(
          '$CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "dev"',
          '$CI_MERGE_REQUEST_TARGET_BRANCH_NAME == "main"',
        ),
      ),
      'rules must always run exactly once',
    ],
    [
      mutateCodexJob((block) =>
        block.replace(
          '  before_script: []',
          '  before_script:\n    - echo bypass',
        ),
      ),
      'explicitly disable before_script',
    ],
  ];

  for (const [source, expectedError] of cases) {
    const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-do-gitlab-ci-'));
    try {
      fs.writeFileSync(path.join(tempDir, '.gitlab-ci.yml'), source, 'utf8');
      const result = validateGitlabCiGuardrailArtifact({ repoRoot: tempDir });
      assert.equal(result.ok, false);
      assert.ok(
        result.errors.some((error) => error.message.includes(expectedError)),
        result.errors.map((error) => error.message).join('; '),
      );
    } finally {
      fs.rmSync(tempDir, { recursive: true, force: true });
    }
  }
});

test('GitLab CI validation rejects a shallow release checkout', () => {
  const tempDir = fs.mkdtempSync(path.join(os.tmpdir(), 'ai-do-gitlab-ci-'));
  fs.writeFileSync(
    path.join(tempDir, '.gitlab-ci.yml'),
    `release_validation:
  script:
    - pnpm check:app-platform-guardrails:artifact
  artifacts:
    when: always
    paths:
      - app-platform-guardrails.json
`,
    'utf8',
  );

  const result = validateGitlabCiGuardrailArtifact({ repoRoot: tempDir });

  assert.equal(result.ok, false);
  assert.ok(
    result.errors.some((error) => error.message.includes('GIT_DEPTH: "0"')),
  );
});

test('package harness scripts retain deterministic app contract gates', () => {
  const packageJson = JSON.parse(
    fs.readFileSync(path.join(__dirname, '..', 'package.json'), 'utf8'),
  );
  const apiProject = JSON.parse(
    fs.readFileSync(
      path.join(__dirname, '..', 'apps/api/project.json'),
      'utf8',
    ),
  );
  const workerProject = JSON.parse(
    fs.readFileSync(
      path.join(__dirname, '..', 'apps/worker/project.json'),
      'utf8',
    ),
  );
  const ciHarnessProject = JSON.parse(
    fs.readFileSync(path.join(__dirname, 'ci/project.json'), 'utf8'),
  );
  const harness = packageJson.scripts['ci:harness'];
  const pythonGuardrails = packageJson.scripts['ci:python-contract-guardrails'];
  const apiContracts = packageJson.scripts['ci:app-api-contracts'];
  const webContracts = packageJson.scripts['ci:app-web-contracts'];

  assert.ok(harness.includes('nx run ci-harness:ci'));
  assert.ok(harness.includes('--parallel=4'));
  assert.ok(harness.includes('--outputStyle=static'));
  assert.ok(harness.includes('--skip-nx-cache'));
  const harnessLeafTargets = ciHarnessProject.targets.ci.dependsOn;
  assert.equal(harnessLeafTargets.length, 18);
  for (const targetName of harnessLeafTargets) {
    const target = ciHarnessProject.targets[targetName];
    assert.equal(target.executor, 'nx:run-commands');
    assert.equal(target.cache, false);
    assert.doesNotMatch(
      target.options.command,
      /(?:^|\s)&(?:\s|$)|\|\|\s*true/,
    );
  }
  const harnessCommands = harnessLeafTargets.map(
    (targetName) => ciHarnessProject.targets[targetName].options.command,
  );
  for (const command of [
    'pnpm test:mr-contract-evidence',
    'pnpm test:codex-review-contract',
    'pnpm test:api-ci-runtime',
    'pnpm test:feature-mr',
    'pnpm check:app-platform-guardrails',
    'pnpm check:mr-contract-evidence',
    'pnpm check:web-i18n',
    'pnpm check:web-dark-mode',
    'pnpm check:env-contract',
    'pnpm check:runtime-separation',
    'pnpm check:skills',
    'pnpm check:path-hardcoding',
    'pnpm test:final-docs',
    'pnpm docs:final:check',
  ]) {
    assert.ok(
      harnessCommands.includes(command),
      `ci:harness is missing ${command}`,
    );
  }
  for (const command of [
    'test:alembic-graph',
    'test:python-source-integrity',
    'check:alembic-graph',
    'check:python-source-integrity',
    'check:api-i18n',
  ]) {
    assert.ok(
      pythonGuardrails.includes(command),
      `ci:python-contract-guardrails is missing ${command}`,
    );
  }
  for (const command of [
    'uv lock --check --directory apps/api',
    'uv lock --check --directory apps/worker',
    'UV_PROJECT_ENVIRONMENT=../../.runtime/ci-api-venv uv sync --frozen --python 3.12 --group dev --directory apps/api',
    'UV_PROJECT_ENVIRONMENT=../../.runtime/ci-worker-venv uv sync --frozen --python 3.12 --group dev --directory apps/worker',
    'AI_DO_POSTGRES_DSN=postgresql+psycopg://contract:contract@127.0.0.1:1/ai_do_ci_contracts AI_DO_WORKER_QUEUE_GROUP=default pnpm nx run api:ci-contracts',
    'nx run api:ci-contracts',
    '--parallel=6',
    '--skip-nx-cache',
  ]) {
    assert.ok(
      apiContracts.includes(command),
      `ci:app-api-contracts is missing ${command}`,
    );
  }
  const apiLeafTargets = [
    'contract-openapi',
    'contract-architecture',
    'contract-lint',
    'contract-typecheck',
    'contract-tests',
  ];
  for (const targetName of apiLeafTargets) {
    const target = apiProject.targets[targetName];
    assert.equal(target.cache, false);
  }
  assert.deepEqual(
    apiProject.targets['ci-contracts'].dependsOn.slice(0, 5),
    apiLeafTargets,
  );
  assert.deepEqual(apiProject.targets['ci-contracts'].dependsOn[5], {
    projects: ['worker'],
    target: 'contract-tests',
  });
  assert.match(
    apiProject.targets['contract-openapi'].options.command,
    /--no-sync/,
  );
  assert.match(
    apiProject.targets['contract-architecture'].options.command,
    /check-api-i18n-messages\.py/,
  );
  assert.match(
    apiProject.targets['contract-architecture'].options.command,
    /uv run --no-sync --frozen[^&]+lint-imports/,
  );
  assert.match(
    apiProject.targets['contract-lint'].options.command,
    /ruff check/,
  );
  assert.match(
    apiProject.targets['contract-typecheck'].options.command,
    /compileall/,
  );
  assert.match(
    apiProject.targets['contract-tests'].options.command,
    /test_platform_adapter_registries\.py/,
  );
  assert.match(
    apiProject.targets['contract-tests'].options.command,
    /test_ai_gateway_direct_call_guard\.py/,
  );
  assert.equal(workerProject.targets['contract-tests'].cache, false);
  assert.match(
    workerProject.targets['contract-tests'].options.command,
    /python -m pytest tests -q/,
  );
  assert.match(
    workerProject.targets['contract-tests'].options.command,
    /AI_DO_WORKER_BROKER_URL=memory:\/\//,
  );
  assert.match(
    workerProject.targets['contract-tests'].options.command,
    /AI_DO_WORKER_RESULT_BACKEND=cache\+memory:\/\//,
  );
  for (const target of [
    ...apiLeafTargets.map((targetName) => apiProject.targets[targetName]),
    workerProject.targets['contract-tests'],
  ]) {
    if (target.options.command.includes('uv run')) {
      assert.match(
        target.options.command,
        /UV_PROJECT_ENVIRONMENT=.*uv run --no-sync/,
      );
    }
  }
  for (const command of [
    'nx run-many -p web',
    '-t architecture,typecheck,test',
    '--parallel=3',
    '--outputStyle=static',
    '--skip-nx-cache',
  ]) {
    assert.ok(
      webContracts.includes(command),
      `ci:app-web-contracts is missing ${command}`,
    );
  }
});
