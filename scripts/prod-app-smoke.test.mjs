import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertBootstrapJson,
  assertDeploymentHealth,
  assertDeploymentReadiness,
  runProductionSmoke,
} from './prod-app-smoke.mjs';

test('validates production health and the expected revision', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        status: 'ok',
        environment: 'production',
        runtime_revision: 'abc123',
      }),
      { headers: { 'content-type': 'application/json' } },
    );

  await assertDeploymentHealth(
    'health',
    new URL('https://prod.example.com/healthz'),
    'abc123',
  );
  await assert.rejects(
    assertDeploymentHealth(
      'health',
      new URL('https://prod.example.com/healthz'),
      'other',
    ),
    /different runtime revision/,
  );
});

test('requires production readiness at the expected revision', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () =>
    new Response(
      JSON.stringify({
        status: 'ok',
        environment: 'production',
        runtime_revision: 'abc123',
      }),
      { headers: { 'content-type': 'application/json' } },
    );

  await assertDeploymentReadiness(
    'readiness',
    new URL('https://prod.example.com/readyz'),
    'abc123',
  );
});

test('requires bootstrap JSON objects', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  globalThis.fetch = async () =>
    new Response(JSON.stringify({ initialized: true }), {
      headers: { 'content-type': 'application/json' },
    });
  await assertBootstrapJson(
    'bootstrap',
    new URL('https://prod.example.com/api/v1/auth/bootstrap-status'),
  );
});

test('checks local and public surfaces in one smoke loop', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  const requestedPaths = [];
  globalThis.fetch = async (url) => {
    const parsed = new URL(url);
    requestedPaths.push(`${parsed.origin}${parsed.pathname}`);
    if (parsed.pathname === '/login') {
      return new Response(
        '<!doctype html><html><body><div id="root"></div></body></html>',
        { headers: { 'content-type': 'text/html' } },
      );
    }
    if (parsed.pathname === '/healthz' || parsed.pathname === '/readyz') {
      return new Response(
        JSON.stringify({
          status: 'ok',
          environment: 'production',
          runtime_revision: 'abc123',
        }),
        { headers: { 'content-type': 'application/json' } },
      );
    }
    return new Response(JSON.stringify({ initialized: true }), {
      headers: { 'content-type': 'application/json' },
    });
  };

  await runProductionSmoke({
    appPort: 8000,
    publicBaseUrl: new URL('https://prod.example.com/'),
    expectedRevision: 'abc123',
  });
  assert.deepEqual(requestedPaths, [
    'http://127.0.0.1:8000/healthz',
    'http://127.0.0.1:8000/readyz',
    'http://127.0.0.1:8000/api/v1/auth/bootstrap-status',
    'http://127.0.0.1:8000/login',
    'https://prod.example.com/healthz',
    'https://prod.example.com/readyz',
    'https://prod.example.com/api/v1/auth/bootstrap-status',
    'https://prod.example.com/login',
  ]);
});
