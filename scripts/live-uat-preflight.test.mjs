import assert from 'node:assert/strict';
import test from 'node:test';

import {
  assertJsonEndpoint,
  assertLoginPage,
  assertOkEndpoint,
  assertRuntimeStatus,
  assertWorkerPing,
  normalizePublicBaseUrl,
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
