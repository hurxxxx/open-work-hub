import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { validateAppContracts } from './app-contract-validation.mjs';

const schema = JSON.parse(
  await readFile(
    new URL('../packages/contracts/app-contracts.schema.json', import.meta.url),
  ),
);
const source = JSON.parse(
  await readFile(
    new URL('../packages/contracts/app-contracts.json', import.meta.url),
  ),
);

function cloneSource() {
  return structuredClone(source);
}

test('current app contracts satisfy schema and policy invariants', () => {
  assert.doesNotThrow(() => validateAppContracts(cloneSource(), schema));
});

test('schema rejects unknown root fields', () => {
  const candidate = cloneSource();
  candidate.legacy = true;
  assert.throws(
    () => validateAppContracts(candidate, schema),
    /Invalid app contract schema/,
  );
});

test('schema requires the canonical declaration', () => {
  const candidate = cloneSource();
  delete candidate.$schema;
  assert.throws(
    () => validateAppContracts(candidate, schema),
    /Invalid app contract schema/,
  );
});

test('workspace global routes require shared chrome', () => {
  const candidate = cloneSource();
  const docs = candidate.apps.find((app) => app.app_id === 'docs');
  docs.routes.find((route) => route.route_id === 'docs.shared').chrome =
    'standard';
  assert.throws(
    () => validateAppContracts(candidate, schema),
    /Workspace app global route must use shared chrome: docs.shared/,
  );
});

test('personal tools cannot claim workspace execution', () => {
  const candidate = cloneSource();
  const mail = candidate.apps.find((app) => app.app_id === 'mail');
  mail.execution_context_kind = 'workspace';
  assert.throws(
    () => validateAppContracts(candidate, schema),
    /Personal-tools app must be platform\/personal: mail/,
  );
});

test('availability, execution, and resource scopes remain independent', () => {
  const candidate = cloneSource();
  const docs = candidate.apps.find((app) => app.app_id === 'docs');
  const mail = candidate.apps.find((app) => app.app_id === 'mail');
  const community = candidate.apps.find((app) => app.app_id === 'community');

  docs.execution_context_kind = 'company';
  docs.resource_scope = 'company';
  mail.resource_scope = 'hybrid';
  community.resource_scope = 'hybrid';

  assert.doesNotThrow(() => validateAppContracts(candidate, schema));
});
