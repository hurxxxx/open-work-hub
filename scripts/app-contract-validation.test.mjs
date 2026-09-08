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

test('rejects product workspace paths and removed context fields', () => {
  const candidate = cloneSource();
  const docs = candidate.apps.find((app) => app.app_id === 'docs');
  docs.routes[0].suffix = '/workspaces/:workspaceSlug';
  assert.throws(() => validateAppContracts(candidate, schema), /Product workspace routes are unsupported/);
  docs.routes[0].suffix = '';
  docs.routes[0].context_scope = 'workspace';
  assert.throws(() => validateAppContracts(candidate, schema), /Invalid app contract schema/);
});

test('personal tools cannot claim company execution', () => {
  const candidate = cloneSource();
  const mail = candidate.apps.find((app) => app.app_id === 'mail');
  mail.execution_context_kind = 'company';
  assert.throws(
    () => validateAppContracts(candidate, schema),
    /Personal-tools app must use personal execution: mail/,
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
