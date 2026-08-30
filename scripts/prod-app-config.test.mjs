import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertProductionAppEnv,
  parseEnvText,
} from './prod-app-config.mjs';

function validEnv(overrides = {}) {
  return new Map(
    Object.entries({
      OPEN_WORK_HUB_API_ALLOW_DEV_ADMIN_LOGIN: '0',
      OPEN_WORK_HUB_API_DEV_PORT: '8001',
      OPEN_WORK_HUB_API_ENVIRONMENT: 'production',
      OPEN_WORK_HUB_API_OBJECT_STORAGE_REQUIRED: 'true',
      OPEN_WORK_HUB_API_SEED_DEV_LOGIN_ACCOUNT: 'false',
      OPEN_WORK_HUB_DM_ATTACHMENT_SIGNING_KEY: 'production-test-signing-key',
      OPEN_WORK_HUB_APP_BIND_HOST: '127.0.0.1',
      OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS: '127.0.0.1',
      OPEN_WORK_HUB_APP_PORT: '14201',
      OPEN_WORK_HUB_APP_PUBLIC_URL: 'https://owh.example.com',
      OPEN_WORK_HUB_ENV_PROFILE: 'prod',
      OPEN_WORK_HUB_INFRA_NGINX_PORT: '14200',
      OPEN_WORK_HUB_OPF_ENABLED: 'true',
      OPEN_WORK_HUB_OPF_REQUIRED: 'true',
      OPEN_WORK_HUB_OPF_SERVICE_BASE_URL: 'http://127.0.0.1:18081',
      OPEN_WORK_HUB_WEB_DEV_PORT: '4200',
      ...overrides,
    }),
  );
}

test('parses dotenv assignments without evaluating shell syntax', () => {
  const values = parseEnvText(`
    # comment
    export OPEN_WORK_HUB_ENV_PROFILE=prod
    OPEN_WORK_HUB_APP_PUBLIC_URL="https://owh.example.com"
    ignored shell text
  `);
  assert.equal(values.get('OPEN_WORK_HUB_ENV_PROFILE'), 'prod');
  assert.equal(
    values.get('OPEN_WORK_HUB_APP_PUBLIC_URL'),
    'https://owh.example.com',
  );
  assert.equal(values.has('ignored shell text'), false);
});

test('accepts a separated production runtime configuration', () => {
  const config = assertProductionAppEnv(validEnv());
  assert.equal(config.appPort, 14201);
  assert.equal(config.publicBaseUrl.href, 'https://owh.example.com/');
});

test('rejects development access and port collisions', () => {
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_API_ALLOW_DEV_ADMIN_LOGIN: '1' }),
      ),
    /ALLOW_DEV_ADMIN_LOGIN/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_APP_PORT: '4200' }),
      ),
    /WEB_DEV_PORT/,
  );
});

test('requires a credential-free HTTPS public origin', () => {
  for (const value of [
    '',
    'http://owh.example.com',
    'https://localhost:14201',
    'https://user:password@owh.example.com',
  ]) {
    assert.throws(() =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_APP_PUBLIC_URL: value }),
      ),
    );
  }
});

test('rejects unsafe production secrets and proxy trust', () => {
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_DM_ATTACHMENT_SIGNING_KEY:
            'dev-dm-attachment-signing-key',
        }),
      ),
    /DM_ATTACHMENT_SIGNING_KEY/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS: '*' }),
      ),
    /exact proxy IP addresses/,
  );
});

test('requires a separate loopback privacy-filter origin', () => {
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_OPF_SERVICE_BASE_URL: 'http://127.0.0.1:14201',
        }),
      ),
    /must not collide/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_OPF_SERVICE_BASE_URL: 'https://opf.example.com',
        }),
      ),
    /loopback HTTP origin/,
  );
});
