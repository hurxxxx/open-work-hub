#!/usr/bin/env node

import { execFileSync } from 'node:child_process';
import { isIP } from 'node:net';
import { pathToFileURL } from 'node:url';

const REQUEST_TIMEOUT_MS = 10_000;

export function normalizePublicBaseUrl(
  rawValue,
  variableName = 'OPEN_WORK_HUB_UAT_BASE_URL',
) {
  if (!rawValue?.trim()) {
    throw new Error(`${variableName} is required`);
  }

  let url;
  try {
    url = new URL(rawValue);
  } catch {
    throw new Error(`${variableName} must be a valid URL`);
  }

  const hostname = url.hostname.toLowerCase().replace(/\.$/, '');
  if (url.protocol !== 'https:') {
    throw new Error(`${variableName} must use https`);
  }
  if (
    !hostname.includes('.') ||
    hostname === 'localhost' ||
    hostname.endsWith('.localhost') ||
    hostname.endsWith('.local') ||
    isIP(hostname) !== 0
  ) {
    throw new Error(`${variableName} must use a public domain name`);
  }
  if (url.username || url.password || url.search || url.hash) {
    throw new Error(
      `${variableName} must not contain credentials, query, or fragment`,
    );
  }
  if (url.pathname !== '/' && url.pathname !== '') {
    throw new Error(`${variableName} must be an origin without a path`);
  }

  return new URL(`${url.origin}/`);
}

export function assertRuntimeStatus(
  output,
  services = ['web', 'api', 'worker'],
) {
  for (const service of services) {
    if (!new RegExp(`^${service}\\s+running\\b`, 'm').test(output)) {
      throw new Error(`development ${service} service is not running`);
    }
  }
}

export function assertWorkerPing(output) {
  if (/no nodes replied/i.test(output) || !/\bpong\b/i.test(output)) {
    throw new Error('development worker did not answer the Celery ping');
  }
}

export async function readJsonEndpoint(label, url) {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    throw new Error(`${label} returned HTTP ${response.status}`);
  }
  const contentType = response.headers.get('content-type') ?? '';
  if (!contentType.toLowerCase().includes('application/json')) {
    throw new Error(`${label} did not return JSON`);
  }
  return response.json();
}

export async function assertJsonEndpoint(label, url, expectedStatus) {
  const body = await readJsonEndpoint(label, url);
  if (body?.status !== expectedStatus) {
    throw new Error(`${label} reported status ${String(body?.status)}`);
  }
  return body;
}

export async function assertJsonObjectEndpoint(label, url) {
  const body = await readJsonEndpoint(label, url);
  if (!body || typeof body !== 'object' || Array.isArray(body)) {
    throw new Error(`${label} did not return a JSON object`);
  }
  return body;
}

export function assertMatchingDevRuntime(localHealth, publicHealth) {
  const fields = ['version', 'environment', 'instance_id', 'runtime_revision'];
  for (const field of fields) {
    const localValue = localHealth?.[field];
    const publicValue = publicHealth?.[field];
    if (typeof localValue !== 'string' || !localValue) {
      throw new Error(`local health did not report ${field}`);
    }
    if (localValue !== publicValue) {
      throw new Error(`public health does not match local ${field}`);
    }
  }
  if (localHealth.environment !== 'development') {
    throw new Error('local health is not a development runtime');
  }
}

export async function assertLoginPage(label, url) {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    throw new Error(`${label} returned HTTP ${response.status}`);
  }
  const contentType = response.headers.get('content-type') ?? '';
  const body = await response.text();
  if (
    !contentType.toLowerCase().includes('text/html') ||
    !/(?:<!doctype html|<html)/i.test(body) ||
    !/<div[^>]+id=["']root["']/i.test(body)
  ) {
    throw new Error(`${label} did not return the rendered web shell`);
  }
}

export async function assertOkEndpoint(label, url) {
  const response = await fetchWithTimeout(url);
  if (!response.ok) {
    throw new Error(`${label} returned HTTP ${response.status}`);
  }
}

async function fetchWithTimeout(url) {
  try {
    return await fetch(url, {
      redirect: 'follow',
      signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
    });
  } catch (error) {
    const detail = error instanceof Error ? error.message : String(error);
    throw new Error(`request failed: ${detail}`);
  }
}

function localPort(name, fallback, env = process.env) {
  const value = env[name] ?? fallback;
  if (!/^\d+$/.test(value) || Number(value) < 1 || Number(value) > 65_535) {
    throw new Error(`${name} must be a valid TCP port`);
  }
  return value;
}

export async function runPublicDevSmoke({
  env = process.env,
  requireWorker = false,
  statusOutput,
  report = true,
} = {}) {
  const publicBaseUrl = normalizePublicBaseUrl(env.OPEN_WORK_HUB_UAT_BASE_URL);
  const apiPort = localPort('OPEN_WORK_HUB_API_DEV_PORT', '8001', env);
  const webPort = localPort('OPEN_WORK_HUB_WEB_DEV_PORT', '4200', env);
  const localApi = new URL(`http://127.0.0.1:${apiPort}/`);
  const localWeb = new URL(`http://127.0.0.1:${webPort}/`);

  const requiredServices = requireWorker
    ? ['web', 'api', 'worker']
    : ['web', 'api'];
  const status =
    statusOutput ??
    execFileSync(
      './dev.sh',
      requireWorker ? ['--with-worker', '--status'] : ['--status'],
      {
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'pipe'],
      },
    );
  assertRuntimeStatus(status, requiredServices);

  const [localHealth, publicHealth] = await Promise.all([
    assertJsonEndpoint('local health', new URL('/healthz', localApi), 'ok'),
    assertJsonEndpoint(
      'public health',
      new URL('/healthz', publicBaseUrl),
      'ok',
    ),
  ]);
  assertMatchingDevRuntime(localHealth, publicHealth);

  for (const [label, url] of [
    ['local readiness', new URL('/readyz', localApi)],
    ['public readiness', new URL('/readyz', publicBaseUrl)],
  ]) {
    await assertJsonEndpoint(label, url, 'ok');
  }
  await assertJsonObjectEndpoint(
    'local bootstrap',
    new URL('/api/v1/auth/bootstrap-status', localApi),
  );
  await assertJsonObjectEndpoint(
    'public bootstrap',
    new URL('/api/v1/auth/bootstrap-status', publicBaseUrl),
  );
  for (const [label, url] of [
    ['local root', new URL('/', localWeb)],
    ['local login', new URL('/login', localWeb)],
    ['public root', new URL('/', publicBaseUrl)],
    ['public login', new URL('/login', publicBaseUrl)],
  ]) {
    await assertLoginPage(label, url);
  }

  if (report) {
    process.stdout.write(
      `Public dev smoke passed for ${publicBaseUrl.origin}: local web and API are running, the public root/login/health/readiness/bootstrap surfaces are available, and public health matches the local development runtime.\n`,
    );
  }
  return { publicBaseUrl };
}

export async function runPreflight({ env = process.env } = {}) {
  const { publicBaseUrl } = await runPublicDevSmoke({
    env,
    requireWorker: true,
    report: false,
  });
  const objectStorageEndpoint = new URL(
    env.OPEN_WORK_HUB_MINIO_ENDPOINT ?? 'http://127.0.0.1:59010',
  );
  if (objectStorageEndpoint.username || objectStorageEndpoint.password) {
    throw new Error(
      'OPEN_WORK_HUB_MINIO_ENDPOINT must not contain credentials',
    );
  }

  let workerPing;
  try {
    workerPing = execFileSync(
      'uv',
      [
        'run',
        '--python',
        '3.12',
        'celery',
        '-A',
        'open_work_hub_worker.celery_app:celery_app',
        'inspect',
        'ping',
        '--timeout',
        '5',
      ],
      {
        cwd: new URL('../apps/worker/', import.meta.url),
        encoding: 'utf8',
        stdio: ['ignore', 'pipe', 'pipe'],
        timeout: 15_000,
      },
    );
  } catch {
    throw new Error('development worker did not answer the Celery ping');
  }
  assertWorkerPing(workerPing);

  await assertOkEndpoint(
    'object storage health',
    new URL('/minio/health/live', objectStorageEndpoint),
  );
  process.stdout.write(
    `UAT preflight passed for ${publicBaseUrl.origin}: web, api, worker ping, object storage, health, readiness, and the login HTML shell are available.\n`,
  );
}

const isMain =
  process.argv[1] && import.meta.url === pathToFileURL(process.argv[1]).href;
if (isMain) {
  const runner = process.argv.includes('--public-dev-smoke')
    ? runPublicDevSmoke
    : runPreflight;
  runner().catch((error) => {
    const detail = error instanceof Error ? error.message : String(error);
    process.stderr.write(`UAT preflight failed: ${detail}\n`);
    process.exitCode = 1;
  });
}
