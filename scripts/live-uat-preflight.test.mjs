import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertJsonEndpoint,
  assertJsonObjectEndpoint,
  assertLoginPage,
  assertMatchingDevRuntime,
  assertOkEndpoint,
  assertRuntimeStatus,
  assertWorkerPing,
  normalizePublicBaseUrl,
  runPublicDevSmoke,
} from './live-uat-preflight.mjs';

test('accepts only credential-free HTTPS public origins', () => {
  assert.equal(
    normalizePublicBaseUrl('https://owh.example.com').href,
    'https://owh.example.com/',
  );
  for (const value of [
    '',
    'http://owh.example.com',
    'https://localhost:4200',
    'https://127.0.0.1',
    'https://owh',
    'https://user:password@owh.example.com',
    'https://owh.example.com/app',
    'https://owh.example.com/?token=secret',
  ]) {
    assert.throws(() => normalizePublicBaseUrl(value));
  }
});

test('requires all three development services', () => {
  const ready = 'web    running\napi    running\nworker running\n';
  assert.doesNotThrow(() => assertRuntimeStatus(ready));
  assert.throws(
    () => assertRuntimeStatus('web running\napi running\n'),
    /worker/,
  );
  assert.doesNotThrow(() => assertWorkerPing('worker@example: OK\n  pong'));
  assert.throws(() =>
    assertWorkerPing('No nodes replied within time constraint'),
  );
  assert.doesNotThrow(() =>
    assertRuntimeStatus('web running\napi running\n', ['web', 'api']),
  );
});

test('requires public health to identify the local development runtime', () => {
  const health = {
    status: 'ok',
    version: '0.1.1',
    environment: 'development',
    instance_id: 'dev-api',
    runtime_revision: 'abc123',
  };
  assert.doesNotThrow(() => assertMatchingDevRuntime(health, { ...health }));
  assert.throws(
    () =>
      assertMatchingDevRuntime(health, {
        ...health,
        runtime_revision: 'stale-revision',
      }),
    /runtime_revision/,
  );
  assert.throws(
    () =>
      assertMatchingDevRuntime(
        { ...health, environment: 'production' },
        { ...health, environment: 'production' },
      ),
    /development runtime/,
  );
});

test('validates health JSON and the login HTML shell', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });

  globalThis.fetch = async () =>
    new Response(JSON.stringify({ status: 'ok' }), {
      headers: { 'content-type': 'application/json' },
    });
  await assertJsonEndpoint(
    'ready',
    new URL('https://owh.example.com/readyz'),
    'ok',
  );
  await assertOkEndpoint(
    'storage',
    new URL('https://storage.example.com/health'),
  );
  await assertJsonObjectEndpoint(
    'bootstrap',
    new URL('https://owh.example.com/api/v1/auth/bootstrap-status'),
  );

  globalThis.fetch = async () =>
    new Response(
      '<!doctype html><html><body><div id="root"></div></body></html>',
      {
        headers: { 'content-type': 'text/html; charset=utf-8' },
      },
    );
  await assertLoginPage('login', new URL('https://owh.example.com/login'));

  globalThis.fetch = async () =>
    new Response('<html><body>Service unavailable</body></html>', {
      headers: { 'content-type': 'text/html' },
    });
  await assert.rejects(
    assertLoginPage('login', new URL('https://owh.example.com/login')),
    /rendered web shell/,
  );
});

test('public dev smoke covers the local runtime and public ingress', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  const requested = [];
  globalThis.fetch = async (url) => {
    const parsed = new URL(url);
    requested.push(`${parsed.origin}${parsed.pathname}`);
    if (parsed.pathname === '/' || parsed.pathname === '/login') {
      return new Response(
        '<!doctype html><html><body><div id="root"></div></body></html>',
        { headers: { 'content-type': 'text/html' } },
      );
    }
    if (parsed.pathname === '/api/v1/auth/bootstrap-status') {
      return new Response(JSON.stringify({ initialized: true }), {
        headers: { 'content-type': 'application/json' },
      });
    }
    return new Response(
      JSON.stringify({
        status: 'ok',
        version: '0.1.1',
        environment: 'development',
        instance_id: 'dev-api',
        runtime_revision: 'abc123',
      }),
      { headers: { 'content-type': 'application/json' } },
    );
  };

  await runPublicDevSmoke({
    env: {
      OPEN_WORK_HUB_API_DEV_PORT: '8002',
      OPEN_WORK_HUB_UAT_BASE_URL: 'https://owh.example.com',
      OPEN_WORK_HUB_WEB_DEV_PORT: '4200',
    },
    statusOutput: 'web running\napi running\n',
    report: false,
  });

  assert.deepEqual(requested, [
    'http://127.0.0.1:8002/healthz',
    'https://owh.example.com/healthz',
    'http://127.0.0.1:8002/readyz',
    'https://owh.example.com/readyz',
    'http://127.0.0.1:8002/api/v1/auth/bootstrap-status',
    'https://owh.example.com/api/v1/auth/bootstrap-status',
    'http://127.0.0.1:4200/',
    'http://127.0.0.1:4200/login',
    'https://owh.example.com/',
    'https://owh.example.com/login',
  ]);
});

test('public dev smoke fails closed on a public bad gateway', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async (url) => {
    const parsed = new URL(url);
    if (parsed.origin === 'https://owh.example.com') {
      return new Response('Bad Gateway', {
        status: 502,
        headers: { 'content-type': 'text/plain' },
      });
    }
    return new Response(
      JSON.stringify({
        status: 'ok',
        version: '0.1.1',
        environment: 'development',
        instance_id: 'dev-api',
        runtime_revision: 'abc123',
      }),
      { headers: { 'content-type': 'application/json' } },
    );
  };

  await assert.rejects(
    runPublicDevSmoke({
      env: {
        OPEN_WORK_HUB_API_DEV_PORT: '8002',
        OPEN_WORK_HUB_UAT_BASE_URL: 'https://owh.example.com',
        OPEN_WORK_HUB_WEB_DEV_PORT: '4200',
      },
      statusOutput: 'web running\napi running\n',
      report: false,
    }),
    /public health returned HTTP 502/,
  );
});
