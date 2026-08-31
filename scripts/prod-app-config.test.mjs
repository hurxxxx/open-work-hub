import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
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
      OPEN_WORK_HUB_APP_PORT: '8000',
      OPEN_WORK_HUB_APP_PUBLIC_URL: 'https://prod.example.com',
      OPEN_WORK_HUB_EDGE_DEV_HOST: 'dev.example.com',
      OPEN_WORK_HUB_EDGE_DEV_UPSTREAM_PORT: '4201',
      OPEN_WORK_HUB_EDGE_LISTEN_PORT: '4200',
      OPEN_WORK_HUB_EDGE_PROD_HOST: 'prod.example.com',
      OPEN_WORK_HUB_EDGE_PROD_UPSTREAM_PORT: '8000',
      OPEN_WORK_HUB_ENV_PROFILE: 'prod',
      OPEN_WORK_HUB_INFRA_NGINX_PORT: '14200',
      OPEN_WORK_HUB_OPF_ENABLED: 'true',
      OPEN_WORK_HUB_OPF_REQUIRED: 'true',
      OPEN_WORK_HUB_OPF_SERVICE_BASE_URL: 'http://127.0.0.1:18081',
      OPEN_WORK_HUB_WEB_DEV_PORT: '4201',
      ...overrides,
    }),
  );
}

test('parses dotenv assignments without evaluating shell syntax', () => {
  const values = parseEnvText(`
    # comment
    export OPEN_WORK_HUB_ENV_PROFILE=prod
    OPEN_WORK_HUB_APP_PUBLIC_URL="https://prod.example.com"
    ignored shell text
  `);
  assert.equal(values.get('OPEN_WORK_HUB_ENV_PROFILE'), 'prod');
  assert.equal(
    values.get('OPEN_WORK_HUB_APP_PUBLIC_URL'),
    'https://prod.example.com',
  );
  assert.equal(values.has('ignored shell text'), false);
});

test('accepts a separated production runtime configuration', () => {
  const config = assertProductionAppEnv(validEnv());
  assert.equal(config.appPort, 8000);
  assert.equal(config.edgeListenPort, 4200);
  assert.equal(config.edgeProdHost, 'prod.example.com');
  assert.equal(config.publicBaseUrl.href, 'https://prod.example.com/');
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
        validEnv({ OPEN_WORK_HUB_APP_PORT: '4201' }),
      ),
    /WEB_DEV_PORT/,
  );
});

test('requires a credential-free HTTPS public origin', () => {
  for (const value of [
    '',
    'http://prod.example.com',
    'https://localhost:8000',
    'https://user:password@prod.example.com',
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
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_APP_FORWARDED_ALLOW_IPS: '10.0.0.10' }),
      ),
    /loopback edge proxy/,
  );
});

test('requires isolated host-aware edge routing', () => {
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_EDGE_LISTEN_PORT: '4201' }),
      ),
    /must not collide with an edge upstream port/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_EDGE_DEV_UPSTREAM_PORT: '4300' }),
      ),
    /must match OPEN_WORK_HUB_WEB_DEV_PORT/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_EDGE_PROD_UPSTREAM_PORT: '8002' }),
      ),
    /must match OPEN_WORK_HUB_APP_PORT/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_EDGE_PROD_HOST: 'other.example.com' }),
      ),
    /must match OPEN_WORK_HUB_APP_PUBLIC_URL/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_EDGE_DEV_HOST: 'prod.example.com' }),
      ),
    /must be distinct/,
  );
});

test('requires a separate loopback privacy-filter origin', () => {
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_OPF_SERVICE_BASE_URL: 'http://127.0.0.1:8000',
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

test('worker healthcheck uses the container hostname without spawning hostname', async () => {
  const composeText = await readFile(
    new URL('../ops/compose/open-work-hub-prod.app.yml', import.meta.url),
    'utf8',
  );
  assert.match(composeText, /--destination "prod-worker@\$\$\{HOSTNAME\}"/);
  assert.doesNotMatch(composeText, /\$\$\(hostname\)/);
});

test('production compose owns a pinned host-aware edge', async () => {
  const [composeText, edgeConfig] = await Promise.all([
    readFile(
      new URL('../ops/compose/open-work-hub-prod.app.yml', import.meta.url),
      'utf8',
    ),
    readFile(
      new URL('../ops/edge/nginx.conf.template', import.meta.url),
      'utf8',
    ),
  ]);
  assert.match(composeText, /container_name: open-work-hub-edge/);
  assert.match(
    composeText,
    /nginx:1\.27-alpine@sha256:65645c7bb6a0661892a8b03b89d0743208a18dd2f3f17a54ef4b76fb8e2f2a10/,
  );
  assert.ok(
    edgeConfig.includes('server_name ${OPEN_WORK_HUB_EDGE_PROD_HOST};'),
  );
  assert.ok(
    edgeConfig.includes(
      'proxy_pass http://127.0.0.1:${OPEN_WORK_HUB_EDGE_PROD_UPSTREAM_PORT};',
    ),
  );
  assert.ok(
    edgeConfig.includes(
      'proxy_pass http://127.0.0.1:${OPEN_WORK_HUB_EDGE_DEV_UPSTREAM_PORT};',
    ),
  );
  assert.match(
    edgeConfig,
    /listen \$\{OPEN_WORK_HUB_EDGE_LISTEN_PORT\} default_server;/,
  );
  assert.match(edgeConfig, /return 421;/);
  assert.doesNotMatch(edgeConfig, /1punicorn/);
});
