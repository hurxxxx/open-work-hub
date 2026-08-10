import assert from 'node:assert/strict';
import fs from 'node:fs';
import path from 'node:path';
import test from 'node:test';
import { fileURLToPath } from 'node:url';

import {
  checkMergeRequestContractEvidence,
  CONTRACT_EVIDENCE_MARKER,
  CORE_ENABLEMENT_MARKER,
  CORE_REQUIRED_CHECK_IDS,
  CORE_REQUIRED_FIELD_IDS,
  isDomainAppDeliveryPath,
  REQUIRED_CHECK_IDS,
  REQUIRED_FIELD_IDS,
} from './check-mr-contract-evidence.mjs';

const mrEnv = {
  CI_PIPELINE_SOURCE: 'merge_request_event',
  CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
  CI_MERGE_REQUEST_LABELS: 'lane::app-sandbox',
  CI_COMMIT_SHA: 'def4567890abcdef',
  CI_MERGE_REQUEST_DIFF_BASE_SHA: 'abc1234567abcdef',
};

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const completeChecks = REQUIRED_CHECK_IDS.map(
  (checkId) => `- [x] <!-- ai-do:check:${checkId} --> checked`,
).join('\n');
const completeFields = REQUIRED_FIELD_IDS.map(
  (fieldId) =>
    `Field: <!-- ai-do:field:${fieldId} --> ${
      fieldId === 'workspace-keyword-search'
        ? 'none — this app does not expose workspace keyword search'
        : `evidence for ${fieldId}`
    }`,
).join('\n');

const completeDescription = `${CONTRACT_EVIDENCE_MARKER}
## Contract Map
## Data, Authorization, And Safety
${completeChecks}
${completeFields}
## Verification Evidence
Pipeline base: abc12345
Source: def45678
## Independent Review
`;

const completeCoreChecks = CORE_REQUIRED_CHECK_IDS.map(
  (checkId) => `- [x] <!-- ai-do:check:${checkId} --> checked`,
).join('\n');
const completeCoreFields = CORE_REQUIRED_FIELD_IDS.map(
  (fieldId) =>
    `Field: <!-- ai-do:field:${fieldId} --> ${
      fieldId === 'workspace-keyword-search'
        ? 'none — this enablement does not change workspace keyword search'
        : `evidence for ${fieldId}`
    }`,
).join('\n');
const completeCoreDescription = `${CORE_ENABLEMENT_MARKER}
## Enablement Contract
${completeCoreChecks}
${completeCoreFields}
## Verification Evidence
Pipeline base: abc12345
Source: def45678
## Core Review
`;

test('recognizes app-owned delivery paths without treating API core as an app', () => {
  assert.equal(
    isDomainAppDeliveryPath('apps/web/src/app-modules/meal/View.tsx'),
    true,
  );
  assert.equal(
    isDomainAppDeliveryPath(
      'apps/api/src/ai_do_api/domains/meal_invoice_ocr/router.py',
    ),
    true,
  );
  assert.equal(
    isDomainAppDeliveryPath('apps/worker/src/ai_do_worker/tasks/ocr.py'),
    true,
  );
  assert.equal(
    isDomainAppDeliveryPath('apps/api/src/ai_do_api/domains/auth/router.py'),
    false,
  );
});

test('repository MR template fits inside the GitLab CI description variable', () => {
  const template = fs.readFileSync(
    path.join(
      __dirname,
      '..',
      '.gitlab',
      'merge_request_templates',
      'Vibe_Domain_App.md',
    ),
    'utf8',
  );

  assert.ok(template.length < 2_700, `template length is ${template.length}`);
  for (const checkId of REQUIRED_CHECK_IDS) {
    assert.ok(template.includes(`<!-- ai-do:check:${checkId} -->`));
  }
  for (const fieldId of REQUIRED_FIELD_IDS) {
    assert.ok(template.includes(`<!-- ai-do:field:${fieldId} -->`));
  }
});

test('repository Core Enablement template fits CI and retains required evidence markers', () => {
  const template = fs.readFileSync(
    path.join(
      __dirname,
      '..',
      '.gitlab',
      'merge_request_templates',
      'Core_Enablement.md',
    ),
    'utf8',
  );

  assert.ok(template.length < 2_700, `template length is ${template.length}`);
  assert.ok(template.includes(CORE_ENABLEMENT_MARKER));
  for (const checkId of CORE_REQUIRED_CHECK_IDS) {
    assert.ok(template.includes(`<!-- ai-do:check:${checkId} -->`));
  }
  for (const fieldId of CORE_REQUIRED_FIELD_IDS) {
    assert.ok(template.includes(`<!-- ai-do:field:${fieldId} -->`));
  }
});

test('skips non-MR and non-app changes', () => {
  assert.equal(
    checkMergeRequestContractEvidence({
      changes: [
        { status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' },
      ],
      description: '',
      env: {},
    }).required,
    false,
  );
  assert.equal(
    checkMergeRequestContractEvidence({
      changes: [{ status: 'M', path: 'docs/README.md' }],
      description: '',
      env: mrEnv,
    }).required,
    false,
  );
});

test('does not apply the App Sandbox template to a Core Enablement MR', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'A', path: 'apps/api/alembic/versions/core_auth.py' }],
    description: '',
    env: {
      ...mrEnv,
      CI_MERGE_REQUEST_LABELS: 'lane::core-platform',
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.required, false);
});

test('mixed app and protected core changes require Core Enablement evidence', () => {
  const changes = [
    { status: 'A', path: 'apps/web/src/app-modules/meal/manifest.ts' },
    { status: 'M', path: 'apps/api/src/ai_do_api/api_registry.py' },
  ];
  const env = {
    ...mrEnv,
    CI_MERGE_REQUEST_LABELS: 'lane::core-platform',
  };
  const missing = checkMergeRequestContractEvidence({
    changes,
    description: '',
    env,
  });
  const complete = checkMergeRequestContractEvidence({
    changes,
    description: completeCoreDescription,
    env,
  });

  assert.equal(missing.ok, false);
  assert.equal(missing.required, true);
  assert.equal(missing.evidenceKind, 'core-enablement');
  assert.ok(
    missing.failures.some((failure) => failure.includes('Core_Enablement.md')),
  );
  assert.equal(complete.ok, true);
  assert.equal(complete.evidenceKind, 'core-enablement');
});

test('workspace keyword search core changes require Core Enablement evidence', () => {
  const description = completeCoreDescription.replace(
    'none — this enablement does not change workspace keyword search',
    'workspace — owner=docs; entity=doc; resource=native_doc; projection=bulk/single; hook=create/update/delete; test=disabled/empty/missing; ACL=source; backfill=all-active; rollback=disable release',
  );
  const result = checkMergeRequestContractEvidence({
    changes: [
      {
        status: 'M',
        path: 'apps/api/src/ai_do_api/domains/search/service.py',
      },
    ],
    description,
    env: {
      ...mrEnv,
      CI_MERGE_REQUEST_LABELS: 'lane::core-platform',
    },
  });

  assert.equal(result.ok, true);
  assert.equal(result.evidenceKind, 'core-enablement');
});

test('workspace keyword search changes reject none evidence even with a reason', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [
      {
        status: 'M',
        path: 'apps/api/src/ai_do_api/domains/search/service.py',
      },
    ],
    description: completeCoreDescription,
    env: {
      ...mrEnv,
      CI_MERGE_REQUEST_LABELS: 'lane::core-platform',
    },
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.some((failure) => failure.includes('not allowed')));
});

test('workspace keyword search evidence rejects bare none declarations', () => {
  const description = completeDescription.replace(
    'none — this app does not expose workspace keyword search',
    'none',
  );
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' }],
    description,
    env: mrEnv,
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) => failure.includes('none — reason')),
  );
});

test('app and harness changes must be split even under the harness lane', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [
      { status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' },
      { status: 'M', path: '.gitlab-ci.yml' },
    ],
    description: '',
    env: {
      ...mrEnv,
      CI_MERGE_REQUEST_LABELS: 'lane::harness-and-policy',
    },
  });

  assert.equal(result.ok, false);
  assert.equal(result.required, true);
  assert.equal(result.evidenceKind, 'split-required');
  assert.ok(result.failures.some((failure) => failure.includes('split')));
});

test('app-owned migrations cannot be mixed with harness changes', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [
      { status: 'A', path: 'apps/api/alembic/versions/meal_additive.py' },
      { status: 'M', path: '.gitlab-ci.yml' },
    ],
    description: '',
    env: {
      ...mrEnv,
      CI_MERGE_REQUEST_LABELS: 'lane::harness-and-policy',
    },
    readFile: () => 'def upgrade():\n    pass\n',
  });

  assert.equal(result.ok, false);
  assert.equal(result.evidenceKind, 'split-required');
});

test('risky app migration requires Core Enablement evidence', () => {
  const changes = [
    { status: 'A', path: 'apps/api/src/ai_do_api/domains/meal/service.py' },
    { status: 'A', path: 'apps/api/alembic/versions/meal_destructive.py' },
  ];
  const env = {
    ...mrEnv,
    CI_MERGE_REQUEST_LABELS: 'lane::core-platform',
  };
  const readFile = (filePath) =>
    filePath.endsWith('meal_destructive.py')
      ? 'def upgrade():\n    op.drop_table("workspaces")\n'
      : '';
  const missing = checkMergeRequestContractEvidence({
    changes,
    description: '',
    env,
    readFile,
  });
  const complete = checkMergeRequestContractEvidence({
    changes,
    description: completeCoreDescription,
    env,
    readFile,
  });

  assert.equal(missing.ok, false);
  assert.equal(missing.evidenceKind, 'core-enablement');
  assert.equal(complete.ok, true);
});

test('requires the template and completed checklist for app delivery MRs', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' }],
    description: '## Summary\n- [ ] later\n',
    env: mrEnv,
  });

  assert.equal(result.ok, false);
  assert.equal(result.required, true);
  assert.ok(
    result.failures.some((failure) => failure.includes('contract marker')),
  );
  assert.ok(
    result.failures.some((failure) => failure.includes('remain unchecked')),
  );
});

test('accepts completed latest-SHA contract evidence', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [
      { status: 'M', path: 'apps/api/src/ai_do_api/domains/patent/service.py' },
    ],
    description: completeDescription,
    env: mrEnv,
  });

  assert.deepEqual(result.failures, []);
  assert.equal(result.ok, true);
  assert.equal(result.required, true);
});

test('rejects unchanged SHA placeholders even when boxes are checked', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'A', path: 'apps/api/alembic/versions/new_app.py' }],
    description: `${completeDescription}\nLatest source SHA: REPLACE_ME\n`,
    env: mrEnv,
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) => failure.includes('SHA placeholders')),
  );
});

test('rejects evidence recorded for an older source or diff-base SHA', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' }],
    description: completeDescription,
    env: {
      ...mrEnv,
      CI_COMMIT_SHA: '11111111aaaaaaaa',
      CI_MERGE_REQUEST_DIFF_BASE_SHA: '22222222bbbbbbbb',
    },
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) =>
      failure.includes('current CI source SHA'),
    ),
  );
  assert.ok(
    result.failures.some((failure) =>
      failure.includes('current MR diff-base SHA'),
    ),
  );
});

test('accepts snapshot evidence after the target branch advances', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' }],
    description: `${completeDescription}\nPipeline SHAs: 11111111 / 22222222\n`,
    env: {
      ...mrEnv,
      CI_COMMIT_SHA: '11111111aaaaaaaa',
      CI_MERGE_REQUEST_DIFF_BASE_SHA: '22222222bbbbbbbb',
      CI_MERGE_REQUEST_TARGET_BRANCH_SHA: '33333333cccccccc',
    },
  });

  assert.equal(result.ok, true);
});

test('fails closed when required pipeline snapshot variables are missing', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' }],
    description: completeDescription,
    env: {
      ...mrEnv,
      CI_COMMIT_SHA: '',
      CI_MERGE_REQUEST_DIFF_BASE_SHA: '',
    },
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) => failure.includes('CI_COMMIT_SHA')),
  );
  assert.ok(
    result.failures.some((failure) =>
      failure.includes('CI_MERGE_REQUEST_DIFF_BASE_SHA'),
    ),
  );
});

test('fails closed when an MR pipeline omits the target branch variable', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [],
    description: '',
    env: {
      CI_PIPELINE_SOURCE: 'merge_request_event',
    },
  });

  assert.equal(result.ok, false);
  assert.equal(result.required, true);
  assert.ok(
    result.failures.some((failure) =>
      failure.includes('CI_MERGE_REQUEST_TARGET_BRANCH_NAME'),
    ),
  );
});

test('reports a failed target-branch merge simulation', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' }],
    description: completeDescription,
    env: mrEnv,
    mergeResultError: 'content conflict',
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) => failure.includes('content conflict')),
  );
});

test('rejects descriptions that delete a required checklist item', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' }],
    description: completeDescription.replace(
      /^.*ai-do:check:authorization.*\n/m,
      '',
    ),
    env: mrEnv,
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) =>
      failure.includes('Required contract check authorization'),
    ),
  );
});

test('rejects a required evidence field left blank or as a placeholder', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' }],
    description: completeDescription.replace(
      /evidence for verification/,
      'REPLACE_ME',
    ),
    env: mrEnv,
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) =>
      failure.includes('Required evidence field verification'),
    ),
  );
});

test('fails clearly instead of validating a truncated MR description', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/meal/View.tsx' }],
    description: completeDescription,
    env: {
      ...mrEnv,
      CI_MERGE_REQUEST_DESCRIPTION_IS_TRUNCATED: 'true',
    },
  });

  assert.equal(result.ok, false);
  assert.ok(
    result.failures.some((failure) =>
      failure.includes('2,700-character limit'),
    ),
  );
});
