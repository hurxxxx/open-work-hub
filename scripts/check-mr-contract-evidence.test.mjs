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
  isProtectedCorePath,
  REQUIRED_CHECK_IDS,
  REQUIRED_FIELD_IDS,
} from './check-mr-contract-evidence.mjs';

const mrEnv = {
  CI_PIPELINE_SOURCE: 'merge_request_event',
  CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'feature/app',
  CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'dev',
  CI_COMMIT_SHA: 'def4567890abcdef',
  CI_MERGE_REQUEST_DIFF_BASE_SHA: 'abc1234567abcdef',
};

const __dirname = path.dirname(fileURLToPath(import.meta.url));

const completeChecks = REQUIRED_CHECK_IDS.map(
  (checkId) => `- [x] <!-- open-work-hub:check:${checkId} --> checked`,
).join('\n');
const completeFields = REQUIRED_FIELD_IDS.map(
  (fieldId) =>
    `Field: <!-- open-work-hub:field:${fieldId} --> ${
      fieldId === 'workspace-keyword-search'
        ? 'none - this app does not expose workspace keyword search'
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
  (checkId) => `- [x] <!-- open-work-hub:check:${checkId} --> checked`,
).join('\n');
const completeCoreFields = CORE_REQUIRED_FIELD_IDS.map(
  (fieldId) =>
    `Field: <!-- open-work-hub:field:${fieldId} --> ${
      fieldId === 'workspace-keyword-search'
        ? 'none - this enablement does not change workspace keyword search'
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

test('recognizes app-owned and protected-core paths', () => {
  assert.equal(
    isDomainAppDeliveryPath('apps/web/src/app-modules/diagrams/View.tsx'),
    true,
  );
  assert.equal(
    isDomainAppDeliveryPath(
      'apps/api/src/open_work_hub_api/domains/bento/router.py',
    ),
    true,
  );
  assert.equal(
    isDomainAppDeliveryPath(
      'apps/api/src/open_work_hub_api/domains/auth/router.py',
    ),
    false,
  );
  assert.equal(isProtectedCorePath('.gitlab-ci.yml'), true);
  assert.equal(isProtectedCorePath('packages/contracts/src/index.ts'), true);
});

test('repository MR templates fit inside the GitLab CI description variable', () => {
  const vibeTemplate = fs.readFileSync(
    path.join(
      __dirname,
      '..',
      '.gitlab',
      'merge_request_templates',
      'Vibe_Domain_App.md',
    ),
    'utf8',
  );
  const coreTemplate = fs.readFileSync(
    path.join(
      __dirname,
      '..',
      '.gitlab',
      'merge_request_templates',
      'Core_Enablement.md',
    ),
    'utf8',
  );

  assert.ok(
    vibeTemplate.length < 2_700,
    `template length is ${vibeTemplate.length}`,
  );
  assert.ok(
    coreTemplate.length < 2_700,
    `template length is ${coreTemplate.length}`,
  );
  assert.ok(vibeTemplate.includes(CONTRACT_EVIDENCE_MARKER));
  assert.ok(coreTemplate.includes(CORE_ENABLEMENT_MARKER));
  for (const checkId of REQUIRED_CHECK_IDS) {
    assert.ok(vibeTemplate.includes(`<!-- open-work-hub:check:${checkId} -->`));
  }
  for (const fieldId of REQUIRED_FIELD_IDS) {
    assert.ok(vibeTemplate.includes(`<!-- open-work-hub:field:${fieldId} -->`));
  }
  for (const checkId of CORE_REQUIRED_CHECK_IDS) {
    assert.ok(coreTemplate.includes(`<!-- open-work-hub:check:${checkId} -->`));
  }
  for (const fieldId of CORE_REQUIRED_FIELD_IDS) {
    assert.ok(coreTemplate.includes(`<!-- open-work-hub:field:${fieldId} -->`));
  }
});

test('skips non-MR, release MR, and irrelevant docs changes', () => {
  assert.equal(
    checkMergeRequestContractEvidence({
      changes: [
        { status: 'M', path: 'apps/web/src/app-modules/bento/View.tsx' },
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
  assert.equal(
    checkMergeRequestContractEvidence({
      changes: [{ status: 'M', path: 'packages/contracts/src/index.ts' }],
      description: '',
      env: {
        ...mrEnv,
        CI_MERGE_REQUEST_SOURCE_BRANCH_NAME: 'dev',
        CI_MERGE_REQUEST_TARGET_BRANCH_NAME: 'main',
      },
    }).required,
    false,
  );
});

test('requires app delivery evidence for app-owned changes', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/bento/View.tsx' }],
    description: '',
    env: mrEnv,
  });

  assert.equal(result.ok, false);
  assert.equal(result.required, true);
  assert.equal(result.evidenceKind, 'app-sandbox');
  assert.ok(
    result.failures.some((failure) => failure.includes('Vibe_Domain_App.md')),
  );
});

test('accepts complete app delivery evidence', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/bento/View.tsx' }],
    description: completeDescription,
    env: mrEnv,
  });

  assert.equal(result.ok, true);
  assert.equal(result.required, true);
});

test('accepts complete core enablement evidence', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: '.gitlab-ci.yml' }],
    description: completeCoreDescription,
    env: mrEnv,
  });

  assert.equal(result.ok, true);
  assert.equal(result.evidenceKind, 'core-enablement');
});

test('rejects unchecked items, placeholders, and stale SHA evidence', () => {
  const result = checkMergeRequestContractEvidence({
    changes: [{ status: 'M', path: 'apps/web/src/app-modules/bento/View.tsx' }],
    description: completeDescription
      .replace(
        '- [x] <!-- open-work-hub:check:scope-clean -->',
        '- [ ] <!-- open-work-hub:check:scope-clean -->',
      )
      .replace('evidence for verification', 'REPLACE_ME')
      .replace('Source: def45678', 'Source: 00000000'),
    env: mrEnv,
  });

  assert.equal(result.ok, false);
  assert.ok(result.failures.some((failure) => failure.includes('scope-clean')));
  assert.ok(result.failures.some((failure) => failure.includes('placeholder')));
  assert.ok(result.failures.some((failure) => failure.includes('source SHA')));
});
