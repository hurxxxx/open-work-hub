import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertBootstrapJson,
  assertDeploymentHealth,
  assertDeploymentReadiness,
  assertEdgeHostRouting,
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

test('requires production routing and unknown-host rejection at the edge', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  const requestedHosts = [];
  globalThis.fetch = async (_url, options) => {
    const host = options?.headers?.Host;
    requestedHosts.push(host);
    if (host === 'unconfigured.invalid') {
      return new Response('', { status: 421 });
    }
    return new Response(
      JSON.stringify({
        status: 'ok',
        environment: 'production',
        runtime_revision: 'abc123',
      }),
      { headers: { 'content-type': 'application/json' } },
    );
  };

  await assertEdgeHostRouting({
    edgeListenPort: 4200,
    edgeProdHost: 'prod.example.com',
    expectedRevision: 'abc123',
  });
  assert.deepEqual(requestedHosts, [
    'prod.example.com',
    'unconfigured.invalid',
  ]);
});

test('checks local and public surfaces in one smoke loop', async (context) => {
  const originalFetch = globalThis.fetch;
  context.after(() => {
    globalThis.fetch = originalFetch;
  });
  const requestedPaths = [];
  globalThis.fetch = async (url, options) => {
    const parsed = new URL(url);
    const host = options?.headers?.Host;
    requestedPaths.push(
      `${parsed.origin}${parsed.pathname}${host ? `#${host}` : ''}`,
    );
    if (host === 'unconfigured.invalid') {
      return new Response('', { status: 421 });
    }
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
    edgeListenPort: 4200,
    edgeProdHost: 'prod.example.com',
    publicBaseUrl: new URL('https://prod.example.com/'),
    expectedRevision: 'abc123',
  });
  assert.deepEqual(requestedPaths, [
    'http://127.0.0.1:4200/healthz#prod.example.com',
    'http://127.0.0.1:4200/healthz#unconfigured.invalid',
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
