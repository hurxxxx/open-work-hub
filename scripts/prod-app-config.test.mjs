import assert from 'node:assert/strict';
import { readFile } from 'node:fs/promises';
import test from 'node:test';

import { assertProductionAppEnv, parseEnvText } from './prod-app-config.mjs';

function validEnv(overrides = {}) {
  return new Map(
    Object.entries({
      OPENROUTER_API_KEY: 'sk-or-v1-production-test-key',
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
      OPEN_WORK_HUB_BENTO_BIND_HOST: '127.0.0.1',
      OPEN_WORK_HUB_BENTO_PORT: '18084',
      OPEN_WORK_HUB_BENTO_SERVER_URL: 'https://bento.example.com',
      OPEN_WORK_HUB_DRAWIO_PORT: '18083',
      OPEN_WORK_HUB_ENV_PROFILE: 'prod',
      OPEN_WORK_HUB_HERMES_API_KEY:
        'production-hermes-runtime-secret-00000001',
      OPEN_WORK_HUB_HERMES_ENABLED: 'true',
      OPEN_WORK_HUB_HERMES_MANAGEMENT_BASE_URL: 'http://127.0.0.1:9119',
      OPEN_WORK_HUB_HERMES_MANAGEMENT_PORT: '9119',
      OPEN_WORK_HUB_HERMES_MANAGEMENT_TOKEN:
        'production-hermes-management-secret-0001',
      OPEN_WORK_HUB_HERMES_MCP_SERVER_URL:
        'http://127.0.0.1:8000/api/v1/internal/hermes/mcp',
      OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET:
        'production-hermes-mcp-secret-0000000001',
      OPEN_WORK_HUB_HERMES_PROFILE_CLONE_SOURCE: 'default',
      OPEN_WORK_HUB_HERMES_RUNTIME_BASE_URL: 'http://127.0.0.1:8642',
      OPEN_WORK_HUB_HERMES_RUNTIME_PORT: '8642',
      OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_BASE_URL:
        'http://127.0.0.1:8765',
      OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_PORT: '8765',
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
  assert.equal(config.bentoBindHost, '127.0.0.1');
  assert.equal(config.bentoServerUrl.href, 'https://bento.example.com/');
  assert.equal(config.hermesRuntimeBaseUrl.href, 'http://127.0.0.1:8642/');
  assert.equal(
    config.hermesTerminalBrokerBaseUrl.href,
    'http://127.0.0.1:8765/',
  );
  assert.equal(config.hermesTerminalBrokerPort, 8765);
  assert.equal(config.publicBaseUrl.href, 'https://prod.example.com/');
});

test('requires an exact private or loopback Bento IPv4 bind address', () => {
  for (const value of [
    '',
    '0.0.0.0',
    '::',
    '::1',
    'fd00::1',
    '203.0.113.10',
    'proxy.internal',
  ]) {
    assert.throws(
      () =>
        assertProductionAppEnv(
          validEnv({ OPEN_WORK_HUB_BENTO_BIND_HOST: value }),
        ),
      /exact private or loopback IPv4 address/,
    );
  }

  for (const value of [
    '10.20.30.40',
    '172.16.0.1',
    '192.168.1.10',
  ]) {
    assert.equal(
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_BENTO_BIND_HOST: value }),
      ).bentoBindHost,
      value,
    );
  }
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
    () => assertProductionAppEnv(validEnv({ OPEN_WORK_HUB_APP_PORT: '4200' })),
    /WEB_DEV_PORT/,
  );
  assert.throws(
    () => assertProductionAppEnv(validEnv({ OPEN_WORK_HUB_APP_PORT: '18084' })),
    /BENTO_PORT/,
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
      assertProductionAppEnv(validEnv({ OPEN_WORK_HUB_APP_PUBLIC_URL: value })),
    );
  }
});

test('requires a separate credential-free HTTPS Bento origin', () => {
  for (const value of [
    '',
    'http://bento.example.com',
    'https://localhost:18084',
    'https://user:password@bento.example.com',
    'https://prod.example.com',
  ]) {
    assert.throws(() =>
      assertProductionAppEnv(
        validEnv({ OPEN_WORK_HUB_BENTO_SERVER_URL: value }),
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

test('requires isolated production Hermes credentials', () => {
  for (const [key, value] of [
    ['OPENROUTER_API_KEY', ''],
    ['OPEN_WORK_HUB_HERMES_API_KEY', 'change-me'],
    ['OPEN_WORK_HUB_HERMES_MANAGEMENT_TOKEN', 'short'],
    ['OPEN_WORK_HUB_HERMES_MCP_SHARED_SECRET', 'dev-secret'],
  ]) {
    assert.throws(() => assertProductionAppEnv(validEnv({ [key]: value })));
  }
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_HERMES_MANAGEMENT_TOKEN:
            'production-hermes-runtime-secret-00000001',
        }),
      ),
    /must be distinct/,
  );
});

test('requires loopback Hermes endpoints on their declared ports', () => {
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_HERMES_RUNTIME_BASE_URL: 'http://0.0.0.0:8642',
        }),
      ),
    /loopback HTTP endpoint/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_HERMES_MCP_SERVER_URL:
            'http://127.0.0.1:8000/api/v1/tools/mcp',
        }),
      ),
    /internal Hermes MCP endpoint/,
  );
  assert.throws(
    () =>
      assertProductionAppEnv(
        validEnv({
          OPEN_WORK_HUB_HERMES_TERMINAL_BROKER_BASE_URL:
            'http://127.0.0.1:8766',
        }),
      ),
    /Hermes Terminal broker port/,
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

test('production compose does not add a second ingress proxy', async () => {
  const [composeText, releaseScript] = await Promise.all([
    readFile(
      new URL('../ops/compose/open-work-hub-prod.app.yml', import.meta.url),
      'utf8',
    ),
    readFile(new URL('./prod-app.sh', import.meta.url), 'utf8'),
  ]);
  assert.doesNotMatch(composeText, /open-work-hub-edge|ops\/edge/);
  assert.match(releaseScript, /--remove-orphans/);
});

test('production image build embeds the validated Bento public URL', async () => {
  const [dockerfile, releaseScript] = await Promise.all([
    readFile(new URL('../ops/app/Dockerfile', import.meta.url), 'utf8'),
    readFile(new URL('./prod-app.sh', import.meta.url), 'utf8'),
  ]);
  assert.match(dockerfile, /ARG OPEN_WORK_HUB_BENTO_SERVER_URL/);
  assert.match(
    dockerfile,
    /OPEN_WORK_HUB_BENTO_SERVER_URL="\$\{OPEN_WORK_HUB_BENTO_SERVER_URL\}"/,
  );
  assert.match(
    releaseScript,
    /--build-arg "OPEN_WORK_HUB_BENTO_SERVER_URL=\$bento_server_url"/,
  );
});

test('production runtime checks the fixed terminal broker port before mutation', async () => {
  const releaseScript = await readFile(
    new URL('./prod-app.sh', import.meta.url),
    'utf8',
  );
  assert.match(releaseScript, /require_terminal_broker_port_available/);
  assert.match(releaseScript, /refusing before build or migration/);
  assert.match(releaseScript, /expected_binding" == "127\.0\.0\.1:\$port"/);
});
